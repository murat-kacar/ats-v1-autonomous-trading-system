from ats_contracts.models import DecisionProposal, ReasonCode


def test_decision_probabilities_are_well_formed() -> None:
    model = DecisionProposal(
        request_id="r-1",
        p_up=0.4,
        p_down=0.4,
        p_flat=0.2,
        edge_bps_after_cost=2.5,
        confidence=0.62,
        selected_horizon="15m",
        reason_codes=[ReasonCode.OK],
    )
    assert round(model.p_up + model.p_down + model.p_flat, 6) == 1.0
