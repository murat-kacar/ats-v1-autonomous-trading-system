from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .secrets import MissingSecretsError, SecretManager


class StaleDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class StaleDataStatus:
    stale: bool
    reason: str
    last_event_ts: str | None
    age_seconds: float | None


@dataclass(frozen=True)
class StartupHealthReport:
    constitution_path: str
    event_log_dir: str
    heartbeat_path: str
    required_secret_keys: list[str]
    secrets_ok: bool
    stale_data_status: StaleDataStatus


class StartupHealthChecker:
    def __init__(
        self,
        constitution_path: Path,
        event_log_dir: Path,
        heartbeat_path: Path,
        max_stale_seconds: int,
        secret_manager: SecretManager,
    ) -> None:
        self._constitution_path = constitution_path
        self._event_log_dir = event_log_dir
        self._heartbeat_path = heartbeat_path
        self._max_stale_seconds = max_stale_seconds
        self._secret_manager = secret_manager

    def run(self, enforce_stale: bool) -> StartupHealthReport:
        if not self._constitution_path.exists():
            raise RuntimeError(f"Constitution file missing: {self._constitution_path}")

        self._event_log_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(self._event_log_dir, os.W_OK):
            raise RuntimeError(f"Event log dir is not writable: {self._event_log_dir}")

        try:
            self._secret_manager.require_all()
            secrets_ok = True
        except MissingSecretsError as exc:
            raise RuntimeError(str(exc)) from exc

        stale_data_status = self.check_stale_data()
        if enforce_stale and stale_data_status.stale:
            raise RuntimeError(
                f"Stale-data kill on startup: {stale_data_status.reason}"
            )

        return StartupHealthReport(
            constitution_path=str(self._constitution_path),
            event_log_dir=str(self._event_log_dir),
            heartbeat_path=str(self._heartbeat_path),
            required_secret_keys=self._secret_manager.required_keys,
            secrets_ok=secrets_ok,
            stale_data_status=stale_data_status,
        )

    def check_stale_data(self, now: datetime | None = None) -> StaleDataStatus:
        current = now if now is not None else datetime.now(UTC)

        if not self._heartbeat_path.exists():
            return StaleDataStatus(
                stale=True,
                reason="HEARTBEAT_FILE_MISSING",
                last_event_ts=None,
                age_seconds=None,
            )

        raw = self._heartbeat_path.read_text(encoding="utf-8").strip()
        if not raw:
            return StaleDataStatus(
                stale=True,
                reason="HEARTBEAT_FILE_EMPTY",
                last_event_ts=None,
                age_seconds=None,
            )

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return StaleDataStatus(
                stale=True,
                reason="HEARTBEAT_JSON_INVALID",
                last_event_ts=None,
                age_seconds=None,
            )

        ts_raw = str(payload.get("last_event_ts", "")).strip()
        if not ts_raw:
            return StaleDataStatus(
                stale=True,
                reason="LAST_EVENT_TS_MISSING",
                last_event_ts=None,
                age_seconds=None,
            )

        try:
            parsed = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            return StaleDataStatus(
                stale=True,
                reason="LAST_EVENT_TS_INVALID",
                last_event_ts=ts_raw,
                age_seconds=None,
            )

        age = (current - parsed.astimezone(UTC)).total_seconds()
        if age > self._max_stale_seconds:
            return StaleDataStatus(
                stale=True,
                reason="STALE_DATA_THRESHOLD_EXCEEDED",
                last_event_ts=parsed.astimezone(UTC).isoformat(),
                age_seconds=age,
            )

        return StaleDataStatus(
            stale=False,
            reason="OK",
            last_event_ts=parsed.astimezone(UTC).isoformat(),
            age_seconds=age,
        )

    def assert_live_data(self, now: datetime | None = None) -> StaleDataStatus:
        status = self.check_stale_data(now=now)
        if status.stale:
            raise StaleDataError(status.reason)
        return status
