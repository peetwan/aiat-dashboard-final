"""Pure reviewed cross-source innovation identities and K04 evidence tables."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from ..common import Components, PipelineError, canonical_json, normalize, stable_id
from .innovation_sources import (
    SOURCE_ORDER,
    LocalInnovation,
    SourceBundle,
    load_sources,
)
from .resolution import locator_matches, logical_source, review_payloads_under

TABLE_COLUMNS = {
    "global_innovations": (
        "global_innovation_id",
        "display_name",
        "aliases_json",
        "member_count",
        "source_count",
        "sources_json",
        "source_ids_json",
        "identity_status",
        "qualifies_k04",
    ),
    "innovation_crosswalk": (
        "global_innovation_id",
        "source",
        "local_innovation_id",
        "local_display_name",
        "local_identity_status",
        "source_ids_json",
    ),
    "source_records": (
        "global_innovation_id",
        "source",
        "local_innovation_id",
        "source_id",
        "source_key",
        "observation_id",
        "title_raw",
        "raw_file",
        "row_locator",
        "file_sha256",
    ),
    "identity_decisions": (
        "review_id",
        "decision",
        "status",
        "local_members_json",
        "raw_members_json",
        "reason",
        "evidence_json",
        "origin",
        "review_file",
    ),
    "readiness_evidence": (
        "global_innovation_id",
        "source",
        "local_innovation_id",
        "source_id",
        "observation_id",
        "assessment_id",
        "source_locator",
        "scale",
        "raw_level",
        "numeric_level",
        "label_raw",
        "qualifies_k04",
        "basis",
        "assessment_context",
    ),
    "innovation_use_locations": (
        "global_innovation_id",
        "source",
        "local_innovation_id",
        "source_id",
        "observation_id",
        "location_id",
        "location_role",
        "province_raw",
        "province_normalized",
        "province_code",
        "district_normalized",
        "district_code",
        "subdistrict_normalized",
        "subdistrict_code",
        "resolution_status",
        "coverage_eligibility",
        "source_locator",
    ),
    "measure_results": ("measure", "value", "unit", "status", "definition"),
    "measure_contributions": (
        "measure",
        "global_innovation_id",
        "contribution",
        "status",
        "qualifying_assessment_ids_json",
    ),
    "province_k04_contributions": (
        "measure",
        "province_code",
        "province_name",
        "global_innovation_id",
        "contribution",
        "identity_status",
        "status",
        "qualifying_assessment_ids_json",
        "use_location_ids_json",
        "evidence_context_note",
    ),
    "province_k04_results": (
        "measure",
        "province_code",
        "province_name",
        "value",
        "unit",
        "status",
    ),
    "unresolved_components": (
        "unresolved_component_id",
        "current_identity_count",
        "candidate_edge_count",
        "demonstrated_nonconflicting_identity_reduction",
        "current_k04_count",
        "demonstrated_nonconflicting_k04_reduction",
        "interpretation",
    ),
    "unresolved_component_members": (
        "unresolved_component_id",
        "global_innovation_id",
        "qualifies_k04",
        "demonstrated_scenario_group_id",
    ),
    "unresolved_component_edges": (
        "unresolved_edge_id",
        "unresolved_component_id",
        "edge_role",
        "left_global_innovation_id",
        "right_global_innovation_id",
        "left_local_member",
        "right_local_member",
        "decision_id",
        "decision",
        "origin",
        "source_locator",
        "evidence_json",
        "reason",
        "demonstrated_scenario_action",
        "selected_in_demonstrated_scenario",
    ),
    "review_supersessions": (
        "superseded_review_id",
        "left_local_member",
        "right_local_member",
        "left_global_innovation_id",
        "right_global_innovation_id",
        "superseding_review_ids_json",
        "source_locator",
        "reason",
    ),
    "source_files": ("path", "sha256", "size_bytes", "role"),
}


@dataclass(frozen=True)
class Review:
    review_id: str
    decision: str
    local_members: tuple[str, ...]
    raw_members: tuple[dict[str, Any], ...]
    reason: str
    evidence: tuple[dict[str, Any], ...]
    origin: str
    review_file: str


def _all_items(bundles: dict[str, SourceBundle]) -> dict[str, LocalInnovation]:
    return {
        item.key: item
        for source in SOURCE_ORDER
        for item in bundles[source].innovations.values()
    }


def _review_pairs(members: tuple[str, ...]) -> set[frozenset[str]]:
    if len(members) == 2:
        return {frozenset(members)}
    return {
        frozenset((left, right))
        for index, left in enumerate(members)
        for right in members[index + 1 :]
        if left.split(":", 1)[0] != right.split(":", 1)[0]
    }


def _resolve_member(bundle: SourceBundle, member: dict[str, Any], where: str) -> str:
    source_id = str(member.get("source_id", ""))
    member_key = member.get("source_member_key")
    if member_key is not None:
        local_id = bundle.source_member_to_local.get(str(member_key))
        if local_id is None or source_id not in bundle.innovations[local_id].source_ids:
            raise PipelineError(f"{where} has a stale or mismatched context member")
        return local_id
    if source_id in bundle.source_id_to_local:
        return bundle.source_id_to_local[source_id]
    matches = [
        item.local_innovation_id
        for item in bundle.innovations.values()
        if source_id in item.source_ids
    ]
    if len(matches) > 1:
        raise PipelineError(
            f"{where} source ID is reused; source_member_key is required"
        )
    raise PipelineError(
        f"{where} member is stale or unknown: {bundle.source}:{source_id}"
    )


def _load_reviews(
    reviews: dict[str, Any], bundles: dict[str, SourceBundle]
) -> list[Review]:
    payloads = review_payloads_under(reviews, "cross_source_innovations/reviews")
    if not payloads:
        raise PipelineError(
            "innovations input contract: no locked innovation review payloads"
        )
    result: list[Review] = []
    seen: set[str] = set()
    for path, payload in payloads:
        if not isinstance(payload, list):
            raise PipelineError(f"Innovation review {path} must contain a list")
        for position, raw in enumerate(payload):
            where = f"{path}:{position}"
            if not isinstance(raw, dict):
                raise PipelineError(f"{where} must be an object")
            review_id = str(raw.get("review_id", ""))
            if not review_id or review_id in seen:
                raise PipelineError(
                    f"Missing or duplicate innovation review_id at {where}"
                )
            seen.add(review_id)
            decision, origin, reason = (
                raw.get("decision"),
                raw.get("origin"),
                normalize(raw.get("reason")),
            )
            if (
                decision not in {"must_link", "cannot_link", "unresolved"}
                or origin not in {"analyst_review", "user_confirmed"}
                or not reason
            ):
                raise PipelineError(f"{where} has invalid decision, origin, or reason")
            members = raw.get("members")
            evidence = raw.get("evidence")
            if (
                not isinstance(members, list)
                or len(members) < 2
                or not isinstance(evidence, list)
                or not evidence
            ):
                raise PipelineError(
                    f"{where} requires at least two members and evidence"
                )
            raw_members: list[dict[str, Any]] = []
            local_members: set[str] = set()
            selected: dict[tuple[str, str], set[str]] = defaultdict(set)
            for member in members:
                if not isinstance(member, dict):
                    raise PipelineError(f"{where} has invalid member")
                source = logical_source(str(member.get("source", "")))
                source_id = str(member.get("source_id", ""))
                if source not in bundles or not source_id:
                    raise PipelineError(f"{where} has invalid member endpoint")
                local_id = _resolve_member(bundles[source], member, where)
                local_members.add(f"{source}:{local_id}")
                selected[source, source_id].add(local_id)
                raw_members.append(dict(member, source=source))
            if len(local_members) < 2:
                raise PipelineError(
                    f"{where} resolves to fewer than two source-local identities"
                )
            sources = {value.split(":", 1)[0] for value in local_members}
            if len(sources) == 1 and (
                len(local_members) != 2 or decision == "must_link"
            ):
                raise PipelineError(
                    f"{where} same-source merge belongs in the source builder"
                )
            for claim in evidence:
                if not isinstance(claim, dict):
                    raise PipelineError(f"{where} has invalid evidence")
                source = logical_source(str(claim.get("source", "")))
                source_id, locator = (
                    str(claim.get("source_id", "")),
                    str(claim.get("locator", "")),
                )
                if (source, source_id) not in selected or not normalize(
                    claim.get("claim")
                ):
                    raise PipelineError(
                        f"{where} evidence does not name a reviewed member"
                    )
                bases = [
                    row["raw_file"] + "#" + row["row_locator"]
                    for row in bundles[source].source_records
                    if row["source_id"] == source_id
                    and row["local_innovation_id"] in selected[source, source_id]
                ]
                if not bases or not any(
                    locator_matches(locator, base) for base in bases
                ):
                    raise PipelineError(
                        f"{where} has stale evidence locator for {source}:{source_id}"
                    )
            expected = raw.get("expected_titles", {})
            if expected:
                if not isinstance(expected, dict):
                    raise PipelineError(f"{where} expected_titles must be an object")
                for key, title in expected.items():
                    source_name, source_id = key.split(":", 1)
                    source = logical_source(source_name)
                    titles = {
                        normalize(row["title_raw"]).casefold()
                        for row in bundles[source].source_records
                        if row["source_id"] == source_id
                    }
                    if normalize(title).casefold() not in titles:
                        raise PipelineError(f"{where} expected title changed for {key}")
            result.append(
                Review(
                    review_id,
                    decision,
                    tuple(sorted(local_members)),
                    tuple(raw_members),
                    reason,
                    tuple(evidence),
                    origin,
                    f"review-config://{path}",
                )
            )
    return sorted(result, key=lambda row: row.review_id)


def _boundary_rows(
    reviews: list[Review], bundles: dict[str, SourceBundle]
) -> list[dict[str, Any]]:
    rows = [row for bundle in bundles.values() for row in bundle.boundary_evidence]
    for review in reviews:
        if review.decision not in {"cannot_link", "unresolved"}:
            continue
        for pair in _review_pairs(review.local_members):
            rows.append(
                {
                    "pair": pair,
                    "boundary_kind": "cannot_link_constraint"
                    if review.decision == "cannot_link"
                    else "unresolved_candidate",
                    "decision_id": review.review_id,
                    "decision": review.decision,
                    "origin": review.origin,
                    "source_locator": f"{review.review_file}#review_id={review.review_id}",
                    "evidence_json": canonical_json(review.evidence),
                    "reason": review.reason,
                }
            )
    return rows


def _apply_reviews(
    items: dict[str, LocalInnovation],
    reviews: list[Review],
    protected: set[frozenset[str]],
) -> tuple[
    dict[str, str], list[dict[str, Any]], set[frozenset[str]], set[frozenset[str]]
]:
    cannot, unresolved = set(), set()
    dispositions: dict[frozenset[str], str] = {}
    for review in reviews:
        for pair in _review_pairs(review.local_members):
            existing = dispositions.get(pair)
            if existing and existing != review.decision:
                raise PipelineError(
                    f"Conflicting innovation reviews for {sorted(pair)}"
                )
            dispositions[pair] = review.decision
            if review.decision == "cannot_link":
                cannot.add(pair)
            elif review.decision == "unresolved":
                unresolved.add(pair)
    components = Components(items, protected | cannot | unresolved)
    decision_rows = []
    for review in reviews:
        outcomes = []
        if review.decision == "must_link":
            anchor = review.local_members[0]
            outcomes = [
                components.merge(anchor, member) for member in review.local_members[1:]
            ]
            if "blocked_cannot_link" in outcomes:
                raise PipelineError(
                    f"Must-link {review.review_id} violates a protected component boundary"
                )
        decision_rows.append(
            {
                "review_id": review.review_id,
                "decision": review.decision,
                "status": "applied_union"
                if review.decision == "must_link"
                else "protected_boundary",
                "local_members_json": canonical_json(review.local_members),
                "raw_members_json": canonical_json(review.raw_members),
                "reason": review.reason,
                "evidence_json": canonical_json(review.evidence),
                "origin": review.origin,
                "review_file": review.review_file,
            }
        )
    groups: dict[str, list[str]] = defaultdict(list)
    for key in sorted(items):
        groups[components.find(key)].append(key)
    mapping = {}
    for members in groups.values():
        global_id = stable_id("global_innovation", *sorted(members))
        mapping.update({member: global_id for member in members})
    for pair in protected | cannot | unresolved:
        left, right = tuple(pair)
        if mapping[left] == mapping[right]:
            raise PipelineError("Protected innovation boundary collapsed")
    return mapping, decision_rows, cannot, unresolved


def _globals(
    items: dict[str, LocalInnovation],
    mapping: dict[str, str],
    readiness: list[dict],
    unresolved: set[frozenset[str]],
) -> tuple[list[dict], list[dict], set[str]]:
    members_by_global: dict[str, list[str]] = defaultdict(list)
    for member, global_id in mapping.items():
        members_by_global[global_id].append(member)
    qualifying = {
        mapping[f"{row['source']}:{row['local_innovation_id']}"]
        for row in readiness
        if row["qualifies_k04"] == "True"
    }
    uncertain = {mapping[member] for pair in unresolved for member in pair}
    rank = {source: index for index, source in enumerate(SOURCE_ORDER)}
    globals_, crosswalk = [], []
    for global_id, members in sorted(members_by_global.items()):
        ordered = sorted(members, key=lambda key: (rank[key.split(":", 1)[0]], key))
        representative = items[ordered[0]]
        sources = sorted({items[member].source for member in members}, key=rank.get)
        source_ids = {
            source: sorted(
                {
                    sid
                    for member in members
                    if items[member].source == source
                    for sid in items[member].source_ids
                }
            )
            for source in sources
        }
        globals_.append(
            {
                "global_innovation_id": global_id,
                "display_name": representative.display_name,
                "aliases_json": canonical_json(
                    sorted(
                        {
                            alias
                            for member in members
                            for alias in items[member].aliases
                            if alias
                        }
                    )
                ),
                "member_count": len(members),
                "source_count": len(sources),
                "sources_json": canonical_json(sources),
                "source_ids_json": canonical_json(source_ids),
                "identity_status": "provisional_unresolved_candidates"
                if global_id in uncertain
                else "reviewed_cross_source"
                if len(sources) > 1
                else "source_local_only",
                "qualifies_k04": str(global_id in qualifying),
            }
        )
        for member in ordered:
            item = items[member]
            crosswalk.append(
                {
                    "global_innovation_id": global_id,
                    "source": item.source,
                    "local_innovation_id": item.local_innovation_id,
                    "local_display_name": item.display_name,
                    "local_identity_status": item.identity_status,
                    "source_ids_json": canonical_json(sorted(item.source_ids)),
                }
            )
    return globals_, crosswalk, qualifying


def _unresolved(
    mapping: dict[str, str],
    unresolved_pairs: set[frozenset[str]],
    cannot_pairs: set[frozenset[str]],
    qualifying: set[str],
    boundary: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    active_edges = {
        frozenset(mapping[x] for x in pair)
        for pair in unresolved_pairs
        if len({mapping[x] for x in pair}) == 2
    }
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in active_edges:
        left, right = tuple(edge)
        adjacency[left].add(right)
        adjacency[right].add(left)
    groups = []
    seen = set()
    for start in sorted(adjacency):
        if start in seen:
            continue
        stack = [start]
        members = set()
        while stack:
            node = stack.pop()
            if node in members:
                continue
            members.add(node)
            stack.extend(adjacency[node] - members)
        seen |= members
        groups.append(sorted(members))
    rows = []
    member_rows = []
    edge_rows = []
    cannot_global = {
        frozenset(mapping[x] for x in pair)
        for pair in cannot_pairs
        if len({mapping[x] for x in pair}) == 2
    }
    for members in groups:
        component_id = stable_id("unresolved_component", *members)
        scenario = Components(members, cannot_global)
        selected = set()
        for edge in sorted(
            (e for e in active_edges if e <= set(members)), key=lambda x: sorted(x)
        ):
            left, right = sorted(edge)
            outcome = scenario.merge(left, right)
            if outcome == "merged":
                selected.add(edge)
        roots = {scenario.find(x) for x in members}
        current_ready = sum(x in qualifying for x in members)
        hypothetical = len({scenario.find(x) for x in members if x in qualifying})
        rows.append(
            {
                "unresolved_component_id": component_id,
                "current_identity_count": len(members),
                "candidate_edge_count": sum(e <= set(members) for e in active_edges),
                "demonstrated_nonconflicting_identity_reduction": len(members)
                - len(roots),
                "current_k04_count": current_ready,
                "demonstrated_nonconflicting_k04_reduction": current_ready
                - hypothetical,
                "interpretation": "Deterministic compatible-edge scenario for review impact; not a verified lower count.",
            }
        )
        for member in members:
            member_rows.append(
                {
                    "unresolved_component_id": component_id,
                    "global_innovation_id": member,
                    "qualifies_k04": str(member in qualifying),
                    "demonstrated_scenario_group_id": stable_id(
                        "unresolved_scenario_group", component_id, scenario.find(member)
                    ),
                }
            )
        for evidence in boundary:
            local_pair = evidence["pair"]
            global_pair = frozenset(mapping[x] for x in local_pair)
            if len(global_pair) != 2 or not global_pair <= set(members):
                continue
            left_local, right_local = sorted(local_pair)
            left_global, right_global = mapping[left_local], mapping[right_local]
            chosen = global_pair in selected
            edge_rows.append(
                {
                    "unresolved_edge_id": stable_id(
                        "unresolved_edge",
                        component_id,
                        evidence["decision_id"],
                        left_local,
                        right_local,
                    ),
                    "unresolved_component_id": component_id,
                    "edge_role": evidence["boundary_kind"],
                    "left_global_innovation_id": left_global,
                    "right_global_innovation_id": right_global,
                    "left_local_member": left_local,
                    "right_local_member": right_local,
                    "decision_id": evidence["decision_id"],
                    "decision": evidence["decision"],
                    "origin": evidence["origin"],
                    "source_locator": evidence["source_locator"],
                    "evidence_json": evidence["evidence_json"]
                    if isinstance(evidence["evidence_json"], str)
                    else canonical_json(evidence["evidence_json"]),
                    "reason": evidence["reason"],
                    "demonstrated_scenario_action": "merged"
                    if chosen
                    else "not_applied_constraint",
                    "selected_in_demonstrated_scenario": str(chosen),
                }
            )
    return rows, member_rows, edge_rows


def build_tables(
    source_tables: dict[str, dict[str, list[dict]]],
    reviews: dict[str, Any],
    raw_inputs: dict[str, dict],
    geography: Any,
) -> dict[str, list[dict]]:
    """Build accepted identities from injected source tables and locked reviews only."""
    del geography  # Locations have already been normalized by their source owners.
    bundles = load_sources(source_tables, raw_inputs)
    items = _all_items(bundles)
    reviewed = _load_reviews(reviews, bundles)
    local_cannot = set().union(
        *(bundle.cannot_local_pairs for bundle in bundles.values())
    )
    local_unresolved = set().union(
        *(bundle.unresolved_local_pairs for bundle in bundles.values())
    )
    mapping, decisions, reviewed_cannot, reviewed_unresolved = _apply_reviews(
        items, reviewed, local_cannot | local_unresolved
    )
    boundary = _boundary_rows(reviewed, bundles)
    # A confirmed global separation supersedes a weaker unresolved edge.
    separations = {
        frozenset(mapping[x] for x in row["pair"])
        for row in boundary
        if row["boundary_kind"] == "cannot_link_constraint"
    }
    active_unresolved = {
        pair
        for pair in local_unresolved | reviewed_unresolved
        if frozenset(mapping[x] for x in pair) not in separations
    }
    supersessions = []
    for row in boundary:
        if (
            row["boundary_kind"] != "unresolved_candidate"
            or row["pair"] in active_unresolved
        ):
            continue
        left, right = sorted(row["pair"])
        supersessions.append(
            {
                "superseded_review_id": row["decision_id"],
                "left_local_member": left,
                "right_local_member": right,
                "left_global_innovation_id": mapping[left],
                "right_global_innovation_id": mapping[right],
                "superseding_review_ids_json": canonical_json(
                    sorted(
                        r["decision_id"]
                        for r in boundary
                        if r["boundary_kind"] == "cannot_link_constraint"
                        and frozenset(mapping[x] for x in r["pair"])
                        == frozenset((mapping[left], mapping[right]))
                    )
                ),
                "source_locator": row["source_locator"],
                "reason": "A confirmed separation between these global identities supersedes this unresolved edge; the original review remains traceable.",
            }
        )
    all_readiness = [row for bundle in bundles.values() for row in bundle.readiness]
    globals_, crosswalk, qualifying = _globals(
        items, mapping, all_readiness, active_unresolved
    )
    records = []
    readiness = []
    locations = []
    for bundle in bundles.values():
        for source_rows, target in (
            (bundle.source_records, records),
            (bundle.readiness, readiness),
            (bundle.use_locations, locations),
        ):
            for row in source_rows:
                target.append(
                    {
                        "global_innovation_id": mapping[
                            f"{row['source']}:{row['local_innovation_id']}"
                        ],
                        **row,
                    }
                )
    status_by_global = {
        row["global_innovation_id"]: row["identity_status"] for row in globals_
    }
    qualifying_assessments = defaultdict(list)
    for row in readiness:
        if row["qualifies_k04"] == "True":
            qualifying_assessments[row["global_innovation_id"]].append(
                row["assessment_id"]
            )
    contributions = []
    for row in globals_:
        global_id = row["global_innovation_id"]
        status = (
            "provisional_unresolved_identity"
            if row["identity_status"] == "provisional_unresolved_candidates"
            else "reviewed_identity"
        )
        contributions.append(
            {
                "measure": "C04_LISTED",
                "global_innovation_id": global_id,
                "contribution": 1,
                "status": status,
                "qualifying_assessment_ids_json": "[]",
            }
        )
        if global_id in qualifying:
            contributions.append(
                {
                    "measure": "K04",
                    "global_innovation_id": global_id,
                    "contribution": 1,
                    "status": status,
                    "qualifying_assessment_ids_json": canonical_json(
                        sorted(qualifying_assessments[global_id])
                    ),
                }
            )
    by_province = defaultdict(list)
    for row in locations:
        if row.get("province_code"):
            by_province[row["global_innovation_id"], str(row["province_code"])].append(
                row
            )
    province_contributions = []
    for (global_id, code), rows in sorted(by_province.items()):
        if global_id not in qualifying:
            continue
        name = next(
            (
                str(row.get("province_normalized"))
                for row in rows
                if row.get("province_normalized")
            ),
            "",
        )
        province_contributions.append(
            {
                "measure": "K04",
                "province_code": code,
                "province_name": name,
                "global_innovation_id": global_id,
                "contribution": 1,
                "identity_status": status_by_global[global_id],
                "status": "provisional_unresolved_identity"
                if status_by_global[global_id] == "provisional_unresolved_candidates"
                else "reviewed_identity",
                "qualifying_assessment_ids_json": canonical_json(
                    sorted(qualifying_assessments[global_id])
                ),
                "use_location_ids_json": canonical_json(
                    sorted(str(row["location_id"]) for row in rows)
                ),
                "evidence_context_note": "Readiness and supported innovation-use location are separate assertions joined only through the reviewed global identity.",
            }
        )
    counts = Counter(row["province_code"] for row in province_contributions)
    names = {
        row["province_code"]: row["province_name"] for row in province_contributions
    }
    province_results = [
        {
            "measure": "K04",
            "province_code": code,
            "province_name": names[code],
            "value": counts[code],
            "unit": "distinct_global_innovations",
            "status": "provisional_cross_source",
        }
        for code in sorted(counts)
    ]
    results = [
        {
            "measure": "C04_LISTED",
            "value": len(globals_),
            "unit": "distinct_global_innovations",
            "status": "provisional_cross_source",
            "definition": "All source-local listed innovations after reviewed cross-source unions.",
        },
        {
            "measure": "K04",
            "value": len(qualifying),
            "unit": "distinct_global_innovations",
            "status": "provisional_cross_source",
            "definition": "Distinct global innovations with at least one eligible qualifying readiness assessment.",
        },
    ]
    unresolved, unresolved_members, unresolved_edges = _unresolved(
        mapping,
        active_unresolved,
        local_cannot | reviewed_cannot,
        qualifying,
        [
            row
            for row in boundary
            if row["boundary_kind"] == "cannot_link_constraint"
            or row["pair"] in active_unresolved
        ],
    )
    source_files = []
    for source, bundle in bundles.items():
        raw_input = raw_inputs[bundle.canonical_source_id]
        runs = {
            str(item.get("run_id", ""))
            for item in raw_input.get("metadata", {}).values()
            if isinstance(item, dict) and item.get("run_id")
        }
        if len(runs) != 1:
            raise PipelineError(
                f"Raw input {bundle.canonical_source_id} lacks one run identity"
            )
        run_id = next(iter(runs))
        for item in raw_input.get("files", []):
            if isinstance(item, dict) and item.get("path") and item.get("sha256"):
                source_files.append(
                    {
                        "path": f"evidence://{bundle.canonical_source_id}/{run_id}/{item['path']}",
                        "sha256": item["sha256"],
                        "size_bytes": item.get("size", ""),
                        "role": f"{source}_source_input",
                    }
                )
    output = {name: [] for name in TABLE_COLUMNS}
    output.update(
        {
            "global_innovations": globals_,
            "innovation_crosswalk": crosswalk,
            "source_records": records,
            "identity_decisions": decisions,
            "readiness_evidence": readiness,
            "innovation_use_locations": locations,
            "measure_results": results,
            "measure_contributions": contributions,
            "province_k04_contributions": province_contributions,
            "province_k04_results": province_results,
            "unresolved_components": unresolved,
            "unresolved_component_members": unresolved_members,
            "unresolved_component_edges": unresolved_edges,
            "review_supersessions": supersessions,
            "source_files": source_files,
        }
    )
    return {
        name: sorted(
            (
                {column: row.get(column, "") for column in TABLE_COLUMNS[name]}
                for row in rows
            ),
            key=canonical_json,
        )
        for name, rows in output.items()
    }
