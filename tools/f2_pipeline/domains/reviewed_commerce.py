"""Pure reviewed commerce reconciliation over the accepted offering baseline."""

from __future__ import annotations

import copy
import json
import math
import re
from collections import defaultdict
from typing import Any

from ..common import PipelineError, readable, safe_text
from .commerce import (
    TABLE_COLUMNS as BASELINE_TABLE_COLUMNS,
    UnionFind,
    components,
    json_text,
    stable_id,
    validate_output,
)
from .raw_inputs import SOURCE_IDS, observation_uri, resolve_evidence
from .resolution import locator_matches, locator_parts, review_payloads_under

LEARNING_CULTURAL_BUSINESS_BASIS = "source_declared_cultural_business"
LEARNING_CULTURAL_BUSINESS_CONTRACT = "learning_area_based_all_rows_v1"
LEARNING_IDENTITY_QUALITIES = {
    "named_source_business",
    "ambiguous_business_label",
    "community_or_support_label",
    "named_person_label",
    "group_or_network_label",
    "missing_source_name",
}

STATUSES = {"supported", "unresolved", "not_established"}
KINDS = {"operator", "offering"}
BASES = {
    "source_reported_business",
    "source_reported_manufacturer",
    "source_reported_seller",
    "physical_prototype",
    "completed_design",
    "developed_product",
    "delivered_system",
    "source_reported_offering",
    "reviewed_context",
    LEARNING_CULTURAL_BUSINESS_BASIS,
}

TABLE_COLUMNS = {
    **BASELINE_TABLE_COLUMNS,
    "reviewed_evidence": (
        "evidence_id",
        "candidate_id",
        "source",
        "raw_locator",
        "evidence_text",
        "relationship",
        "source_record_id",
        "citation_source_record_id",
        "global_innovation_id",
        "status",
        "basis",
        "entity_kind",
        "global_operator_id",
        "global_offering_id",
    ),
    "review_coverage": (
        "candidate_id",
        "source",
        "entity_kind",
        "display_name",
        "status",
        "basis",
        "eligibility_contract",
        "identity_quality",
        "identity_review_note",
        "output_type",
        "unit_basis",
        "reason",
        "global_entity_id",
        "audit_ref",
    ),
    "reviewed_identity_decisions": (
        "review_id",
        "left",
        "right",
        "decision",
        "reason",
        "evidence_refs_json",
    ),
    "reported_product_totals": (
        "claim_id",
        "source",
        "value",
        "unit",
        "raw_locator",
        "quote",
        "reason",
        "value_quote",
        "additive_to_k07",
        "membership_status",
    ),
    "reviewed_relationships": (
        "relationship_id",
        "subject",
        "object",
        "relationship",
        "reason",
        "evidence_candidate",
        "subject_global_id",
        "object_global_id",
        "evidence_refs_json",
    ),
    "offering_families": (
        "family_id",
        "display_name",
        "member_count",
        "identity_status",
        "counting_basis",
    ),
    "offering_family_members": (
        "family_id",
        "global_offering_id",
        "membership_role",
        "reason",
    ),
    "offering_family_decisions": (
        "family_id",
        "display_name",
        "basis",
        "reason",
        "members_json",
        "evidence_refs_json",
    ),
}


def _fail(message: str) -> None:
    raise PipelineError(message)


def _evidence_text(value: object) -> str:
    if not isinstance(value, (str, int, float)) and value is not None:
        _fail("Commerce evidence must cite a scalar field")
    text = str(value or "")
    if re.search(r"</?[A-Za-z][^>]*>", text):
        text = readable(text)
    return safe_text(text)


def _load_reviews(reviews: dict[str, Any]) -> tuple[dict[str, list], dict[str, dict]]:
    combined = {
        key: []
        for key in (
            "candidates",
            "identity_decisions",
            "relationships",
            "aggregate_claims",
            "counting_groups",
        )
    }
    pins: dict[str, dict] = {}
    payloads = review_payloads_under(reviews, "reviewed_commerce")
    if not payloads:
        _fail("No reviewed commerce inputs supplied")
    for path, payload in payloads:
        if not isinstance(payload, dict) or payload.get("schema_version") != 2:
            _fail(f"Unsupported reviewed commerce schema: {path}")
        for key in combined:
            rows = payload.get(key, [])
            if not isinstance(rows, list):
                _fail(f"Reviewed commerce {path} has invalid {key}")
            combined[key].extend(copy.deepcopy(rows))
        for pin in payload.get("evidence_pins", []):
            if (
                not isinstance(pin, dict)
                or not pin.get("relative_path")
                or not pin.get("sha256")
            ):
                _fail(f"Reviewed commerce {path} has an invalid evidence pin")
            relative = str(pin["relative_path"])
            if relative in pins and pins[relative] != pin:
                _fail(f"Conflicting reviewed commerce evidence pin: {relative}")
            pins[relative] = dict(pin)
    if not combined["candidates"]:
        _fail("No reviewed commerce candidates configured")
    return combined, pins


