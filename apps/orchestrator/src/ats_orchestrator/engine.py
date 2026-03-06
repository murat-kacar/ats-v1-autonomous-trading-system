from __future__ import annotations

from ats_contracts.models import (
    DataLayerResult,
    DataSanityInput,
    DecisionCoreInput,
    DecisionProposal,
    EvidencePacket,
    ExecutionIntent,
    ExecutionReport,
    ExecutionSimulationInput,
    ExecutionSimulationResult,
    HorizonWindowCandidate,
    LiquidityGateInput,
    MarketDataFetchInput,
    MonitoringEvaluationInput,
    MonitoringEvaluationResult,
    ReasonCode,
    RiskDecision,
    RiskEnvelopeInput,
    RiskEnvelopeResult,
    StateMode,
)
from ats_decision_core.engine import build_decision_proposal
from ats_evidence_swarm.binance_um import BinanceUMPublicClient
from ats_evidence_swarm.experts import compile_evidence_packet
from ats_evidence_swarm.sanity import evaluate_data_sanity
from ats_execution_kernel.engine import simulate_execution
from ats_monitoring.engine import evaluate_monitoring
from ats_risk_adjudicator.sizing import build_risk_envelope
from ats_risk_rules.constitution import ConstitutionConfig
from ats_risk_rules.rules import decide_risk_decision
from pydantic import BaseModel, ConfigDict, Field


class PaperRiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equity_usd: float = Field(default=1_000.0, gt=0.0)
    state_mode: StateMode = StateMode.NORMAL
    uncertainty_score: float | None = Field(default=None, ge=0.0, le=1.0)
    fractional_kelly: float = Field(default=0.05, ge=0.0, le=1.0)
    daily_loss_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    open_positions: int = Field(default=0, ge=0)
    stop_loss_bps: int = Field(default=150, ge=1)
    time_stop_seconds: int = Field(default=900, ge=0)
    circuit_breaker_triggered: bool = False
    liquidity_gate_passed: bool = True
    ntz_uncertainty_high: bool | None = None
    ntz_correlation_abnormal: bool | None = None
    ntz_funding_extreme: bool | None = None
    constitution_breach: bool = False


class PaperExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: StateMode | None = None
    reduce_only: bool | None = None
    reference_price: float | None = Field(default=None, gt=0.0)
    liquidity: LiquidityGateInput | None = None
    rolling_1m_vol_pct: float | None = Field(default=None, ge=0.0)
    one_minute_move_pct: float | None = Field(default=None, ge=0.0)
    avg_fill_time_seconds: float = Field(default=8.0, gt=0.0)
    elapsed_unwind_seconds: float = Field(default=0.0, ge=0.0)
    commission_bps: float = Field(default=2.0, ge=0.0)
    slippage_bps: float = Field(default=1.0, ge=0.0)
    funding_bps: float = 0.0
    impact_bps: float = Field(default=0.8, ge=0.0)
    requested_kill_switch: bool = False
    maker_preferred: bool = True


class PaperMonitoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recent_trade_pnls: list[float] = Field(default_factory=lambda: [0.0], min_length=1)
    baseline_pnl_mean: float = 0.0
    baseline_pnl_std: float = Field(default=1.0, gt=0.0)
    ci_coverage: float = Field(default=0.75, ge=0.0, le=1.0)
    brier_score: float = Field(default=0.2, ge=0.0)
    baseline_brier_score: float = Field(default=0.2, gt=0.0)


class PaperRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    symbol: str = "BTCUSDT"
    data_layer_override: DataLayerResult | None = None
    fetch_input: MarketDataFetchInput | None = None
    decision_candidates: list[HorizonWindowCandidate] = Field(default_factory=list)
    min_sample_size: int = Field(default=150, ge=1)
    allowed_horizons: list[str] = Field(default_factory=lambda: ["5m", "15m", "1h", "4h"])
    allowed_windows_days: list[int] = Field(default_factory=lambda: [30, 60, 120])
    risk: PaperRiskConfig = Field(default_factory=PaperRiskConfig)
    execution: PaperExecutionConfig = Field(default_factory=PaperExecutionConfig)
    monitoring: PaperMonitoringConfig = Field(default_factory=PaperMonitoringConfig)


class PaperRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    symbol: str
    used_live_data: bool
    data_layer: DataLayerResult
    evidence: EvidencePacket
    decision: DecisionProposal
    risk_envelope: RiskEnvelopeResult
    risk_decision: RiskDecision
    execution_result: ExecutionSimulationResult
    monitoring_result: MonitoringEvaluationResult


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _mid_price(snapshot: DataLayerResult) -> float:
    bid = float(snapshot.market_snapshot.book_ticker.bid_price)
    ask = float(snapshot.market_snapshot.book_ticker.ask_price)
    return (bid + ask) / 2.0


def _derived_liquidity(snapshot: DataLayerResult) -> LiquidityGateInput:
    mid = _mid_price(snapshot)
    bid = snapshot.market_snapshot.book_ticker.bid_price
    ask = snapshot.market_snapshot.book_ticker.ask_price

    spread_bps = 0.0 if mid <= 0.0 else ((ask - bid) / mid) * 10_000.0

    bids = snapshot.market_snapshot.depth_snapshot.bids[:5]
    asks = snapshot.market_snapshot.depth_snapshot.asks[:5]
    depth_notional = sum(level.qty * mid for level in bids + asks)

    implied_impact = max(0.1, min(30.0, spread_bps * 0.8))

    return LiquidityGateInput(
        spread_bps=spread_bps,
        depth_1pct_usd=depth_notional,
        expected_impact_bps=implied_impact,
    )


def _auto_candidates(evidence: EvidencePacket) -> list[HorizonWindowCandidate]:
    momentum = abs(evidence.feature_values.get("trend_momentum", 0.0))
    volatility = abs(evidence.feature_values.get("volatility_realized_vol", 0.0))

    base_edge = max(1.8, 4.0 + (momentum * 6_000.0) - (volatility * 4_500.0))
    wf = _clamp(0.8 + (momentum * 180.0), 0.4, 1.6)

    return [
        HorizonWindowCandidate(
            horizon="5m",
            window_days=30,
            sample_size=180,
            walk_forward_score=wf * 0.85,
            embargo_passed=True,
            gross_edge_bps=base_edge * 0.85,
            fee_bps=2.0,
            slippage_bps=1.2,
            funding_bps=0.4,
            impact_bps=0.9,
        ),
        HorizonWindowCandidate(
            horizon="15m",
            window_days=60,
            sample_size=240,
            walk_forward_score=wf,
            embargo_passed=True,
            gross_edge_bps=base_edge,
            fee_bps=1.8,
            slippage_bps=1.0,
            funding_bps=0.4,
            impact_bps=0.8,
        ),
        HorizonWindowCandidate(
            horizon="1h",
            window_days=120,
            sample_size=300,
            walk_forward_score=wf * 0.9,
            embargo_passed=True,
            gross_edge_bps=base_edge * 1.05,
            fee_bps=1.8,
            slippage_bps=1.1,
            funding_bps=0.5,
            impact_bps=1.0,
        ),
    ]


def _derive_side(decision: DecisionProposal) -> str | None:
    top = max(decision.p_up, decision.p_down, decision.p_flat)
    if top == decision.p_flat:
        return None
    if decision.p_up >= decision.p_down:
        return "BUY"
    return "SELL"


def _risk_ntz_uncertainty(mode: StateMode, uncertainty: float) -> bool:
    threshold = 0.6 if mode == StateMode.CAUTION else 0.7
    return uncertainty > threshold


