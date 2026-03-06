from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ats_orchestrator.walkforward import (
    WalkforwardConfig,
    attach_funding_rates,
    fetch_binance_funding_rates,
    fetch_binance_klines,
    run_walkforward_replay,
)
from ats_risk_rules.constitution import load_constitution


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


async def _run(args: argparse.Namespace) -> int:
    end = datetime.now(UTC)
    start = end - timedelta(days=int(args.years) * 365)

    bars = await fetch_binance_klines(
        symbol=args.symbol,
        interval=args.interval,
        start=start,
        end=end,
    )
    if not bars:
        print("No bars fetched from Binance UM Futures.")
        return 2

    funding = await fetch_binance_funding_rates(
        symbol=args.symbol,
        start=start,
        end=end,
    )
    bars_with_funding = attach_funding_rates(bars, funding)

    constitution = load_constitution()
    config = WalkforwardConfig(
        symbol=args.symbol,
        interval=args.interval,
        initial_capital_usd=args.initial_capital_usd,
        warmup_bars=args.warmup_bars,
        max_steps=args.max_steps,
    )

    summary, steps = await run_walkforward_replay(
        bars=bars_with_funding,
        constitution=constitution,
        config=config,
    )

    print("=== Walkforward (5Y) Summary ===")
    print(f"symbol={summary.symbol}")
    print(f"runtime_days={summary.runtime_days}")
    print(
        f"steps={summary.total_steps} "
        f"accepted={summary.accepted_trades} denied={summary.denied_steps}"
    )
    print(f"net_pnl_usd={summary.net_pnl_usd:.4f} final_equity_usd={summary.final_equity_usd:.4f}")
    print(
        "phase1="
        f"30d:{summary.phase1_30d_runtime} "
        f"50trades:{summary.phase1_50_trades} "
        f"risk_adjusted:{summary.phase1_positive_risk_adjusted} "
        f"zero_breach:{summary.phase1_zero_constitution_breach} "
        f"deny_explainable:{summary.phase1_deny_explainable} "
        f"exit_passed:{summary.phase1_exit_passed}"
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, object] = {
        "generated_at": datetime.now(UTC),
        "start": start,
        "end": end,
        "config": asdict(config),
        "summary": asdict(summary),
    }
    if args.include_steps:
        payload["steps"] = [asdict(item) for item in steps]

    payload_json = json.dumps(payload, indent=2, default=_json_default)
    await asyncio.to_thread(output_path.write_text, payload_json, encoding="utf-8")
    print(f"written={output_path}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run 5-year walkforward replay with online Mode A/B updates.",
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="UM futures symbol")
    parser.add_argument(
        "--interval",
        default="1h",
        help="Binance kline interval (e.g. 1h)",
    )
    parser.add_argument("--years", type=int, default=5, help="Historical lookback years")
    parser.add_argument("--initial-capital-usd", type=float, default=1_000.0)
    parser.add_argument("--warmup-bars", type=int, default=240)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/home/deploy/ats/artifacts/reports/walkforward_5y_summary.json"),
    )
    parser.add_argument(
        "--include-steps",
        action="store_true",
        help="Include step-level records in output JSON (large file)",
    )

    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
