# ATS v1.0 Workspace

This repository is the bootstrap monorepo for ATS v1.0.

## Layout

- `apps/orchestrator`: coordination entrypoint
- `services/*`: runtime services
- `libs/contracts`: canonical message schemas
- `libs/risk-rules`: deterministic risk/state-machine helpers
- `libs/event-log`: append-only event logging helpers

## Quick Start

```bash
~/.local/bin/uv lock
~/.local/bin/uv sync --all-packages --group dev
~/.local/bin/uv run --all-packages pytest
```

## Important

- Use versioned changes only.
- Keep execution-critical logic deterministic.
- Do not bypass constitution/risk layers.
