# API Key Rotation Runbook (v1.0)

## Scope
- Binance API keys (`BINANCE_API_KEY`, `BINANCE_API_SECRET`)
- OpenAI API key (`OPENAI_API_KEY`)

## Preconditions
- New keys are created and tested in paper/staging first.
- Old keys remain valid until cutover verification completes.
- Maintenance window is announced.

## Procedure
1. Create new keys in provider console with minimum required permissions.
2. Update secret store / runtime env on VPS (`/home/deploy/ats/infra/config/runtime.env` or secret backend).
3. Restart services in order:
   - `risk-adjudicator`
   - `orchestrator`
4. Verify startup health:
   - `GET /healthz/startup` returns `status=OK`
5. Run smoke checks:
   - risk adjudication endpoint responds
   - stale-data guard status is healthy
6. Revoke old keys only after all checks pass.
7. Record rotation metadata:
   - timestamp
   - operator
   - changed providers
   - validation evidence

## Validation Checklist
- Startup checks passed with no missing secrets.
- No spike in deny reasons linked to auth errors.
- Event logs show normal decision flow.

## Rollback
- Reapply previous known-good secrets.
- Restart services.
- Confirm `/healthz/startup` and smoke checks.
