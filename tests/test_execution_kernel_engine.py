from ats_contracts.models import (
    ExecutionIntent,
    ExecutionSimulationInput,
    LiquidityGateInput,
    ReasonCode,
    StateMode,
)
from ats_execution_kernel.engine import simulate_execution


def _base_input() -> ExecutionSimulationInput:
    return ExecutionSimulationInput(
        request_id="ex-1",
        intent=ExecutionIntent(
            request_id="ex-1",
            symbol="BTCUSDT",
            side="BUY",
            qty=0.01,
            maker_preferred=True,
        ),
        reference_price=100_000.0,
        order_size_usd=1_000.0,
        mode=StateMode.NORMAL,
        reduce_only=False,
        liquidity=LiquidityGateInput(
            spread_bps=4.0,
            depth_1pct_usd=25_000.0,
            expected_impact_bps=5.0,
        ),
        rolling_1m_vol_pct=0.4,
        one_minute_move_pct=0.8,
        avg_fill_time_seconds=8.0,
        elapsed_unwind_seconds=0.0,
        commission_bps=2.0,
        slippage_bps=1.0,
        funding_bps=0.2,
        impact_bps=0.8,
        requested_kill_switch=False,
    )


def test_simulation_passes_maker_first_path() -> None:
    result = simulate_execution(_base_input())

    assert result.report.accepted is True
    assert result.report.reason_codes == [ReasonCode.OK]
    assert result.liquidity_gate_passed is True
    assert result.circuit_breaker_triggered is False
    assert result.kill_switch_mode is None
    assert result.total_cost_bps == 3.6


def test_liquidity_gate_blocks_execution() -> None:
    input_data = _base_input().model_copy(
        update={
            "liquidity": LiquidityGateInput(
                spread_bps=12.0,
                depth_1pct_usd=10_000.0,
                expected_impact_bps=18.0,
            )
        }
    )

    result = simulate_execution(input_data)

    assert result.report.accepted is False
    assert result.report.reason_codes == [ReasonCode.LIQUIDITY_GATE]


def test_circuit_breaker_blocks_execution() -> None:
    input_data = _base_input().model_copy(
        update={
            "one_minute_move_pct": 2.6,
            "rolling_1m_vol_pct": 0.4,
            "liquidity": LiquidityGateInput(
                spread_bps=13.0,
                depth_1pct_usd=30_000.0,
                expected_impact_bps=5.0,
            ),
        }
    )

    result = simulate_execution(input_data)

    assert result.report.accepted is False
    assert result.circuit_breaker_triggered is True
    assert result.report.reason_codes == [ReasonCode.CIRCUIT_BREAKER]


def test_kill_switch_aggressive_mode_adds_cost() -> None:
    input_data = _base_input().model_copy(
        update={
            "requested_kill_switch": True,
            "avg_fill_time_seconds": 10.0,
            "elapsed_unwind_seconds": 45.0,
        }
    )

    result = simulate_execution(input_data)

    assert result.report.accepted is True
    assert result.kill_switch_mode == "aggressive_liquidation"
    assert result.total_cost_bps > 8.0


def test_defense_mode_requires_reduce_only() -> None:
    input_data = _base_input().model_copy(
        update={
            "mode": StateMode.DEFENSE,
            "reduce_only": False,
        }
    )

    result = simulate_execution(input_data)

    assert result.report.accepted is False
    assert result.report.reason_codes == [ReasonCode.RISK_LIMIT]
