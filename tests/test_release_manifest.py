from pathlib import Path

from ats_event_log.release_manifest import build_release_manifest, hash_directory


def test_hash_directory_returns_none_for_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert hash_directory(missing) is None


def test_build_release_manifest_contains_required_hashes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "a.txt").write_text("alpha", encoding="utf-8")
    (repo_root / "b.txt").write_text("beta", encoding="utf-8")

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "constitution.json").write_text('{"x":1}', encoding="utf-8")

    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"model")

    dataset_dir = tmp_path / "datasets"
    dataset_dir.mkdir()
    (dataset_dir / "data.parquet").write_bytes(b"dataset")

    # Initialize minimal git repo for code hash path.
    import subprocess

    subprocess.check_call(["git", "-C", str(repo_root), "init", "-b", "main"])
    subprocess.check_call(["git", "-C", str(repo_root), "config", "user.name", "test"])
    subprocess.check_call(["git", "-C", str(repo_root), "config", "user.email", "test@example.com"])
    subprocess.check_call(["git", "-C", str(repo_root), "add", "."])
    subprocess.check_call(["git", "-C", str(repo_root), "commit", "-m", "init"])

    manifest = build_release_manifest(
        repo_root=repo_root,
        model_dir=model_dir,
        config_dir=config_dir,
        dataset_dir=dataset_dir,
    )

    assert manifest["code_hash"] is not None
    assert manifest["model_hash"] is not None
    assert manifest["config_hash"] is not None
    assert manifest["dataset_hash"] is not None
    assert len(str(manifest["manifest_hash"])) == 64
