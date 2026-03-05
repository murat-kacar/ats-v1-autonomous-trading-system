# Autonomous Trading System - v1.0 Tech Stack Lock

Status: Locked
Lock date: 2026-03-05
Scope: v1.0 (single symbol, single venue, production-safe)

This is the canonical technology lock for v1.0. Versions are pinned for determinism.
No rolling upgrades in production.

## 1) Stack Policy

- Use the newest stable and compatible set as of lock date.
- Freeze exact versions in lockfiles and container tags.
- Update cadence: once per year (unless critical security incident).
- Any upgrade requires replay/backtest/paper regression pass before production.

## 2) Exchange + AI Providers

- Exchange: Binance USD-M Futures (BTCUSDT primary instrument).
- AI provider: OpenAI API.
- Execution critical path must remain deterministic code (AI advisory only upstream).

## 3) Runtime and Infrastructure Lock

- OS: Ubuntu Server 24.04 LTS
- Python: 3.14.3
- Package manager: uv 0.10.8
- Container engine: Docker Engine 29.2.1
- Compose: Docker Compose 5.1.0

Core services:
- PostgreSQL: 18.3
- Redis: 8.6.1
- NATS Server (JetStream): 2.12.4

Observability:
- Prometheus: 3.10.0
- Grafana: 12.4.0
- Loki: 3.6.7

## 4) Python Application Dependencies (Pinned)

Framework and contracts:
- openai==2.24.0
- mcp==1.26.0
- fastmcp==3.1.0
- fastapi==0.135.1
- uvicorn==0.41.0
- pydantic==2.12.5
- httpx==0.28.1
- websockets==16.0
- nats-py==2.14.0
- redis==7.2.1
- psycopg==3.3.3
- sqlalchemy==2.0.48
- alembic==1.18.4

Data and ML:
- numpy==2.4.2
- scipy==1.17.1
- scikit-learn==1.8.0
- lightgbm==4.6.0
- optuna==4.7.0
- polars==1.38.1
- duckdb==1.4.4
- pyarrow==23.0.1

Reliability and telemetry:
- prometheus-client==0.24.1
- structlog==25.5.0
- orjson==3.11.7
- tenacity==9.1.4

Quality:
- pytest==9.0.2
- pytest-asyncio==1.3.0
- ruff==0.15.4
- mypy==1.19.1
- hypothesis==6.151.9

## 5) MCP Server Management Model (Locked)

### 5.1 MCP roles
- Each specialist agent runs as an independent MCP server.
- MCP servers are advisory-only: feature, risk flag, uncertainty contribution.
- MCP servers cannot place orders and cannot bypass risk/execution layers.

### 5.2 MCP Supervisor service
- Registry: maintains active MCP servers and capabilities.
- Health: heartbeat every 10s, liveness/readiness checks.
- Control: timeout, retry budget, exponential backoff, circuit-open on repeated failure.
- Isolation: failing MCP server is degraded/disabled without stopping execution kernel.
- Audit: every MCP response stored with request id and latency.

### 5.3 Transport and contracts
- Internal transport: NATS subjects per capability group.
- Contract-first payloads via Pydantic schemas (versioned).
- Strict timeouts on MCP calls; timeout returns neutral evidence (not hard-fail trading by itself).

## 6) Critical Path Latency Budget (v1.0)

- Decision Core (excluding MCP fan-out): <= 120 ms p95
- Risk Adjudicator: <= 30 ms p95
- Execution pre-trade guards: <= 20 ms p95
- Total decision-to-order path: <= 250 ms p95

If latency budget is breached persistently:
- Reduce agent fan-out and meta complexity before considering infra scaling.

## 7) Determinism Rules

- Pin exact versions in `pyproject.toml` + `uv.lock`.
- Pin container images by exact version tag (optionally digest in production).
- No floating ranges (`^`, `~`, `*`, `latest`) in production manifests.
- Reproducible build artifacts must include:
  - code commit hash
  - dependency lock hash
  - config hash
  - model artifact hash

## 8) Upgrade Policy (Annual)

Default window:
- One planned annual upgrade window (Q1 each year).

Emergency exception:
- Security fix or exchange/API breaking change can trigger out-of-cycle upgrade.

Upgrade gate (mandatory):
1. Build with new lock set
2. Unit/integration pass
3. Deterministic replay pass
4. Backtest parity check (post-cost)
5. 14-day paper validation
6. Micro-live canary before full rollout

## 9) Explicit Non-Goals for v1.0

- Multi-exchange execution routing
- Multi-asset portfolio optimizer
- Autonomous architecture mutation in production
- Unbounded online retraining without promotion gate

---

This lock is valid for v1.0 build start.
Any deviation requires versioned change request and approval log.
