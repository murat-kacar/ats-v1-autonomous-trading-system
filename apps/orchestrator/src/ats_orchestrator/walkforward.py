from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from statistics import fmean, pstdev

import httpx
from ats_contracts.models import (
    BookTicker,
    DataLayerResult,
    DataSanityDiagnostics,
    DepthLevel,
    DepthSnapshot,
    FundingSnapshot,
    HorizonWindowCandidate,
    MarketDataSnapshot,
    ReasonCode,
    StateEvaluationInput,
    StateSnapshot,
    TradeTick,
)
from ats_evidence_swarm.binance_um import BinanceUMPublicClient
from ats_risk_rules.constitution import ConstitutionConfig
from ats_risk_rules.state_machine import evaluate_state_transition

from .engine import (
    PaperExecutionConfig,
    PaperMonitoringConfig,
    PaperRiskConfig,
    PaperRunInput,
    PaperRunResult,
    run_paper_cycle,
)

_INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1_800,
    "1h": 3_600,
    "2h": 7_200,
    "4h": 14_400,
    "6h": 21_600,
    "8h": 28_800,
    "12h": 43_200,
    "1d": 86_400,
}


@dataclass(frozen=True)
class HistoricalBar:
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    funding_rate: float = 0.0


@dataclass(frozen=True)
class FundingPoint:
    ts: datetime
    rate: float


@dataclass(frozen=True)
class Genome:
    fractional_kelly: float = 0.05
    stop_loss_bps: int = 150
    time_stop_seconds: int = 900
    horizon_bias: float = 0.0
    maker_preferred: bool = True


@dataclass(frozen=True)
class WalkforwardConfig:
    symbol: str = "BTCUSDT"
    interval: str = "1h"
    initial_capital_usd: float = 1_000.0
    warmup_bars: int = 240
    context_bars: int = 240
    mode_a_update_every_trades: int = 20
    mode_b_evolve_every_trades: int = 50
    max_steps: int | None = None


@dataclass(frozen=True)
class WalkforwardStep:
    ts: datetime
    request_id: str
    mode: str
    accepted: bool
    decision_reason: str
    execution_reason: str
    selected_horizon: str
    trade_pnl: float
    equity_usd: float


@dataclass(frozen=True)
class WalkforwardSummary:
    symbol: str
    bars_processed: int
    runtime_days: int
    total_steps: int
    accepted_trades: int
    denied_steps: int
    net_pnl_usd: float
    final_equity_usd: float
    max_drawdown_pct: float
    sharpe_like: float
    sortino_like: float
    constitution_breach_count: int
    deny_reason_counts: dict[str, int]
    phase1_30d_runtime: bool
    phase1_50_trades: bool
    phase1_positive_risk_adjusted: bool
    phase1_zero_constitution_breach: bool
    phase1_deny_explainable: bool
    phase1_exit_passed: bool


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_mean(values: list[float]) -> float:
    return fmean(values) if values else 0.0


def _safe_std(values: list[float]) -> float:
    return pstdev(values) if len(values) >= 2 else 0.0


def _returns(values: list[float]) -> list[float]:
    if len(values) < 2:
        return []

    output: list[float] = []
    for prev, current in pairwise(values):
        if prev <= 0.0:
            continue
        output.append((current - prev) / prev)
    return output


def _interval_delta(interval: str) -> timedelta:
    seconds = _INTERVAL_SECONDS.get(interval)
    if seconds is None:
        supported = ", ".join(sorted(_INTERVAL_SECONDS))
        raise ValueError(f"Unsupported interval '{interval}'. Supported: {supported}")
    return timedelta(seconds=seconds)


