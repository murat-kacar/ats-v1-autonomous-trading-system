from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import cast

from ats_contracts.models import (
    ReasonCode,
    RiskDecision,
    RiskEnvelopeInput,
    RiskEvaluationInput,
    StateEvaluationInput,
    StateEvaluationResult,
    TradeAction,
)
from ats_event_log.logger import EventLogger
from ats_risk_rules.constitution import (
    DEFAULT_CONSTITUTION_PATH,
    ConstitutionConfig,
    load_constitution,
)
from ats_risk_rules.rules import decide_risk_decision
from ats_risk_rules.state_machine import evaluate_state_transition
from ats_security import SecretManager, StartupHealthChecker
from fastapi import FastAPI

from .sizing import build_risk_envelope

DEFAULT_EVENT_LOG_DIR = "/home/deploy/ats/var/log/events"
DEFAULT_HEARTBEAT_PATH = "/home/deploy/ats/var/run/market_data_heartbeat.json"
DEFAULT_REQUIRED_SECRETS = "BINANCE_API_KEY,BINANCE_API_SECRET,OPENAI_API_KEY"

EVENT_LOG_DIR_ENV = "ATS_EVENT_LOG_DIR"
CONSTITUTION_PATH_ENV = "ATS_CONSTITUTION_PATH"
HEARTBEAT_PATH_ENV = "ATS_MARKET_HEARTBEAT_PATH"
REQUIRED_SECRETS_ENV = "ATS_REQUIRED_SECRETS"
STALE_MAX_SECONDS_ENV = "ATS_STALE_DATA_MAX_SECONDS"
ENFORCE_STARTUP_HEALTH_ENV = "ATS_ENFORCE_STARTUP_HEALTH"
ENFORCE_STALE_ON_STARTUP_ENV = "ATS_ENFORCE_STALE_DATA_ON_STARTUP"
ENFORCE_STALE_ON_REQUEST_ENV = "ATS_ENFORCE_STALE_DATA_ON_REQUEST"


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(value, 1)


def _build_event_logger(service_name: str) -> EventLogger:
    base_dir = Path(os.getenv(EVENT_LOG_DIR_ENV, DEFAULT_EVENT_LOG_DIR))
    return EventLogger(base_dir / f"{service_name}.ndjson")


def _load_constitution_from_env() -> ConstitutionConfig:
    configured_path = Path(os.getenv(CONSTITUTION_PATH_ENV, str(DEFAULT_CONSTITUTION_PATH)))
    return load_constitution(configured_path)


def _required_secret_keys() -> list[str]:
    raw = os.getenv(REQUIRED_SECRETS_ENV, DEFAULT_REQUIRED_SECRETS)
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values


app = FastAPI(title="ats-risk-adjudicator", version="0.1.0")
event_logger = _build_event_logger("risk_adjudicator")
constitution = _load_constitution_from_env()

secret_manager = SecretManager(required_keys=_required_secret_keys())
startup_health_checker = StartupHealthChecker(
    constitution_path=Path(os.getenv(CONSTITUTION_PATH_ENV, str(DEFAULT_CONSTITUTION_PATH))),
    event_log_dir=Path(os.getenv(EVENT_LOG_DIR_ENV, DEFAULT_EVENT_LOG_DIR)),
    heartbeat_path=Path(os.getenv(HEARTBEAT_PATH_ENV, DEFAULT_HEARTBEAT_PATH)),
    max_stale_seconds=_parse_int_env(STALE_MAX_SECONDS_ENV, 120),
    secret_manager=secret_manager,
)


@app.on_event("startup")
def run_startup_health_checks() -> None:
    enforce_startup = _parse_bool_env(ENFORCE_STARTUP_HEALTH_ENV, True)
    enforce_stale = _parse_bool_env(ENFORCE_STALE_ON_STARTUP_ENV, True)

    if not enforce_startup:
        app.state.startup_report = {"status": "SKIPPED"}
        return

    report = startup_health_checker.run(enforce_stale=enforce_stale)
    app.state.startup_report = asdict(report)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "risk-adjudicator"}


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
        "status": "OK",
        "report": report,
        "secret_snapshot": secret_manager.masked_snapshot(),
    }


