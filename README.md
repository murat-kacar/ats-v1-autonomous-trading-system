# ATS v1.0 Workspace

This repository is the bootstrap monorepo for ATS v1.0.

## Layout

- `apps/orchestrator`: coordination entrypoint
- `services/*`: runtime services
- `libs/contracts`: canonical message schemas
- `libs/risk-rules`: deterministic risk/state-machine helpers
- `libs/event-log`: append-only event logging helpers and manifest hashing
- `tools/*`: replay and manifest CLI utilities

## Quick Start

```bash
~/.local/bin/uv lock
~/.local/bin/uv sync --all-packages --group dev
~/.local/bin/uv run --all-packages pytest
```

## Phase 0.4 Utilities

```bash
# Replay logged risk decisions (same input -> same decision)
~/.local/bin/uv run --all-packages python tools/replay_risk_decisions.py \
  --log /home/deploy/ats/var/log/events/risk_adjudicator.ndjson

# Build release hash manifest
~/.local/bin/uv run --all-packages python tools/generate_release_manifest.py \
  --repo-root /home/deploy/ats \
  --config-dir /home/deploy/ats/infra/config \
  --model-dir /home/deploy/ats/artifacts/models \
  --dataset-dir /home/deploy/ats/data/datasets \
  --output /home/deploy/ats/artifacts/releases/release-manifest.v1.json
```

## Important

- Use versioned changes only.
- Keep execution-critical logic deterministic.
- Do not bypass constitution/risk layers.
