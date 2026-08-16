from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
BASE_RUN = WORKSPACE_ROOT / "data/qa/web_profile_team_drive_simple/20260814T_team_drive_simple_final"
MERGE_RUN = WORKSPACE_ROOT / "data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01"
OUTPUT_DIR = PROJECT_ROOT / "data/public"
LEARNING_PATH = OUTPUT_DIR / "learning_dashboard.json"
LEARNING_MANIFEST_PATH = OUTPUT_DIR / "learning_dashboard_manifest.json"

BOUNDARY_LAYER = (
    "https://gis-portal.disaster.go.th/arcgis/rest/services/MapDX/"
    "DPM_TH_Boundary/FeatureServer/1/query"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def csv_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def safe_float(value: Any) -> float | None:
    if value in (None, "", "\\N"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_boundaries(refresh: bool) -> dict[str, Any]:
    cached = OUTPUT_DIR / "thailand_provinces.geojson"
    if cached.exists() and not refresh:
        return read_json(cached)

    query = urllib.parse.urlencode(
        {
            "where": "1=1",
            "outFields": "PROV_CODE,PROV_NAM_T,PROV_NAM_E,REGION_6,Centroid_x,Centroid_y",
            "returnGeometry": "true",
            "outSR": "4326",
            "geometryPrecision": "5",
            "maxAllowableOffset": "0.004",
            "f": "geojson",
        }
    )
    request = urllib.request.Request(
        f"{BOUNDARY_LAYER}?{query}",
        headers={"User-Agent": "AIAT-Public-Data-Builder/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))

    features = payload.get("features", [])
    if len(features) != 77:
        raise RuntimeError(f"Expected 77 province boundaries, received {len(features)}")
    payload["source"] = BOUNDARY_LAYER.rsplit("/query", 1)[0]
    payload["license_note_th"] = "ขอบเขตจังหวัดจาก ArcGIS REST ของกรมป้องกันและบรรเทาสาธารณภัย"
    return payload


def canonical_code(value: Any) -> str | None:
    if value in (None, "", "\\N", "_unknown", "_multi_province"):
        return None
    text = str(value).strip()
    if text.isdigit():
        return text.zfill(2)[:2]
    return None


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).replace("จังหวัด", "")


def resolve_housing_code(
    row: dict[str, Any], code_by_name: dict[str, str]
) -> str | None:
    for value in (
        row.get("source_fields__cwt_id"),
        row.get("source_fields__province_id"),
        row.get("partition_key"),
    ):
        code = canonical_code(value)
        if code:
            return code
    for value in (
        row.get("source_fields__cwt_dc"),
        row.get("source_fields__cwt_name"),
        row.get("source_fields__province_name"),
        row.get("source_fields__province_name_th"),
        row.get("source_fields__area_name"),
        row.get("partition_key"),
    ):
        code = code_by_name.get(normalize_text(value))
        if code:
            return code
    return None


def housing_unmapped_reason(
    row: dict[str, Any], resolved_code: str | None, valid_codes: set[str]
) -> str:
    if resolved_code is not None and resolved_code not in valid_codes:
        return "source_province_code_not_in_official_crosswalk"
    if row.get("partition_type") == "area_name_noncanonical":
        return "source_geography_not_at_province_grain"
    if row.get("partition_key") in (None, "", "\\N", "_unmapped", "_unknown"):
        return "source_geography_missing"
    return "source_geography_not_in_exact_crosswalk"


def build_public_data(refresh_boundaries: bool) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog_path = PROJECT_ROOT / "config/source_catalog.json"
    catalog = read_json(catalog_path)
    restricted_source_ids = sorted(
        source["source_id"]
        for source in catalog["sources"]
        if source.get("cloud_policy") == "restricted_local_only"
    )
    restricted_source_count = len(restricted_source_ids)
    public_sources = [
        source
        for source in catalog["sources"]
        if source.get("production_values_allowed")
        and source.get("cloud_policy") != "restricted_local_only"
    ]
    learning_payload = read_json(LEARNING_PATH)
    learning_source = learning_payload["source"]
    if not any(source["source_id"] == learning_source["source_id"] for source in public_sources):
        public_sources.append(learning_source)
    public_sources.sort(key=lambda source: source["ordinal"])
    if len(public_sources) != 11:
        raise RuntimeError(f"Expected 11 approved public sources, received {len(public_sources)}")

    boundaries = fetch_boundaries(refresh_boundaries)
    boundary_by_code: dict[str, dict[str, Any]] = {}
    code_by_th: dict[str, str] = {}
    for feature in boundaries["features"]:
        props = feature.setdefault("properties", {})
        code = str(props.get("PROV_CODE", "")).zfill(2)
        if not code:
            continue
        boundary_by_code[code] = feature
        code_by_th[normalize_text(props.get("PROV_NAM_T"))] = code

    profiles: dict[str, dict[str, Any]] = {}
    for code, feature in boundary_by_code.items():
        props = feature["properties"]
        centroid_x = safe_float(props.get("Centroid_x"))
        centroid_y = safe_float(props.get("Centroid_y"))
        profiles[code] = {
            "province_code": code,
            "province_name_th": props.get("PROV_NAM_T") or "ไม่ระบุ",
            "province_name_en": props.get("PROV_NAM_E") or "Not specified",
            "region": props.get("REGION_6") or "ไม่ระบุ",
            "centroid": [centroid_x, centroid_y] if centroid_x is not None and centroid_y is not None else None,
            "sra_overall_score": None,
            "sra_dimension_scores": {},
            "area_based_participant_records": 0,
            "innovation_records": 0,
            "cultural_records": 0,
            "housing_observations": 0,
            "pppconnext_aggregate_rows": 0,
            "learning_dashboard_business_records": 0,
            "apptech_registered_users": 0,
            "apptech_interactions": 0,
            "city_capital_cities": 0,
            "evidence_sources": [],
            "evidence_source_count": 0,
            "quality_status": "candidate_needs_review",
        }

    input_paths: list[Path] = [catalog_path, LEARNING_PATH, LEARNING_MANIFEST_PATH]

    # SRA-DSS: preserve the source's provisional score and unit without interpreting it.
    sra_path = BASE_RUN / "01_f1_sradss_ppaos/data/f1_sradss_ppaos_current_year_2569_indicator_rows.csv"
    input_paths.append(sra_path)
    for row in csv_rows(sra_path):
        code = canonical_code(row.get("province_code"))
        value = safe_float(row.get("value"))
        metric = row.get("metric_key")
        if code not in profiles or value is None or not metric:
            continue
        if metric == "overall":
            profiles[code]["sra_overall_score"] = value
        elif metric in {"financial", "human", "natural_res", "physical", "social"}:
            profiles[code]["sra_dimension_scores"][metric] = value

    # Area-based: one row is one participating unit, explicitly not the area's population.
    area_path = BASE_RUN / "11_f2_learning_area_based/data.csv"
    input_paths.append(area_path)
    area_unmapped_reason_counts: dict[str, int] = defaultdict(int)
    for row in csv_rows(area_path):
        province_name = normalize_text(row.get("source_fields__province"))
        code = code_by_th.get(province_name) or canonical_code(row.get("partition_key"))
        if code in profiles:
            profiles[code]["area_based_participant_records"] += 1
        elif not province_name:
            area_unmapped_reason_counts["source_province_missing"] += 1
        else:
            area_unmapped_reason_counts["province_name_not_in_crosswalk"] += 1

    # AppTech MRU: count a record once per distinct province listed in its public areas field.
    innovation_path = BASE_RUN / "08_f2_apptech_mru/data/f2_apptech_mru_source_apptech_mru_public_innovation.csv"
    input_paths.append(innovation_path)
    for row in csv_rows(innovation_path):
        codes: set[str] = set()
        partition_code = canonical_code(row.get("partition_key"))
        if partition_code:
            codes.add(partition_code)
        try:
            areas = json.loads(row.get("normalized_fields__areas") or "[]")
        except json.JSONDecodeError:
            areas = []
        for area in areas:
            code = code_by_th.get(normalize_text(area.get("province")))
            if code:
                codes.add(code)
        for code in codes:
            if code in profiles:
                profiles[code]["innovation_records"] += 1

    # Cultural Map: publish the validated public point projection, not its large raw payload.
    cultural_path = MERGE_RUN / "03_f2_culturalmap_university/data/map_inspiration.json"
    input_paths.append(cultural_path)
    cultural_root = read_json(cultural_path)
    cultural_features: list[dict[str, Any]] = []
    for row in cultural_root["data"]["records"]:
        data = row.get("data") or {}
        location = data.get("location") or {}
        coordinates = location.get("coordinates") or {}
        latitude = safe_float(coordinates.get("latitude"))
        longitude = safe_float(coordinates.get("longitude"))
        province = (location.get("administrative") or {}).get("province") or {}
        code = canonical_code(province.get("code"))
        if latitude is None or longitude is None or code not in profiles:
            continue
        classification = data.get("classification") or {}
        category = classification.get("primary_category") or {}
        names = data.get("names") or {}
        warnings = row.get("validation_warnings") or []
        profiles[code]["cultural_records"] += 1
        cultural_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                "properties": {
                    "external_id": row.get("external_id"),
                    "title": names.get("en") or row.get("external_id") or "Cultural record",
                    "category_code": category.get("code") or "unknown",
                    "category": category.get("name_en") or "Not specified",
                    "cultural_type": (classification.get("cultural_type") or {}).get("name_en") or "Not specified",
                    "province_code": code,
                    "province_name_th": profiles[code]["province_name_th"],
                    "province_name_en": profiles[code]["province_name_en"],
                    "source_url": row.get("source_url"),
                    "quality_status": "needs_review" if warnings else "candidate",
                },
            }
        )

    # Housing portal: technical observation count by source province id; values remain available upstream.
    housing_dir = BASE_RUN / "23_f3_housing_portal/data"
    housing_unmapped_reason_counts: dict[str, int] = defaultdict(int)
    for housing_path in sorted(housing_dir.glob("*.csv")):
        input_paths.append(housing_path)
        for row in csv_rows(housing_path):
            code = resolve_housing_code(row, code_by_th)
            if code in profiles:
                profiles[code]["housing_observations"] += 1
            else:
                reason = housing_unmapped_reason(row, code, set(profiles))
                housing_unmapped_reason_counts[reason] += 1

    # Audited source-level pipeline: retain the original grain for each geography link.
    source_insights_path = OUTPUT_DIR / "source_insights.json"
    input_paths.append(source_insights_path)
    source_insights = read_json(source_insights_path)
    for code, links in source_insights["province_links"].items():
        if code not in profiles:
            continue
        profiles[code]["pppconnext_aggregate_rows"] = len(links.get("f1_pppconnext") or [])
        learning = links.get("f2_learning_dashboard") or {}
        profiles[code]["learning_dashboard_business_records"] = learning.get("value", 0)
        apptech = links.get("f2_apptech_mtr") or {}
        profiles[code]["apptech_registered_users"] = apptech.get("registered_users", 0)
        profiles[code]["apptech_interactions"] = apptech.get("interactions", 0)
        profiles[code]["city_capital_cities"] = len(links.get("f3_city_capital_open_data") or [])

    metric_sources = {
        "sra_overall_score": "f1_sradss_ppaos",
        "area_based_participant_records": "f2_learning_area_based",
        "innovation_records": "f2_apptech_mru",
        "cultural_records": "f2_culturalmap_university",
        "housing_observations": "f3_housing_portal",
        "pppconnext_aggregate_rows": "f1_pppconnext",
        "learning_dashboard_business_records": "f2_learning_dashboard",
        "city_capital_cities": "f3_city_capital_open_data",
    }
    numeric_metrics = list(metric_sources)
    metric_max = {
        metric: max((profile[metric] or 0) for profile in profiles.values()) or 1
        for metric in numeric_metrics
    }
    for code, profile in profiles.items():
        sources = [
            source_id
            for metric, source_id in metric_sources.items()
            if profile[metric] not in (None, 0)
        ]
        # AppTech's public province API explicitly returns all 77 provinces, including zero activity.
        sources.append("f2_apptech_mtr")
        profile["evidence_sources"] = sources
        profile["evidence_source_count"] = len(sources)
        profile["visual_index"] = {
            metric: round((profile[metric] or 0) / metric_max[metric], 6)
            for metric in numeric_metrics
        }
        profile["visual_index"]["evidence_source_count"] = round(
            len(sources) / (len(metric_sources) + 1), 6
        )

        props = boundary_by_code[code]["properties"]
        props.update(
            {
                "province_code": code,
                "province_name_th": profile["province_name_th"],
                "province_name_en": profile["province_name_en"],
                "evidence_source_count": len(sources),
                "sra_overall_score": profile["sra_overall_score"] or 0,
                "area_based_participant_records": profile["area_based_participant_records"],
                "innovation_records": profile["innovation_records"],
                "cultural_records": profile["cultural_records"],
                "housing_observations": profile["housing_observations"],
                "pppconnext_aggregate_rows": profile["pppconnext_aggregate_rows"],
                "learning_dashboard_business_records": profile["learning_dashboard_business_records"],
                "apptech_registered_users": profile["apptech_registered_users"],
                "apptech_interactions": profile["apptech_interactions"],
                "city_capital_cities": profile["city_capital_cities"],
                "idx_evidence_source_count": profile["visual_index"]["evidence_source_count"],
                **{f"idx_{metric}": profile["visual_index"][metric] for metric in numeric_metrics},
            }
        )

    source_inventory = []
    for source in public_sources:
        item = {
            "ordinal": source["ordinal"],
            "source_id": source["source_id"],
            "name_th": source["name_th"],
            "url": source["url"],
            "acquisition_mode": source["acquisition_mode"],
            "expected_record_count": source["expected_record_count"],
            "readiness_status": source["readiness_status"],
            "quality_label_th": source.get(
                "quality_label_th",
                "ข้อมูล candidate · ต้องทบทวนความหมายก่อนใช้เป็น KPI",
            ),
            "notes_th": source.get("notes_th", ""),
        }
        if source["source_id"] in {
            "f2_culturalmap_university",
            "f2_learning_dashboard",
        }:
            source_insight = source_insights["sources"][source["source_id"]]
            item["projection_coverage"] = source_insight["coverage"]
            if source["source_id"] == "f2_culturalmap_university":
                item["privacy_projection"] = source_insight["privacy_projection"]
        source_inventory.append(item)

    expected_total = sum(item["expected_record_count"] for item in source_inventory)
    evidence_province_count = sum(
        1 for profile in profiles.values() if profile["evidence_source_count"] > 0
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    learning_unmatched_count = learning_payload["coverage"]["unmatched_province_rows"]
    unmapped_public_records = (
        sum(area_unmapped_reason_counts.values())
        + learning_unmatched_count
        + sum(housing_unmapped_reason_counts.values())
    )
    public_catalog = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "publication_status": "public_candidate_projection",
        "warning_th": "ข้อมูลทุกชุดเป็น candidate/needs_review ใช้สำรวจหลักฐานและจำลองฉากทัศน์ ไม่ใช่คำสั่งจัดสรรงบหรือ KPI ที่รับรองแล้ว",
        "summary": {
            "public_sources": len(source_inventory),
            "candidate_records_referenced": expected_total,
            "provinces_with_evidence": evidence_province_count,
            "geocoded_cultural_points": len(cultural_features),
            "cultural_supporting_records": source_insights["sources"]
            ["f2_culturalmap_university"]["coverage"]["supporting_records"],
            "restricted_sources_excluded": restricted_source_count,
            "unmapped_public_records": unmapped_public_records,
        },
        "unmapped": {
            "total_records": unmapped_public_records,
            "by_source": {
                "f2_learning_area_based": {
                    "records": sum(area_unmapped_reason_counts.values()),
                    "reason_counts": dict(sorted(area_unmapped_reason_counts.items())),
                },
                "f2_learning_dashboard": {
                    "records": learning_unmatched_count,
                    "reason_counts": {
                        "province_name_not_in_exact_crosswalk": learning_unmatched_count
                    },
                },
                "f3_housing_portal": {
                    "records": sum(housing_unmapped_reason_counts.values()),
                    "reason_counts": dict(sorted(housing_unmapped_reason_counts.items())),
                },
            },
            "download_path": "/downloads/unmapped_records.json",
        },
        "themes": [
            {
                "id": "community",
                "name_th": "ความเป็นอยู่และพื้นที่",
                "description_th": "คะแนนต้นทาง SRA-DSS และหน่วยเข้าร่วมโครงการ Area-Based",
                "source_ids": [
                    "f1_sradss_ppaos",
                    "f2_learning_dashboard",
                    "f2_learning_area_based",
                ],
            },
            {
                "id": "innovation",
                "name_th": "นวัตกรรมพร้อมใช้",
                "description_th": "ทะเบียนนวัตกรรมจากเครือข่ายมหาวิทยาลัย 3 ระบบ",
                "source_ids": ["f2_rmutdb", "f2_apptech_mtr", "f2_apptech_mru"],
            },
            {
                "id": "housing",
                "name_th": "ที่อยู่อาศัยและเมือง",
                "description_th": "ชุดข้อมูลประชากร เศรษฐกิจ อุปทาน และดัชนีที่อยู่อาศัย",
                "source_ids": ["f3_housing_portal", "f3_city_capital_open_data"],
            },
            {
                "id": "culture",
                "name_th": "วัฒนธรรมและการท่องเที่ยว",
                "description_th": "จุดวัฒนธรรมที่มีพิกัดและข้อมูลท่องเที่ยวลำพูน",
                "source_ids": ["f2_culturalmap_university", "f3_ruamthiao_lamphun"],
            },
        ],
        "metrics": {
            "evidence_source_count": {
                "label_th": "จำนวนแหล่งหลักฐานที่เชื่อมกับจังหวัด",
                "unit": "sources",
                "semantic_status": "technical_coverage_only",
            },
            "sra_overall_score": {
                "label_th": "overall score จาก SRA-DSS",
                "unit": "source_score",
                "semantic_status": "provisional_source_definition",
            },
            "area_based_participant_records": {
                "label_th": "หน่วยเข้าร่วม Area-Based",
                "unit": "records",
                "semantic_status": "participant_records_not_population",
            },
            "innovation_records": {
                "label_th": "ผลงาน AppTech ที่ระบุจังหวัด",
                "unit": "records",
                "semantic_status": "candidate_records",
            },
            "cultural_records": {
                "label_th": "จุดวัฒนธรรมที่มีพิกัด",
                "unit": "records",
                "semantic_status": "candidate_records",
            },
            "housing_observations": {
                "label_th": "แถวข้อมูล Thai Housing Portal",
                "unit": "observations",
                "semantic_status": "technical_observation_count",
            },
            "pppconnext_aggregate_rows": {
                "label_th": "ตัวชี้วัดครัวเรือนระดับจังหวัดจาก PPPConnext",
                "unit": "aggregate rows",
                "semantic_status": "candidate_aggregate_rows",
            },
            "learning_dashboard_business_records": {
                "label_th": "ธุรกิจชุมชนในกลุ่มผู้เข้าร่วมโครงการตามต้นทาง",
                "unit": None,
                "semantic_status": "selected_project_scope_unit_and_as_of_unknown",
            },
            "apptech_registered_users": {
                "label_th": "ผู้ใช้ที่ API AppTech ผูกกับจังหวัด",
                "unit": "users",
                "semantic_status": "candidate_source_aggregate",
            },
            "apptech_interactions": {
                "label_th": "การปฏิสัมพันธ์ที่ API AppTech ผูกกับจังหวัด",
                "unit": "interactions",
                "semantic_status": "candidate_source_aggregate",
            },
            "city_capital_cities": {
                "label_th": "เทศบาลในชุด City Capital",
                "unit": "cities",
                "semantic_status": "municipality_records_not_province_metrics",
            },
        },
        "sources": source_inventory,
        "provinces": sorted(profiles.values(), key=lambda row: row["province_name_th"]),
        "methodology": {
            "budget_simulator_th": "ผู้ใช้กำหนดงบและสัดส่วนเอง ระบบคำนวณผลรวมเท่านั้น ไม่มีการแนะนำอัตโนมัติ",
            "map_height_th": "ความสูงเป็นค่าที่ normalize เพื่อการแสดงผลภายใน metric เดียว ห้ามเปรียบเทียบข้าม metric",
            "province_join_th": "ใช้รหัสจังหวัดจากต้นทางและขอบเขตจังหวัดของ ปภ.; ไม่ join ด้วยชื่อเมื่อมีรหัส",
            "privacy_th": "เผยแพร่เฉพาะ aggregate/ทะเบียนสาธารณะและตัด source ที่เป็น restricted_local_only ออกจาก public data",
            "unmapped_th": "เก็บแถวที่ไม่มีจังหวัดไว้ใน unmapped_records.json โดยไม่เดาพื้นที่",
        },
    }

    points_geojson = {
        "type": "FeatureCollection",
        "name": "AIAT public cultural points",
        "source_id": "f2_culturalmap_university",
        "quality_status": "candidate_needs_review",
        "features": cultural_features,
    }

    # Keep the cached official boundary stable across ordinary rebuilds. A refresh
    # replaces this timestamp, while metric-only builds remain content-addressable.
    boundaries.setdefault("generated_at", generated_at)
    boundaries["quality_status"] = "reference_boundary_with_candidate_metrics"

    catalog_output = OUTPUT_DIR / "public_dashboard.json"
    province_csv = OUTPUT_DIR / "province_evidence.csv"
    source_csv = OUTPUT_DIR / "source_inventory.csv"
    points_output = OUTPUT_DIR / "cultural_points.geojson"
    boundary_output = OUTPUT_DIR / "thailand_provinces.geojson"
    write_json(catalog_output, public_catalog)
    write_json(points_output, points_geojson)
    write_json(boundary_output, boundaries)

    province_fields = [
        "province_code",
        "province_name_th",
        "province_name_en",
        "region",
        "evidence_source_count",
        "sra_overall_score",
        "area_based_participant_records",
        "innovation_records",
        "cultural_records",
        "housing_observations",
        "pppconnext_aggregate_rows",
        "learning_dashboard_business_records",
        "apptech_registered_users",
        "apptech_interactions",
        "city_capital_cities",
        "quality_status",
    ]
    with province_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=province_fields)
        writer.writeheader()
        for profile in public_catalog["provinces"]:
            writer.writerow({field: profile.get(field) for field in province_fields})

    source_fields = [
        "ordinal",
        "source_id",
        "name_th",
        "url",
        "acquisition_mode",
        "expected_record_count",
        "readiness_status",
        "quality_label_th",
    ]
    with source_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=source_fields)
        writer.writeheader()
        for source in source_inventory:
            writer.writerow({field: source.get(field) for field in source_fields})

    outputs = [catalog_output, province_csv, source_csv, points_output, boundary_output]
    manifest = {
        "manifest_version": "1.0.0",
        "generated_at": generated_at,
        "publication_status": "public_candidate_projection",
        "inputs": [
            {
                "path": str(path.relative_to(WORKSPACE_ROOT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in input_paths
        ],
        "outputs": [
            {
                "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in outputs
        ],
        "excluded_source_ids": restricted_source_ids,
    }
    write_json(OUTPUT_DIR / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": "ok",
                "public_sources": len(source_inventory),
                "provinces_with_evidence": evidence_province_count,
                "cultural_points": len(cultural_features),
                "outputs": len(outputs) + 1,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the approved public dashboard projection")
    parser.add_argument(
        "--refresh-boundaries",
        action="store_true",
        help="Refresh the 77-province GeoJSON from the official DDPM ArcGIS layer",
    )
    args = parser.parse_args()
    build_public_data(refresh_boundaries=args.refresh_boundaries)
