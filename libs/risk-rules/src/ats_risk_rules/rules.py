from __future__ import annotations

from enum import IntEnum

from ats_contracts.models import ReasonCode, RiskDecision, RiskEvaluationInput, TradeAction


class GuardTrigger(IntEnum):
    STRATEGY_INTENT = 6
    RISK_LIMIT = 5
    NO_TRADE_ZONE = 4
    LIQUIDITY_GATE = 3
    CIRCUIT_BREAKER = 2
    CONSTITUTION_BREACH = 1


_DEFAULT_GUARD_PRECEDENCE = [
    "CONSTITUTION_BREACH",
    "CIRCUIT_BREAKER",
    "LIQUIDITY_GATE",
    "NO_TRADE_ZONE",
    "RISK_LIMIT",
    "STRATEGY_INTENT",
]

_GUARD_BY_NAME = {
    "CONSTITUTION_BREACH": GuardTrigger.CONSTITUTION_BREACH,
    "CIRCUIT_BREAKER": GuardTrigger.CIRCUIT_BREAKER,
    "LIQUIDITY_GATE": GuardTrigger.LIQUIDITY_GATE,
    "NO_TRADE_ZONE": GuardTrigger.NO_TRADE_ZONE,
    "RISK_LIMIT": GuardTrigger.RISK_LIMIT,
    "STRATEGY_INTENT": GuardTrigger.STRATEGY_INTENT,
}


def _guard_ranks(guard_precedence: list[str] | None) -> dict[GuardTrigger, int]:
    ranks: dict[GuardTrigger, int] = {}
    raw = guard_precedence or _DEFAULT_GUARD_PRECEDENCE

    ordered = [name.strip().upper() for name in raw if name.strip()]
    for index, name in enumerate(ordered):
        trigger = _GUARD_BY_NAME.get(name)
        if trigger is not None and trigger not in ranks:
            ranks[trigger] = index

    fallback_rank = len(ranks)
    for name in _DEFAULT_GUARD_PRECEDENCE:
        trigger = _GUARD_BY_NAME[name]
        if trigger not in ranks:
            ranks[trigger] = fallback_rank
            fallback_rank += 1

    return ranks


def select_top_guard(
    active_guards: list[GuardTrigger],
    guard_precedence: list[str] | None = None,
) -> GuardTrigger | None:
    """Return highest-priority guard according to immutable precedence."""
    if not active_guards:
        return None
    ranks = _guard_ranks(guard_precedence)
    return min(active_guards, key=lambda guard: ranks.get(guard, 9_999))


def _strategy_block_reason(input_data: RiskEvaluationInput) -> ReasonCode:
    for code in input_data.decision.reason_codes:
        if code != ReasonCode.OK:
            return code
    if input_data.decision.edge_bps_after_cost <= 0:
        return ReasonCode.NO_HORIZON_PASSED
    return ReasonCode.OK


def _has_strategy_block(input_data: RiskEvaluationInput) -> bool:
    if input_data.reduce_only:
        return False
    return _strategy_block_reason(input_data) != ReasonCode.OK


def _collect_active_guards(input_data: RiskEvaluationInput) -> list[GuardTrigger]:
    active_guards: list[GuardTrigger] = []

    if input_data.constitution_breach:
        active_guards.append(GuardTrigger.CONSTITUTION_BREACH)
    if input_data.circuit_breaker_triggered:
        active_guards.append(GuardTrigger.CIRCUIT_BREAKER)
    if not input_data.liquidity_gate_passed:
        active_guards.append(GuardTrigger.LIQUIDITY_GATE)
    if input_data.ntz_blocked:
        active_guards.append(GuardTrigger.NO_TRADE_ZONE)
    if (
        not input_data.risk_limits_passed
        or input_data.proposed_size_usd <= 0
        or input_data.proposed_leverage <= 0
    ):
        active_guards.append(GuardTrigger.RISK_LIMIT)
    if _has_strategy_block(input_data):
        active_guards.append(GuardTrigger.STRATEGY_INTENT)

    return active_guards


def _reason_for_guard(input_data: RiskEvaluationInput, guard: GuardTrigger) -> ReasonCode:
    if guard == GuardTrigger.CONSTITUTION_BREACH:
        return ReasonCode.CONSTITUTION_BREACH
    if guard == GuardTrigger.CIRCUIT_BREAKER:
        return ReasonCode.CIRCUIT_BREAKER
    if guard == GuardTrigger.LIQUIDITY_GATE:
        return ReasonCode.LIQUIDITY_GATE
    if guard == GuardTrigger.NO_TRADE_ZONE:
        return ReasonCode.NO_TRADE_ZONE
    if guard == GuardTrigger.RISK_LIMIT:
        return ReasonCode.RISK_LIMIT
    return _strategy_block_reason(input_data)


def decide_risk_decision(
    input_data: RiskEvaluationInput,
    guard_precedence: list[str] | None = None,
) -> RiskDecision:
    active_guards = _collect_active_guards(input_data)
    top_guard = select_top_guard(active_guards, guard_precedence=guard_precedence)

    if top_guard is not None:
        reason = _reason_for_guard(input_data, top_guard)
        return RiskDecision(
            request_id=input_data.request_id,
            action=TradeAction.DENY,
            size_usd=0.0,
            leverage=0.0,
            stop_loss_bps=0,
            time_stop_seconds=0,
            reason_codes=[reason],
        )

    return RiskDecision(
        request_id=input_data.request_id,
        action=TradeAction.ALLOW,
        size_usd=input_data.proposed_size_usd,
        leverage=input_data.proposed_leverage,
        stop_loss_bps=input_data.stop_loss_bps,
        time_stop_seconds=input_data.time_stop_seconds,
        reason_codes=[ReasonCode.OK],
    )
