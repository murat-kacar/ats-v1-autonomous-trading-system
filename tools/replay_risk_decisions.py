from __future__ import annotations

import argparse
from pathlib import Path

from ats_risk_rules.replay import replay_from_event_log


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay risk decisions from an ndjson event log")
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("/home/deploy/ats/var/log/events/risk_adjudicator.ndjson"),
        help="Path to risk decision event log",
    )
    args = parser.parse_args()

    if not args.log.exists():
        print(f"Log file not found: {args.log}")
        return 2

    replayed, mismatches = replay_from_event_log(args.log)
    print(f"replayed={replayed} mismatches={len(mismatches)}")

    if mismatches:
        for item in mismatches[:20]:
            print(f"[mismatch] request_id={item.request_id} {item.message}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
