from __future__ import annotations

from dataclasses import dataclass

from ats_contracts.models import (
    DecisionCoreInput,
    DecisionProposal,
    HorizonWindowCandidate,
    ReasonCode,
)


@dataclass(frozen=True)
class HorizonSelection:
    candidate: HorizonWindowCandidate
    post_cost_edge_bps: float
    score: float


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _post_cost_edge_bps(candidate: HorizonWindowCandidate) -> float:
    return (
        candidate.gross_edge_bps
        - candidate.fee_bps
        - candidate.slippage_bps
        - candidate.funding_bps
        - candidate.impact_bps
    )


def select_horizon_window(input_data: DecisionCoreInput) -> HorizonSelection | None:
    allowed_horizons = set(input_data.allowed_horizons)
    allowed_windows = set(input_data.allowed_windows_days)

    valid: list[HorizonSelection] = []

    for candidate in input_data.candidates:
        if candidate.horizon not in allowed_horizons:
            continue
        if candidate.window_days not in allowed_windows:
            continue
        if candidate.sample_size < input_data.min_sample_size:
            continue
        if not candidate.embargo_passed:
            continue
        if candidate.walk_forward_score <= 0.0:
            continue

        edge_after_cost = _post_cost_edge_bps(candidate)
        if edge_after_cost <= 0.0:
            continue

        sample_quality = min(1.0, candidate.sample_size / (input_data.min_sample_size * 2.0))
        wf_quality = min(1.0, candidate.walk_forward_score / 2.0)

        score = edge_after_cost * (0.60 + 0.40 * sample_quality) * (0.40 + 0.60 * wf_quality)

        valid.append(
            HorizonSelection(
                candidate=candidate,
                post_cost_edge_bps=edge_after_cost,
                score=score,
            )
        )

    if not valid:
        return None

    horizon_rank = {name: idx for idx, name in enumerate(input_data.allowed_horizons)}

    return max(
        valid,
        key=lambda item: (
            item.score,
            item.post_cost_edge_bps,
            item.candidate.walk_forward_score,
            item.candidate.sample_size,
            -horizon_rank.get(item.candidate.horizon, 9_999),
            item.candidate.window_days,
        ),
    )


def _directional_score(input_data: DecisionCoreInput) -> float:
    evidence = input_data.evidence

    weighted_sum = 0.0
    total_weight = 0.0

    for source, reliability in evidence.source_reliability.items():
        direction = _clamp(evidence.feature_values.get(f"{source}_direction", 0.0), -1.0, 1.0)
        confidence = _clamp(evidence.feature_values.get(f"{source}_confidence", 0.5), 0.0, 1.0)

        weight = _clamp(reliability, 0.0, 1.0) * (0.35 + 0.65 * confidence)
        weighted_sum += direction * weight
        total_weight += weight

    if total_weight <= 0.0:
        return 0.0

    return _clamp(weighted_sum / total_weight, -1.0, 1.0)


def _probabilities(input_data: DecisionCoreInput) -> tuple[float, float, float, float]:
    directional = _directional_score(input_data)
    uncertainty = _clamp(input_data.evidence.uncertainty_score, 0.0, 1.0)

    p_flat = _clamp(0.20 + 0.65 * uncertainty, 0.20, 0.92)
    direction_mass = 1.0 - p_flat

    p_up = direction_mass * (0.5 + 0.5 * directional)
    p_down = direction_mass - p_up

    confidence = _clamp((1.0 - uncertainty) * (0.45 + 0.55 * abs(directional)), 0.0, 1.0)

    return p_up, p_down, p_flat, confidence


def build_decision_proposal(input_data: DecisionCoreInput) -> DecisionProposal:
    selection = select_horizon_window(input_data)

    if selection is None:
        return DecisionProposal(
            request_id=input_data.request_id,
            p_up=0.0,
            p_down=0.0,
            p_flat=1.0,
            edge_bps_after_cost=0.0,
            confidence=0.0,
            selected_horizon="NO_VALID_HORIZON",
            reason_codes=[ReasonCode.NO_HORIZON_PASSED],
        )

    p_up, p_down, p_flat, confidence = _probabilities(input_data)

    sample_quality = min(1.0, selection.candidate.sample_size / (input_data.min_sample_size * 2.0))
    wf_quality = min(1.0, selection.candidate.walk_forward_score / 2.0)
    confidence_adjusted = _clamp(confidence * (0.50 + 0.50 * sample_quality * wf_quality), 0.0, 1.0)

    horizon_label = f"{selection.candidate.horizon}|{selection.candidate.window_days}d"

    return DecisionProposal(
        request_id=input_data.request_id,
        p_up=p_up,
        p_down=p_down,
        p_flat=p_flat,
        edge_bps_after_cost=selection.post_cost_edge_bps,
        confidence=confidence_adjusted,
        selected_horizon=horizon_label,
        reason_codes=[ReasonCode.OK],
    )
