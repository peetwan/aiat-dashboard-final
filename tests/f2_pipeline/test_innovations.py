import pytest

from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.domains.innovations import build_tables


CANONICAL = {
    "icommunity": "f2_icommunity",
    "pmua_apptech": "f2_target_household",
    "rinmp": "f2_apptech_mtr",
    "apptech_mru": "f2_apptech_mru",
}


def _raw(source_id):
    return {
        "datasets": {"items": {"data": [{"id": "one"}]}},
        "metadata": {
            "items": {
                "source_id": source_id,
                "run_id": "run",
                "file": "items.json",
                "sha256": "hash",
            }
        },
        "files": [
            {"path": "items.json", "sha256": "hash", "size": 1, "dataset_key": "items"}
        ],
    }


def _observation(source_id, observation_id, source_record_id):
    return {
        "observation_id": observation_id,
        "source_id": source_record_id,
        "source_key": source_record_id,
        "raw_file": f"evidence://{source_id}/run/items.json",
        "row_locator": "data/0",
        "file_sha256": "hash",
    }


def _inputs(*, readiness=False, use_location=False):
    i_obs = _observation(CANONICAL["icommunity"], "io", "i-1")
    p_obs = _observation(CANONICAL["pmua_apptech"], "po", "p-1")
    r_obs = _observation(CANONICAL["rinmp"], "ro", "r-1")
    source_tables = {
        CANONICAL["icommunity"]: {
            "source_observations": [i_obs],
            "innovations": [
                {
                    "innovation_id": "i",
                    "display_name": "Alpha",
                    "identity_status": "reviewed",
                    "source_ids_json": '["i-1"]',
                    "aliases_json": "[]",
                    "source_member_keys_json": "[]",
                }
            ],
            "innovation_details": [
                {
                    "innovation_id": "i",
                    "observation_id": "io",
                    "title_raw": "Alpha",
                    "description": "",
                }
            ],
            "researcher_assertions": [],
            "institution_assertions": [],
            "readiness": (
                [
                    {
                        "innovation_id": "i",
                        "observation_id": "io",
                        "assessment_id": "ia",
                        "scale": "TRL",
                        "end_level": 8,
                        "qualifies": True,
                        "basis": "valid_numeric_trl_8_9",
                    }
                ]
                if readiness
                else []
            ),
            # Readiness context is deliberately not a declared use location.
            "locations": [
                {
                    "location_id": "readiness-place",
                    "entity_id": "i",
                    "observation_id": "io",
                    "location_role": "readiness_location",
                    "province_code": "10",
                    "province_normalized": "Bangkok",
                    "status": "resolved",
                }
            ],
            "identity_decisions": [],
        },
        CANONICAL["pmua_apptech"]: {
            "source_observations": [p_obs],
            "innovations": [
                {
                    "innovation_id": "p",
                    "display_name": "Alpha",
                    "identity_status": "reviewed",
                    "source_ids_json": '["p-1"]',
                    "aliases_json": "[]",
                    "source_member_keys_json": "[]",
                }
            ],
            "innovation_details": [
                {
                    "innovation_id": "p",
                    "observation_id": "po",
                    "source_id": "p-1",
                    "title_raw": "Alpha",
                }
            ],
            "map_area_items": [],
            "description_sections": [],
            "readiness_assessments": [],
            "innovation_area_assertions": (
                [
                    {
                        "assertion_id": "use-place",
                        "innovation_id": "p",
                        "observation_id": "po",
                        "province_code": "10",
                        "province_normalized": "Bangkok",
                        "resolution_status": "resolved",
                        "coverage_eligibility": "eligible_resolved_use",
                        "hierarchy_pairs_json": "[]",
                    }
                ]
                if use_location
                else []
            ),
            "ip_assertions": [],
            "identity_decisions": [],
        },
        CANONICAL["rinmp"]: {
            "source_observations": [r_obs],
            "innovations": [
                {
                    "innovation_id": "r",
                    "display_name": "Gamma",
                    "identity_status": "reviewed",
                    "source_ids_json": '["r-1"]',
                    "aliases_json": "[]",
                    "source_member_keys_json": "[]",
                }
            ],
            "innovation_profiles": [
                {
                    "innovation_id": "r",
                    "observation_id": "ro",
                    "source_id": "r-1",
                    "title_raw": "Gamma",
                }
            ],
            "readiness_assertions": [],
            "location_assertions": [],
            "identity_decisions": [],
        },
        CANONICAL["apptech_mru"]: {
            "source_observations": [],
            "innovations": [],
            "innovation_observations": [],
            "readiness_assessments": [],
            "identity_decisions": [],
        },
    }
    raw_inputs = {source_id: _raw(source_id) for source_id in CANONICAL.values()}
    return source_tables, raw_inputs


