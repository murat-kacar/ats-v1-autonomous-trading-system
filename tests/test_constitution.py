from pathlib import Path

from ats_contracts.models import StateMode
from ats_risk_rules.constitution import load_constitution


def test_constitution_file_loads_from_repo() -> None:
    cfg = load_constitution(Path("infra/config/constitution.v1.json"))

    assert cfg.total_capital_usd == 1000.0
    assert cfg.max_drawdown_pct == 50.0
    assert cfg.drawdown_thresholds.caution_pct == 20.0
    assert cfg.drawdown_thresholds.defense_pct == 35.0
    assert cfg.cooldowns.post_halt_shadow_only_hours == 24
    assert cfg.mode_limits[StateMode.NORMAL].max_positions == 5
    assert cfg.mode_limits[StateMode.HALT].max_leverage == 0.0
