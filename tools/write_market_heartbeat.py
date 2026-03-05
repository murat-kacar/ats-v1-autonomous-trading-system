from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Write market data heartbeat timestamp")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/home/deploy/ats/var/run/market_data_heartbeat.json"),
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"last_event_ts": datetime.now(UTC).isoformat()}
    args.output.write_text(json.dumps(payload), encoding="utf-8")
    print(f"heartbeat_written={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
