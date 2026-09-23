"""Validate owner approval for a fixed subset of staged public detail fields."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .common import PipelineError, canonical_json

APPROVAL_V1_ID = "f2-public-fields-owner-approval-v1"
APPROVAL_V2_ID = "f2-public-fields-owner-approval-v2"
APPROVAL_ID = APPROVAL_V1_ID
V1_APPROVED_DETAIL_MEASURES = frozenset(
    {"C04_LISTED", "C08_PARTICIPATING", "K03", "K04", "K05", "K07"}
)
V2_APPROVED_DETAIL_MEASURES = frozenset(
    {
        "C04_LISTED",
        "C08_PARTICIPATING",
        "K01B",
        "K03",
        "K04",
        "K05",
        "K07",
        "K12",
    }
)
APPROVED_DETAIL_MEASURES = V1_APPROVED_DETAIL_MEASURES
PARTIAL_FIELD_APPROVAL_STATUS = "partial_owner_field_approval"
ALL_FIELDS_FIELD_APPROVAL_STATUS = "all_fields_owner_field_approval"
PENDING_FIELD_APPROVAL_STATUS = "pending_owner_acceptance"
C02_FIELD_REVIEW_ID = "f2-c02-person-fields-review-v2"
C02_REVIEWED_DETAIL_MEASURES = frozenset({"C02_COMMUNITY"})
C02_FIELD_REVIEW_CONDITIONS = {
    "membership": "accepted_c02_assertion_roster_preserved",
    "identity": "accepted_global_person_id_and_uncertainty_preserved",
    "fields": "source_scoped_public_work_attribution_only",
    "geography": "national_only_no_person_geography_or_map",
    "promotion": "separate_authorization_required",
}
C02_PENDING_FIELD_REVIEW_STATUS = "pending_owner_acceptance"
C02_ACCEPTED_FIELD_REVIEW_STATUS = "accepted"
C02_OWNER_ACCEPTANCE_ID = "f2-c02-person-fields-owner-acceptance-v1"
C02_REVIEWED_SOURCE_MANIFEST_SHA256 = (
    "a25fe40d8df8c55c721bf4949135c69aa66d1f11f709099b56762925b4f03053"
)
C02_REVIEW_SCOPE_SHA256 = (
    "0a009ca18932b991dfe54161ed57bc23db2c1ccbeeefa3b61df7d39b53ed6541"
)
C02_PRIVATE_REVISIONS = {
    C02_PENDING_FIELD_REVIEW_STATUS: "f2-dashboard-snapshot-v3-c02-review-v2",
    C02_ACCEPTED_FIELD_REVIEW_STATUS: "f2-dashboard-snapshot-v3-c02-accepted-v1",
}
C02_OWNER_ACCEPTANCE_KEYS = {
    "schema_version",
    "acceptance_id",
    "acceptance_status",
    "review_id",
    "reviewed_measures",
    "review_scope_sha256",
    "source_candidate_manifest_sha256",
    "scope",
    "public_promotion_approved",
    "deployment_approved",
}

C02_GEOGRAPHY_REVIEW_ID = "f2-c02-source-reported-innovator-province-review-v1"
C02_GEOGRAPHY_ACCEPTANCE_ID = (
    "f2-c02-source-reported-innovator-province-acceptance-v1"
)
C02_GEOGRAPHY_DIMENSION = "source_reported_innovator_location"
C02_GEOGRAPHY_REVIEW_CONDITIONS = {
    "identity_join": "reviewed_source_local_identity_only",
    "admission": "exact_source_province_excluding_geocode_conflicts",
    "publication": "province_code_and_name_only",
    "unknown_geography": "retained_in_national_population_only",
    "multiplicity": "multiple_memberships_nonadditive",
    "map": "unavailable",
    "promotion": "separate_local_authorization_required",
}
C02_GEOGRAPHY_PRIVATE_REVISIONS = {
    C02_PENDING_FIELD_REVIEW_STATUS: (
        "f2-dashboard-snapshot-v3-c02-province-review-v1"
    ),
    C02_ACCEPTED_FIELD_REVIEW_STATUS: (
        "f2-dashboard-snapshot-v3-c02-province-accepted-v1"
    ),
}
C02_MAP_REVIEW_ID = "f2-c02-source-reported-innovator-province-map-review-v1"
C02_MAP_ACCEPTANCE_ID = "f2-c02-source-reported-innovator-province-map-acceptance-v1"
C02_MAP_REVIEW_CONDITIONS = {
    "identity_join": "reviewed_source_local_identity_only",
    "admission": "exact_source_province_excluding_geocode_conflicts",
    "publication": "province_code_name_and_aggregate_distinct_person_count",
    "unknown_geography": "retained_in_national_population_only",
    "multiplicity": "multiple_memberships_nonadditive",
    "map": "province_aggregate_choropleth_only",
    "promotion": "separate_local_authorization_required",
}
C02_MAP_PRIVATE_REVISIONS = {
    C02_PENDING_FIELD_REVIEW_STATUS: "f2-dashboard-snapshot-v3-c02-map-review-v1",
    C02_ACCEPTED_FIELD_REVIEW_STATUS: "f2-dashboard-snapshot-v3-c02-map-accepted-v1",
}
C02_GEOGRAPHY_REVIEW_SPECS = {
    C02_GEOGRAPHY_REVIEW_ID: {
        "acceptance_id": C02_GEOGRAPHY_ACCEPTANCE_ID,
        "conditions": C02_GEOGRAPHY_REVIEW_CONDITIONS,
        "private_revisions": C02_GEOGRAPHY_PRIVATE_REVISIONS,
        "scope": "c02_source_reported_innovator_province_only",
    },
    C02_MAP_REVIEW_ID: {
        "acceptance_id": C02_MAP_ACCEPTANCE_ID,
        "conditions": C02_MAP_REVIEW_CONDITIONS,
        "private_revisions": C02_MAP_PRIVATE_REVISIONS,
        "scope": "c02_source_reported_innovator_province_aggregate_map_only",
    },
}
C02_GEOGRAPHY_ACCEPTANCE_KEYS = {
    "schema_version",
    "acceptance_id",
    "acceptance_status",
    "review_id",
    "reviewed_measures",
    "review_scope_sha256",
    "source_candidate_manifest_sha256",
    "dimension",
    "scope",
    "local_promotion_approved",
    "deployment_approved",
}

V1_APPROVAL_CONDITIONS = {
    "core_fields": "source_scoped_matrix_with_exclusions_and_uncertainty",
    "location_precision": "source_supported_province_district_subdistrict",
    "location_roles": "subject_owned_no_substitution",
    "product_prices": "source_reported_per_offering_with_unit_and_snapshot",
    "zero_price_label": "price unspecified/source reports 0",
    "media": "source_attributed_references_only",
    "participation": "not_proven_improvement",
    "time": "snapshot_based_no_year_filter",
}
V2_APPROVAL_CONDITIONS = {
    **V1_APPROVAL_CONDITIONS,
    "cultural_title": "CD-5342_title_withheld_pending_review",
    "counts": "existing_measure_counts_unchanged",
    "identity_uncertainty": "preserve_provisional_and_unresolved_identities",
    "privacy_exclusions": "existing_field_level_exclusions_remain",
}
APPROVAL_CONDITIONS = V1_APPROVAL_CONDITIONS
_APPROVAL_KEYS = {
    "approval_id",
    "status",
    "approved_measures",
    "public_promotion_approved",
    "conditions",
    "scope_sha256",
}

_APPROVAL_SPECS = {
    APPROVAL_V1_ID: (
        V1_APPROVED_DETAIL_MEASURES,
        V1_APPROVAL_CONDITIONS,
        PARTIAL_FIELD_APPROVAL_STATUS,
    ),
    APPROVAL_V2_ID: (
        V2_APPROVED_DETAIL_MEASURES,
        V2_APPROVAL_CONDITIONS,
        ALL_FIELDS_FIELD_APPROVAL_STATUS,
    ),
}


def approved_detail_measures(approval: dict | None) -> frozenset[str]:
    """Return the exact accepted detail measures for validated approval metadata."""
    if approval is None:
        return frozenset()
    return _APPROVAL_SPECS[approval["approval_id"]][0]


def approval_review_status(approval: dict | None) -> str:
    """Return the root review status represented by validated approval metadata."""
    if approval is None:
        return PENDING_FIELD_APPROVAL_STATUS
    return _APPROVAL_SPECS[approval["approval_id"]][2]


def _approval_spec(approval: dict) -> tuple[frozenset[str], dict, str]:
    approval_id = approval.get("approval_id")
    try:
        return _APPROVAL_SPECS[approval_id]
    except TypeError:
        pass
    except KeyError:
        pass
    raise PipelineError("Detail owner approval does not match an accepted version")


def _approved_measures(policy: dict) -> list[str]:
    approval = policy.get("detail_owner_approval")
    if not isinstance(approval, dict):
        raise PipelineError("Detail owner approval metadata is missing or malformed")
    measures = approval.get("approved_measures")
    if (
        not isinstance(measures, list)
        or any(not isinstance(value, str) or not value for value in measures)
        or len(measures) != len(set(measures))
    ):
        raise PipelineError("Detail owner approval measure scope is malformed")
    return measures


def approval_scope_sha256(policy: dict) -> str:
    """Hash every policy surface capable of changing the approved detail fields."""
    if not isinstance(policy, dict):
        raise PipelineError("Detail owner approval policy is malformed")
    measures = _approved_measures(policy)
    detail_policies = policy.get("detail_policies")
    if not isinstance(detail_policies, dict) or any(
        measure not in detail_policies for measure in measures
    ):
        raise PipelineError("Detail owner approval references a missing detail policy")
    reviewed_contexts = policy.get("reviewed_label_contexts", {})
    if not isinstance(reviewed_contexts, dict):
        raise PipelineError("Reviewed label contexts are malformed")
    scope: dict[str, Any] = {
        "approved_measures": sorted(measures),
        "detail_policies": {
            measure: detail_policies[measure] for measure in sorted(measures)
        },
        "reviewed_label_contexts": {
            measure: reviewed_contexts.get(measure, {}) for measure in sorted(measures)
        },
        "excluded_fields": policy.get("excluded_fields", []),
        "detail_field_contexts": policy.get("detail_field_contexts", {}),
        "publication_field_contexts": policy.get("publication_field_contexts", {}),
        "publication_media_source_prefixes": policy.get(
            "publication_media_source_prefixes", {}
        ),
        "sources": policy.get("sources", {}),
    }
    return hashlib.sha256(canonical_json(scope).encode("utf-8")).hexdigest()


def c02_field_review_scope_sha256(policy: dict) -> str:
    """Hash the substantive C02-only projection scope, excluding review state."""
    if not isinstance(policy, dict):
        raise PipelineError("C02 field review policy is malformed")
    detail_policies = policy.get("detail_policies")
    projection = policy.get("c02_projection")
    if (
        not isinstance(detail_policies, dict)
        or not C02_REVIEWED_DETAIL_MEASURES <= set(detail_policies)
        or not isinstance(projection, dict)
    ):
        raise PipelineError("C02 field review references a missing projection scope")
    reviewed_projection = dict(projection)
    reviewed_projection["status"] = C02_PENDING_FIELD_REVIEW_STATUS
    reviewed_detail_policies = {
        measure: {
            **detail_policies[measure],
            "review_status": C02_PENDING_FIELD_REVIEW_STATUS,
        }
        for measure in sorted(C02_REVIEWED_DETAIL_MEASURES)
    }
    scope = {
        "reviewed_measures": sorted(C02_REVIEWED_DETAIL_MEASURES),
        "detail_policies": reviewed_detail_policies,
        "c02_projection": reviewed_projection,
        "excluded_fields": policy.get("excluded_fields", []),
        "detail_field_contexts": policy.get("detail_field_contexts", {}),
        "sources": policy.get("sources", {}),
    }
    return hashlib.sha256(canonical_json(scope).encode("utf-8")).hexdigest()


def c02_geography_review_spec(review: Any) -> dict:
    """Return the immutable review specification selected by review ID."""
    review_id = review.get("review_id") if isinstance(review, dict) else None
    spec = C02_GEOGRAPHY_REVIEW_SPECS.get(review_id)
    if spec is None:
        raise PipelineError("C02 geography review uses an unknown version")
    return spec


def c02_geography_private_revision(review: Any) -> str | None:
    """Return the private revision bound to a review version and status."""
    spec = c02_geography_review_spec(review)
    status = review.get("status") if isinstance(review, dict) else None
    return spec["private_revisions"].get(status)


def c02_geography_review_scope_sha256(policy: dict) -> str:
    """Hash the province-only C02 review scope independent of review state."""
    if not isinstance(policy, dict):
        raise PipelineError("C02 geography review policy is malformed")
    review = policy.get("c02_geography_review")
    detail_policy = policy.get("detail_policies", {}).get("C02_COMMUNITY")
    if not isinstance(review, dict) or not isinstance(detail_policy, dict):
        raise PipelineError("C02 geography review references a missing scope")
    normalized_review = {
        key: value
        for key, value in review.items()
        if key != "scope_sha256"
    }
    normalized_review["status"] = C02_PENDING_FIELD_REVIEW_STATUS
    normalized_review["source_candidate_manifest_sha256"] = ""
    scope = {
        "review": normalized_review,
        "detail_fields": detail_policy.get("detail_fields", []),
        "excluded_fields": policy.get("excluded_fields", []),
        "detail_field_contexts": policy.get("detail_field_contexts", {}),
        "sources": policy.get("sources", {}),
    }
    return hashlib.sha256(canonical_json(scope).encode("utf-8")).hexdigest()


def validate_c02_geography_acceptance(evidence: Any, review: dict) -> dict:
    """Validate owner acceptance for the exact pending province candidate."""
    if (
        not isinstance(evidence, dict)
        or set(evidence) != C02_GEOGRAPHY_ACCEPTANCE_KEYS
    ):
        raise PipelineError("C02 geography acceptance has an unexpected schema")
    spec = c02_geography_review_spec(review)
    measures = evidence.get("reviewed_measures")
    candidate_sha256 = review.get("source_candidate_manifest_sha256")
    if (
        evidence.get("schema_version") != 1
        or evidence.get("acceptance_id") != spec["acceptance_id"]
        or evidence.get("acceptance_status") != C02_ACCEPTED_FIELD_REVIEW_STATUS
        or evidence.get("review_id") != review.get("review_id")
        or not isinstance(measures, list)
        or set(measures) != C02_REVIEWED_DETAIL_MEASURES
        or len(measures) != len(C02_REVIEWED_DETAIL_MEASURES)
        or evidence.get("review_scope_sha256") != review.get("scope_sha256")
        or not isinstance(candidate_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", candidate_sha256)
        or evidence.get("source_candidate_manifest_sha256") != candidate_sha256
        or evidence.get("dimension") != C02_GEOGRAPHY_DIMENSION
        or evidence.get("scope") != spec["scope"]
        or evidence.get("local_promotion_approved") is not False
        or evidence.get("deployment_approved") is not False
    ):
        raise PipelineError(
            "C02 geography acceptance is stale, broader than the review, or not accepted"
        )
    return evidence


def validate_c02_geography_review(policy: dict) -> dict | None:
    """Validate a versioned pending or accepted C02 province review."""
    if not isinstance(policy, dict):
        raise PipelineError("C02 geography review policy is malformed")
    review = policy.get("c02_geography_review")
    if review is None:
        return None
    expected_keys = {
        "review_id",
        "status",
        "reviewed_measures",
        "dimension",
        "conditions",
        "scope_sha256",
        "source_candidate_manifest_sha256",
        "public_promotion_approved",
        "deployment_approved",
    }
    status = review.get("status") if isinstance(review, dict) else None
    spec = c02_geography_review_spec(review)
    measures = review.get("reviewed_measures") if isinstance(review, dict) else None
    candidate_sha256 = (
        review.get("source_candidate_manifest_sha256")
        if isinstance(review, dict)
        else None
    )
    if (
        not isinstance(review, dict)
        or set(review) != expected_keys
        or review.get("review_id") not in C02_GEOGRAPHY_REVIEW_SPECS
        or status
        not in {
            C02_PENDING_FIELD_REVIEW_STATUS,
            C02_ACCEPTED_FIELD_REVIEW_STATUS,
        }
        or not isinstance(measures, list)
        or set(measures) != C02_REVIEWED_DETAIL_MEASURES
        or len(measures) != len(C02_REVIEWED_DETAIL_MEASURES)
        or review.get("dimension") != C02_GEOGRAPHY_DIMENSION
        or review.get("conditions") != spec["conditions"]
        or review.get("scope_sha256") != c02_geography_review_scope_sha256(policy)
        or review.get("public_promotion_approved") is not False
        or review.get("deployment_approved") is not False
        or policy.get("private_revision_id")
        != c02_geography_private_revision(review)
    ):
        raise PipelineError("C02 geography review does not match its versioned scope")
    evidence = policy.get("c02_geography_acceptance")
    if status == C02_PENDING_FIELD_REVIEW_STATUS:
        if candidate_sha256 != "" or evidence is not None:
            raise PipelineError(
                "Pending C02 geography review cannot include acceptance"
            )
    else:
        validate_c02_geography_acceptance(evidence, review)
    return review


def validate_c02_owner_acceptance(evidence: Any, review: dict) -> dict:
    """Validate owner acceptance bound to the exact reviewed C02 candidate."""
    if not isinstance(evidence, dict) or set(evidence) != C02_OWNER_ACCEPTANCE_KEYS:
        raise PipelineError("C02 owner acceptance has an unexpected schema")
    measures = evidence.get("reviewed_measures")
    if (
        evidence.get("schema_version") != 1
        or evidence.get("acceptance_id") != C02_OWNER_ACCEPTANCE_ID
        or evidence.get("acceptance_status") != C02_ACCEPTED_FIELD_REVIEW_STATUS
        or evidence.get("review_id") != C02_FIELD_REVIEW_ID
        or evidence.get("review_id") != review.get("review_id")
        or not isinstance(measures, list)
        or set(measures) != C02_REVIEWED_DETAIL_MEASURES
        or len(measures) != len(C02_REVIEWED_DETAIL_MEASURES)
        or evidence.get("review_scope_sha256") != review.get("scope_sha256")
        or evidence.get("review_scope_sha256") != C02_REVIEW_SCOPE_SHA256
        or evidence.get("source_candidate_manifest_sha256")
        != C02_REVIEWED_SOURCE_MANIFEST_SHA256
        or evidence.get("scope") != "c02_person_fields_only"
        or evidence.get("public_promotion_approved") is not False
        or evidence.get("deployment_approved") is not False
    ):
        raise PipelineError(
            "C02 owner acceptance is stale, broader than field review, or not accepted"
        )
    return evidence


def validate_c02_field_review(policy: dict) -> dict:
    """Validate the pending or explicitly accepted C02 person-field review."""
    if not isinstance(policy, dict):
        raise PipelineError("C02 field review policy is malformed")
    review = policy.get("c02_field_review")
    expected_keys = {
        "review_id",
        "status",
        "reviewed_measures",
        "conditions",
        "scope_sha256",
        "public_promotion_approved",
    }
    if not isinstance(review, dict) or set(review) != expected_keys:
        raise PipelineError("C02 field review has an unexpected schema")
    measures = review.get("reviewed_measures")
    status = review.get("status")
    detail_policies = policy.get("detail_policies")
    detail_policy = (
        detail_policies.get("C02_COMMUNITY")
        if isinstance(detail_policies, dict)
        else None
    )
    if (
        review.get("review_id") != C02_FIELD_REVIEW_ID
        or status
        not in {
            C02_PENDING_FIELD_REVIEW_STATUS,
            C02_ACCEPTED_FIELD_REVIEW_STATUS,
        }
        or not isinstance(measures, list)
        or set(measures) != C02_REVIEWED_DETAIL_MEASURES
        or len(measures) != len(C02_REVIEWED_DETAIL_MEASURES)
        or review.get("conditions") != C02_FIELD_REVIEW_CONDITIONS
        or review.get("public_promotion_approved") is not False
        or not isinstance(detail_policy, dict)
        or detail_policy.get("review_status") != status
        or (
            "c02_geography_review" not in policy
            and policy.get("private_revision_id") != C02_PRIVATE_REVISIONS[status]
        )
    ):
        scope_name = (
            "pending review scope"
            if status == C02_PENDING_FIELD_REVIEW_STATUS
            else "accepted review scope"
        )
        raise PipelineError(f"C02 field review does not match the {scope_name}")
    evidence = policy.get("c02_owner_acceptance")
    if status == C02_PENDING_FIELD_REVIEW_STATUS:
        if evidence is not None:
            raise PipelineError("Pending C02 field review cannot include acceptance")
    else:
        validate_c02_owner_acceptance(evidence, review)
    return review


def validate_detail_owner_approval(policy: dict) -> dict | None:
    """Return accepted scoped approval, or ``None`` for a legacy pending policy."""
    if not isinstance(policy, dict):
        raise PipelineError("Detail owner approval policy is malformed")
    if (
        policy.get("staged_for_review") is not True
        or policy.get("owner_checkpoint_required") is not True
        or policy.get("publication_approval_claimed") is not False
    ):
        raise PipelineError(
            "Field cleaning or owner field approval cannot authorize public promotion"
        )
    approval = policy.get("detail_owner_approval")
    if approval is None:
        if (
            policy.get("additional_field_review_status")
            != PENDING_FIELD_APPROVAL_STATUS
        ):
            raise PipelineError(
                "Pending detail policy has inconsistent approval status"
            )
        return None
    if not isinstance(approval, dict) or set(approval) != _APPROVAL_KEYS:
        raise PipelineError("Detail owner approval metadata has an unexpected schema")
    measures = _approved_measures(policy)
    approved_measures, conditions, review_status = _approval_spec(approval)
    if (
        approval.get("status") != "accepted"
        or set(measures) != approved_measures
        or len(measures) != len(approved_measures)
        or approval.get("public_promotion_approved") is not False
        or approval.get("conditions") != conditions
        or policy.get("additional_field_review_status") != review_status
    ):
        raise PipelineError("Detail owner approval does not match the accepted scope")
    scope_sha256 = approval.get("scope_sha256")
    if (
        not isinstance(scope_sha256, str)
        or len(scope_sha256) != 64
        or scope_sha256 != approval_scope_sha256(policy)
    ):
        raise PipelineError("Detail owner approval scope hash does not match policy")
    return approval


def validate_embedded_detail_owner_approval(metadata: dict) -> dict | None:
    """Validate staged metadata when the full policy is not available."""
    status = metadata.get("additional_field_review_status")
    approval = metadata.get("detail_owner_approval")
    if status == PENDING_FIELD_APPROVAL_STATUS and approval is None:
        return None
    if not isinstance(approval, dict) or set(approval) != _APPROVAL_KEYS:
        raise PipelineError(
            "Staged field approval metadata is malformed or inconsistent"
        )
    approved_measures, conditions, review_status = _approval_spec(approval)
    measures = approval.get("approved_measures")
    geography_review = metadata.get("c02_geography_review")
    status_matches = status == review_status or (
        isinstance(geography_review, dict)
        and status == geography_review.get("status")
    )
    if (
        not status_matches
        or not isinstance(measures, list)
        or any(not isinstance(measure, str) for measure in measures)
        or set(measures) != approved_measures
        or len(measures) != len(approved_measures)
        or approval.get("status") != "accepted"
        or approval.get("public_promotion_approved") is not False
        or approval.get("conditions") != conditions
        or not isinstance(approval.get("scope_sha256"), str)
        or len(approval["scope_sha256"]) != 64
    ):
        raise PipelineError(
            "Staged field approval metadata is malformed or inconsistent"
        )
    return approval