def _validate_pin(pin: dict, raw_inputs: dict[str, dict]) -> None:
    source_id = str(pin.get("source_id", ""))
    dataset_key = str(pin.get("dataset_key", ""))
    relative = str(pin.get("relative_path", ""))
    parts = relative.split("/", 2)
    if (
        len(parts) != 3
        or parts[0] != source_id
        or parts[1] != str(pin.get("run_id", ""))
    ):
        _fail(f"Malformed reviewed commerce evidence pin: {relative}")
    raw_input = raw_inputs.get(source_id)
    metadata = (
        raw_input.get("metadata", {}).get(dataset_key)
        if isinstance(raw_input, dict)
        else None
    )
    if not isinstance(metadata, dict):
        _fail(f"Reviewed commerce evidence dataset is not supplied: {relative}")
    canonical = next(
        (
            row
            for row in raw_input.get("files", [])
            if row.get("path") == parts[2] and row.get("dataset_key") == dataset_key
        ),
        None,
    )
    if (
        metadata.get("source_id") != source_id
        or str(metadata.get("run_id", "")) != parts[1]
        or (metadata.get("canonical_evidence_path") or metadata.get("file")) != parts[2]
        or not isinstance(canonical, dict)
        or str(canonical.get("sha256", "")) != str(pin.get("sha256", ""))
    ):
        _fail(f"Stale reviewed commerce evidence pin: {relative}")


def _innovation_record_endpoints(
    innovation_tables: dict[str, list[dict]],
    raw_inputs: dict[str, dict],
) -> dict[tuple[str, str], list[tuple[str, str]]]:
    result: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for row in innovation_tables.get("source_records", []):
        source = str(row.get("source", ""))
        canonical_source = SOURCE_IDS.get(source)
        global_id = str(row.get("global_innovation_id", ""))
        if (
            canonical_source is None
            or canonical_source not in raw_inputs
            or not global_id
        ):
            _fail("Invalid innovation source record in commerce context")
        endpoint = observation_uri(raw_inputs, canonical_source, row)
        for field in ("source_id", "source_key", "observation_id"):
            source_record_id = str(row.get(field, "")).strip()
            item = (global_id, endpoint)
            if source_record_id and item not in result[(source, source_record_id)]:
                result[(source, source_record_id)].append(item)
    return dict(result)


def _source_observation_endpoints(
    source: str,
    source_tables: dict[str, dict[str, list[dict]]],
    raw_inputs: dict[str, dict],
) -> tuple[dict[str, list[str]], list[str]]:
    if source not in SOURCE_IDS:
        _fail(f"Unknown reviewed commerce source: {source}")
    canonical_source = SOURCE_IDS[source]
    if canonical_source not in source_tables or canonical_source not in raw_inputs:
        _fail(f"Reviewed commerce source is not supplied: {source}")
    by_record: dict[str, list[str]] = defaultdict(list)
    all_endpoints: list[str] = []
    for observation in source_tables[canonical_source].get("source_observations", []):
        endpoint = observation_uri(raw_inputs, canonical_source, observation)
        all_endpoints.append(endpoint)
        for field in ("source_id", "source_key", "observation_id"):
            record_id = str(observation.get(field, "")).strip()
            if record_id and endpoint not in by_record[record_id]:
                by_record[record_id].append(endpoint)
    if not all_endpoints:
        _fail(f"Reviewed commerce source has no observations: {source}")
    return dict(by_record), all_endpoints


