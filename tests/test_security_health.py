import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ats_security.health import StartupHealthChecker, StaleDataError
from ats_security.secrets import SecretManager


def _mk_checker(tmp_path: Path, heartbeat_content: dict[str, object] | None) -> StartupHealthChecker:
    constitution_path = tmp_path / "constitution.json"
    constitution_path.write_text('{"ok": true}', encoding="utf-8")

    event_dir = tmp_path / "events"
    heartbeat_path = tmp_path / "heartbeat.json"

    if heartbeat_content is not None:
        heartbeat_path.write_text(json.dumps(heartbeat_content), encoding="utf-8")

    return StartupHealthChecker(
        constitution_path=constitution_path,
        event_log_dir=event_dir,
        heartbeat_path=heartbeat_path,
        max_stale_seconds=120,
        secret_manager=SecretManager(required_keys=["X"], env={"X": "ok"}),
    )


def test_startup_health_passes_with_fresh_heartbeat(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    checker = _mk_checker(
        tmp_path,
        {
            "last_event_ts": (now - timedelta(seconds=30)).isoformat(),
        },
    )

    report = checker.run(enforce_stale=True)
    assert report.secrets_ok is True
    assert report.stale_data_status.stale is False


def test_stale_data_detected_and_runtime_kill(tmp_path: Path) -> None:
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    checker = _mk_checker(
        tmp_path,
        {
            "last_event_ts": (now - timedelta(seconds=999)).isoformat(),
        },
    )

    status = checker.check_stale_data(now=now)
    assert status.stale is True
    assert status.reason == "STALE_DATA_THRESHOLD_EXCEEDED"

    try:
        checker.assert_live_data(now=now)
    except StaleDataError as exc:
        assert "STALE_DATA_THRESHOLD_EXCEEDED" in str(exc)
    else:
        raise AssertionError("StaleDataError expected")


def test_startup_health_fails_when_stale_enforced(tmp_path: Path) -> None:
    checker = _mk_checker(tmp_path, None)

    try:
        checker.run(enforce_stale=True)
    except RuntimeError as exc:
        assert "Stale-data kill on startup" in str(exc)
    else:
        raise AssertionError("RuntimeError expected")
