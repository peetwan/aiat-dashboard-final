import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.domains.programme_coverage import TABLE_COLUMNS, build_tables
from tools.f2_pipeline.domains.raw_inputs import SOURCE_IDS


def _bundle(source_id, document):
    return {
        "datasets": {"records": document},
        "metadata": {
            "records": {
                "source_id": source_id,
                "run_id": "run-1",
                "file": f"{source_id}.json",
                "sha256": f"sha-{source_id}",
            }
        },
        "files": [],
    }


def _observation(source_id, observation_id):
    return {
        "observation_id": observation_id,
        "source_id": observation_id,
        "source_key": observation_id,
        "raw_file": f"{source_id}.json",
        "row_locator": f"evidence://{source_id}/run-1/{source_id}.json#/data/0",
        "file_sha256": f"sha-{source_id}",
    }


def _fixture():
    source_tables = {source_id: {} for source_id in SOURCE_IDS.values()}
    raw_inputs = {}
    for alias in (
        "icommunity",
        "atlocal",
        "cultural_map",
        "pmua_apptech",
        "rinmp",
        "learning_area_based",
    ):
        source_id = SOURCE_IDS[alias]
        raw_inputs[source_id] = _bundle(source_id, {"data": [{"evidence": alias}]})

    icommunity = SOURCE_IDS["icommunity"]
    source_tables[icommunity] = {
        "source_observations": [_observation(icommunity, "obs-icommunity")],
        "person_roles": [
            {
                "person_id": "person-supported",
                "observation_id": "obs-icommunity",
                "role": "community_innovator",
            }
        ],
        "locations": [
            {
                "location_id": "icommunity-person-supported",
                "observation_id": "obs-icommunity",
                "entity_id": "person-supported",
                "location_role": "source_person_location",
                "province_code": "10",
            },
            {
                "location_id": "icommunity-person-unmatched",
                "observation_id": "obs-icommunity",
                "entity_id": "person-unmatched",
                "location_role": "source_person_location",
                "province_code": "10",
            },
            {
                "location_id": "icommunity-innovation-unknown",
                "observation_id": "obs-icommunity",
                "entity_id": "innovation-icommunity",
                "location_role": "declared_innovation_use",
                "province_code": "",
            },
        ],
        "activities": [
            {
                "activity_id": "icommunity-activity-unknown",
                "observation_id": "obs-icommunity",
                "province": "",
            }
        ],
    }

    atlocal = SOURCE_IDS["atlocal"]
    source_tables[atlocal] = {
        "source_observations": [_observation(atlocal, "obs-atlocal")],
        "locations": [
            {
                "location_id": "atlocal-listing",
                "observation_id": "obs-atlocal",
                "location_role": "source_listing_location",
                "province_code": "10",
            },
            {
                "location_id": "atlocal-institution",
                "observation_id": "obs-atlocal",
                "location_role": "institution_context",
                "province_code": "10",
            },
        ],
        "activities": [],
    }

    cultural_map = SOURCE_IDS["cultural_map"]
    source_tables[cultural_map] = {
        "source_observations": [_observation(cultural_map, "obs-cultural-map")],
        "target_province_evidence": [
            {
                "evidence_id": "cultural-map-supported",
                "observation_id": "obs-cultural-map",
                "province_code": "10",
                "location_role": "mapped_subject_location",
                "qualifies_target_province": "True",
                "basis": "source-published cultural subject coverage",
            },
            {
                "evidence_id": "cultural-map-context",
                "observation_id": "obs-cultural-map",
                "province_code": "10",
                "location_role": "activity_context",
                "qualifies_target_province": "False",
                "basis": "context only",
            },
        ],
        "target_provinces": [{"province_code": "10"}],
        "measure_contributions": [],
    }

    pmua = SOURCE_IDS["pmua_apptech"]
    source_tables[pmua] = {
        "source_observations": [_observation(pmua, "obs-pmua")],
        "innovation_area_assertions": [
            {
                "assertion_id": "pmua-area",
                "observation_id": "obs-pmua",
                "province_code": "10",
                "source_locator": "data/0",
            }
        ],
        "measure_contributions": [
            {
                "measure": "K01A_innovation_use_provinces",
                "entity_id": "th-province:10",
            }
        ],
    }

    rinmp = SOURCE_IDS["rinmp"]
    source_tables[rinmp] = {
        "source_observations": [_observation(rinmp, "obs-rinmp")],
        "location_assertions": [
            {
                "location_id": "rinmp-use",
                "observation_id": "obs-rinmp",
                "province_code": "10",
                "location_role": "declared_innovation_use",
                "coverage_eligibility": "eligible_programme_target_or_use_coverage",
                "source_locator": "data/0",
            },
            {
                "location_id": "rinmp-institution",
                "observation_id": "obs-rinmp",
                "province_code": "10",
                "location_role": "researcher_institution_affiliation",
                "coverage_eligibility": "institution_only_not_programme_coverage",
                "source_locator": "data/0",
            },
        ],
        "measure_contributions": [
            {
                "measure": "K01A_target_provinces",
                "entity_id": "th-province:10",
            }
        ],
    }

    learning = SOURCE_IDS["learning_area_based"]
    source_tables[learning] = {
        "source_observations": [_observation(learning, "obs-learning")],
        "locations": [
            {
                "location_id": "learning-business",
                "observation_id": "obs-learning",
                "province_code": "10",
                "location_role": "programme_business_location",
            },
            {
                "location_id": "learning-institution",
                "observation_id": "obs-learning",
                "province_code": "10",
                "location_role": "research_unit_location",
            },
        ],
        "measure_contributions": [
            {
                "measure": "K01_programme_coverage_provinces",
                "business_id": "business-1",
                "province_code": "10",
            }
        ],
    }

    dashboard = SOURCE_IDS["learning_dashboard"]
    raw_inputs[dashboard] = _bundle(
        dashboard,
        {"coverage": [{"count": 5}, {"count": 0}]},
    )
    source_tables[dashboard] = {
        "coverage_assertions": [
            {
                "coverage_assertion_id": "dashboard-positive",
                "reported_business_count": "5",
                "province_code": "10",
                "coverage_role": "positive_source_reported_programme_coverage",
                "raw_locator": (
                    f"evidence://{dashboard}/run-1/{dashboard}.json#/coverage/0"
                ),
            },
            {
                "coverage_assertion_id": "dashboard-zero",
                "reported_business_count": "0",
                "province_code": "10",
                "coverage_role": "positive_source_reported_programme_coverage",
                "raw_locator": (
                    f"evidence://{dashboard}/run-1/{dashboard}.json#/coverage/1"
                ),
            },
        ]
    }

    source_tables[SOURCE_IDS["apptech_mru"]] = {
        "institution_assertions": [{"province_code": "10"}]
    }
    reviews = {
        "cross_source_activities_coverage/runtime.json": {"schema_version": 1},
        "cross_source_activities_coverage/reviewed_evidence.json": {
            "schema_version": 1
        },
    }
    innovation_tables = {
        "innovation_use_locations": [
            {
                "source": "icommunity",
                "location_id": "icommunity-innovation-unknown",
                "location_role": "declared_innovation_use",
                "coverage_eligibility": "eligible_innovation_use",
            },
            {
                "source": "pmua_apptech",
                "location_id": "pmua-area:0",
                "location_role": "declared_innovation_use",
                "coverage_eligibility": "eligible_innovation_use",
            },
            {
                "source": "rinmp",
                "location_id": "rinmp-use",
                "location_role": "declared_innovation_use",
                "coverage_eligibility": "eligible_programme_target_or_use_coverage",
            },
        ]
    }
    geography = SimpleNamespace(
        provinces=[{"provinceCode": "10", "provinceNameTh": "Bangkok"}]
    )
    return source_tables, reviews, raw_inputs, geography, innovation_tables


