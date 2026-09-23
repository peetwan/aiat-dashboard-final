from types import SimpleNamespace

import pytest

from tools.f2_pipeline.common import Components, PipelineError
from tools.f2_pipeline.domains.people import (
    _assessment_tables,
    _indexes,
    _pair_edges,
    _registry,
    _person_location_tables,
    _resolve_endpoint,
    _validate_runtime_pins,
)
from tools.f2_pipeline.domains.person_sources import PersonSources, SOURCE_ORDER, _Builder
from tools.f2_pipeline.domains.resolution import (
    EvidenceLocatorIndex,
    SOURCE_ALIASES,
    locator_matches,
)


def _entity(entity_id, *, eligible_roles=(), source_ids=()):
    return {
        "source": "icommunity",
        "source_local_id": entity_id.removeprefix("icommunity:"),
        "entity_kind": "person",
        "identity_basis": "source_reviewed_identity",
        "display_name": entity_id,
        "aliases": [entity_id],
        "matching_names": [entity_id],
        "source_ids": list(source_ids),
        "observation_ids": [],
        "identity_status": "source_supported",
        "natural_person_status": "confirmed_natural_person",
        "quality_flags": [],
        "eligible_roles": list(eligible_roles),
    }


def _assertion(assertion_id, entity_id, *, role="", eligible_roles=(), work_id="work"):
    return {
        "assertion_id": assertion_id,
        "assertion_kind": "person_role",
        "source_entity_id": entity_id,
        "source": "icommunity",
        "source_local_id": entity_id.removeprefix("icommunity:"),
        "source_record_id": assertion_id,
        "observation_id": "",
        "source_key": "",
        "raw_name": entity_id,
        "matching_name": entity_id,
        "role": role,
        "eligible_roles": list(eligible_roles),
        "institution_raw": "",
        "institution_role": "",
        "local_innovation_id": "local-work",
        "global_innovation_id": work_id,
        "relationship_id": "",
        "source_locator": "evidence://f2_icommunity/run/items.json#data/0",
        "evidence_text": "",
        "natural_person_status": "confirmed_natural_person",
        "quality_flags": [],
        "context": {},
    }


def test_shared_work_does_not_transfer_role_or_identity():
    left = "icommunity:left"
    right = "icommunity:right"
    bundle = PersonSources(
        entities={
            left: _entity(left, eligible_roles=("community_innovator",)),
            right: _entity(right),
        },
        assertions=[
            _assertion(
                "left-role",
                left,
                role="community_innovator",
                eligible_roles=("community_innovator",),
            ),
            _assertion("right-mention", right, role="researcher", work_id="work"),
        ],
        admission=[],
        input_files=[],
    )

    people, crosswalk, _ = _registry(bundle, Components(bundle.entities, set()), set())

    assert len(people) == 2
    assert sum(row["community_innovator_eligible"] == "True" for row in people) == 1
    assert len({row["global_person_id"] for row in crosswalk}) == 2


def test_registry_preserves_legacy_global_person_id_encoding():
    left = "icommunity:person-1"
    right = "rinmp:person-2"
    bundle = PersonSources(
        entities={left: _entity(left), right: _entity(right)},
        assertions=[],
        admission=[],
        input_files=[],
    )
    components = Components(bundle.entities, set())
    components.merge(right, left)

    people, crosswalk, _ = _registry(bundle, components, set())

    assert [row["global_person_id"] for row in people] == [
        "global_person_30b9102ce6824e001ab5"
    ]
    assert {row["global_person_id"] for row in crosswalk} == {
        "global_person_30b9102ce6824e001ab5"
    }


