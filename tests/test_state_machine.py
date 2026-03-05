from datetime import UTC, datetime, timedelta

from ats_contracts.models import StateEvaluationInput, StateMode, StateSnapshot, TradingGate
from ats_risk_rules.constitution import load_constitution
from ats_risk_rules.state_machine import evaluate_state_transition


def _cfg():
    return load_constitution()


def test_normal_conditions_stay_normal() -> None:
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    result = evaluate_state_transition(
        StateEvaluationInput(
            snapshot=StateSnapshot(mode=StateMode.NORMAL),
            event_time=now,
            drawdown_pct=5.0,
        ),
        _cfg(),
    )

    assert result.snapshot.mode == StateMode.NORMAL
    assert result.trading_gate == TradingGate.LIVE
    assert result.transitioned is False


def test_drawdown_triggers_caution() -> None:
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    result = evaluate_state_transition(
        StateEvaluationInput(
            snapshot=StateSnapshot(mode=StateMode.NORMAL),
            event_time=now,
            drawdown_pct=25.0,
        ),
        _cfg(),
    )

    assert result.snapshot.mode == StateMode.CAUTION
    assert result.transitioned is True
    assert result.transition_reason == "CAUTION_TRIGGERED"


def test_defense_overrides_caution_when_drawdown_higher() -> None:
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    result = evaluate_state_transition(
        StateEvaluationInput(
            snapshot=StateSnapshot(mode=StateMode.CAUTION),
            event_time=now,
            drawdown_pct=40.0,
        ),
        _cfg(),
    )

    assert result.snapshot.mode == StateMode.DEFENSE
    assert result.transition_reason == "DEFENSE_TRIGGERED"


def test_constitution_breach_forces_halt() -> None:
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    result = evaluate_state_transition(
        StateEvaluationInput(
            snapshot=StateSnapshot(mode=StateMode.DEFENSE),
            event_time=now,
            drawdown_pct=10.0,
            constitution_breach=True,
        ),
        _cfg(),
    )

    assert result.snapshot.mode == StateMode.HALT
    assert result.trading_gate == TradingGate.HALTED


def test_exit_defense_starts_no_new_positions_cooldown() -> None:
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    result = evaluate_state_transition(
        StateEvaluationInput(
            snapshot=StateSnapshot(mode=StateMode.DEFENSE),
            event_time=now,
            drawdown_pct=5.0,
        ),
        _cfg(),
    )

    assert result.snapshot.mode == StateMode.NORMAL
    assert result.snapshot.defense_cooldown_until == now + timedelta(hours=6)
    assert result.trading_gate == TradingGate.NO_NEW_POSITIONS


def test_halt_requires_manual_resume() -> None:
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    result = evaluate_state_transition(
        StateEvaluationInput(
            snapshot=StateSnapshot(mode=StateMode.HALT),
            event_time=now,
            drawdown_pct=10.0,
            manual_resume=False,
        ),
        _cfg(),
    )

    assert result.snapshot.mode == StateMode.HALT
    assert result.transitioned is False
    assert result.transition_reason == "HALT_MANUAL_RESUME_REQUIRED"


def test_halt_exit_starts_shadow_only_cooldown() -> None:
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    result = evaluate_state_transition(
        StateEvaluationInput(
            snapshot=StateSnapshot(mode=StateMode.HALT),
            event_time=now,
            drawdown_pct=5.0,
            manual_resume=True,
        ),
        _cfg(),
    )

    assert result.snapshot.mode == StateMode.NORMAL
    assert result.snapshot.halt_shadow_until == now + timedelta(hours=24)
    assert result.trading_gate == TradingGate.SHADOW_ONLY


def test_expired_cooldowns_are_cleared() -> None:
    now = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    stale = now - timedelta(minutes=1)

    result = evaluate_state_transition(
        StateEvaluationInput(
            snapshot=StateSnapshot(
                mode=StateMode.NORMAL,
                defense_cooldown_until=stale,
                halt_shadow_until=stale,
            ),
            event_time=now,
            drawdown_pct=2.0,
        ),
        _cfg(),
    )

    assert result.snapshot.defense_cooldown_until is None
    assert result.snapshot.halt_shadow_until is None
    assert result.trading_gate == TradingGate.LIVE
