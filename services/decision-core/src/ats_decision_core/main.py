from __future__ import annotations

from ats_contracts.models import DecisionCoreInput, DecisionProposal
from fastapi import FastAPI

from .engine import build_decision_proposal

app = FastAPI(title="ats-decision-core", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "decision-core"}


@app.post("/v1/decision/propose", response_model=DecisionProposal)
def propose_decision(input_data: DecisionCoreInput) -> DecisionProposal:
    return build_decision_proposal(input_data)
