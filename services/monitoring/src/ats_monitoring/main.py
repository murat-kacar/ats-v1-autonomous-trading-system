from __future__ import annotations

from ats_contracts.models import MonitoringEvaluationInput, MonitoringEvaluationResult
from fastapi import FastAPI

from .engine import evaluate_monitoring

app = FastAPI(title="ats-monitoring", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "monitoring"}


@app.post("/v1/monitoring/evaluate", response_model=MonitoringEvaluationResult)
def monitoring_evaluate(input_data: MonitoringEvaluationInput) -> MonitoringEvaluationResult:
    return evaluate_monitoring(input_data)
