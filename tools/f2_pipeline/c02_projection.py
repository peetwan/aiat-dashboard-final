"""Source-scoped private C02 person projection.

The adapter reuses accepted global person identities, counted membership and
qualifying assertion IDs.  It does not resolve identities or infer eligibility.
All output remains staged pending the separate C02 owner field review.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any, Iterable
from urllib.parse import urlsplit

from app.privacy import EMAIL_RE, PHONE_RE, SOCIAL_CONTACT_RE
from app.publication import _privacy_problems

from .common import (
    PipelineError,
    canonical_json,
    matching_name,
    normalize,
    readable,
    stable_id,
)
from .public_details import _identity_review

C02_MEASURES = ("C02_COMMUNITY",)
C02_QUALIFYING_ROLES = frozenset({"community_innovator", "inventor"})
ROLE_LABELS_TH = {
    "community_innovator": "นวัตกรชุมชน",
    "inventor": "ผู้ประดิษฐ์",
}
ROLE_MEASURES = {
    "community_innovator": ["C02_COMMUNITY"],
    "inventor": ["C02_COMMUNITY"],
}
_RELATIONSHIP_KINDS = {
    "community_innovator": "contributed_to_innovation",
    "inventor": "invented_innovation",
}
_PLACEHOLDER_LABEL = "ชื่ออยู่ระหว่างการตรวจสอบ"
_C02_PUBLIC_TITLE_PREFIX = re.compile(r"^อาจารย์\s*")
_PRIVATE_TEXT = re.compile(
    r"(?:เลขประจำตัวประชาชน|เลขบัญชี|รหัสผ่าน|password|passcode|"
    r"authorization\s*:|bearer\s+[a-z0-9._~-]+)",
    re.I,
)
_LOCAL_PATH = re.compile(
    r"(?:file://|(?:^|\s)/(?:Users|home|private|var|tmp)/|[A-Za-z]:\\|"
    r"(?:raw|normalized|evidence)://)",
    re.I,
)
_CONTEXT_KEYS = {
    "admission_context",
    "allowed_assertion_kinds",
    "allowed_role_mappings",
    "blocked_name_quality_flags",
    "context_sha256",
    "organization_roles",
    "priority",
    "required_context_values",
    "source_id",
    "work_id_field",
    "work_label_field",
    "work_table",
}


def _json_list(value: Any) -> list:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    try:
        result = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PipelineError("C02 input has an invalid JSON list") from exc
    if not isinstance(result, list):
        raise PipelineError("C02 input JSON cell is not a list")
    return result


def _json_object(value: Any) -> dict:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PipelineError("C02 input has an invalid JSON object") from exc
    if not isinstance(result, dict):
        raise PipelineError("C02 input JSON cell is not an object")
    return result


def _rows(tables: dict, name: str) -> list[dict]:
    rows = tables.get(name, [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"C02 projection table is malformed: {name}")
    return rows


def _context_digest(spec: dict) -> str:
    value = {key: item for key, item in spec.items() if key != "context_sha256"}
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _validated_projection(policy: dict) -> dict:
    projection = policy.get("c02_projection")
    review = policy.get("c02_field_review")
    if not isinstance(projection, dict):
        raise PipelineError("C02 projection policy is missing")
    if (
        not isinstance(review, dict)
        or projection.get("status") != review.get("status")
        or projection.get("status")
        not in {"pending_owner_acceptance", "accepted"}
    ):
        raise PipelineError("C02 projection review status is invalid or inconsistent")
    if projection.get("public_promotion_approved") is not False:
        raise PipelineError("C02 projection cannot authorize promotion")
    expected = projection.get("expected_counted_totals")
    if not isinstance(expected, dict) or set(expected) != set(C02_MEASURES):
        raise PipelineError("C02 counted-total policy is malformed")
    contexts = projection.get("source_contexts")
    if not isinstance(contexts, dict) or not contexts:
        raise PipelineError("C02 source contexts are missing")
    for source, spec in contexts.items():
        if (
            not isinstance(source, str)
            or not source
            or not isinstance(spec, dict)
            or set(spec) != _CONTEXT_KEYS
            or spec.get("context_sha256") != _context_digest(spec)
        ):
            raise PipelineError("C02 source context hash does not match its scope")
        mappings = spec.get("allowed_role_mappings")
        if not isinstance(mappings, dict) or any(
            not isinstance(raw_role, str)
            or not raw_role
            or not isinstance(roles, list)
            or not roles
            or not set(roles) <= C02_QUALIFYING_ROLES
            for raw_role, roles in mappings.items()
        ):
            raise PipelineError("C02 source role mapping is malformed")
        source_id = spec.get("source_id")
        source_policy = policy.get("sources", {}).get(source)
        if (
            not isinstance(source_id, str)
            or not source_id
            or not isinstance(source_policy, dict)
            or source_policy.get("source_id") != source_id
        ):
            raise PipelineError("C02 source context is not bound to a public source")
    return projection


def apply_c02_projection_policy(
    base_policy: dict,
    extension: dict,
    owner_acceptance: dict | None = None,
    geography_acceptance: dict | None = None,
) -> dict:
    """Merge a versioned C02 extension without changing the accepted base scope."""
    if not isinstance(base_policy, dict) or not isinstance(extension, dict):
        raise PipelineError("C02 policy extension is malformed")
    expected_keys = {
        "schema_version",
        "policy_id",
        "release_id",
        "private_revision_id",
        "c02_field_review",
        "c02_projection",
        "detail_policies",
    }
    has_geography_review = "c02_geography_review" in extension
    if has_geography_review:
        expected_keys.add("c02_geography_review")
    if set(extension) != expected_keys or extension.get("schema_version") != 1:
        raise PipelineError("C02 policy extension has an unexpected schema")
    if extension.get("release_id") != "f2-dashboard-snapshot-v3":
        raise PipelineError("C02 policy extension must retain the logical v3 release")
    from .field_approval import (
        C02_PRIVATE_REVISIONS,
        approval_scope_sha256,
        c02_geography_private_revision,
        validate_c02_field_review,
        validate_c02_geography_review,
        validate_detail_owner_approval,
    )

    review = extension.get("c02_field_review")
    status = review.get("status") if isinstance(review, dict) else None
    geography_review = extension.get("c02_geography_review")
    geography_status = (
        geography_review.get("status")
        if isinstance(geography_review, dict)
        else None
    )
    expected_revision = (
        c02_geography_private_revision(geography_review)
        if has_geography_review
        else C02_PRIVATE_REVISIONS.get(status)
    )
    if (
        status not in C02_PRIVATE_REVISIONS
        or (has_geography_review and status != "accepted")
        or extension.get("private_revision_id") != expected_revision
    ):
        raise PipelineError("C02 policy extension has an unexpected private revision")
    detail_policies = extension.get("detail_policies")
    if not isinstance(detail_policies, dict) or set(detail_policies) != set(
        C02_MEASURES
    ):
        raise PipelineError("C02 detail policy must cover exactly the C02 measure")
    accepted_approval = validate_detail_owner_approval(base_policy)
    if accepted_approval is None:
        raise PipelineError("C02 extension requires the accepted base detail approval")
    accepted_scope = approval_scope_sha256(base_policy)
    result = deepcopy(base_policy)
    existing = result.get("detail_policies")
    if not isinstance(existing, dict) or set(existing) & set(C02_MEASURES):
        raise PipelineError("C02 detail policy collides with the accepted base policy")
    result["detail_policies"] = {**existing, **deepcopy(detail_policies)}
    result["private_revision_id"] = extension["private_revision_id"]
    result["c02_field_review"] = deepcopy(extension["c02_field_review"])
    result["c02_projection"] = deepcopy(extension["c02_projection"])
    if owner_acceptance is not None:
        result["c02_owner_acceptance"] = deepcopy(owner_acceptance)
    if has_geography_review:
        result["c02_geography_review"] = deepcopy(geography_review)
        if geography_acceptance is not None:
            result["c02_geography_acceptance"] = deepcopy(geography_acceptance)
    _validated_projection(result)
    validate_c02_field_review(result)
    validate_c02_geography_review(result)
    if (
        approval_scope_sha256(result) != accepted_scope
        or result["detail_owner_approval"] != accepted_approval
    ):
        raise PipelineError("C02 extension changed the accepted detail approval scope")
    return result


def _clean_label(
    value: Any, *, context: str | None = None, limit: int = 300
) -> str | None:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    text = readable(value)
    if (
        not text
        or text != normalize(value)
        or len(text) > limit
        or _PRIVATE_TEXT.search(text)
        or _LOCAL_PATH.search(text)
        or EMAIL_RE.search(text)
        or PHONE_RE.search(text)
        or SOCIAL_CONTACT_RE.search(text)
    ):
        return None
    contexts = {"/label": context} if context else {}
    problems = _privacy_problems(
        {"label": text},
        artifact_path="staged-c02-field",
        restricted_source_ids=set(),
        profile="aggregate_public",
        field_contexts=contexts,
    )
    return None if problems else text


def _source_public_url(policy: dict, source: str) -> str | None:
    spec = policy.get("sources", {}).get(source, {})
    value = spec.get("public_url")
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.hostname not in set(spec.get("public_url_hosts", []))
    ):
        return None
    return value


def _source_system(policy: dict, source: str) -> str:
    value = policy.get("sources", {}).get(source, {}).get("originating_system")
    if not isinstance(value, str) or not value:
        raise PipelineError("C02 source has no approved originating system")
    return value


def _source_context_allows(assertion: dict, spec: dict) -> bool:
    if assertion.get("assertion_kind") not in spec["allowed_assertion_kinds"]:
        return False
    if assertion.get("natural_person_status") != "supported_natural_person":
        return False
    raw_role = str(assertion.get("role") or "")
    eligible = set(_json_list(assertion.get("eligible_roles_json")))
    if not eligible & set(spec["allowed_role_mappings"].get(raw_role, [])):
        return False
    context = _json_object(assertion.get("context_json"))
    return all(
        context.get(key) in values
        for key, values in spec["required_context_values"].items()
    )


def _group(rows: Iterable[dict], key: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        value = str(row.get(key) or "")
        if value:
            grouped[value].append(row)
    return grouped


def _child_disposition(candidate: int, emitted: int, reasons: Iterable[str]) -> dict:
    reason_counts = Counter(reasons)
    withheld = candidate - emitted
    if withheld < 0 or sum(reason_counts.values()) != withheld:
        raise PipelineError("C02 child disposition does not reconcile")
    return {
        "candidate_count": candidate,
        "emitted_count": emitted,
        "withheld_count": withheld,
        "withheld_reasons": dict(sorted(reason_counts.items())),
    }


def _work_labels(tables: dict, contexts: dict) -> dict[tuple[str, str], str]:
    labels: dict[tuple[str, str], str] = {}
    for source, spec in contexts.items():
        table = spec["work_table"]
        id_field = spec["work_id_field"]
        label_field = spec["work_label_field"]
        for row in _rows(tables, table):
            work_id = str(row.get(id_field) or "")
            label = _clean_label(row.get(label_field), context="work_attribution")
            if not work_id or label is None:
                continue
            key = (source, work_id)
            if key in labels and labels[key] != label:
                raise PipelineError("C02 source work identity has conflicting labels")
            labels[key] = label
    return labels


def _membership(
    tables: dict, projection: dict
) -> tuple[dict[str, set[str]], dict[tuple[str, str], set[str]]]:
    entity_ids = {
        measure: {
            str(row.get("entity_id"))
            for row in _rows(tables, "entity_contributions")
            if row.get("measure_id") == measure and row.get("entity_id")
        }
        for measure in C02_MEASURES
    }
    for measure in C02_MEASURES:
        expected = projection["expected_counted_totals"][measure]
        if (
            not isinstance(expected, int)
            or expected < 0
            or len(entity_ids[measure]) != expected
        ):
            raise PipelineError(
                f"{measure} counted population differs from reviewed C02 policy"
            )
    if not entity_ids["C02_COMMUNITY"]:
        raise PipelineError("C02 accepted population is empty")
    qualifying: dict[tuple[str, str], set[str]] = {}
    seen: set[tuple[str, str]] = set()
    for row in _rows(tables, "domains/people/measure_contributions"):
        measure = str(row.get("measure_id") or "")
        if measure not in C02_MEASURES:
            continue
        person_id = str(row.get("global_person_id") or "")
        key = (measure, person_id)
        if key in seen:
            raise PipelineError("C02 measure contribution repeats a person")
        seen.add(key)
        ids = _json_list(row.get("qualifying_assertion_ids_json"))
        if not ids or any(not isinstance(value, str) or not value for value in ids):
            raise PipelineError("C02 contribution lacks qualifying assertion IDs")
        qualifying[key] = set(ids)
    for measure, ids in entity_ids.items():
        if ids != {person for current, person in qualifying if current == measure}:
            raise PipelineError(
                f"{measure} accepted membership and contribution rows differ"
            )
    return entity_ids, qualifying


def _role_rows(
    person_id: str,
    memberships: set[str],
    assertion_ids: set[str],
    assertions: dict[str, dict],
    crosswalk_by_entity: dict[str, dict],
    contexts: dict,
) -> tuple[list[dict], list[tuple[dict, str]], list[str]]:
    roles: list[dict] = []
    admitted_assertions: list[tuple[dict, str]] = []
    reasons: list[str] = []
    for assertion_id in sorted(assertion_ids):
        row = assertions.get(assertion_id)
        if row is None or str(row.get("global_person_id") or "") != person_id:
            reasons.append("qualifying_assertion_missing_or_identity_mismatch")
            continue
        source = str(row.get("source") or "")
        spec = contexts.get(source)
        crosswalk = crosswalk_by_entity.get(str(row.get("source_entity_id") or ""))
        if (
            spec is None
            or crosswalk is None
            or crosswalk.get("global_person_id") != person_id
            or crosswalk.get("source") != source
            or not _source_context_allows(row, spec)
        ):
            reasons.append("qualifying_assertion_context_not_approved")
            continue
        raw_role = str(row.get("role") or "")
        eligible = set(_json_list(row.get("eligible_roles_json")))
        emitted_for_assertion = False
        reason_count = len(reasons)
        for role in sorted(eligible & set(spec["allowed_role_mappings"][raw_role])):
            qualifies_for = ROLE_MEASURES[role]
            if not set(qualifies_for) <= memberships:
                reasons.append("qualifying_role_measure_mismatch")
                continue
            roles.append(
                {
                    "assertion_id": assertion_id,
                    "role_code": role,
                    "role_label_th": ROLE_LABELS_TH[role],
                    "qualifies_for": qualifies_for,
                    "evidence_basis": "source_supported_person_role",
                    "source_id": spec["source_id"],
                }
            )
            admitted_assertions.append((row, role))
            emitted_for_assertion = True
        if not emitted_for_assertion and len(reasons) == reason_count:
            reasons.append("qualifying_role_not_canonical")
    return roles, admitted_assertions, reasons

def _person_name_key(value: str) -> str:
    """Compare accepted C02 labels after scoped honorific normalization."""
    name = matching_name(value)
    candidate = _C02_PUBLIC_TITLE_PREFIX.sub("", name).strip()
    if candidate != name and len(candidate.split()) >= 2:
        name = matching_name(candidate)
    return name.casefold()


def _admitted_name(
    admitted_assertions: list[tuple[dict, str]],
    crosswalk_by_entity: dict[str, dict],
    contexts: dict,
) -> tuple[str, str, str | None]:
    candidates = []
    blocked = False
    for row, _ in admitted_assertions:
        source = str(row.get("source") or "")
        spec = contexts[source]
        crosswalk = crosswalk_by_entity[str(row["source_entity_id"])]
        quality = set(_json_list(crosswalk.get("quality_flags_json")))
        if quality & set(spec["blocked_name_quality_flags"]):
            blocked = True
            continue
        label = _clean_label(row.get("raw_name"), context="work_attribution")
        crosswalk_label = _clean_label(
            crosswalk.get("display_name"), context="work_attribution"
        )
        if (
            label is None
            or crosswalk_label is None
            or _person_name_key(label) != _person_name_key(crosswalk_label)
        ):
            blocked = True
            continue
        candidates.append((int(spec["priority"]), source, crosswalk_label))
    if not candidates:
        return (
            _PLACEHOLDER_LABEL,
            "withheld",
            "public_name_context_not_approved"
            if blocked
            else "public_name_unavailable",
        )
    return (
        sorted(candidates, key=lambda value: (value[0], value[1], value[2]))[0][2],
        "available",
        None,
    )


def _organizations(
    admitted_assertions: list[tuple[dict, str]], contexts: dict
) -> tuple[list[dict], dict[tuple[str, str], str], list[str]]:
    rows: dict[tuple[str, str, str], dict] = {}
    assertion_organizations: dict[tuple[str, str], str] = {}
    reasons: list[str] = []
    candidates = 0
    for assertion, role_code in admitted_assertions:
        value = assertion.get("institution_raw")
        if value in (None, ""):
            continue
        candidates += 1
        source = str(assertion.get("source") or "")
        spec = contexts[source]
        organization_role = spec["organization_roles"].get(
            str(assertion.get("institution_role") or "")
        )
        label = _clean_label(value, context="organization")
        if not organization_role or label is None:
            reasons.append("organization_context_not_approved")
            continue
        source_id = spec["source_id"]
        key = (label, organization_role, source_id)
        rows[key] = {
            "organization": label,
            "role": organization_role,
            "role_label_th": "หน่วยงานวิจัย"
            if organization_role == "research_organization"
            else "หน่วยงานที่สังกัด",
            "source_id": source_id,
        }
        assertion_organizations[(str(assertion["assertion_id"]), role_code)] = label
    return [rows[key] for key in sorted(rows)], assertion_organizations, reasons


def _relationships(
    admitted_assertions: list[tuple[dict, str]],
    contexts: dict,
    work_labels: dict[tuple[str, str], str],
    public_targets: dict[str, tuple[str, str]],
) -> tuple[list[dict], dict[tuple[str, str], str], bool, list[str]]:
    rows: dict[tuple[str, str, str], dict] = {}
    assertion_work_ids: dict[tuple[str, str], str] = {}
    reasons: list[str] = []
    unavailable = False
    for assertion, role_code in admitted_assertions:
        source = str(assertion.get("source") or "")
        source_id = contexts[source]["source_id"]
        global_id = str(assertion.get("global_innovation_id") or "")
        local_id = str(assertion.get("local_innovation_id") or "")
        if not global_id and not local_id:
            if assertion.get("relationship_id"):
                unavailable = True
                reasons.append("work_identity_not_established")
            continue
        if global_id in public_targets:
            label, target_measure = public_targets[global_id]
            entity_id = global_id
        else:
            label = work_labels.get((source, local_id))
            entity_id = global_id or stable_id("public_work", source_id, local_id)
            target_measure = ""
        if not label:
            reasons.append("work_label_context_not_approved")
            continue
        key = (entity_id, role_code, source_id)
        relation = {
            "kind": _RELATIONSHIP_KINDS[role_code],
            "entity_id": entity_id,
            "label": label,
            "role_code": role_code,
            "role_label_th": ROLE_LABELS_TH[role_code],
            "source_id": source_id,
        }
        if target_measure:
            relation["target_detail"] = {
                "topic_id": "k04",
                "measure_id": target_measure,
                "entity_id": global_id,
            }
        rows[key] = relation
        assertion_work_ids[(str(assertion["assertion_id"]), role_code)] = entity_id
    return [rows[key] for key in sorted(rows)], assertion_work_ids, unavailable, reasons


def _finalize_detail(detail: dict, policy: dict, measure: str) -> str | None:
    expected = set(policy["detail_policies"][measure].get("detail_fields", []))
    if set(detail) != expected:
        raise PipelineError(f"{measure} detail fields differ from its C02 policy")
    projection = policy["c02_projection"]
    problems = _privacy_problems(
        detail,
        artifact_path=f"staged-c02-detail/{measure}",
        restricted_source_ids=set(),
        profile="aggregate_public",
        field_contexts=projection["field_contexts"],
    )
    return "public_detail_privacy_check" if problems else None


def _person_province_locations(
    tables: dict, policy: dict, geography_review: dict | None
) -> dict[str, list[dict]]:
    if geography_review is None:
        return {}
    public_sources = {
        spec.get("source_id"): spec.get("source_id")
        for spec in policy.get("sources", {}).values()
        if isinstance(spec, dict) and spec.get("source_id")
    }
    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in _rows(tables, "domains/people/person_location_assertions"):
        person_id = str(row.get("global_person_id", ""))
        province_code = str(row.get("province_code", ""))
        province_name = str(row.get("province_name_th", ""))
        source_id = public_sources.get(str(row.get("source", "")))
        if (
            not person_id
            or not province_code
            or not province_name
            or source_id is None
            or row.get("location_role") != "source_reported_innovator_location"
            or row.get("evidence_basis") != "exact_source_province_name_lookup"
            or row.get("province_resolution_status") != "exact_source_province"
            or row.get("review_status") != "accepted"
            or province_code in grouped[person_id]
        ):
            raise PipelineError("C02 person province assertion is malformed")
        grouped[person_id][province_code] = {
            "province_code": province_code,
            "province": province_name,
            "location_role": "source_reported_innovator_location",
            "source_id": source_id,
        }
    return {
        person_id: [locations[code] for code in sorted(locations)]
        for person_id, locations in grouped.items()
    }


def build_c02_details(
    tables: dict,
    policy: dict,
    public_targets: dict[str, tuple[str, str]],
) -> dict[str, dict[str, dict]]:
    """Return admitted and wholly withheld C02 details for the accepted roster."""
    from .field_approval import (
        validate_c02_field_review,
        validate_c02_geography_review,
    )

    projection = _validated_projection(policy)
    contexts = projection["source_contexts"]
    field_review_status = validate_c02_field_review(policy)["status"]
    geography_review = validate_c02_geography_review(policy)
    review_status = (
        geography_review["status"] if geography_review else field_review_status
    )
    person_locations = _person_province_locations(
        tables, policy, geography_review
    )
    entity_ids, qualifying = _membership(tables, projection)
    people = {
        str(row.get("global_person_id")): row
        for row in _rows(tables, "domains/people/global_people")
        if row.get("global_person_id")
    }
    assertions = {
        str(row.get("assertion_id")): row
        for row in _rows(tables, "domains/people/person_assertions")
        if row.get("assertion_id")
    }
    crosswalk_rows = _rows(tables, "domains/people/person_crosswalk")
    crosswalk_by_entity = {
        str(row.get("source_entity_id")): row
        for row in crosswalk_rows
        if row.get("source_entity_id")
    }
    crosswalks_by_person = _group(crosswalk_rows, "global_person_id")
    work_labels = _work_labels(tables, contexts)
    result = {measure: {"details": {}, "withheld": {}} for measure in C02_MEASURES}
    all_people = sorted(set().union(*entity_ids.values()))
    for person_id in all_people:
        memberships = {
            measure for measure in C02_MEASURES if person_id in entity_ids[measure]
        }
        person = people.get(person_id)
        if person is None or not person_id.startswith("global_person_"):
            reason = "missing_accepted_global_person"
            for measure in memberships:
                result[measure]["withheld"][person_id] = reason
            continue
        identity_status = str(person.get("identity_status") or "")
        if identity_status not in {"source_supported", "reviewed_cross_source"}:
            reason = "unsupported_global_identity_status"
            for measure in memberships:
                result[measure]["withheld"][person_id] = reason
            continue
        assertion_ids = set().union(
            *(qualifying[(measure, person_id)] for measure in memberships)
        )
        roles, admitted_assertions, role_reasons = _role_rows(
            person_id,
            memberships,
            assertion_ids,
            assertions,
            crosswalk_by_entity,
            contexts,
        )
        if not roles:
            reason = "no_approved_qualifying_assertion"
            for measure in memberships:
                result[measure]["withheld"][person_id] = reason
            continue
        label, label_availability, label_reason = _admitted_name(
            admitted_assertions, crosswalk_by_entity, contexts
        )
        organizations, assertion_orgs, organization_reasons = _organizations(
            admitted_assertions, contexts
        )
        relationships, assertion_works, count_unavailable, relationship_reasons = (
            _relationships(
                admitted_assertions,
                contexts,
                work_labels,
                public_targets,
            )
        )
        for role in roles:
            key = (role["assertion_id"], role["role_code"])
            if key in assertion_orgs:
                role["organization"] = assertion_orgs[key]
            if key in assertion_works:
                role["related_entity_id"] = assertion_works[key]
                role["related_entity_type"] = "innovation"
        qualifying_source_keys = sorted(
            {
                str(assertion.get("source"))
                for assertion, _ in admitted_assertions
                if assertion.get("source")
            }
        )
        supporting_source_keys = sorted(
            {
                str(row.get("source"))
                for row in crosswalks_by_person.get(person_id, [])
                if row.get("source") in policy.get("sources", {})
            }
        )
        source_ids = sorted(
            {
                policy["sources"][source]["source_id"]
                for source in supporting_source_keys
            }
        )
        listings = []
        for source in qualifying_source_keys:
            source_url = _source_public_url(policy, source)
            listing = {
                "label": "ข้อมูลนวัตกรจากแหล่งต้นทาง",
                "source_id": contexts[source]["source_id"],
                "record_link_availability": "available" if source_url else "withheld",
            }
            if source_url:
                listing["source_url"] = source_url
                listing["link_scope"] = "source"
            else:
                listing["record_link_withholding_reason"] = (
                    "source_public_url_not_approved"
                )
            listings.append(listing)
        distinct_work_ids = {row["entity_id"] for row in relationships}
        source_quality_flags = sorted(
            {
                flag
                for crosswalk in crosswalks_by_person.get(person_id, [])
                for flag in _json_list(crosswalk.get("quality_flags_json"))
                if flag
                in {
                    "incomplete_or_ambiguous_name",
                    "incomplete_name",
                    "source_reported_person",
                    "possible_duplicate",
                }
            }
        )
        locations = person_locations.get(person_id, [])
        detail = {
            "entity_id": person_id,
            "label": label,
            "label_availability": label_availability,
            "label_withholding_reason": label_reason,
            "identity_status": identity_status,
            "province_codes": [
                location["province_code"] for location in locations
            ],
            "category_codes": [],
            "descriptions": [],
            "listings": listings,
            "locations": locations,
            "media": [],
            "relationships": relationships,
            "children": {
                "qualifying_roles": sorted(
                    roles,
                    key=lambda row: (
                        row["role_code"],
                        row["source_id"],
                        row["assertion_id"],
                    ),
                ),
                "organizations": organizations,
            },
            "flags": {
                "unresolved_identity": "possible_duplicate" in source_quality_flags,
                "possible_duplicate": "possible_duplicate" in source_quality_flags,
                "source_quality_flags": source_quality_flags,
                "identity_review": _identity_review(
                    "reviewed_possible_duplicate"
                    if "possible_duplicate" in source_quality_flags
                    else identity_status,
                    source_ids,
                ),
                "person_publication_context": "public_work_attribution",
                "k02_relationship": "not_established",
                "geography_not_published": not bool(locations),
                "person_province_basis": (
                    "source_reported_innovator_location" if locations else "unavailable"
                ),
                "province_memberships_overlap": bool(locations),
                "geography_review_status": (
                    geography_review["status"] if geography_review else "not_reviewed"
                ),
                "related_work_count_unavailable": count_unavailable,
                "missing_public_detail_fields": [
                    field
                    for field, withheld in (
                        ("label", label_availability == "withheld"),
                        ("organizations", bool(organization_reasons)),
                        ("relationships", bool(relationship_reasons)),
                    )
                    if withheld
                ],
                "additional_field_review_status": review_status,
                "owner_checkpoint_required": True,
                "child_dispositions": {
                    "qualifying_roles": _child_disposition(
                        len(assertion_ids),
                        len({row["assertion_id"] for row in roles}),
                        role_reasons,
                    ),
                    "organizations": _child_disposition(
                        len(organizations) + len(organization_reasons),
                        len(organizations),
                        organization_reasons,
                    ),
                    "relationships": _child_disposition(
                        len(relationships) + len(relationship_reasons),
                        len(relationships),
                        relationship_reasons,
                    ),
                },
            },
            "source_ids": source_ids,
            "originating_systems": sorted(
                {_source_system(policy, source) for source in supporting_source_keys}
            ),
            "related_work_count": len(distinct_work_ids),
            "detail_availability": "available",
        }
        reason = _finalize_detail(detail, policy, next(iter(memberships)))
        if reason:
            for measure in memberships:
                result[measure]["withheld"][person_id] = reason
            continue
        for measure in memberships:
            if set(detail) != set(policy["detail_policies"][measure]["detail_fields"]):
                raise PipelineError("Shared C02 detail policies disagree")
            result[measure]["details"][person_id] = detail
    for measure in C02_MEASURES:
        represented = set(result[measure]["details"]) | set(result[measure]["withheld"])
        if represented != entity_ids[measure] or set(result[measure]["details"]) & set(
            result[measure]["withheld"]
        ):
            raise PipelineError(f"{measure} public detail coverage does not reconcile")
    return result