def _validate_evidence_endpoint(
    source: str,
    source_record_id: str,
    citation_source_record_id: str,
    locator: str,
    source_endpoints: dict[str, tuple[dict[str, list[str]], list[str]]],
) -> None:
    canonical_source = SOURCE_IDS.get(source)
    locator_source = locator_parts(locator)[0]
    if canonical_source is None or locator_source != canonical_source:
        _fail(f"Reviewed commerce evidence belongs to another source: {source}")
    by_record, _ = source_endpoints[source]
    if not source_record_id or source_record_id not in by_record:
        _fail(
            f"Reviewed commerce context belongs to no source record: "
            f"{source}:{source_record_id}"
        )
    if not citation_source_record_id or not any(
        locator_matches(locator, endpoint)
        for endpoint in by_record.get(citation_source_record_id, [])
    ):
        _fail(
            f"Reviewed commerce evidence belongs to another source record: "
            f"{source}:{citation_source_record_id}"
        )


def _validate_aggregate_endpoint(
    source: str,
    locator: str,
    source_endpoints: dict[str, tuple[dict[str, list[str]], list[str]]],
) -> None:
    canonical_source = SOURCE_IDS.get(source)
    locator_source = locator_parts(locator)[0]
    if canonical_source is None or locator_source != canonical_source:
        _fail(f"Reviewed commerce aggregate belongs to another source: {source}")
    _, endpoints = source_endpoints[source]
    if not any(locator_matches(locator, endpoint) for endpoint in endpoints):
        _fail(
            f"Reviewed commerce aggregate belongs to no source observation: {locator}"
        )

def _validate_learning_cultural_business_candidate(candidate: dict) -> bool:
    contract = candidate.get("eligibility_contract")
    if contract is None:
        return False
    if (
        contract != LEARNING_CULTURAL_BUSINESS_CONTRACT
        or candidate.get("source") != "learning_area_based"
        or candidate.get("kind") != "operator"
        or candidate.get("status") != "supported"
        or candidate.get("basis") != LEARNING_CULTURAL_BUSINESS_BASIS
        or candidate.get("identity_quality") not in LEARNING_IDENTITY_QUALITIES
        or not str(candidate.get("identity_review_note", "")).strip()
    ):
        _fail("Invalid Learning cultural-business eligibility contract")
    if (
        candidate.get("identity_quality") == "missing_source_name"
    ) != (candidate.get("display_name") == "Name unavailable"):
        _fail("Learning cultural-business missing-name placeholder is inconsistent")
    return True



