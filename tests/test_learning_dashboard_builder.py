from __future__ import annotations

import json

import pytest

from tools.build_learning_dashboard import (
    BOUNDARY_PATH,
    RAW_RESPONSE_PATH,
    build_projection,
    normalize_header_table,
    province_crosswalk,
)


def test_real_learning_dashboard_payload_is_lossless_and_exactly_geocoded():
    raw_payload = json.loads(RAW_RESPONSE_PATH.read_text(encoding="utf-8-sig"))
    boundary = json.loads(BOUNDARY_PATH.read_text(encoding="utf-8-sig"))
    projection = build_projection(
        raw_payload,
        province_crosswalk(boundary),
        observed_at="2026-08-03T05:00:00Z",
    )

    assert projection["coverage"] == {
        "province_rows": 66,
        "linked_province_rows": 66,
        "linked_provinces": 66,
        "unmatched_province_rows": 0,
        "entity_type_rows": 3,
        "category_rows": 7,
        "geography_rows": 6,
        "geography_impact_rows": 6,
    }
    assert len(projection["province_links"]) == 66
    assert projection["unmatched_province_rows"] == []
    assert all(row["unit"] is None and row["as_of"] is None for row in projection["province_rows"])
    assert projection["non_province_tables"]["entity_types"]["row_count"] == 3
    assert projection["non_province_tables"]["categories"]["row_count"] == 7
    assert projection["non_province_impact"]["join_status"] == "not_joined_no_explicit_geography_key"
    assert projection["non_province_impact"]["unit"] is None
    assert projection["non_province_impact"]["as_of"] is None


def test_unmatched_province_row_is_preserved_without_inference():
    payload = {
        "provinces": [["Province", "ธุรกิจชุมชน"], ["จังหวัดสมมติ", 2]],
        "entityTypes": [["Entity Type", "Popularity"]],
        "categories": [["Category", "Popularity"]],
        "geography": [["Geography", "Popularity"]],
        "geographyImpact": [],
        "impactSummary": {},
    }

    projection = build_projection(payload, {"สมุทรปราการ": "11"}, observed_at=None)

    assert projection["coverage"]["linked_provinces"] == 0
    assert projection["coverage"]["unmatched_province_rows"] == 1
    assert projection["unmatched_province_rows"][0]["province_name_th"] == "จังหวัดสมมติ"
    assert projection["unmatched_province_rows"][0]["province_code"] is None


def test_header_array_width_mismatch_fails_closed():
    with pytest.raises(ValueError, match="width does not match header"):
        normalize_header_table(
            [["Province", "ธุรกิจชุมชน"], ["สงขลา"]],
            "provinces",
        )
