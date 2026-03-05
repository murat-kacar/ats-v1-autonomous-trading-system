from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import orjson


class EventLogger:
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event_type: str, payload: dict[str, object]) -> str:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        digest = sha256(orjson.dumps(record)).hexdigest()
        record["payload_hash"] = digest

        with self._file_path.open("ab") as fp:
            fp.write(orjson.dumps(record) + b"\n")
        return digest