def _review(review_id, decision, *members):
    evidence = []
    for source, source_id in members:
        canonical = CANONICAL[source]
        evidence.append(
            {
                "source": source,
                "source_id": source_id,
                "claim": "reviewed identity evidence",
                "locator": f"evidence://{canonical}/run/items.json#data/0",
            }
        )
    return {
        "review_id": review_id,
        "decision": decision,
        "origin": "analyst_review",
        "reason": "synthetic reviewed decision",
        "members": [
            {"source": source, "source_id": source_id} for source, source_id in members
        ],
        "evidence": evidence,
    }


def test_transitive_review_union_cannot_cross_a_protected_boundary():
    source_tables, raw_inputs = _inputs()
    reviews = {
        "cross_source_innovations/reviews/cases.json": [
            _review("ab", "must_link", ("icommunity", "i-1"), ("pmua_apptech", "p-1")),
            _review("ac", "cannot_link", ("icommunity", "i-1"), ("rinmp", "r-1")),
            _review("bc", "must_link", ("pmua_apptech", "p-1"), ("rinmp", "r-1")),
        ]
    }

    with pytest.raises(PipelineError, match="protected component boundary"):
        build_tables(source_tables, reviews, raw_inputs, geography=None)


def test_readiness_and_use_location_remain_separate_supported_assertions():
    source_tables, raw_inputs = _inputs(readiness=True, use_location=True)
    reviews = {
        "cross_source_innovations/reviews/cases.json": [
            _review("ab", "must_link", ("icommunity", "i-1"), ("pmua_apptech", "p-1")),
        ]
    }

    tables = build_tables(source_tables, reviews, raw_inputs, geography=None)

    assert tables["measure_results"] == [
        {
            "measure": "C04_LISTED",
            "value": 2,
            "unit": "distinct_global_innovations",
            "status": "provisional_cross_source",
            "definition": "All source-local listed innovations after reviewed cross-source unions.",
        },
        {
            "measure": "K04",
            "value": 1,
            "unit": "distinct_global_innovations",
            "status": "provisional_cross_source",
            "definition": "Distinct global innovations with at least one eligible qualifying readiness assessment.",
        },
    ]
    assert {row["location_id"] for row in tables["innovation_use_locations"]} == {
        "use-place:0"
    }
    assert len(tables["province_k04_contributions"]) == 1
    assert tables["province_k04_contributions"][0]["province_code"] == "10"


def test_review_evidence_locator_must_resolve_to_the_current_source_record():
    source_tables, raw_inputs = _inputs()
    review = _review("ab", "must_link", ("icommunity", "i-1"), ("pmua_apptech", "p-1"))
    review["evidence"][0]["locator"] = "evidence://f2_icommunity/old/items.json#data/0"

    with pytest.raises(PipelineError, match="stale evidence locator"):
        build_tables(
            source_tables,
            {"cross_source_innovations/reviews/cases.json": [review]},
            raw_inputs,
            geography=None,
        )