def _to_execution_denied(request_id: str, reason: ReasonCode) -> ExecutionSimulationResult:
    report = ExecutionReport(
        request_id=request_id,
        accepted=False,
        exchange_order_id=None,
        fill_price=None,
        slippage_bps=None,
        reason_codes=[reason],
    )
    return ExecutionSimulationResult(
        report=report,
        liquidity_gate_passed=False,
        circuit_breaker_triggered=False,
        kill_switch_mode=None,
        total_cost_bps=0.0,
        net_fill_price=None,
    )


async def _build_data_layer(
    input_data: PaperRunInput,
    market_client: BinanceUMPublicClient,
) -> tuple[DataLayerResult, bool]:
    if input_data.data_layer_override is not None:
        return input_data.data_layer_override, False

    fetch = input_data.fetch_input or MarketDataFetchInput(symbol=input_data.symbol)
    symbol = input_data.symbol.upper().strip()

    snapshot = await market_client.fetch_snapshot(
        symbol=symbol,
        depth_limit=fetch.depth_limit,
        trade_limit=fetch.trade_limit,
    )

    diagnostics = evaluate_data_sanity(
        DataSanityInput(
            market_snapshot=snapshot,
            max_feed_delay_ms=fetch.max_feed_delay_ms,
            outlier_tick_z_threshold=fetch.outlier_tick_z_threshold,
            volume_z_threshold=fetch.volume_z_threshold,
            volume_baseline_qty_1m=fetch.volume_baseline_qty_1m,
            volume_baseline_std_1m=fetch.volume_baseline_std_1m,
        )
    )

    return DataLayerResult(market_snapshot=snapshot, diagnostics=diagnostics), True


