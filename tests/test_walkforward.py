from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from ats_orchestrator.walkforward import (
    FundingPoint,
    Genome,
    HistoricalBar,
    WalkforwardConfig,
    attach_funding_rates,
    build_horizon_candidates,
    run_walkforward_replay,
)
from ats_risk_rules.constitution import load_constitution


def _build_bars(count: int) -> list[HistoricalBar]:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    bars: list[HistoricalBar] = []

    price = 42_000.0
    for idx in range(count):
        open_time = start + timedelta(hours=idx)
        close_time = open_time + timedelta(hours=1)

        drift = 0.00035 + (0.0012 * math.sin(idx / 18.0))
        close = max(100.0, price * (1.0 + drift))

        bars.append(
            HistoricalBar(
                open_time=open_time,
                close_time=close_time,
                open=price,
                high=max(price, close) * 1.001,
                low=min(price, close) * 0.999,
                close=close,
                volume=1_000.0 + (120.0 * abs(math.sin(idx / 11.0))),
                funding_rate=0.0001 * math.sin(idx / 16.0),
            )
        )
        price = close

    return bars


def test_attach_funding_rates_uses_latest_rate() -> None:
    bars = _build_bars(6)
    points = [
        FundingPoint(ts=bars[0].open_time, rate=0.0001),
        FundingPoint(ts=bars[3].open_time, rate=-0.0002),
    ]

    enriched = attach_funding_rates(bars, points)

    assert enriched[0].funding_rate == pytest.approx(0.0001)
    assert enriched[2].funding_rate == pytest.approx(0.0001)
    assert enriched[3].funding_rate == pytest.approx(-0.0002)
    assert enriched[5].funding_rate == pytest.approx(-0.0002)


def test_build_horizon_candidates_has_supported_horizons() -> None:
    context = _build_bars(300)

    candidates = build_horizon_candidates(context, Genome())

    assert candidates
    assert {item.horizon for item in candidates}.issubset({"5m", "15m", "1h", "4h"})
    assert all(item.sample_size == len(context) for item in candidates)


@pytest.mark.asyncio
async def test_run_walkforward_replay_smoke() -> None:
    bars = _build_bars(900)

    summary, steps = await run_walkforward_replay(
        bars=bars,
        constitution=load_constitution(),
        config=WalkforwardConfig(symbol="BTCUSDT", warmup_bars=240, max_steps=240),
    )

    assert summary.total_steps == 240
    assert len(steps) == 240
    assert summary.accepted_trades > 0
    assert summary.accepted_trades + summary.denied_steps == summary.total_steps
    assert summary.final_equity_usd > 0.0
    assert isinstance(summary.phase1_exit_passed, bool)
