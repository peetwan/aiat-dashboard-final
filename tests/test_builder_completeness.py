from __future__ import annotations

import csv
import json
import re
from collections import Counter

from tools.build_provincial_briefings import (
    BASE_RUN,
    MERGE_RUN,
    REQUIREMENT_PATH,
    STAGED_ROOT,
    normalize_text,
    project_cultural_record,
    project_unmapped_housing_record,
    project_requirement_record,
    project_tourism_payload,
    resolve_row_code,
    sanitize_public_text,
)
from tools.build_source_insights import build_cultural_supporting_coverage


def test_cultural_supporting_projection_is_aggregate_only_and_complete():
    projection = build_cultural_supporting_coverage()

    assert projection["coverage"]["map_records"] == 5_258
    assert projection["coverage"]["supporting_records"] == 361
    assert projection["coverage"]["total_records"] == 5_619
    assert {
        row["dataset_id"]: row["record_count"]
        for row in projection["coverage"]["datasets"]
    } == {
        "map_inspiration": 5_258,
        "products": 226,
        "activities": 43,
        "recreation": 80,
        "team": 12,
    }
    assert projection["privacy_projection"] == {
        "supporting_records_exposed": False,
        "contact_fields_exposed": False,
        "aggregate_counts_only": True,
    }
    assert "records" not in projection