async def run_paper_cycle(
    input_data: PaperRunInput,
    constitution: ConstitutionConfig,
    market_client: BinanceUMPublicClient,
) -> PaperRunResult:
    data_layer, used_live_data = await _build_data_layer(input_data, market_client)

    evidence = compile_evidence_packet(
        request_id=input_data.request_id,
        data_layer=data_layer,
    )

    candidates = input_data.decision_candidates or _auto_candidates(evidence)

    decision = build_decision_proposal(
        DecisionCoreInput(
            request_id=input_data.request_id,
            evidence=evidence,
            candidates=candidates,
            min_sample_size=input_data.min_sample_size,
            allowed_horizons=input_data.allowed_horizons,
            allowed_windows_days=input_data.allowed_windows_days,
        )
    )

    uncertainty = input_data.risk.uncertainty_score
    if uncertainty is None:
        uncertainty = evidence.uncertainty_score

    ntz_uncertainty = input_data.risk.ntz_uncertainty_high
    if ntz_uncertainty is None:
        ntz_uncertainty = _risk_ntz_uncertainty(input_data.risk.state_mode, uncertainty)

    ntz_correlation = input_data.risk.ntz_correlation_abnormal
    if ntz_correlation is None:
        corr = abs(evidence.feature_values.get("macro_correlation_price_volume_corr", 0.0))
        ntz_correlation = corr > 0.85

    ntz_funding = input_data.risk.ntz_funding_extreme
    if ntz_funding is None:
        ntz_funding = "FUNDING_EXTREME" in evidence.risk_flags

    envelope = build_risk_envelope(
        RiskEnvelopeInput(
            request_id=input_data.request_id,
            decision=decision,
            equity_usd=input_data.risk.equity_usd,
            state_mode=input_data.risk.state_mode,
            uncertainty_score=uncertainty,
            fractional_kelly=input_data.risk.fractional_kelly,
            daily_loss_pct=input_data.risk.daily_loss_pct,
            open_positions=input_data.risk.open_positions,
            stop_loss_bps=input_data.risk.stop_loss_bps,
            time_stop_seconds=input_data.risk.time_stop_seconds,
            circuit_breaker_triggered=input_data.risk.circuit_breaker_triggered,
            liquidity_gate_passed=input_data.risk.liquidity_gate_passed,
            ntz_uncertainty_high=ntz_uncertainty,
            ntz_correlation_abnormal=ntz_correlation,
            ntz_funding_extreme=ntz_funding,
            constitution_breach=input_data.risk.constitution_breach,
        ),
        constitution,
    )

    risk_decision = decide_risk_decision(envelope.evaluation_input)

    side = _derive_side(decision)
    execution_result: ExecutionSimulationResult

    if risk_decision.action.value != "ALLOW":
        execution_result = _to_execution_denied(
            request_id=input_data.request_id,
            reason=risk_decision.reason_codes[0],
        )
    elif side is None:
        execution_result = _to_execution_denied(
            request_id=input_data.request_id,
            reason=ReasonCode.NO_HORIZON_PASSED,
        )
    else:
        reference_price = input_data.execution.reference_price or _mid_price(data_layer)
        qty = max(1e-9, risk_decision.size_usd / reference_price)

        mode = input_data.execution.mode or input_data.risk.state_mode
        reduce_only = input_data.execution.reduce_only
        if reduce_only is None:
            reduce_only = mode in {StateMode.DEFENSE, StateMode.HALT}

        liquidity = input_data.execution.liquidity or _derived_liquidity(data_layer)

        rolling_vol = input_data.execution.rolling_1m_vol_pct
        if rolling_vol is None:
            rolling_vol = abs(evidence.feature_values.get("volatility_realized_vol", 0.0)) * 100.0

        one_minute_move = input_data.execution.one_minute_move_pct
        if one_minute_move is None:
            one_minute_move = rolling_vol * 0.75

        execution_result = simulate_execution(
            ExecutionSimulationInput(
                request_id=input_data.request_id,
                intent=ExecutionIntent(
                    request_id=input_data.request_id,
                    symbol=input_data.symbol.upper().strip(),
                    side=side,
                    qty=qty,
                    maker_preferred=input_data.execution.maker_preferred,
                ),
                reference_price=reference_price,
                order_size_usd=risk_decision.size_usd,
                mode=mode,
                reduce_only=reduce_only,
                liquidity=liquidity,
                rolling_1m_vol_pct=rolling_vol,
                one_minute_move_pct=one_minute_move,
                avg_fill_time_seconds=input_data.execution.avg_fill_time_seconds,
                elapsed_unwind_seconds=input_data.execution.elapsed_unwind_seconds,
                commission_bps=input_data.execution.commission_bps,
                slippage_bps=input_data.execution.slippage_bps,
                funding_bps=input_data.execution.funding_bps,
                impact_bps=input_data.execution.impact_bps,
                requested_kill_switch=input_data.execution.requested_kill_switch,
            )
        )

    pnl_series = list(input_data.monitoring.recent_trade_pnls)
    if execution_result.report.accepted:
        realized_edge_bps = decision.edge_bps_after_cost - execution_result.total_cost_bps
        trade_pnl = risk_decision.size_usd * (realized_edge_bps / 10_000.0)
        pnl_series.append(trade_pnl)

    if len(pnl_series) > 200:
        pnl_series = pnl_series[-200:]

    monitoring_result = evaluate_monitoring(
        MonitoringEvaluationInput(
            request_id=input_data.request_id,
            recent_trade_pnls=pnl_series,
            baseline_pnl_mean=input_data.monitoring.baseline_pnl_mean,
            baseline_pnl_std=input_data.monitoring.baseline_pnl_std,
            ci_coverage=input_data.monitoring.ci_coverage,
            brier_score=input_data.monitoring.brier_score,
            baseline_brier_score=input_data.monitoring.baseline_brier_score,
        )
    )

    return PaperRunResult(
        request_id=input_data.request_id,
        symbol=input_data.symbol.upper().strip(),
        used_live_data=used_live_data,
        data_layer=data_layer,
        evidence=evidence,
        decision=decision,
        risk_envelope=envelope,
        risk_decision=risk_decision,
        execution_result=execution_result,
        monitoring_result=monitoring_result,
    )
