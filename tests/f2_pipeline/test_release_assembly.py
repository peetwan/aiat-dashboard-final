import csv
import json

import pytest

from tools.f2_pipeline.common import PipelineError, write_csv, read_csv
from tools.f2_pipeline.full_release import assemble_measures, validate_json_columns


def test_json_columns_round_trip_objects_arrays_and_explicit_string_scalars(tmp_path):
    rows = [
        {
            "object_json": {"id": 1},
            "array_json": [1, 2],
            "string_json": json.dumps("007"),
            "missing_json": None,
        }
    ]
    check = validate_json_columns({"source/areas": rows})
    assert check["status"] == "passed"
    assert check["actual"] == 3
    path = tmp_path / "areas.csv"
    write_csv(path, rows)
    stored = read_csv(path)[0]
    assert json.loads(stored["object_json"]) == {"id": 1}
    assert json.loads(stored["array_json"]) == [1, 2]
    assert json.loads(stored["string_json"]) == "007"
    assert stored["missing_json"] == ""


@pytest.mark.parametrize(
    "value", ["unquoted source area", True, '{"id": 1, "id": 2}', "NaN"]
)
def test_malformed_json_columns_fail_before_release_commit(value):
    with pytest.raises(PipelineError, match="source/areas/raw_area_json"):
        validate_json_columns({"source/areas": [{"raw_area_json": value}]})


def test_large_source_envelope_cells_round_trip_with_a_bounded_csv_reader(tmp_path):
    envelope = {"synthetic": "x" * 140_000}
    path = tmp_path / "source_files.csv"
    write_csv(path, [{"envelope_json": envelope}])
    previous_limit = csv.field_size_limit(131_072)
    try:
        assert json.loads(read_csv(path)[0]["envelope_json"]) == envelope
    finally:
        csv.field_size_limit(previous_limit)


def test_c02_person_province_membership_uses_reviewed_domain_assertion():
    sources = {
        "f2_culturalmap_university": {
            "mapped_subjects": [],
            "mapped_locations": [],
            "category_assertions": [],
            "mapped_listing_observations": [],
        },
        "f2_cultural_market_civil": {"locations": []},
    }
    domains = {
        "areas": {
            "global_cultural_areas": [],
            "area_crosswalk": [],
            "area_assertions": [],
        },
        "activities": {
            "global_activities": [],
            "activity_venues": [],
            "activity_publication_links": [],
        },
        "innovations": {
            "global_innovations": [],
            "measure_contributions": [],
            "innovation_use_locations": [],
        },
        "people": {
            "global_people": [
                {"global_person_id": "person-1", "display_name": "Person One"}
            ],
            "measure_contributions": [
                {
                    "measure_id": "C02_COMMUNITY",
                    "global_person_id": "person-1",
                    "qualifying_assertion_ids_json": '["role-1"]',
                }
            ],
            "person_location_assertions": [
                {
                    "location_assertion_id": "province-1",
                    "global_person_id": "person-1",
                    "province_code": "10",
                    "location_role": "source_reported_innovator_location",
                }
            ],
        },
    }

    root = assemble_measures(sources, domains)

    assert root["province_memberships"] == [
        {
            "measure_id": "C02_COMMUNITY",
            "entity_id": "person-1",
            "province_code": "10",
            "location_role": "source_reported_innovator_location",
            "evidence_table": "domains/people/person_location_assertions",
            "evidence_key": "location_assertion_id",
            "evidence_id": "province-1",
        }
    ]
