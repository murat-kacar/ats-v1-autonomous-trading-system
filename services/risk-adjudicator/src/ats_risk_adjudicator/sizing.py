from __future__ import annotations

from ats_contracts.models import (
    RiskEnvelopeInput,
    RiskEnvelopeResult,
    RiskEvaluationInput,
    StateMode,
)
from ats_risk_rules.constitution import ConstitutionConfig


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_risk_envelope(
    input_data: RiskEnvelopeInput,
    constitution: ConstitutionConfig,
) -> RiskEnvelopeResult:
    mode_limit = constitution.mode_limits[input_data.state_mode]

    ntz_blocked = (
        input_data.ntz_uncertainty_high
        and input_data.ntz_correlation_abnormal
        and input_data.ntz_funding_extreme
        and not input_data.reduce_only
    )

    uncertainty_scale = _clamp(1.0 - input_data.uncertainty_score, 0.0, 1.0)
    base_size_usd = input_data.equity_usd * input_data.fractional_kelly * uncertainty_scale

    max_single_loss_usd = (
        constitution.total_capital_usd * constitution.max_single_position_loss_pct / 100.0
    )

    stop_loss_fraction = max(input_data.stop_loss_bps / 10_000.0, 1e-6)
    max_size_by_loss_usd = max_single_loss_usd / stop_loss_fraction

    proposed_size_usd = min(base_size_usd, max_size_by_loss_usd)
    if input_data.reduce_only and proposed_size_usd <= 0.0:
        proposed_size_usd = min(input_data.equity_usd, max_size_by_loss_usd)

    max_lev = mode_limit.max_leverage
    if max_lev <= 1.0:
        proposed_leverage = max_lev
    else:
        proposed_leverage = min(
            max_lev,
            1.0 + (input_data.decision.confidence * (max_lev - 1.0)),
        )
    if input_data.reduce_only and proposed_leverage <= 0.0:
        proposed_leverage = 1.0

    risk_limits_passed = True

    if not input_data.reduce_only and input_data.state_mode == StateMode.HALT:
        risk_limits_passed = False
    if not input_data.reduce_only and mode_limit.max_positions <= 0:
        risk_limits_passed = False
    if not input_data.reduce_only and input_data.open_positions >= mode_limit.max_positions:
        risk_limits_passed = False
    if input_data.reduce_only and input_data.open_positions <= 0:
        risk_limits_passed = False
    if (
        not input_data.reduce_only
        and input_data.daily_loss_pct >= constitution.daily_loss_limit_pct
    ):
        risk_limits_passed = False
    if proposed_size_usd <= 0.0 or proposed_leverage <= 0.0:
        risk_limits_passed = False

    evaluation_input = RiskEvaluationInput(
        request_id=input_data.request_id,
        decision=input_data.decision,
        proposed_size_usd=round(proposed_size_usd, 8),
        proposed_leverage=round(proposed_leverage, 8),
        stop_loss_bps=input_data.stop_loss_bps,
        time_stop_seconds=input_data.time_stop_seconds,
        constitution_breach=input_data.constitution_breach,
        circuit_breaker_triggered=input_data.circuit_breaker_triggered,
        liquidity_gate_passed=input_data.liquidity_gate_passed,
        ntz_blocked=ntz_blocked,
        risk_limits_passed=risk_limits_passed,
        reduce_only=input_data.reduce_only,
    )

    return RiskEnvelopeResult(
        evaluation_input=evaluation_input,
        ntz_blocked=ntz_blocked,
        proposed_size_usd=evaluation_input.proposed_size_usd,
        proposed_leverage=evaluation_input.proposed_leverage,
        risk_limits_passed=risk_limits_passed,
    )
