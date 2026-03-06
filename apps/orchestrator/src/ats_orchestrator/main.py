from __future__ import annotations

import os
from pathlib import Path

from ats_contracts.models import RiskDecision, RiskEvaluationInput
from ats_event_log.logger import EventLogger
from ats_evidence_swarm.binance_um import BinanceUMPublicClient
from ats_risk_rules.constitution import DEFAULT_CONSTITUTION_PATH, load_constitution
from ats_risk_rules.rules import decide_risk_decision
from ats_security import SecretManager
from fastapi import FastAPI

from .engine import PaperRunInput, PaperRunResult, run_paper_cycle

DEFAULT_EVENT_LOG_DIR = "/home/deploy/ats/var/log/events"
EVENT_LOG_DIR_ENV = "ATS_EVENT_LOG_DIR"
ENFORCE_STARTUP_HEALTH_ENV = "ATS_ENFORCE_STARTUP_HEALTH"
CONSTITUTION_PATH_ENV = "ATS_CONSTITUTION_PATH"


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _build_event_logger(service_name: str) -> EventLogger:
    base_dir = Path(os.getenv(EVENT_LOG_DIR_ENV, DEFAULT_EVENT_LOG_DIR))
    return EventLogger(base_dir / f"{service_name}.ndjson")


app = FastAPI(title="ATS Orchestrator", version="0.1.0")
event_logger = _build_event_logger("orchestrator")
secret_manager = SecretManager(required_keys=["OPENAI_API_KEY"])
constitution = load_constitution(
    Path(os.getenv(CONSTITUTION_PATH_ENV, str(DEFAULT_CONSTITUTION_PATH)))
)
market_client = BinanceUMPublicClient()


@app.on_event("startup")
def run_startup_checks() -> None:
    if not _parse_bool_env(ENFORCE_STARTUP_HEALTH_ENV, True):
        app.state.startup_report = {"status": "SKIPPED"}
        return

    secret_manager.require_all()
    app.state.startup_report = {
        "status": "OK",
        "required_secret_keys": secret_manager.required_keys,
    }


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "orchestrator"}


@app.get("/healthz/startup")
def startup_healthz() -> dict[str, object]:
    report = getattr(app.state, "startup_report", None)
    if report is None:
        return {
            "status": "NOT_RUN",
            "required_secret_keys": secret_manager.required_keys,
            "secret_snapshot": secret_manager.masked_snapshot(),
        }

    return {
        "status": report.get("status", "UNKNOWN"),
        "report": report,
        "secret_snapshot": secret_manager.masked_snapshot(),
    }


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


@app.post("/v1/paper/run-once", response_model=PaperRunResult)
async def run_paper_once(input_data: PaperRunInput) -> PaperRunResult:
    request_payload = input_data.model_dump(mode="json")
    request_event = event_logger.append("orchestrator.paper.requested", request_payload)

    result = await run_paper_cycle(
        input_data=input_data,
        constitution=constitution,
        market_client=market_client,
    )

    event_logger.append(
        "orchestrator.paper.completed",
        {
            "request_id": input_data.request_id,
            "input_hash": request_event.input_hash,
            "used_live_data": result.used_live_data,
            "decision": result.decision.model_dump(mode="json"),
            "risk_decision": result.risk_decision.model_dump(mode="json"),
            "execution_reason_codes": [
                code.value for code in result.execution_result.report.reason_codes
            ],
            "monitoring_action": result.monitoring_result.recommended_action,
        },
    )
    return result
