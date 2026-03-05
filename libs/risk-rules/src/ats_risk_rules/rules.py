from __future__ import annotations

from enum import IntEnum


class GuardTrigger(IntEnum):
    STRATEGY_INTENT = 6
    RISK_LIMIT = 5
    NO_TRADE_ZONE = 4
    LIQUIDITY_GATE = 3
    CIRCUIT_BREAKER = 2
    CONSTITUTION_BREACH = 1


def select_top_guard(active_guards: list[GuardTrigger]) -> GuardTrigger | None:
    """Return highest-priority guard according to immutable precedence."""
    if not active_guards:
        return None
    return min(active_guards)
