from pathlib import Path

from ats_contracts.models import DecisionProposal, ReasonCode, RiskDecision, RiskEvaluationInput, TradeAction
from ats_risk_rules.replay import replay_from_event_log, replay_pairs
from ats_risk_rules.rules import decide_risk_decision


def _build_input(idx: int) -> RiskEvaluationInput:
    no_horizon = idx % 10 == 0
    constitution_breach = idx % 211 == 0
    liquidity_passed = idx % 7 != 0

    reason = ReasonCode.NO_HORIZON_PASSED if no_horizon else ReasonCode.OK
    edge = -0.2 if no_horizon else 1.0 + (idx % 5) * 0.1

    decision = DecisionProposal(
        request_id=f"req-{idx}",
        p_up=0.4,
        p_down=0.3,
        p_flat=0.3,
        edge_bps_after_cost=edge,
        confidence=0.6,
        selected_horizon="15m",
        reason_codes=[reason],
    )

    return RiskEvaluationInput(
        request_id=f"req-{idx}",
        decision=decision,
        proposed_size_usd=100.0,
        proposed_leverage=1.2,
        stop_loss_bps=100,
        time_stop_seconds=600,
        constitution_breach=constitution_breach,
        liquidity_gate_passed=liquidity_passed,
    )


def test_replay_pairs_with_1000_synthetic_events() -> None:
    pairs: list[tuple[RiskEvaluationInput, RiskDecision]] = []
    for idx in range(1000):
        input_data = _build_input(idx)
        expected = decide_risk_decision(input_data)
        pairs.append((input_data, expected))

    mismatches = replay_pairs(pairs)
    assert mismatches == []


def test_replay_from_event_log(tmp_path: Path) -> None:
    log_path = tmp_path / "risk.ndjson"

    input_data = _build_input(1)
    expected = decide_risk_decision(input_data)

    requested = {
        "event_type": "risk_adjudicator.requested",
        "payload": input_data.model_dump(mode="json"),
    }
    completed = {
        "event_type": "risk_adjudicator.completed",
        "payload": {
            "request_id": input_data.request_id,
            "result": expected.model_dump(mode="json"),
            "decision_action": TradeAction.ALLOW.value,
            "reason_codes": [ReasonCode.OK.value],
        },
    }

    log_path.write_text(
        "\n".join([
            __import__("json").dumps(requested),
            __import__("json").dumps(completed),
        ]),
        encoding="utf-8",
    )

    replayed, mismatches = replay_from_event_log(log_path)
    assert replayed == 1
    assert mismatches == []
