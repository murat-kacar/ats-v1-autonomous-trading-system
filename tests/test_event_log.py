import json
from pathlib import Path

from ats_event_log.logger import EventLogger


def test_event_logger_appends_hash_and_payload(tmp_path: Path) -> None:
    log_path = tmp_path / "events" / "test.ndjson"
    logger = EventLogger(log_path)

    digest = logger.append("risk.completed", {"request_id": "r-1", "allow": False})

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    parsed = json.loads(lines[0])
    assert parsed["event_type"] == "risk.completed"
    assert parsed["payload"]["request_id"] == "r-1"
    assert parsed["payload_hash"] == digest
    assert len(digest) == 64
