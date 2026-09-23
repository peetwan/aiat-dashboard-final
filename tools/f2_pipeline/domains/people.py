"""Pure reviewed cross-source people registry and private companion evidence."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from ..common import Components, PipelineError, canonical_json, stable_id
from .person_sources import (
    SOURCE_ORDER as PERSON_SOURCE_ORDER,
    PersonSources,
    load_person_sources,
)
from .resolution import (
    EvidenceLocatorIndex,
    SOURCE_ALIASES,
    json_list,
    logical_source,
    review_payload,
    source_tables_for,
    truth,
)

PERSON_MEASURES = {
    "C02_COMMUNITY": {
        "community_innovator",
        "inventor",
    },
}

TABLE_COLUMNS = {
    "global_people": (
        "global_person_id",
        "display_name",
        "aliases_json",
        "source_count",
        "source_entity_count",
        "roles_json",
        "eligible_roles_json",
        "natural_person_statuses_json",
        "identity_status",
        "community_innovator_eligible",
        "cultural_entrepreneur_eligible",
    ),
    "person_crosswalk": (
        "global_person_id",
        "source_entity_id",
        "source",
        "source_local_id",
        "entity_kind",
        "identity_basis",
        "display_name",
        "source_ids_json",
        "observation_ids_json",
        "identity_status",
        "natural_person_status",
        "quality_flags_json",
    ),
    "person_assertions": (
        "assertion_id",
        "assertion_kind",
        "global_person_id",
        "attached_global_person_ids_json",
        "identity_treatment",
        "source_entity_id",
        "source",
        "source_local_id",
        "source_record_id",
        "observation_id",
        "source_key",
        "raw_name",
        "matching_name",
        "role",
        "eligible_roles_json",
        "institution_raw",
        "institution_role",
        "local_innovation_id",
        "global_innovation_id",
        "relationship_id",
        "source_locator",
        "evidence_text",
        "natural_person_status",
        "quality_flags_json",
        "context_json",
    ),
    "person_location_admission": (
        "location_admission_id",
        "source",
        "source_entity_id",
        "global_person_id",
        "source_location_id",
        "source_observation_id",
        "source_location_role",
        "province_code",
        "province_name_th",
        "source_resolution_status",
        "decision",
        "reason",
    ),
    "person_location_assertions": (
        "location_assertion_id",
        "global_person_id",
        "province_code",
        "province_name_th",
        "location_role",
        "source",
        "source_entity_ids_json",
        "source_location_ids_json",
        "source_observation_ids_json",
        "evidence_basis",
        "province_resolution_status",
        "review_status",
    ),
    "admission": (
        "admission_id",
        "source",
        "source_record_id",
        "observation_id",
        "assertion_id",
        "source_entity_id",
        "decision",
        "subject_kind",
        "reason",
        "source_locator",
        "global_person_id",
        "quality_flags_json",
        "context_json",
    ),
    "candidate_pairs": (
        "candidate_id",
        "left_anchor_id",
        "right_anchor_id",
        "left_names_json",
        "right_names_json",
        "decision",
        "review_status",
        "audit_source_correction_flag",
        "requires_current_source_correction",
        "shared_institutions_json",
        "shared_work_ids_json",
        "shared_pages_json",
        "reason",
        "origin",
    ),
    "identity_decisions": (
        "candidate_id",
        "review_decision",
        "effective_decision",
        "edge_basis",
        "left_current_entity_ids_json",
        "right_current_entity_ids_json",
        "left_current_assertion_ids_json",
        "right_current_assertion_ids_json",
        "applied_edges_json",
        "left_remap_method",
        "right_remap_method",
        "reason",
        "origin",
    ),
    "relationships": (
        "relationship_row_id",
        "global_person_id",
        "source_entity_id",
        "assertion_id",
        "source",
        "role",
        "relationship_id",
        "local_innovation_id",
        "global_innovation_id",
        "source_locator",
    ),
    "unresolved_components": (
        "unresolved_component_id",
        "member_count",
        "candidate_ids_json",
        "treatment",
    ),
    "unresolved_component_members": (
        "unresolved_component_id",
        "source_entity_id",
        "global_person_id",
    ),
    "unresolved_component_edges": (
        "candidate_id",
        "constraint_type",
        "left_source_entity_id",
        "right_source_entity_id",
        "reason",
    ),
    "source_uncertainties": (
        "uncertainty_group_id",
        "uncertainty_type",
        "assertion_id",
        "source_entity_id",
        "global_person_id",
        "raw_name",
        "source_locator",
        "context_json",
        "treatment",
    ),
    "assessment_observations": (
        "assessment_id",
        "global_person_id",
        "source_entity_id",
        "person_id",
        "observation_id",
        "project_id",
    ),
    "development_assessments": (
        "assessment_id",
        "global_person_id",
        "source_entity_id",
        "person_id",
        "any_increase",
        "mixed_change",
        "assessment_period",
        "complete",
    ),
    "development_scores": (
        "assessment_id",
        "global_person_id",
        "source_entity_id",
        "person_id",
        "dimension",
        "start_score",
        "current_score",
        "delta",
    ),
    "assessment_admission": (
        "assessment_id",
        "global_person_id",
        "source_entity_id",
        "decision",
        "reason",
    ),
    "measure_contributions": (
        "contribution_id",
        "measure_id",
        "global_person_id",
        "contribution_value",
        "basis",
        "qualifying_assertion_ids_json",
    ),
    "measure_results": (
        "measure_id",
        "value",
        "unit",
        "result_type",
        "coverage",
        "source_reference",
    ),
    "source_files": ("path", "sha256", "size_bytes"),
}


@dataclass(frozen=True)
class EndpointResolution:
    entity_ids: tuple[str, ...]
    assertion_ids: tuple[str, ...]
    evidence_only_assertion_ids: tuple[str, ...]
    method: str


def _normalized_name(value: Any) -> str:
    return " ".join(str(value).casefold().replace(".", " ").split())


def _institution_key(value: Any) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    text = text.replace("มหาวิทยาลัยเทคโนโลยีราชมงคล", "มทร.")
    text = text.replace("มหาวิทยาลัยราชภัฎ", "มรภ.").replace("มหาวิทยาลัยราชภัฏ", "มรภ.")
    text = (
        text.replace("ในพระบรมราชูปถัมภ์", "")
        .replace("ฯ", "")
        .replace("เจ้าคุณหทาร", "เจ้าคุณทหาร")
    )
    text = text.split("วิทยาเขต")[0]
    aliases = {
        "ม.ราชภัฏนครศรีธรรมราช": "มรภ.นครศรีธรรมราช",
        "มรภเลย": "มรภ.เลย",
        "ราชภัฏกำแพงเพชร": "มรภ.กำแพงเพชร",
        "มนร.": "มหาวิทยาลัยนราธิวาสราชนครินทร์",
        "มจธ.": "มหาวิทยาลัยเทคโนโลยีพระจอมเกล้าธนบุรี",
        "มหาวิทยาัยราชภัฏนครศรีธรรมราช": "มรภ.นครศรีธรรมราช",
        "มหาวิทยาลราชภัฏบ้านสมเด็จเจ้าพระยา": "มรภ.บ้านสมเด็จเจ้าพระยา",
        "มหาวิทาลัยราชภัฏบ้านสมเด็จเจ้าพระยา": "มรภ.บ้านสมเด็จเจ้าพระยา",
        "เทคโนโลยีราชมงคลศรีวิชัย": "มทร.ศรีวิชัย",
        "ม.ฟ.น.": "มหาวิทยาลัยฟาฏอนี",
    }
    text = aliases.get(text, text)
    return (
        text
        if any(
            marker in text
            for marker in (
                "มหาวิทยาลัย",
                "มทร.",
                "มรภ.",
                "สถาบัน",
                "กรม",
                "สำนักงาน",
                "วิทยาลัย",
                "ศูนย์เรียนรู้",
                "ห้างหุ้นส่วน",
                "วิสาหกิจ",
            )
        )
        else ""
    )


def _validate_runtime_pins(
    runtime: dict[str, Any],
    reviews: dict[str, Any],
    raw_inputs: dict[str, dict],
    source_tables: dict[str, dict[str, list[dict]]],
    innovation_tables: dict[str, list[dict]],
) -> list[dict]:
    if runtime.get("schema_version") != 1 or not isinstance(
        runtime.get("source_input_pins"), list
    ):
        raise PipelineError("People runtime review has unsupported schema")
    evidence: dict[str, set[str]] = defaultdict(set)
    source_files: list[dict] = []
    for canonical_source_id in (
        SOURCE_ALIASES[source][-1] for source in PERSON_SOURCE_ORDER
    ):
        raw_input = raw_inputs.get(canonical_source_id)
        if not isinstance(raw_input, dict):
            raise PipelineError(f"Missing people raw input {canonical_source_id}")
        metadata = raw_input.get("metadata", {})
        runs = {
            str(item.get("run_id", ""))
            for item in metadata.values()
            if isinstance(item, dict) and item.get("run_id")
        }
        if len(runs) != 1:
            raise PipelineError(
                f"Raw input {canonical_source_id} lacks one run identity"
            )
        run_id = next(iter(runs))
        dataset_hashes: dict[str, set[str]] = defaultdict(set)
        for dataset, item in metadata.items():
            if isinstance(item, dict) and item.get("sha256"):
                dataset_hashes[str(dataset)].add(str(item["sha256"]))
        for item in raw_input.get("files", []):
            if (
                not isinstance(item, dict)
                or not item.get("path")
                or not item.get("sha256")
            ):
                continue
            path = f"evidence://{canonical_source_id}/{run_id}/{item['path']}"
            hashes = {str(item["sha256"])} | dataset_hashes.get(
                str(item.get("dataset_key", "")), set()
            )
            evidence[path].update(hashes)
            source_files.append(
                {
                    "path": path,
                    "sha256": item["sha256"],
                    "size_bytes": item.get("size", ""),
                }
            )
        for dataset, item in metadata.items():
            if (
                not isinstance(item, dict)
                or not item.get("file")
                or not item.get("sha256")
            ):
                continue
            path = f"evidence://{canonical_source_id}/{run_id}/{item['file']}"
            evidence[path].add(str(item["sha256"]))
            if not any(row["path"] == path for row in source_files):
                source_files.append(
                    {
                        "path": path,
                        "sha256": item["sha256"],
                        "size_bytes": item.get("size", ""),
                    }
                )
    for pin in runtime["source_input_pins"]:
        path, expected = str(pin.get("path", "")), str(pin.get("sha256", ""))
        if path.startswith("evidence://"):
            if expected not in evidence.get(path, set()):
                raise PipelineError(f"Stale people source pin: {path}")
        elif path.startswith("review-config://"):
            review_payload(reviews, path.removeprefix("review-config://"))
        elif path.startswith("normalized://cross_source/innovations-v1/"):
            table = path.rsplit("/", 1)[-1].removesuffix(".csv")
            if table not in innovation_tables or not isinstance(
                innovation_tables[table], list
            ):
                raise PipelineError(f"Missing normalized producer endpoint: {path}")
        elif path.startswith("normalized://source_local/"):
            parts = path.removeprefix("normalized://source_local/").split("/")
            if (
                len(parts) != 2
                or not parts[0].endswith("-v1")
                or not parts[1].endswith(".csv")
            ):
                raise PipelineError(f"Malformed normalized source endpoint: {path}")
            source = logical_source(parts[0].removesuffix("-v1"))
            _, tables = source_tables_for(source_tables, source)
            table_name = parts[1].removesuffix(".csv")
            if table_name not in tables or not isinstance(tables[table_name], list):
                raise PipelineError(f"Missing normalized producer endpoint: {path}")
        elif path.startswith("normalized://"):
            raise PipelineError(f"Unsupported normalized producer endpoint: {path}")
        else:
            raise PipelineError(f"People runtime contains non-immutable pin: {path}")
    return sorted(source_files, key=lambda row: row["path"])


def _load_reviews(
    reviews: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runtime = review_payload(reviews, "cross_source_people/runtime.json")
    catalog = review_payload(
        reviews, "cross_source_people/reviews/anchor_evidence.json"
    )
    if not isinstance(runtime, dict) or not isinstance(catalog, dict):
        raise PipelineError("Invalid people review runtime or anchor catalogue")
    anchors = {
        row["anchor_id"]: row
        for row in catalog.get("anchors", [])
        if isinstance(row, dict) and row.get("anchor_id")
    }
    assertions = {
        row["assertion_id"]: row
        for row in catalog.get("assertions", [])
        if isinstance(row, dict) and row.get("assertion_id")
    }
    result = []
    seen = set()
    for item in runtime.get("review_files", []):
        path = str(item.get("path", "")).removeprefix("review-config://")
        payload = review_payload(reviews, path)
        if not isinstance(payload, list):
            raise PipelineError(f"People review {path} must contain a list")
        for row in payload:
            if (
                not isinstance(row, dict)
                or not row.get("candidate_id")
                or row["candidate_id"] in seen
            ):
                raise PipelineError("Missing or duplicate people candidate_id")
            seen.add(row["candidate_id"])
            if row.get("decision") not in {"match", "keep_separate", "unresolved"}:
                raise PipelineError(
                    f"Unsupported people decision {row.get('decision')!r}"
                )
            try:
                left = dict(anchors[row["left_anchor_id"]])
                right = dict(anchors[row["right_anchor_id"]])
            except KeyError as exc:
                raise PipelineError(
                    f"Stale people review anchor: {exc.args[0]}"
                ) from exc
            try:
                left["assertions"] = [
                    assertions[value] for value in row.get("left_assertion_ids", [])
                ]
                right["assertions"] = [
                    assertions[value] for value in row.get("right_assertion_ids", [])
                ]
            except KeyError as exc:
                raise PipelineError(
                    f"Stale people review assertion: {exc.args[0]}"
                ) from exc
            result.append(
                {**row, "review_status": "reviewed", "left": left, "right": right}
            )
    return sorted(result, key=lambda row: row["candidate_id"]), runtime


def _indexes(bundle: PersonSources) -> dict[str, Any]:
    assertions = {row["assertion_id"]: row for row in bundle.assertions}
    if len(assertions) != len(bundle.assertions):
        raise PipelineError("Duplicate current person assertion IDs")
    source_ids = defaultdict(set)
    locals_ = defaultdict(set)
    observations = defaultdict(set)
    locator_index = EvidenceLocatorIndex()
    for assertion in bundle.assertions:
        locator = assertion.get("source_locator", "")
        if locator:
            locator_index.add(locator, assertion)
    for entity_id, entity in bundle.entities.items():
        locals_[entity["source"], str(entity["source_local_id"])].add(entity_id)
        for value in entity.get("source_ids", []):
            source_ids[entity["source"], str(value)].add(entity_id)
        for value in entity.get("observation_ids", []):
            observations[entity["source"], str(value)].add(entity_id)
    return {
        "assertions": assertions,
        "locator_index": locator_index,
        "source_ids": source_ids,
        "local_ids": locals_,
        "observations": observations,
    }


def _resolve_endpoint(
    endpoint: dict[str, Any], bundle: PersonSources, indexes: dict[str, Any]
) -> EndpointResolution:
    source = logical_source(str(endpoint.get("source", "")))
    entities = set()
    assertion_ids = set()
    evidence_only = set()
    methods = set()
    local_id = str(endpoint.get("source_local_id", ""))
    exact = indexes["local_ids"].get((source, local_id), set()) if local_id else set()
    if exact:
        entities |= exact
        methods.add("source_local_id")
    names = {
        _normalized_name(name)
        for name in [*endpoint.get("names", []), *endpoint.get("matching_names", [])]
        if name
    }

    def name_matches(entity_id):
        entity = bundle.entities[entity_id]
        current = {
            _normalized_name(value)
            for value in [
                entity.get("display_name", ""),
                *entity.get("matching_names", []),
                *entity.get("aliases", []),
            ]
            if value
        }
        return bool(names & current) if names else True

    if not exact:
        sid = set()
        obs = set()
        for value in endpoint.get("source_ids", []):
            sid |= indexes["source_ids"].get((source, str(value)), set())
        for value in endpoint.get("observation_ids", []):
            obs |= indexes["observations"].get((source, str(value)), set())
        lineage = (sid & obs or sid | obs) if sid and obs else sid | obs
        lineage = {value for value in lineage if name_matches(value)}
        if lineage:
            entities |= lineage
            methods.add("reviewed_name_and_source_lineage")
    for frozen in endpoint.get("assertions", []):
        locator = str(frozen.get("locator", ""))
        hits = [
            row
            for row in indexes["locator_index"].related(locator)
            if row.get("source") == source
        ]
        if names:
            hits = [
                row
                for row in hits
                if _normalized_name(row.get("raw_name", "")) in names
                or _normalized_name(row.get("matching_name", "")) in names
                or (
                    row.get("assertion_kind") == "evidence_only"
                    and any(
                        name and name in _normalized_name(row.get("raw_name", ""))
                        for name in names
                    )
                )
                or (
                    any(
                        _normalized_name(row.get("matching_name", "")).startswith(
                            name + " "
                        )
                        for name in names
                        if name
                    )
                    and _normalized_name(frozen.get("name_raw", ""))
                    in _normalized_name(row.get("raw_name", ""))
                )
            ]
        for row in hits:
            assertion_ids.add(row["assertion_id"])
            if row.get("source_entity_id"):
                entities.add(row["source_entity_id"])
            else:
                evidence_only.add(row["assertion_id"])
        if hits:
            methods.add("raw_locator")
    return EndpointResolution(
        tuple(sorted(entities)),
        tuple(sorted(assertion_ids)),
        tuple(sorted(evidence_only)),
        "+".join(sorted(methods)) or "unmapped",
    )


def _assertion_has_gate(assertion: dict[str, Any], review: dict[str, Any]) -> bool:
    work = set(review.get("shared_work_ids", []))
    institutions = {
        _institution_key(value) for value in review.get("shared_institutions", [])
    }
    pages = set(review.get("shared_pages", []))
    if work and assertion.get("global_innovation_id") in work:
        return True
    if institutions & {
        _institution_key(assertion.get("institution_raw", "")),
        _institution_key(assertion.get("context", {}).get("institution_key", "")),
    }:
        return True
    locator = assertion.get("source_locator", "")
    if pages and any(page and page in locator for page in pages):
        return True
    return not (work or institutions or pages)


def _gated(
    resolution: EndpointResolution, review: dict[str, Any], indexes: dict[str, Any]
) -> tuple[str, ...]:
    assertion_entities = {
        indexes["assertions"][aid].get("source_entity_id", "")
        for aid in resolution.assertion_ids
        if _assertion_has_gate(indexes["assertions"][aid], review)
    } - {""}
    if assertion_entities:
        return tuple(sorted(set(resolution.entity_ids) & assertion_entities))
    if (
        review.get("shared_work_ids")
        or review.get("shared_institutions")
        or review.get("shared_pages")
    ):
        return ()
    return resolution.entity_ids if len(resolution.entity_ids) == 1 else ()


def _pair_edges(
    left: tuple[str, ...], right: tuple[str, ...], bundle: PersonSources
) -> tuple[list[tuple[str, str]], str]:
    if not left or not right:
        return [], "endpoint_without_person_entity"
    if len(left) == 1:
        return [
            (left[0], value) for value in right if value != left[0]
        ], "reviewed_star_edge"
    if len(right) == 1:
        return [
            (value, right[0]) for value in left if value != right[0]
        ], "reviewed_star_edge"
    edges = []
    for left_id in left:
        for right_id in right:
            if set(bundle.entities[left_id].get("observation_ids", [])) & set(
                bundle.entities[right_id].get("observation_ids", [])
            ):
                edges.append((left_id, right_id))
    return (
        (sorted(set(edges)), "reviewed_shared_observation_edges")
        if edges
        else ([], "ambiguous_multi_entity_endpoint")
    )


def _global_person_id(members: list[str]) -> str:
    value = "\x1f".join(members)
    return f"global_person_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


def _registry(
    bundle: PersonSources, components: Components, attachments: set[str]
) -> tuple[list[dict], list[dict], dict[str, str]]:
    groups = defaultdict(list)
    for member in components.parent:
        groups[components.find(member)].append(member)
    assertions_by_entity = defaultdict(list)
    for assertion in bundle.assertions:
        if assertion.get("source_entity_id"):
            assertions_by_entity[assertion["source_entity_id"]].append(assertion)
    people = []
    crosswalk = []
    entity_to_global = {}
    for members in sorted((sorted(value) for value in groups.values())):
        entities = [bundle.entities[value] for value in members]
        global_id = _global_person_id(members)
        aliases = sorted(
            {
                value
                for entity in entities
                for value in [
                    entity.get("display_name", ""),
                    *entity.get("aliases", []),
                ]
                if value
            }
        )
        eligible = sorted(
            {
                role
                for member in members
                for row in assertions_by_entity[member]
                if row["assertion_id"] not in attachments
                for role in row.get("eligible_roles", [])
            }
        )
        roles = sorted(
            {
                row.get("role", "")
                for member in members
                for row in assertions_by_entity[member]
                if row.get("role") and row["assertion_id"] not in attachments
            }
        )
        statuses = sorted(
            {entity.get("natural_person_status", "") for entity in entities}
        )
        display = sorted(
            (
                entity.get("display_name", "")
                for entity in entities
                if entity.get("display_name")
            ),
            key=lambda value: (-len(value), value.casefold()),
        )
        people.append(
            {
                "global_person_id": global_id,
                "display_name": display[0] if display else "",
                "aliases_json": canonical_json(aliases),
                "source_count": len({entity["source"] for entity in entities}),
                "source_entity_count": len(members),
                "roles_json": canonical_json(roles),
                "eligible_roles_json": canonical_json(eligible),
                "natural_person_statuses_json": canonical_json(statuses),
                "identity_status": "reviewed_cross_source"
                if len({entity["source"] for entity in entities}) > 1
                else "source_supported",
                "community_innovator_eligible": str(
                    bool(set(eligible) & PERSON_MEASURES["C02_COMMUNITY"])
                ),
                "cultural_entrepreneur_eligible": str(
                    "cultural_entrepreneur" in eligible
                ),
            }
        )
        for member, entity in zip(members, entities):
            entity_to_global[member] = global_id
            crosswalk.append(
                {
                    "global_person_id": global_id,
                    "source_entity_id": member,
                    "source": entity["source"],
                    "source_local_id": entity["source_local_id"],
                    "entity_kind": entity["entity_kind"],
                    "identity_basis": entity["identity_basis"],
                    "display_name": entity["display_name"],
                    "source_ids_json": canonical_json(
                        sorted(entity.get("source_ids", []))
                    ),
                    "observation_ids_json": canonical_json(
                        sorted(entity.get("observation_ids", []))
                    ),
                    "identity_status": entity["identity_status"],
                    "natural_person_status": entity["natural_person_status"],
                    "quality_flags_json": canonical_json(
                        sorted(entity.get("quality_flags", []))
                    ),
                }
            )
    return people, crosswalk, entity_to_global


def _assessment_tables(
    source_tables: dict[str, dict[str, list[dict]]], entity_to_global: dict[str, str]
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    _, tables = source_tables_for(source_tables, "icommunity")
    required = (
        "assessment_observations",
        "development_assessments",
        "development_scores",
    )
    if any(name not in tables for name in required):
        raise PipelineError(
            "iCommunity assessment tables are required for paired assessment admission"
        )
    observations = defaultdict(list)
    scores = defaultdict(list)
    for row in tables["assessment_observations"]:
        observations[str(row.get("assessment_id", ""))].append(row)
    for row in tables["development_scores"]:
        scores[str(row.get("assessment_id", ""))].append(row)
    assessment_rows = []
    score_rows = []
    observation_rows = []
    admission = []
    seen = set()
    for row in tables["development_assessments"]:
        assessment_id = str(row.get("assessment_id", ""))
        person_id = str(row.get("person_id", ""))
        entity_id = f"icommunity:{person_id}"
        if (
            not assessment_id
            or assessment_id in seen
            or entity_id not in entity_to_global
        ):
            raise PipelineError("Stale or duplicate iCommunity development assessment")
        seen.add(assessment_id)
        current_scores = scores.get(assessment_id, [])
        current_observations = observations.get(assessment_id, [])
        score_people = {str(value.get("person_id", "")) for value in current_scores}
        observation_people = {
            str(value.get("person_id", "")) for value in current_observations
        }
        paired = (
            bool(current_scores and current_observations)
            and score_people == {person_id}
            and observation_people == {person_id}
        )
        dimensions = [str(value.get("dimension", "")) for value in current_scores]
        complete = (
            truth(row.get("complete"))
            and paired
            and len(dimensions) == len(set(dimensions)) == 3
            and all(dimensions)
        )
        for value in current_scores:
            try:
                start = float(value["start_score"])
                current = float(value["current_score"])
                delta = float(value["delta"])
            except (KeyError, TypeError, ValueError):
                complete = False
                continue
            if abs((current - start) - delta) > 1e-9:
                raise PipelineError(
                    f"Assessment {assessment_id} has an invalid paired delta"
                )
        global_id = entity_to_global[entity_id]
        materialized = {
            **row,
            "assessment_id": assessment_id,
            "person_id": person_id,
            "source_entity_id": entity_id,
            "global_person_id": global_id,
            "complete": str(complete),
            "any_increase": str(
                complete and any(float(value["delta"]) > 0 for value in current_scores)
            ),
            "mixed_change": str(
                complete
                and any(float(value["delta"]) > 0 for value in current_scores)
                and any(float(value["delta"]) < 0 for value in current_scores)
            ),
        }
        assessment_rows.append(materialized)
        for value in current_scores:
            score_rows.append(
                {**value, "source_entity_id": entity_id, "global_person_id": global_id}
            )
        for value in current_observations:
            observation_rows.append(
                {**value, "source_entity_id": entity_id, "global_person_id": global_id}
            )
        admission.append(
            {
                "assessment_id": assessment_id,
                "global_person_id": global_id,
                "source_entity_id": entity_id,
                "decision": "admit_complete_paired_assessment"
                if complete
                else "retain_incomplete_assessment_evidence",
                "reason": "Start/current scores remain paired within one source assessment context."
                if complete
                else "Missing, duplicate, cross-person, or incomplete score context is not admitted to person measures.",
            }
        )
    unknown = (set(scores) | set(observations)) - seen
    if unknown:
        raise PipelineError(
            f"Assessment evidence references unknown assessments: {sorted(unknown)[:3]}"
        )
    return observation_rows, assessment_rows, score_rows, admission


def _person_location_tables(
    source_tables: dict[str, dict[str, list[dict]]],
    entity_to_global: dict[str, str],
    geography: Any,
) -> tuple[list[dict], list[dict]]:
    """Review source-person locations into province-only global assertions."""
    source_id, tables = source_tables_for(source_tables, "icommunity")
    locations = tables.get("locations")
    if not isinstance(locations, list):
        raise PipelineError(
            "iCommunity locations are required for person province admission"
        )
    province_names = {
        str(row["provinceCode"]).zfill(2): str(row["provinceNameTh"])
        for row in geography.provinces
    }
    if len(province_names) != len(geography.provinces):
        raise PipelineError("Duplicate canonical province code in geography reference")

    admission = []
    accepted = defaultdict(
        lambda: {
            "source_entity_ids": set(),
            "source_location_ids": set(),
            "source_observation_ids": set(),
        }
    )
    seen_location_ids = set()
    for row in locations:
        if row.get("location_role") != "source_person_location":
            continue
        location_id = str(row.get("location_id", ""))
        observation_id = str(row.get("observation_id", ""))
        local_person_id = str(row.get("entity_id", ""))
        source_entity_id = f"icommunity:{local_person_id}" if local_person_id else ""
        global_person_id = entity_to_global.get(source_entity_id, "")
        province_code = str(row.get("province_code", "")).zfill(2)
        if not row.get("province_code"):
            province_code = ""
        source_status = str(row.get("status", ""))
        if not location_id or location_id in seen_location_ids or not observation_id:
            raise PipelineError(
                "Duplicate or incomplete iCommunity person location evidence"
            )
        seen_location_ids.add(location_id)

        if not global_person_id:
            decision = "exclude_missing_global_person"
            reason = (
                "The source-local person location has no reviewed global person mapping."
            )
        elif source_status == "source_geocode_conflict":
            decision = "exclude_source_geocode_conflict"
            reason = (
                "The source geocode conflicts with the source-reported named hierarchy."
            )
        elif province_code not in province_names:
            decision = "exclude_unknown_province"
            reason = (
                "The source-reported province does not resolve exactly to the pinned "
                "canonical province reference."
            )
        else:
            decision = "accept_exact_source_province"
            reason = (
                "The province name resolves exactly in the pinned canonical reference; "
                "lower-level hierarchy is not published or required."
            )
            key = (global_person_id, province_code)
            accepted[key]["source_entity_ids"].add(source_entity_id)
            accepted[key]["source_location_ids"].add(location_id)
            accepted[key]["source_observation_ids"].add(observation_id)

        admission.append(
            {
                "location_admission_id": stable_id(
                    "person_location_admission", source_id, location_id
                ),
                "source": source_id,
                "source_entity_id": source_entity_id,
                "global_person_id": global_person_id,
                "source_location_id": location_id,
                "source_observation_id": observation_id,
                "source_location_role": "source_person_location",
                "province_code": province_code
                if province_code in province_names
                else "",
                "province_name_th": province_names.get(province_code, ""),
                "source_resolution_status": source_status,
                "decision": decision,
                "reason": reason,
            }
        )

    assertions = []
    for (global_person_id, province_code), support in sorted(accepted.items()):
        assertions.append(
            {
                "location_assertion_id": stable_id(
                    "person_location_assertion", global_person_id, province_code
                ),
                "global_person_id": global_person_id,
                "province_code": province_code,
                "province_name_th": province_names[province_code],
                "location_role": "source_reported_innovator_location",
                "source": source_id,
                "source_entity_ids_json": canonical_json(
                    sorted(support["source_entity_ids"])
                ),
                "source_location_ids_json": canonical_json(
                    sorted(support["source_location_ids"])
                ),
                "source_observation_ids_json": canonical_json(
                    sorted(support["source_observation_ids"])
                ),
                "evidence_basis": "exact_source_province_name_lookup",
                "province_resolution_status": "exact_source_province",
                "review_status": "accepted",
            }
        )

    accepted_location_ids = {
        location_id
        for row in assertions
        for location_id in json_list(row["source_location_ids_json"])
    }
    admission_by_location = {
        row["source_location_id"]: row for row in admission
    }
    if len(admission_by_location) != len(admission) or accepted_location_ids != {
        location_id
        for location_id, row in admission_by_location.items()
        if row["decision"] == "accept_exact_source_province"
    }:
        raise PipelineError("Person province admission/assertion reconciliation failed")
    return admission, assertions


def build_tables(
    source_tables: dict[str, dict[str, list[dict]]],
    reviews: dict[str, Any],
    raw_inputs: dict[str, dict],
    geography: Any,
    innovation_tables: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """Build reviewed people, role and paired-assessment evidence without discovery."""
    bundle = load_person_sources(source_tables, reviews, raw_inputs, innovation_tables)
    reviewed, runtime = _load_reviews(reviews)
    source_files = _validate_runtime_pins(
        runtime, reviews, raw_inputs, source_tables, innovation_tables
    )
    indexes = _indexes(bundle)
    valid_work = {
        row["global_innovation_id"]
        for row in innovation_tables.get("global_innovations", [])
    }
    for review in reviewed:
        if not set(review.get("shared_work_ids", [])) <= valid_work:
            raise PipelineError(
                f"People review {review['candidate_id']} has stale normalized innovation context"
            )
    resolutions = {
        row["candidate_id"]: (
            _resolve_endpoint(row["left"], bundle, indexes),
            _resolve_endpoint(row["right"], bundle, indexes),
        )
        for row in reviewed
    }
    protected = set()
    for review in reviewed:
        if review["decision"] == "match":
            continue
        left, right = resolutions[review["candidate_id"]]
        protected |= {
            frozenset((a, b))
            for a in left.entity_ids
            for b in right.entity_ids
            if a != b
        }
    components = Components(bundle.entities, protected)
    decision_rows = []
    candidate_rows = []
    attachments = defaultdict(set)
    for review in reviewed:
        left, right = resolutions[review["candidate_id"]]
        effective = "conservative_non_match"
        basis = "reviewed_non_match"
        applied = []
        if review["decision"] == "match":
            left_gated, right_gated = (
                _gated(left, review, indexes),
                _gated(right, review, indexes),
            )
            left_evidence = tuple(
                aid
                for aid in left.evidence_only_assertion_ids
                if _assertion_has_gate(indexes["assertions"][aid], review)
            )
            right_evidence = tuple(
                aid
                for aid in right.evidence_only_assertion_ids
                if _assertion_has_gate(indexes["assertions"][aid], review)
            )
            same = logical_source(review["left"]["source"]) == logical_source(
                review["right"]["source"]
            )
            left_mention = "mention" in review["left"].get("kind", "")
            right_mention = "mention" in review["right"].get("kind", "")
            if (
                same
                and left_mention
                and review["right"].get("kind") == "source_local_person"
                and len(right_gated) == 1
                and left_gated
            ):
                for aid in left.assertion_ids:
                    attachments[right_gated[0]].add(aid)
                for entity in left_gated:
                    if (
                        components.merge(entity, right_gated[0])
                        == "blocked_cannot_link"
                    ):
                        raise PipelineError("Protected people boundary collapsed")
                effective, basis = (
                    "supported_evidence_attachment",
                    "reviewed_same_source_mention_reference",
                )
            elif (
                same
                and right_mention
                and review["left"].get("kind") == "source_local_person"
                and len(left_gated) == 1
                and right_gated
            ):
                for aid in right.assertion_ids:
                    attachments[left_gated[0]].add(aid)
                for entity in right_gated:
                    if components.merge(entity, left_gated[0]) == "blocked_cannot_link":
                        raise PipelineError("Protected people boundary collapsed")
                effective, basis = (
                    "supported_evidence_attachment",
                    "reviewed_same_source_mention_reference",
                )
            elif left_evidence and len(right_gated) == 1:
                for aid in left_evidence:
                    attachments[right_gated[0]].add(aid)
                effective, basis = (
                    "supported_evidence_attachment",
                    "reviewed_mixed_text_reference",
                )
            elif right_evidence and len(left_gated) == 1:
                for aid in right_evidence:
                    attachments[left_gated[0]].add(aid)
                effective, basis = (
                    "supported_evidence_attachment",
                    "reviewed_mixed_text_reference",
                )
            else:
                edges, basis = _pair_edges(left_gated, right_gated, bundle)
                if not edges and set(left_gated) & set(right_gated):
                    effective = "already_resolved_in_current_source"
                elif edges:
                    source_correction = (
                        review.get("source_correction_required", False)
                        and review["left"].get("kind") == "source_local_person"
                        and review["right"].get("kind") == "source_local_person"
                    )
                    if source_correction and any(
                        bundle.entities[a]["source"] == bundle.entities[b]["source"]
                        for a, b in edges
                    ):
                        effective = "source_correction_not_applied"
                    else:
                        for a, b in edges:
                            if components.merge(a, b) == "blocked_cannot_link":
                                raise PipelineError(
                                    f"Protected people boundary collapsed through {review['candidate_id']}"
                                )
                        applied = edges
                        effective = "reviewed_match_applied"
                else:
                    effective = "reviewed_match_unmapped_or_ambiguous"
        decision_rows.append(
            {
                "candidate_id": review["candidate_id"],
                "review_decision": review["decision"],
                "effective_decision": effective,
                "edge_basis": basis,
                "left_current_entity_ids_json": canonical_json(left.entity_ids),
                "right_current_entity_ids_json": canonical_json(right.entity_ids),
                "left_current_assertion_ids_json": canonical_json(left.assertion_ids),
                "right_current_assertion_ids_json": canonical_json(right.assertion_ids),
                "applied_edges_json": canonical_json(applied),
                "left_remap_method": left.method,
                "right_remap_method": right.method,
                "reason": review["reason"],
                "origin": review["origin"],
            }
        )
        candidate_rows.append(
            {
                "candidate_id": review["candidate_id"],
                "left_anchor_id": review["left"]["anchor_id"],
                "right_anchor_id": review["right"]["anchor_id"],
                "left_names_json": canonical_json(review["left"].get("names", [])),
                "right_names_json": canonical_json(review["right"].get("names", [])),
                "decision": review["decision"],
                "review_status": "reviewed",
                "audit_source_correction_flag": str(
                    bool(review.get("source_correction_required", False))
                ),
                "requires_current_source_correction": str(
                    bool(review.get("source_correction_required", False))
                    and review["left"].get("kind") == "source_local_person"
                    and review["right"].get("kind") == "source_local_person"
                ),
                "shared_institutions_json": canonical_json(
                    review.get("shared_institutions", [])
                ),
                "shared_work_ids_json": canonical_json(
                    review.get("shared_work_ids", [])
                ),
                "shared_pages_json": canonical_json(review.get("shared_pages", [])),
                "reason": review["reason"],
                "origin": review["origin"],
            }
        )
    attachment_ids = {aid for values in attachments.values() for aid in values}
    people, crosswalk, entity_to_global = _registry(bundle, components, attachment_ids)
    assertion_rows = []
    relationships = []
    for assertion in sorted(bundle.assertions, key=lambda row: row["assertion_id"]):
        global_id = entity_to_global.get(assertion.get("source_entity_id", ""), "")
        attached = sorted(
            {
                entity_to_global[entity]
                for entity, ids in attachments.items()
                if assertion["assertion_id"] in ids
            }
        )
        output = {
            **assertion,
            "global_person_id": global_id,
            "attached_global_person_ids_json": canonical_json(attached),
            "identity_treatment": "reviewed_evidence_attachment_only"
            if assertion["assertion_id"] in attachment_ids
            else "source_role_assertion",
            "eligible_roles_json": canonical_json(assertion.get("eligible_roles", [])),
            "quality_flags_json": canonical_json(assertion.get("quality_flags", [])),
            "context_json": canonical_json(assertion.get("context", {})),
        }
        assertion_rows.append(output)
        if (
            global_id
            and assertion["assertion_id"] not in attachment_ids
            and (
                assertion.get("relationship_id")
                or assertion.get("global_innovation_id")
            )
        ):
            relationships.append(
                {
                    "relationship_row_id": stable_id(
                        "person_relationship", assertion["assertion_id"]
                    ),
                    "global_person_id": global_id,
                    "source_entity_id": assertion["source_entity_id"],
                    "assertion_id": assertion["assertion_id"],
                    "source": assertion["source"],
                    "role": assertion.get("role", ""),
                    "relationship_id": assertion.get("relationship_id", ""),
                    "local_innovation_id": assertion.get("local_innovation_id", ""),
                    "global_innovation_id": assertion.get("global_innovation_id", ""),
                    "source_locator": assertion.get("source_locator", ""),
                }
            )
    admission = [
        {
            **row,
            "global_person_id": entity_to_global.get(
                row.get("source_entity_id", ""), ""
            ),
            "quality_flags_json": canonical_json(row.get("quality_flags", [])),
            "context_json": canonical_json(row.get("context", {})),
        }
        for row in bundle.admission
    ]
    uncertainties = []
    for row in assertion_rows:
        flags = set(json_list(row["quality_flags_json"]))
        context = row.get("context", {})
        for kind in sorted(
            flags
            & {
                "shared_account_has_conflicting_names",
                "unresolved_existing_name_overlap",
            }
        ):
            parts = [
                kind,
                context.get("account_identifier_type", "")
                if kind.startswith("shared_account")
                else row["assertion_id"],
                context.get("account_identifier", "")
                if kind.startswith("shared_account")
                else "",
            ]
            uncertainties.append(
                {
                    "uncertainty_group_id": stable_id(
                        "source_person_uncertainty", *parts
                    ),
                    "uncertainty_type": kind,
                    "assertion_id": row["assertion_id"],
                    "source_entity_id": row["source_entity_id"],
                    "global_person_id": row["global_person_id"],
                    "raw_name": row["raw_name"],
                    "source_locator": row["source_locator"],
                    "context_json": row["context_json"],
                    "treatment": "retain_separate_without_inferred_identity_edge",
                }
            )
    constraint_reviews = [
        row
        for row in reviewed
        if row["decision"] in {"unresolved", "keep_separate"}
        or next(
            item
            for item in decision_rows
            if item["candidate_id"] == row["candidate_id"]
        )["effective_decision"]
        in {"reviewed_match_unmapped_or_ambiguous", "source_correction_not_applied"}
    ]
    unresolved_edges = []
    adjacency = defaultdict(set)
    for review in constraint_reviews:
        left, right = resolutions[review["candidate_id"]]
        for a in left.entity_ids:
            for b in right.entity_ids:
                if a == b:
                    continue
                adjacency[a].add(b)
                adjacency[b].add(a)
                unresolved_edges.append(
                    {
                        "candidate_id": review["candidate_id"],
                        "constraint_type": review["decision"],
                        "left_source_entity_id": a,
                        "right_source_entity_id": b,
                        "reason": review["reason"],
                    }
                )
    unresolved_components = []
    unresolved_members = []
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
        cid = stable_id("unresolved_person_component", *sorted(members))
        candidates = sorted(
            {
                row["candidate_id"]
                for row in unresolved_edges
                if row["left_source_entity_id"] in members
                or row["right_source_entity_id"] in members
            }
        )
        unresolved_components.append(
            {
                "unresolved_component_id": cid,
                "member_count": len(members),
                "candidate_ids_json": canonical_json(candidates),
                "treatment": "retain_reviewed_identity_constraints",
            }
        )
        for member in sorted(members):
            unresolved_members.append(
                {
                    "unresolved_component_id": cid,
                    "source_entity_id": member,
                    "global_person_id": entity_to_global.get(member, ""),
                }
            )
    assessment_observations, assessments, scores, assessment_admission = (
        _assessment_tables(source_tables, entity_to_global)
    )
    person_location_admission, person_location_assertions = _person_location_tables(
        source_tables, entity_to_global, geography
    )
    contributions = []
    results = []
    assertions_by_global = defaultdict(list)
    for row in assertion_rows:
        if row["global_person_id"] and row["assertion_id"] not in attachment_ids:
            assertions_by_global[row["global_person_id"]].append(row)
    for measure, roles in PERSON_MEASURES.items():
        qualifying = sorted(
            {
                row["global_person_id"]
                for row in people
                if set(json_list(row["eligible_roles_json"])) & roles
            }
        )
        for global_id in qualifying:
            ids = sorted(
                row["assertion_id"]
                for row in assertions_by_global[global_id]
                if set(json_list(row["eligible_roles_json"])) & roles
                or row.get("role") in roles
            )
            if not ids:
                raise PipelineError(
                    f"{measure} contribution lacks a qualifying assertion"
                )
            contributions.append(
                {
                    "contribution_id": stable_id(
                        "person_measure_contribution", measure, global_id
                    ),
                    "measure_id": measure,
                    "global_person_id": global_id,
                    "contribution_value": 1,
                    "basis": "distinct_global_person_with_source_supported_role",
                    "qualifying_assertion_ids_json": canonical_json(ids),
                }
            )
        results.append(
            {
                "measure_id": measure,
                "value": len(qualifying),
                "unit": "distinct_people",
                "result_type": "record_derived_snapshot",
                "coverage": "available_named_person_evidence",
                "source_reference": "person_assertions#qualifying_assertion_ids_json",
            }
        )
    for measure, condition in (
        ("C08_ASSESSED_PEOPLE", lambda row: truth(row["complete"])),
        (
            "C08_INCREASED_PEOPLE",
            lambda row: truth(row["complete"]) and truth(row["any_increase"]),
        ),
    ):
        by_global = defaultdict(list)
        for row in assessments:
            if condition(row):
                by_global[row["global_person_id"]].append(row["assessment_id"])
        for global_id, ids in sorted(by_global.items()):
            contributions.append(
                {
                    "contribution_id": stable_id(
                        "person_measure_contribution", measure, global_id
                    ),
                    "measure_id": measure,
                    "global_person_id": global_id,
                    "contribution_value": 1,
                    "basis": "distinct_global_person_with_complete_paired_assessment"
                    if measure.endswith("ASSESSED_PEOPLE")
                    else "distinct_global_person_with_complete_assessment_reporting_increase",
                    "qualifying_assertion_ids_json": canonical_json(sorted(ids)),
                }
            )
        results.append(
            {
                "measure_id": measure,
                "value": len(by_global),
                "unit": "distinct_people",
                "result_type": "record_derived_snapshot",
                "coverage": "complete_source_paired_assessments",
                "source_reference": "development_assessments#assessment_id",
            }
        )
    output = {name: [] for name in TABLE_COLUMNS}
    output.update(
        {
            "global_people": people,
            "person_crosswalk": crosswalk,
            "person_assertions": assertion_rows,
            "admission": admission,
            "person_location_admission": person_location_admission,
            "person_location_assertions": person_location_assertions,
            "candidate_pairs": candidate_rows,
            "identity_decisions": decision_rows,
            "relationships": relationships,
            "unresolved_components": unresolved_components,
            "unresolved_component_members": unresolved_members,
            "unresolved_component_edges": unresolved_edges,
            "source_uncertainties": uncertainties,
            "assessment_observations": assessment_observations,
            "development_assessments": assessments,
            "development_scores": scores,
            "assessment_admission": assessment_admission,
            "measure_contributions": contributions,
            "measure_results": results,
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
