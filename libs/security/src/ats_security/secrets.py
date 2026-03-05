from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


class MissingSecretsError(RuntimeError):
    pass


@dataclass(frozen=True)
class SecretFetchResult:
    values: dict[str, str]
    missing: list[str]


class SecretManager:
    def __init__(
        self,
        required_keys: list[str],
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._required_keys = list(dict.fromkeys(required_keys))
        self._env = env if env is not None else os.environ

    @property
    def required_keys(self) -> list[str]:
        return self._required_keys.copy()

    def fetch_required(self) -> SecretFetchResult:
        values: dict[str, str] = {}
        missing: list[str] = []

        for key in self._required_keys:
            value = self._env.get(key, "")
            if value:
                values[key] = value
            else:
                missing.append(key)

        return SecretFetchResult(values=values, missing=missing)

    def require_all(self) -> dict[str, str]:
        result = self.fetch_required()
        if result.missing:
            missing = ", ".join(result.missing)
            raise MissingSecretsError(f"Missing required secrets: {missing}")
        return result.values

    def masked_snapshot(self) -> dict[str, str]:
        result = self.fetch_required()
        output: dict[str, str] = {}
        for key in self._required_keys:
            if key in result.values:
                output[key] = redact_secret(result.values[key])
            else:
                output[key] = "MISSING"
        return output


def redact_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
