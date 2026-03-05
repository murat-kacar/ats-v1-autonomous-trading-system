from ats_risk_rules.rules import GuardTrigger, select_top_guard


def test_constitution_guard_wins() -> None:
    guard = select_top_guard(
        [
            GuardTrigger.STRATEGY_INTENT,
            GuardTrigger.RISK_LIMIT,
            GuardTrigger.CONSTITUTION_BREACH,
        ]
    )
    assert guard == GuardTrigger.CONSTITUTION_BREACH


def test_empty_guard_list() -> None:
    assert select_top_guard([]) is None
