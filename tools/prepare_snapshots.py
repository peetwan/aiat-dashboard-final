#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DASHBOARD_ROOT.parent


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy approved local snapshots into the standalone app")
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--max-file-mb", type=float, default=50)
    parser.add_argument("--include-large", action="store_true")
    parser.add_argument("--include-owner-pending", action="store_true")
    args = parser.parse_args()

    catalog = json.loads((DASHBOARD_ROOT / "config/source_catalog.json").read_text(encoding="utf-8"))
    selected = set(args.source)
    report = {"copied": [], "skipped": []}
    for source in catalog["sources"]:
        source_id = source["source_id"]
        if selected and source_id not in selected:
            continue
        if not selected and source["acquisition_mode"] != "snapshot_only":
            report["skipped"].append({"source_id": source_id, "reason": "api_first_not_needed_by_default"})
            continue
        if source["cloud_policy"] == "restricted_local_only":
            report["skipped"].append({"source_id": source_id, "reason": "restricted_local_only"})
            continue
        if source["cloud_policy"] == "owner_terms_pending" and not args.include_owner_pending:
            report["skipped"].append({"source_id": source_id, "reason": "owner_terms_pending"})
            continue
        target_root = DASHBOARD_ROOT / "data/snapshots" / source_id
        artifacts = []
        for relative in source["snapshot_origin_files"]:
            origin = PROJECT_ROOT / relative
            size_mb = origin.stat().st_size / (1024 * 1024)
            if size_mb > args.max_file_mb and not args.include_large:
                report["skipped"].append(
                    {"source_id": source_id, "path": relative, "reason": f"file_too_large_{size_mb:.1f}MB"}
                )
                continue
            target_root.mkdir(parents=True, exist_ok=True)
            target = target_root / origin.name
            shutil.copy2(origin, target)
            artifacts.append(
                {
                    "path": target.relative_to(DASHBOARD_ROOT).as_posix(),
                    "sha256": sha256_file(target),
                    "bytes": target.stat().st_size,
                    "origin": relative,
                }
            )
        if artifacts:
            manifest = {
                "manifest_version": "0.1.0",
                "source_id": source_id,
                "purpose": "local snapshot replay; do not commit",
                "artifacts": artifacts,
            }
            (target_root / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            report["copied"].append({"source_id": source_id, "files": len(artifacts)})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
