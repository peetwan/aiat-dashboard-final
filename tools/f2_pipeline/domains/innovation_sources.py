"""Adapt four source-local innovation domains to the reviewed common model."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..common import normalize
from .resolution import (
    contextual_evidence_locator,
    evidence_locator,
    fail,
    json_list,
    source_tables_for,
    truth,
)

SOURCE_ORDER = ("icommunity", "pmua_apptech", "rinmp", "apptech_mru")


@dataclass
class LocalInnovation:
    source: str
    local_innovation_id: str
    display_name: str
    identity_status: str
    source_ids: list[str]
    aliases: set[str] = field(default_factory=set)
    descriptions: list[tuple[str, str, str]] = field(default_factory=list)
    researchers: set[str] = field(default_factory=set)
    institutions: set[str] = field(default_factory=set)
    ip_identifiers: set[str] = field(default_factory=set)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.local_innovation_id}"


@dataclass
class SourceBundle:
    source: str
    canonical_source_id: str
    innovations: dict[str, LocalInnovation]
    source_id_to_local: dict[str, str]
    source_records: list[dict[str, Any]]
    readiness: list[dict[str, Any]]
    use_locations: list[dict[str, Any]]
    cannot_local_pairs: set[frozenset[str]]
    unresolved_local_pairs: set[frozenset[str]]
    boundary_evidence: list[dict[str, Any]]
    source_member_to_local: dict[str, str] = field(default_factory=dict)


def _table(tables: dict[str, list[dict]], name: str) -> list[dict]:
    rows = tables.get(name)
    if not isinstance(rows, list):
        fail("innovations", f"missing source table {name}")
    return rows


def _observations(tables: dict[str, list[dict]]) -> dict[str, dict]:
    rows = _table(tables, "source_observations")
    index = {str(row.get("observation_id", "")): row for row in rows}
    if "" in index or len(index) != len(rows):
        fail(
            "innovations", "source_observations has missing or duplicate observation_id"
        )
    return index


def _source_record(
    source: str,
    local_id: str,
    source_id: str,
    observation: dict,
    title: Any,
    raw_input: dict,
    context_locator: Any = "",
) -> dict[str, Any]:
    locator = contextual_evidence_locator(raw_input, observation, context_locator)
    raw_file, _, row_locator = locator.partition("#")
    return {
        "source": source,
        "local_innovation_id": local_id,
        "source_id": str(source_id),
        "source_key": observation.get("source_key", ""),
        "observation_id": observation.get("observation_id", ""),
        "title_raw": normalize(title),
        "raw_file": raw_file,
        "row_locator": row_locator,
        "file_sha256": observation.get("file_sha256", ""),
    }


def _base_innovations(
    source: str, tables: dict[str, list[dict]]
) -> tuple[
    dict[str, LocalInnovation], dict[str, str], dict[str, set[str]], dict[str, str]
]:
    innovations: dict[str, LocalInnovation] = {}
    raw_id_locals: dict[str, set[str]] = defaultdict(set)
    member_to_local: dict[str, str] = {}
    for row in _table(tables, "innovations"):
        local_id = str(row.get("innovation_id", ""))
        if not local_id or local_id in innovations:
            fail(
                "innovations",
                f"{source} innovations has missing or duplicate innovation_id",
            )
        source_ids = [str(value) for value in json_list(row.get("source_ids_json"))]
        aliases = {
            normalize(value)
            for value in json_list(row.get("aliases_json"))
            if normalize(value)
        }
        display = normalize(row.get("display_name"))
        if display:
            aliases.add(display)
        item = LocalInnovation(
            source,
            local_id,
            display,
            str(row.get("identity_status", "")),
            source_ids,
            aliases,
        )
        innovations[local_id] = item
        for source_id in source_ids:
            raw_id_locals[source_id].add(local_id)
        for member in json_list(row.get("source_member_keys_json")):
            member = str(member)
            if member in member_to_local:
                fail(
                    "innovations",
                    f"{source} context member appears in two identities: {member}",
                )
            member_to_local[member] = local_id
    unique = {
        source_id: next(iter(locals_))
        for source_id, locals_ in raw_id_locals.items()
        if len(locals_) == 1
    }
    return innovations, unique, raw_id_locals, member_to_local


def _protected_pairs(
    source: str, rows: list[dict], source_id_to_local: dict[str, str]
) -> tuple[set[frozenset[str]], set[frozenset[str]], list[dict[str, Any]]]:
    cannot: set[frozenset[str]] = set()
    unresolved: set[frozenset[str]] = set()
    evidence: list[dict[str, Any]] = []
    cannot_values = {
        "cannot_link",
        "cannot_link_preserved",
        "cannot_link_context_split",
        "cannot_link_prior_reviewed",
        "partition",
        "separate",
        "resolved_separate",
    }
    unresolved_values = {
        "unresolved",
        "separate_pending_new_evidence",
        "retained_unresolved_candidate",
        "reviewed_unresolved",
    }
    for row in rows:
        decision = str(row.get("decision") or row.get("outcome") or "")
        if decision not in cannot_values | unresolved_values:
            continue
        raw_ids = json_list(
            row.get("source_ids_json")
            or row.get("source_keys_json")
            or row.get("evidence_source_ids_json")
        )
        if not raw_ids:
            raw_ids = [row.get("left_source_id", ""), row.get("right_source_id", "")]
        resolved: set[str] = set()
        for raw in raw_ids:
            value = str(raw)
            value = (
                value.rsplit(":", 1)[-1] if value not in source_id_to_local else value
            )
            if value in source_id_to_local:
                resolved.add(source_id_to_local[value])
        if len(resolved) < 2:
            continue
        for index, left in enumerate(sorted(resolved)):
            for right in sorted(resolved)[index + 1 :]:
                pair = frozenset((f"{source}:{left}", f"{source}:{right}"))
                target = unresolved if decision in unresolved_values else cannot
                target.add(pair)
                evidence.append(
                    {
                        "pair": pair,
                        "boundary_kind": "unresolved_candidate"
                        if decision in unresolved_values
                        else "cannot_link_constraint",
                        "decision_id": str(row.get("decision_id", "")),
                        "decision": decision,
                        "origin": "source_local_review",
                        "source_locator": str(row.get("source_locator", "")),
                        "evidence_json": row.get("evidence_locators_json")
                        or row.get("evidence_observation_ids_json")
                        or "[]",
                        "reason": str(row.get("reason", "")),
                    }
                )
    return cannot, unresolved, evidence


def _load_icommunity(
    canonical: str, tables: dict[str, list[dict]], raw_input: dict
) -> SourceBundle:
    innovations, unique, raw_id_locals, member_to_local = _base_innovations(
        "icommunity", tables
    )
    observations = _observations(tables)
    observation_to_local: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    for row in _table(tables, "innovation_details"):
        local_id, observation_id = (
            str(row.get("innovation_id", "")),
            str(row.get("observation_id", "")),
        )
        if (
            local_id not in innovations
            or observation_id not in observations
            or observation_id in observation_to_local
        ):
            fail("innovations", "stale iCommunity innovation detail endpoint")
        observation_to_local[observation_id] = local_id
        description = normalize(row.get("description"))
        if description:
            innovations[local_id].descriptions.append(
                (
                    description,
                    observation_id,
                    str(
                        row.get("source_locator")
                        or evidence_locator(raw_input, observations[observation_id])
                    ),
                )
            )
    for observation_id, local_id in observation_to_local.items():
        observation = observations[observation_id]
        source_id = str(observation.get("source_id", ""))
        if source_id not in raw_id_locals or local_id not in raw_id_locals[source_id]:
            fail(
                "innovations",
                "iCommunity observation membership disagrees with source identity",
            )
        title = next(
            (
                row.get("title_raw") or row.get("innovation_name_raw")
                for row in _table(tables, "innovation_details")
                if str(row.get("observation_id")) == observation_id
            ),
            innovations[local_id].display_name,
        )
        records.append(
            _source_record(
                "icommunity", local_id, source_id, observation, title, raw_input
            )
        )
    for row in _table(tables, "researcher_assertions"):
        local_id = observation_to_local.get(str(row.get("observation_id", "")))
        if local_id and normalize(row.get("full_name")):
            innovations[local_id].researchers.add(normalize(row.get("full_name")))
    for row in _table(tables, "institution_assertions"):
        local_id = observation_to_local.get(str(row.get("observation_id", "")))
        if local_id and normalize(row.get("name")):
            innovations[local_id].institutions.add(normalize(row.get("name")))
    readiness = []
    for row in _table(tables, "readiness"):
        local_id = str(row.get("innovation_id", ""))
        observation_id = str(row.get("observation_id", ""))
        if local_id not in innovations or observation_id not in observations:
            fail("innovations", "stale iCommunity readiness endpoint")
        readiness.append(
            {
                "source": "icommunity",
                "local_innovation_id": local_id,
                "source_id": observations[observation_id].get("source_id", ""),
                "observation_id": observation_id,
                "assessment_id": row.get("assessment_id", ""),
                "source_locator": str(
                    row.get("source_locator")
                    or evidence_locator(raw_input, observations[observation_id])
                ),
                "scale": row.get("scale", ""),
                "raw_level": row.get("export_raw", ""),
                "numeric_level": row.get("end_level", ""),
                "label_raw": row.get("label_raw", ""),
                "qualifies_k04": str(truth(row.get("qualifies"))),
                "basis": row.get("basis", ""),
                "assessment_context": row.get(
                    "assessment_context", "project_end_export"
                ),
            }
        )
    locations = []
    for row in _table(tables, "locations"):
        local_id = str(row.get("entity_id", ""))
        if (
            local_id not in innovations
            or row.get("location_role") != "declared_innovation_use"
        ):
            continue
        observation_id = str(row.get("observation_id", ""))
        if observation_id not in observations:
            fail("innovations", "stale iCommunity location endpoint")
        locations.append(
            _location_row(
                "icommunity",
                local_id,
                observations[observation_id],
                row,
                raw_input,
                "status",
            )
        )
    cannot, unresolved, boundaries = _protected_pairs(
        "icommunity",
        _table(tables, "identity_decisions"),
        {**unique, **member_to_local},
    )
    return SourceBundle(
        "icommunity",
        canonical,
        innovations,
        unique,
        records,
        readiness,
        locations,
        cannot,
        unresolved,
        boundaries,
        member_to_local,
    )


def _location_row(
    source: str,
    local_id: str,
    observation: dict,
    row: dict,
    raw_input: dict,
    status_field: str = "resolution_status",
) -> dict[str, Any]:
    return {
        "source": source,
        "local_innovation_id": local_id,
        "source_id": observation.get("source_id", row.get("source_id", "")),
        "observation_id": observation.get("observation_id", ""),
        "location_id": row.get("location_id") or row.get("assertion_id", ""),
        "location_role": row.get("location_role", "declared_innovation_use"),
        "province_raw": row.get("province_raw", ""),
        "province_normalized": row.get("province_normalized", ""),
        "province_code": row.get("province_code", ""),
        "district_normalized": row.get("district_normalized", ""),
        "district_code": row.get("district_code", ""),
        "subdistrict_normalized": row.get("subdistrict_normalized", ""),
        "subdistrict_code": row.get("subdistrict_code", ""),
        "resolution_status": row.get(status_field, ""),
        "coverage_eligibility": row.get(
            "coverage_eligibility", "eligible_innovation_use"
        ),
        "source_locator": (
            contextual_evidence_locator(raw_input, observation, row.get("source_locator"))
            if source == "rinmp"
            else str(row.get("source_locator") or evidence_locator(raw_input, observation))
        ),
    }


def _load_standard(
    source: str,
    canonical: str,
    tables: dict[str, list[dict]],
    raw_input: dict,
    detail_table: str,
    detail_title: str,
) -> tuple[SourceBundle, dict[str, dict]]:
    innovations, unique, _, member_map = _base_innovations(source, tables)
    observations = _observations(tables)
    records = []
    for row in _table(tables, detail_table):
        local_id, observation_id, source_id = (
            str(row.get("innovation_id", "")),
            str(row.get("observation_id", "")),
            str(row.get("source_id", "")),
        )
        if (
            local_id not in innovations
            or observation_id not in observations
            or unique.get(source_id) != local_id
        ):
            fail("innovations", f"stale {source} detail endpoint")
        if source == "rinmp" and (
            str(observations[observation_id].get("source_id", "")) != source_id
        ):
            fail("innovations", "RINMP profile and observation source IDs disagree")
        innovations[local_id].aliases.add(normalize(row.get(detail_title)))
        records.append(
            _source_record(
                source,
                local_id,
                source_id,
                observations[observation_id],
                row.get(detail_title),
                raw_input,
            )
        )
    cannot, unresolved, boundaries = _protected_pairs(
        source, _table(tables, "identity_decisions"), unique
    )
    return SourceBundle(
        source,
        canonical,
        innovations,
        unique,
        records,
        [],
        [],
        cannot,
        unresolved,
        boundaries,
        member_map,
    ), observations


def _load_pmua(
    canonical: str, tables: dict[str, list[dict]], raw_input: dict
) -> SourceBundle:
    bundle, observations = _load_standard(
        "pmua_apptech", canonical, tables, raw_input, "innovation_details", "title_raw"
    )
    for row in _table(tables, "innovation_details"):
        item = bundle.innovations[str(row["innovation_id"])]
        if normalize(row.get("researcher_name_raw")):
            item.researchers.add(normalize(row.get("researcher_name_raw")))
        if normalize(row.get("university_name_raw")):
            item.institutions.add(normalize(row.get("university_name_raw")))
    for row in _table(tables, "map_area_items"):
        local_id, oid = (
            str(row.get("innovation_id", "")),
            str(row.get("map_observation_id", "")),
        )
        if local_id not in bundle.innovations or oid not in observations:
            fail("innovations", "stale PMUA map endpoint")
        bundle.innovations[local_id].aliases.add(normalize(row.get("title_raw")))
        if normalize(row.get("university_raw")):
            bundle.innovations[local_id].institutions.add(
                normalize(row.get("university_raw"))
            )
        bundle.source_records.append(
            _source_record(
                "pmua_apptech",
                local_id,
                str(row.get("source_id", "")),
                observations[oid],
                row.get("title_raw"),
                raw_input,
                row.get("source_locator", ""),
            )
        )
    for row in _table(tables, "description_sections"):
        text, local_id = (
            normalize(row.get("text_readable")),
            str(row.get("innovation_id", "")),
        )
        if text and local_id in bundle.innovations:
            bundle.innovations[local_id].descriptions.append(
                (
                    text,
                    str(row.get("observation_id", "")),
                    str(row.get("source_locator", "")),
                )
            )
    for row in _table(tables, "ip_assertions"):
        value, local_id = (
            normalize(row.get("value_raw")),
            str(row.get("innovation_id", "")),
        )
        if value and row.get("identifier_status") not in {
            "missing",
            "not_an_identifier",
        }:
            bundle.innovations[local_id].ip_identifiers.add(value)
    for row in _table(tables, "readiness_assessments"):
        local_id, oid = (
            str(row.get("innovation_id", "")),
            str(row.get("observation_id", "")),
        )
        if local_id not in bundle.innovations or oid not in observations:
            fail("innovations", "stale PMUA readiness endpoint")
        bundle.readiness.append(
            {
                "source": "pmua_apptech",
                "local_innovation_id": local_id,
                "source_id": row.get(
                    "source_id", observations[oid].get("source_id", "")
                ),
                "observation_id": oid,
                "assessment_id": row.get("assessment_id", ""),
                "source_locator": row.get("source_locator")
                or evidence_locator(raw_input, observations[oid]),
                "scale": row.get("scale", ""),
                "raw_level": row.get("raw_level", ""),
                "numeric_level": row.get("level", ""),
                "label_raw": row.get("label_raw", ""),
                "qualifies_k04": str(truth(row.get("qualifies"))),
                "basis": row.get("basis", ""),
                "assessment_context": row.get("assessment_context", ""),
            }
        )
    records_by_observation = defaultdict(list)
    for record in bundle.source_records:
        records_by_observation[record["observation_id"]].append(record["source_id"])
    for row in _table(tables, "innovation_area_assertions"):
        local_id, oid = (
            str(row.get("innovation_id", "")),
            str(row.get("observation_id", "")),
        )
        if (
            local_id not in bundle.innovations
            or oid not in observations
            or not records_by_observation[oid]
        ):
            fail("innovations", "stale PMUA use-location endpoint")
        pairs = json_list(row.get("hierarchy_pairs_json")) or [{}]
        for index, pair in enumerate(pairs):
            copy = dict(row)
            copy.update(
                {
                    "location_id": f"{row.get('assertion_id', '')}:{index}",
                    "district_normalized": pair.get("district_name", ""),
                    "district_code": pair.get("district_code", ""),
                    "subdistrict_normalized": pair.get("subdistrict_name", ""),
                    "subdistrict_code": pair.get("subdistrict_code", ""),
                }
            )
            bundle.use_locations.append(
                _location_row(
                    "pmua_apptech", local_id, observations[oid], copy, raw_input
                )
            )
    return bundle


def _load_rinmp(
    canonical: str, tables: dict[str, list[dict]], raw_input: dict
) -> SourceBundle:
    bundle, observations = _load_standard(
        "rinmp", canonical, tables, raw_input, "innovation_profiles", "title_raw"
    )
    for row in _table(tables, "innovation_profiles"):
        item = bundle.innovations[str(row["innovation_id"])]
        if normalize(row.get("owner_display_name_raw")):
            item.researchers.add(normalize(row.get("owner_display_name_raw")))
        if normalize(row.get("institute_name_raw")):
            item.institutions.add(normalize(row.get("institute_name_raw")))
    for row in _table(tables, "readiness_assertions"):
        local_id, oid = (
            str(row.get("innovation_id", "")),
            str(row.get("observation_id", "")),
        )
        if local_id not in bundle.innovations or oid not in observations:
            fail("innovations", "stale RINMP readiness endpoint")
        bundle.readiness.append(
            {
                "source": "rinmp",
                "local_innovation_id": local_id,
                "source_id": row.get("source_id", ""),
                "observation_id": oid,
                "assessment_id": row.get("assertion_id", ""),
                "source_locator": contextual_evidence_locator(
                    raw_input, observations[oid], row.get("source_locator")
                ),
                "scale": row.get("scale", ""),
                "raw_level": row.get("value_raw", ""),
                "numeric_level": row.get("numeric_level", ""),
                "label_raw": "",
                "qualifies_k04": str(truth(row.get("qualifies_k04"))),
                "basis": row.get("validity", ""),
                "assessment_context": row.get("assessment_context", ""),
            }
        )
    for row in _table(tables, "location_assertions"):
        if not str(row.get("coverage_eligibility", "")).startswith("eligible_"):
            continue
        local_id, oid = (
            str(row.get("innovation_id", "")),
            str(row.get("observation_id", "")),
        )
        if local_id not in bundle.innovations or oid not in observations:
            fail("innovations", "stale RINMP location endpoint")
        bundle.use_locations.append(
            _location_row("rinmp", local_id, observations[oid], row, raw_input)
        )
    return bundle


def _load_mru(
    canonical: str, tables: dict[str, list[dict]], raw_input: dict
) -> SourceBundle:
    bundle, observations = _load_standard(
        "apptech_mru",
        canonical,
        tables,
        raw_input,
        "innovation_observations",
        "title_raw",
    )
    for row in _table(tables, "innovation_observations"):
        item = bundle.innovations[str(row["innovation_id"])]
        for value in json_list(row.get("original_inventors_json")):
            if normalize(value):
                item.researchers.add(normalize(value))
        for field_name in ("inventors_raw", "account_owner_name_raw"):
            if normalize(row.get(field_name)):
                item.researchers.add(normalize(row.get(field_name)))
        for field_name in ("rights_holder_raw", "account_affiliation_raw"):
            if normalize(row.get(field_name)):
                item.institutions.add(normalize(row.get(field_name)))
    for row in _table(tables, "readiness_assessments"):
        local_id, oid = (
            str(row.get("innovation_id", "")),
            str(row.get("observation_id", "")),
        )
        if local_id not in bundle.innovations or oid not in observations:
            fail("innovations", "stale MRU readiness endpoint")
        valid, qualifies = (
            truth(row.get("trl_valid")),
            truth(row.get("qualifies_k04_assertion")),
        )
        bundle.readiness.append(
            {
                "source": "apptech_mru",
                "local_innovation_id": local_id,
                "source_id": row.get("source_id", ""),
                "observation_id": oid,
                "assessment_id": row.get("assessment_id", ""),
                "source_locator": contextual_evidence_locator(
                    raw_input, observations[oid], row.get("source_locator")
                ),
                "scale": "TRL",
                "raw_level": row.get("trl_level", ""),
                "numeric_level": row.get("trl_level", ""),
                "label_raw": "",
                "qualifies_k04": str(qualifies),
                "basis": "valid_numeric_trl_8_9"
                if qualifies
                else "valid_numeric_trl_below_8"
                if valid
                else "invalid_trl",
                "assessment_context": "mru_innovation_listing",
            }
        )
    return bundle


def load_sources(
    source_tables: dict[str, dict[str, list[dict]]], raw_inputs: dict[str, dict]
) -> dict[str, SourceBundle]:
    loaders = {
        "icommunity": _load_icommunity,
        "pmua_apptech": _load_pmua,
        "rinmp": _load_rinmp,
        "apptech_mru": _load_mru,
    }
    bundles: dict[str, SourceBundle] = {}
    for source in SOURCE_ORDER:
        canonical, tables = source_tables_for(source_tables, source)
        raw_input = raw_inputs.get(canonical)
        if not isinstance(raw_input, dict):
            fail("innovations", f"missing raw_inputs for {canonical}")
        bundles[source] = loaders[source](canonical, tables, raw_input)
    return bundles