def test_review_accepts_only_the_locked_gzip_alias_of_a_resolved_nested_map_pointer():
    source_tables, raw_inputs = _inputs()
    pmua = source_tables[CANONICAL["pmua_apptech"]]
    pmua["source_observations"] = [
        {
            "observation_id": "map-observation",
            "source_id": "map-envelope",
            "source_key": "map",
            "raw_file": "innovation_map_all.json",
            "row_locator": "evidence://f2_target_household/run/innovation_map_all.json#",
            "file_sha256": "expanded-hash",
        }
    ]
    pmua["innovations"] = [
        {
            "innovation_id": "map-local",
            "display_name": "Map innovation",
            "identity_status": "source_map_limited_listing",
            "source_ids_json": '["10095"]',
            "aliases_json": "[]",
            "source_member_keys_json": "[]",
        }
    ]
    pmua["innovation_details"] = []
    pmua["map_area_items"] = [
        {
            "innovation_id": "map-local",
            "map_observation_id": "map-observation",
            "source_id": "10095",
            "title_raw": "Map innovation",
            "source_locator": "prov_data/สุพรรณบุรี/0",
        }
    ]
    raw_inputs[CANONICAL["pmua_apptech"]] = {
        "datasets": {"map": {"prov_data": {"สุพรรณบุรี": [{"prod_id": 10095}]}}},
        "metadata": {
            "map": {
                "source_id": CANONICAL["pmua_apptech"],
                "run_id": "run",
                "file": "innovation_map_all.json",
                "canonical_evidence_path": "innovation_map_all.json.gz",
                "sha256": "expanded-hash",
            }
        },
        "files": [
            {
                "path": "innovation_map_all.json",
                "sha256": "expanded-hash",
                "size": 1,
                "dataset_key": "map",
            },
            {
                "path": "innovation_map_all.json.gz",
                "sha256": "gzip-hash",
                "size": 1,
                "dataset_key": "map",
            },
        ],
    }
    review = _review(
        "map-alias", "must_link", ("icommunity", "i-1"), ("pmua_apptech", "10095")
    )
    review["evidence"][1]["locator"] = (
        "evidence://f2_target_household/run/innovation_map_all.json.gz#prov_data/สุพรรณบุรี/0"
    )

    tables = build_tables(
        source_tables,
        {"cross_source_innovations/reviews/cases.json": [review]},
        raw_inputs,
        geography=None,
    )

    map_record = next(
        row for row in tables["source_records"] if row["source_id"] == "10095"
    )
    assert (
        map_record["raw_file"]
        == "evidence://f2_target_household/run/innovation_map_all.json"
    )
    assert map_record["row_locator"] == "prov_data/สุพรรณบุรี/0"


def test_rinmp_profile_cannot_claim_one_source_id_with_another_observation():
    source_tables, raw_inputs = _inputs()
    rinmp = source_tables[CANONICAL["rinmp"]]
    rinmp["source_observations"][0]["source_id"] = "other-source-id"
    with pytest.raises(PipelineError, match="profile and observation source IDs disagree"):
        build_tables(source_tables, {}, raw_inputs, geography=None)


@pytest.mark.parametrize("kind", ["readiness", "location"])
@pytest.mark.parametrize(
    "pointer",
    [
        "evidence://f2_apptech_mtr/run/items.json#data/0/missing",
        "evidence://f2_apptech_mtr/run/items.json#data/1",
        "evidence://f2_apptech_mtr/run/items.json#data",
        "evidence://f2_apptech_mtr/other-run/items.json#data/0",
        "evidence://f2_apptech_mtr/run/other.json#data/0",
        "evidence://f2_apptech_mru/run/items.json#data/0",
    ],
)
def test_rinmp_assertion_evidence_must_resolve_inside_its_observation(kind, pointer):
    source_tables, raw_inputs = _inputs()
    raw_inputs[CANONICAL["rinmp"]]["datasets"]["items"]["data"].append({"id": "other"})
    row = {
        "innovation_id": "r",
        "observation_id": "ro",
        "source_id": "r-1",
        "source_locator": pointer,
    }
    if kind == "readiness":
        row.update(assertion_id="readiness", scale="TRL", qualifies_k04=False)
        table = "readiness_assertions"
    else:
        row.update(location_id="location", coverage_eligibility="eligible_innovation_use")
        table = "location_assertions"
    source_tables[CANONICAL["rinmp"]][table] = [row]
    with pytest.raises(PipelineError, match="evidence|observation"):
        build_tables(source_tables, {}, raw_inputs, geography=None)


def test_rinmp_readiness_accepts_a_resolving_child_of_its_observation():
    source_tables, raw_inputs = _inputs()
    raw_inputs[CANONICAL["rinmp"]]["datasets"]["items"]["data"][0]["trl"] = 7
    pointer = "evidence://f2_apptech_mtr/run/items.json#data/0/trl"
    source_tables[CANONICAL["rinmp"]]["readiness_assertions"] = [{
        "innovation_id": "r", "observation_id": "ro", "source_id": "r-1",
        "assertion_id": "readiness", "scale": "TRL", "numeric_level": 7,
        "qualifies_k04": False, "source_locator": pointer,
    }]
    tables = build_tables(
        source_tables, {"cross_source_innovations/reviews/cases.json": []},
        raw_inputs, geography=None,
    )
    assert tables["readiness_evidence"][0]["source_locator"] == pointer
