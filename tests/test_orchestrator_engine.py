from datetime import UTC, datetime, timedelta

import pytest
from ats_contracts.models import (
    BookTicker,
    DataLayerResult,
    DataSanityDiagnostics,
    DepthLevel,
    DepthSnapshot,
    FundingSnapshot,
    HorizonWindowCandidate,
    LiquidityGateInput,
    MarketDataSnapshot,
    ReasonCode,
    TradeTick,
)
from ats_evidence_swarm.binance_um import BinanceUMPublicClient
from ats_orchestrator.engine import PaperExecutionConfig, PaperRunInput, run_paper_cycle
from ats_risk_rules.constitution import load_constitution


def _data_layer_result() -> DataLayerResult:
    now = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)

    snapshot = MarketDataSnapshot(
        symbol="BTCUSDT",
        collected_at=now,
        book_ticker=BookTicker(
            symbol="BTCUSDT",
            event_time=now - timedelta(milliseconds=120),
            bid_price=100_000.0,
            bid_qty=5.0,
            ask_price=100_010.0,
            ask_qty=4.8,
        ),
        depth_snapshot=DepthSnapshot(
            symbol="BTCUSDT",
            event_time=now - timedelta(milliseconds=120),
            bids=[
                DepthLevel(price=100_000.0, qty=8.0),
                DepthLevel(price=99_990.0, qty=7.0),
            ],
            asks=[
                DepthLevel(price=100_010.0, qty=8.2),
                DepthLevel(price=100_020.0, qty=7.3),
            ],
        ),
        trades=[
            TradeTick(
                trade_id=1,
                price=99_980.0,
                qty=1.2,
                is_buyer_maker=False,
                trade_time=now - timedelta(milliseconds=400),
            ),
            TradeTick(
                trade_id=2,
                price=99_990.0,
                qty=1.1,
                is_buyer_maker=True,
                trade_time=now - timedelta(milliseconds=320),
            ),
            TradeTick(
                trade_id=3,
                price=100_000.0,
                qty=1.0,
                is_buyer_maker=False,
                trade_time=now - timedelta(milliseconds=250),
            ),
            TradeTick(
                trade_id=4,
                price=100_005.0,
                qty=1.3,
                is_buyer_maker=True,
                trade_time=now - timedelta(milliseconds=200),
            ),
            TradeTick(
                trade_id=5,
                price=100_012.0,
                qty=1.4,
                is_buyer_maker=False,
                trade_time=now - timedelta(milliseconds=150),
            ),
            TradeTick(
                trade_id=6,
                price=100_018.0,
                qty=1.25,
                is_buyer_maker=True,
                trade_time=now - timedelta(milliseconds=120),
            ),
        ],
        funding=FundingSnapshot(
            symbol="BTCUSDT",
            funding_rate=0.00025,
            mark_price=100_005.0,
            event_time=now - timedelta(milliseconds=150),
            next_funding_time=now + timedelta(hours=3),
        ),
    )

    diagnostics = DataSanityDiagnostics(
        feed_delay_ms=120.0,
        feed_delay_anomaly=False,
        outlier_tick_anomaly=False,
        volume_anomaly=False,
        volume_z_score=None,
        anomaly_flags=["SANITY_OK"],
        uncertainty_contrib=0.12,
        data_quality_score=0.88,
    )

    return DataLayerResult(market_snapshot=snapshot, diagnostics=diagnostics)


@pytest.mark.asyncio
async def test_run_paper_cycle_allow_path() -> None:
    input_data = PaperRunInput(
        request_id="orch-allow-1",
        symbol="BTCUSDT",
        data_layer_override=_data_layer_result(),
        decision_candidates=[
            HorizonWindowCandidate(
                horizon="15m",
                window_days=60,
                sample_size=260,
                walk_forward_score=1.1,
                embargo_passed=True,
                gross_edge_bps=14.0,
                fee_bps=1.8,
                slippage_bps=1.0,
                funding_bps=0.4,
                impact_bps=0.8,
            )
        ],
        execution=PaperExecutionConfig(
            liquidity=LiquidityGateInput(
                spread_bps=4.0,
                depth_1pct_usd=100_000.0,
                expected_impact_bps=5.0,
            ),
        ),
    )

    result = await run_paper_cycle(
        input_data=input_data,
        constitution=load_constitution(),
        market_client=BinanceUMPublicClient(),
    )

    assert result.used_live_data is False
    assert result.decision.reason_codes == [ReasonCode.OK]
    assert result.risk_decision.reason_codes == [ReasonCode.OK]
    assert result.execution_result.report.accepted is True
    assert result.monitoring_result.recommended_action in {
        "KEEP_LIVE",
        "REDUCE_LIVE_SIZE",
        "DEMOTE_TO_SHADOW",
    }


@pytest.mark.asyncio
async def test_run_paper_cycle_denies_without_valid_horizon() -> None:
    input_data = PaperRunInput(
        request_id="orch-deny-1",
        symbol="BTCUSDT",
        data_layer_override=_data_layer_result(),
        decision_candidates=[
            HorizonWindowCandidate(
                horizon="15m",
                window_days=60,
                sample_size=80,
                walk_forward_score=1.0,
                embargo_passed=True,
                gross_edge_bps=12.0,
                fee_bps=1.8,
                slippage_bps=1.0,
                funding_bps=0.4,
                impact_bps=0.8,
            )
        ],
    )

    result = await run_paper_cycle(
        input_data=input_data,
        constitution=load_constitution(),
        market_client=BinanceUMPublicClient(),
    )

    assert result.decision.reason_codes == [ReasonCode.NO_HORIZON_PASSED]
    assert result.risk_decision.reason_codes == [ReasonCode.NO_HORIZON_PASSED]
    assert result.execution_result.report.accepted is False
    assert result.execution_result.report.reason_codes == [ReasonCode.NO_HORIZON_PASSED]
