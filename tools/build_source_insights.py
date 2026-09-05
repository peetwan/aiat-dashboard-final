from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.public_work_details import (
    project_cultural_supporting, project_mtr_work, project_rmutdb_work, rmutdb_public_contacts, mtr_public_contacts,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(
    os.environ.get("AIAT_EVIDENCE_ROOT", str(PROJECT_ROOT.parent))
).expanduser().resolve()
BASE_RUN = WORKSPACE_ROOT / "data/qa/web_profile_team_drive_simple/20260814T_team_drive_simple_final"
PPP_PATH = (
    WORKSPACE_ROOT
    / "data/staged/f1_pppconnext/20260817T_public_api_silver_02/silver/records.jsonl"
)
APPTECH_RAW_ROOT = (
    WORKSPACE_ROOT / "data/raw/network/f2_apptech_mtr/20260816T_geo_link_audit_07"
)
APPTECH_RECORD_PATH = (
    WORKSPACE_ROOT
    / "data/staged/f2_apptech_mtr/20260817T_public_api_silver_07/silver/apptech_public_innovation.jsonl"
)
APPTECH_CURRENT_ROOT = (
    WORKSPACE_ROOT / "data/raw/network/f2_apptech_mtr/20260817T_public_api_completeness_07"
)
CITY_PATH = (
    WORKSPACE_ROOT
    / "data/raw/external_team_scraper/f3_city_capital_open_data/20260816T_external_team_import_14/output/latest.json"
)
CITY_CROSSWALK_PATH = (
    WORKSPACE_ROOT
    / "data/raw/ckan/f3_city_capital_open_data/20260816T_dla_city_crosswalk_14b/matched_cities.json"
)
CITY_CURRENT_SURFACE_MANIFEST = (
    WORKSPACE_ROOT
    / "data/raw/network/f3_city_capital_open_data/20260817T_static_surface_14/manifest.json"
)
OUTPUT_PATH = PROJECT_ROOT / "data/public/source_insights.json"
MANIFEST_PATH = PROJECT_ROOT / "data/public/source_insights_manifest.json"
LEARNING_PATH = PROJECT_ROOT / "data/public/learning_dashboard.json"
LEARNING_MANIFEST_PATH = PROJECT_ROOT / "data/public/learning_dashboard_manifest.json"
HOUSING_SPATIAL_SUMMARY_PATH = PROJECT_ROOT / "data/public/housing_spatial_summary.json"
HOUSING_DEMAND_SUMMARY_PATH = PROJECT_ROOT / "data/public/housing_demand_summary.json"
AREA_BASED_RESPONSE_PATH = (
    WORKSPACE_ROOT / "data/raw/network/f2_learning_area_based/20260803T_network/response.json"
)
AREA_BASED_CURRENT_OBSERVATION = (
    WORKSPACE_ROOT
    / "data/raw/network/f2_learning_area_based/20260817T_freshness_check_11/observation.json"
)
CULTURAL_ROOT = (
    WORKSPACE_ROOT
    / "data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01"
    / "03_f2_culturalmap_university/data"
)
CULTURAL_DATASETS = {
    "map_inspiration": ("map_inspiration.json", 5_258, "province_point_records"),
    "products": ("products.json", 226, "supporting_records_not_geo_joined"),
    "activities": ("activities.json", 43, "supporting_records_not_geo_joined"),
    "recreation": ("recreation.json", 80, "supporting_records_not_geo_joined"),
    "team": ("team.json", 12, "source_team_records_not_geo_joined"),
}

AUDIT_EVIDENCE_PATHS = {
    source_id: WORKSPACE_ROOT
    / f"data/source_audit/{folder}/evidence/website_completeness_20260817.json"
    for source_id, folder in {
        "f1_sradss_ppaos": "01_f1_sradss_ppaos",
        "f1_pppconnext": "02_f1_pppconnext",
        "f2_culturalmap_university": "03_f2_culturalmap_university",
        "f2_rmutdb": "06_f2_rmutdb",
        "f2_apptech_mtr": "07_f2_apptech_mtr",
        "f2_apptech_mru": "08_f2_apptech_mru",
        "f2_learning_area_based": "11_f2_learning_area_based",
        "f3_city_capital_open_data": "14_f3_city_capital_open_data",
        "f3_ruamthiao_lamphun": "16_f3_ruamthiao_lamphun",
        "f3_housing_portal": "23_f3_housing_portal",
    }.items()
}


CITY_GROUP_LABELS = {
    "environment": "สิ่งแวดล้อมและภูมิอากาศ",
    "infrastructure": "บริการเมืองและโครงสร้างพื้นฐาน",
    "society_economy": "สังคมและเศรษฐกิจ",
}

# Only metrics whose direction is explicit from the published label/description are
# included in the executive readout. This is not a policy score or budget ranking.
CITY_CONCERN_DIRECTIONS = {
    "environment.heatDays": "high",
    "environment.pm25": "high",
    "environment.canopy": "low",
    "environment.flood": "high",
    "environment.hazard": "high",
    "environment.lst": "high",
    "environment.green": "low",
    "infrastructure.electricity": "low",
    "infrastructure.waterAccess": "low",
    "infrastructure.internet": "low",
    "infrastructure.wasteMgmt": "low",
    "infrastructure.transport": "low",
    "society_economy.unemploymentClean": "high",
    "society_economy.informal": "high",
    "society_economy.accidents": "high",
    "society_economy.itaScore": "low",
    "society_economy.educationClean": "low",
    "society_economy.dependency": "high",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl_rows(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def csv_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


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


def input_entry(path: Path) -> dict[str, Any]:
    return {
        "path": provenance_path(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def clean(value: Any) -> str | None:
    text = " ".join(str(value or "").strip().split())
    return None if not text or text == "\\N" else text


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_province(value: Any) -> str:
    return " ".join(str(value or "").replace("จังหวัด", "").strip().split())


def distribution(
    rows: Iterable[dict[str, Any]], field: str, limit: int | None = None
) -> list[dict[str, Any]]:
    counts = Counter(clean(row.get(field)) for row in rows)
    counts.pop(None, None)
    total = sum(counts.values())
    items = counts.most_common(limit)
    return [
        {
            "label_th": label,
            "value": value,
            "share_pct": round(value / total * 100, 1) if total else 0,
        }
        for label, value in items
    ]


def build_ppp(code_by_name: dict[str, str]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    rows = list(jsonl_rows(PPP_PATH))
    level_counts = Counter(row.get("geography_level") for row in rows)
    record_type_counts = Counter(row.get("record_type") for row in rows)
    province_links: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmatched: set[str] = set()
    province_metrics = {
        "households_total": ("ครัวเรือนที่สำรวจไม่ซ้ำ", "ครัวเรือน"),
        "members_total": ("สมาชิกในครัวเรือน", "คน"),
        "poor_households_total": ("ครัวเรือนยากจนจริง", "ครัวเรือน"),
        "poor_members_total": ("สมาชิกครัวเรือนยากจน", "คน"),
        "poor_households_rate": ("สัดส่วนครัวเรือนยากจนจริง", "ratio"),
        "avg_score": ("คะแนนศักยภาพทุนเฉลี่ย", "คะแนน"),
    }
    for row in rows:
        if row.get("record_type") != "province_summary":
            continue
        province_name = normalize_province(row.get("geography_name_th"))
        code = str(row.get("geography_code") or "").zfill(2)
        code = code if code in set(code_by_name.values()) else code_by_name.get(province_name)
        if not code:
            if province_name:
                unmatched.add(province_name)
            continue
        for metric_key, (metric_name, unit) in province_metrics.items():
            province_links[code].append({
                "metric_key": metric_key,
                "metric_name": metric_name,
                "value": safe_float((row.get("values") or {}).get(metric_key)),
                "unit": unit,
                "source_url": row.get("provenance", {}).get("source_page"),
                "endpoint_url": row.get("provenance", {}).get("endpoint"),
                "fetched_at": row.get("provenance", {}).get("fetched_at"),
                "as_of": row.get("provenance", {}).get("as_of"),
                "quality_status": row.get("quality", {}).get("status"),
            })

    name_by_code = {code: name for name, code in code_by_name.items()}
    national = next(row for row in rows if row["record_type"] == "national_summary")
    capital = [row for row in rows if row["record_type"] == "capital_dimension"]
    assistance = next(row for row in rows if row["record_type"] == "assistance_summary")
    fetched_at_values = sorted({
        row.get("provenance", {}).get("fetched_at")
        for row in rows
        if row.get("provenance", {}).get("fetched_at")
    })
    return {
        "source_id": "f1_pppconnext",
        "name_th": "PPPConnext",
        "source_url": "https://ppaos.com/2026/dashboard/ppaos/",
        "acquisition": "public_aggregate_api",
        "freshness_status": "observed_2026_08_17_source_as_of_not_provided",
        "quality_status": "candidate_needs_semantic_owner_review",
        "grain_th": "หนึ่งแถวต่อ aggregate ที่หน้า Dashboard รุ่น 2026 แสดง; ไม่มีข้อมูลครัวเรือนหรือบุคคลรายตัว",
        "readout_th": "ข้อมูลปัจจุบันตรงกับหน้า PPPConnext รุ่น 2026 ครบทั้ง 20 จังหวัด ปีสำรวจ ทุน 5 มิติ และความช่วยเหลือ; ยังต้องให้ owner ยืนยันนิยามก่อนใช้เป็น KPI ทางการ",
        "national_summary": national["values"],
        "capital_dimensions": [
            {
                "key": row["dimension_key"],
                "label_th": row["dimension_label_th"],
                **row["values"],
            }
            for row in capital
        ],
        "assistance_summary": assistance["values"],
        "fetched_at": fetched_at_values[-1] if fetched_at_values else None,
        "as_of": None,
        "coverage": {
            "aggregate_rows": len(rows),
            "province_rows": record_type_counts.get("province_summary", 0),
            "linked_provinces": len(province_links),
            "unmatched_province_names": sorted(unmatched),
        },
        "geography_levels": [
            {"key": key, "value": level_counts[key]}
            for key in ("national_dashboard_scope", "province")
        ],
        "widgets": [
            {"key": key, "value": value}
            for key, value in record_type_counts.most_common()
        ],
        "metrics": [
            {"label_th": label, "metric_key": key, "unit": unit, "province_count": len(province_links)}
            for key, (label, unit) in province_metrics.items()
        ],
        "provinces": [
            {
                "province_code": code,
                "province_name_th": name_by_code.get(code, code),
                "metrics": records,
            }
            for code, records in sorted(province_links.items())
        ],
        "evidence": [
            "data/staged/f1_pppconnext/20260817T_public_api_silver_02/manifest.json",
            "data/raw/network/f1_pppconnext/20260817T_public_api_fetch_02/manifest.json",
            "data/raw/network/f1_pppconnext/20260817T_public_api_fetch_02/network_observation.json",
        ],
    }, dict(province_links)


def build_apptech() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    records = [
        {
            **row,
            **{
                f"normalized_fields__{key}": value
                for key, value in (row.get("normalized_fields") or {}).items()
            },
        }
        for row in jsonl_rows(APPTECH_RECORD_PATH)
    ]
    institute_map_path = APPTECH_RAW_ROOT / "responses/institute_map.json"
    public_contacts = mtr_public_contacts(WORKSPACE_ROOT, records)
    innovator_map_path = APPTECH_RAW_ROOT / "responses/innovator_map.json"
    interaction_map_path = APPTECH_RAW_ROOT / "responses/interaction_map.json"
    statistics_path = APPTECH_CURRENT_ROOT / "profiles/custom_statistics.profile.json"
    institute_rows = read_json(institute_map_path)["data"]["mapData"]
    innovator_rows = read_json(innovator_map_path)["data"]["mapData"]
    interaction_payload = read_json(interaction_map_path)["data"]
    interaction_rows = (
        interaction_payload.get("mapData", interaction_payload)
        if isinstance(interaction_payload, dict)
        else interaction_payload
    )
    stats = read_json(statistics_path)["aggregate_scalars"]
    institute_by_code = {str(row["code"]).zfill(2): row for row in institute_rows}
    innovator_by_code = {str(row["code"]).zfill(2): row for row in innovator_rows}
    interaction_by_code = {str(row["code"]).zfill(2): row for row in interaction_rows}
    province_links: dict[str, dict[str, Any]] = {}
    for code in sorted(set(institute_by_code) | set(innovator_by_code) | set(interaction_by_code)):
        source = innovator_by_code.get(code) or interaction_by_code.get(code) or institute_by_code[code]
        province_links[code] = {
            "province_name_th": source.get("province"),
            "registered_users": safe_float((innovator_by_code.get(code) or {}).get("appTechLength")) or 0,
            "interactions": safe_float((interaction_by_code.get(code) or {}).get("appTechLength")) or 0,
            "institutes": safe_float((institute_by_code.get(code) or {}).get("appTechLength")) or 0,
            "source_url": "https://rinmp.com/",
            "quality_status": "aggregate_candidate_needs_review",
        }

    return {
        "source_id": "f2_apptech_mtr",
        "name_th": "AppTech MTR",
        "public_records": [project_mtr_work(row, public_contacts[row["source_record_id"]]) for row in records],
        "source_url": "https://rinmp.com/",
        "acquisition": "public_api",
        "freshness_status": "records_and_statistics_observed_2026_08_17_geo_aggregates_observed_2026_08_16",
        "quality_status": "structural_candidate_needs_review",
        "grain_th": "ทะเบียนนวัตกรรมหนึ่งแถวต่อรายการ; แผนที่ API เป็นยอดรวมผู้ใช้และการปฏิสัมพันธ์ต่อจังหวัด",
        "readout_th": "API จังหวัดใช้บอกการกระจายผู้ใช้และกิจกรรม ไม่ใช้แทนจำนวนผลงานนวัตกรรม",
        "statistics": {
            "snapshot_records": len(records),
            "upstream_total_apptech": stats.get("totalAppTechCount"),
            "innovators": stats.get("innovatorCount"),
            "registered_users": stats.get("normalUserCount"),
            "requirements": stats.get("requirementCount"),
            "matched_requirements": stats.get("matchRequirementCount"),
            "institute_count": stats.get("instituteCount"),
            "province_user_total": int(sum(item["registered_users"] for item in province_links.values())),
            "province_interaction_total": int(sum(item["interactions"] for item in province_links.values())),
            "province_user_coverage": sum(item["registered_users"] > 0 for item in province_links.values()),
            "province_interaction_coverage": sum(item["interactions"] > 0 for item in province_links.values()),
        },
        "distributions": {
            "institutes": distribution(records, "normalized_fields__institute_name", 10),
            "categories": distribution(records, "normalized_fields__category_name", 10),
            "atl_levels": distribution(records, "normalized_fields__atl_level"),
        },
        "province_activity": [
            {"province_code": code, **values}
            for code, values in sorted(
                province_links.items(),
                key=lambda item: item[1]["registered_users"],
                reverse=True,
            )
        ],
        "audit_notes": [
            "public list และ API สถิติรอบ 2026-08-17 ตรงกันที่ 630 รายการ; Silver เดิม 621 ขาด 9 รายการและมี 1 record เดิมเปลี่ยน version",
            "institute map ตอบ 77 จังหวัดแต่ค่าเป็นศูนย์ทั้งหมด จึงไม่ใช้วิเคราะห์",
            "province maps เป็น snapshot 2026-08-16 และเป็นคนละ grain กับทะเบียนนวัตกรรม; ต้นทางไม่ส่ง CORS header จึงเรียกผ่าน serving API ของโครงการ",
        ],
        "evidence": [
            "data/raw/network/f2_apptech_mtr/20260817T_public_api_completeness_07/manifest.json",
            "data/staged/f2_apptech_mtr/20260817T_public_api_silver_07/manifest.json",
            "data/source_audit/07_f2_apptech_mtr/evidence/website_completeness_20260817.json",
            "data/raw/network/f2_apptech_mtr/20260816T_geo_link_audit_07/manifest.json",
            "data/raw/network/f2_apptech_mtr/20260816T_geo_link_audit_07/observation.json",
        ],
    }, province_links


def build_rmutdb() -> dict[str, Any]:
    rows = list(csv_rows(BASE_RUN / "06_f2_rmutdb/data.csv"))
    detailed = [row for row in rows if row.get("record_type") == "rmutdb_ebook_innovation_detail"]
    summaries = [row for row in rows if row.get("record_type") != "rmutdb_ebook_innovation_detail"]
    silver = list(jsonl_rows(WORKSPACE_ROOT / "data/staged/silver/f2_rmutdb/20260805T_ebook_silver_01/rmutdb_ebook_innovation.jsonl"))
    contacts = rmutdb_public_contacts(WORKSPACE_ROOT, silver)
    trl_counter: Counter[str] = Counter()
    for row in detailed:
        value = clean(row.get("normalized_fields__trl_level"))
        match = re.search(r"([2-9])", value or "")
        if match:
            trl_counter[match.group(1)] += 1
    return {
        "source_id": "f2_rmutdb",
        "name_th": "RMUTDB Innovation",
        "public_records": [project_rmutdb_work(row, contacts[row["source_record_id"]]) for row in silver],
        "source_url": "https://rmutdb.net/",
        "acquisition": "public_pdf_snapshot",
        "freshness_status": "all_11_ebook_files_verified_unchanged_2026_08_17_last_modified_2023_03_05",
        "quality_status": "candidate_needs_review",
        "grain_th": "หนึ่งแถวต่อผลงานที่สกัดจาก e-book สาธารณะ",
        "readout_th": "ไม่ผูกจังหวัด เพราะมหาวิทยาลัยเจ้าของผลงานไม่ใช่สถานที่ใช้งานนวัตกรรม",
        "statistics": {
            "records": len(rows),
            "detailed_records": len(detailed),
            "annual_summary_records": len(summaries),
        },
        "distributions": {
            "technology_groups": distribution(detailed, "normalized_fields__technology_group"),
            "institutions": distribution(detailed, "normalized_fields__owner_affiliation"),
            "trl_levels": [
                {"label_th": f"TRL {key}", "value": trl_counter[key]}
                for key in sorted(trl_counter, key=int)
            ],
            "ip_status": distribution(detailed, "normalized_fields__ip_protection_status"),
        },
        "audit_notes": [
            "JSON API ตอบ 401 จึงใช้ public e-book เท่านั้น",
            "ฉบับละเอียดและฉบับสรุปประจำปีเป็นคนละรูปแบบ ไม่บวกเป็นยอดผลงาน authoritative",
            "ไม่มี record-level province/location ที่ยืนยันได้",
            "HEAD public e-book ครบ 11/11 เมื่อ 2026-08-17 และ metadata ไม่เปลี่ยนจาก snapshot เดิม",
            "ยอดหน้า Dashboard ที่เคยสังเกต 1,015 มากกว่าฉบับละเอียด 1,006 อยู่ 9 รายการ; ต้องขอ owner-approved export/API จึงจะปิดช่องว่าง live database ได้",
        ],
        "evidence": [
            "data/raw/export/f2_rmutdb/20260805T_ebook_export_01/manifest.json",
            "data/staged/silver/f2_rmutdb/20260805T_ebook_silver_01/summary.json",
            "data/raw/network/f2_rmutdb/20260817T_ebook_catalog_06/manifest.json",
            "data/source_audit/06_f2_rmutdb/evidence/website_completeness_20260817.json",
        ],
    }


def build_cultural_supporting_coverage() -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
    public_records: list[dict[str, Any]] = []
    supporting_records = 0
    total_records = 0
    for dataset_id, (filename, expected_count, geography_status) in CULTURAL_DATASETS.items():
        path = CULTURAL_ROOT / filename
        payload = read_json(path)
        records = (payload.get("data") or {}).get("records")
        if not isinstance(records, list):
            raise RuntimeError(f"cultural dataset {dataset_id} has no records array")
        if len(records) != expected_count:
            raise RuntimeError(
                f"cultural dataset {dataset_id} expected {expected_count} records, found {len(records)}"
            )
        total_records += len(records)
        if dataset_id != "map_inspiration":
            supporting_records += len(records)
            public_records.extend(project_cultural_supporting(row, dataset_id) for row in records)
        datasets.append({
            "dataset_id": dataset_id,
            "record_count": len(records),
            "grain": "one_public_source_record",
            "geography_status": geography_status,
        })

    return {
        "source_id": "f2_culturalmap_university",
        "name_th": "แผนที่วัฒนธรรมไทย Cultural Mapping (ภาคมหาวิทยาลัย)",
        "source_url": "https://www.culturalmapthailand.info/",
        "acquisition": "public_feed_and_listing_snapshot",
        "freshness_status": "id_sets_verified_2026_08_17_source_as_of_unknown",
        "quality_status": "candidate_needs_review",
        "grain_th": "นับแยกตาม dataset ต้นทาง; 361 supporting records ไม่ถูกบวกเป็นจุดแผนที่หรือผูกจังหวัด",
        "readout_th": "ทะเบียน Map 5,258 รายการ และ Products, Activities, Re-Creation, Team อีก 361 รายการ เก็บชื่อผู้จัดทำและข้อมูลติดต่องานตามหน้าสาธารณะ ไม่ผูกจังหวัดเมื่อไม่มีข้อมูลพื้นที่ยืนยัน",
        "public_records": public_records,
        "coverage": {
            "map_records": 5_258,
            "supporting_records": supporting_records,
            "total_records": total_records,
            "datasets": datasets,
        },
        "privacy_projection": {
            "supporting_records_exposed": True,
            "public_work_details": True,
            "account_identifiers_exposed": False,
        },
        "evidence": [
            "data/raw/network/f2_culturalmap_university/20260817T_current_surface_03/manifest.json",
            "data/staged/f2_culturalmap_university/20260817T_current_surface_reconciled_03/manifest.json",
            *[
                f"data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01/03_f2_culturalmap_university/data/{filename}"
                for filename, _, _ in CULTURAL_DATASETS.values()
            ],
        ],
    }


def build_city(
    code_by_name: dict[str, str],
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    payload = read_json(CITY_PATH)
    crosswalk = read_json(CITY_CROSSWALK_PATH)
    city_catalog = {city["city_id"]: city for city in payload["cities"]}
    crosswalk_by_city = {item["city_id"]: item for item in crosswalk["matches"]}
    observations: dict[str, dict[str, float | None]] = defaultdict(dict)
    for row in payload["observations"]:
        observations[row["city_id"]][row["metric_id"]] = safe_float(row.get("value"))

    city_rows: list[dict[str, Any]] = []
    province_links: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for city_id, city in city_catalog.items():
        match = crosswalk_by_city[city_id]
        province_name = normalize_province(match["province_name_th"])
        code = code_by_name.get(province_name)
        if not code:
            raise RuntimeError(f"official city crosswalk did not resolve province: {province_name}")
        item = {
            "city_id": city_id,
            "city_name_th": city["name_th"],
            "province_code": code,
            "province_name_th": match["province_name_th"],
            "district_name_th": match["district_name_th"],
            "values": observations[city_id],
        }
        city_rows.append(item)
        province_links[code].append(item)

    metrics: list[dict[str, Any]] = []
    for definition in payload["metrics"]:
        metric_id = definition["metric_id"]
        ranked = sorted(
            (
                (city, city["values"].get(metric_id))
                for city in city_rows
                if city["values"].get(metric_id) is not None
            ),
            key=lambda item: item[1],
        )
        values = [value for _, value in ranked]
        middle = median(values) if values else None
        metrics.append({
            **definition,
            "concern_direction": CITY_CONCERN_DIRECTIONS.get(metric_id),
            "available_city_count": len(values),
            "minimum": values[0] if values else None,
            "median": middle,
            "maximum": values[-1] if values else None,
            "lowest": [
                {"city_name_th": city["city_name_th"], "province_name_th": city["province_name_th"], "value": value}
                for city, value in ranked[:2]
            ],
            "highest": [
                {"city_name_th": city["city_name_th"], "province_name_th": city["province_name_th"], "value": value}
                for city, value in reversed(ranked[-2:])
            ],
        })

    concern_signals: list[dict[str, Any]] = []
    metric_by_id = {metric["metric_id"]: metric for metric in metrics}
    for city in city_rows:
        for metric_id, direction in CITY_CONCERN_DIRECTIONS.items():
            value = city["values"].get(metric_id)
            metric = metric_by_id[metric_id]
            middle = metric["median"]
            if value is None or middle in (None, 0):
                continue
            gap = (value - middle) / abs(middle)
            attention = gap > 0.10 if direction == "high" else gap < -0.10
            if attention:
                concern_signals.append({
                    "city_id": city["city_id"],
                    "city_name_th": city["city_name_th"],
                    "province_code": city["province_code"],
                    "metric_id": metric_id,
                    "label_th": metric["label_th"],
                    "value": value,
                    "display_unit": metric.get("display_unit"),
                    "median": middle,
                    "comparison": "above" if gap > 0 else "below",
                    "gap_strength": round(abs(gap), 4),
                })
    concern_signals.sort(key=lambda item: item["gap_strength"], reverse=True)

    groups = []
    for group_id, label in CITY_GROUP_LABELS.items():
        groups.append({
            "group_id": group_id,
            "label_th": label,
            "metrics": [metric for metric in metrics if metric["category_id"] == group_id],
        })

    return {
        "source_id": "f3_city_capital_open_data",
        "name_th": "City Capital Open Data",
        "source_url": payload["source"]["url"],
        "acquisition": "public_inline_data_snapshot",
        "freshness_status": "homepage_byte_identical_2026_08_17_source_as_of_unknown",
        "quality_status": "structured_candidate_needs_review",
        "grain_th": "หนึ่ง observation ต่อเทศบาล × ตัวชี้วัด",
        "readout_th": "เชื่อมเทศบาลกับจังหวัดด้วยทะเบียน อปท. ทางการ และเก็บค่าระดับเมืองแยกจากค่าระดับจังหวัด",
        "coverage": {
            "cities": len(city_rows),
            "linked_cities": len(crosswalk_by_city),
            "linked_provinces": len(province_links),
            "metrics": len(metrics),
            "observations": len(payload["observations"]),
        },
        "groups": groups,
        "cities": city_rows,
        "executive_signals": concern_signals[:24],
        "audit_notes": [
            "current homepage HTML รอบ 2026-08-17 ตรงกับ raw HTML ที่ parser ใช้เมื่อ 2026-08-16 ทุก byte จึงยืนยันว่า 18 เมือง × 39 metrics ยังครบ 702 observations",
            "ค่ากลางคำนวณเฉพาะ 18 เมืองใน snapshot นี้ ไม่ใช่ค่ากลางประเทศไทย",
            "ไม่มีการสร้างคะแนนจัดสรรงบหรือรวมตัวชี้วัดต่างหน่วย",
            "as_of รายตัวชี้วัดไม่ระบุโดยต้นทาง",
        ],
        "evidence": [
            "data/raw/network/f3_city_capital_open_data/20260817T_static_surface_14/manifest.json",
            "data/source_audit/14_f3_city_capital_open_data/evidence/website_completeness_20260817.json",
            "data/raw/external_team_scraper/f3_city_capital_open_data/20260816T_external_team_import_14/manifest.json",
            "data/raw/ckan/f3_city_capital_open_data/20260816T_dla_city_crosswalk_14b/manifest.json",
        ],
    }, dict(province_links)


def build_executive_portfolio(
    ppp: dict[str, Any],
    apptech: dict[str, Any],
    city: dict[str, Any],
    rmutdb: dict[str, Any],
    cultural: dict[str, Any],
    area_based: dict[str, Any],
) -> dict[str, Any]:
    evidence = {
        source_id: read_json(path)
        for source_id, path in AUDIT_EVIDENCE_PATHS.items()
    }
    housing = evidence["f3_housing_portal"]
    housing_spatial = read_json(HOUSING_SPATIAL_SUMMARY_PATH)
    housing_demand = read_json(HOUSING_DEMAND_SUMMARY_PATH)
    tourism = evidence["f3_ruamthiao_lamphun"]
    city_audit = evidence["f3_city_capital_open_data"]

    status_rows = [
        {
            "source_id": "f1_sradss_ppaos",
            "label_th": "SRA DSS",
            "status": "complete",
            "status_th": "Public API ครบ",
            "summary_th": "refresh ปี 2569 ครบ 888 geography requests และ 1,066 extended requests; 18 responses ที่ไม่มีข้อมูลถูกต้นทางระบุเป็น 404",
            "dashboard_tabs": ["ภาพรวม", "คนและพื้นที่", "มิติการพัฒนา", "ที่มา/อัปเดต"],
        },
        {
            "source_id": "f1_pppconnext",
            "label_th": "PPPConnext",
            "status": "partial",
            "status_th": "Aggregate ใช้ได้",
            "summary_th": "ข้อมูลภาพรวมสาธารณะครบ 4 endpoints ส่วน survey detail อยู่หลัง login",
            "dashboard_tabs": ["ภาพรวม", "คนและพื้นที่", "มิติการพัฒนา", "ที่มา/อัปเดต"],
        },
        {
            "source_id": "f2_culturalmap_university",
            "label_th": "Cultural Map",
            "status": "complete",
            "status_th": "ครบตามหน้าเว็บ",
            "summary_th": "public records ครบ 5,619 รายการ พร้อมรายละเอียดผลงานและช่องทางติดต่องาน",
            "dashboard_tabs": ["ภาพรวม", "คนและพื้นที่", "ที่มา/อัปเดต"],
        },
        {
            "source_id": "f2_rmutdb",
            "label_th": "RMUTDB",
            "status": "partial",
            "status_th": "Public export ใช้ได้",
            "summary_th": "e-book 11 ไฟล์ครบ; ฉบับละเอียด 1,006 รายการยังต่างจากยอดหน้า live 9 รายการ และ public API ตอบ 503",
            "dashboard_tabs": ["โครงการและงบ", "ที่มา/อัปเดต"],
        },
        {
            "source_id": "f2_apptech_mtr",
            "label_th": "AppTech MTR",
            "status": "complete",
            "status_th": "ครบตาม API",
            "summary_th": "รายการนวัตกรรม 630 รายการตรงกับยอดรวม upstream",
            "dashboard_tabs": ["ภาพรวม", "โครงการและงบ", "คนและพื้นที่", "ที่มา/อัปเดต"],
        },
        {
            "source_id": "f2_apptech_mru",
            "label_th": "38RAT",
            "status": "partial",
            "status_th": "ใช้ snapshot ล่าสุด",
            "summary_th": "คง snapshot ที่ผ่าน validation 503 รายการ เพราะ current refresh ได้ 192 จาก total 501 ก่อนต้นทาง timeout",
            "dashboard_tabs": ["โครงการและงบ", "คนและพื้นที่", "ที่มา/อัปเดต"],
        },
        {
            "source_id": "f2_learning_area_based",
            "label_th": "Area Based",
            "status": "complete",
            "status_th": "ครบตาม API",
            "summary_th": "1,002 หน่วยธุรกิจและ unique IDs ตรงกับหน้าเว็บทุกแถว",
            "dashboard_tabs": ["ภาพรวม", "โครงการและงบ", "คนและพื้นที่", "ที่มา/อัปเดต"],
        },
        {
            "source_id": "f3_city_capital_open_data",
            "label_th": "City Capital",
            "status": "complete",
            "status_th": "ครบตามหน้าเว็บ",
            "summary_th": "18 เมือง คูณ 39 ตัวชี้วัด ครบ 702 observations และคง null 4 ค่า",
            "dashboard_tabs": ["ภาพรวม", "คนและพื้นที่", "มิติการพัฒนา", "ที่มา/อัปเดต"],
        },
        {
            "source_id": "f3_ruamthiao_lamphun",
            "label_th": "Visit Lamphun",
            "status": "complete",
            "status_th": "ครบตามหน้าเว็บ",
            "summary_th": "เนื้อหาสาธารณะ 157 รายการจาก 5 routes ตรงกับ bundle ปัจจุบัน",
            "dashboard_tabs": ["คนและพื้นที่", "ที่มา/อัปเดต"],
        },
        {
            "source_id": "f3_housing_portal",
            "label_th": "Housing Portal",
            "status": "complete",
            "status_th": "CKAN, Spatial และ Demand ครบ",
            "summary_th": "public CKAN 7,259 rows, spatial 194,532 features และ demand 25,919 rows พร้อมเข้า database; demand ตัด source id และผ่าน contact scan",
            "dashboard_tabs": ["ภาพรวม", "คนและพื้นที่", "มิติการพัฒนา", "ที่มา/อัปเดต"],
        },
    ]
    status_counts = Counter(row["status"] for row in status_rows)
    if status_counts != Counter({"complete": 7, "partial": 3}):
        raise ValueError(f"unexpected audited source status counts: {status_counts}")

    national = ppp["national_summary"]
    assistance = ppp["assistance_summary"]
    apptech_stats = apptech["statistics"]
    area_stats = area_based["statistics"]
    cultural_coverage = cultural["coverage"]
    housing_counts = housing_spatial["counts"]
    if housing_demand.get("record_count") != 25_919:
        raise ValueError("unexpected housing demand record count")
    tourism_datasets = tourism["structured_coverage"]["datasets"]
    city_snapshot = city_audit["structured_snapshot"]

    cultural_labels = {
        "map_inspiration": "จุดวัฒนธรรม",
        "products": "ผลิตภัณฑ์",
        "recreation": "แหล่งนันทนาการ",
        "activities": "กิจกรรม",
        "team": "ข้อมูลทีม",
    }
    business_types = area_based["published_aggregate_dimensions"]["byBusinessType"]

    return {
        "audit": {
            "observed_at": "2026-08-17",
            "source_count": len(status_rows),
            "complete_source_count": status_counts["complete"],
            "partial_source_count": status_counts["partial"],
            "mixed_source_count": status_counts["mixed"],
            "status_rows": status_rows,
            "evidence": [
                provenance_path(path)
                for path in AUDIT_EVIDENCE_PATHS.values()
            ],
        },
        "headline_metrics": [
            {
                "key": "surveyed_households",
                "label_th": "ครัวเรือนในขอบเขตสำรวจ",
                "value": national["households_total"],
                "unit": "ครัวเรือน",
                "note_th": "PPPConnext รวม 20 จังหวัด",
                "source_id": "f1_pppconnext",
            },
            {
                "key": "surveyed_members",
                "label_th": "สมาชิกในครัวเรือน",
                "value": national["members_total"],
                "unit": "คน",
                "note_th": "aggregate จากหน้า public รุ่น 2026",
                "source_id": "f1_pppconnext",
            },
            {
                "key": "assistance_budget",
                "label_th": "งบความช่วยเหลือ",
                "value": assistance["total_budget_baht"],
                "display_value": f"{assistance['total_budget_baht'] / 1_000_000:.1f}",
                "unit": "ล้านบาท",
                "note_th": f"{assistance['total_households']:,} ครัวเรือน",
                "source_id": "f1_pppconnext",
            },
            {
                "key": "apptech_innovations",
                "label_th": "นวัตกรรม AppTech MTR",
                "value": apptech_stats["snapshot_records"],
                "unit": "รายการ",
                "note_th": "ตรงกับยอด upstream ปัจจุบัน",
                "source_id": "f2_apptech_mtr",
            },
            {
                "key": "area_businesses",
                "label_th": "หน่วยธุรกิจ Area Based",
                "value": area_stats["participant_or_business_rows"],
                "unit": "หน่วย",
                "note_th": f"{area_stats['visible_provinces']} จังหวัด",
                "source_id": "f2_learning_area_based",
            },
            {
                "key": "cultural_records",
                "label_th": "ข้อมูลวัฒนธรรม",
                "value": cultural_coverage["total_records"],
                "unit": "รายการ",
                "note_th": "ครบทั้ง 5 datasets สาธารณะ",
                "source_id": "f2_culturalmap_university",
            },
            {
                "key": "housing_points",
                "label_th": "จุดข้อมูลที่อยู่อาศัย",
                "value": housing_counts["housing_points"],
                "unit": "จุด",
                "note_th": "169 แขวงในกรุงเทพมหานคร",
                "source_id": "f3_housing_portal",
            },
            {
                "key": "housing_demand_responses",
                "label_th": "คำตอบ Housing demand",
                "value": housing_demand["record_count"],
                "unit": "คำตอบ",
                "note_th": "ครบ 77 จังหวัด; ไม่ใช่จำนวนประชากร",
                "source_id": "f3_housing_portal",
            },
            {
                "key": "city_capital_cities",
                "label_th": "เมืองที่มีตัวชี้วัดทุนเมือง",
                "value": city["coverage"]["cities"],
                "unit": "เมือง",
                "note_th": f"{city['coverage']['metrics']} ตัวชี้วัดต่อเมือง",
                "source_id": "f3_city_capital_open_data",
            },
        ],
        "charts": {
            "livelihood_capital": {
                "title_th": "ทุนดำรงชีพเฉลี่ย",
                "unit_th": "คะแนนตามนิยามต้นทาง",
                "items": [
                    {"label_th": item["label_th"], "value": item["average"]}
                    for item in ppp["capital_dimensions"]
                ],
            },
            "area_business_types": {
                "title_th": "ประเภทธุรกิจใน Area Based",
                "unit_th": "หน่วยธุรกิจ",
                "items": [
                    {"label_th": label, "value": value}
                    for label, value in sorted(
                        business_types.items(), key=lambda item: item[1], reverse=True
                    )
                ],
            },
            "cultural_records": {
                "title_th": "องค์ประกอบข้อมูลวัฒนธรรม",
                "unit_th": "public records",
                "items": [
                    {
                        "label_th": cultural_labels[item["dataset_id"]],
                        "value": item["record_count"],
                    }
                    for item in cultural_coverage["datasets"]
                ],
            },
            "housing_spatial": {
                "title_th": "ขนาดข้อมูลแผนที่ที่อยู่อาศัย",
                "unit_th": "spatial features",
                "items": [
                    {"label_th": "พื้นที่เสี่ยงน้ำท่วม", "value": housing_counts["flood_grid"]},
                    {"label_th": "จุดที่อยู่อาศัย", "value": housing_counts["housing_points"]},
                    {"label_th": "กริดการเข้าถึงบริการ", "value": housing_counts["accessibility_grid"]},
                    {"label_th": "ขอบเขตแขวง", "value": housing_counts["subdistrict_boundaries"]},
                ],
            },
            "housing_demand": {
                "title_th": "ความต้องการที่อยู่อาศัยในอนาคต",
                "unit_th": "คำตอบแบบสำรวจ",
                "items": [
                    {"label_th": item["label_th"], "value": item["value"]}
                    for item in housing_demand["national"]["single_choice_distributions"]
                    ["future_housing_demand"]["items"]
                ],
            },
            "tourism_inventory": {
                "title_th": "ข้อมูลท่องเที่ยวลำพูน",
                "unit_th": "รายการสาธารณะ",
                "items": [
                    {"label_th": "สถานที่", "value": tourism_datasets["tourism_venues"]},
                    {"label_th": "รายการแนะนำ", "value": tourism_datasets["recommendations"]},
                    {"label_th": "บริการเดินทาง", "value": tourism_datasets["transport_services"]},
                    {"label_th": "สถานีท่องเที่ยว", "value": tourism_datasets["tourism_stations"]},
                    {"label_th": "กลุ่มโคม", "value": tourism_datasets["lantern_groups"]},
                ],
            },
            "city_data_completeness": {
                "title_th": "ความครบของข้อมูลทุนเมือง",
                "unit_th": "observations",
                "items": [
                    {"label_th": "ค่าตัวเลข", "value": city_snapshot["numeric_values"]},
                    {"label_th": "คงเป็น null ตามต้นทาง", "value": city_snapshot["null_values"]},
                ],
                "total": city_snapshot["observations"],
            },
        },
        "source_notes": {
            "housing_public_rows": housing["railway_ckan_projection"]["value_approved_row_count"],
            "housing_spatial_features": housing_spatial["total_spatial_features"],
            "housing_demand_rows_published": housing_demand["record_count"],
            "housing_unassigned_rows": housing["railway_ckan_projection"]["unassigned_rows"],
            "tourism_public_items": tourism["structured_coverage"]["all_content_item_count"],
            "rmutdb_detailed_records": rmutdb["statistics"]["detailed_records"],
            "rmutdb_live_gap": evidence["f2_rmutdb"]["dashboard_comparison"]["unresolved_difference"],
        },
    }


def build(*, generated_at: str | None = None) -> None:
    province_reference = read_json(APPTECH_RAW_ROOT / "responses/innovator_map.json")["data"]["mapData"]
    code_by_name = {
        normalize_province(row["province"]): str(row["code"]).zfill(2)
        for row in province_reference
    }
    ppp, ppp_links = build_ppp(code_by_name)
    apptech, apptech_links = build_apptech()
    city, city_links = build_city(code_by_name)
    rmutdb = build_rmutdb()
    cultural = build_cultural_supporting_coverage()
    learning_payload = read_json(LEARNING_PATH)
    learning_source = learning_payload["source"]
    learning = {
        "source_id": learning_source["source_id"],
        "name_th": learning_source["name_th"],
        "source_url": learning_source["url"],
        "endpoint_url": learning_source["endpoint_url"],
        "acquisition": "public_aggregate_api_snapshot",
        "freshness_status": "source_as_of_unknown",
        "quality_status": learning_payload["quality"]["status"],
        "grain_th": "ตาราง aggregate ระดับจังหวัดและภาพรวมกลุ่มจากผู้เข้าร่วมโครงการที่ต้นทางเลือก",
        "readout_th": "ผูกเฉพาะชื่อจังหวัดที่ตรงกับขอบเขตทางการ และเก็บตารางที่ไม่ใช่จังหวัดแยกโดยไม่รวมหน่วย",
        "scope_warning_th": learning_payload["quality"]["scope_warning_th"],
        "coverage": learning_payload["coverage"],
        "provinces": learning_payload["province_rows"],
        "unmatched_province_rows": learning_payload["unmatched_province_rows"],
        "non_province_tables": learning_payload["non_province_tables"],
        "non_province_impact": learning_payload["non_province_impact"],
        "evidence": learning_payload["evidence"],
    }
    learning_links = learning_payload["province_links"]
    area_rows = list(csv_rows(BASE_RUN / "11_f2_learning_area_based/data.csv"))
    area_payload = read_json(AREA_BASED_RESPONSE_PATH)
    area_stats = area_payload["stats"]
    area_current = read_json(AREA_BASED_CURRENT_OBSERVATION)
    area_missing_province_count = sum(
        not clean(row.get("source_fields__province")) for row in area_rows
    )
    area_based = {
        "source_id": "f2_learning_area_based",
        "name_th": "PMUA Area Based",
        "source_url": "https://lesuper.app/opendata/pmua/area-based",
        "endpoint_url": "https://lesuper.app/api/opendata/pmua/area-based",
        "acquisition": "public_api_with_validated_snapshot_fallback",
        "freshness_status": "byte_identical_to_2026_08_03_snapshot_when_checked_2026_08_17",
        "quality_status": "structural_candidate_needs_review",
        "grain_th": "data rows คือหน่วย/ผู้ประกอบการเข้าร่วม; aggregate stats เป็นคนละ grain; ไม่ใช่จำนวนโครงการ",
        "readout_th": "ตัวเลขและกราฟทุกชุดบนหน้าเว็บมาจาก stats envelope และ reconcile กับ 1,002 rows; business type มีเฉพาะ aggregate ไม่มี field ราย row",
        "statistics": {
            "participant_or_business_rows": len(area_rows),
            "unique_ids": area_current["current"]["unique_id_count"],
            "visible_regions": len(area_stats["byRegion"]),
            "visible_provinces": len(area_stats["byProvince"]),
            "visible_districts": len(area_stats["byDistrict"]),
            "visible_subdistricts": len(area_stats["bySubDistrict"]),
            "missing_province_rows": area_missing_province_count,
            "row_updated_at_watermark": area_current["current"]["max_updatedAt"],
        },
        "published_aggregate_dimensions": area_stats,
        "audit_notes": [
            "หน้าเว็บรอบ 2026-08-17 แสดง 6 ภูมิภาค, 55 จังหวัด, 256 อำเภอ, 533 ตำบล และ 1,002 ธุรกิจ ตรงกับ API",
            "current API body SHA-256 ตรงกับ snapshot 2026-08-03 ทุก byte; row count 1,002, unique IDs 1,002 และ schema ไม่เปลี่ยน",
            "byProvince/byDistrict/bySubDistrict รวมได้ 996/988/985 เพราะมีค่า geography ว่าง 6/14/17 rows; ไม่เติมค่าหรือแปลงเป็นศูนย์",
            "กลุ่ม projectName+fiscalYear+researchUnit เป็น provisional grouping เท่านั้นและห้ามเรียก 1,002 rows ว่าจำนวนโครงการ",
        ],
        "evidence": [
            "data/raw/firecrawl_scrape/f2_learning_area_based/20260817T_page_scrape_11b/manifest.json",
            "data/raw/network/f2_learning_area_based/20260817T_freshness_check_11/manifest.json",
            "data/source_audit/11_f2_learning_area_based/evidence/website_completeness_20260817.json",
            "data/staged/f2_learning_area_based/20260803T_pmua_silver_01/manifest.json",
        ],
    }
    executive_portfolio = build_executive_portfolio(
        ppp, apptech, city, rmutdb, cultural, area_based
    )
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "publication_status": "public_candidate_projection",
        "warning_th": "เปรียบเทียบตาม grain และหน่วยของต้นทางเท่านั้น ไม่ใช่คะแนนจัดสรรงบ",
        "executive_portfolio": executive_portfolio,
        "audit_summary": {
            "geo_linkable_source_ids": [
                "f1_pppconnext",
                "f2_apptech_mtr",
                "f3_city_capital_open_data",
            ],
            "supplemental_geo_linkable_source_ids": ["f2_learning_dashboard"],
            "all_geo_linkable_source_ids": [
                "f1_pppconnext",
                "f2_apptech_mtr",
                "f3_city_capital_open_data",
                "f2_learning_dashboard",
            ],
            "non_geo_source_ids": ["f2_rmutdb"],
            "aggregate_only_projection_source_ids": [],
            "join_policy": "authoritative_or_source_confirmed_geography_only",
            "unmapped_public_records": {
                "f2_learning_area_based": {
                    "records": area_missing_province_count,
                    "reason": "source_province_missing",
                }
            },
        },
        "sources": {
            "f1_pppconnext": ppp,
            "f2_apptech_mtr": apptech,
            "f3_city_capital_open_data": city,
            "f2_rmutdb": rmutdb,
            "f2_culturalmap_university": cultural,
            "f2_learning_dashboard": learning,
            "f2_learning_area_based": area_based,
        },
        "province_links": {
            code: {
                "f1_pppconnext": ppp_links.get(code, []),
                "f2_apptech_mtr": apptech_links.get(code),
                "f3_city_capital_open_data": city_links.get(code, []),
                "f2_learning_dashboard": learning_links.get(code),
            }
            for code in sorted(code_by_name.values())
        },
        "methodology": {
            "pppconnext": "source province codes from the observed PPPConnext 2026 public aggregate API, checked against the canonical 77-province reference",
            "apptech_mtr": "source API province code and label; aggregate grains kept separate",
            "city_capital": "exact municipality type+name match against official DLA registry",
            "rmutdb": "not joined; owner affiliation is not innovation location",
            "culturalmap": "map records retain their own province points; supporting work records retain public attribution and contacts without an unverified province join",
            "learning_dashboard": "exact Thai province name against the official 77-province boundary; non-province tables remain separate",
        },
    }
    write_json(OUTPUT_PATH, payload)
    inputs = [
        PPP_PATH,
        WORKSPACE_ROOT / "data/staged/f1_pppconnext/20260817T_public_api_silver_02/manifest.json",
        WORKSPACE_ROOT / "data/raw/network/f1_pppconnext/20260817T_public_api_fetch_02/manifest.json",
        WORKSPACE_ROOT / "data/raw/network/f1_pppconnext/20260817T_public_api_fetch_02/network_observation.json",
        APPTECH_RECORD_PATH,
        WORKSPACE_ROOT / "data/staged/f2_apptech_mtr/20260817T_public_api_silver_07/manifest.json",
        APPTECH_CURRENT_ROOT / "manifest.json",
        APPTECH_CURRENT_ROOT / "profiles/custom_statistics.profile.json",
        WORKSPACE_ROOT / "data/source_audit/07_f2_apptech_mtr/evidence/website_completeness_20260817.json",
        APPTECH_RAW_ROOT / "responses/institute_map.json",
        APPTECH_RAW_ROOT / "responses/innovator_map.json",
        APPTECH_RAW_ROOT / "responses/interaction_map.json",
        APPTECH_RAW_ROOT / "responses/statistics.json",
        BASE_RUN / "06_f2_rmutdb/data.csv",
        CITY_PATH,
        CITY_CROSSWALK_PATH,
        CITY_CURRENT_SURFACE_MANIFEST,
        LEARNING_PATH,
        LEARNING_MANIFEST_PATH,
        HOUSING_SPATIAL_SUMMARY_PATH,
        HOUSING_DEMAND_SUMMARY_PATH,
        AREA_BASED_RESPONSE_PATH,
        AREA_BASED_CURRENT_OBSERVATION,
        *[CULTURAL_ROOT / values[0] for values in CULTURAL_DATASETS.values()],
        *AUDIT_EVIDENCE_PATHS.values(),
    ]
    manifest = {
        "manifest_version": "1.0.0",
        "generated_at": generated_at,
        "inputs": [input_entry(path) for path in inputs],
        "output": input_entry(OUTPUT_PATH),
    }
    write_json(MANIFEST_PATH, manifest)
    print(json.dumps({
        "status": "ok",
        "output": OUTPUT_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "ppp_linked_provinces": ppp["coverage"]["linked_provinces"],
        "apptech_province_rows": len(apptech_links),
        "city_linked": city["coverage"]["linked_cities"],
        "learning_linked_provinces": learning["coverage"]["linked_provinces"],
        "area_based_unmapped_records": area_missing_province_count,
        "cultural_supporting_records": cultural["coverage"]["supporting_records"],
        "rmutdb_geo_joined": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    build()
