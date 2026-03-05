from ats_contracts.models import DecisionProposal, ReasonCode, RiskEvaluationInput, TradeAction
from ats_risk_rules.rules import GuardTrigger, decide_risk_decision, select_top_guard


def _base_decision() -> DecisionProposal:
    return DecisionProposal(
        request_id="r-base",
        p_up=0.4,
        p_down=0.4,
        p_flat=0.2,
        edge_bps_after_cost=1.5,
        confidence=0.65,
        selected_horizon="15m",
        reason_codes=[ReasonCode.OK],
    )


def test_constitution_guard_wins() -> None:
    guard = select_top_guard(
        [
            GuardTrigger.STRATEGY_INTENT,
            GuardTrigger.RISK_LIMIT,
            GuardTrigger.CONSTITUTION_BREACH,
        ]
    )
    assert guard == GuardTrigger.CONSTITUTION_BREACH


def test_empty_guard_list() -> None:
    assert select_top_guard([]) is None


def test_risk_decision_allow_when_no_guards_active() -> None:
    result = decide_risk_decision(
        RiskEvaluationInput(
            request_id="r-allow",
            decision=_base_decision(),
            proposed_size_usd=120.0,
            proposed_leverage=1.5,
            stop_loss_bps=120,
            time_stop_seconds=900,
        )
    )

    assert result.action == TradeAction.ALLOW
    assert result.reason_codes == [ReasonCode.OK]
    assert result.size_usd == 120.0


def test_risk_decision_precedence_is_deterministic() -> None:
    decision = _base_decision().model_copy(update={"reason_codes": [ReasonCode.NO_HORIZON_PASSED]})

    result = decide_risk_decision(
        RiskEvaluationInput(
            request_id="r-deny",
            decision=decision,
            proposed_size_usd=120.0,
            proposed_leverage=1.5,
            constitution_breach=True,
            circuit_breaker_triggered=True,
            liquidity_gate_passed=False,
        )
    )

    assert result.action == TradeAction.DENY
    assert result.reason_codes == [ReasonCode.CONSTITUTION_BREACH]


def test_no_horizon_blocks_when_no_higher_guard() -> None:
    decision = _base_decision().model_copy(
        update={
            "edge_bps_after_cost": -0.1,
            "reason_codes": [ReasonCode.NO_HORIZON_PASSED],
        }
    )

    result = decide_risk_decision(
        RiskEvaluationInput(
            request_id="r-no-horizon",
            decision=decision,
            proposed_size_usd=120.0,
            proposed_leverage=1.5,
        )
    )

    assert result.action == TradeAction.DENY
    assert result.reason_codes == [ReasonCode.NO_HORIZON_PASSED]
