import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools.f2_pipeline.c02_projection import (
    _context_digest,
    apply_c02_projection_policy,
    build_c02_details,
)
from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.field_approval import (
    C02_ACCEPTED_FIELD_REVIEW_STATUS,
    approval_scope_sha256,
    c02_field_review_scope_sha256,
    c02_geography_review_scope_sha256,
    validate_c02_field_review,
    validate_c02_geography_review,
)
from tools.f2_pipeline.full_projection import _item_index


def _policy():
    base = json.loads(
        Path("config/f2_pipeline/public_projection_policy.json").read_text()
    )
    extension = json.loads(
        Path("config/f2_pipeline/c02-projection-policy.v2.json").read_text()
    )
    extension = deepcopy(extension)
    projection = extension["c02_projection"]
    projection["expected_counted_totals"] = {"C02_COMMUNITY": 5}
    context = projection["source_contexts"]["icommunity"]
    context["allowed_role_mappings"] = {
        "community": ["community_innovator"],
        "inventor": ["inventor"],
    }
    context["context_sha256"] = _context_digest(context)
    merged = deepcopy(base)
    merged["detail_policies"].update(extension["detail_policies"])
    merged["c02_projection"] = projection
    merged["c02_field_review"] = extension["c02_field_review"]
    extension["c02_field_review"]["scope_sha256"] = c02_field_review_scope_sha256(
        merged
    )
    return apply_c02_projection_policy(base, extension)


def _accepted_policy(c02_owner_acceptance):
    base = json.loads(
        Path("config/f2_pipeline/public_projection_policy.json").read_text()
    )
    extension = json.loads(
        Path(
            "config/f2_pipeline/c02-projection-policy.accepted-v1.json"
        ).read_text()
    )
    return apply_c02_projection_policy(base, extension, c02_owner_acceptance)


def _pending_geography_policy(c02_owner_acceptance):
    base = json.loads(
        Path("config/f2_pipeline/public_projection_policy.json").read_text()
    )
    extension = json.loads(
        Path(
            "config/f2_pipeline/c02-projection-policy.province-review-v1.json"
        ).read_text()
    )
    return apply_c02_projection_policy(base, extension, c02_owner_acceptance)


def _assertion(
    person,
    role,
    *,
    assertion_id,
    work="",
    raw_name=None,
    source="icommunity",
    missing_work_identity=False,
):
    return {
        "assertion_id": assertion_id,
        "assertion_kind": "source_local_identity",
        "global_person_id": person,
        "source_entity_id": f"{source}:{person}",
        "source": source,
        "raw_name": raw_name or person,
        "role": role,
        "eligible_roles_json": json.dumps(
            {
                "community": ["community_innovator"],
                "inventor": ["inventor"],
            }.get(role, [])
        ),
        "natural_person_status": "supported_natural_person",
        "context_json": "{}",
        "global_innovation_id": work,
        "local_innovation_id": ""
        if missing_work_identity
        else "local-work"
        if not work
        else "",
        "relationship_id": assertion_id,
    }


def _tables():
    people = [
        "global_person_1",
        "global_person_2",
        "global_person_3",
        "global_person_4",
        "global_person_5",
    ]
    assertions = [
        _assertion("global_person_1", "community", assertion_id="a1", work="work-1"),
        _assertion(
            "global_person_1", "community", assertion_id="a1-duplicate", work="work-1"
        ),
        _assertion("global_person_2", "inventor", assertion_id="a2", work="work-1"),
        _assertion(
            "global_person_3",
            "inventor",
            assertion_id="a3",
            raw_name="อาจารย์ ดร.สมชาย ตัวอย่าง",
        ),
        _assertion(
            "global_person_4",
            "inventor",
            assertion_id="a4",
            missing_work_identity=True,
        ),
        _assertion(
            "global_person_5",
            "researcher",
            assertion_id="a5",
            raw_name="x@example.test",
        ),
    ]
    return {
        "entity_contributions": [
            {"measure_id": "C02_COMMUNITY", "entity_id": person}
            for person in people
        ],
        "domains/people/measure_contributions": [
            {
                "measure_id": "C02_COMMUNITY",
                "global_person_id": person,
                "qualifying_assertion_ids_json": json.dumps(ids),
            }
            for person, ids in {
                "global_person_1": ["a1", "a1-duplicate"],
                "global_person_2": ["a2"],
                "global_person_3": ["a3"],
                "global_person_4": ["a4"],
                "global_person_5": ["a5"],
            }.items()
        ],
        "domains/people/global_people": [
            {"global_person_id": person, "identity_status": "source_supported"}
            for person in people
        ],
        "domains/people/person_assertions": assertions,
        "domains/people/person_crosswalk": [
            *[
                {
                    "source_entity_id": f"icommunity:{person}",
                    "global_person_id": person,
                    "source": "icommunity",
                    "display_name": "สมชาย ตัวอย่าง" if person == "global_person_3" else person,
                    "quality_flags_json": (
                        '["incomplete_name", "possible_duplicate"]'
                        if person == "global_person_4"
                        else "[]"
                    ),
                }
                for person in people
            ],
            {
                "source_entity_id": "pmua_apptech:global_person_1",
                "global_person_id": "global_person_1",
                "source": "pmua_apptech",
                "display_name": "global_person_1",
                "quality_flags_json": "[]",
            },
        ],
        "sources/f2_icommunity/innovations": [
            {"innovation_id": "local-work", "display_name": "Local work"}
        ],
        "sources/f2_apptech_mru/innovations": [],
    }


