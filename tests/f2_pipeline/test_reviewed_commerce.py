import pytest

from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.domains.reviewed_commerce import (
    LEARNING_CULTURAL_BUSINESS_BASIS,
    LEARNING_CULTURAL_BUSINESS_CONTRACT,
    _build_offering_families,
    _load_reviews,
    _reconcile,
    _validate_learning_cultural_business_candidate,
    _validate_reviews,
    _validate_pin,
)


def _candidate(candidate_id, kind="operator", status="supported"):
    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "status": status,
        "source": "rinmp",
        "source_local_id": candidate_id,
        "display_name": candidate_id,
        "aliases": [],
        "basis": "source_reported_business"
        if kind == "operator"
        else "source_reported_offering",
        "output_type": "product" if kind == "offering" else "",
        "unit_basis": "one form" if kind == "offering" else "",
    }


def _raw_bundle(source_id):
    return {
        "datasets": {
            "records": {"data": [{"text": "same quote"}, {"text": "same quote"}]}
        },
        "metadata": {
            "records": {
                "source_id": source_id,
                "run_id": "run",
                "file": "records.json",
                "canonical_evidence_path": "records.json.gz",
                "sha256": "expanded-hash",
            }
        },
        "files": [
            {
                "path": "records.json.gz",
                "dataset_key": "records",
                "sha256": "raw-hash",
            }
        ],
    }


def _observation(source_id, record_id, row):
    return {
        "observation_id": f"observation-{record_id}",
        "source_id": record_id,
        "source_key": f"records:{record_id}",
        "raw_file": f"evidence://{source_id}/run/records.json.gz",
        "row_locator": f"data/{row}",
        "file_sha256": "raw-hash",
    }


def _review_with_evidence(source, source_record_id, locator):
    candidate = _candidate(f"{source}:reviewed")
    candidate.update(
        {
            "source": source,
            "source_local_id": "reviewed",
            "reason": "Synthetic reviewed extraction.",
            "evidence": [
                {
                    "source_record_id": source_record_id,
                    "raw_locator": locator,
                    "quote": "same quote",
                }
            ],
        }
    )
    return {
        "candidates": [candidate],
        "identity_decisions": [],
        "relationships": [],
        "aggregate_claims": [],
        "counting_groups": [],
    }


def _pin(source_id):
    relative = f"{source_id}/run/records.json.gz"
    return {
        relative: {
            "relative_path": relative,
            "source_id": source_id,
            "run_id": "run",
            "dataset_key": "records",
            "sha256": "raw-hash",
        }
    }


def test_plain_raw_file_pin_needs_no_gzip_alias_but_keeps_exact_byte_hash():
    source_id = "f2_apptech_mtr"
    raw = _raw_bundle(source_id)
    raw["metadata"]["records"].pop("canonical_evidence_path")
    raw["files"][0]["path"] = "records.json"
    pin = next(iter(_pin(source_id).values()))
    pin["relative_path"] = f"{source_id}/run/records.json"
    _validate_pin(pin, {source_id: raw})
    pin["sha256"] = "wrong-byte-hash"
    with pytest.raises(PipelineError, match="Stale reviewed commerce evidence pin"):
        _validate_pin(pin, {source_id: raw})


def test_private_schema_v2_ledgers_merge_by_review_family():
    candidate = _candidate("candidate")
    reviews = {
        "reviewed_commerce/candidates.json": {
            "schema_version": 2,
            "candidates": [candidate],
            "identity_decisions": [],
            "relationships": [],
            "aggregate_claims": [],
            "evidence_pins": [
                {
                    "relative_path": "f2_apptech_mtr/run/app_tech.json.gz",
                    "source_id": "f2_apptech_mtr",
                    "run_id": "run",
                    "dataset_key": "app_tech",
                    "sha256": "hash",
                }
            ],
        },
        "reviewed_commerce/product_families.json": {
            "schema_version": 2,
            "counting_groups": [{"family_id": "family"}],
            "evidence_pins": [],
        },
    }

    combined, pins = _load_reviews(reviews)

    assert combined["candidates"] == [candidate]
    assert combined["counting_groups"] == [{"family_id": "family"}]
    assert set(pins) == {"f2_apptech_mtr/run/app_tech.json.gz"}


