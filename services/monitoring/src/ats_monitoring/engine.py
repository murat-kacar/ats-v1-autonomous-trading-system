from __future__ import annotations

import statistics

from ats_contracts.models import MonitoringEvaluationInput, MonitoringEvaluationResult


def _safe_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.pstdev(values)


def _drawdown(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0

    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    return max_dd


def _risk_metrics(pnls: list[float]) -> tuple[float, float, float, float]:
    mean_pnl = statistics.fmean(pnls)
    std_pnl = _safe_std(pnls)

    sharpe = 0.0 if std_pnl <= 0.0 else mean_pnl / std_pnl

    downside = [pnl for pnl in pnls if pnl < 0.0]
    downside_std = _safe_std(downside)
    sortino = 0.0 if downside_std <= 0.0 else mean_pnl / downside_std

    max_dd = _drawdown(pnls)
    calmar = 0.0 if max_dd <= 0.0 else mean_pnl / max_dd

    hits = len([pnl for pnl in pnls if pnl > 0.0])
    hit_rate = hits / len(pnls)

    return sharpe, sortino, calmar, hit_rate


def evaluate_monitoring(input_data: MonitoringEvaluationInput) -> MonitoringEvaluationResult:
    mean_recent = statistics.fmean(input_data.recent_trade_pnls)
    pnl_z = abs(mean_recent - input_data.baseline_pnl_mean) / input_data.baseline_pnl_std

    pnl_drift = len(input_data.recent_trade_pnls) >= 50 and pnl_z > 2.0

    brier_ratio = input_data.brier_score / input_data.baseline_brier_score
    calibration_drift = input_data.ci_coverage < 0.65 or brier_ratio > 1.5

    dual_channel_drift = pnl_drift and calibration_drift

    if dual_channel_drift:
        recommended_action = "DEMOTE_TO_SHADOW"
    elif pnl_drift or calibration_drift:
        recommended_action = "REDUCE_LIVE_SIZE"
    else:
        recommended_action = "KEEP_LIVE"

    sharpe, sortino, calmar, hit_rate = _risk_metrics(input_data.recent_trade_pnls)

    return MonitoringEvaluationResult(
        request_id=input_data.request_id,
        pnl_drift=pnl_drift,
        calibration_drift=calibration_drift,
        dual_channel_drift=dual_channel_drift,
        recommended_action=recommended_action,
        pnl_z_score=pnl_z,
        ci_coverage=input_data.ci_coverage,
        brier_ratio=brier_ratio,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        hit_rate=hit_rate,
    )