def test_c02_projection_preserves_roles_withholds_fields_and_deduplicates_work():
    details = build_c02_details(
        _tables(), _policy(), {"work-1": ("Public work", "K04")}
    )
    c02 = details["C02_COMMUNITY"]
    assert set(c02["details"]) == {
        "global_person_1",
        "global_person_2",
        "global_person_3",
        "global_person_4",
    }
    assert c02["withheld"] == {
        "global_person_5": "no_approved_qualifying_assertion"
    }
    assert c02["details"]["global_person_3"]["label_availability"] == "available"
    assert c02["details"]["global_person_3"]["label"] == "สมชาย ตัวอย่าง"
    assert c02["details"]["global_person_4"]["flags"]["related_work_count_unavailable"] is True
    assert c02["details"]["global_person_4"]["flags"]["unresolved_identity"] is True
    assert c02["details"]["global_person_4"]["flags"]["possible_duplicate"] is True
    assert c02["details"]["global_person_1"]["flags"]["identity_review"] == {
        "outcome": "source_record_only",
        "merge_scope": None,
        "counting": "separate",
        "name_quality": "supported",
    }
    assert c02["details"]["global_person_4"]["flags"]["identity_review"] == {
        "outcome": "unresolved",
        "merge_scope": None,
        "counting": "separate",
        "name_quality": "supported",
    }
    assert c02["details"]["global_person_1"]["related_work_count"] == 1
    assert (
        c02["details"]["global_person_1"]["relationships"][0]["target_detail"][
            "entity_id"
        ]
        == "work-1"
    )
    assert "target_detail" not in c02["details"]["global_person_3"]["relationships"][0]
    items, _ = _item_index(["C02_COMMUNITY"], details, "f2/topic/k02")
    assert items["global_person_1"]["role_codes"] == ["community_innovator"]
    assert items["global_person_2"]["role_codes"] == ["inventor"]
    assert items["global_person_4"]["related_work_count_unavailable"] is True
    assert items["global_person_1"]["identity_review"]["outcome"] == (
        "source_record_only"
    )
    assert items["global_person_4"]["identity_review"]["outcome"] == "unresolved"
    assert items["global_person_1"]["related_work_count"] == 1
    assert c02["details"]["global_person_1"]["source_ids"] == [
        "f2_icommunity",
        "f2_target_household",
    ]
    assert "example.test" not in json.dumps(details)


def test_c02_projection_publishes_only_reviewed_person_provinces(
    monkeypatch, c02_owner_acceptance
):
    tables = _tables()
    for assertion in tables["domains/people/person_assertions"]:
        assertion["role"] = "community_innovator"
        assertion["eligible_roles_json"] = '["community_innovator"]'
    tables["domains/people/person_location_assertions"] = [
        {
            "location_assertion_id": f"location-{code}",
            "global_person_id": "global_person_1",
            "province_code": code,
            "province_name_th": name,
            "location_role": "source_reported_innovator_location",
            "source": "f2_icommunity",
            "evidence_basis": "exact_source_province_name_lookup",
            "province_resolution_status": "exact_source_province",
            "review_status": "accepted",
            "district_raw": "must not be published",
            "latitude": "13.0",
        }
        for code, name in (("10", "กรุงเทพมหานคร"), ("20", "ชลบุรี"))
    ]
    monkeypatch.setattr(
        "tools.f2_pipeline.c02_projection._membership",
        lambda _tables, _projection: (
            {
                "C02_COMMUNITY": {
                    f"global_person_{index}" for index in range(1, 6)
                }
            },
            {
                ("C02_COMMUNITY", f"global_person_{index}"): {f"a{index}"}
                for index in range(1, 6)
            }
            | {
                ("C02_COMMUNITY", "global_person_1"): {"a1", "a1-duplicate"}
            },
        ),
    )

    details = build_c02_details(
        tables, _pending_geography_policy(c02_owner_acceptance), {}
    )
    first = details["C02_COMMUNITY"]["details"]["global_person_1"]
    unknown = details["C02_COMMUNITY"]["details"]["global_person_2"]

    assert first["province_codes"] == ["10", "20"]
    assert first["locations"] == [
        {
            "province_code": "10",
            "province": "กรุงเทพมหานคร",
            "location_role": "source_reported_innovator_location",
            "source_id": "f2_icommunity",
        },
        {
            "province_code": "20",
            "province": "ชลบุรี",
            "location_role": "source_reported_innovator_location",
            "source_id": "f2_icommunity",
        },
    ]
    assert first["flags"]["geography_not_published"] is False
    assert first["flags"]["person_province_basis"] == (
        "source_reported_innovator_location"
    )
    assert unknown["province_codes"] == []
    assert unknown["locations"] == []
    assert unknown["flags"]["geography_not_published"] is True
    serialized = json.dumps(first, ensure_ascii=False)
    assert "district_raw" not in serialized
    assert "latitude" not in serialized


