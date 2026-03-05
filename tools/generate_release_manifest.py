from __future__ import annotations

import argparse
from pathlib import Path

from ats_event_log.release_manifest import build_release_manifest, write_release_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ATS release manifest hash bundle")
    parser.add_argument("--repo-root", type=Path, default=Path("/home/deploy/ats"))
    parser.add_argument("--model-dir", type=Path, default=Path("/home/deploy/ats/artifacts/models"))
    parser.add_argument("--config-dir", type=Path, default=Path("/home/deploy/ats/infra/config"))
    parser.add_argument("--dataset-dir", type=Path, default=Path("/home/deploy/ats/data/datasets"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/home/deploy/ats/artifacts/releases/release-manifest.v1.json"),
    )
    args = parser.parse_args()

    manifest = build_release_manifest(
        repo_root=args.repo_root,
        model_dir=args.model_dir,
        config_dir=args.config_dir,
        dataset_dir=args.dataset_dir,
    )
    write_release_manifest(manifest, args.output)

    print(f"manifest_written={args.output}")
    print(f"manifest_hash={manifest['manifest_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
