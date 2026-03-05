from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReasonCode(StrEnum):
    OK = "OK"
    NO_HORIZON_PASSED = "NO_HORIZON_PASSED"
    CONSTITUTION_BREACH = "CONSTITUTION_BREACH"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    LIQUIDITY_GATE = "LIQUIDITY_GATE"
    NO_TRADE_ZONE = "NO_TRADE_ZONE"
    RISK_LIMIT = "RISK_LIMIT"


class TradeAction(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


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
    reason_codes: list[ReasonCode]


class RiskDecision(BaseContract):
    request_id: str
    action: TradeAction
    size_usd: float = Field(ge=0.0)
    leverage: float = Field(ge=0.0)
    stop_loss_bps: int = Field(ge=0)
    time_stop_seconds: int = Field(ge=0)
    reason_codes: list[ReasonCode]


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
    reason_codes: list[ReasonCode]