def _validate_reviews(
    review: dict[str, list],
    pins: dict[str, dict],
    source_tables: dict[str, dict[str, list[dict]]],
    raw_inputs: dict[str, dict],
    innovation_tables: dict[str, list[dict]],
) -> list[dict]:
    for pin in pins.values():
        _validate_pin(pin, raw_inputs)
    pin_bases = {f"evidence://{relative}" for relative in pins}
    innovation_endpoints = _innovation_record_endpoints(innovation_tables, raw_inputs)
    reviewed_sources = {
        str(row.get("source", ""))
        for key in ("candidates", "aggregate_claims")
        for row in review[key]
    }
    source_endpoints = {
        source: _source_observation_endpoints(source, source_tables, raw_inputs)
        for source in reviewed_sources
    }
    learning_tables = source_tables.get(SOURCE_IDS["learning_area_based"], {})
    learning_links = {
        str(row.get("source_id", "")): str(row.get("business_id", ""))
        for row in learning_tables.get("business_observation_links", [])
    }
    learning_locations = {
        str(row.get("location_id", "")): row
        for row in learning_tables.get("locations", [])
    }
    seen: set[str] = set()
    claims: list[dict] = []
    business_bases = {
        "source_reported_business",
        "source_reported_manufacturer",
        "source_reported_seller",
    }
    for candidate in review["candidates"]:
        cid = str(candidate.get("candidate_id", ""))
        source = str(candidate.get("source", ""))
        if not cid or cid in seen:
            _fail(f"Missing or duplicate reviewed commerce candidate: {cid}")
        if source not in SOURCE_IDS:
            _fail(f"Unknown reviewed commerce source: {source}")
        seen.add(cid)
        status, kind, basis = (
            candidate.get("status"),
            candidate.get("kind"),
            candidate.get("basis"),
        )
        if status not in STATUSES or kind not in KINDS:
            _fail(f"Unsupported commerce status or entity kind: {cid}")
        learning_cultural_business = _validate_learning_cultural_business_candidate(
            candidate
        )
        if not str(candidate.get("reason", "")).strip() or basis not in BASES:
            _fail(f"Missing reason or unsupported commerce evidence basis: {cid}")
        if status == "supported":
            if (kind == "operator") != (
                basis in business_bases | {LEARNING_CULTURAL_BUSINESS_BASIS}
            ):
                _fail(f"Commerce evidence basis does not establish entity kind: {cid}")
            if kind == "offering" and not all(
                str(candidate.get(field, "")).strip()
                for field in ("output_type", "unit_basis")
            ):
                _fail(f"Supported commerce offering lacks a counting unit: {cid}")
            if not str(candidate.get("display_name", "")).strip() or not candidate.get(
                "evidence"
            ):
                _fail(f"Supported commerce candidate lacks name or evidence: {cid}")
        for evidence in candidate.get("evidence", []):
            source_record_id = str(evidence.get("source_record_id", ""))
            citation_source_record_id = str(
                evidence.get("citation_source_record_id") or source_record_id
            )
            global_innovation_id = str(evidence.get("global_innovation_id", ""))
            if candidate.get("source") == "learning_area_based" and kind == "operator":
                business_id = str(candidate.get("source_local_id", ""))
                if any(
                    learning_links.get(record_id) != business_id
                    for record_id in (source_record_id, citation_source_record_id)
                ):
                    _fail(
                        f"Commerce evidence belongs to another Learning identity: {cid}"
                    )
            locator = str(evidence.get("raw_locator", ""))
            if global_innovation_id and not any(
                innovation_id == global_innovation_id
                and locator_matches(locator, endpoint)
                for innovation_id, endpoint in innovation_endpoints.get(
                    (source, citation_source_record_id),
                    [],
                )
            ):
                _fail(f"Commerce evidence belongs to another innovation: {cid}")
            _validate_evidence_endpoint(
                source,
                source_record_id,
                citation_source_record_id,
                locator,
                source_endpoints,
            )
            base = locator.split("#", 1)[0]
            if base not in pin_bases:
                _fail(f"Unpinned reviewed commerce evidence: {locator}")
            actual = _evidence_text(resolve_evidence(raw_inputs, locator))
            quote = _evidence_text(evidence.get("quote"))
            if quote not in actual or (
                status == "supported"
                and not quote
                and not (
                    learning_cultural_business
                    and candidate.get("identity_quality") == "missing_source_name"
                    and not actual
                )
            ):
                _fail(f"Reviewed commerce quotation does not match source: {cid}")
            claims.append(
                {
                    "evidence_id": stable_id("commerce_evidence", cid, locator, quote),
                    "candidate_id": cid,
                    "source": candidate.get("source", ""),
                    "raw_locator": locator,
                    "evidence_text": quote,
                    "relationship": evidence.get("relationship", ""),
                    "source_record_id": source_record_id,
                    "citation_source_record_id": citation_source_record_id,
                    "global_innovation_id": global_innovation_id,
                    "status": status,
                    "basis": basis,
                }
            )
        for location in candidate.get("locations", []):
            location_id = str(location.get("location_id", ""))
            original = learning_locations.get(location_id)
            if (
                candidate.get("source") != "learning_area_based"
                or not location_id
                or original != location
            ):
                _fail(f"Stale or unsupported reviewed commerce location: {cid}")
            if str(location.get("business_id", "")) != str(
                candidate.get("source_local_id", "")
            ):
                _fail(f"Reviewed commerce location belongs to another business: {cid}")
    evidence_ids = [row["evidence_id"] for row in claims]
    if len(evidence_ids) != len(set(evidence_ids)):
        _fail("Duplicate reviewed commerce evidence claim")
    aggregate_ids = [str(row.get("claim_id", "")) for row in review["aggregate_claims"]]
    if not all(aggregate_ids) or len(aggregate_ids) != len(set(aggregate_ids)):
        _fail("Missing or duplicate commerce aggregate claim ID")
    for aggregate in review["aggregate_claims"]:
        locator = str(aggregate.get("raw_locator", ""))
        _validate_aggregate_endpoint(
            str(aggregate.get("source", "")),
            locator,
            source_endpoints,
        )
        if locator.split("#", 1)[0] not in pin_bases:
            _fail(f"Unpinned reviewed commerce aggregate: {locator}")
        actual = _evidence_text(resolve_evidence(raw_inputs, locator))
        quote = _evidence_text(aggregate.get("quote"))
        value = aggregate.get("value")
        if not quote or quote not in actual:
            _fail(f"Stale reviewed commerce aggregate evidence: {locator}")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            or not str(aggregate.get("reason", "")).strip()
            or not str(aggregate.get("unit", "")).strip()
        ):
            _fail("Invalid reviewed commerce aggregate claim")
        value_quote = _evidence_text(aggregate.get("value_quote"))
        number = re.search(r"\d+(?:\.\d+)?", value_quote)
        if not number or value_quote not in quote or float(number.group()) != value:
            _fail("Reviewed commerce aggregate number lacks exact quotation support")
    return claims


