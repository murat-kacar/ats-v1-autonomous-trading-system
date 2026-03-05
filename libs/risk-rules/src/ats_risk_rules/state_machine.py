from __future__ import annotations

from datetime import timedelta

from ats_contracts.models import (
    StateEvaluationInput,
    StateEvaluationResult,
    StateMode,
    StateSnapshot,
    TradingGate,
)

from .constitution import ConstitutionConfig


def _normalize_cooldown(until, now):
    if until is None:
        return None
    if now >= until:
        return None
    return until


def _derive_target_mode(input_data: StateEvaluationInput, config: ConstitutionConfig) -> tuple[StateMode, str]:
    if input_data.constitution_breach or input_data.drawdown_pct > config.max_drawdown_pct:
        return StateMode.HALT, "HALT_TRIGGERED"

    thresholds = config.drawdown_thresholds

    if input_data.drawdown_pct > thresholds.defense_pct or input_data.critical_correlation:
        return StateMode.DEFENSE, "DEFENSE_TRIGGERED"

    if input_data.drawdown_pct > thresholds.caution_pct or input_data.uncertainty_spike:
        return StateMode.CAUTION, "CAUTION_TRIGGERED"

    return StateMode.NORMAL, "NORMAL_CONDITIONS"


def _compute_gate(snapshot: StateSnapshot, event_time) -> TradingGate:
    if snapshot.mode == StateMode.HALT:
        return TradingGate.HALTED

    if snapshot.halt_shadow_until is not None and event_time < snapshot.halt_shadow_until:
        return TradingGate.SHADOW_ONLY

    if snapshot.defense_cooldown_until is not None and event_time < snapshot.defense_cooldown_until:
        return TradingGate.NO_NEW_POSITIONS

    return TradingGate.LIVE


def evaluate_state_transition(
    input_data: StateEvaluationInput,
    config: ConstitutionConfig,
) -> StateEvaluationResult:
    current = input_data.snapshot
    event_time = input_data.event_time

    target_mode, transition_reason = _derive_target_mode(input_data, config)

    next_mode = target_mode
    if current.mode == StateMode.HALT and target_mode != StateMode.HALT and not input_data.manual_resume:
        next_mode = StateMode.HALT
        transition_reason = "HALT_MANUAL_RESUME_REQUIRED"

    next_snapshot = StateSnapshot(
        mode=next_mode,
        defense_cooldown_until=_normalize_cooldown(current.defense_cooldown_until, event_time),
        halt_shadow_until=_normalize_cooldown(current.halt_shadow_until, event_time),
    )

    if current.mode == StateMode.DEFENSE and next_mode != StateMode.DEFENSE:
        next_snapshot.defense_cooldown_until = event_time + timedelta(
            hours=config.cooldowns.post_defense_no_new_positions_hours
        )

    if current.mode == StateMode.HALT and next_mode != StateMode.HALT:
        next_snapshot.halt_shadow_until = event_time + timedelta(
            hours=config.cooldowns.post_halt_shadow_only_hours
        )

    gate = _compute_gate(next_snapshot, event_time)

    return StateEvaluationResult(
        snapshot=next_snapshot,
        trading_gate=gate,
        transitioned=current.mode != next_mode,
        transition_reason=transition_reason,
    )