def _stale_kill_decision(request_id: str) -> RiskDecision:
    return RiskDecision(
        request_id=request_id,
        action=TradeAction.DENY,
        size_usd=0.0,
        leverage=0.0,
        stop_loss_bps=0,
        time_stop_seconds=0,
        reason_codes=[ReasonCode.STALE_DATA],
    )


def _enforce_stale_guard(
    request_id: str,
    request_input_hash: str,
    event_type: str,
) -> RiskDecision | None:
    if not _parse_bool_env(ENFORCE_STALE_ON_REQUEST_ENV, True):
        return None

    stale_status = startup_health_checker.check_stale_data()
    if not stale_status.stale:
        return None

    result = _stale_kill_decision(request_id)
    event_logger.append(
        event_type,
        {
            "request_id": request_id,
            "input_hash": request_input_hash,
            "reason": stale_status.reason,
            "age_seconds": stale_status.age_seconds,
            "result": result.model_dump(mode="json"),
        },
    )
    return result


@app.post("/v1/risk/adjudicate", response_model=RiskDecision)
def adjudicate(input_data: RiskEvaluationInput) -> RiskDecision:
    request_payload = input_data.model_dump(mode="json")
    request_event = event_logger.append("risk_adjudicator.requested", request_payload)

    stale_result = _enforce_stale_guard(
        request_id=input_data.request_id,
        request_input_hash=request_event.input_hash,
        event_type="risk_adjudicator.killed.stale_data",
    )
    if stale_result is not None:
        return stale_result

    result = cast(RiskDecision, decide_risk_decision(input_data))

    event_logger.append(
        "risk_adjudicator.completed",
        {
            "request_id": input_data.request_id,
            "input_hash": request_event.input_hash,
            "result": result.model_dump(mode="json"),
            "decision_action": result.action.value,
            "reason_codes": [code.value for code in result.reason_codes],
        },
    )
    return result


@app.post("/v1/risk/evaluate", response_model=RiskDecision)
def evaluate_risk(input_data: RiskEnvelopeInput) -> RiskDecision:
    request_payload = input_data.model_dump(mode="json")
    request_event = event_logger.append("risk_adjudicator.envelope.requested", request_payload)

    stale_result = _enforce_stale_guard(
        request_id=input_data.request_id,
        request_input_hash=request_event.input_hash,
        event_type="risk_adjudicator.envelope.killed.stale_data",
    )
    if stale_result is not None:
        return stale_result

    envelope = build_risk_envelope(input_data, constitution)
    result = cast(RiskDecision, decide_risk_decision(envelope.evaluation_input))

    event_logger.append(
        "risk_adjudicator.envelope.completed",
        {
            "request_id": input_data.request_id,
            "input_hash": request_event.input_hash,
            "evaluation": envelope.evaluation_input.model_dump(mode="json"),
            "ntz_blocked": envelope.ntz_blocked,
            "risk_limits_passed": envelope.risk_limits_passed,
            "result": result.model_dump(mode="json"),
            "decision_action": result.action.value,
            "reason_codes": [code.value for code in result.reason_codes],
        },
    )
    return result


@app.post("/v1/state/evaluate", response_model=StateEvaluationResult)
def evaluate_state(input_data: StateEvaluationInput) -> StateEvaluationResult:
    request_payload = input_data.model_dump(mode="json")
    request_event = event_logger.append("risk_adjudicator.state.requested", request_payload)

    result = cast(StateEvaluationResult, evaluate_state_transition(input_data, constitution))

    event_logger.append(
        "risk_adjudicator.state.completed",
        {
            "input_hash": request_event.input_hash,
            "result": result.model_dump(mode="json"),
        },
    )
    return result
