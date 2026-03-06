from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from itertools import pairwise

from ats_contracts.models import DataLayerResult, EvidencePacket, MarketDataSnapshot

_FORBIDDEN_ADVISORY_TERMS = {
    "action",
    "allow",
    "deny",
    "order",
    "execution",
    "position",
    "leverage",
    "buy",
    "sell",
    "forecast",
    "prediction",
    "p_up",
    "p_down",
    "p_flat",
}

_DEFAULT_EXPERT_TIMEOUT_SECONDS = 0.02


@dataclass(frozen=True)
class ExpertSignal:
    name: str
    direction_score: float
    confidence: float
    features: dict[str, float]
    risk_flags: list[str]
    reliability: float


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _neutral_signal(name: str, reason: str) -> ExpertSignal:
    return ExpertSignal(
        name=name,
        direction_score=0.0,
        confidence=0.0,
        features={"neutral_fallback": 1.0},
        risk_flags=[f"{name.upper()}_{reason}_FALLBACK"],
        reliability=0.15,
    )


def run_expert_with_fallback(
    name: str,
    fn: Callable[[MarketDataSnapshot], ExpertSignal],
    snapshot: MarketDataSnapshot,
    timeout_seconds: float = _DEFAULT_EXPERT_TIMEOUT_SECONDS,
) -> ExpertSignal:
    if timeout_seconds <= 0.0:
        timeout_seconds = _DEFAULT_EXPERT_TIMEOUT_SECONDS

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn, snapshot)
        try:
            signal = future.result(timeout=timeout_seconds)
        except TimeoutError:
            return _neutral_signal(name, "TIMEOUT")
        except Exception:
            return _neutral_signal(name, "ERROR")

    if signal.name != name:
        return _neutral_signal(name, "NAME_MISMATCH")
    return signal


def _pct_change(start: float, end: float) -> float:
    if start <= 0.0:
        return 0.0
    return (end - start) / start


def _returns(prices: list[float]) -> list[float]:
    if len(prices) < 2:
        return []

    series: list[float] = []
    for prev, current in pairwise(prices):
        if prev <= 0.0:
            continue
        series.append((current - prev) / prev)
    return series


def _pearson_corr(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0

    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)

    centered = [(x - mean_x, y - mean_y) for x, y in zip(xs, ys, strict=True)]
    cov = sum(dx * dy for dx, dy in centered)
    var_x = sum(dx * dx for dx, _ in centered)
    var_y = sum(dy * dy for _, dy in centered)

    if var_x <= 0.0 or var_y <= 0.0:
        return 0.0

    return _clamp(cov / math.sqrt(var_x * var_y), -1.0, 1.0)


def _trend_signal(snapshot: MarketDataSnapshot) -> ExpertSignal:
    prices = [trade.price for trade in snapshot.trades]
    momentum = _pct_change(prices[0], prices[-1]) if prices else 0.0

    direction = _clamp(momentum * 40.0, -1.0, 1.0)
    confidence = _clamp(abs(momentum) * 80.0, 0.0, 1.0)

    risk_flags: list[str] = []
    if abs(momentum) < 0.0008:
        risk_flags.append("TREND_WEAK")

    reliability = 0.72 if len(prices) >= 60 else 0.60

    return ExpertSignal(
        name="trend",
        direction_score=direction,
        confidence=confidence,
        features={
            "momentum": momentum,
            "start_price": prices[0] if prices else 0.0,
            "last_price": prices[-1] if prices else 0.0,
        },
        risk_flags=risk_flags,
        reliability=reliability,
    )


def _mean_reversion_signal(snapshot: MarketDataSnapshot) -> ExpertSignal:
    prices = [trade.price for trade in snapshot.trades]
    if not prices:
        return ExpertSignal(
            name="mean_reversion",
            direction_score=0.0,
            confidence=0.0,
            features={"deviation": 0.0, "mean_price": 0.0},
            risk_flags=["MEAN_REV_DATA_THIN"],
            reliability=0.35,
        )

    mean_price = statistics.fmean(prices)
    deviation = _pct_change(mean_price, prices[-1])

    direction = _clamp(-deviation * 35.0, -1.0, 1.0)
    confidence = _clamp(abs(deviation) * 90.0, 0.0, 1.0)

    risk_flags: list[str] = []
    if abs(deviation) > 0.008:
        risk_flags.append("MEAN_REV_STRETCHED")

    return ExpertSignal(
        name="mean_reversion",
        direction_score=direction,
        confidence=confidence,
        features={
            "deviation": deviation,
            "mean_price": mean_price,
        },
        risk_flags=risk_flags,
        reliability=0.68,
    )


def _volatility_signal(snapshot: MarketDataSnapshot) -> ExpertSignal:
    prices = [trade.price for trade in snapshot.trades]
    returns = _returns(prices)

    realized_vol = statistics.pstdev(returns) if len(returns) >= 2 else 0.0
    last_return = returns[-1] if returns else 0.0

    direction = _clamp(last_return * 55.0, -1.0, 1.0)
    confidence = _clamp(realized_vol * 450.0, 0.0, 1.0)

    risk_flags: list[str] = []
    if realized_vol > 0.0025:
        risk_flags.append("VOLATILITY_SPIKE")

    return ExpertSignal(
        name="volatility",
        direction_score=direction,
        confidence=confidence,
        features={
            "realized_vol": realized_vol,
            "last_return": last_return,
        },
        risk_flags=risk_flags,
        reliability=0.66,
    )