def _reconcile(
    review: dict[str, list], tables: dict[str, list[dict]]
) -> tuple[dict[str, str], list[dict], list[dict]]:
    candidates = {
        row["candidate_id"]: row
        for row in review["candidates"]
        if row["status"] == "supported"
    }
    baseline: dict[str, dict] = {}
    for kind, table in (
        ("operator", "global_operators"),
        ("offering", "global_offerings"),
    ):
        for row in tables[table]:
            baseline[row[f"global_{kind}_id"]] = {"kind": kind, **row}
    if candidates.keys() & baseline.keys():
        _fail("Commerce candidate and baseline namespaces collide")
    kinds = {key: row["kind"] for key, row in candidates.items()} | {
        key: row["kind"] for key, row in baseline.items()
    }
    union = UnionFind(kinds)
    decisions = review["identity_decisions"]
    review_ids = [str(row.get("review_id", "")) for row in decisions]
    if not all(review_ids) or len(review_ids) != len(set(review_ids)):
        _fail("Missing or duplicate reviewed commerce identity decision")
    for decision in decisions:
        left, right = decision.get("left"), decision.get("right")
        if (
            left not in kinds
            or right not in kinds
            or left == right
            or kinds[left] != kinds[right]
        ):
            _fail(f"Invalid commerce identity endpoints: {decision.get('review_id')}")
        if (
            decision.get("decision") not in {"match", "keep_separate", "unresolved"}
            or not str(decision.get("reason", "")).strip()
        ):
            _fail("Invalid commerce identity decision")
        if set(decision.get("evidence_refs", [])) != {left, right}:
            _fail("Commerce identity review must cite both endpoint contexts")
    for decision in decisions:
        if decision["decision"] == "match":
            union.union(decision["left"], decision["right"])
    for decision in decisions:
        if decision["decision"] != "match" and union.find(
            decision["left"]
        ) == union.find(decision["right"]):
            _fail(f"Commerce match crosses protected review: {decision['review_id']}")
    uncertain = {
        endpoint
        for row in decisions
        if row["decision"] == "unresolved"
        for endpoint in (row["left"], row["right"])
    }
    mapping: dict[str, str] = {}
    crosswalk: list[dict] = []
    for members in components(union):
        previous = [member for member in members if member in baseline]
        if len(previous) > 1:
            _fail("New commerce evidence bridges distinct baseline identities")
        kind = kinds[members[0]]
        global_id = previous[0] if previous else stable_id(kind, *members)
        mapping.update({member: global_id for member in members})
        for candidate_id in members:
            if candidate_id not in candidates:
                continue
            candidate = candidates[candidate_id]
            crosswalk.append(
                {
                    f"global_{kind}_id": global_id,
                    f"source_{kind}_id": f"{candidate['source']}:{candidate['source_local_id']}",
                    "candidate_id": candidate_id,
                    "source": candidate["source"],
                    f"source_local_{kind}_id": candidate["source_local_id"],
                    "display_name": candidate["display_name"],
                    "identity_status": "reviewed_identity"
                    if len(members) > 1
                    else "reviewed_provisional_identity",
                    "source_details_json": json_text(
                        {
                            "basis": candidate["basis"],
                            "eligibility_contract": candidate.get(
                                "eligibility_contract", ""
                            ),
                            "identity_quality": candidate.get("identity_quality", ""),
                            "identity_review_note": candidate.get(
                                "identity_review_note", ""
                            ),
                            "output_type": candidate.get("output_type", ""),
                            "unit_basis": candidate.get("unit_basis", ""),
                            "aliases_json": json_text(candidate.get("aliases", [])),
                            "candidate_id": candidate_id,
                        }
                    ),
                }
            )
        aliases = {
            alias
            for candidate_id in members
            if candidate_id in candidates
            for alias in (
                candidates[candidate_id]["display_name"],
                *candidates[candidate_id].get("aliases", []),
            )
            if alias
        }
        table_name = "global_operators" if kind == "operator" else "global_offerings"
        if previous:
            global_row = next(
                row
                for row in tables[table_name]
                if row[f"global_{kind}_id"] == global_id
            )
            try:
                aliases.update(json.loads(global_row["aliases_json"]))
            except (TypeError, ValueError) as exc:
                raise PipelineError("Invalid baseline commerce aliases") from exc
            global_row["aliases_json"] = json_text(sorted(aliases))
            if len(members) > 1:
                global_row["identity_status"] = "reviewed_extended_identity"
        else:
            global_row = {
                f"global_{kind}_id": global_id,
                "display_name": candidates[members[0]]["display_name"],
                "aliases_json": json_text(sorted(aliases)),
                "source_count": 0,
                "source_entity_count": 0,
                "identity_status": "reviewed_identity"
                if len(members) > 1
                else "reviewed_provisional_identity",
            }
            tables[table_name].append(global_row)
        if uncertain.intersection(members):
            global_row["identity_status"] = "reviewed_possible_duplicate"
    return mapping, crosswalk, decisions


