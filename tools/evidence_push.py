#!/usr/bin/env python3
"""อัปโหลด run ใหม่ขึ้น team evidence bucket (คนดูแล source ใช้ key ชุด read-write)

วิธีใช้:
    python tools/evidence_push.py <source_id> <run_dir> [--run-id 20260818T041500Z]

โฟลเดอร์ run ต้องมี manifest_input.json ที่คนกรอกเอง (fetched_by, as_of, grain ต่อ dataset)
ที่เหลือ (gzip, sha256, row_count, manifest.json) เครื่องมือทำให้ — ดู docs/evidence-storage.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.evidence_store import (  # noqa: E402
    EvidenceStoreError,
    config_from_env,
    make_client,
    push_run,
    remote_run_prefix,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_id", help="source id ตาม registry เช่น spu_sukhothai_care")
    parser.add_argument("run_dir", type=Path, help="โฟลเดอร์ run ที่มี dataset + manifest_input.json")
    parser.add_argument(
        "--run-id",
        default=None,
        help="UTC timestamp เช่น 20260818T041500Z (ไม่ระบุ = ใช้ชื่อโฟลเดอร์ถ้าเข้ารูป หรือเวลาปัจจุบัน)",
    )
    args = parser.parse_args()

    try:
        config = config_from_env()
        client = make_client(config)
        manifest = push_run(client, config, args.source_id, args.run_dir, run_id=args.run_id)
    except EvidenceStoreError as error:
        print(f"push ล้มเหลว: {error}", file=sys.stderr)
        return 2

    prefix = remote_run_prefix(config, args.source_id, manifest["run_id"])
    print(f"push สำเร็จ → s3://{config.bucket}/{prefix}")
    for entry in manifest["datasets"]:
        print(
            f"  {entry['dataset_key']}: {entry['file']} "
            f"rows={entry['row_count']} sha256={entry['sha256'][:12]}…"
        )
    for entry in manifest["extra_files"]:
        print(f"  (extra) {entry['file']} sha256={entry['sha256'][:12]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
