#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(
    os.environ.get("AIAT_EVIDENCE_ROOT", str(PROJECT_ROOT.parent))
).expanduser().resolve()
RAW_RESPONSE_PATH = (
    WORKSPACE_ROOT
    / "data/raw/network/f2_learning_dashboard/20260803T_network/response.txt"
)
RAW_OBSERVATION_PATH = (
    WORKSPACE_ROOT
    / "data/raw/network/f2_learning_dashboard/20260803T_network/observation.json"
)
BOUNDARY_PATH = PROJECT_ROOT / "data/public/thailand_provinces.geojson"
OUTPUT_PATH = PROJECT_ROOT / "data/public/learning_dashboard.json"
MANIFEST_PATH = PROJECT_ROOT / "data/public/learning_dashboard_manifest.json"

SOURCE_ID = "f2_learning_dashboard"
SOURCE_URL = "https://lesuper.app/opendata/pmua/dashboard"
ENDPOINT_URL = "https://lesuper.app/api/opendata/pmua"
SCOPE_WARNING_TH = (
    "ข้อมูลครอบคลุมผู้เข้าร่วมโครงการที่ต้นทางเลือก ไม่ใช่ธุรกิจชุมชนทั้งหมด "
    "และต้นทางไม่ได้ระบุหน่วยหรือวันที่ as_of ระดับชุดข้อมูล"
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def provenance_path(
    path: Path,
    *,
    evidence_root: Path = WORKSPACE_ROOT,
    dashboard_root: Path = PROJECT_ROOT,
) -> str:
    """Return a stable path without assuming the repo lives under the evidence root."""
    resolved = path.expanduser().resolve()
    dashboard_root = dashboard_root.expanduser().resolve()
    evidence_root = evidence_root.expanduser().resolve()
    try:
        relative = resolved.relative_to(dashboard_root)
    except ValueError:
        try:
            return resolved.relative_to(evidence_root).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"provenance input is outside the dashboard and evidence roots: {resolved}"
            ) from exc
    return (Path("dashboard_final") / relative).as_posix()


