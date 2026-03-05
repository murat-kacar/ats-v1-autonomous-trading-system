from __future__ import annotations

from ats_contracts.models import ExecutionSimulationInput, ExecutionSimulationResult
from fastapi import FastAPI

from .engine import simulate_execution

app = FastAPI(title="ats-execution-kernel", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "execution-kernel"}


@app.post("/v1/execution/simulate", response_model=ExecutionSimulationResult)
def execution_simulate(input_data: ExecutionSimulationInput) -> ExecutionSimulationResult:
    return simulate_execution(input_data)
