from __future__ import annotations

import copy

import pytest

from tools.f2_pipeline.sources.cultural_map import build_tables


class Geography:
    reference_version = "synthetic"

    def resolve(self, province, district):
        return {
            "province_normalized": province,
            "province_code": {"Alpha": "10", "Beta": "20"}[province],
            "district_normalized": district or "",
            "district_code": "1001" if district else "",
            "subdistrict_normalized": "",
            "subdistrict_code": "",
            "correction_reason": "",
        }


def record(external_id, title="A", province="Alpha", categories=("C1",), history="history"):
    return {
        "external_id": external_id,
        "title": title,
        "data": {
            "names": {"th": title},
            "classification": {
                "primary_category": {"code": categories[0], "name_th": categories[0]},
                "additional_categories": [{"code": code} for code in categories[1:]],
                "cultural_type": {"code": "T"},
            },
            "location": {"administrative": {"province": {"name_th": province, "code": "10" if province == "Alpha" else "20"}, "amphure": {"name_th": "District", "code": "1001"}}, "coordinates": {"latitude": 1, "longitude": 2}},
            "description": {"history": history},
            "dates": {"recorded": "2020-01-01"},
            "media": {"images": [{"url": "image"}], "clips": [], "documents": [], "links": [], "narration_links": []},
        },
    }


def inputs(rows):
    captures = {key: {"data": {"records": []}} for key in ("map_inspiration", "products", "activities", "recreation", "team")}
    captures["map_inspiration"]["data"]["records"] = rows
    metadata = {key: {"sha256": f"hash-{key}", "captured_at": "2026-01-01T00:00:00Z", "source_id": "source", "run_id": "run", "file": f"{key}.json"} for key in captures}
    return captures, metadata


def test_merges_preserve_listing_category_location_narrative_and_media():
    captures, metadata = inputs([record("one", categories=("C1", "C2")), record("two", province="Beta", categories=("C3",))])
    tables = build_tables(captures, {"subject_identity": {"reviewed_merges": [["one", "two"]]}}, Geography(), metadata)
    assert len(tables["mapped_subjects"]) == 1
    subject = tables["mapped_subjects"][0]
    assert subject["province_codes_json"] == ["10", "20"]
    assert len(tables["mapped_listing_observations"]) == 2
    assert {row["category_code"] for row in tables["category_assertions"]} == {"C1", "C2", "C3"}
    assert len(tables["mapped_locations"]) == len(tables["mapped_narrative_evidence"]) == len(tables["mapped_media"]) == 2
    assert len(tables["source_observations"]) == 2


def test_separation_and_unresolved_candidates_remain_distinct_and_traceable():
    captures, metadata = inputs([record("one"), record("two"), record("three")])
    tables = build_tables(captures, {"subject_identity": {"separations": [["one", "two"]], "unresolved_candidates": [["two", "three"]]}}, Geography(), metadata)
    assert len(tables["mapped_subjects"]) == 3
    assert {(row["outcome"], row["status"]) for row in tables["identity_decisions"]} == {("cannot_link", "resolved_separate"), ("retained_unresolved_candidate", "unresolved")}
    observations = {row["observation_id"] for row in tables["source_observations"]}
    assert all(set(row["evidence_observation_ids_json"]) <= observations for row in tables["identity_decisions"])


def test_cannot_link_blocks_transitive_review_merge():
    captures, metadata = inputs([record("one"), record("two"), record("three")])
    reviews = {"subject_identity": {"reviewed_merges": [["one", "two"], ["two", "three"]], "cannot_links": [["one", "three"]]}}
    with pytest.raises(ValueError, match="cannot-links prevent unsafe transitive merging"):
        build_tables(captures, reviews, Geography(), metadata)

def test_unresolved_candidate_blocks_an_unsupported_merge():
    captures, metadata = inputs([record("one"), record("two")])
    reviews = {"subject_identity": {"reviewed_merges": [["one", "two"]], "unresolved_candidates": [["one", "two"]]}}
    with pytest.raises(ValueError, match="cannot-links prevent unsafe transitive merging"):
        build_tables(captures, reviews, Geography(), metadata)

def test_subject_near_an_unresolved_candidate_is_flagged_even_when_merged_elsewhere():
    captures, metadata = inputs([record("one"), record("two"), record("three")])
    reviews = {"subject_identity": {"reviewed_merges": [["one", "three"]], "unresolved_candidates": [["one", "two"]]}}
    tables = build_tables(captures, reviews, Geography(), metadata)
    merged = next(row for row in tables["mapped_subjects"] if set(row["source_ids_json"]) == {"one", "three"})
    assert merged["identity_status"] == "unresolved_possible_duplicate"


def test_subdistrict_is_preserved_and_crosswalked_against_resolved_district():
    class SubdistrictGeography(Geography):
        subdistricts = [{"subdistrictNameTh": "Tambon", "subdistrictCode": "100101", "districtCode": "1001", "provinceCode": "10"}]

    row = record("one")
    row["data"]["location"]["administrative"]["tambon"] = {"name_th": "Tambon", "code": "100101"}
    captures, metadata = inputs([row])
    location = build_tables(captures, {}, SubdistrictGeography(), metadata)["mapped_locations"][0]
    assert location["subdistrict_normalized"] == "Tambon"
    assert location["subdistrict_code"] == "100101"


def test_unmatched_tambon_claim_is_raw_not_normalized():
    row = record("one")
    row["data"]["location"]["administrative"]["tambon"] = {"name_th": "Unmatched", "code": "999999"}
    captures, metadata = inputs([row])
    location = build_tables(captures, {}, Geography(), metadata)["mapped_locations"][0]
    assert location["subdistrict_raw"] == "Unmatched"
    assert location["subdistrict_code"] == ""
    assert location["subdistrict_normalized"] == ""
    assert location["status"] == "source_hierarchy_conflict"


def test_observation_identity_is_not_capture_row_order():
    first, metadata = inputs([record("one"), record("two")])
    second, _ = inputs([record("two"), record("one")])
    first_ids = {row["source_id"]: row["observation_id"] for row in build_tables(first, {}, Geography(), metadata)["source_observations"]}
    second_ids = {row["source_id"]: row["observation_id"] for row in build_tables(second, {}, Geography(), metadata)["source_observations"]}
    assert first_ids == second_ids


def test_duplicate_ids_and_schema_drift_are_explicit():
    captures, metadata = inputs([record("one"), record("one")])
    with pytest.raises(ValueError, match="duplicate source ID"):
        build_tables(captures, {}, Geography(), metadata)
    captures, metadata = inputs([record("one")])
    captures["map_inspiration"] = copy.deepcopy(captures["map_inspiration"])
    del captures["map_inspiration"]["data"]["records"][0]["data"]["classification"]["primary_category"]
    with pytest.raises(ValueError, match="lacks primary category"):
        build_tables(captures, {}, Geography(), metadata)
