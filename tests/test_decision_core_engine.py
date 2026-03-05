from datetime import UTC, datetime

import pytest
from ats_contracts.models import (
    DecisionCoreInput,
    EvidencePacket,
    HorizonWindowCandidate,
    ReasonCode,
)
from ats_decision_core.engine import build_decision_proposal, select_horizon_window


def _evidence_packet() -> EvidencePacket:
    return EvidencePacket(
        request_id="req-1",
        created_at=datetime(2026, 3, 5, 18, 0, tzinfo=UTC),
        uncertainty_score=0.32,
        data_quality_score=0.91,
        feature_values={
            "trend_direction": 0.45,
            "trend_confidence": 0.72,
            "mean_reversion_direction": -0.10,
            "mean_reversion_confidence": 0.40,
            "volatility_direction": 0.18,
            "volatility_confidence": 0.55,
        },
        risk_flags=["SANITY_OK"],
        source_reliability={
            "trend": 0.75,
            "mean_reversion": 0.65,
            "volatility": 0.60,
        },
    )


def test_select_horizon_window_returns_best_valid_candidate() -> None:
    input_data = DecisionCoreInput(
        request_id="req-1",
        evidence=_evidence_packet(),
        candidates=[
            HorizonWindowCandidate(
                horizon="5m",
                window_days=30,
                sample_size=170,
                walk_forward_score=0.7,
                embargo_passed=True,
                gross_edge_bps=8.2,
                fee_bps=2.0,
                slippage_bps=1.1,
                funding_bps=0.4,
                impact_bps=0.5,
            ),
            HorizonWindowCandidate(
                horizon="15m",
                window_days=60,
                sample_size=260,
                walk_forward_score=1.1,
                embargo_passed=True,
                gross_edge_bps=12.0,
                fee_bps=1.8,
                slippage_bps=1.0,
                funding_bps=0.4,
                impact_bps=0.8,
            ),
            HorizonWindowCandidate(
                horizon="1h",
                window_days=120,
                sample_size=200,
                walk_forward_score=0.9,
                embargo_passed=False,
                gross_edge_bps=16.0,
                fee_bps=2.0,
                slippage_bps=1.5,
                funding_bps=1.0,
                impact_bps=1.0,
            ),
        ],
    )

    selected = select_horizon_window(input_data)

    assert selected is not None
    assert selected.candidate.horizon == "15m"
    assert selected.candidate.window_days == 60
    assert selected.post_cost_edge_bps == pytest.approx(8.0)


def test_build_decision_returns_no_horizon_when_no_valid_candidates() -> None:
    input_data = DecisionCoreInput(
        request_id="req-2",
        evidence=_evidence_packet(),
        candidates=[
            HorizonWindowCandidate(
                horizon="5m",
                window_days=30,
                sample_size=120,
                walk_forward_score=1.2,
                embargo_passed=True,
                gross_edge_bps=10.0,
                fee_bps=2.0,
                slippage_bps=1.5,
                funding_bps=0.5,
                impact_bps=0.8,
            )
        ],
    )

    proposal = build_decision_proposal(input_data)

    assert proposal.reason_codes == [ReasonCode.NO_HORIZON_PASSED]
    assert proposal.selected_horizon == "NO_VALID_HORIZON"
    assert proposal.p_up == 0.0
    assert proposal.p_down == 0.0
    assert proposal.p_flat == 1.0
    assert proposal.edge_bps_after_cost == 0.0


def test_build_decision_outputs_probabilities_and_positive_edge() -> None:
    input_data = DecisionCoreInput(
        request_id="req-3",
        evidence=_evidence_packet(),
        candidates=[
            HorizonWindowCandidate(
                horizon="15m",
                window_days=60,
                sample_size=300,
                walk_forward_score=1.4,
                embargo_passed=True,
                gross_edge_bps=14.0,
                fee_bps=2.0,
                slippage_bps=1.1,
                funding_bps=0.5,
                impact_bps=0.9,
            )
        ],
    )

    proposal = build_decision_proposal(input_data)

    assert proposal.reason_codes == [ReasonCode.OK]
    assert proposal.selected_horizon == "15m|60d"
    assert proposal.edge_bps_after_cost == 9.5
    assert 0.0 <= proposal.p_up <= 1.0
    assert 0.0 <= proposal.p_down <= 1.0
    assert 0.0 <= proposal.p_flat <= 1.0
    assert round(proposal.p_up + proposal.p_down + proposal.p_flat, 6) == 1.0
    assert 0.0 <= proposal.confidence <= 1.0