def test_reviewed_bridge_cannot_collapse_two_baseline_operator_identities():
    candidate = _candidate("candidate")
    review = {
        "candidates": [candidate],
        "identity_decisions": [
            {
                "review_id": "left",
                "left": "candidate",
                "right": "operator_left",
                "decision": "match",
                "reason": "reviewed left identity",
                "evidence_refs": ["candidate", "operator_left"],
            },
            {
                "review_id": "right",
                "left": "candidate",
                "right": "operator_right",
                "decision": "match",
                "reason": "reviewed right identity",
                "evidence_refs": ["candidate", "operator_right"],
            },
        ],
    }
    tables = {
        "global_operators": [
            {"global_operator_id": "operator_left"},
            {"global_operator_id": "operator_right"},
        ],
        "global_offerings": [],
    }

    with pytest.raises(PipelineError, match="distinct baseline identities"):
        _reconcile(review, tables)


def test_non_supported_candidates_remain_reviewed_without_becoming_entities():
    review = {
        "candidates": [
            _candidate("supported"),
            _candidate("unresolved", status="unresolved"),
            _candidate("not-established", status="not_established"),
        ],
        "identity_decisions": [],
    }
    tables = {"global_operators": [], "global_offerings": []}

    mapping, crosswalk, _ = _reconcile(review, tables)

    assert set(mapping) == {"supported"}
    assert [row["candidate_id"] for row in crosswalk] == ["supported"]
    assert {row["global_operator_id"] for row in tables["global_operators"]} == {
        mapping["supported"]
    }


def test_learning_cultural_business_contract_separates_eligibility_from_name_quality():
    candidate = {
        **_candidate("learning:business"),
        "source": "learning_area_based",
        "status": "supported",
        "basis": LEARNING_CULTURAL_BUSINESS_BASIS,
        "eligibility_contract": LEARNING_CULTURAL_BUSINESS_CONTRACT,
        "identity_quality": "community_or_support_label",
        "identity_review_note": "The source label is ambiguous but eligibility is contractual.",
    }

    assert _validate_learning_cultural_business_candidate(candidate) is True


def test_learning_cultural_business_missing_name_requires_explicit_placeholder():
    candidate = {
        **_candidate("learning:missing"),
        "source": "learning_area_based",
        "display_name": "",
        "status": "supported",
        "basis": LEARNING_CULTURAL_BUSINESS_BASIS,
        "eligibility_contract": LEARNING_CULTURAL_BUSINESS_CONTRACT,
        "identity_quality": "missing_source_name",
        "identity_review_note": "The source did not provide a business name.",
    }

    with pytest.raises(
        PipelineError,
        match="missing-name placeholder is inconsistent",
    ):
        _validate_learning_cultural_business_candidate(candidate)

    candidate["display_name"] = "Name unavailable"
    assert _validate_learning_cultural_business_candidate(candidate) is True




def test_reviewed_family_counts_variants_once_and_retains_range_evidence():
    tables = {
        "global_offerings": [
            {
                "global_offering_id": "offering_one",
                "display_name": "one",
                "identity_status": "source_local_identity",
            },
            {
                "global_offering_id": "offering_two",
                "display_name": "two",
                "identity_status": "source_local_identity",
            },
            {
                "global_offering_id": "offering_range",
                "display_name": "range",
                "identity_status": "source_local_identity",
            },
        ]
    }
    mapping = {
        "candidate_one": "offering_one",
        "candidate_two": "offering_two",
        "candidate_range": "offering_range",
    }
    review = {
        "counting_groups": [
            {
                "family_id": "reviewed_family",
                "display_name": "reviewed variants",
                "basis": "catalogue_family_and_variants",
                "reason": "Two named variants with one broad catalogue range retained as evidence.",
                "members": [
                    {"entity_id": "candidate_one", "role": "variant"},
                    {"entity_id": "candidate_two", "role": "variant"},
                    {"entity_id": "candidate_range", "role": "range_evidence"},
                ],
                "evidence_refs": ["candidate_one", "candidate_two", "candidate_range"],
            }
        ]
    }

    _build_offering_families(review, tables, mapping)

    assert [row["family_id"] for row in tables["offering_families"]] == [
        "reviewed_family"
    ]
    assert {row["global_offering_id"] for row in tables["offering_family_members"]} == {
        "offering_one",
        "offering_two",
        "offering_range",
    }
    assert len(tables["global_offerings"]) == 3