def _build_offering_families(
    review: dict[str, list], tables: dict[str, list[dict]], mapping: dict[str, str]
) -> None:
    offerings = {row["global_offering_id"]: row for row in tables["global_offerings"]}
    families: list[dict] = []
    members: list[dict] = []
    decisions: list[dict] = []
    assigned: dict[str, str] = {}
    range_ids: set[str] = set()
    group_ids: set[str] = set()
    allowed_roles = {"family_representation", "variant", "range_evidence"}
    for group in review.get("counting_groups", []):
        family_id = group.get("family_id")
        if group.get("basis") not in {
            "ordinary_variants",
            "catalogue_family_and_variants",
        }:
            _fail("Unknown reviewed commerce family basis")
        if (
            family_id in group_ids
            or not str(group.get("display_name", "")).strip()
            or not str(group.get("reason", "")).strip()
        ):
            _fail("Duplicate or incomplete reviewed commerce family")
        group_ids.add(family_id)
        refs = {row["entity_id"] for row in group["members"]}
        if set(group.get("evidence_refs", [])) != refs or len(refs) != len(
            group["members"]
        ):
            _fail("Commerce family review must cite every distinct member")
        resolved: dict[str, str] = {}
        for member in group["members"]:
            endpoint, role = member.get("entity_id"), member.get("role")
            global_id = mapping.get(endpoint)
            if global_id not in offerings or role not in allowed_roles:
                _fail("Commerce family member is not an admitted offering")
            if global_id in resolved and resolved[global_id] != role:
                if "range_evidence" in {resolved[global_id], role}:
                    _fail("One commerce offering has contradictory family roles")
                role = "family_representation"
            resolved[global_id] = role
        if not any(role != "range_evidence" for role in resolved.values()):
            _fail("A commerce family needs an identified product")
        for global_id, role in sorted(resolved.items()):
            if role == "range_evidence":
                range_ids.add(global_id)
            else:
                if global_id in assigned:
                    _fail(
                        "A commerce product or variant belongs to two counted families"
                    )
                assigned[global_id] = family_id
            members.append(
                {
                    "family_id": family_id,
                    "global_offering_id": global_id,
                    "membership_role": role,
                    "reason": group["reason"],
                }
            )
        families.append(
            {
                "family_id": family_id,
                "display_name": group["display_name"],
                "member_count": len(resolved),
                "identity_status": "reviewed_product_family",
                "counting_basis": group["basis"],
            }
        )
        decisions.append(
            {
                "family_id": family_id,
                "display_name": group["display_name"],
                "basis": group["basis"],
                "reason": group["reason"],
                "members_json": json_text(group["members"]),
                "evidence_refs_json": json_text(group["evidence_refs"]),
            }
        )
    if range_ids & assigned.keys():
        _fail("A broad commerce range cannot add its own family count")
    for global_id, row in sorted(offerings.items()):
        if global_id in assigned or global_id in range_ids:
            continue
        family_id = stable_id("offering_family", global_id)
        if family_id in group_ids:
            _fail("Configured commerce family ID collides with singleton family")
        families.append(
            {
                "family_id": family_id,
                "display_name": row["display_name"],
                "member_count": 1,
                "identity_status": row["identity_status"],
                "counting_basis": "individual_supported_offering",
            }
        )
        members.append(
            {
                "family_id": family_id,
                "global_offering_id": global_id,
                "membership_role": "family_representation",
                "reason": "One supported offering; no reviewed family grouping changes its unit.",
            }
        )
    if {row["global_offering_id"] for row in members} != offerings.keys():
        _fail("An admitted commerce offering lost family membership")
    tables["offering_families"] = sorted(families, key=lambda row: row["family_id"])
    tables["offering_family_members"] = sorted(
        members, key=lambda row: (row["family_id"], row["global_offering_id"])
    )
    tables["offering_family_decisions"] = decisions


