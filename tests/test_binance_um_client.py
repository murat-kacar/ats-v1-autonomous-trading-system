from datetime import UTC, datetime

import httpx
import pytest
from ats_evidence_swarm.binance_um import BinanceUMPublicClient


@pytest.mark.asyncio
async def test_fetch_snapshot_maps_binance_payloads() -> None:
    ts_ms = int(datetime(2026, 3, 5, 16, 0, tzinfo=UTC).timestamp() * 1000)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path == "/fapi/v1/ticker/bookTicker":
            return httpx.Response(
                200,
                json={
                    "symbol": "BTCUSDT",
                    "time": ts_ms,
                    "bidPrice": "100.0",
                    "bidQty": "3.2",
                    "askPrice": "100.1",
                    "askQty": "2.8",
                },
            )

        if path == "/fapi/v1/depth":
            return httpx.Response(
                200,
                json={
                    "E": ts_ms,
                    "bids": [["100.0", "10.0"]],
                    "asks": [["100.2", "12.0"]],
                },
            )

        if path == "/fapi/v1/trades":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 1,
                        "price": "100.0",
                        "qty": "0.5",
                        "isBuyerMaker": False,
                        "time": ts_ms,
                    },
                    {
                        "id": 2,
                        "price": "100.1",
                        "qty": "0.6",
                        "isBuyerMaker": True,
                        "time": ts_ms,
                    },
                ],
            )

        if path == "/fapi/v1/premiumIndex":
            return httpx.Response(
                200,
                json={
                    "symbol": "BTCUSDT",
                    "lastFundingRate": "0.0001",
                    "markPrice": "100.05",
                    "time": ts_ms,
                    "nextFundingTime": ts_ms + 28_800_000,
                },
            )

        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://fapi.binance.com",
        transport=transport,
    ) as client:
        adapter = BinanceUMPublicClient(client=client)
        snapshot = await adapter.fetch_snapshot(
            "BTCUSDT",
            depth_limit=10,
            trade_limit=2,
        )

    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.book_ticker.bid_price == 100.0
    assert snapshot.depth_snapshot.bids[0].qty == 10.0
    assert len(snapshot.trades) == 2
    assert snapshot.funding is not None
    assert snapshot.funding.funding_rate == 0.0001


@pytest.mark.asyncio
async def test_fetch_trades_raises_when_payload_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/trades":
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://fapi.binance.com",
        transport=transport,
    ) as client:
        adapter = BinanceUMPublicClient(client=client)
        with pytest.raises(RuntimeError, match="Trades payload is empty"):
            await adapter.fetch_trades("BTCUSDT", limit=20)
