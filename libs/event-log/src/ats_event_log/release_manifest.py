from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_hash(base_dir: Path, files: list[Path]) -> str:
    normalized: list[tuple[str, str]] = []
    for file_path in files:
        rel = file_path.resolve().relative_to(base_dir.resolve()).as_posix()
        normalized.append((rel, _file_sha256(file_path)))

    normalized.sort(key=lambda x: x[0])
    payload = "".join(f"{rel}\0{digest}\n" for rel, digest in normalized).encode("utf-8")
    return sha256(payload).hexdigest()


def _files_in_dir(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*") if p.is_file())


def hash_directory(directory: Path) -> str | None:
    if not directory.exists():
        return None
    files = _files_in_dir(directory)
    if not files:
        return None
    return _bundle_hash(directory, files)


def _git_tracked_files(repo_root: Path) -> list[Path]:
    output = subprocess.check_output(
        ["git", "-C", str(repo_root), "ls-files"],
        text=True,
    )
    files = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        path = repo_root / line
        if path.is_file():
            files.append(path)
    return files


def hash_code(repo_root: Path) -> str:
    files = _git_tracked_files(repo_root)
    if not files:
        raise RuntimeError("No git-tracked files found for code hash")
    return _bundle_hash(repo_root, files)


def build_release_manifest(
    repo_root: Path,
    model_dir: Path,
    config_dir: Path,
    dataset_dir: Path,
) -> dict[str, object]:
    generated_at = datetime.now(UTC).isoformat()
    code_hash = hash_code(repo_root)
    model_hash = hash_directory(model_dir)
    config_hash = hash_directory(config_dir)
    dataset_hash = hash_directory(dataset_dir)

    manifest: dict[str, object] = {
        "version": "v1",
        "generated_at": generated_at,
        "repo_root": str(repo_root),
        "code_hash": code_hash,
        "model_hash": model_hash,
        "config_hash": config_hash,
        "dataset_hash": dataset_hash,
    }

    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest["manifest_hash"] = sha256(canonical).hexdigest()
    return manifest


def write_release_manifest(manifest: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