def test_c02_projection_still_withholds_a_substantive_name_mismatch():
    tables = _tables()
    assertions = {
        row["assertion_id"]: row for row in tables["domains/people/person_assertions"]
    }
    assertions["a3"]["raw_name"] = "different person"
    detail = build_c02_details(tables, _policy(), {})["C02_COMMUNITY"]["details"][
        "global_person_3"
    ]
    assert detail["label_availability"] == "withheld"
    assert detail["label_withholding_reason"] == "public_name_context_not_approved"


def test_c02_review_scope_is_tamper_evident_and_never_promotion_approval():
    base = json.loads(
        Path("config/f2_pipeline/public_projection_policy.json").read_text()
    )
    policy = _policy()
    assert policy["c02_field_review"]["public_promotion_approved"] is False
    assert approval_scope_sha256(base) == approval_scope_sha256(policy)
    assert base["detail_owner_approval"] == policy["detail_owner_approval"]
    assert all(
        "source_allowlists" not in detail
        for detail in policy["detail_policies"].values()
        if detail["adapter"] == "c02_source_scoped_person_projection"
    )

    extension = json.loads(
        Path("config/f2_pipeline/c02-projection-policy.v2.json").read_text()
    )
    extension["c02_projection"]["public_promotion_approved"] = True
    with pytest.raises(PipelineError, match="cannot authorize promotion"):
        apply_c02_projection_policy(base, extension)

    extension = json.loads(
        Path("config/f2_pipeline/c02-projection-policy.v2.json").read_text()
    )
    extension["detail_policies"]["C02_COMMUNITY"]["review_status"] = "tampered"
    with pytest.raises(PipelineError, match="pending review scope"):
        apply_c02_projection_policy(base, extension)


def test_c02_accepted_review_is_exact_and_historical_pending_remains_valid(
    c02_owner_acceptance,
):
    base = json.loads(
        Path("config/f2_pipeline/public_projection_policy.json").read_text()
    )
    pending = apply_c02_projection_policy(
        base,
        json.loads(
            Path("config/f2_pipeline/c02-projection-policy.v2.json").read_text()
        ),
    )
    accepted = _accepted_policy(c02_owner_acceptance)

    assert validate_c02_field_review(pending)["status"] == "pending_owner_acceptance"
    assert (
        validate_c02_field_review(accepted)["status"]
        == C02_ACCEPTED_FIELD_REVIEW_STATUS
    )
    assert (
        accepted["detail_policies"]["C02_COMMUNITY"]["review_status"]
        == C02_ACCEPTED_FIELD_REVIEW_STATUS
    )
    assert accepted["c02_field_review"]["scope_sha256"] == (
        pending["c02_field_review"]["scope_sha256"]
    )
    assert accepted["c02_field_review"]["public_promotion_approved"] is False
    assert accepted["c02_owner_acceptance"]["deployment_approved"] is False


def test_pending_c02_geography_review_preserves_accepted_field_scope(
    c02_owner_acceptance,
):
    base = json.loads(
        Path("config/f2_pipeline/public_projection_policy.json").read_text()
    )
    extension = json.loads(
        Path(
            "config/f2_pipeline/c02-projection-policy.province-review-v1.json"
        ).read_text()
    )

    policy = apply_c02_projection_policy(base, extension, c02_owner_acceptance)

    assert validate_c02_field_review(policy)["status"] == "accepted"
    review = validate_c02_geography_review(policy)
    assert review["status"] == "pending_owner_acceptance"
    assert review["dimension"] == "source_reported_innovator_location"
    assert review["scope_sha256"] == c02_geography_review_scope_sha256(policy)
    assert review["source_candidate_manifest_sha256"] == ""
    assert review["public_promotion_approved"] is False
    assert review["deployment_approved"] is False
    assert "c02_geography_acceptance" not in policy

    extension["c02_geography_review"]["conditions"]["map"] = "province"
    with pytest.raises(PipelineError, match="geography review"):
        apply_c02_projection_policy(base, extension, c02_owner_acceptance)

