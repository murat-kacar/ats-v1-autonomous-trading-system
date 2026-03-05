from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import orjson


@dataclass(frozen=True)
class AppendResult:
    event_id: str
    ts: str
    input_hash: str
    event_hash: str


def _canonical_json_bytes(value: object) -> bytes:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)


def _sha256_hex(value: object) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()


class EventLogger:
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event_type: str, payload: dict[str, object]) -> AppendResult:
        ts = datetime.now(UTC).isoformat()
        event_id = uuid4().hex
        input_hash = _sha256_hex(payload)

        record = {
            "event_id": event_id,
            "ts": ts,
            "event_type": event_type,
            "input_hash": input_hash,
            "payload": payload,
        }

        event_hash = _sha256_hex(record)
        record["event_hash"] = event_hash

        with self._file_path.open("ab") as fp:
            fp.write(orjson.dumps(record) + b"\n")

        return AppendResult(
            event_id=event_id,
            ts=ts,
            input_hash=input_hash,
            event_hash=event_hash,
        )
