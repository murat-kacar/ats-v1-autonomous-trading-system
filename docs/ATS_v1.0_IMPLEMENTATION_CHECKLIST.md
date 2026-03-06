# Autonomous Trading System - v1.0 Implementation Checklist

Status: Execution plan aligned with v1.0 scope
Reference: `ATS_v1.0_SCOPE_OPERATING_RULES.md`

Use this as the single build checklist. Do not start a phase unless previous phase exit criteria are met.

Goal authority:
- Canonical goals are locked in `ATS_v1.0_SCOPE_OPERATING_RULES.md` (Sections 0 and 1).
- This checklist tracks execution only; it does not redefine goals.
- If any checklist item conflicts with canonical goals, update this checklist before implementation.

## Phase 0 - Foundation and Safety Rails

Goal:
- Build deterministic control plane before any strategy logic.

### 0.1 Repository and project skeleton
- [x] Create monorepo layout:
  - `apps/orchestrator`
  - `services/evidence-swarm`
  - `services/decision-core`
  - `services/risk-adjudicator`
  - `services/execution-kernel`
  - `services/monitoring`
  - `libs/contracts`
  - `libs/risk-rules`
  - `libs/event-log`
- [x] Create shared config system (`env`, schema validation, immutable runtime snapshot).
- [x] Add static analysis + formatting + unit test runner.

### 0.2 Canonical contracts and reason codes
- [x] Define strict message schemas:
  - `EvidencePacket`
  - `DecisionProposal`
  - `RiskDecision`
  - `ExecutionIntent`
  - `ExecutionReport`
- [x] Define mandatory `reason_codes` enum (deny, throttle, halt, no-trade).
- [x] Add schema compatibility tests across all services.

### 0.3 Constitution and state machine engine
- [x] Implement immutable constitution loader (read-only at runtime).
- [x] Implement deterministic mode transitions: NORMAL/CAUTION/DEFENSE/HALT.
- [x] Implement cooldown semantics on mode exit:
  - DEFENSE exit -> 6h no new positions
  - HALT exit -> 24h shadow-only
- [x] Add precedence engine:
  1. Constitution breach
  2. Circuit breaker
  3. Liquidity gate
  4. No-trade zone
  5. Risk limits
  6. Strategy intent

### 0.4 Audit and replayability
- [x] Implement append-only event log with IDs and timestamps.
- [x] Log every deny/allow decision with reason code and inputs hash.
- [x] Add deterministic replay tool: same inputs -> same decisions.
- [x] Add release manifest hash bundle:
  - code hash
  - model hash
  - config hash
  - dataset hash (if applicable)

### 0.5 Secrets and operational safety
- [x] Integrate secrets manager for API keys.
- [x] Add key rotation runbook and emergency revoke procedure.
- [x] Implement startup health checks and stale-data kill condition.

Exit criteria (Phase 0):
- [x] All schemas versioned and tested
- [x] State transitions 100% deterministic in tests
- [x] Replay test passes for at least 1,000 synthetic events
- [x] No order route available unless constitution/risk passes

---

## Phase 1 - Paper Trading Core (No Real Funds)

Goal:
- Build end-to-end decision loop with strict safety and realistic cost modeling.

### 1.1 Data adapters (single venue, BTCUSDT perp)
- [x] Implement market data ingest:
  - top-of-book
  - depth snapshots
  - trades
  - funding
- [x] Implement data sanity checks:
  - feed delay
  - outlier ticks
  - volume anomalies
- [x] Map anomalies to uncertainty_score contribution (no hard block by default).

### 1.2 Evidence swarm (advisory only)
- [x] Define expert taxonomy for v1.0 advisory swarm:
  - market microstructure
  - macro and cross-asset
  - funding/basis and derivatives structure
  - on-chain flow and reserves
  - sentiment/news and economic-journalism narrative
  - broker-style execution diagnostics
  - econometrics and mathematical validation
- [x] Implement initial advisory agents:
  - trend evidence
  - mean-reversion evidence
  - volatility evidence
  - microstructure evidence
  - funding/basis evidence
  - macro-correlation evidence
- [x] Enforce no-trading-authority rule at interface level.
- [x] Enforce no-forecast-authority rule at interface level (agents provide stats/evidence only).
- [x] Standardize outputs to EvidencePacket schema.
- [x] Add per-agent reliability scoring and timeout-to-neutral fallback.

