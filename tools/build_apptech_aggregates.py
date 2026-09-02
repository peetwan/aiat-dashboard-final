"""สร้าง public aggregate จาก ResponseRecorder run โดยไม่อ่าน Candidate DB/network."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from app.catalog import load_ingestion_plans
from app.connectors.target_household import (
    FAMILY_DASHBOARD_URL,
    INNOVATOR_DASHBOARD_URL,
    parse_household_economic_summary,
    parse_innovator_dashboard,
)
from app.settings import PROJECT_ROOT


SOURCE_ID = "f2_target_household"
OUTPUT_NAME = "apptech_aggregates.json"
MANIFEST_NAME = "apptech_aggregates_manifest.json"


def _json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def build(run_dir: Path, year_filters: list[str]) -> tuple[dict, dict]:
    """เลือกเฉพาะจำนวนระดับจังหวัดและยอดเงินระดับประเทศที่มีหลักฐานครบทุกปี."""
    run_dir = run_dir.resolve()
    if not year_filters or len(set(year_filters)) != len(year_filters) or "all" not in year_filters:
        raise ValueError("AppTech publication requires unique year filters including all")
    manifest_raw = (run_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest.get("source_id") != SOURCE_ID or manifest.get("status") != "complete":
        raise ValueError("AppTech publication requires a complete ResponseRecorder run")
    observed_at = manifest["fetched_at"]
    if datetime.fromisoformat(observed_at.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("ResponseRecorder fetched_at must include its timezone")

    endpoints = {INNOVATOR_DASHBOARD_URL, FAMILY_DASHBOARD_URL}
    pages: dict[tuple[str, str], str] = {}
    evidence: list[dict] = []
    for artifact in manifest["artifacts"]:
        url = urlsplit(artifact["url"])
        endpoint = url._replace(query="", fragment="").geturl()
        if endpoint not in endpoints:
            continue
        query = parse_qsl(url.query, keep_blank_values=True)
        if url.fragment or (query and (len(query) != 1 or query[0][0] != "year_filter")):
            raise ValueError("Unexpected AppTech dashboard query")
        year = query[0][1] if query else "all"
        identity = (endpoint, year)
        if year not in year_filters or identity in pages:
            raise ValueError("Unexpected or duplicate AppTech dashboard year")
        if artifact.get("http_status") != 200 or artifact.get("method") != "GET":
            raise ValueError("AppTech dashboard response was not a successful GET")
        path = (run_dir / Path(artifact["path"]).name).resolve()
        if path.parent != run_dir:
            raise ValueError("AppTech response must stay inside its recorded run")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != artifact["sha256"] or len(raw) != artifact["bytes"]:
            raise ValueError("AppTech response hash or size does not match its recorder manifest")
        pages[identity] = raw.decode("utf-8")
        evidence.append({"source_url": artifact["url"], "sha256": digest, "bytes": len(raw)})

    required = {(endpoint, year) for endpoint in endpoints for year in year_filters}
    if set(pages) != required:
        raise ValueError("AppTech publication is missing a dashboard/year response")
    innovators: list[dict] = []
    economics: list[dict] = []
    for year in year_filters:
        innovators.extend(row for _, row in parse_innovator_dashboard(pages[(INNOVATOR_DASHBOARD_URL, year)], year))
        economics.append(parse_household_economic_summary(pages[(FAMILY_DASHBOARD_URL, year)], year)[1])
    payload = {
        "schema_version": "1.0.0",
        "source_id": SOURCE_ID,
        "source_url": "https://pmua-apptech.com/dashboard",
        "generated_at": observed_at,
        "as_of": None,
        "year_filters": year_filters,
        "privacy": {"aggregate_only": True, "individual_records_included": False, "direct_identifiers_included": False},
        "innovator_dashboard_province": sorted(innovators, key=lambda row: (row["year_filter"], row["province_name_th"])),
        "household_economic_summary": economics,
    }
    provenance = {
        "schema_version": "1.0.0",
        "source_id": SOURCE_ID,
        "generated_at": observed_at,
        "as_of": None,
        "run_id": manifest["run_id"],
        "recorder_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "inputs": sorted(evidence, key=lambda item: item["source_url"]),
        "output": {"path": f"data/public/{OUTPUT_NAME}", "sha256": hashlib.sha256(_json_bytes(payload)).hexdigest()},
        "counts": {"innovator_dashboard_province": len(innovators), "household_economic_summary": len(economics)},
        "privacy": payload["privacy"],
    }
    return payload, provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "data/public")
    args = parser.parse_args()
    years = load_ingestion_plans()["sources"][SOURCE_ID]["dashboard_year_filters"]
    payload, provenance = build(args.run_dir, years)
    # Validate the entire recorded input before writing either public output.
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / OUTPUT_NAME).write_bytes(_json_bytes(payload))
    (args.output_dir / MANIFEST_NAME).write_bytes(_json_bytes(provenance))
    print(json.dumps(provenance["counts"]))


if __name__ == "__main__":
    main()