def test_candidate_cannot_cite_evidence_from_another_source():
    rinmp = "f2_apptech_mtr"
    icommunity = "f2_icommunity"
    review = _review_with_evidence(
        "rinmp",
        "record-one",
        f"evidence://{icommunity}/run/records.json.gz#data/0/text",
    )
    source_tables = {
        rinmp: {
            "source_observations": [_observation(rinmp, "record-one", 0)],
        },
    }
    raw_inputs = {
        rinmp: _raw_bundle(rinmp),
        icommunity: _raw_bundle(icommunity),
    }

    with pytest.raises(PipelineError, match="belongs to another source"):
        _validate_reviews(
            review,
            _pin(icommunity),
            source_tables,
            raw_inputs,
            {"innovation_crosswalk": []},
        )


def test_candidate_cannot_attach_another_record_quote_from_same_source():
    rinmp = "f2_apptech_mtr"
    review = _review_with_evidence(
        "rinmp",
        "record-one",
        f"evidence://{rinmp}/run/records.json.gz#data/1/text",
    )
    source_tables = {
        rinmp: {
            "source_observations": [
                _observation(rinmp, "record-one", 0),
                _observation(rinmp, "record-two", 1),
            ],
        },
    }

    with pytest.raises(PipelineError, match="belongs to another source record"):
        _validate_reviews(
            review,
            _pin(rinmp),
            source_tables,
            {rinmp: _raw_bundle(rinmp)},
            {"innovation_crosswalk": []},
        )


def test_duplicate_innovation_source_id_is_scoped_to_the_cited_record():
    rinmp = "f2_apptech_mtr"
    first = {
        **_observation(rinmp, "shared-record", 0),
        "observation_id": "observation-one",
    }
    second = {
        **_observation(rinmp, "shared-record", 1),
        "observation_id": "observation-two",
    }
    source_tables = {rinmp: {"source_observations": [first, second]}}
    innovation_tables = {
        "source_records": [
            {
                **first,
                "source": "rinmp",
                "local_innovation_id": "local-one",
                "global_innovation_id": "innovation-one",
            },
            {
                **second,
                "source": "rinmp",
                "local_innovation_id": "local-two",
                "global_innovation_id": "innovation-two",
            },
        ],
    }
    locator = f"evidence://{rinmp}/run/records.json.gz#data/0/text"
    review = _review_with_evidence("rinmp", "shared-record", locator)
    review["candidates"][0]["evidence"][0]["global_innovation_id"] = "innovation-one"

    claims = _validate_reviews(
        review,
        _pin(rinmp),
        source_tables,
        {rinmp: _raw_bundle(rinmp)},
        innovation_tables,
    )

    assert claims[0]["global_innovation_id"] == "innovation-one"

    wrong_review = _review_with_evidence("rinmp", "shared-record", locator)
    wrong_review["candidates"][0]["evidence"][0]["global_innovation_id"] = (
        "innovation-two"
    )
    with pytest.raises(PipelineError, match="belongs to another innovation"):
        _validate_reviews(
            wrong_review,
            _pin(rinmp),
            source_tables,
            {rinmp: _raw_bundle(rinmp)},
            innovation_tables,
        )


def test_explicit_citation_record_preserves_context_and_validates_origin():
    rinmp = "f2_apptech_mtr"
    source_tables = {
        rinmp: {
            "source_observations": [
                _observation(rinmp, "context-record", 0),
                _observation(rinmp, "citation-record", 1),
            ],
        },
    }
    locator = f"evidence://{rinmp}/run/records.json.gz#data/1/text"
    review = _review_with_evidence("rinmp", "context-record", locator)
    review["candidates"][0]["evidence"][0]["citation_source_record_id"] = (
        "citation-record"
    )

    claims = _validate_reviews(
        review,
        _pin(rinmp),
        source_tables,
        {rinmp: _raw_bundle(rinmp)},
        {"source_records": []},
    )

    assert claims[0]["source_record_id"] == "context-record"
    assert claims[0]["citation_source_record_id"] == "citation-record"

    wrong_review = _review_with_evidence("rinmp", "context-record", locator)
    wrong_review["candidates"][0]["evidence"][0]["citation_source_record_id"] = (
        "missing-record"
    )
    with pytest.raises(PipelineError, match="belongs to another source record"):
        _validate_reviews(
            wrong_review,
            _pin(rinmp),
            source_tables,
            {rinmp: _raw_bundle(rinmp)},
            {"source_records": []},
        )
