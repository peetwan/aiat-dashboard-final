"""ลอง privacy projection กับไฟล์ในเครื่อง โดยไม่เขียน database หรือเผยแพร่ข้อมูล."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.connector_contracts import load_runtime_connector_contract, prepare_contract_records
from app.privacy import sanitize_payload
from app.publication import _privacy_problems, load_contracts


def read_payload(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        if ".jsonl" in path.suffixes:
            return [json.loads(line) for line in handle if line.strip()]
        if ".csv" in path.suffixes:
            return list(csv.DictReader(handle))
        return json.load(handle)


def preview_connector(payload, source_id: str, dataset_key: str) -> dict:
    contract = load_runtime_connector_contract(source_id)
    if contract is None:
        raise ValueError("ไม่พบ connector contract ของ source นี้")
    grains = [g for g in contract["dataset_grains"] if re.fullmatch(g["key_pattern"], dataset_key)]
    if len(grains) != 1:
        raise ValueError("dataset-key ต้องตรงกับ grain เดียวใน contract")
    contexts = grains[0].get("field_contexts", {})
    # Connector fixture envelopes and ordinary JSON/JSONL records both work.
    if isinstance(payload, dict) and payload.get("fixture_version") == "1.0":
        rows = [r["payload"] for r in payload["records"] if r["dataset_key"] == dataset_key]
    else:
        rows = payload if isinstance(payload, list) else [payload]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("input ต้องมี record objects อย่างน้อยหนึ่งรายการ")
    changes: list[tuple[str, str]] = []
    for row in rows:
        sanitize_payload(row, field_contexts=contexts, changes=changes)
    prepared = prepare_contract_records(contract, [(dataset_key, row) for row in rows])
    counts = Counter(changes)
    return {
        "status": "candidate_valid", "source_id": source_id, "dataset_key": dataset_key,
        "records": len(prepared), "field_contexts": contexts,
        "changes": [{"pointer": p, "reason": r, "occurrences": n} for (p, r), n in sorted(counts.items())],
        "note_th": "ตรวจ projection, grain และ identity แล้ว; ยังไม่ใช่การเผยแพร่",
    }


def preview_publication(payload, contract_id: str, artifact: str) -> dict:
    contracts = load_contracts(ROOT / "config/publication_contracts")
    contract = next((c for _, c in contracts if c["contract_id"] == contract_id), None)
    if contract is None:
        raise ValueError("ไม่พบ publication contract")
    artifact_path = (ROOT / artifact).resolve()
    if not artifact_path.is_relative_to(ROOT / "data/public"):
        raise ValueError("artifact ต้องอยู่ใน data/public")
    artifact = artifact_path.relative_to(ROOT).as_posix()
    matches = [o for o in contract["outputs"] if o.get("path") == artifact or (
        o.get("path_glob") and fnmatchcase(artifact, o["path_glob"])
    )]
    if len(matches) != 1:
        raise ValueError("artifact ต้องเป็น path ที่ประกาศใน contract")
    output = matches[0]
    catalog = json.loads((ROOT / "config/source_catalog.json").read_text(encoding="utf-8"))
    restricted = {s["source_id"] for s in catalog["sources"] if s.get("cloud_policy") == "restricted_local_only"}
    problems = _privacy_problems(
        payload, artifact_path=artifact, restricted_source_ids=restricted,
        profile=contract["privacy_profile"], field_contexts=output.get("field_contexts", {}),
    )
    return {"status": "privacy_invalid" if problems else "privacy_valid", "problems": problems,
            "note_th": "preview เฉพาะ privacy; ตรวจ publication ครบด้วย python -m app.cli check"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON, JSONL, CSV หรือ .gz")
    lane = parser.add_mutually_exclusive_group(required=True)
    lane.add_argument("--source", help="source_id ของ connector")
    lane.add_argument("--publication", help="contract_id ของ public artifact")
    parser.add_argument("--dataset-key")
    parser.add_argument("--artifact", help="path ของ output เช่น data/public/example.json")
    args = parser.parse_args(argv)
    if args.source and not args.dataset_key:
        parser.error("--source ต้องใช้คู่กับ --dataset-key")
    if args.publication and not args.artifact:
        parser.error("--publication ต้องใช้คู่กับ --artifact")
    try:
        payload = read_payload(args.input)
        report = preview_connector(payload, args.source, args.dataset_key) if args.source else preview_publication(payload, args.publication, args.artifact)
    except (ValueError, OSError) as exc:
        # Parser errors can quote private source values; report only the class.
        print(json.dumps({"status": "invalid", "error_type": type(exc).__name__,
                          "note_th": "ตรวจรูปแบบไฟล์ source/dataset-key และ contract ให้ตรงกัน"}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report["status"] == "privacy_invalid")


if __name__ == "__main__":
    raise SystemExit(main())
