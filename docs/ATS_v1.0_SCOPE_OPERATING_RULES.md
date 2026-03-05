# Autonomous Trading System - v1.0 Scope + Operating Rules

Status: Locked baseline for implementation start

This document is the implementation baseline for v1.0. Any change must be versioned and justified.

## 1) Decision Filter (Top Priority)

Primary objective:
- Maximize long-term capital growth under immutable risk constraints.

Priority order for conflicting goals:
1. Survival (avoid catastrophic loss)
2. Stable compounding
3. Speed of profit

If a rule or model update improves short-term return but weakens survival controls, it is rejected.

## 2) Trading Scope (v1.0)

In scope:
- Symbol: BTCUSDT (single instrument)
- Venue: Single exchange (configured once, not dynamic)
- Market type: Perpetual futures
- Direction: Long and short
- Execution style: Maker-first, taker only under explicit urgency rules

Out of scope (v1.0):
- Multi-exchange smart routing
- Multi-asset portfolio allocation
- Genetic strategy evolution in live critical path
- Fully autonomous architecture-changing self-modification

## 3) Constitution (Immutable)

No component (agent, ML, or orchestration) can override these:

- Total capital: 1,000 USD
- Max drawdown: 50% (HALT)
- Max single-position loss: 10% of capital
- Daily loss limit: 5% of capital
- Max leverage: 3x NORMAL, 2x CAUTION, 1x DEFENSE
- Max concurrent positions: 5 NORMAL, 3 CAUTION, 0 new DEFENSE/HALT
- Kill switch timeout: min(60s, 3 x avg_fill_time)
- Circuit breaker trigger: max(2%, 3 x rolling_1m_vol) + spread spike
- Liquidity gate:
  - spread_bps < 8 (NORMAL), < 5 (CAUTION)
  - depth_1pct_usd > order_size_usd x 20 (NORMAL), x 30 (CAUTION)
  - expected_impact_bps < 15 (NORMAL), < 10 (CAUTION)
- NTZ thresholds:
  - uncertainty_score > 0.7 (NORMAL) / > 0.6 (CAUTION)
  - avg_pairwise_corr_30m > 0.85 OR corr_delta(5m-60m) > 0.2
  - funding_z > 2.5

## 4) State Machine (Deterministic)

Modes:
- NORMAL: default
- CAUTION: drawdown > 20% or uncertainty spike
- DEFENSE: drawdown > 35% or critical correlation stress
- HALT: drawdown > 50% or constitution breach

Exit cooldowns:
- Post-DEFENSE: 6h no-new-positions (timer starts at DEFENSE exit)
- Post-HALT: 24h shadow-only (timer starts at HALT exit)

## 5) Layered Runtime (v1.0)

### 5.1 Evidence Swarm (many agents, no trading authority)

Swarm agents can include: market microstructure, macro, funding/basis, on-chain, sentiment/news, broker-style execution diagnostics, math/statistics validators.

Hard rule:
- Swarm agents do not predict final direction and do not place orders.
- They only emit structured evidence:
  - feature_values
  - risk_flags
  - uncertainty_contrib
  - source_reliability

### 5.2 Evidence Compiler

- Normalizes all agent outputs into one schema.
- Resolves conflicts and assigns reliability-weighted aggregates.
- Emits evidence packet + data quality score.

### 5.3 Decision Core (single forecasting authority)

- Only this layer can produce tradable forecast:
  - p_up, p_down, p_flat
  - edge_bps_after_cost
  - confidence

Optional advisory meta is allowed, but maximum 2 meta steps in critical path.

### 5.4 Risk Adjudicator (final go/no-go)

- Enforces constitution, mode limits, portfolio limits.
- Computes final notional and leverage.
- Emits final action:
  - ALLOW / DENY
  - size, leverage, stop, time_stop
  - reason_codes

### 5.5 Execution Kernel (pure deterministic code)

- Maker-first policy
- Liquidity gate (all conditions must pass)
- Inline circuit breaker
- Kill switch dual mode:
  - Controlled unwind
  - Timeout -> aggressive exit

No AI reasoning inside execution critical path.

### 5.6 Audit + Learning

- Every decision and rejection must be event-logged with reason code.
- Learning can tune only permitted parameters and never breach constitution.

## 6) No-Trade Rule (Hard)

No-Trade Zone blocks new entries only when all three are true:
1. High uncertainty threshold breached
2. Correlation stress condition breached
3. Funding extreme breached

If one or two conditions are true:
- Trade is still possible, but size must be reduced by risk policy.

## 7) Horizon Selection Protocol (Adaptive)

No fixed trading horizon is hardcoded.

Candidate horizons:
- 5m, 15m, 1h, 4h

A horizon is tradable only if all pass:
- net_edge_after_cost > 0
- calibration coverage >= threshold
- Brier <= threshold

Window selection:
- Candidate windows: 30d, 60d, 120d
- Minimum sample: 150 trades per candidate
- Validation: walk-forward with embargo
- Score: tradable_score = median(net_edge_after_cost) - calibration_penalty - instability_penalty

Selection rule:
- Choose the highest-scoring valid horizon-window pair.
- If no pair passes -> mandatory NO_TRADE (reason code: NO_HORIZON_PASSED).

Reselection cadence:
- Daily and every 20 new trades.

## 8) Position Sizing Rules (v1.0 practical safety)

Base size:
- fractional_kelly x (1 - uncertainty_score)

Hard caps (deterministic):
- Per-trade max loss <= 10% capital
- Daily stop <= 5% capital
- Mode leverage and concurrency limits always applied

If any cap conflicts with model signal, cap wins.

## 9) Backtest and Promotion Gate (Must Pass)

Backtest is invalid unless all included:
- Commissions
- Slippage
- Funding
- Impact model consistent with live execution assumptions

Promotion pipeline:
1. Sandbox (offline)
2. Shadow/paper (minimum 30 days + 50 trades + positive risk-adjusted return)
3. Micro-live allocation (small fraction of capital)
4. Gradual scale-up only after stability checks

## 10) Governance and Operational Safety

Required before live:
- Signed release artifact with code/model/config hashes
- One-command rollback to Last Known Good
- Incident runbook for HALT, exchange/API failure, and stale-data conditions
- Secret management and periodic key rotation

## 11) Explicit Anti-Overengineering Guard

For v1.0, any feature is rejected if:
- It does not reduce a defined risk, and
- It does not measurably improve post-cost tradable edge, or
- It increases critical-path latency without a risk-compensation benefit.

## 12) Inheritance from Previous Architecture Drafts

This v1.0 baseline intentionally preserves the strongest elements from prior diagrams:
- Constitution-first control
- Uncertainty-first propagation
- Deterministic state machine transitions
- Separation of evidence, decision, risk, and execution authority
- Inline circuit breaker and dual-mode kill switch
- Auditability and bounded adaptive learning

What changed for practical solo implementation:
- Critical path simplified
- Scope constrained to single symbol and single venue
- Experimental modules moved out of v1.0 live path

---

Implementation starts from this file.
Any rule change requires explicit version bump and changelog entry.
