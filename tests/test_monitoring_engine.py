from ats_contracts.models import MonitoringEvaluationInput
from ats_monitoring.engine import evaluate_monitoring


def test_monitoring_detects_dual_channel_drift() -> None:
    input_data = MonitoringEvaluationInput(
        request_id="m-1",
        recent_trade_pnls=[-5.0] * 45 + [6.0] * 5,
        baseline_pnl_mean=2.0,
        baseline_pnl_std=1.0,
        ci_coverage=0.60,
        brier_score=0.45,
        baseline_brier_score=0.20,
    )

    result = evaluate_monitoring(input_data)

    assert result.pnl_drift is True
    assert result.calibration_drift is True
    assert result.dual_channel_drift is True
    assert result.recommended_action == "DEMOTE_TO_SHADOW"


def test_monitoring_without_drift_keeps_live() -> None:
    input_data = MonitoringEvaluationInput(
        request_id="m-2",
        recent_trade_pnls=[1.0, -0.5, 0.8, 1.2, -0.2, 0.4],
        baseline_pnl_mean=0.45,
        baseline_pnl_std=0.50,
        ci_coverage=0.75,
        brier_score=0.15,
        baseline_brier_score=0.14,
    )

    result = evaluate_monitoring(input_data)

    assert result.pnl_drift is False
    assert result.calibration_drift is False
    assert result.dual_channel_drift is False
    assert result.recommended_action == "KEEP_LIVE"
