from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
BASE_RUN = WORKSPACE_ROOT / "data/qa/web_profile_team_drive_simple/20260814T_team_drive_simple_final"
MERGE_RUN = WORKSPACE_ROOT / "data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01"
STAGED_ROOT = WORKSPACE_ROOT / "data/staged"
OUTPUT_ROOT = PROJECT_ROOT / "data/public/provincial_briefings"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_entry(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(WORKSPACE_ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def csv_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def jsonl_rows(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def clean(value: Any) -> Any:
    if value in (None, "", "\\N"):
        return None
    return value


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).replace("จังหวัด", "")


def canonical_code(value: Any) -> str | None:
    if value in (None, "", "\\N", "_unknown", "_multi_province"):
        return None
    text = str(value).strip()
    return text.zfill(2)[:2] if text.isdigit() else None


def source_fields(row: dict[str, Any], prefix: str = "source_fields__") -> dict[str, Any]:
    return {
        key.removeprefix(prefix): clean(value)
        for key, value in row.items()
        if key.startswith(prefix) and clean(value) is not None
    }


def compact_provenance(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "endpoint_url": clean(row.get("source_endpoint")),
        "fetched_at": clean(row.get("fetched_at")),
        "as_of": clean(row.get("as_of")),
        "quality_status": clean(row.get("quality_status")),
        "record_hash": clean(row.get("source_record_sha256")),
    }


def source_meta(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": source["source_id"],
        "name_th": source["name_th"],
        "url": source["url"],
        "acquisition_mode": source["acquisition_mode"],
        "readiness_status": source["readiness_status"],
    }


def initial_section(source_id: str, title_th: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "title_th": title_th,
        "status": "source_has_no_record_for_province",
        "total_records": 0,
        "items": [],
    }


def resolve_row_code(
    row: dict[str, Any], code_by_name: dict[str, str]
) -> str | None:
    candidates = (
        row.get("source_fields__cwt_id"),
        row.get("source_fields__province_id"),
        row.get("partition_key"),
    )
    for value in candidates:
        code = canonical_code(value)
        if code:
            return code
    names = (
        row.get("source_fields__cwt_dc"),
        row.get("source_fields__cwt_name"),
        row.get("source_fields__province_name"),
        row.get("source_fields__province_name_th"),
        row.get("source_fields__area_name"),
        row.get("partition_key"),
    )
    for value in names:
        code = code_by_name.get(normalize_text(value))
        if code:
            return code
    return None


def indicator(
    key: str,
    label_th: str,
    value: float,
    display_value: str,
    unit: str,
    source_url: str,
    source_id: str = "f3_housing_portal",
    note_th: str | None = None,
    calculation_th: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label_th": label_th,
        "value": value,
        "display_value": display_value,
        "unit": unit,
        "source_id": source_id,
        "source_url": source_url,
        "note_th": note_th,
        "calculation_th": calculation_th,
    }


def add_housing_signals(briefing: dict[str, Any]) -> None:
    groups = briefing["sections"]["housing"]["resource_groups"]
    by_id = {group["resource_id"]: group for group in groups}
    signals: list[dict[str, Any]] = []

    population = by_id.get("827aca76-9e90-43ed-86a2-cb9cb8651280")
    if population and population["rows"]:
        latest = max(population["rows"], key=lambda row: safe_float(row["values"].get("year")) or -1)
        value = safe_float(latest["values"].get("population"))
        year = latest["values"].get("year")
        if value is not None:
            signals.append(indicator(
                "population_latest", f"ประชากรในชุดข้อมูล ปี {year}", value,
                f"{value:,.0f}", "หน่วยตามต้นทาง", population["source_url"],
                note_th="ต้นทางยังไม่ระบุหน่วยใน resource metadata",
            ))

    simple_metrics = (
        (
            "197a5259-80a8-4c19-b90f-0bb9430d0037",
            "house_price_income_ratio",
            "อัตราส่วนราคาบ้านต่อรายได้",
            "house_price_income_ratio",
            "เท่า",
            lambda value: f"{value:.2f}",
        ),
        (
            "51b9cc37-cc96-4b33-900c-fa74408dcde0",
            "overcrowding_pct",
            "ที่อยู่อาศัยแออัด",
            "pct_overcrowded",
            "%",
            lambda value: f"{value:.2f}%",
        ),
        (
            "d9dd729e-3d23-445e-a126-4c7b69d7a578",
            "affordability_index",
            "ดัชนีความสามารถในการจ่ายที่อยู่อาศัย",
            "Mean",
            "ค่าดัชนีต้นทาง",
            lambda value: f"{value:.2f}",
        ),
    )
    for resource_id, key, label, field, unit, formatter in simple_metrics:
        group = by_id.get(resource_id)
        if not group or not group["rows"]:
            continue
        value = safe_float(group["rows"][0]["values"].get(field))
        if value is not None:
            signals.append(indicator(
                key, label, value, formatter(value), unit, group["source_url"],
                note_th="คงนิยามจากชื่อ field และ resource ของต้นทาง",
            ))

    loan = by_id.get("75436ffc-f88b-4092-a8c5-d1e4eec9c45f")
    if loan and loan["rows"]:
        share = safe_float(loan["rows"][0]["values"].get("share_loan_pass"))
        if share is not None:
            value = share * 100
            signals.append(indicator(
                "housing_loan_pass_share", "ผ่านเกณฑ์สินเชื่อที่อยู่อาศัย", value,
                f"{value:.2f}%", "%", loan["source_url"],
                calculation_th="share_loan_pass × 100",
            ))

    flood = by_id.get("7d51f36e-7072-4a2a-8067-4f10d97d5485")
    if flood and flood["rows"]:
        values = flood["rows"][0]["values"]
        level_4 = safe_float(values.get("risk_level_4_pct_area"))
        level_5 = safe_float(values.get("risk_level_5_pct_area"))
        if level_4 is not None and level_5 is not None:
            value = level_4 + level_5
            signals.append(indicator(
                "flood_risk_area_level_4_5", "พื้นที่เสี่ยงน้ำท่วมระดับ 4–5", value,
                f"{value:.2f}%", "% ของพื้นที่ตามต้นทาง", flood["source_url"],
                calculation_th="risk_level_4_pct_area + risk_level_5_pct_area",
            ))

    briefing["executive_signals"] = signals


def build() -> None:
    dashboard = read_json(PROJECT_ROOT / "data/public/public_dashboard.json")
    catalog = read_json(PROJECT_ROOT / "config/source_catalog.json")
    public_sources = {
        source["source_id"]: source
        for source in catalog["sources"]
        if source.get("production_values_allowed")
        and source.get("cloud_policy") != "restricted_local_only"
    }
    generated_at = datetime.now(timezone.utc).isoformat()
    code_by_name = {
        normalize_text(province["province_name_th"]): province["province_code"]
        for province in dashboard["provinces"]
    }
    briefings: dict[str, dict[str, Any]] = {}
    for province in dashboard["provinces"]:
        code = province["province_code"]
        briefings[code] = {
            "schema_version": "2.0.0",
            "generated_at": generated_at,
            "publication_status": "public_candidate_projection",
            "province": {
                "province_code": code,
                "province_name_th": province["province_name_th"],
                "province_name_en": province["province_name_en"],
                "region": province["region"],
                "centroid": province["centroid"],
            },
            "executive_signals": [],
            "sections": {
                "sra": initial_section("f1_sradss_ppaos", "สถานการณ์ความเปราะบาง SRA-DSS"),
                "area_based": initial_section("f2_learning_area_based", "โครงการพัฒนาระดับพื้นที่"),
                "innovation": initial_section("f2_apptech_mru", "นวัตกรรมพร้อมใช้ในพื้นที่"),
                "housing": {
                    **initial_section("f3_housing_portal", "ที่อยู่อาศัยและความเสี่ยงเมือง"),
                    "resource_groups": [],
                },
                "culture": initial_section("f2_culturalmap_university", "ทุนวัฒนธรรมในพื้นที่"),
                "tourism": initial_section("f3_ruamthiao_lamphun", "การเดินทางและท่องเที่ยวลำพูน"),
            },
            "source_coverage": [],
            "quality": {
                "status": "candidate_needs_review",
                "note_th": "แสดงค่าตามต้นทางและ derivation ที่ระบุเท่านั้น ไม่สร้างคะแนนจัดสรรงบอัตโนมัติ",
                "restricted_source_ids_excluded": [
                    "f2_wallet_all_realtime",
                    "f2_wallet_cluster_realtime",
                ],
            },
        }

    # SRA-DSS: province aggregates only. Songkhla is intentionally absent from year 2569.
    sra_path = BASE_RUN / "01_f1_sradss_ppaos/data/f1_sradss_ppaos_current_year_2569_indicator_rows.csv"
    for row in csv_rows(sra_path):
        code = canonical_code(row.get("province_code"))
        value = safe_float(row.get("value"))
        if code not in briefings or value is None or not clean(row.get("metric_key")):
            continue
        section = briefings[code]["sections"]["sra"]
        section["items"].append({
            "metric_key": row["metric_key"],
            "value": value,
            "unit": clean(row.get("unit")),
            "as_of": clean(row.get("as_of")),
            "snapshot_date": clean(row.get("snapshot_date")),
            "source_url": clean(row.get("source_endpoint")),
            "definition_status": clean(row.get("definition_status")),
        })

    # Area-Based: keep every project record attached to a province.
    area_path = BASE_RUN / "11_f2_learning_area_based/data.csv"
    for row in csv_rows(area_path):
        code = code_by_name.get(normalize_text(row.get("source_fields__province")))
        if code not in briefings:
            continue
        briefings[code]["sections"]["area_based"]["items"].append({
            "record_id": clean(row.get("source_fields__id")),
            "project_name": clean(row.get("source_fields__projectName")),
            "fiscal_year": clean(row.get("source_fields__fiscalYear")),
            "research_unit": clean(row.get("source_fields__researchUnit")),
            "business_name": clean(row.get("source_fields__businessName")),
            "district": clean(row.get("source_fields__district")),
            "subdistrict": clean(row.get("source_fields__subDistrict")),
            "updated_at": clean(row.get("source_fields__updatedAt")),
            "source_url": clean(row.get("source_endpoint")),
            "provenance": compact_provenance(row),
        })

    # AppTech MRU: use the richer validated Silver projection, while the list is refreshed by API.
    innovation_path = (
        STAGED_ROOT
        / "f2_apptech_mru/20260805T_apptech_mru_silver_02/silver/apptech_mru_public_innovation.jsonl"
    )
    for row in jsonl_rows(innovation_path):
        fields = row.get("normalized_fields") or {}
        codes = {
            code_by_name.get(normalize_text(area.get("province")))
            for area in fields.get("areas") or []
        }
        for code in codes - {None}:
            if code not in briefings:
                continue
            provenance = row.get("provenance") or {}
            briefings[code]["sections"]["innovation"]["items"].append({
                "record_id": fields.get("record_id") or row.get("record_id"),
                "title": fields.get("title"),
                "owner_affiliation_name": fields.get("owner_affiliation_name"),
                "description": fields.get("description"),
                "knowledge_technology": fields.get("knowledge_technology"),
                "innovation_type": fields.get("innovation_type_label"),
                "category": fields.get("category_label"),
                "trl_level": fields.get("trl_level"),
                "innovation_value_baht": fields.get("innovation_value_baht"),
                "funding": fields.get("funding") or [],
                "roi_indicator": fields.get("roi_indicator"),
                "roi_unit": fields.get("roi_unit"),
                "sroi_indicator": fields.get("sroi_indicator"),
                "sroi_unit": fields.get("sroi_unit"),
                "target_groups": fields.get("target_groups") or [],
                "highlights": fields.get("highlights") or [],
                "areas": fields.get("areas") or [],
                "source_url": provenance.get("detail_url") or provenance.get("endpoint_url"),
                "fetched_at": provenance.get("fetched_at"),
            })

    # Cultural Map: all province records, including records without coordinates.
    cultural_path = MERGE_RUN / "03_f2_culturalmap_university/data/map_inspiration.json"
    cultural_root = read_json(cultural_path)
    for row in cultural_root["data"]["records"]:
        data = row.get("data") or {}
        location = data.get("location") or {}
        administrative = location.get("administrative") or {}
        code = canonical_code((administrative.get("province") or {}).get("code"))
        if code not in briefings:
            continue
        classification = data.get("classification") or {}
        assessment = data.get("assessment") or {}
        names = data.get("names") or {}
        media = data.get("media") or {}
        dates = data.get("dates") or {}
        description = data.get("description") or {}
        item = {
            "record_id": row.get("external_id"),
            "record_code": (data.get("identifiers") or {}).get("record_code"),
            "title_th": names.get("th") or row.get("title"),
            "title_en": names.get("en"),
            "category": (classification.get("primary_category") or {}).get("name_th"),
            "cultural_type": (classification.get("cultural_type") or {}).get("name_th"),
            "risk_status_code": (assessment.get("risk") or {}).get("status_code"),
            "risk_reason": (assessment.get("risk") or {}).get("reason"),
            "history": description.get("history"),
            "potential": description.get("potential"),
            "stakeholders": description.get("stakeholders"),
            "amphoe": (administrative.get("amphure") or {}).get("name_th"),
            "tambon": (administrative.get("tambon") or {}).get("name_th"),
            "coordinates": {
                "latitude": (location.get("coordinates") or {}).get("latitude"),
                "longitude": (location.get("coordinates") or {}).get("longitude"),
            },
            "recorded_at": dates.get("recorded"),
            "image_url": ((media.get("images") or [{}])[0] or {}).get("url"),
            "source_url": row.get("source_url"),
            "validation_warnings": row.get("validation_warnings") or [],
        }
        briefings[code]["sections"]["culture"]["items"].append(item)

    # Housing: every approved flattened record, grouped by CKAN resource.
    housing_metadata_path = (
        STAGED_ROOT
        / "f3_housing_portal/20260803T_housing_silver_02/resource_inventory.json"
    )
    housing_metadata = {
        item["resource_id"]: item
        for item in read_json(housing_metadata_path)["resources"]
    }
    grouped_rows: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    housing_dir = BASE_RUN / "23_f3_housing_portal/data"
    housing_paths = sorted(housing_dir.glob("*.csv"))
    for path in housing_paths:
        for row in csv_rows(path):
            code = resolve_row_code(row, code_by_name)
            if code not in briefings:
                continue
            resource_id = row.get("resource_id") or row.get("dataset_id", "").rsplit(":", 1)[-1]
            grouped_rows[code][resource_id].append({
                "row_number": clean(row.get("row_number")) or clean(row.get("source_record_id")),
                "values": source_fields(row),
                "provenance": compact_provenance(row),
            })
    for code, resources in grouped_rows.items():
        groups = []
        for resource_id, rows in resources.items():
            metadata = housing_metadata.get(resource_id, {})
            sample = rows[0] if rows else {"provenance": {}}
            groups.append({
                "dataset_key": metadata.get("dataset_key"),
                "dataset_title": metadata.get("dataset_title"),
                "resource_id": resource_id,
                "resource_name": metadata.get("resource_name") or resource_id,
                "source_url": metadata.get("resource_url") or sample["provenance"].get("endpoint_url"),
                "resource_metadata_modified": metadata.get("resource_metadata_modified"),
                "definition_status": metadata.get("status") or "needs_review",
                "field_names": sorted({key for item in rows for key in item["values"]}),
                "row_count": len(rows),
                "rows": rows,
            })
        groups.sort(key=lambda item: (item["dataset_key"] or "", item["resource_name"] or ""))
        briefings[code]["sections"]["housing"]["resource_groups"] = groups
        briefings[code]["sections"]["housing"]["items"] = []

    # Ruam Thiao is explicitly Lamphun-scoped in its source definition.
    tourism_files = sorted((MERGE_RUN / "16_f3_ruamthiao_lamphun/data").glob("*.json"))
    if "51" in briefings:
        briefings["51"]["sections"]["tourism"]["items"] = [
            {
                "page_id": payload.get("page_id"),
                "source_url": payload.get("source_url"),
                "scraped_at": payload.get("scraped_at"),
                "data": payload.get("data"),
            }
            for payload in (read_json(path) for path in tourism_files)
        ]

    not_province_scoped = {
        "f2_rmutdb": "ทะเบียนไม่มี field จังหวัดที่ยืนยันแล้ว",
        "f2_apptech_mtr": "ทะเบียนไม่มี field จังหวัดที่ยืนยันแล้ว",
        "f3_city_capital_open_data": "ต้นทางเป็นระดับเทศบาลและยังไม่มี province key ที่ยืนยันแล้ว",
        "f1_pppconnext": "มีชื่อพื้นที่แต่ระดับ geography ยังไม่ชัด จึงไม่ join เป็นจังหวัด",
    }
    section_source = {
        "f1_sradss_ppaos": "sra",
        "f2_culturalmap_university": "culture",
        "f2_apptech_mru": "innovation",
        "f2_learning_area_based": "area_based",
        "f3_housing_portal": "housing",
        "f3_ruamthiao_lamphun": "tourism",
    }

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    written_files: list[Path] = []
    for code, briefing in briefings.items():
        for section in briefing["sections"].values():
            if section["source_id"] == "f3_housing_portal":
                total = sum(group["row_count"] for group in section["resource_groups"])
            else:
                total = len(section["items"])
            section["total_records"] = total
            section["status"] = "available" if total else "source_has_no_record_for_province"

        add_housing_signals(briefing)
        coverage = []
        for source_id, source in public_sources.items():
            item = source_meta(source)
            if source_id in not_province_scoped:
                item.update({
                    "status": "not_province_scoped",
                    "records": None,
                    "note_th": not_province_scoped[source_id],
                })
            else:
                section = briefing["sections"].get(section_source.get(source_id, ""))
                records = section["total_records"] if section else 0
                item.update({
                    "status": "available" if records else "source_has_no_record_for_province",
                    "records": records,
                    "note_th": None,
                })
            coverage.append(item)
        briefing["source_coverage"] = sorted(coverage, key=lambda item: public_sources[item["source_id"]]["ordinal"])
        briefing["available_source_ids"] = [
            item["source_id"] for item in briefing["source_coverage"] if item["status"] == "available"
        ]
        output_path = OUTPUT_ROOT / f"{code}.json"
        write_json(output_path, briefing)
        written_files.append(output_path)

    input_paths = [
        PROJECT_ROOT / "config/source_catalog.json",
        PROJECT_ROOT / "data/public/public_dashboard.json",
        sra_path,
        area_path,
        innovation_path,
        cultural_path,
        housing_metadata_path,
        *housing_paths,
        *tourism_files,
    ]
    index = {
        "schema_version": "2.0.0",
        "generated_at": generated_at,
        "province_count": len(briefings),
        "source_count": len(public_sources),
        "inputs": [manifest_entry(path) for path in input_paths],
        "files": [
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sorted(written_files)
        ],
    }
    write_json(OUTPUT_ROOT / "index.json", index)
    print(json.dumps({"status": "ok", **index}, ensure_ascii=False))


if __name__ == "__main__":
    build()
