import os
from datetime import UTC, datetime, timedelta

from ats_contracts.models import (
    BookTicker,
    DataLayerResult,
    DataSanityDiagnostics,
    DepthLevel,
    DepthSnapshot,
    HorizonWindowCandidate,
    MarketDataSnapshot,
    TradeTick,
)
from ats_orchestrator.engine import PaperExecutionConfig, PaperRunInput
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from ats_orchestrator.main import app


def _data_layer_result() -> DataLayerResult:
    now = datetime(2026, 3, 6, 12, 15, tzinfo=UTC)

    snapshot = MarketDataSnapshot(
        symbol="BTCUSDT",
        collected_at=now,
        book_ticker=BookTicker(
            symbol="BTCUSDT",
            event_time=now - timedelta(milliseconds=120),
            bid_price=100_000.0,
            bid_qty=4.2,
            ask_price=100_010.0,
            ask_qty=4.1,
        ),
        depth_snapshot=DepthSnapshot(
            symbol="BTCUSDT",
            event_time=now - timedelta(milliseconds=120),
            bids=[DepthLevel(price=100_000.0, qty=6.0)],
            asks=[DepthLevel(price=100_010.0, qty=6.2)],
        ),
        trades=[
            TradeTick(
                trade_id=1,
                price=99_990.0,
                qty=1.1,
                is_buyer_maker=False,
                trade_time=now - timedelta(milliseconds=300),
            ),
            TradeTick(
                trade_id=2,
                price=100_008.0,
                qty=1.3,
                is_buyer_maker=True,
                trade_time=now - timedelta(milliseconds=120),
            ),
        ],
        funding=None,
    )

    diagnostics = DataSanityDiagnostics(
        feed_delay_ms=120.0,
        feed_delay_anomaly=False,
        outlier_tick_anomaly=False,
        volume_anomaly=False,
        volume_z_score=None,
        anomaly_flags=["SANITY_OK"],
        uncertainty_contrib=0.10,
        data_quality_score=0.90,
    )

    return DataLayerResult(market_snapshot=snapshot, diagnostics=diagnostics)


def test_orchestrator_paper_run_once_endpoint() -> None:
    client = TestClient(app)

    payload = PaperRunInput(
        request_id="orch-api-1",
        symbol="BTCUSDT",
        data_layer_override=_data_layer_result(),
        decision_candidates=[
            HorizonWindowCandidate(
                horizon="15m",
                window_days=60,
                sample_size=220,
                walk_forward_score=1.0,
                embargo_passed=True,
                gross_edge_bps=12.0,
                fee_bps=1.8,
                slippage_bps=1.0,
                funding_bps=0.4,
                impact_bps=0.8,
            )
        ],
        execution=PaperExecutionConfig(
            liquidity={
                "spread_bps": 4.0,
                "depth_1pct_usd": 80_000.0,
                "expected_impact_bps": 4.0,
            }
        ),
    ).model_dump(mode="json")

    response = client.post("/v1/paper/run-once", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "orch-api-1"
    assert body["decision"]["reason_codes"] in [["OK"], ["NO_HORIZON_PASSED"]]
    assert body["risk_decision"]["reason_codes"]
    assert "monitoring_result" in body
