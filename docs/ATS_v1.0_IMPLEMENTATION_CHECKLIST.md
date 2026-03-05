# Autonomous Trading System - v1.0 Implementation Checklist

Status: Execution plan aligned with v1.0 scope
Reference: `ATS_v1.0_SCOPE_OPERATING_RULES.md`

Use this as the single build checklist. Do not start a phase unless previous phase exit criteria are met.

## Phase 0 - Foundation and Safety Rails

Goal:
- Build deterministic control plane before any strategy logic.

### 0.1 Repository and project skeleton
- [ ] Create monorepo layout:
  - `apps/orchestrator`
  - `services/evidence-swarm`
  - `services/decision-core`
  - `services/risk-adjudicator`
  - `services/execution-kernel`
  - `services/monitoring`
  - `libs/contracts`
  - `libs/risk-rules`
  - `libs/event-log`
- [ ] Create shared config system (`env`, schema validation, immutable runtime snapshot).
- [ ] Add static analysis + formatting + unit test runner.

### 0.2 Canonical contracts and reason codes
- [ ] Define strict message schemas:
  - `EvidencePacket`
  - `DecisionProposal`
  - `RiskDecision`
  - `ExecutionIntent`
  - `ExecutionReport`
- [ ] Define mandatory `reason_codes` enum (deny, throttle, halt, no-trade).
- [ ] Add schema compatibility tests across all services.

### 0.3 Constitution and state machine engine
- [ ] Implement immutable constitution loader (read-only at runtime).
- [ ] Implement deterministic mode transitions: NORMAL/CAUTION/DEFENSE/HALT.
- [ ] Implement cooldown semantics on mode exit:
  - DEFENSE exit -> 6h no new positions
  - HALT exit -> 24h shadow-only
- [ ] Add precedence engine:
  1. Constitution breach
  2. Circuit breaker
  3. Liquidity gate
  4. No-trade zone
  5. Risk limits
  6. Strategy intent

### 0.4 Audit and replayability
- [ ] Implement append-only event log with IDs and timestamps.
- [ ] Log every deny/allow decision with reason code and inputs hash.
- [ ] Add deterministic replay tool: same inputs -> same decisions.
- [ ] Add release manifest hash bundle:
  - code hash
  - model hash
  - config hash
  - dataset hash (if applicable)

### 0.5 Secrets and operational safety
- [ ] Integrate secrets manager for API keys.
- [ ] Add key rotation runbook and emergency revoke procedure.
- [ ] Implement startup health checks and stale-data kill condition.

Exit criteria (Phase 0):
- [ ] All schemas versioned and tested
- [ ] State transitions 100% deterministic in tests
- [ ] Replay test passes for at least 1,000 synthetic events
- [ ] No order route available unless constitution/risk passes

---

## Phase 1 - Paper Trading Core (No Real Funds)

Goal:
- Build end-to-end decision loop with strict safety and realistic cost modeling.

### 1.1 Data adapters (single venue, BTCUSDT perp)
- [ ] Implement market data ingest:
  - top-of-book
  - depth snapshots
  - trades
  - funding
- [ ] Implement data sanity checks:
  - feed delay
  - outlier ticks
  - volume anomalies
- [ ] Map anomalies to `uncertainty_score` contribution (no hard block by default).

### 1.2 Evidence swarm (advisory only)
- [ ] Implement initial advisory agents:
  - trend evidence
  - mean-reversion evidence
  - volatility evidence
  - microstructure evidence
  - funding/basis evidence
  - macro-correlation evidence
- [ ] Enforce no-trading-authority rule at interface level.
- [ ] Standardize outputs to EvidencePacket schema.

### 1.3 Evidence compiler
- [ ] Build reliability-weighted aggregation.
- [ ] Resolve evidence conflicts and compute source reliability score.
- [ ] Emit unified evidence packet + quality flags.

### 1.4 Decision core
- [ ] Produce only:
  - `p_up`, `p_down`, `p_flat`
  - `edge_bps_after_cost`
  - `confidence`
- [ ] Implement adaptive horizon selector:
  - candidate horizons: 5m, 15m, 1h, 4h
  - candidate windows: 30d, 60d, 120d
  - min sample: 150 trades/window
  - validation: walk-forward + embargo
- [ ] Enforce hard rule:
  - no valid horizon-window pair -> `NO_TRADE` with `NO_HORIZON_PASSED`

### 1.5 Risk adjudicator
- [ ] Implement fractional sizing with uncertainty scaling:
  - `size = fractional_kelly * (1 - uncertainty_score)`
- [ ] Enforce hard caps:
  - max single-position loss 10%
  - daily loss 5%
  - mode leverage/concurrency limits
- [ ] Enforce NTZ rule:
  - block only when all three NTZ conditions hold
- [ ] Emit final `ALLOW/DENY` decision with full reason codes.

### 1.6 Execution simulator (paper mode)
- [ ] Implement maker-first simulation.
- [ ] Implement liquidity gate checks (spread, depth, impact).
- [ ] Implement circuit breaker inline in execution path.
- [ ] Implement kill switch:
  - controlled unwind
  - timeout -> aggressive exit
- [ ] Model costs in paper execution:
  - commission
  - slippage
  - funding
  - impact

### 1.7 Monitoring and drift
- [ ] Real-time PnL and risk-adjusted metrics.
- [ ] Dual-channel drift detection:
  - PnL drift
  - calibration drift
- [ ] Automatic demotion to shadow behavior on critical drift.

Exit criteria (Phase 1):
- [ ] 30 consecutive days paper runtime
- [ ] At least 50 paper trades
- [ ] Positive risk-adjusted return after all costs
- [ ] Zero constitution breaches in paper logs
- [ ] All deny reasons explainable from logs without ambiguity

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
