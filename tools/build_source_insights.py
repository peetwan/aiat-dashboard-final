from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
BASE_RUN = WORKSPACE_ROOT / "data/qa/web_profile_team_drive_simple/20260814T_team_drive_simple_final"
PPP_PATH = (
    WORKSPACE_ROOT
    / "data/staged/f1_pppconnext/20260804T_pppconnext_bi_silver_01/silver/bi_aggregate_records.jsonl"
)
APPTECH_RAW_ROOT = (
    WORKSPACE_ROOT / "data/raw/network/f2_apptech_mtr/20260816T_geo_link_audit_07"
)
CITY_PATH = (
    WORKSPACE_ROOT
    / "data/raw/external_team_scraper/f3_city_capital_open_data/20260816T_external_team_import_14/output/latest.json"
)
CITY_CROSSWALK_PATH = (
    WORKSPACE_ROOT
    / "data/raw/ckan/f3_city_capital_open_data/20260816T_dla_city_crosswalk_14b/matched_cities.json"
)
OUTPUT_PATH = PROJECT_ROOT / "data/public/source_insights.json"
MANIFEST_PATH = PROJECT_ROOT / "data/public/source_insights_manifest.json"
LEARNING_PATH = PROJECT_ROOT / "data/public/learning_dashboard.json"
LEARNING_MANIFEST_PATH = PROJECT_ROOT / "data/public/learning_dashboard_manifest.json"
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


def input_entry(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(WORKSPACE_ROOT).as_posix(),
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
    normalized = [row["normalized_fields"] for row in rows]
    level_counts = Counter(row.get("geography_level") for row in normalized)
    widget_counts = Counter(row.get("bi_widget") for row in normalized)
    metric_counts = Counter(clean(row.get("metric_name")) for row in normalized)
    province_links: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmatched: set[str] = set()
    for row, source in zip(normalized, rows, strict=True):
        if row.get("geography_level") != "province":
            continue
        province_name = normalize_province(row.get("geography_name"))
        code = code_by_name.get(province_name)
        if not code:
            if province_name:
                unmatched.add(province_name)
            continue
        province_links[code].append({
            "metric_name": clean(row.get("metric_name")),
            "value": safe_float(row.get("metric_value")),
            "unit": clean(row.get("metric_unit")) or "unknown",
            "widget": clean(row.get("bi_widget")),
            "source_url": source.get("provenance", {}).get("source_url"),
            "endpoint_url": source.get("provenance", {}).get("endpoint_url"),
            "quality_status": source.get("quality", {}).get("quality_status"),
        })

    name_by_code = {code: name for name, code in code_by_name.items()}
    return {
        "source_id": "f1_pppconnext",
        "name_th": "PPPConnext",
        "source_url": "http://www.ppaos.com/ppaos/bi/PPPCONNEXT/",
        "acquisition": "public_aggregate_json_snapshot",
        "freshness_status": "unknown",
        "quality_status": "parsed_aggregate_candidate",
        "grain_th": "หนึ่งแถวต่อพื้นที่ × ตัวชี้วัดในกราฟต้นทาง",
        "readout_th": "ชุด BI ที่คัดแล้วมีระดับภาค จังหวัด และอำเภอ จึงใช้ผูกพื้นที่ได้โดยไม่แตะข้อมูลครัวเรือนรายบุคคล",
        "coverage": {
            "aggregate_rows": len(rows),
            "province_rows": level_counts.get("province", 0),
            "linked_provinces": len(province_links),
            "unmatched_province_names": sorted(unmatched),
        },
        "geography_levels": [
            {"key": key, "value": level_counts[key]}
            for key in ("region", "province", "district")
        ],
        "widgets": [
            {"key": key, "value": value}
            for key, value in widget_counts.most_common()
        ],
        "metrics": [
            {"label_th": key, "record_count": value}
            for key, value in metric_counts.most_common()
            if key
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
            "data/staged/f1_pppconnext/20260804T_pppconnext_bi_silver_01/manifest.json",
            "data/raw/network/f1_pppconnext/20260804T_pppconnext_bi_probe_01/observation.json",
        ],
    }, dict(province_links)


def build_apptech() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    record_path = BASE_RUN / "07_f2_apptech_mtr/data.csv"
    records = list(csv_rows(record_path))
    institute_map_path = APPTECH_RAW_ROOT / "responses/institute_map.json"
    innovator_map_path = APPTECH_RAW_ROOT / "responses/innovator_map.json"
    interaction_map_path = APPTECH_RAW_ROOT / "responses/interaction_map.json"
    statistics_path = APPTECH_RAW_ROOT / "responses/statistics.json"
    institute_rows = read_json(institute_map_path)["data"]["mapData"]
    innovator_rows = read_json(innovator_map_path)["data"]["mapData"]
    interaction_payload = read_json(interaction_map_path)["data"]
    interaction_rows = (
        interaction_payload.get("mapData", interaction_payload)
        if isinstance(interaction_payload, dict)
        else interaction_payload
    )
    stats = read_json(statistics_path)["data"]
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
        "source_url": "https://rinmp.com/",
        "acquisition": "public_api",
        "freshness_status": "observed_2026_08_16",
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
            "API สถิติสดรายงานผลงาน 626 รายการ ขณะที่ snapshot รายการมี 621 รายการ จึงแยกเวลาสังเกตและไม่รวมยอด",
            "institute map ตอบ 77 จังหวัดแต่ค่าเป็นศูนย์ทั้งหมด จึงไม่ใช้วิเคราะห์",
            "ต้นทางไม่ส่ง CORS header; dashboard เรียกผ่าน serving API ของโครงการ",
        ],
        "evidence": [
            "data/raw/network/f2_apptech_mtr/20260816T_geo_link_audit_07/manifest.json",
            "data/raw/network/f2_apptech_mtr/20260816T_geo_link_audit_07/observation.json",
        ],
    }, province_links


