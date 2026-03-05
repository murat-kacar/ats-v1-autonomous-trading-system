from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="ats-execution-kernel", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "execution-kernel"}