def test_complete_assessment_admission_keeps_scores_within_one_context():
    source_tables = {
        "f2_icommunity": {
            "assessment_observations": [
                {
                    "assessment_id": "complete",
                    "person_id": "p",
                    "observation_id": "one",
                    "project_id": "project",
                },
                {
                    "assessment_id": "incomplete",
                    "person_id": "p",
                    "observation_id": "two",
                    "project_id": "project",
                },
            ],
            "development_assessments": [
                {
                    "assessment_id": "complete",
                    "person_id": "p",
                    "assessment_period": "paired",
                    "complete": "True",
                },
                {
                    "assessment_id": "incomplete",
                    "person_id": "p",
                    "assessment_period": "paired",
                    "complete": "False",
                },
            ],
            "development_scores": [
                {
                    "assessment_id": "complete",
                    "person_id": "p",
                    "dimension": "knowledge",
                    "start_score": 1,
                    "current_score": 2,
                    "delta": 1,
                },
                {
                    "assessment_id": "complete",
                    "person_id": "p",
                    "dimension": "skill",
                    "start_score": 2,
                    "current_score": 2,
                    "delta": 0,
                },
                {
                    "assessment_id": "complete",
                    "person_id": "p",
                    "dimension": "attitude",
                    "start_score": 3,
                    "current_score": 2,
                    "delta": -1,
                },
                {
                    "assessment_id": "incomplete",
                    "person_id": "p",
                    "dimension": "knowledge",
                    "start_score": 1,
                    "current_score": 4,
                    "delta": 3,
                },
                {
                    "assessment_id": "incomplete",
                    "person_id": "p",
                    "dimension": "skill",
                    "start_score": 1,
                    "current_score": 4,
                    "delta": 3,
                },
            ],
        }
    }

    observations, assessments, scores, admission = _assessment_tables(
        source_tables, {"icommunity:p": "global-p"}
    )

    by_id = {row["assessment_id"]: row for row in assessments}
    decisions = {row["assessment_id"]: row["decision"] for row in admission}
    assert by_id["complete"]["complete"] == "True"
    assert by_id["complete"]["any_increase"] == "True"
    assert by_id["complete"]["mixed_change"] == "True"
    assert decisions == {
        "complete": "admit_complete_paired_assessment",
        "incomplete": "retain_incomplete_assessment_evidence",
    }
    assert {row["assessment_id"] for row in observations + scores} == {
        "complete",
        "incomplete",
    }


def test_person_location_admission_is_province_only_and_reconciled():
    source_tables = {
        "f2_icommunity": {
            "locations": [
                {
                    "location_id": "accepted-1",
                    "observation_id": "observation-1",
                    "entity_id": "source-person",
                    "location_role": "source_person_location",
                    "province_code": "10",
                    "status": "hierarchy_unresolved",
                    "district_raw": "must not escape",
                    "latitude": "13.0",
                },
                {
                    "location_id": "accepted-2",
                    "observation_id": "observation-2",
                    "entity_id": "source-person",
                    "location_role": "source_person_location",
                    "province_code": "10",
                    "status": "hierarchy_match",
                },
                {
                    "location_id": "conflict",
                    "observation_id": "observation-3",
                    "entity_id": "source-person",
                    "location_role": "source_person_location",
                    "province_code": "20",
                    "status": "source_geocode_conflict",
                },
                {
                    "location_id": "unknown",
                    "observation_id": "observation-4",
                    "entity_id": "source-person",
                    "location_role": "source_person_location",
                    "province_code": "",
                    "status": "hierarchy_unresolved",
                },
                {
                    "location_id": "organization-location",
                    "observation_id": "observation-5",
                    "entity_id": "source-person",
                    "location_role": "organization_location",
                    "province_code": "20",
                    "status": "hierarchy_match",
                },
            ]
        }
    }
    geography = SimpleNamespace(
        provinces=[
            {"provinceCode": 10, "provinceNameTh": "กรุงเทพมหานคร"},
            {"provinceCode": 20, "provinceNameTh": "ชลบุรี"},
        ]
    )

    admission, assertions = _person_location_tables(
        source_tables,
        {"icommunity:source-person": "global-person"},
        geography,
    )

    assert [row["decision"] for row in admission] == [
        "accept_exact_source_province",
        "accept_exact_source_province",
        "exclude_source_geocode_conflict",
        "exclude_unknown_province",
    ]
    assert len(assertions) == 1
    assertion = assertions[0]
    assert assertion["global_person_id"] == "global-person"
    assert assertion["province_code"] == "10"
    assert assertion["province_name_th"] == "กรุงเทพมหานคร"
    assert assertion["location_role"] == "source_reported_innovator_location"
    assert assertion["source_location_ids_json"] == '["accepted-1","accepted-2"]'
    assert not (
        {"district_raw", "latitude", "source_geocode"}
        & set(admission[0])
        & set(assertion)
    )