async def fetch_binance_klines(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    *,
    base_url: str = "https://fapi.binance.com",
    timeout_seconds: float = 15.0,
    limit: int = 1_500,
    http_client: httpx.AsyncClient | None = None,
) -> list[HistoricalBar]:
    if start >= end:
        return []

    step_ms = int(_interval_delta(interval).total_seconds() * 1000)
    start_ms = int(start.astimezone(UTC).timestamp() * 1000)
    end_ms = int(end.astimezone(UTC).timestamp() * 1000)

    own_client = http_client is None
    client = http_client or httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)

    try:
        cursor = start_ms
        bars: list[HistoricalBar] = []

        while cursor < end_ms:
            response = await client.get(
                "/fapi/v1/klines",
                params={
                    "symbol": symbol.upper().strip(),
                    "interval": interval,
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": limit,
                },
            )
            response.raise_for_status()

            payload = response.json()
            if not isinstance(payload, list):
                raise RuntimeError("Unexpected kline payload type")
            if not payload:
                break

            last_open_ms = cursor
            for row in payload:
                if not isinstance(row, list) or len(row) < 7:
                    continue

                open_ms = int(row[0])
                close_ms = int(row[6])
                open_time = datetime.fromtimestamp(open_ms / 1000.0, tz=UTC)
                close_time = datetime.fromtimestamp(close_ms / 1000.0, tz=UTC)

                if open_time < start:
                    continue
                if open_time >= end:
                    continue

                bars.append(
                    HistoricalBar(
                        open_time=open_time,
                        close_time=close_time,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                    )
                )
                last_open_ms = max(last_open_ms, open_ms)

            next_cursor = last_open_ms + step_ms
            if next_cursor <= cursor:
                next_cursor = cursor + step_ms
            cursor = next_cursor

        by_open_time = {bar.open_time: bar for bar in bars}
        return [by_open_time[key] for key in sorted(by_open_time)]
    finally:
        if own_client:
            await client.aclose()


async def fetch_binance_funding_rates(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    base_url: str = "https://fapi.binance.com",
    timeout_seconds: float = 15.0,
    limit: int = 1_000,
    http_client: httpx.AsyncClient | None = None,
) -> list[FundingPoint]:
    if start >= end:
        return []

    start_ms = int(start.astimezone(UTC).timestamp() * 1000)
    end_ms = int(end.astimezone(UTC).timestamp() * 1000)

    own_client = http_client is None
    client = http_client or httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)

    try:
        cursor = start_ms
        points: list[FundingPoint] = []

        while cursor < end_ms:
            response = await client.get(
                "/fapi/v1/fundingRate",
                params={
                    "symbol": symbol.upper().strip(),
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": limit,
                },
            )
            response.raise_for_status()

            payload = response.json()
            if not isinstance(payload, list):
                raise RuntimeError("Unexpected funding payload type")
            if not payload:
                break

            last_time = cursor
            for row in payload:
                if not isinstance(row, dict):
                    continue

                funding_time = int(row.get("fundingTime", 0))
                ts = datetime.fromtimestamp(funding_time / 1000.0, tz=UTC)
                if ts < start:
                    continue
                if ts >= end:
                    continue

                points.append(
                    FundingPoint(
                        ts=ts,
                        rate=float(row.get("fundingRate", 0.0)),
                    )
                )
                last_time = max(last_time, funding_time)

            next_cursor = last_time + 1
            if next_cursor <= cursor:
                break
            cursor = next_cursor

        dedup = {point.ts: point for point in points}
        return [dedup[key] for key in sorted(dedup)]
    finally:
        if own_client:
            await client.aclose()


def attach_funding_rates(
    bars: list[HistoricalBar],
    funding_points: list[FundingPoint],
) -> list[HistoricalBar]:
    if not funding_points:
        return bars

    points = sorted(funding_points, key=lambda item: item.ts)

    idx = 0
    active_rate = points[0].rate
    output: list[HistoricalBar] = []

    for bar in bars:
        while idx + 1 < len(points) and points[idx + 1].ts <= bar.open_time:
            idx += 1
            active_rate = points[idx].rate

        output.append(
            HistoricalBar(
                open_time=bar.open_time,
                close_time=bar.close_time,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                funding_rate=active_rate,
            )
        )

    return output