def manifest_entry(path: Path) -> dict[str, Any]:
    return {
        "path": provenance_path(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def exact_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def finite_number(value: Any, *, table_name: str, row_number: int) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{table_name} row {row_number} value must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{table_name} row {row_number} value must be finite")
    return value


def normalize_header_table(payload: Any, table_name: str) -> dict[str, Any]:
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise ValueError(f"{table_name} must be a header-array table")
    headers = [exact_text(value) for value in payload[0]]
    if len(headers) != 2 or any(not value for value in headers):
        raise ValueError(f"{table_name} must have exactly two non-empty headers")

    rows: list[dict[str, Any]] = []
    for row_number, raw_row in enumerate(payload[1:], start=1):
        if not isinstance(raw_row, list) or len(raw_row) != len(headers):
            raise ValueError(f"{table_name} row {row_number} width does not match header")
        label = exact_text(raw_row[0])
        if not label:
            raise ValueError(f"{table_name} row {row_number} label is empty")
        rows.append(
            {
                "source_row_number": row_number,
                "label": label,
                "value": finite_number(
                    raw_row[1], table_name=table_name, row_number=row_number
                ),
            }
        )
    return {"source_headers": headers, "row_count": len(rows), "rows": rows}


def province_crosswalk(boundary_payload: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for feature in boundary_payload.get("features") or []:
        properties = feature.get("properties") or {}
        name = exact_text(properties.get("PROV_NAM_T"))
        code = exact_text(properties.get("PROV_CODE")).zfill(2)
        if not name or not code.isdigit():
            continue
        if name in result and result[name] != code:
            raise ValueError(f"duplicate province name in boundary crosswalk: {name}")
        result[name] = code
    if len(result) != 77:
        raise ValueError(f"expected 77 exact province names, found {len(result)}")
    return result


def build_projection(
    raw_payload: dict[str, Any],
    code_by_exact_name: dict[str, str],
    *,
    observed_at: str | None,
) -> dict[str, Any]:
    required_keys = {
        "provinces",
        "entityTypes",
        "categories",
        "geography",
        "geographyImpact",
        "impactSummary",
    }
    missing = sorted(required_keys - set(raw_payload))
    if missing:
        raise ValueError(f"raw learning dashboard payload missing keys: {missing}")

    province_table = normalize_header_table(raw_payload["provinces"], "provinces")
    entity_table = normalize_header_table(raw_payload["entityTypes"], "entityTypes")
    category_table = normalize_header_table(raw_payload["categories"], "categories")
    geography_table = normalize_header_table(raw_payload["geography"], "geography")

    matched_rows: list[dict[str, Any]] = []
    unmatched_rows: list[dict[str, Any]] = []
    links: dict[str, dict[str, Any]] = {}
    metric_label = province_table["source_headers"][1]
    for row in province_table["rows"]:
        code = code_by_exact_name.get(row["label"])
        item = {
            "source_row_number": row["source_row_number"],
            "province_name_th": row["label"],
            "province_code": code,
            "metric_label_th": metric_label,
            "value": row["value"],
            "unit": None,
            "as_of": None,
            "scope_warning_th": SCOPE_WARNING_TH,
            "source_url": SOURCE_URL,
            "endpoint_url": ENDPOINT_URL,
            "quality_status": "candidate_scope_definition_and_freshness_review",
        }
        if code is None:
            unmatched_rows.append(item)
            continue
        if code in links:
            raise ValueError(f"duplicate province code in learning dashboard payload: {code}")
        matched_rows.append(item)
        links[code] = item

    impact_rows = raw_payload["geographyImpact"]
    if not isinstance(impact_rows, list) or not all(
        isinstance(row, dict) for row in impact_rows
    ):
        raise ValueError("geographyImpact must be an array of objects")
    normalized_impact_rows = [
        {"source_row_number": index, **row}
        for index, row in enumerate(impact_rows, start=1)
    ]
    impact_summary = raw_payload["impactSummary"]
    if not isinstance(impact_summary, dict):
        raise ValueError("impactSummary must be an object")

    return {
        "schema_version": "1.0.0",
        "generated_at": observed_at,
        "publication_status": "public_candidate_projection",
        "source": {
            "ordinal": 10,
            "source_id": SOURCE_ID,
            "name_th": "Dashboard LE",
            "url": SOURCE_URL,
            "endpoint_url": ENDPOINT_URL,
            "method": "POST",
            "acquisition_mode": "api_first",
            "readiness_status": "needs_review",
            "expected_record_count": len(province_table["rows"]),
            "quality_label_th": "ข้อมูล candidate · ต้องยืนยันขอบเขต นิยาม หน่วย และเวลา",
            "notes_th": SCOPE_WARNING_TH,
        },
        "quality": {
            "status": "candidate_scope_definition_and_freshness_review",
            "as_of": None,
            "unit_status": "not_specified_by_source",
            "scope_warning_th": SCOPE_WARNING_TH,
            "province_join_method": "exact_thai_name_against_official_boundary",
        },
        "coverage": {
            "province_rows": province_table["row_count"],
            "linked_province_rows": len(matched_rows),
            "linked_provinces": len(links),
            "unmatched_province_rows": len(unmatched_rows),
            "entity_type_rows": entity_table["row_count"],
            "category_rows": category_table["row_count"],
            "geography_rows": geography_table["row_count"],
            "geography_impact_rows": len(normalized_impact_rows),
        },
        "province_rows": matched_rows,
        "unmatched_province_rows": unmatched_rows,
        "province_links": links,
        "non_province_tables": {
            "entity_types": entity_table,
            "categories": category_table,
            "geography": geography_table,
        },
        "non_province_impact": {
            "join_status": "not_joined_no_explicit_geography_key",
            "unit": None,
            "as_of": None,
            "rows": normalized_impact_rows,
            "summary": impact_summary,
        },
        "evidence": [
            "data/raw/network/f2_learning_dashboard/20260803T_network/response.txt",
            "data/raw/network/f2_learning_dashboard/20260803T_network/observation.json",
        ],
    }


def build() -> dict[str, Any]:
    raw_payload = read_json(RAW_RESPONSE_PATH)
    observation = read_json(RAW_OBSERVATION_PATH)
    crosswalk = province_crosswalk(read_json(BOUNDARY_PATH))
    output = build_projection(
        raw_payload,
        crosswalk,
        observed_at=observation.get("observed_at"),
    )
    write_json(OUTPUT_PATH, output)
    manifest = {
        "manifest_version": "1.0.0",
        "generated_at": output["generated_at"],
        "source_id": SOURCE_ID,
        "inputs": [
            manifest_entry(RAW_RESPONSE_PATH),
            manifest_entry(RAW_OBSERVATION_PATH),
            manifest_entry(BOUNDARY_PATH),
        ],
        "output": manifest_entry(OUTPUT_PATH),
    }
    write_json(MANIFEST_PATH, manifest)
    print(
        json.dumps(
            {
                "status": "ok",
                "source_id": SOURCE_ID,
                **output["coverage"],
            },
            ensure_ascii=False,
        )
    )
    return output


if __name__ == "__main__":
    build()