def _microstructure_signal(snapshot: MarketDataSnapshot) -> ExpertSignal:
    bids = snapshot.depth_snapshot.bids[:5]
    asks = snapshot.depth_snapshot.asks[:5]

    bid_depth = sum(level.qty for level in bids)
    ask_depth = sum(level.qty for level in asks)
    total_depth = bid_depth + ask_depth

    imbalance = 0.0
    if total_depth > 0.0:
        imbalance = (bid_depth - ask_depth) / total_depth

    bid = snapshot.book_ticker.bid_price
    ask = snapshot.book_ticker.ask_price
    mid = (bid + ask) / 2.0
    spread_bps = 0.0 if mid <= 0.0 else ((ask - bid) / mid) * 10_000.0

    direction = _clamp(imbalance * 2.5, -1.0, 1.0)
    confidence = _clamp(abs(imbalance) * 2.0, 0.0, 1.0)

    risk_flags: list[str] = []
    if spread_bps > 8.0:
        risk_flags.append("SPREAD_WIDE")
    if total_depth < 3.0:
        risk_flags.append("DEPTH_THIN")

    return ExpertSignal(
        name="microstructure",
        direction_score=direction,
        confidence=confidence,
        features={
            "depth_imbalance": imbalance,
            "spread_bps": spread_bps,
            "depth_total": total_depth,
        },
        risk_flags=risk_flags,
        reliability=0.74,
    )


def _funding_basis_signal(snapshot: MarketDataSnapshot) -> ExpertSignal:
    if snapshot.funding is None:
        return ExpertSignal(
            name="funding_basis",
            direction_score=0.0,
            confidence=0.0,
            features={"funding_rate": 0.0},
            risk_flags=["FUNDING_DATA_MISSING"],
            reliability=0.30,
        )

    funding_rate = snapshot.funding.funding_rate

    direction = _clamp(-funding_rate * 2000.0, -1.0, 1.0)
    confidence = _clamp(abs(funding_rate) * 2800.0, 0.0, 1.0)

    risk_flags: list[str] = []
    if abs(funding_rate) > 0.0008:
        risk_flags.append("FUNDING_EXTREME")

    return ExpertSignal(
        name="funding_basis",
        direction_score=direction,
        confidence=confidence,
        features={
            "funding_rate": funding_rate,
            "mark_price": snapshot.funding.mark_price,
        },
        risk_flags=risk_flags,
        reliability=0.67,
    )


def _macro_correlation_signal(snapshot: MarketDataSnapshot) -> ExpertSignal:
    prices = [trade.price for trade in snapshot.trades]
    qtys = [trade.qty for trade in snapshot.trades]

    corr = _pearson_corr(prices, qtys)

    direction = _clamp(corr, -1.0, 1.0)
    confidence = _clamp(abs(corr) * 0.6, 0.0, 1.0)

    return ExpertSignal(
        name="macro_correlation",
        direction_score=direction,
        confidence=confidence,
        features={"price_volume_corr": corr},
        risk_flags=["MACRO_PROXY_ONLY"],
        reliability=0.38,
    )


def assert_advisory_only(features: dict[str, float], risk_flags: list[str]) -> None:
    lowered_feature_keys = [key.lower() for key in features]
    lowered_flags = [flag.lower() for flag in risk_flags]

    for token in _FORBIDDEN_ADVISORY_TERMS:
        if any(token in key for key in lowered_feature_keys):
            raise ValueError(f"Advisory payload contains forbidden feature token: {token}")
        if any(token in flag for flag in lowered_flags):
            raise ValueError(f"Advisory payload contains forbidden risk token: {token}")


def compile_evidence_packet(request_id: str, data_layer: DataLayerResult) -> EvidencePacket:
    expert_specs: list[tuple[str, Callable[[MarketDataSnapshot], ExpertSignal]]] = [
        ("trend", _trend_signal),
        ("mean_reversion", _mean_reversion_signal),
        ("volatility", _volatility_signal),
        ("microstructure", _microstructure_signal),
        ("funding_basis", _funding_basis_signal),
        ("macro_correlation", _macro_correlation_signal),
    ]

    signals = [
        run_expert_with_fallback(name, fn, data_layer.market_snapshot)
        for name, fn in expert_specs
    ]

    feature_values: dict[str, float] = {}
    risk_flags = set(data_layer.diagnostics.anomaly_flags)
    source_reliability: dict[str, float] = {}
    direction_scores: list[float] = []

    for signal in signals:
        enriched_features = {
            f"{signal.name}_{key}": value for key, value in signal.features.items()
        }
        enriched_features[f"{signal.name}_direction"] = signal.direction_score
        enriched_features[f"{signal.name}_confidence"] = signal.confidence

        assert_advisory_only(enriched_features, signal.risk_flags)

        feature_values.update(enriched_features)
        risk_flags.update(signal.risk_flags)
        quality_multiplier = 0.65 + (0.35 * data_layer.diagnostics.data_quality_score)
        source_reliability[signal.name] = _clamp(signal.reliability * quality_multiplier, 0.0, 1.0)
        direction_scores.append(signal.direction_score)

    disagreement = statistics.pstdev(direction_scores) if len(direction_scores) >= 2 else 0.0
    disagreement_penalty = _clamp(disagreement * 0.35, 0.0, 0.35)

    avg_reliability = statistics.fmean(source_reliability.values())
    reliability_penalty = _clamp((0.60 - avg_reliability) * 0.20, 0.0, 0.15)

    uncertainty_score = _clamp(
        data_layer.diagnostics.uncertainty_contrib + disagreement_penalty + reliability_penalty,
        0.0,
        1.0,
    )

    return EvidencePacket(
        request_id=request_id,
        uncertainty_score=uncertainty_score,
        data_quality_score=data_layer.diagnostics.data_quality_score,
        feature_values=feature_values,
        risk_flags=sorted(risk_flags),
        source_reliability=source_reliability,
    )
