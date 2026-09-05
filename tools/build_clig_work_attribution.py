"""สร้างเครดิตผู้วิจัย CLIG จากหลักฐานที่ตรวจ hash และจับคู่โครงการแล้ว."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.privacy import sanitize_payload

CONTEXTS = {
    "/researcher_name_th": "work_attribution",
    "/researcher_name_en": "work_attribution",
}


def read_dataset(run: Path, source: str, filename: str) -> tuple[list[dict], dict]:
    manifest_bytes = (run / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest["source_id"] != source:
        raise ValueError("source manifest does not match the requested source")
    declarations = [d for d in manifest["datasets"] if d["file"] == filename]
    if len(declarations) != 1:
        raise ValueError("dataset must have exactly one manifest declaration")
    raw = (run / filename).read_bytes()
    declaration = declarations[0]
    if hashlib.sha256(raw).hexdigest() != declaration["sha256"]:
        raise ValueError("dataset hash mismatch")
    rows = [json.loads(line) for line in gzip.decompress(raw).splitlines() if line.strip()]
    if len(rows) != declaration["row_count"]:
        raise ValueError("dataset count mismatch")
    return rows, {"manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                  "data_sha256": declaration["sha256"], "run_id": manifest["run_id"]}


def project_attributions(projects: list[dict], details: list[dict]) -> list[dict]:
    by_project = {row["project_id"]: row for row in projects}
    by_detail = {row["detail_ref"]: row for row in details}
    if len(by_project) != len(projects) or len(by_detail) != len(details) or set(by_project) != set(by_detail):
        raise ValueError("project/detail identities must match completely without duplicates")
    result = []
    for project_id in sorted(by_project):
        detail = by_detail[project_id]
        if detail["source_url"] != by_project[project_id]["detail_url"]:
            raise ValueError("project/detail source URL mismatch")
        fields = detail["fields"]
        result.append(sanitize_payload({
            "project_id": project_id, "project_title": detail["project_name"],
            "researcher_name_th": fields.get("ชื่อ-นามสกุล (ภาษาไทย)") or None,
            "researcher_name_en": fields.get("ชื่อ-นามสกุล (ภาษาอังกฤษ)") or None,
            "researcher_position": fields.get("ตำแหน่ง") or None,
            "lead_organization": fields.get("หน่วยงาน") or None,
            "source_url": detail["source_url"], "source_sha256": detail["raw_html_sha256"],
            "fetched_at": detail["fetched_at"],
        }, field_contexts=CONTEXTS))
    return result


def build(project_run: Path, detail_run: Path, *, generated_at: str, output: Path) -> dict:
    projects, project_evidence = read_dataset(project_run, "clig_projects", "projects.jsonl.gz")
    details, detail_evidence = read_dataset(detail_run, "f4_research_dashboard_psu", "project_detail_records.jsonl.gz")
    items = project_attributions(projects, details)
    payload = {
        "schema_version": "1.0.0", "generated_at": generated_at,
        "source_id": "clig_projects", "source_url": "https://clig.oas.psu.ac.th/project/search_project",
        "publication_status": "public_candidate_projection", "as_of": None,
        "grain_th": "หนึ่งรายการต่อโครงการ CLIG ที่จับคู่ ID และ URL รายละเอียดตรงกัน",
        "note_th": "ใช้รายละเอียดจากหน้าผลงาน ส่วน fetched_at คือเวลาบันทึกหลักฐาน ไม่ใช่วันที่อ้างอิงข้อมูล",
        "evidence": {"project_listing": project_evidence, "project_details": detail_evidence},
        "items": items,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {"records": len(items), "thai_names": sum(bool(r["researcher_name_th"]) for r in items),
            "english_names": sum(bool(r["researcher_name_en"]) for r in items)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_run", type=Path)
    parser.add_argument("detail_run", type=Path)
    parser.add_argument("--generated-at", default=datetime.now(timezone.utc).isoformat())
    parser.add_argument("--output", type=Path, default=ROOT / "data/public/clig_work_attribution.json")
    args = parser.parse_args()
    print(json.dumps(build(args.project_run, args.detail_run, generated_at=args.generated_at, output=args.output)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
