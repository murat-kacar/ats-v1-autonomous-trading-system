from datetime import UTC, datetime, timedelta

from ats_contracts.models import (
    BookTicker,
    DataSanityInput,
    DepthLevel,
    DepthSnapshot,
    FundingSnapshot,
    MarketDataSnapshot,
    TradeTick,
)
from ats_evidence_swarm.sanity import evaluate_data_sanity


def _snapshot(
    now: datetime,
    *,
    prices: list[float],
    qtys: list[float],
    age_ms: int,
) -> MarketDataSnapshot:
    trades = [
        TradeTick(
            trade_id=i + 1,
            price=price,
            qty=qty,
            is_buyer_maker=bool(i % 2),
            trade_time=now - timedelta(milliseconds=age_ms + (len(prices) - i) * 20),
        )
        for i, (price, qty) in enumerate(zip(prices, qtys, strict=True))
    ]

    return MarketDataSnapshot(
        symbol="BTCUSDT",
        collected_at=now,
        book_ticker=BookTicker(
            symbol="BTCUSDT",
            event_time=now - timedelta(milliseconds=age_ms),
            bid_price=100.0,
            bid_qty=2.0,
            ask_price=100.1,
            ask_qty=1.8,
        ),
        depth_snapshot=DepthSnapshot(
            symbol="BTCUSDT",
            event_time=now - timedelta(milliseconds=age_ms),
            bids=[DepthLevel(price=100.0, qty=3.0)],
            asks=[DepthLevel(price=100.2, qty=2.5)],
        ),
        trades=trades,
        funding=FundingSnapshot(
            symbol="BTCUSDT",
            funding_rate=0.0001,
            mark_price=100.0,
            event_time=now - timedelta(milliseconds=age_ms),
            next_funding_time=now + timedelta(hours=2),
        ),
    )


def test_sanity_nominal_case_has_high_quality() -> None:
    now = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)
    snapshot = _snapshot(
        now,
        prices=[100.0, 100.1, 100.15, 100.2, 100.18, 100.16],
        qtys=[0.5, 0.6, 0.55, 0.5, 0.65, 0.52],
        age_ms=180,
    )

    result = evaluate_data_sanity(DataSanityInput(market_snapshot=snapshot))

    assert result.feed_delay_anomaly is False
    assert result.outlier_tick_anomaly is False
    assert result.volume_anomaly is False
    assert result.uncertainty_contrib == 0.0
    assert result.data_quality_score == 1.0


def test_sanity_feed_delay_penalizes_uncertainty() -> None:
    now = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)
    snapshot = _snapshot(
        now,
        prices=[100.0, 100.1, 100.05, 100.08, 100.07, 100.09],
        qtys=[0.4, 0.5, 0.45, 0.41, 0.42, 0.39],
        age_ms=3000,
    )

    result = evaluate_data_sanity(
        DataSanityInput(
            market_snapshot=snapshot,
            max_feed_delay_ms=1500,
        )
    )

    assert result.feed_delay_anomaly is True
    assert "FEED_DELAY_ANOMALY" in result.anomaly_flags
    assert result.uncertainty_contrib > 0.0
    assert result.data_quality_score < 1.0


def test_sanity_outlier_tick_detected() -> None:
    now = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)
    snapshot = _snapshot(
        now,
        prices=[100.0, 100.0, 100.02, 100.01, 99.99, 105.0],
        qtys=[0.5, 0.51, 0.49, 0.52, 0.5, 0.48],
        age_ms=200,
    )

    result = evaluate_data_sanity(
        DataSanityInput(
            market_snapshot=snapshot,
            outlier_tick_z_threshold=4.0,
        )
    )

    assert result.outlier_tick_anomaly is True
    assert "OUTLIER_TICK" in result.anomaly_flags
    assert result.uncertainty_contrib > 0.0


def test_sanity_volume_anomaly_detected_when_baseline_provided() -> None:
    now = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)
    snapshot = _snapshot(
        now,
        prices=[100.0, 100.03, 100.02, 100.05, 100.04, 100.01],
        qtys=[2.0, 2.2, 2.1, 1.9, 2.3, 2.4],
        age_ms=220,
    )

    result = evaluate_data_sanity(
        DataSanityInput(
            market_snapshot=snapshot,
            volume_baseline_qty_1m=2.0,
            volume_baseline_std_1m=0.5,
            volume_z_threshold=4.0,
        )
    )

    assert result.volume_z_score is not None
    assert result.volume_z_score > 4.0
    assert result.volume_anomaly is True
    assert "VOLUME_ANOMALY" in result.anomaly_flags