def test_person_location_assertions_join_by_source_identity_and_allow_multiple_provinces():
    source_tables = {
        "f2_icommunity": {
            "locations": [
                {
                    "location_id": f"location-{code}",
                    "observation_id": f"observation-{code}",
                    "entity_id": "mapped-person",
                    "location_role": "source_person_location",
                    "province_code": code,
                    "status": "hierarchy_unresolved",
                }
                for code in ("10", "20")
            ]
            + [
                {
                    "location_id": "unmapped",
                    "observation_id": "same-name-is-not-an-identity",
                    "entity_id": "unmapped-person",
                    "location_role": "source_person_location",
                    "province_code": "10",
                    "status": "hierarchy_match",
                }
            ]
        }
    }
    geography = SimpleNamespace(
        provinces=[
            {"provinceCode": 10, "provinceNameTh": "กรุงเทพมหานคร"},
            {"provinceCode": 20, "provinceNameTh": "ชลบุรี"},
        ]
    )

    admission, assertions = _person_location_tables(
        source_tables,
        {"icommunity:mapped-person": "global-person"},
        geography,
    )

    assert {
        (row["global_person_id"], row["province_code"]) for row in assertions
    } == {("global-person", "10"), ("global-person", "20")}
    assert admission[-1]["decision"] == "exclude_missing_global_person"
    assert admission[-1]["global_person_id"] == ""


def test_post_v2_source_correction_remaps_old_endpoints_to_one_current_entity():
    entity_id = "icommunity:corrected"
    bundle = PersonSources(
        entities={entity_id: _entity(entity_id, source_ids=("old-left", "old-right"))},
        assertions=[],
        admission=[],
        input_files=[],
    )
    indexes = _indexes(bundle)

    left = _resolve_endpoint(
        {"source": "icommunity", "source_ids": ["old-left"], "names": [entity_id]},
        bundle,
        indexes,
    )
    right = _resolve_endpoint(
        {"source": "icommunity", "source_ids": ["old-right"], "names": [entity_id]},
        bundle,
        indexes,
    )

    assert left.entity_ids == (entity_id,)
    assert right.entity_ids == (entity_id,)
    assert left.method == right.method == "reviewed_name_and_source_lineage"
    edges, _ = _pair_edges(left.entity_ids, right.entity_ids, bundle)
    assert edges == []


def test_locator_index_is_differentially_equivalent_to_review_matching():
    current = [
        "evidence://f2_icommunity/run/items.json#data",
        "evidence://f2_icommunity/run/items.json#data/5",
        "evidence://f2_icommunity/run/items.json#data/5/name",
        "evidence://f2_icommunity/run/items.json#data/6",
        "evidence://f2_icommunity/other/items.json#data/5",
        "evidence://f2_target_household/run/items.json#data/5",
        "evidence://f2_icommunity/run/other.json#data/5",
        "evidence://f2_icommunity/run/items.json#",
    ]
    reviews = [
        "evidence://f2_icommunity/run/items.json.gz#data/5",
        "evidence://f2_icommunity/run/items.json.gz#data",
        "evidence://f2_icommunity/run/items.json.gz#data/6",
        "evidence://f2_icommunity/run/items.json.gz#",
        "evidence://f2_icommunity/other/items.json.gz#data/5",
        "evidence://f2_target_household/run/items.json.gz#data/5",
    ]
    index = EvidenceLocatorIndex()
    for ordinal, locator in enumerate(current):
        index.add(locator, ordinal)

    for review in reviews:
        expected = [
            ordinal
            for ordinal, locator in enumerate(current)
            if locator_matches(review, locator)
        ]
        assert index.related(review) == expected


