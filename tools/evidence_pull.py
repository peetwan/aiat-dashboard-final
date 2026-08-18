#!/usr/bin/env python3
"""ดึง run จาก team evidence bucket ลง AIAT_EVIDENCE_ROOT พร้อมตรวจ sha256 ทุกไฟล์

วิธีใช้:
    python tools/evidence_pull.py <source_id>                 # run ล่าสุด
    python tools/evidence_pull.py <source_id> --run <run_id>  # run ที่ระบุ
    python tools/evidence_pull.py <source_id> --list          # ดู run ทั้งหมด

hash ไม่ตรง = คำสั่งล้มเหลว (exit 2) ไม่ใช่แค่เตือน — ดู docs/evidence-storage.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.evidence_store import (  # noqa: E402
    EvidenceStoreError,
    config_from_env,
    list_runs,
    make_client,
    pull_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_id", help="source id ตาม registry เช่น spu_sukhothai_care")
    parser.add_argument("--run", default="latest", help="run_id หรือ latest (ค่าเริ่มต้น)")
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="เขียนลง root อื่นแทน AIAT_EVIDENCE_ROOT (ปกติไม่ต้องระบุ)",
    )
    parser.add_argument("--force", action="store_true", help="ดึงทับโฟลเดอร์ local เดิม")
    parser.add_argument("--list", action="store_true", help="แสดง run ทั้งหมดของ source แล้วจบ")
    args = parser.parse_args()

    try:
        config = config_from_env()
        client = make_client(config)
        if args.list:
            runs = list_runs(client, config, args.source_id)
            if not runs:
                print(f"ยังไม่มี run ของ {args.source_id}")
            for run_id in runs:
                print(run_id)
            return 0
        dest = pull_run(
            client,
            config,
            args.source_id,
            run=args.run,
            dest_root=args.dest,
            force=args.force,
        )
    except EvidenceStoreError as error:
        print(f"pull ล้มเหลว: {error}", file=sys.stderr)
        return 2

    print(f"pull สำเร็จ (ตรวจ sha256 ครบ) → {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
