from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime

import httpx
from ats_contracts.models import (
    BookTicker,
    DepthLevel,
    DepthSnapshot,
    FundingSnapshot,
    MarketDataSnapshot,
    TradeTick,
)

QueryScalar = str | int | float | bool | None
QueryValue = QueryScalar | list[QueryScalar] | tuple[QueryScalar, ...]
QueryParams = Mapping[str, QueryValue]


def _ms_to_datetime(ms: int | None) -> datetime | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


class BinanceUMPublicClient:
    def __init__(
        self,
        base_url: str = "https://fapi.binance.com",
        timeout_seconds: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def _get_json(self, path: str, params: QueryParams) -> object:
        if self._client is None:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
            ) as client:
                response = await client.get(path, params=params)
        else:
            response = await self._client.get(path, params=params)

        response.raise_for_status()
        return response.json()

    async def fetch_book_ticker(self, symbol: str) -> BookTicker:
        payload = await self._get_json("/fapi/v1/ticker/bookTicker", {"symbol": symbol})
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected book ticker payload type")

        event_ms = payload.get("time")
        if event_ms is None:
            event_ms = payload.get("updateTime")

        return BookTicker(
            symbol=str(payload.get("symbol", symbol)),
            event_time=_ms_to_datetime(int(event_ms)) if event_ms is not None else None,
            bid_price=float(payload["bidPrice"]),
            bid_qty=float(payload["bidQty"]),
            ask_price=float(payload["askPrice"]),
            ask_qty=float(payload["askQty"]),
        )

    async def fetch_depth(self, symbol: str, limit: int = 100) -> DepthSnapshot:
        payload = await self._get_json(
            "/fapi/v1/depth",
            {"symbol": symbol, "limit": limit},
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected depth payload type")

        bids = [
            DepthLevel(price=float(row[0]), qty=float(row[1]))
            for row in payload.get("bids", [])
        ]
        asks = [
            DepthLevel(price=float(row[0]), qty=float(row[1]))
            for row in payload.get("asks", [])
        ]

        event_ms = payload.get("E")
        return DepthSnapshot(
            symbol=symbol,
            event_time=_ms_to_datetime(int(event_ms)) if event_ms is not None else None,
            bids=bids,
            asks=asks,
        )

    async def fetch_trades(self, symbol: str, limit: int = 200) -> list[TradeTick]:
        payload = await self._get_json(
            "/fapi/v1/trades",
            {"symbol": symbol, "limit": limit},
        )
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected trades payload type")

        trades: list[TradeTick] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            trades.append(
                TradeTick(
                    trade_id=int(row["id"]),
                    price=float(row["price"]),
                    qty=float(row["qty"]),
                    is_buyer_maker=bool(row.get("isBuyerMaker", False)),
                    trade_time=_ms_to_datetime(int(row["time"])) or datetime.now(UTC),
                )
            )

        if not trades:
            raise RuntimeError("Trades payload is empty")

        return trades

    async def fetch_funding(self, symbol: str) -> FundingSnapshot:
        payload = await self._get_json("/fapi/v1/premiumIndex", {"symbol": symbol})
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected funding payload type")

        event_time = None
        if payload.get("time") is not None:
            event_time = _ms_to_datetime(int(payload["time"]))

        next_funding_time = None
        if payload.get("nextFundingTime") is not None:
            next_funding_time = _ms_to_datetime(int(payload["nextFundingTime"]))

        return FundingSnapshot(
            symbol=str(payload.get("symbol", symbol)),
            funding_rate=float(payload.get("lastFundingRate", 0.0)),
            mark_price=float(payload.get("markPrice", 0.0) or 0.0),
            event_time=event_time,
            next_funding_time=next_funding_time,
        )

    async def fetch_snapshot(
        self,
        symbol: str,
        depth_limit: int = 100,
        trade_limit: int = 200,
    ) -> MarketDataSnapshot:
        book, depth, trades, funding = await asyncio.gather(
            self.fetch_book_ticker(symbol),
            self.fetch_depth(symbol, limit=depth_limit),
            self.fetch_trades(symbol, limit=trade_limit),
            self.fetch_funding(symbol),
        )

        return MarketDataSnapshot(
            symbol=symbol,
            collected_at=datetime.now(UTC),
            book_ticker=book,
            depth_snapshot=depth,
            trades=trades,
            funding=funding,
        )
