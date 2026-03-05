from __future__ import annotations

from ats_contracts.models import (
    ExecutionReport,
    ExecutionSimulationInput,
    ExecutionSimulationResult,
    ReasonCode,
    StateMode,
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _mode_thresholds(mode: StateMode) -> tuple[float, float, float]:
    if mode == StateMode.CAUTION:
        return 5.0, 30.0, 10.0
    return 8.0, 20.0, 15.0


def _liquidity_gate(input_data: ExecutionSimulationInput) -> bool:
    spread_limit, depth_mult, impact_limit = _mode_thresholds(input_data.mode)

    spread_ok = input_data.liquidity.spread_bps < spread_limit
    depth_ok = input_data.liquidity.depth_1pct_usd > input_data.order_size_usd * depth_mult
    impact_ok = input_data.liquidity.expected_impact_bps < impact_limit

    return spread_ok and depth_ok and impact_ok


def _circuit_breaker_triggered(input_data: ExecutionSimulationInput) -> bool:
    threshold_pct = max(2.0, 3.0 * input_data.rolling_1m_vol_pct)

    spread_limit, _, _ = _mode_thresholds(input_data.mode)
    spread_spike = input_data.liquidity.spread_bps > (spread_limit * 1.5)

    return input_data.one_minute_move_pct >= threshold_pct and spread_spike


def _kill_switch_mode(input_data: ExecutionSimulationInput) -> str | None:
    if not input_data.requested_kill_switch:
        return None

    timeout = min(60.0, 3.0 * input_data.avg_fill_time_seconds)
    if input_data.elapsed_unwind_seconds <= timeout:
        return "controlled_unwind"
    return "aggressive_liquidation"


def _fill_price(reference_price: float, side: str, total_cost_bps: float) -> float:
    impact_multiplier = total_cost_bps / 10_000.0

    if side.upper() == "BUY":
        return reference_price * (1.0 + impact_multiplier)
    return reference_price * (1.0 - impact_multiplier)


def simulate_execution(input_data: ExecutionSimulationInput) -> ExecutionSimulationResult:
    if input_data.mode in {StateMode.DEFENSE, StateMode.HALT} and not input_data.reduce_only:
        report = ExecutionReport(
            request_id=input_data.request_id,
            accepted=False,
            exchange_order_id=None,
            fill_price=None,
            slippage_bps=None,
            reason_codes=[ReasonCode.RISK_LIMIT],
        )
        return ExecutionSimulationResult(
            report=report,
            liquidity_gate_passed=False,
            circuit_breaker_triggered=False,
            kill_switch_mode=None,
            total_cost_bps=0.0,
            net_fill_price=None,
        )

    breaker = _circuit_breaker_triggered(input_data)
    if breaker:
        report = ExecutionReport(
            request_id=input_data.request_id,
            accepted=False,
            exchange_order_id=None,
            fill_price=None,
            slippage_bps=None,
            reason_codes=[ReasonCode.CIRCUIT_BREAKER],
        )
        return ExecutionSimulationResult(
            report=report,
            liquidity_gate_passed=False,
            circuit_breaker_triggered=True,
            kill_switch_mode=None,
            total_cost_bps=0.0,
            net_fill_price=None,
        )

    gate_passed = _liquidity_gate(input_data)
    if not gate_passed:
        report = ExecutionReport(
            request_id=input_data.request_id,
            accepted=False,
            exchange_order_id=None,
            fill_price=None,
            slippage_bps=None,
            reason_codes=[ReasonCode.LIQUIDITY_GATE],
        )
        return ExecutionSimulationResult(
            report=report,
            liquidity_gate_passed=False,
            circuit_breaker_triggered=False,
            kill_switch_mode=None,
            total_cost_bps=0.0,
            net_fill_price=None,
        )


    kill_mode = _kill_switch_mode(input_data)

    additional_slippage = 0.0
    if kill_mode == "aggressive_liquidation":
        additional_slippage = max(5.0, input_data.liquidity.expected_impact_bps)

    maker_discount = 0.40 if input_data.intent.maker_preferred and kill_mode is None else 0.0

    total_cost_bps = (
        input_data.commission_bps
        + input_data.slippage_bps
        + input_data.funding_bps
        + input_data.impact_bps
        + additional_slippage
        - maker_discount
    )
    total_cost_bps = _clamp(total_cost_bps, 0.0, 500.0)

    fill_price = _fill_price(input_data.reference_price, input_data.intent.side, total_cost_bps)

    report = ExecutionReport(
        request_id=input_data.request_id,
        accepted=True,
        exchange_order_id=f"sim-{input_data.request_id}",
        fill_price=round(fill_price, 8),
        slippage_bps=round(
            input_data.slippage_bps + input_data.impact_bps + additional_slippage,
            8,
        ),
        reason_codes=[ReasonCode.OK],
    )

    return ExecutionSimulationResult(
        report=report,
        liquidity_gate_passed=True,
        circuit_breaker_triggered=False,
        kill_switch_mode=kill_mode,
        total_cost_bps=round(total_cost_bps, 8),
        net_fill_price=round(fill_price, 8),
    )
