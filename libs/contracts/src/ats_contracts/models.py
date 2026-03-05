from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReasonCode(StrEnum):
    OK = "OK"
    NO_HORIZON_PASSED = "NO_HORIZON_PASSED"
    CONSTITUTION_BREACH = "CONSTITUTION_BREACH"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    LIQUIDITY_GATE = "LIQUIDITY_GATE"
    NO_TRADE_ZONE = "NO_TRADE_ZONE"
    RISK_LIMIT = "RISK_LIMIT"
    STALE_DATA = "STALE_DATA"


class TradeAction(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class StateMode(StrEnum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    DEFENSE = "DEFENSE"
    HALT = "HALT"


class TradingGate(StrEnum):
    LIVE = "LIVE"
    NO_NEW_POSITIONS = "NO_NEW_POSITIONS"
    SHADOW_ONLY = "SHADOW_ONLY"
    HALTED = "HALTED"


class BaseContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidencePacket(BaseContract):
    request_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    uncertainty_score: float = Field(ge=0.0, le=1.0)
    data_quality_score: float = Field(ge=0.0, le=1.0)
    feature_values: dict[str, float]
    risk_flags: list[str]
    source_reliability: dict[str, float]


class DecisionProposal(BaseContract):
    request_id: str
    p_up: float = Field(ge=0.0, le=1.0)
    p_down: float = Field(ge=0.0, le=1.0)
    p_flat: float = Field(ge=0.0, le=1.0)
    edge_bps_after_cost: float
    confidence: float = Field(ge=0.0, le=1.0)
    selected_horizon: str
    reason_codes: list[ReasonCode] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_probability_sum(self) -> DecisionProposal:
        total = self.p_up + self.p_down + self.p_flat
        if abs(total - 1.0) > 1e-3:
            raise ValueError("DecisionProposal probabilities must sum to 1.0 (+/- 1e-3)")
        return self


class RiskEvaluationInput(BaseContract):
    request_id: str
    decision: DecisionProposal
    proposed_size_usd: float = Field(ge=0.0)
    proposed_leverage: float = Field(ge=0.0)
    stop_loss_bps: int = Field(default=0, ge=0)
    time_stop_seconds: int = Field(default=0, ge=0)
    constitution_breach: bool = False
    circuit_breaker_triggered: bool = False
    liquidity_gate_passed: bool = True
    ntz_blocked: bool = False
    risk_limits_passed: bool = True


class RiskDecision(BaseContract):
    request_id: str
    action: TradeAction
    size_usd: float = Field(ge=0.0)
    leverage: float = Field(ge=0.0)
    stop_loss_bps: int = Field(default=0, ge=0)
    time_stop_seconds: int = Field(default=0, ge=0)
    reason_codes: list[ReasonCode] = Field(min_length=1)


class StateSnapshot(BaseContract):
    mode: StateMode = StateMode.NORMAL
    defense_cooldown_until: datetime | None = None
    halt_shadow_until: datetime | None = None


class StateEvaluationInput(BaseContract):
    snapshot: StateSnapshot = Field(default_factory=StateSnapshot)
    event_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    drawdown_pct: float = Field(ge=0.0, le=100.0)
    uncertainty_spike: bool = False
    critical_correlation: bool = False
    constitution_breach: bool = False
    manual_resume: bool = False


class StateEvaluationResult(BaseContract):
    snapshot: StateSnapshot
    trading_gate: TradingGate
    transitioned: bool
    transition_reason: str


class DepthLevel(BaseContract):
    price: float = Field(gt=0.0)
    qty: float = Field(ge=0.0)


class BookTicker(BaseContract):
    symbol: str
    event_time: datetime | None = None
    bid_price: float = Field(gt=0.0)
    bid_qty: float = Field(ge=0.0)
    ask_price: float = Field(gt=0.0)
    ask_qty: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_spread(self) -> BookTicker:
        if self.ask_price < self.bid_price:
            raise ValueError("ask_price must be >= bid_price")
        return self


class DepthSnapshot(BaseContract):
    symbol: str
    event_time: datetime | None = None
    bids: list[DepthLevel] = Field(min_length=1)
    asks: list[DepthLevel] = Field(min_length=1)


class TradeTick(BaseContract):
    trade_id: int
    price: float = Field(gt=0.0)
    qty: float = Field(gt=0.0)
    is_buyer_maker: bool
    trade_time: datetime


class FundingSnapshot(BaseContract):
    symbol: str
    funding_rate: float
    mark_price: float = Field(gt=0.0)
    event_time: datetime | None = None
    next_funding_time: datetime | None = None


class MarketDataSnapshot(BaseContract):
    symbol: str
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    book_ticker: BookTicker
    depth_snapshot: DepthSnapshot
    trades: list[TradeTick] = Field(min_length=1)
    funding: FundingSnapshot | None = None


class DataSanityInput(BaseContract):
    market_snapshot: MarketDataSnapshot
    max_feed_delay_ms: int = Field(default=1500, ge=1, le=60000)
    outlier_tick_z_threshold: float = Field(default=6.0, ge=1.0, le=25.0)
    volume_z_threshold: float = Field(default=4.0, ge=1.0, le=25.0)
    volume_baseline_qty_1m: float | None = Field(default=None, ge=0.0)
    volume_baseline_std_1m: float | None = Field(default=None, gt=0.0)


class DataSanityDiagnostics(BaseContract):
    feed_delay_ms: float | None
    feed_delay_anomaly: bool
    outlier_tick_anomaly: bool
    volume_anomaly: bool
    volume_z_score: float | None
    anomaly_flags: list[str]
    uncertainty_contrib: float = Field(ge=0.0, le=1.0)
    data_quality_score: float = Field(ge=0.0, le=1.0)


class DataLayerResult(BaseContract):
    market_snapshot: MarketDataSnapshot
    diagnostics: DataSanityDiagnostics


class MarketDataFetchInput(BaseContract):
    symbol: str = "BTCUSDT"
    depth_limit: int = Field(default=100, ge=5, le=1000)
    trade_limit: int = Field(default=200, ge=20, le=1000)
    max_feed_delay_ms: int = Field(default=1500, ge=1, le=60000)
    outlier_tick_z_threshold: float = Field(default=6.0, ge=1.0, le=25.0)
    volume_z_threshold: float = Field(default=4.0, ge=1.0, le=25.0)
    volume_baseline_qty_1m: float | None = Field(default=None, ge=0.0)
    volume_baseline_std_1m: float | None = Field(default=None, gt=0.0)


class HorizonWindowCandidate(BaseContract):
    horizon: str
    window_days: int = Field(ge=1)
    sample_size: int = Field(ge=0)
    walk_forward_score: float
    embargo_passed: bool = True
    gross_edge_bps: float
    fee_bps: float = Field(default=0.0, ge=0.0)
    slippage_bps: float = Field(default=0.0, ge=0.0)
    funding_bps: float = Field(default=0.0, ge=0.0)
    impact_bps: float = Field(default=0.0, ge=0.0)


class DecisionCoreInput(BaseContract):
    request_id: str
    evidence: EvidencePacket
    candidates: list[HorizonWindowCandidate] = Field(default_factory=list)
    min_sample_size: int = Field(default=150, ge=1)
    allowed_horizons: list[str] = Field(default_factory=lambda: ["5m", "15m", "1h", "4h"])
    allowed_windows_days: list[int] = Field(default_factory=lambda: [30, 60, 120])


class ExecutionIntent(BaseContract):
    request_id: str
    symbol: str
    side: str
    qty: float = Field(gt=0.0)
    maker_preferred: bool


class ExecutionReport(BaseContract):
    request_id: str
    accepted: bool
    exchange_order_id: str | None = None
    fill_price: float | None = None
    slippage_bps: float | None = None
    reason_codes: list[ReasonCode] = Field(min_length=1)