def test_source_local_runtime_pin_requires_a_fresh_injected_table():
    raw_inputs = {}
    source_tables = {}
    for source in (
        "icommunity",
        "pmua_apptech",
        "apptech_mru",
        "rinmp",
        "atlocal",
        "cultural_map",
    ):
        canonical = SOURCE_ALIASES[source][-1]
        raw_inputs[canonical] = {
            "metadata": {
                "data": {
                    "source_id": canonical,
                    "run_id": "run",
                    "file": "data.json",
                    "sha256": "hash",
                }
            },
            "files": [
                {
                    "path": "data.json",
                    "sha256": "hash",
                    "size": 1,
                    "dataset_key": "data",
                }
            ],
        }
        source_tables[canonical] = {"people": []}
    runtime = {
        "schema_version": 1,
        "source_input_pins": [
            {
                "path": "normalized://source_local/icommunity-v1/people.csv",
                "sha256": "obsolete-derived-hash",
            }
        ],
    }

    _validate_runtime_pins(
        runtime, {}, raw_inputs, source_tables, {"innovation_crosswalk": []}
    )
    del source_tables[SOURCE_ALIASES["icommunity"][-1]]["people"]

    with pytest.raises(PipelineError, match="Missing normalized producer endpoint"):
        _validate_runtime_pins(
            runtime, {}, raw_inputs, source_tables, {"innovation_crosswalk": []}
        )


def _source_assertion_builder(source):
    canonical = SOURCE_ALIASES[source][-1]
    source_tables = {SOURCE_ALIASES[name][-1]: {} for name in SOURCE_ORDER}
    source_tables[canonical] = {"source_observations": [{
        "observation_id": "observation", "source_id": "record",
        "raw_file": "items.json", "row_locator": "data/0", "file_sha256": "hash",
    }]}
    raw_inputs = {key: {} for key in source_tables}
    raw_inputs[canonical] = {
        "datasets": {"items": {"data": [{"role": "inventor"}, {"role": "other"}]}},
        "metadata": {"items": {
            "source_id": canonical, "run_id": "run",
            "file": "items.json", "sha256": "hash",
        }},
    }
    builder = _Builder(source_tables, {}, raw_inputs, {"innovation_crosswalk": []})
    pilot = "apptech-mru-v1" if source == "apptech_mru" else "rinmp-v1"
    builder.load_observations(source, pilot)
    return builder


@pytest.mark.parametrize("source", ["apptech_mru", "rinmp"])
@pytest.mark.parametrize("pointer", ["data/0/missing", "data/1/role", "data"])
def test_person_assertion_rejects_missing_or_foreign_observation_evidence(source, pointer):
    builder = _source_assertion_builder(source)
    canonical = SOURCE_ALIASES[source][-1]
    with pytest.raises(PipelineError, match="evidence|observation"):
        builder.add_assertion(
            assertion_id="assertion", assertion_kind="evidence_only",
            source=source, observation_id="observation",
            source_locator=f"evidence://{canonical}/run/items.json#{pointer}",
        )


@pytest.mark.parametrize("source", ["apptech_mru", "rinmp"])
@pytest.mark.parametrize("legacy", [False, True])
def test_person_assertion_preserves_valid_owned_evidence(source, legacy):
    builder = _source_assertion_builder(source)
    canonical = SOURCE_ALIASES[source][-1]
    expected = f"evidence://{canonical}/run/items.json#data/0/role"
    builder.add_assertion(
        assertion_id="assertion", assertion_kind="evidence_only",
        source=source, observation_id="observation",
        source_locator="legacy/items.json#data/0/role" if legacy else expected,
    )
    assert builder.finish().assertions[0]["source_locator"] == expected
