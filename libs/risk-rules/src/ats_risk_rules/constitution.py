from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ats_contracts.models import StateMode

DEFAULT_CONSTITUTION_PATH = Path("/home/deploy/ats/infra/config/constitution.v1.json")


class DrawdownThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    caution_pct: float = Field(ge=0.0, le=100.0)
    defense_pct: float = Field(ge=0.0, le=100.0)
    halt_pct: float = Field(ge=0.0, le=100.0)


class ModeLimit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_positions: int = Field(ge=0)
    max_leverage: float = Field(ge=0.0)
    risk_contribution_ceiling_pct: float = Field(ge=0.0)


class CooldownConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    post_defense_no_new_positions_hours: int = Field(ge=0)
    post_halt_shadow_only_hours: int = Field(ge=0)


class ConstitutionConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_capital_usd: float = Field(gt=0.0)
    max_drawdown_pct: float = Field(ge=0.0, le=100.0)
    max_single_position_loss_pct: float = Field(ge=0.0, le=100.0)
    daily_loss_limit_pct: float = Field(ge=0.0, le=100.0)
    drawdown_thresholds: DrawdownThresholds
    mode_limits: dict[StateMode, ModeLimit]
    cooldowns: CooldownConfig
    guard_precedence: list[str]


def load_constitution(path: Path = DEFAULT_CONSTITUTION_PATH) -> ConstitutionConfig:
    if not path.exists():
        raise FileNotFoundError(f"Constitution file not found: {path}")

    raw_json = path.read_text(encoding="utf-8")
    return ConstitutionConfig.model_validate_json(raw_json)
