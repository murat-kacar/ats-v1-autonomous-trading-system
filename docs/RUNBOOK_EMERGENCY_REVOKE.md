# Emergency Revoke Runbook (v1.0)

Use this when keys are suspected compromised or unauthorized orders appear.

## Immediate Actions (first 5 minutes)
1. Trigger trading stop:
   - Force HALT mode and stop new order submissions.
2. Revoke compromised keys at provider side immediately.
3. Disable outbound trading service if revoke confirmation is delayed.

## Containment
1. Rotate to pre-created backup keys (if available).
2. Keep `ATS_ENFORCE_STALE_DATA_ON_REQUEST=true` and startup checks enabled.
3. Verify no active sessions remain with revoked credentials.

## Recovery
1. Deploy fresh keys with least privilege.
2. Restart services and validate `/healthz/startup`.
3. Keep system in shadow-only window until confidence recovers.

## Post-Incident
1. Export incident timeline from event logs.
2. Compare all orders with exchange audit history.
3. Document root cause and corrective actions.
4. Rotate all related credentials (GitHub tokens, VPS secrets, API keys).

## Mandatory Evidence
- revoke confirmation screenshot or API response
- service restart timestamps
- startup health output
- first successful post-recovery smoke test