def build_tables(
    source_tables: dict[str, dict[str, list[dict]]],
    reviews: dict[str, Any],
    raw_inputs: dict[str, dict],
    geography: Any,
    baseline_tables: dict[str, list[dict]],
    people_tables: dict[str, list[dict]],
    innovation_tables: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """Extend a fresh accepted offering baseline using only injected reviewed evidence."""
    del geography
    review, pins = _load_reviews(reviews)
    claims = _validate_reviews(
        review, pins, source_tables, raw_inputs, innovation_tables
    )
    tables = copy.deepcopy(baseline_tables)
    required = {
        "global_operators",
        "global_offerings",
        "operator_crosswalk",
        "offering_crosswalk",
        "locations",
        "measure_results",
    }
    if not required <= tables.keys() or any(
        not isinstance(tables[name], list) for name in required
    ):
        _fail("Reviewed commerce baseline tables are incomplete")
    person_ids = {
        row.get("global_person_id") for row in people_tables.get("global_people", [])
    }
    if any(
        row.get("global_person_id") not in person_ids
        for row in tables.get("person_operator_links", [])
    ):
        _fail("Commerce baseline person link is absent from injected people identities")
    mapping, crosswalk, decisions = _reconcile(review, tables)
    for kind in ("operator", "offering"):
        key = f"global_{kind}_id"
        table_name = f"{kind}_crosswalk"
        tables[table_name].extend(row for row in crosswalk if key in row)
        source_ids = [row[f"source_{kind}_id"] for row in tables[table_name]]
        if len(source_ids) != len(set(source_ids)):
            _fail("Reviewed commerce source-local identity already exists in baseline")
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in tables[table_name]:
            grouped[row[key]].append(row)
        global_table = "global_operators" if kind == "operator" else "global_offerings"
        for row in tables[global_table]:
            row["source_count"] = len({item["source"] for item in grouped[row[key]]})
            row["source_entity_count"] = len(grouped[row[key]])
    candidates = {row["candidate_id"]: row for row in review["candidates"]}
    tables["reviewed_evidence"] = [
        {
            **claim,
            "entity_kind": candidates[claim["candidate_id"]]["kind"],
            "global_operator_id": mapping.get(claim["candidate_id"], "")
            if candidates[claim["candidate_id"]]["kind"] == "operator"
            else "",
            "global_offering_id": mapping.get(claim["candidate_id"], "")
            if candidates[claim["candidate_id"]]["kind"] == "offering"
            else "",
        }
        for claim in claims
    ]
    tables["review_coverage"] = [
        {
            "candidate_id": row["candidate_id"],
            "source": row["source"],
            "entity_kind": row["kind"],
            "display_name": row.get("display_name", ""),
            "status": row["status"],
            "basis": row["basis"],
            "eligibility_contract": row.get("eligibility_contract", ""),
            "identity_quality": row.get("identity_quality", ""),
            "identity_review_note": row.get("identity_review_note", ""),
            "output_type": row.get("output_type", ""),
            "unit_basis": row.get("unit_basis", ""),
            "reason": row["reason"],
            "global_entity_id": mapping.get(row["candidate_id"], ""),
            "audit_ref": row.get("audit_ref", ""),
        }
        for row in review["candidates"]
    ]
    tables["reviewed_identity_decisions"] = [
        {
            **{key: value for key, value in row.items() if key != "evidence_refs"},
            "evidence_refs_json": json_text(row["evidence_refs"]),
        }
        for row in decisions
    ]
    tables["reported_product_totals"] = [
        {**row, "additive_to_k07": "False", "membership_status": "not_reconciled"}
        for row in review["aggregate_claims"]
    ]
    for candidate in review["candidates"]:
        candidate_id = candidate["candidate_id"]
        if candidate_id not in mapping:
            continue
        kind = candidate["kind"]
        for location in candidate.get("locations", []):
            tables["locations"].append(
                {
                    **location,
                    "source_location_id": stable_id(
                        "commerce_location", candidate_id, location["location_id"]
                    ),
                    "source": candidate["source"],
                    "source_entity_id": f"{candidate['source']}:{candidate['source_local_id']}",
                    f"source_{kind}_id": f"{candidate['source']}:{candidate['source_local_id']}",
                    f"global_{kind}_id": mapping[candidate_id],
                    "global_offering_id": mapping[candidate_id]
                    if kind == "offering"
                    else "",
                    "global_operator_id": mapping[candidate_id]
                    if kind == "operator"
                    else "",
                    "raw_locator": candidate["evidence"][0]["raw_locator"].rsplit(
                        "/", 1
                    )[0],
                    "status": location.get(
                        "resolution_status", location.get("status", "")
                    ),
                    "source_details_json": json_text(
                        {
                            "location_table": "normalized://source_local/learning-area-based-v1/locations.csv",
                            "location_id": location["location_id"],
                        }
                    ),
                }
            )
    operator_ids = {row["global_operator_id"] for row in tables["global_operators"]}
    offering_ids = {row["global_offering_id"] for row in tables["global_offerings"]}
    tables["reviewed_relationships"] = []
    for relationship in review["relationships"]:
        left, right = relationship["subject"], relationship["object"]
        left_global, right_global = mapping.get(left, left), mapping.get(right, right)
        if not str(relationship.get("reason", "")).strip() or not relationship.get(
            "evidence_refs"
        ):
            _fail("Reviewed commerce relationship lacks evidence")
        if left_global not in operator_ids or right_global not in offering_ids:
            _fail("Reviewed commerce relationship must link operator to offering")
        if relationship.get("relationship") not in {
            "manufacturer_of",
            "seller_of",
            "service_provider_of",
        }:
            _fail("Unsupported reviewed commerce relationship type")
        evidence_candidate = relationship.get("evidence_candidate", left)
        if (
            evidence_candidate not in {left, right}
            or evidence_candidate not in candidates
            or evidence_candidate not in mapping
        ):
            _fail("Reviewed commerce relationship evidence lacks an admitted endpoint")
        locators = {
            item["raw_locator"] for item in candidates[evidence_candidate]["evidence"]
        }
        if not set(relationship["evidence_refs"]) <= locators:
            _fail("Reviewed commerce relationship cites evidence outside its endpoint")
        tables["reviewed_relationships"].append(
            {
                **{
                    key: value
                    for key, value in relationship.items()
                    if key != "evidence_refs"
                },
                "subject_global_id": left_global,
                "object_global_id": right_global,
                "evidence_refs_json": json_text(relationship["evidence_refs"]),
            }
        )
    _build_offering_families(review, tables, mapping)
    measures = (
        ("K05_source_supported_operators", "global_operators", "global_operator_id"),
        ("K07_source_reported_offerings", "offering_families", "family_id"),
    )
    tables["measure_contributions"] = [
        {"measure": measure, "entity_id": row[key]}
        for measure, table_name, key in measures
        for row in tables[table_name]
    ]
    for result in tables["measure_results"]:
        for measure, table_name, key in measures:
            if result.get("measure") == measure:
                result.update(
                    {
                        "value": len(tables[table_name]),
                        "scope": "Accepted baseline plus admitted and reconciled reviewed commerce evidence; incomplete narrative coverage remains explicit",
                        "status": "reviewed_partial_coverage",
                        "counting_key": key,
                    }
                )
    source_files = {
        str(row.get("path", "")): dict(row)
        for row in tables.get("source_files", [])
        if row.get("path")
    }
    for relative, pin in sorted(pins.items()):
        path = f"evidence://{relative}"
        if path in source_files:
            if str(source_files[path].get("sha256", "")) != str(pin["sha256"]):
                _fail(f"Reviewed commerce provenance conflicts with baseline: {path}")
            continue
        source_files[path] = {
            "path": path,
            "sha256": pin["sha256"],
            "fingerprint_kind": "raw_file",
            "reviewed_sha256": pin["sha256"],
        }
    tables["source_files"] = [source_files[path] for path in sorted(source_files)]
    validate_output(tables)
    return {
        name: [
            {column: row.get(column, "") for column in TABLE_COLUMNS[name]}
            for row in rows
        ]
        for name, rows in tables.items()
        if name in TABLE_COLUMNS
    }
