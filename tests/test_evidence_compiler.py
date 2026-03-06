import time
from datetime import UTC, datetime, timedelta

import pytest
from ats_contracts.models import (
    BookTicker,
    DataLayerResult,
    DataSanityDiagnostics,
    DepthLevel,
    DepthSnapshot,
    FundingSnapshot,
    MarketDataSnapshot,
    TradeTick,
)
from ats_evidence_swarm.experts import (
    ExpertSignal,
    assert_advisory_only,
    compile_evidence_packet,
    run_expert_with_fallback,
)


def _data_layer_result() -> DataLayerResult:
    now = datetime(2026, 3, 5, 17, 0, tzinfo=UTC)

    snapshot = MarketDataSnapshot(
        symbol="BTCUSDT",
        collected_at=now,
        book_ticker=BookTicker(
            symbol="BTCUSDT",
            event_time=now - timedelta(milliseconds=120),
            bid_price=100.0,
            bid_qty=4.0,
            ask_price=100.1,
            ask_qty=3.8,
        ),
        depth_snapshot=DepthSnapshot(
            symbol="BTCUSDT",
            event_time=now - timedelta(milliseconds=120),
            bids=[
                DepthLevel(price=100.0, qty=4.0),
                DepthLevel(price=99.9, qty=3.5),
            ],
            asks=[
                DepthLevel(price=100.1, qty=3.8),
                DepthLevel(price=100.2, qty=3.6),
            ],
        ),
        trades=[
            TradeTick(
                trade_id=1,
                price=100.0,
                qty=0.8,
                is_buyer_maker=False,
                trade_time=now - timedelta(milliseconds=400),
            ),
            TradeTick(
                trade_id=2,
                price=100.05,
                qty=0.9,
                is_buyer_maker=True,
                trade_time=now - timedelta(milliseconds=300),
            ),
            TradeTick(
                trade_id=3,
                price=100.1,
                qty=1.0,
                is_buyer_maker=False,
                trade_time=now - timedelta(milliseconds=200),
            ),
            TradeTick(
                trade_id=4,
                price=100.08,
                qty=0.7,
                is_buyer_maker=True,
                trade_time=now - timedelta(milliseconds=160),
            ),
            TradeTick(
                trade_id=5,
                price=100.12,
                qty=0.95,
                is_buyer_maker=False,
                trade_time=now - timedelta(milliseconds=120),
            ),
        ],
        funding=FundingSnapshot(
            symbol="BTCUSDT",
            funding_rate=0.0002,
            mark_price=100.08,
            event_time=now - timedelta(milliseconds=150),
            next_funding_time=now + timedelta(hours=2),
        ),
    )

    diagnostics = DataSanityDiagnostics(
        feed_delay_ms=120.0,
        feed_delay_anomaly=False,
        outlier_tick_anomaly=False,
        volume_anomaly=False,
        volume_z_score=None,
        anomaly_flags=["SANITY_OK"],
        uncertainty_contrib=0.08,
        data_quality_score=0.92,
    )

    return DataLayerResult(market_snapshot=snapshot, diagnostics=diagnostics)


def test_compile_evidence_packet_outputs_all_experts() -> None:
    data_layer = _data_layer_result()

    packet = compile_evidence_packet(request_id="req-42", data_layer=data_layer)

    assert packet.request_id == "req-42"
    assert packet.data_quality_score == data_layer.diagnostics.data_quality_score
    assert packet.uncertainty_score >= data_layer.diagnostics.uncertainty_contrib

    assert "SANITY_OK" in packet.risk_flags
    assert set(packet.source_reliability) == {
        "trend",
        "mean_reversion",
        "volatility",
        "microstructure",
        "funding_basis",
        "macro_correlation",
    }

    assert "trend_direction" in packet.feature_values
    assert "mean_reversion_deviation" in packet.feature_values
    assert "volatility_realized_vol" in packet.feature_values
    assert "microstructure_spread_bps" in packet.feature_values
    assert "funding_basis_funding_rate" in packet.feature_values
    assert "macro_correlation_price_volume_corr" in packet.feature_values


def test_advisory_guard_rejects_trading_authority_tokens() -> None:
    with pytest.raises(ValueError, match="forbidden feature token"):
        assert_advisory_only({"position_action_hint": 1.0}, [])


def test_expert_timeout_returns_neutral_fallback() -> None:
    snapshot = _data_layer_result().market_snapshot

    def _slow_expert(_snapshot: MarketDataSnapshot) -> ExpertSignal:
        time.sleep(0.05)
        return ExpertSignal(
            name="slow_expert",
            direction_score=0.4,
            confidence=0.9,
            features={"foo": 1.0},
            risk_flags=[],
            reliability=0.9,
        )

    signal = run_expert_with_fallback(
        name="slow_expert",
        fn=_slow_expert,
        snapshot=snapshot,
        timeout_seconds=0.001,
    )

    assert signal.direction_score == 0.0
    assert signal.confidence == 0.0
    assert "SLOW_EXPERT_TIMEOUT_FALLBACK" in signal.risk_flags
