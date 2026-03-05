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
    def validate_probability_sum(self) -> "DecisionProposal":
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
