from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

import pytest

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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_WORKSPACE_REASON = (
    "immutable raw/staged evidence is not included in the public clone"
)
CULTURAL_FILES = (
    "map_inspiration.json",
    "products.json",
    "activities.json",
    "recreation.json",
    "team.json",
)
CULTURAL_DIR = MERGE_RUN / "03_f2_culturalmap_university/data"
HOUSING_METADATA_PATH = (
    STAGED_ROOT
    / "f3_housing_portal/20260803T_housing_silver_02/resource_inventory.json"
)
HOUSING_DIR = BASE_RUN / "23_f3_housing_portal/data"
TOURISM_DIR = MERGE_RUN / "16_f3_ruamthiao_lamphun/data"


@pytest.mark.skipif(
    not all((CULTURAL_DIR / filename).is_file() for filename in CULTURAL_FILES),
    reason=EVIDENCE_WORKSPACE_REASON,
)
def test_cultural_supporting_projection_keeps_work_details_and_complete_counts():
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
        "supporting_records_exposed": True,
        "contact_fields_exposed": True,
        "aggregate_counts_only": False,
        "public_work_details": True,
        "account_identifiers_exposed": False,
    }
    assert len(projection["public_records"]) == 361
    assert len({(r["dataset_id"], r["record_id"]) for r in projection["public_records"]}) == 361
    assert not {"account_identifier", "informants_raw"}.intersection(recursive_keys(projection))


@pytest.mark.skipif(
    not REQUIREMENT_PATH.is_file(),
    reason=EVIDENCE_WORKSPACE_REASON,
)
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
            "owner_name",
            "owner_affiliation_name",
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


@pytest.mark.skipif(
    not REQUIREMENT_PATH.is_file(),
    reason=EVIDENCE_WORKSPACE_REASON,
)
def test_requirement_province_crosswalk_does_not_strip_or_infer_prefixes():
    row = json.loads(REQUIREMENT_PATH.read_text(encoding="utf-8").splitlines()[0])
    row["normalized_fields"]["areas"][0]["province"] = "จังหวัดศรีสะเกษ"

    codes, _, unmatched = project_requirement_record(row, {"ศรีสะเกษ": "33"})

    assert codes == []
    assert unmatched == ["จังหวัดศรีสะเกษ"]


@pytest.mark.skipif(
    not HOUSING_METADATA_PATH.is_file() or not any(HOUSING_DIR.glob("*.csv")),
    reason=EVIDENCE_WORKSPACE_REASON,
)
def test_all_approved_housing_rows_reconcile_with_306_sanitized_unmapped_rows():
    dashboard = json.loads(
        (PROJECT_ROOT / "data/public/public_dashboard.json").read_text(
            encoding="utf-8"
        )
    )
    code_by_name = {
        normalize_text(row["province_name_th"]): row["province_code"]
        for row in dashboard["provinces"]
    }
    valid_codes = set(code_by_name.values())
    metadata = {
        row["resource_id"]: row
        for row in json.loads(HOUSING_METADATA_PATH.read_text(encoding="utf-8"))["resources"]
    }

    total = 0
    mapped = 0
    unmapped = []
    for path in sorted(HOUSING_DIR.glob("*.csv")):
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


@pytest.mark.skipif(
    not (CULTURAL_DIR / "map_inspiration.json").is_file(),
    reason=EVIDENCE_WORKSPACE_REASON,
)
def test_cultural_briefing_projection_preserves_work_attribution_without_account_ids():
    cultural_path = CULTURAL_DIR / "map_inspiration.json"
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
        "address",
        "work_contact",
        "recorder_name",
        "recorder_institution",
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
        "account_identifier",
        "birth",
        "income",
        "social",
    }
    assert forbidden.isdisjoint(set(recursive_keys(item)))


@pytest.mark.skipif(
    not any(TOURISM_DIR.glob("*.json")),
    reason=EVIDENCE_WORKSPACE_REASON,
)
def test_tourism_projection_keeps_public_service_contacts_and_counts():
    projections = {
        item["page_id"]: item
        for item in (
            project_tourism_payload(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(TOURISM_DIR.glob("*.json"))
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
    assert projections["komepage"]["data"]["lantern_group_count"] == 10
    assert len(projections["komepage"]["data"]["lantern_production_groups"]) == 10
    assert len(projections["contact"]["data"]["emergency_numbers"]) == 6
    assert len(projections["contact"]["data"]["service_centres"]) == 3
    centres = projections["contact"]["data"]["service_centres"]
    assert sum(len(centre["phones"]) for centre in centres) == 7
    assert centres[0]["opening_hours"] == "07.30 - 18.00 น."
    stations = projections["homepage"]["data"]["map"]["stations"]
    assert all(set(station) == {"name", "nearby_count"} for station in stations)
    recommendation_items = [
        item
        for category in projections["recommend"]["data"]["categories"]
        for item in category["items"]
    ]
    assert all(set(item) == {"record_id", "title", "description"} for item in recommendation_items)
    from app.publication import _privacy_problems
    contract = json.loads((PROJECT_ROOT / "config/publication_contracts/provincial_briefings.json").read_text(encoding="utf-8"))
    payload = {"sections": {"tourism": {"items": list(projections.values())}}}
    assert _privacy_problems(payload, artifact_path="tourism", restricted_source_ids=set(),
                             profile="aggregate_public", field_contexts=contract["outputs"][0]["field_contexts"]) == []


def test_public_description_sanitizer_removes_contact_fragments():
    value = "อาหารพื้นถิ่น ติดต่อ 081-234-5678; LINE ID: secret.person; เปิดทุกวัน"

    projected = sanitize_public_text(value)

    assert projected == "อาหารพื้นถิ่น เปิดทุกวัน"
    assert "081" not in projected
    assert "secret.person" not in projected
