from __future__ import annotations

import os
from pathlib import Path

from ats_contracts.models import RiskDecision, RiskEvaluationInput
from ats_event_log.logger import EventLogger
from ats_risk_rules.rules import decide_risk_decision
from fastapi import FastAPI

DEFAULT_EVENT_LOG_DIR = "/home/deploy/ats/var/log/events"
EVENT_LOG_DIR_ENV = "ATS_EVENT_LOG_DIR"


def _build_event_logger(service_name: str) -> EventLogger:
    base_dir = Path(os.getenv(EVENT_LOG_DIR_ENV, DEFAULT_EVENT_LOG_DIR))
    return EventLogger(base_dir / f"{service_name}.ndjson")


app = FastAPI(title="ATS Orchestrator", version="0.1.0")
event_logger = _build_event_logger("orchestrator")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "orchestrator"}


@app.post("/v1/risk/adjudicate", response_model=RiskDecision)
def adjudicate_risk(input_data: RiskEvaluationInput) -> RiskDecision:
    request_payload = input_data.model_dump(mode="json")
    request_event = event_logger.append("orchestrator.risk.requested", request_payload)

    result = decide_risk_decision(input_data)

    event_logger.append(
        "orchestrator.risk.completed",
        {
            "request_id": input_data.request_id,
            "input_hash": request_event.input_hash,
            "result": result.model_dump(mode="json"),
            "decision_action": result.action.value,
            "reason_codes": [code.value for code in result.reason_codes],
        },
    )
    return result