def build_rmutdb() -> dict[str, Any]:
    rows = list(csv_rows(BASE_RUN / "06_f2_rmutdb/data.csv"))
    detailed = [row for row in rows if row.get("record_type") == "rmutdb_ebook_innovation_detail"]
    summaries = [row for row in rows if row.get("record_type") != "rmutdb_ebook_innovation_detail"]
    trl_counter: Counter[str] = Counter()
    for row in detailed:
        value = clean(row.get("normalized_fields__trl_level"))
        match = re.search(r"([2-9])", value or "")
        if match:
            trl_counter[match.group(1)] += 1
    return {
        "source_id": "f2_rmutdb",
        "name_th": "RMUTDB Innovation",
        "source_url": "https://rmutdb.net/",
        "acquisition": "public_pdf_snapshot",
        "freshness_status": "ebook_last_modified_2023_03_05",
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
        ],
        "evidence": [
            "data/raw/export/f2_rmutdb/20260805T_ebook_export_01/manifest.json",
            "data/staged/silver/f2_rmutdb/20260805T_ebook_silver_01/summary.json",
        ],
    }


def build_cultural_supporting_coverage() -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
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
        "acquisition": "external_team_public_snapshot",
        "freshness_status": "source_as_of_unknown",
        "quality_status": "candidate_needs_review",
        "grain_th": "นับแยกตาม dataset ต้นทาง; 361 supporting records ไม่ถูกบวกเป็นจุดแผนที่หรือผูกจังหวัด",
        "readout_th": "เปิดเผยเฉพาะยอดรวมของ Products, Activities, Re-Creation และ Team; ไม่ส่ง contact หรือแถวข้อมูลสนับสนุน",
        "coverage": {
            "map_records": 5_258,
            "supporting_records": supporting_records,
            "total_records": total_records,
            "datasets": datasets,
        },
        "privacy_projection": {
            "supporting_records_exposed": False,
            "contact_fields_exposed": False,
            "aggregate_counts_only": True,
        },
        "evidence": [
            f"data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01/03_f2_culturalmap_university/data/{filename}"
            for filename, _, _ in CULTURAL_DATASETS.values()
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
        "freshness_status": "source_as_of_unknown",
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
            "ค่ากลางคำนวณเฉพาะ 18 เมืองใน snapshot นี้ ไม่ใช่ค่ากลางประเทศไทย",
            "ไม่มีการสร้างคะแนนจัดสรรงบหรือรวมตัวชี้วัดต่างหน่วย",
            "as_of รายตัวชี้วัดไม่ระบุโดยต้นทาง",
        ],
        "evidence": [
            "data/raw/external_team_scraper/f3_city_capital_open_data/20260816T_external_team_import_14/manifest.json",
            "data/raw/ckan/f3_city_capital_open_data/20260816T_dla_city_crosswalk_14b/manifest.json",
        ],
    }, dict(province_links)


def build() -> None:
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
    area_missing_province_count = sum(
        not clean(row.get("source_fields__province")) for row in area_rows
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "publication_status": "public_candidate_projection",
        "warning_th": "เปรียบเทียบตาม grain และหน่วยของต้นทางเท่านั้น ไม่ใช่คะแนนจัดสรรงบ",
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
            "aggregate_only_projection_source_ids": ["f2_culturalmap_university"],
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
            "pppconnext": "exact Thai province-name crosswalk from curated aggregate BI rows",
            "apptech_mtr": "source API province code and label; aggregate grains kept separate",
            "city_capital": "exact municipality type+name match against official DLA registry",
            "rmutdb": "not joined; owner affiliation is not innovation location",
            "culturalmap": "map records retain their own province points; four supporting datasets are aggregate counts only and expose no contact fields",
            "learning_dashboard": "exact Thai province name against the official 77-province boundary; non-province tables remain separate",
        },
    }
    write_json(OUTPUT_PATH, payload)
    inputs = [
        PPP_PATH,
        BASE_RUN / "07_f2_apptech_mtr/data.csv",
        APPTECH_RAW_ROOT / "responses/institute_map.json",
        APPTECH_RAW_ROOT / "responses/innovator_map.json",
        APPTECH_RAW_ROOT / "responses/interaction_map.json",
        APPTECH_RAW_ROOT / "responses/statistics.json",
        BASE_RUN / "06_f2_rmutdb/data.csv",
        CITY_PATH,
        CITY_CROSSWALK_PATH,
        LEARNING_PATH,
        LEARNING_MANIFEST_PATH,
        *[CULTURAL_ROOT / values[0] for values in CULTURAL_DATASETS.values()],
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
