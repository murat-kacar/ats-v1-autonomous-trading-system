from ats_contracts.models import (
    DecisionProposal,
    ReasonCode,
    RiskEnvelopeInput,
    StateMode,
    TradeAction,
)
from ats_risk_adjudicator.sizing import build_risk_envelope
from ats_risk_rules.constitution import ConstitutionConfig, load_constitution
from ats_risk_rules.rules import decide_risk_decision


def _decision() -> DecisionProposal:
    return DecisionProposal(
        request_id="r-eval",
        p_up=0.46,
        p_down=0.24,
        p_flat=0.30,
        edge_bps_after_cost=7.5,
        confidence=0.70,
        selected_horizon="15m|60d",
        reason_codes=[ReasonCode.OK],
    )


def _constitution() -> ConstitutionConfig:
    return load_constitution()


def test_build_risk_envelope_applies_fractional_kelly_with_uncertainty() -> None:
    envelope = build_risk_envelope(
        RiskEnvelopeInput(
            request_id="r-kelly",
            decision=_decision(),
            equity_usd=1_000.0,
            state_mode=StateMode.NORMAL,
            uncertainty_score=0.20,
            fractional_kelly=0.10,
            daily_loss_pct=1.0,
            open_positions=1,
            stop_loss_bps=200,
        ),
        _constitution(),
    )

    assert envelope.proposed_size_usd == 80.0
    assert envelope.proposed_leverage == 2.4
    assert envelope.risk_limits_passed is True


def test_daily_loss_limit_fails_risk_limits() -> None:
    envelope = build_risk_envelope(
        RiskEnvelopeInput(
            request_id="r-dd",
            decision=_decision(),
            equity_usd=1_000.0,
            state_mode=StateMode.NORMAL,
            uncertainty_score=0.10,
            fractional_kelly=0.08,
            daily_loss_pct=5.2,
            open_positions=1,
            stop_loss_bps=150,
        ),
        _constitution(),
    )

    decision = decide_risk_decision(envelope.evaluation_input)

    assert envelope.risk_limits_passed is False
    assert decision.action == TradeAction.DENY
    assert decision.reason_codes == [ReasonCode.RISK_LIMIT]


def test_ntz_blocks_only_when_all_three_conditions_true() -> None:
    base = RiskEnvelopeInput(
        request_id="r-ntz",
        decision=_decision(),
        equity_usd=1_000.0,
        state_mode=StateMode.NORMAL,
        uncertainty_score=0.25,
        fractional_kelly=0.08,
        daily_loss_pct=1.0,
        open_positions=1,
        stop_loss_bps=180,
        ntz_uncertainty_high=True,
        ntz_correlation_abnormal=True,
        ntz_funding_extreme=False,
    )

    partial = build_risk_envelope(base, _constitution())
    partial_decision = decide_risk_decision(partial.evaluation_input)

    full = build_risk_envelope(
        base.model_copy(update={"ntz_funding_extreme": True}),
        _constitution(),
    )
    full_decision = decide_risk_decision(full.evaluation_input)

    assert partial.ntz_blocked is False
    assert partial_decision.action == TradeAction.ALLOW

    assert full.ntz_blocked is True
    assert full_decision.action == TradeAction.DENY
    assert full_decision.reason_codes == [ReasonCode.NO_TRADE_ZONE]
