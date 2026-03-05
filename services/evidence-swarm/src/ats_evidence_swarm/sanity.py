from __future__ import annotations

import statistics
from datetime import datetime

from ats_contracts.models import DataSanityDiagnostics, DataSanityInput, MarketDataSnapshot

_FEED_DELAY_WEIGHT = 0.40
_OUTLIER_WEIGHT = 0.25
_VOLUME_WEIGHT = 0.25


def _latest_market_event(snapshot: MarketDataSnapshot) -> datetime | None:
    points: list[datetime | None] = [
        snapshot.book_ticker.event_time,
        snapshot.depth_snapshot.event_time,
    ]
    if snapshot.funding is not None:
        points.append(snapshot.funding.event_time)

    points.extend(trade.trade_time for trade in snapshot.trades)

    valid_points = [point for point in points if point is not None]
    if not valid_points:
        return None
    return max(valid_points)


def _feed_delay_ms(snapshot: MarketDataSnapshot) -> float | None:
    latest = _latest_market_event(snapshot)
    if latest is None:
        return None

    delay_ms = (snapshot.collected_at - latest).total_seconds() * 1000.0
    return max(0.0, delay_ms)


def _robust_z_score(value: float, samples: list[float]) -> float | None:
    if len(samples) < 5:
        return None

    median = statistics.median(samples)
    deviations = [abs(sample - median) for sample in samples]
    mad = statistics.median(deviations)
    if mad <= 0.0:
        return None

    return abs(value - median) / (1.4826 * mad)


def _scaled_penalty(z_score: float, threshold: float, max_weight: float) -> float:
    if z_score <= threshold:
        return 0.0

    severity = min(1.0, (z_score - threshold) / threshold)
    return max_weight * (0.35 + (0.65 * severity))


def evaluate_data_sanity(input_data: DataSanityInput) -> DataSanityDiagnostics:
    snapshot = input_data.market_snapshot
    flags: list[str] = []
    uncertainty = 0.0

    feed_delay = _feed_delay_ms(snapshot)
    feed_delay_anomaly = False

    if feed_delay is None:
        feed_delay_anomaly = True
        flags.append("FEED_DELAY_MISSING_TS")
        uncertainty += _FEED_DELAY_WEIGHT * 0.65
    elif feed_delay > input_data.max_feed_delay_ms:
        feed_delay_anomaly = True
        flags.append("FEED_DELAY_ANOMALY")
        ratio = (feed_delay - input_data.max_feed_delay_ms) / input_data.max_feed_delay_ms
        severity = min(1.0, ratio)
        uncertainty += _FEED_DELAY_WEIGHT * (0.25 + (0.75 * severity))

    prices = [trade.price for trade in snapshot.trades]
    outlier_z = _robust_z_score(snapshot.trades[-1].price, prices)
    outlier_tick_anomaly = False

    if outlier_z is not None and outlier_z > input_data.outlier_tick_z_threshold:
        outlier_tick_anomaly = True
        flags.append("OUTLIER_TICK")
        uncertainty += _scaled_penalty(
            z_score=outlier_z,
            threshold=input_data.outlier_tick_z_threshold,
            max_weight=_OUTLIER_WEIGHT,
        )

    total_volume_qty = sum(trade.qty for trade in snapshot.trades)
    volume_z: float | None = None
    volume_anomaly = False

    if (
        input_data.volume_baseline_qty_1m is not None
        and input_data.volume_baseline_std_1m is not None
    ):
        volume_z = (
            abs(total_volume_qty - input_data.volume_baseline_qty_1m)
            / input_data.volume_baseline_std_1m
        )
        if volume_z > input_data.volume_z_threshold:
            volume_anomaly = True
            flags.append("VOLUME_ANOMALY")
            uncertainty += _scaled_penalty(
                z_score=volume_z,
                threshold=input_data.volume_z_threshold,
                max_weight=_VOLUME_WEIGHT,
            )

    uncertainty = min(1.0, uncertainty)
    quality = max(0.0, 1.0 - uncertainty)

    return DataSanityDiagnostics(
        feed_delay_ms=feed_delay,
        feed_delay_anomaly=feed_delay_anomaly,
        outlier_tick_anomaly=outlier_tick_anomaly,
        volume_anomaly=volume_anomaly,
        volume_z_score=volume_z,
        anomaly_flags=flags,
        uncertainty_contrib=uncertainty,
        data_quality_score=quality,
    )
