import json
from pathlib import Path

from ats_event_log.logger import EventLogger


def test_event_logger_appends_hash_and_payload(tmp_path: Path) -> None:
    log_path = tmp_path / "events" / "test.ndjson"
    logger = EventLogger(log_path)

    result = logger.append("risk.completed", {"request_id": "r-1", "allow": False})

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    parsed = json.loads(lines[0])
    assert parsed["event_type"] == "risk.completed"
    assert parsed["payload"]["request_id"] == "r-1"
    assert parsed["input_hash"] == result.input_hash
    assert parsed["event_hash"] == result.event_hash
    assert parsed["event_id"] == result.event_id
    assert len(result.input_hash) == 64
    assert len(result.event_hash) == 64
