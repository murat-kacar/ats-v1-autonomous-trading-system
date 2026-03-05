from __future__ import annotations

from ats_contracts.models import (
    DataLayerResult,
    DataSanityDiagnostics,
    DataSanityInput,
    MarketDataFetchInput,
)
from fastapi import FastAPI, HTTPException

from .binance_um import BinanceUMPublicClient
from .sanity import evaluate_data_sanity

app = FastAPI(title="ats-evidence-swarm", version="0.1.0")
_client = BinanceUMPublicClient()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "evidence-swarm"}


@app.post("/v1/data/sanity/evaluate", response_model=DataSanityDiagnostics)
def evaluate_sanity(input_data: DataSanityInput) -> DataSanityDiagnostics:
    return evaluate_data_sanity(input_data)


@app.post("/v1/data/fetch-snapshot", response_model=DataLayerResult)
async def fetch_snapshot(input_data: MarketDataFetchInput) -> DataLayerResult:
    symbol = input_data.symbol.upper().strip()

    try:
        snapshot = await _client.fetch_snapshot(
            symbol=symbol,
            depth_limit=input_data.depth_limit,
            trade_limit=input_data.trade_limit,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=502, detail=f"Upstream data fetch failed: {exc}") from exc

    diagnostics = evaluate_data_sanity(
        DataSanityInput(
            market_snapshot=snapshot,
            max_feed_delay_ms=input_data.max_feed_delay_ms,
            outlier_tick_z_threshold=input_data.outlier_tick_z_threshold,
            volume_z_threshold=input_data.volume_z_threshold,
            volume_baseline_qty_1m=input_data.volume_baseline_qty_1m,
            volume_baseline_std_1m=input_data.volume_baseline_std_1m,
        )
    )

    return DataLayerResult(market_snapshot=snapshot, diagnostics=diagnostics)