def test_two_public_requirements_are_sanitized_and_exactly_province_linked():
    rows = [
        json.loads(line)
        for line in REQUIREMENT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    code_by_exact_name = {"ศรีสะเกษ": "33", "นครปฐม": "73"}

    projections = [project_requirement_record(row, code_by_exact_name) for row in rows]

    assert len(projections) == 2
    assert {tuple(codes) for codes, _, _ in projections} == {("33",), ("73",)}
    assert all(not unmatched for _, _, unmatched in projections)
    for _, item, _ in projections:
        assert item["record_grain"] == "one_public_requirement"
        assert item["provenance"]["as_of"] is None
        assert set(item) == {
            "record_id",
            "record_grain",
            "title",
            "description",
            "category",
            "areas",
            "source_url",
            "provenance",
            "scope_note_th",
        }
        serialized = json.dumps(item, ensure_ascii=False).lower()
        assert "owner_full_name" not in serialized
        assert "owner_user_id" not in serialized
        assert "profile_image" not in serialized
        assert "email" not in serialized
        assert "phone" not in serialized


def test_requirement_province_crosswalk_does_not_strip_or_infer_prefixes():
    row = json.loads(REQUIREMENT_PATH.read_text(encoding="utf-8").splitlines()[0])
    row["normalized_fields"]["areas"][0]["province"] = "จังหวัดศรีสะเกษ"

    codes, _, unmatched = project_requirement_record(row, {"ศรีสะเกษ": "33"})

    assert codes == []
    assert unmatched == ["จังหวัดศรีสะเกษ"]


def test_all_approved_housing_rows_reconcile_with_306_sanitized_unmapped_rows():
    dashboard = json.loads(
        (BASE_RUN.parents[3] / "dashboard_final/data/public/public_dashboard.json").read_text(
            encoding="utf-8"
        )
    )
    code_by_name = {
        normalize_text(row["province_name_th"]): row["province_code"]
        for row in dashboard["provinces"]
    }
    valid_codes = set(code_by_name.values())
    metadata_path = (
        STAGED_ROOT
        / "f3_housing_portal/20260803T_housing_silver_02/resource_inventory.json"
    )
    metadata = {
        row["resource_id"]: row
        for row in json.loads(metadata_path.read_text(encoding="utf-8"))["resources"]
    }

    total = 0
    mapped = 0
    unmapped = []
    housing_dir = BASE_RUN / "23_f3_housing_portal/data"
    for path in sorted(housing_dir.glob("*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                total += 1
                code = resolve_row_code(row, code_by_name)
                if code in valid_codes:
                    mapped += 1
                    continue
                resource_id = row.get("resource_id") or row.get("dataset_id", "").rsplit(":", 1)[-1]
                unmapped.append(
                    project_unmapped_housing_record(
                        row,
                        metadata.get(resource_id, {}),
                        code,
                        valid_codes,
                    )
                )

    assert (total, mapped, len(unmapped)) == (7_259, 6_953, 306)
    assert Counter(row["reason"] for row in unmapped) == {
        "source_geography_not_at_province_grain": 248,
        "source_province_code_not_in_official_crosswalk": 55,
        "source_geography_missing": 3,
    }
    assert all(row["dataset_id"] and row["resource_id"] and row["reason"] for row in unmapped)
    assert all(
        row["record"]["record_grain"] == "one_approved_public_projection_row"
        for row in unmapped
    )
    public_field_names = {
        key.lower()
        for row in unmapped
        for key in row["record"]["values"]
    }
    assert not any(
        marker in field
        for field in public_field_names
        for marker in ("email", "phone", "contact", "person_name")
    )


def recursive_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key.lower()
            yield from recursive_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from recursive_keys(child)


def test_cultural_briefing_projection_is_a_strict_executive_whitelist():
    cultural_path = MERGE_RUN / "03_f2_culturalmap_university/data/map_inspiration.json"
    source = json.loads(cultural_path.read_text(encoding="utf-8"))
    code, item = project_cultural_record(source["data"]["records"][0], cultural_path)

    assert code is not None
    assert set(item) == {
        "record_id",
        "record_code",
        "title_th",
        "title_en",
        "category",
        "cultural_type",
        "province_code",
        "province_name_th",
        "amphoe",
        "tambon",
        "source_url",
        "provenance",
        "quality",
    }
    assert set(item["provenance"]) == {"source_artifact", "recorded_at", "record_hash"}
    assert set(item["quality"]) == {"status", "warning_count"}
    forbidden = {
        "history",
        "potential",
        "stakeholders",
        "coordinates",
        "latitude",
        "longitude",
        "image_url",
        "media",
        "people",
        "phone",
        "email",
        "address",
        "birth",
        "income",
        "social",
    }
    assert forbidden.isdisjoint(set(recursive_keys(item)))


def test_tourism_projection_keeps_counts_but_no_contact_or_address_fields():
    tourism_dir = MERGE_RUN / "16_f3_ruamthiao_lamphun/data"
    projections = {
        item["page_id"]: item
        for item in (
            project_tourism_payload(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(tourism_dir.glob("*.json"))
        )
    }

    assert {key: item["record_count"] for key, item in projections.items()} == {
        "contact": 6,
        "homepage": 12,
        "komepage": 10,
        "recommend": 13,
        "travel": 13,
    }
    assert projections["contact"]["data"]["service_availability_label_count"] == 9
    assert projections["komepage"]["data"] == {"lantern_group_count": 10}
    stations = projections["homepage"]["data"]["map"]["stations"]
    assert all(set(station) == {"name", "nearby_count"} for station in stations)
    recommendation_items = [
        item
        for category in projections["recommend"]["data"]["categories"]
        for item in category["items"]
    ]
    assert all(set(item) == {"record_id", "title", "description"} for item in recommendation_items)
    forbidden_markers = (
        "phone",
        "email",
        "address",
        "social",
        "lantern_production_groups",
        "venues",
        "image",
        "operator",
        "location",
        "service_contacts",
        "emergency_numbers",
    )
    keys = set(recursive_keys(projections))
    assert not any(marker in key for key in keys for marker in forbidden_markers)
    serialized = json.dumps(projections, ensure_ascii=False)
    assert not re.search(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", serialized)
    assert not re.search(r"(?<![\dA-Za-z])(?:\+?66|0)\s*\d(?:[\s().-]*\d){7,9}(?!\d)", serialized)


def test_public_description_sanitizer_removes_contact_fragments():
    value = "อาหารพื้นถิ่น ติดต่อ 081-234-5678; LINE ID: secret.person; เปิดทุกวัน"

    projected = sanitize_public_text(value)

    assert projected == "อาหารพื้นถิ่น เปิดทุกวัน"
    assert "081" not in projected
    assert "secret.person" not in projected