### 1.3 Evidence compiler
- [x] Build reliability-weighted aggregation.
- [x] Resolve evidence conflicts and compute source reliability score.
- [x] Emit unified evidence packet + quality flags.

### 1.4 Decision core
- [x] Produce only:
  - `p_up`, `p_down`, `p_flat`
  - `edge_bps_after_cost`
  - `confidence`
- [x] Implement adaptive horizon selector:
  - candidate horizons: 5m, 15m, 1h, 4h
  - candidate windows: 30d, 60d, 120d
  - min sample: 150 trades/window
  - validation: walk-forward + embargo
- [x] Enforce hard rule:
  - no valid horizon-window pair -> `NO_TRADE` with `NO_HORIZON_PASSED`

### 1.5 Risk adjudicator
- [x] Implement fractional sizing with uncertainty scaling:
  - `size = fractional_kelly * (1 - uncertainty_score)`
- [x] Enforce hard caps:
  - max single-position loss 10%
  - daily loss 5%
  - mode leverage/concurrency limits
- [x] Enforce NTZ rule:
  - block only when all three NTZ conditions hold
- [x] Emit final ALLOW/DENY decision with full reason codes.

### 1.6 Execution simulator (paper mode)
- [x] Implement maker-first simulation.
- [x] Implement liquidity gate checks (spread, depth, impact).
- [x] Implement circuit breaker inline in execution path.
- [x] Implement kill switch:
  - controlled unwind
  - timeout -> aggressive exit
- [x] Model costs in paper execution:
  - commission
  - slippage
  - funding
  - impact

### 1.7 Monitoring and drift
- [x] Real-time PnL and risk-adjusted metrics.
- [x] Dual-channel drift detection:
  - PnL drift
  - calibration drift
- [x] Automatic demotion to shadow behavior on critical drift.

Exit criteria (Phase 1):
- [ ] 30 consecutive days paper runtime
- [ ] At least 50 paper trades
- [ ] Positive risk-adjusted return after all costs
- [ ] Zero constitution breaches in paper logs
- [ ] All deny reasons explainable from logs without ambiguity

Note:
- Phase 1 engineering implementation is complete; exit criteria above are runtime-validation gates and remain pending until paper window is observed.

---

## Phase 2 - Micro Live Deployment (Capital-Constrained)

Goal:
- Start real trading with strict exposure limits and reversible rollout.

### 2.1 Live readiness gate
- [ ] Run kill-switch drill in staging (pass/fail recorded).
- [ ] Run rollback drill to Last Known Good snapshot.
- [ ] Validate clock sync and idempotent order submission.
- [ ] Sign release manifest and freeze config for launch.

### 2.2 Micro-live launch controls
- [ ] Allocate only a small capital fraction initially (config-locked).
- [ ] Keep same execution + risk code path as paper (no branch divergence).
- [ ] Enable real-time alerts for:
  - mode changes
  - deny bursts
  - slippage spikes
  - stale data

### 2.3 Scale policy
- [ ] Define stepwise scale increments.
- [ ] Increase size only if all conditions hold during evaluation window:
  - positive post-cost edge
  - stable calibration
  - no constitution breach
  - no unresolved incident
- [ ] Any critical incident resets scale level to prior safe step.

### 2.4 Incident response
- [ ] HALT playbook tested end-to-end.
- [ ] Exchange/API outage playbook tested.
- [ ] Data corruption/stale-feed playbook tested.
- [ ] Post-incident review template enforced.

Exit criteria (Phase 2):
- [ ] Live system stable through initial evaluation window
- [ ] No high-severity unresolved incident
- [ ] Scale-up decision supported by metrics and signed review note

---

## Not in v1.0 Live Critical Path

- [ ] Multi-exchange routing
- [ ] Multi-asset optimization
- [ ] Autonomous architecture mutation
- [ ] Genetic strategy evolution in live path
- [ ] Unbounded meta-layer additions that increase critical-path latency

---

## Definition of Done (v1.0)

v1.0 is complete only if:
- [ ] Deterministic safety controls dominate all model decisions
- [ ] Every order decision is fully auditable and replayable
- [ ] No-trade behavior works as designed when edge is not proven
- [ ] Live performance is evaluated post-cost, not gross
- [ ] System remains operable by a solo owner without hidden complexity