def test_programme_coverage_preserves_eligibility_unknowns_exclusions_and_lineage():
    source_tables, reviews, raw_inputs, geography, innovation_tables = _fixture()
    source_before = copy.deepcopy(source_tables)
    raw_before = copy.deepcopy(raw_inputs)

    tables = build_tables(
        source_tables, reviews, raw_inputs, geography, innovation_tables
    )

    assertions = tables["coverage_assertions"]
    by_key = {(row["source"], row["source_row_id"]): row for row in assertions}
    assert len(assertions) == 15
    assert all(
        set(row) == set(TABLE_COLUMNS["coverage_assertions"]) for row in assertions
    )
    assert (
        by_key[("icommunity-v1", "icommunity-person-supported")]["disposition"]
        == "qualifying_resolved"
    )
    assert (
        by_key[("icommunity-v1", "icommunity-person-unmatched")]["disposition"]
        == "excluded_role_or_context"
    )
    assert (
        by_key[("icommunity-v1", "icommunity-innovation-unknown")]["disposition"]
        == "qualifying_unknown_province"
    )
    assert (
        by_key[("icommunity-v1", "icommunity-activity-unknown")]["disposition"]
        == "qualifying_unknown_province"
    )
    for source, key in (
        ("atlocal-v1", "atlocal-institution"),
        ("cultural-map-v1", "cultural-map-context"),
        ("rinmp-v1", "rinmp-institution"),
        ("learning-area-based-v1", "learning-institution"),
        ("learning-dashboard-v1", "dashboard-zero"),
    ):
        assert by_key[(source, key)]["disposition"] == "excluded_role_or_context"
    assert not any(row["source"] == "apptech-mru-v1" for row in assertions)
    assert (
        by_key[("learning-dashboard-v1", "dashboard-positive")]["evidence_kind"]
        == "aggregate_only"
    )
    assert all(row["raw_locator"].startswith("evidence://") for row in assertions)
    assert all(row["lineage_status"] == "resolved" for row in assertions)
    expected_id = (
        "coverage_"
        + hashlib.sha256(
            "\x1f".join(
                ("icommunity-v1", "locations", "icommunity-person-supported")
            ).encode()
        ).hexdigest()[:20]
    )
    assert (
        by_key[("icommunity-v1", "icommunity-person-supported")][
            "coverage_assertion_id"
        ]
        == expected_id
    )
    assert (
        json.loads(by_key[("rinmp-v1", "rinmp-institution")]["source_details_json"])
        == source_tables[SOURCE_IDS["rinmp"]]["location_assertions"][1]
    )

    assert tables["measure_results"] == [
        {
            "measure": "K01A_supported_target_provinces",
            "value": 1,
            "scope": "K01A demonstration; distinct qualifying Thai province codes",
            "status": "demonstration_not_final_release",
        }
    ]
    assert tables["province_evidence_index"] == [
        {
            "province_code": "10",
            "province_name": "Bangkok",
            "sources_json": json.dumps(
                [
                    "atlocal-v1",
                    "cultural-map-v1",
                    "icommunity-v1",
                    "learning-area-based-v1",
                    "learning-dashboard-v1",
                    "pmua-apptech-v1",
                    "rinmp-v1",
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "qualifying_assertion_count": 7,
        }
    ]
    contributor_ids = json.loads(
        tables["measure_contributions"][0]["contributor_ids_json"]
    )
    assert len(contributor_ids) == len(set(contributor_ids)) == 7
    assert source_tables == source_before
    assert raw_inputs == raw_before


def test_programme_coverage_rejects_dropped_innovation_location_relationships():
    source_tables, reviews, raw_inputs, geography, innovation_tables = _fixture()
    innovation_tables["innovation_use_locations"] = [
        row
        for row in innovation_tables["innovation_use_locations"]
        if row["source"] != "pmua_apptech"
    ]

    with pytest.raises(
        PipelineError,
        match="disagrees with innovation location relationships",
    ):
        build_tables(source_tables, reviews, raw_inputs, geography, innovation_tables)