def test_pending_c02_map_review_versions_the_aggregate_choropleth_scope(
    c02_owner_acceptance,
):
    base = json.loads(
        Path("config/f2_pipeline/public_projection_policy.json").read_text()
    )
    extension = json.loads(
        Path("config/f2_pipeline/c02-projection-policy.map-review-v1.json").read_text()
    )

    policy = apply_c02_projection_policy(base, extension, c02_owner_acceptance)
    review = validate_c02_geography_review(policy)

    assert review["status"] == "pending_owner_acceptance"
    assert review["conditions"]["map"] == "province_aggregate_choropleth_only"
    assert (
        review["conditions"]["publication"]
        == "province_code_name_and_aggregate_distinct_person_count"
    )
    assert policy["private_revision_id"] == (
        "f2-dashboard-snapshot-v3-c02-map-review-v1"
    )
    assert review["scope_sha256"] == c02_geography_review_scope_sha256(policy)


@pytest.mark.parametrize(
    ("target", "key", "value"),
    [
        ("review", "review_id", "wrong-review"),
        ("review", "scope_sha256", "0" * 64),
        ("review", "reviewed_measures", ["C02_COMMUNITY", "C02_BROADER"]),
        ("review", "status", "unknown"),
        ("acceptance", "source_candidate_manifest_sha256", "0" * 64),
        ("acceptance", "review_scope_sha256", "0" * 64),
        ("acceptance", "scope", "all_fields"),
        ("acceptance", "public_promotion_approved", True),
        ("acceptance", "deployment_approved", True),
        ("detail", "review_status", "pending_owner_acceptance"),
    ],
)
def test_c02_accepted_review_rejects_wrong_binding(
    target, key, value, c02_owner_acceptance
):
    base = json.loads(
        Path("config/f2_pipeline/public_projection_policy.json").read_text()
    )
    extension = json.loads(
        Path(
            "config/f2_pipeline/c02-projection-policy.accepted-v1.json"
        ).read_text()
    )
    evidence = c02_owner_acceptance
    if target == "review":
        extension["c02_field_review"][key] = value
    elif target == "detail":
        extension["detail_policies"]["C02_COMMUNITY"][key] = value
    else:
        evidence[key] = value

    with pytest.raises(PipelineError):
        apply_c02_projection_policy(base, extension, evidence)


def test_c02_accepted_review_requires_owner_acceptance_evidence():
    base = json.loads(
        Path("config/f2_pipeline/public_projection_policy.json").read_text()
    )
    extension = json.loads(
        Path(
            "config/f2_pipeline/c02-projection-policy.accepted-v1.json"
        ).read_text()
    )

    with pytest.raises(PipelineError, match="owner acceptance"):
        apply_c02_projection_policy(base, extension)


def test_c02_counted_total_drift_fails_before_public_admission():
    tables = _tables()
    tables["entity_contributions"].pop()
    with pytest.raises(PipelineError, match="counted population differs"):
        build_c02_details(tables, _policy(), {"work-1": ("Public work", "K04")})


def test_c02_organization_admission_is_independent_of_name_and_identity_status():
    policy = _policy()
    context = policy["c02_projection"]["source_contexts"]["icommunity"]
    context["organization_roles"] = {"explicit_affiliation": "affiliated_organization"}
    context["context_sha256"] = _context_digest(context)
    policy["c02_field_review"]["scope_sha256"] = c02_field_review_scope_sha256(policy)
    tables = _tables()
    tables["domains/people/global_people"][0]["identity_status"] = (
        "reviewed_cross_source"
    )
    assertions = {
        row["assertion_id"]: row for row in tables["domains/people/person_assertions"]
    }
    assertions["a3"].update(
        institution_raw="Synthetic Public Organization",
        institution_role="explicit_affiliation",
    )
    assertions["a2"].update(
        institution_raw="private@example.test",
        institution_role="explicit_affiliation",
    )
    details = build_c02_details(tables, policy, {})["C02_COMMUNITY"]["details"]
    assert details["global_person_1"]["identity_status"] == "reviewed_cross_source"
    assert details["global_person_1"]["source_ids"] == [
        "f2_icommunity",
        "f2_target_household",
    ]
    titled = details["global_person_3"]
    assert titled["label_availability"] == "available"
    assert (
        titled["children"]["organizations"][0]["organization"]
        == "Synthetic Public Organization"
    )
    named = details["global_person_2"]
    assert named["label_availability"] == "available"
    assert named["children"]["organizations"] == []
    assert "organizations" in named["flags"]["missing_public_detail_fields"]
    assert named["flags"]["child_dispositions"]["organizations"]["withheld_count"] == 1
    assert "private@example.test" not in json.dumps(details)
