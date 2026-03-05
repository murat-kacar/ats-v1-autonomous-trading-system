from __future__ import annotations

import os
from pathlib import Path

from ats_contracts.models import (
    RiskDecision,
    RiskEvaluationInput,
    StateEvaluationInput,
    StateEvaluationResult,
)
from ats_event_log.logger import EventLogger
from ats_risk_rules.constitution import DEFAULT_CONSTITUTION_PATH, load_constitution
from ats_risk_rules.rules import decide_risk_decision
from ats_risk_rules.state_machine import evaluate_state_transition
from fastapi import FastAPI

DEFAULT_EVENT_LOG_DIR = "/home/deploy/ats/var/log/events"
EVENT_LOG_DIR_ENV = "ATS_EVENT_LOG_DIR"
CONSTITUTION_PATH_ENV = "ATS_CONSTITUTION_PATH"


def _build_event_logger(service_name: str) -> EventLogger:
    base_dir = Path(os.getenv(EVENT_LOG_DIR_ENV, DEFAULT_EVENT_LOG_DIR))
    return EventLogger(base_dir / f"{service_name}.ndjson")


def _load_constitution_from_env():
    configured_path = Path(os.getenv(CONSTITUTION_PATH_ENV, str(DEFAULT_CONSTITUTION_PATH)))
    return load_constitution(configured_path)


app = FastAPI(title="ats-risk-adjudicator", version="0.1.0")
event_logger = _build_event_logger("risk_adjudicator")
constitution = _load_constitution_from_env()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "risk-adjudicator"}


@app.post("/v1/risk/adjudicate", response_model=RiskDecision)
def adjudicate(input_data: RiskEvaluationInput) -> RiskDecision:
    request_payload = input_data.model_dump(mode="json")
    request_hash = event_logger.append("risk_adjudicator.requested", request_payload)

    result = decide_risk_decision(input_data)

    event_logger.append(
        "risk_adjudicator.completed",
        {
            "request_id": input_data.request_id,
            "request_hash": request_hash,
            "result": result.model_dump(mode="json"),
        },
    )
    return result


@app.post("/v1/state/evaluate", response_model=StateEvaluationResult)
def evaluate_state(input_data: StateEvaluationInput) -> StateEvaluationResult:
    request_payload = input_data.model_dump(mode="json")
    request_hash = event_logger.append("risk_adjudicator.state.requested", request_payload)

    result = evaluate_state_transition(input_data, constitution)

    event_logger.append(
        "risk_adjudicator.state.completed",
        {
            "request_hash": request_hash,
            "result": result.model_dump(mode="json"),
        },
    )
    return result