def _corr(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(ys) < 2 or len(xs) != len(ys):
        return 0.0

    mean_x = _safe_mean(xs)
    mean_y = _safe_mean(ys)

    cov = _safe_mean([(x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=False)])
    std_x = _safe_std(xs)
    std_y = _safe_std(ys)

    denom = std_x * std_y
    if denom <= 0.0:
        return 0.0

    return _clamp(cov / denom, -1.0, 1.0)


def _spread_bps(context: list[HistoricalBar]) -> float:
    closes = [bar.close for bar in context[-64:]]
    vol = _safe_std(_returns(closes))
    return _clamp(2.0 + (vol * 6_500.0), 1.5, 7.5)


def build_data_layer_from_bar(
    symbol: str,
    bar: HistoricalBar,
    context: list[HistoricalBar],
) -> DataLayerResult:
    spread_bps = _spread_bps(context)
    spread_abs = bar.close * (spread_bps / 10_000.0)

    bid = max(1e-9, bar.close - (spread_abs / 2.0))
    ask = max(1e-9, bar.close + (spread_abs / 2.0))

    qty_unit = max(0.01, bar.volume / 10_000.0)

    bids = [
        DepthLevel(price=max(1e-9, bid * (1.0 - (0.0002 * i))), qty=qty_unit * (1.0 + (0.1 * i)))
        for i in range(5)
    ]
    asks = [
        DepthLevel(price=max(1e-9, ask * (1.0 + (0.0002 * i))), qty=qty_unit * (1.0 + (0.1 * i)))
        for i in range(5)
    ]

    trade_path = [bar.open, bar.low, bar.high, bar.close * 0.999, bar.close * 1.001, bar.close]
    duration_seconds = max(1, int((bar.close_time - bar.open_time).total_seconds()))
    tick_step = max(1, duration_seconds // len(trade_path))

    trades: list[TradeTick] = []
    for index, price in enumerate(trade_path, start=1):
        trade_time = bar.open_time + timedelta(seconds=index * tick_step)
        trades.append(
            TradeTick(
                trade_id=index,
                price=max(1e-9, float(price)),
                qty=max(0.0001, qty_unit * 0.75),
                is_buyer_maker=(index % 2 == 0),
                trade_time=trade_time,
            )
        )

    snapshot = MarketDataSnapshot(
        symbol=symbol,
        collected_at=bar.close_time,
        book_ticker=BookTicker(
            symbol=symbol,
            event_time=bar.close_time,
            bid_price=bid,
            bid_qty=qty_unit,
            ask_price=ask,
            ask_qty=qty_unit,
        ),
        depth_snapshot=DepthSnapshot(
            symbol=symbol,
            event_time=bar.close_time,
            bids=bids,
            asks=asks,
        ),
        trades=trades,
        funding=FundingSnapshot(
            symbol=symbol,
            funding_rate=bar.funding_rate,
            mark_price=bar.close,
            event_time=bar.close_time,
            next_funding_time=bar.close_time + timedelta(hours=8),
        ),
    )

    closes = [item.close for item in context[-64:]]
    realized_vol = _safe_std(_returns(closes))
    uncertainty = _clamp(realized_vol * 10.0, 0.02, 0.85)

    flags = ["SYNTHETIC_MARKET_SNAPSHOT"]
    if spread_bps > 8.0:
        flags.append("SPREAD_WIDE")
    if realized_vol > 0.01:
        flags.append("VOLATILITY_SPIKE")

    diagnostics = DataSanityDiagnostics(
        feed_delay_ms=0.0,
        feed_delay_anomaly=False,
        outlier_tick_anomaly=False,
        volume_anomaly=False,
        volume_z_score=None,
        anomaly_flags=flags,
        uncertainty_contrib=uncertainty,
        data_quality_score=_clamp(1.0 - uncertainty, 0.0, 1.0),
    )

    return DataLayerResult(market_snapshot=snapshot, diagnostics=diagnostics)


def build_horizon_candidates(
    context: list[HistoricalBar],
    genome: Genome,
) -> list[HorizonWindowCandidate]:
    if len(context) < 180:
        return []

    closes = [bar.close for bar in context]
    candidates: list[HorizonWindowCandidate] = []

    horizon_specs = [
        ("5m", 12, 30, -genome.horizon_bias * 0.5),
        ("15m", 24, 30, -genome.horizon_bias * 0.25),
        ("1h", 48, 60, genome.horizon_bias * 0.5),
        ("4h", 96, 120, genome.horizon_bias),
    ]

    for horizon, lookback, window_days, bias in horizon_specs:
        if len(closes) <= lookback:
            continue

        start_price = closes[-lookback - 1]
        end_price = closes[-1]
        if start_price <= 0.0:
            continue

        momentum = (end_price - start_price) / start_price
        local_returns = _returns(closes[-lookback - 1 :])
        realized_vol = _safe_std(local_returns)

        gross_edge_bps = 4.0 + (abs(momentum) * 3_500.0) - (realized_vol * 4_200.0) + (bias * 2.5)
        walk_forward_score = _clamp(
            0.45 + (abs(momentum) * 50.0) - (realized_vol * 15.0),
            0.05,
            2.0,
        )
        calibration_coverage = _clamp(
            0.78 - (realized_vol * 8.0) + (abs(momentum) * 1.0),
            0.45,
            0.95,
        )
        brier_ratio = _clamp(
            1.05 + (realized_vol * 14.0) - (abs(momentum) * 5.0),
            0.55,
            2.20,
        )

        candidates.append(
            HorizonWindowCandidate(
                horizon=horizon,
                window_days=window_days,
                sample_size=len(context),
                walk_forward_score=walk_forward_score,
                embargo_passed=True,
                gross_edge_bps=gross_edge_bps,
                fee_bps=1.8,
                slippage_bps=1.0,
                funding_bps=max(0.0, abs(context[-1].funding_rate) * 10_000.0 / 8.0),
                impact_bps=0.8,
                calibration_coverage=calibration_coverage,
                brier_ratio=brier_ratio,
            )
        )

    return candidates


def _ntz_correlation_abnormal(context: list[HistoricalBar]) -> bool:
    if len(context) < 10:
        return False

    corr_30m = abs(
        _corr(
            [bar.close for bar in context[-30:]],
            [bar.volume for bar in context[-30:]],
        )
    )
    corr_5m = abs(_corr([bar.close for bar in context[-5:]], [bar.volume for bar in context[-5:]]))
    corr_60m = abs(
        _corr(
            [bar.close for bar in context[-60:]],
            [bar.volume for bar in context[-60:]],
        )
    )

    corr_delta = corr_5m - corr_60m
    return corr_30m > 0.85 or corr_delta > 0.2


def _ntz_funding_extreme(context: list[HistoricalBar]) -> bool:
    rates = [bar.funding_rate for bar in context[-120:] if abs(bar.funding_rate) > 0.0]
    if len(rates) < 20:
        return False

    mean_rate = _safe_mean(rates)
    std_rate = _safe_std(rates)
    if std_rate <= 1e-9:
        return False

    z = abs((rates[-1] - mean_rate) / std_rate)
    return z > 2.5


def _mode_a_update(genome: Genome, recent_trade_pnls: list[float]) -> Genome:
    if len(recent_trade_pnls) < 20:
        return genome

    recent = recent_trade_pnls[-20:]
    wins = len([pnl for pnl in recent if pnl > 0.0])
    win_rate = wins / len(recent)

    if win_rate >= 0.55:
        next_kelly = _clamp(genome.fractional_kelly * 1.05, 0.01, 0.15)
    elif win_rate <= 0.45:
        next_kelly = _clamp(genome.fractional_kelly * 0.90, 0.01, 0.15)
    else:
        next_kelly = genome.fractional_kelly

    next_bias = _clamp(genome.horizon_bias + ((win_rate - 0.50) * 0.20), -0.8, 0.8)

    return Genome(
        fractional_kelly=next_kelly,
        stop_loss_bps=genome.stop_loss_bps,
        time_stop_seconds=genome.time_stop_seconds,
        horizon_bias=next_bias,
        maker_preferred=genome.maker_preferred,
    )


def _mode_b_evolve(genome: Genome, recent_trade_pnls: list[float]) -> Genome:
    if len(recent_trade_pnls) < 50:
        return genome

    recent = recent_trade_pnls[-50:]
    mean_pnl = _safe_mean(recent)
    vol = max(_safe_std(recent), 1e-6)
    perf = mean_pnl / vol

    conservative = Genome(
        fractional_kelly=_clamp(genome.fractional_kelly * 0.85, 0.01, 0.15),
        stop_loss_bps=min(500, genome.stop_loss_bps + 20),
        time_stop_seconds=max(300, genome.time_stop_seconds - 60),
        horizon_bias=_clamp(genome.horizon_bias * 0.8, -0.8, 0.8),
        maker_preferred=True,
    )

    aggressive = Genome(
        fractional_kelly=_clamp(genome.fractional_kelly * 1.10, 0.01, 0.15),
        stop_loss_bps=max(50, genome.stop_loss_bps - 10),
        time_stop_seconds=min(7_200, genome.time_stop_seconds + 120),
        horizon_bias=_clamp(genome.horizon_bias + 0.05, -0.8, 0.8),
        maker_preferred=genome.maker_preferred,
    )

    if perf < 0.0:
        return conservative
    if perf > 0.25:
        return aggressive
    return genome


def _phase1_criteria(
    runtime_days: int,
    accepted_trades: int,
    sortino_like: float,
    constitution_breach_count: int,
    deny_reason_counts: dict[str, int],
) -> tuple[bool, bool, bool, bool, bool, bool]:
    known_reasons = {item.value for item in ReasonCode}

    c1 = runtime_days >= 30
    c2 = accepted_trades >= 50
    c3 = sortino_like > 0.0
    c4 = constitution_breach_count == 0
    c5 = all(reason in known_reasons for reason in deny_reason_counts)

    return c1, c2, c3, c4, c5, all([c1, c2, c3, c4, c5])


def _risk_adjusted_metrics(trade_pnls: list[float]) -> tuple[float, float]:
    if not trade_pnls:
        return 0.0, 0.0

    mean_pnl = _safe_mean(trade_pnls)
    std_pnl = _safe_std(trade_pnls)
    sharpe_like = 0.0 if std_pnl <= 0.0 else mean_pnl / std_pnl

    downside = [pnl for pnl in trade_pnls if pnl < 0.0]
    downside_std = _safe_std(downside)
    sortino_like = 0.0 if downside_std <= 0.0 else mean_pnl / downside_std

    return sharpe_like, sortino_like


def _decision_direction(result: PaperRunResult) -> int:
    decision = result.decision
    if decision.p_flat >= max(decision.p_up, decision.p_down):
        return 0
    if decision.p_up >= decision.p_down:
        return 1
    return -1


def _realized_trade_return(
    *,
    current_bar: HistoricalBar,
    next_bar: HistoricalBar,
    direction: int,
    decision_edge_bps: float,
    execution_cost_bps: float,
    stop_loss_bps: int,
) -> float:
    if direction == 0:
        return 0.0

    price_change = (next_bar.close - current_bar.close) / max(current_bar.close, 1e-9)
    directional_move = direction * price_change

    expected_edge = (decision_edge_bps - execution_cost_bps) / 10_000.0
    blended = (0.65 * directional_move) + (0.35 * expected_edge)

    stop_loss_fraction = max(stop_loss_bps / 10_000.0, 0.0001)
    take_profit_fraction = stop_loss_fraction * 3.0

    return _clamp(blended, -stop_loss_fraction, take_profit_fraction)


async def run_walkforward_replay(
    bars: list[HistoricalBar],
    constitution: ConstitutionConfig,
    config: WalkforwardConfig,
) -> tuple[WalkforwardSummary, list[WalkforwardStep]]:
    if len(bars) <= config.warmup_bars + 1:
        raise ValueError("Not enough bars for warmup and next-bar PnL evaluation")
    if config.mode_a_update_every_trades <= 0 or config.mode_b_evolve_every_trades <= 0:
        raise ValueError("Mode A/B trade update cadence must be positive")

    ordered = sorted(bars, key=lambda item: item.open_time)

    genome = Genome()
    state_snapshot = StateSnapshot()
    market_client = BinanceUMPublicClient()

    equity = config.initial_capital_usd
    peak_equity = config.initial_capital_usd
    max_drawdown_pct = 0.0

    trade_pnls: list[float] = []
    monitoring_pnls: list[float] = [0.0]

    deny_counts: Counter[str] = Counter()
    constitution_breach_count = 0

    steps: list[WalkforwardStep] = []
    accepted_trades = 0

    current_day: date | None = None
    current_day_pnl = 0.0

    total_steps = 0
    start_ts = ordered[config.warmup_bars].open_time

    for index in range(config.warmup_bars, len(ordered) - 1):
        if config.max_steps is not None and total_steps >= config.max_steps:
            break

        total_steps += 1

        bar = ordered[index]
        next_bar = ordered[index + 1]
        context = ordered[max(0, index - config.context_bars) : index]

        bar_day = bar.open_time.date()
        if current_day is None or bar_day != current_day:
            current_day = bar_day
            current_day_pnl = 0.0

        drawdown_pct = _clamp(
            ((peak_equity - equity) / config.initial_capital_usd) * 100.0,
            0.0,
            100.0,
        )
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

        constitution_breach = drawdown_pct > constitution.max_drawdown_pct
        if constitution_breach:
            constitution_breach_count += 1

        recent_closes = [item.close for item in context[-32:]]
        volatility_spike = _safe_std(_returns(recent_closes)) > 0.01

        state_eval = evaluate_state_transition(
            StateEvaluationInput(
                snapshot=state_snapshot,
                event_time=bar.close_time,
                drawdown_pct=drawdown_pct,
                uncertainty_spike=volatility_spike,
                critical_correlation=False,
                constitution_breach=constitution_breach,
                manual_resume=True,
            ),
            constitution,
        )
        state_snapshot = state_eval.snapshot

        data_layer = build_data_layer_from_bar(config.symbol, bar, context)
        candidates = build_horizon_candidates(context, genome)

        pnl_tail = monitoring_pnls[-200:] if monitoring_pnls else [0.0]
        baseline_mean = _safe_mean(pnl_tail)
        baseline_std = max(_safe_std(pnl_tail), 1e-6)

        uncertainty_score = data_layer.diagnostics.uncertainty_contrib
        uncertainty_threshold = 0.6 if state_snapshot.mode.value == "CAUTION" else 0.7

        request_id = f"wf-{bar.close_time.strftime('%Y%m%d%H%M')}-{total_steps:06d}"

        result = await run_paper_cycle(
            input_data=PaperRunInput(
                request_id=request_id,
                symbol=config.symbol,
                data_layer_override=data_layer,
                decision_candidates=candidates,
                risk=PaperRiskConfig(
                    equity_usd=max(1e-9, equity),
                    state_mode=state_snapshot.mode,
                    uncertainty_score=uncertainty_score,
                    fractional_kelly=genome.fractional_kelly,
                    daily_loss_pct=max(
                        0.0,
                        (-current_day_pnl / config.initial_capital_usd) * 100.0,
                    ),
                    open_positions=0,
                    stop_loss_bps=genome.stop_loss_bps,
                    time_stop_seconds=genome.time_stop_seconds,
                    ntz_uncertainty_high=uncertainty_score > uncertainty_threshold,
                    ntz_correlation_abnormal=_ntz_correlation_abnormal(context),
                    ntz_funding_extreme=_ntz_funding_extreme(context),
                    constitution_breach=constitution_breach,
                ),
                execution=PaperExecutionConfig(
                    mode=state_snapshot.mode,
                    reduce_only=False,
                    maker_preferred=genome.maker_preferred,
                    funding_bps=max(0.0, abs(bar.funding_rate) * 10_000.0 / 8.0),
                ),
                monitoring=PaperMonitoringConfig(
                    recent_trade_pnls=pnl_tail,
                    baseline_pnl_mean=baseline_mean,
                    baseline_pnl_std=baseline_std,
                    ci_coverage=_clamp(0.80 - (uncertainty_score * 0.25), 0.55, 0.95),
                    brier_score=_clamp(0.20 + (uncertainty_score * 0.30), 0.05, 1.20),
                    baseline_brier_score=0.20,
                ),
            ),
            constitution=constitution,
            market_client=market_client,
        )

        accepted = result.execution_result.report.accepted
        execution_reason = result.execution_result.report.reason_codes[0].value
        decision_reason = result.risk_decision.reason_codes[0].value

        trade_pnl = 0.0
        if accepted:
            direction = _decision_direction(result)
            trade_return = _realized_trade_return(
                current_bar=bar,
                next_bar=next_bar,
                direction=direction,
                decision_edge_bps=result.decision.edge_bps_after_cost,
                execution_cost_bps=result.execution_result.total_cost_bps,
                stop_loss_bps=max(1, result.risk_decision.stop_loss_bps),
            )
            trade_pnl = result.risk_decision.size_usd * trade_return
            accepted_trades += 1
            trade_pnls.append(trade_pnl)
        else:
            deny_counts[execution_reason] += 1

        current_day_pnl += trade_pnl
        equity += trade_pnl
        peak_equity = max(peak_equity, equity)

        monitoring_pnls.append(trade_pnl)
        if len(monitoring_pnls) > 200:
            monitoring_pnls = monitoring_pnls[-200:]

        steps.append(
            WalkforwardStep(
                ts=bar.close_time,
                request_id=request_id,
                mode=state_snapshot.mode.value,
                accepted=accepted,
                decision_reason=decision_reason,
                execution_reason=execution_reason,
                selected_horizon=result.decision.selected_horizon,
                trade_pnl=trade_pnl,
                equity_usd=equity,
            )
        )

        if accepted_trades > 0 and accepted_trades % config.mode_a_update_every_trades == 0:
            genome = _mode_a_update(genome, trade_pnls)

        if accepted_trades > 0 and accepted_trades % config.mode_b_evolve_every_trades == 0:
            genome = _mode_b_evolve(genome, trade_pnls)

    runtime_days = 0
    if steps:
        runtime_days = (steps[-1].ts.date() - start_ts.date()).days + 1

    sharpe_like, sortino_like = _risk_adjusted_metrics(trade_pnls)

    (
        phase1_30d_runtime,
        phase1_50_trades,
        phase1_positive_risk_adjusted,
        phase1_zero_breach,
        phase1_deny_explainable,
        phase1_exit,
    ) = _phase1_criteria(
        runtime_days=runtime_days,
        accepted_trades=accepted_trades,
        sortino_like=sortino_like,
        constitution_breach_count=constitution_breach_count,
        deny_reason_counts=dict(deny_counts),
    )

    summary = WalkforwardSummary(
        symbol=config.symbol,
        bars_processed=total_steps,
        runtime_days=runtime_days,
        total_steps=total_steps,
        accepted_trades=accepted_trades,
        denied_steps=total_steps - accepted_trades,
        net_pnl_usd=equity - config.initial_capital_usd,
        final_equity_usd=equity,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_like=sharpe_like,
        sortino_like=sortino_like,
        constitution_breach_count=constitution_breach_count,
        deny_reason_counts=dict(deny_counts),
        phase1_30d_runtime=phase1_30d_runtime,
        phase1_50_trades=phase1_50_trades,
        phase1_positive_risk_adjusted=phase1_positive_risk_adjusted,
        phase1_zero_constitution_breach=phase1_zero_breach,
        phase1_deny_explainable=phase1_deny_explainable,
        phase1_exit_passed=phase1_exit,
    )

    return summary, steps
