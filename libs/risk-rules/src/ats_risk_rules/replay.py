from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ats_contracts.models import RiskDecision, RiskEvaluationInput

from .rules import decide_risk_decision

REQUEST_EVENT_TYPES = {
    "risk_adjudicator.requested",
    "orchestrator.risk.requested",
}

COMPLETED_EVENT_TYPES = {
    "risk_adjudicator.completed",
    "orchestrator.risk.completed",
}


@dataclass(frozen=True)
class ReplayMismatch:
    request_id: str
    message: str


def replay_pairs(pairs: list[tuple[RiskEvaluationInput, RiskDecision]]) -> list[ReplayMismatch]:
    mismatches: list[ReplayMismatch] = []

    for input_data, expected in pairs:
        actual = decide_risk_decision(input_data)
        if actual.model_dump(mode="json") != expected.model_dump(mode="json"):
            mismatches.append(
                ReplayMismatch(
                    request_id=input_data.request_id,
                    message=(
                        "Decision mismatch for request_id="
                        f"{input_data.request_id}: expected={expected.model_dump(mode='json')}"
                        f", actual={actual.model_dump(mode='json')}"
                    ),
                )
            )

    return mismatches


def replay_from_event_log(log_path: Path) -> tuple[int, list[ReplayMismatch]]:
    requests: dict[str, RiskEvaluationInput] = {}
    completed_pairs: list[tuple[RiskEvaluationInput, RiskDecision]] = []
    mismatches: list[ReplayMismatch] = []

    for raw in log_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue

        event = json.loads(raw)
        event_type = event.get("event_type")
        payload = event.get("payload", {})

        if event_type in REQUEST_EVENT_TYPES:
            try:
                input_data = RiskEvaluationInput.model_validate(payload)
            except Exception as exc:  # pragma: no cover
                mismatches.append(
                    ReplayMismatch(request_id=str(payload.get("request_id", "unknown")), message=str(exc))
                )
                continue
            requests[input_data.request_id] = input_data
            continue

        if event_type in COMPLETED_EVENT_TYPES:
            request_id = payload.get("request_id", "")
            if not request_id:
                mismatches.append(
                    ReplayMismatch(request_id="unknown", message="Completed event missing request_id")
                )
                continue

            input_data = requests.get(request_id)
            if input_data is None:
                mismatches.append(
                    ReplayMismatch(
                        request_id=request_id,
                        message="Completed event has no matching request event",
                    )
                )
                continue

            try:
                expected = RiskDecision.model_validate(payload.get("result", {}))
            except Exception as exc:  # pragma: no cover
                mismatches.append(ReplayMismatch(request_id=request_id, message=str(exc)))
                continue

            completed_pairs.append((input_data, expected))

    mismatches.extend(replay_pairs(completed_pairs))
    return len(completed_pairs), mismatches
