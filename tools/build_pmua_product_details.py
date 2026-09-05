"""สร้าง public projection ของ PMUA จาก snapshot ที่ตรวจ hash และจำนวนครบแล้ว."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app.privacy import sanitize_payload
from tools.build_clig_work_attribution import read_dataset

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "f4_pmua_product_details"
FIELDS = (
    "product_id", "source_url", "title", "trl_level", "trl_status", "latitude", "longitude",
    "empirical_evidence", "outcomes", "impacts", "evidence_status", "fetched_at", "raw_html_sha256",
)


def project_details(rows: list[dict], *, expected_count: int) -> list[dict]:
    if not rows or len(rows) != expected_count:
        raise ValueError("PMUA detail count does not match the reviewed snapshot")
    result = []
    seen = set()
    for row in rows:
        product_id = row.get("product_id")
        if type(product_id) is not int or product_id <= 0 or product_id in seen:
            raise ValueError("PMUA product identity is invalid or duplicated")
        seen.add(product_id)
        if row.get("source_url") != f"https://pmua-apptech.com/product/show/{product_id}":
            raise ValueError("PMUA detail URL does not match product identity")
        if row.get("http_status") != 200 or row.get("fetch_error"):
            raise ValueError("PMUA snapshot contains a failed detail fetch")
        if any(field not in row for field in FIELDS) or not row["title"]:
            raise ValueError("PMUA detail schema is incomplete")
        if not re.fullmatch(r"[a-f0-9]{64}", row["raw_html_sha256"]):
            raise ValueError("PMUA detail lacks its source hash")
        if row["evidence_status"] not in {"complete", "partial", "not_reported"}:
            raise ValueError("PMUA evidence status is invalid")
        for field in ("empirical_evidence", "outcomes", "impacts"):
            if not isinstance(row[field], list) or any(not isinstance(item, dict) for item in row[field]):
                raise ValueError("PMUA evidence must contain structured records")
        projection = {field: row[field] for field in FIELDS}
        projection["as_of"] = None
        if sanitize_payload(projection) != projection:
            raise ValueError("PMUA detail requires a scoped privacy review")
        result.append(projection)
    return sorted(result, key=lambda row: row["product_id"])


def build(run: Path, output: Path, *, expected_count: int = 1160) -> dict:
    rows, evidence = read_dataset(run, SOURCE_ID, "product_details.jsonl.gz")
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    payload = {
        "schema_version": "1.0.0", "source_id": SOURCE_ID,
        "generated_at": manifest["fetched_at"], "as_of": None,
        "publication_status": "public_candidate_projection",
        "note_th": "ค่าตัวชี้วัดคงตามข้อความต้นทาง; fetched_at คือเวลาบันทึกหลักฐาน ไม่ใช่วันที่อ้างอิงข้อมูล",
        "evidence": evidence, "items": project_details(rows, expected_count=expected_count),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data/public/pmua_product_details.json")
    args = parser.parse_args()
    print(json.dumps({"records": len(build(args.run, args.output)["items"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
