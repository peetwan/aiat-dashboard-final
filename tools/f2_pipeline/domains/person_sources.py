"""Adapt the reviewed source pilots into person identity evidence.

Source cleaners own identity inside each source. This module keeps those current
identities intact and translates the surrounding claims into a common shape.
It does not infer cross-source identity, parse arbitrary prose for people, or
turn collector and repeated-name buckets into people.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from ..common import PipelineError, matching_name, normalize, stable_id
from .resolution import (
    contextual_evidence_locator,
    evidence_locator,
    fail,
    json_list,
    review_payload,
    source_tables_for,
    truth,
)

SOURCE_ORDER = (
    "icommunity",
    "pmua_apptech",
    "apptech_mru",
    "rinmp",
    "atlocal",
    "cultural_map",
)


@dataclass
class PersonSources:
    entities: dict[str, dict]
    assertions: list[dict]
    admission: list[dict]
    input_files: list[dict]


class _Builder:
    def __init__(
        self,
        source_tables: dict,
        reviews: dict,
        raw_inputs: dict,
        innovation_tables: dict,
    ):
        self.reviews = reviews
        self.raw_inputs = raw_inputs
        self.tables: dict[str, dict[str, list[dict]]] = {}
        self.canonical_sources: dict[str, str] = {}
        for source in SOURCE_ORDER:
            canonical, tables = source_tables_for(source_tables, source)
            self.canonical_sources[source] = canonical
            self.tables[source] = tables
            if canonical not in raw_inputs:
                fail("people", f"missing raw_inputs for {canonical}")
        self.entities: dict[str, dict] = {}
        self.assertions: list[dict] = []
        self.admission: list[dict] = []
        self.input_files: list[dict] = []
        self.observations: dict[str, dict[str, dict]] = {}
        crosswalk = innovation_tables.get("innovation_crosswalk")
        if not isinstance(crosswalk, list):
            fail("people", "innovation_tables lacks innovation_crosswalk")
        self.global_innovations = {
            (str(row["source"]), str(row["local_innovation_id"])): str(
                row["global_innovation_id"]
            )
            for row in crosswalk
        }
        if len(self.global_innovations) != len(crosswalk):
            fail("people", "innovation crosswalk has duplicate source/local keys")

    def csv(self, relative_path: str) -> list[dict]:
        parts = relative_path.split("/")
        try:
            pilot = parts[2]
        except IndexError as exc:
            fail("people", f"invalid normalized table reference {relative_path}")
            raise AssertionError from exc
        source = {
            "icommunity-v1": "icommunity",
            "pmua-apptech-v1": "pmua_apptech",
            "apptech-mru-v1": "apptech_mru",
            "rinmp-v1": "rinmp",
            "atlocal-v1": "atlocal",
            "cultural-map-v1": "cultural_map",
        }.get(pilot)
        table = parts[-1].removesuffix(".csv")
        if source is None or table not in self.tables[source]:
            fail("people", f"missing normalized source table for {relative_path}")
        rows = self.tables[source][table]
        if not isinstance(rows, list):
            fail("people", f"source table {source}.{table} must be a row list")
        return rows

    def json(self, relative_path: str) -> object:
        if relative_path == "config/cross_source_people/source_cultural_map.json":
            return review_payload(
                self.reviews, "cross_source_people/source_cultural_map.json"
            )
        file_name = relative_path.split("/")[-1].removesuffix(".gz")
        source = (
            "icommunity"
            if "/icommunity/" in relative_path
            else "cultural_map"
            if "/f2_culturalmap_university/" in relative_path
            else ""
        )
        if not source:
            fail("people", f"undeclared injected raw input {relative_path}")
        datasets = self.raw_inputs[self.canonical_sources[source]].get("datasets", {})
        for dataset, payload in datasets.items():
            metadata = (
                self.raw_inputs[self.canonical_sources[source]]
                .get("metadata", {})
                .get(dataset, {})
            )
            candidate = (
                str(metadata.get("file", dataset + ".json"))
                .split("/")[-1]
                .removesuffix(".gz")
            )
            if candidate == file_name or dataset + ".json" == file_name:
                return payload
        fail("people", f"raw input {relative_path} is not supplied")
        raise AssertionError

    def load_observations(self, source: str, pilot_name: str) -> None:
        rows = self.csv(f"derived/pilots/{pilot_name}/source_observations.csv")
        index = {str(row.get("observation_id", "")): row for row in rows}
        if "" in index or len(index) != len(rows):
            fail("people", f"{source} observations have missing or duplicate IDs")
        self.observations[source] = index

    def locator(self, source: str, observation_id: str, suffix: str = "") -> str:
        observation = self.observations[source].get(observation_id)
        if not observation:
            return ""
        raw_input = self.raw_inputs[self.canonical_sources[source]]
        return evidence_locator(raw_input, observation, suffix)

    def global_innovation(self, source: str, local_id: str) -> str:
        if not local_id:
            return ""
        value = self.global_innovations.get((source, local_id))
        if value is None:
            fail("people", f"unresolved innovation endpoint {source}:{local_id}")
        return value

    def add_entity(
        self,
        *,
        source: str,
        local_id: str,
        entity_kind: str,
        identity_basis: str,
        display_name: str,
        aliases: list[str] | None = None,
        source_ids: list[str] | None = None,
        observation_ids: list[str] | None = None,
        identity_status: str,
        natural_person_status: str,
        eligible_roles: list[str] | None = None,
        quality_flags: list[str] | None = None,
        source_identity_decision_ids: list[str] | None = None,
    ) -> str:
        source_entity_id = f"{source}:{local_id}"
        names = [display_name, *(aliases or [])]
        row = {
            "source_entity_id": source_entity_id,
            "source": source,
            "source_local_id": local_id,
            "entity_kind": entity_kind,
            "identity_basis": identity_basis,
            "display_name": normalize(display_name),
            "matching_names": sorted(
                {
                    matching_name(name).casefold()
                    for name in names
                    if matching_name(name)
                }
            ),
            "aliases": sorted({normalize(name) for name in names if normalize(name)}),
            "source_ids": sorted(
                {str(value) for value in source_ids or [] if str(value)}
            ),
            "observation_ids": sorted(set(observation_ids or [])),
            "identity_status": identity_status,
            "natural_person_status": natural_person_status,
            "eligible_roles": sorted(set(eligible_roles or [])),
            "quality_flags": sorted(set(quality_flags or [])),
            "source_identity_decision_ids": sorted(
                set(source_identity_decision_ids or [])
            ),
        }
        existing = self.entities.get(source_entity_id)
        if existing and existing != row:
            raise PipelineError(f"Conflicting source entity: {source_entity_id}")
        self.entities[source_entity_id] = row
        return source_entity_id

    def add_assertion(
        self,
        *,
        assertion_id: str,
        assertion_kind: str,
        source: str,
        source_entity_id: str = "",
        source_local_id: str = "",
        source_record_id: str = "",
        observation_id: str = "",
        source_key: str = "",
        raw_name: str = "",
        matching_value: str = "",
        role: str = "",
        eligible_roles: list[str] | None = None,
        institution_raw: str = "",
        institution_role: str = "",
        local_innovation_id: str = "",
        relationship_id: str = "",
        source_locator: str = "",
        evidence_text: str = "",
        natural_person_status: str = "",
        quality_flags: list[str] | None = None,
        context: dict | None = None,
        admission_decision: str | None = None,
        admission_reason: str = "",
        subject_kind: str = "person_evidence",
    ) -> None:
        if assertion_kind not in {
            "source_local_identity",
            "person_claim",
            "evidence_only",
        }:
            raise PipelineError(f"Unknown assertion kind: {assertion_kind}")
        if source_locator and not source_locator.startswith("evidence://"):
            if not observation_id:
                fail(
                    "people",
                    f"assertion {assertion_id} has non-immutable locator without observation",
                )
            current = self.locator(source, observation_id)
            if "#" not in source_locator:
                fail("people", f"assertion {assertion_id} has invalid source locator")
            source_locator = (
                current.split("#", 1)[0] + "#" + source_locator.split("#", 1)[1]
            )
        if source in {"apptech_mru", "rinmp"}:
            observation = self.observations.get(source, {}).get(observation_id)
            if observation is None:
                fail("people", f"assertion {assertion_id} has stale observation")
            source_locator = contextual_evidence_locator(
                self.raw_inputs[self.canonical_sources[source]],
                observation,
                source_locator,
            )
        row = {
            "assertion_id": assertion_id,
            "assertion_kind": assertion_kind,
            "source_entity_id": source_entity_id,
            "source": source,
            "source_local_id": source_local_id,
            "source_record_id": source_record_id,
            "observation_id": observation_id,
            "source_key": source_key,
            "raw_name": normalize(raw_name),
            "matching_name": matching_name(matching_value or raw_name).casefold(),
            "role": role,
            "eligible_roles": sorted(set(eligible_roles or [])),
            "institution_raw": normalize(institution_raw),
            "institution_role": institution_role,
            "local_innovation_id": local_innovation_id,
            "global_innovation_id": self.global_innovation(source, local_innovation_id),
            "relationship_id": relationship_id,
            "source_locator": source_locator,
            "evidence_text": normalize(evidence_text),
            "natural_person_status": natural_person_status,
            "quality_flags": sorted(set(quality_flags or [])),
            "context": context or {},
        }
        self.assertions.append(row)
        if admission_decision:
            self.admission.append(
                {
                    "admission_id": f"admission:{source}:{assertion_id}",
                    "source": source,
                    "source_record_id": source_record_id,
                    "observation_id": observation_id,
                    "assertion_id": assertion_id,
                    "source_entity_id": source_entity_id,
                    "decision": admission_decision,
                    "subject_kind": subject_kind,
                    "reason": admission_reason,
                    "source_locator": source_locator,
                    "quality_flags": sorted(set(quality_flags or [])),
                    "context": context or {},
                }
            )

    def finish(self) -> PersonSources:
        assertion_ids = [row["assertion_id"] for row in self.assertions]
        admission_ids = [row["admission_id"] for row in self.admission]
        if len(assertion_ids) != len(set(assertion_ids)):
            raise PipelineError("Duplicate person assertion IDs")
        if len(admission_ids) != len(set(admission_ids)):
            raise PipelineError("Duplicate person admission IDs")
        for row in self.assertions:
            entity_id = row["source_entity_id"]
            if entity_id and entity_id not in self.entities:
                raise PipelineError(
                    f"Assertion has missing entity: {row['assertion_id']}"
                )
            if (
                row["observation_id"]
                and row["observation_id"] not in self.observations[row["source"]]
            ):
                raise PipelineError(
                    f"Assertion has stale observation: {row['assertion_id']}"
                )
            if row["source_locator"] and not row["source_locator"].startswith(
                "evidence://"
            ):
                raise PipelineError(
                    f"Assertion lacks immutable evidence locator: {row['assertion_id']}"
                )
        return PersonSources(
            dict(sorted(self.entities.items())),
            sorted(self.assertions, key=lambda row: row["assertion_id"]),
            sorted(self.admission, key=lambda row: row["admission_id"]),
            self.input_files,
        )


def _json_list(value) -> list:
    return json_list(value)


def _true(value: object) -> bool:
    return truth(value)


def _source_key(builder: _Builder, source: str, observation_id: str) -> str:
    return builder.observations[source].get(observation_id, {}).get("source_key", "")


def _raw_source_id(builder: _Builder, source: str, observation_id: str) -> str:
    return builder.observations[source].get(observation_id, {}).get("source_id", "")


def _load_icommunity(builder: _Builder) -> None:
    source = "icommunity"
    pilot = "icommunity-v1"
    builder.load_observations(source, pilot)
    people = builder.csv(f"derived/pilots/{pilot}/people.csv")
    entity_observations = builder.csv(f"derived/pilots/{pilot}/entity_observations.csv")
    person_roles = builder.csv(f"derived/pilots/{pilot}/person_roles.csv")
    researcher_assertions = builder.csv(
        f"derived/pilots/{pilot}/researcher_assertions.csv"
    )
    institutions = builder.csv(f"derived/pilots/{pilot}/institution_assertions.csv")
    innovations = builder.csv(f"derived/pilots/{pilot}/innovation_details.csv")
    work_mentions = builder.csv(f"derived/pilots/{pilot}/work_mentions.csv")
    identity_decisions = builder.csv(f"derived/pilots/{pilot}/identity_decisions.csv")
    excluded = builder.csv(f"derived/pilots/{pilot}/non_person_subjects.csv")
    entrepreneur_evidence = builder.csv(
        f"derived/pilots/{pilot}/entrepreneur_evidence.csv"
    )
    raw_rows = builder.json("data/icommunity/apptech_innovators.json")["data"]

    raw_by_observation = {
        row["observation_id"]: raw_rows[int(row["row_locator"].split("/")[-1])]
        for row in builder.observations[source].values()
        if row["dataset"] == "apptech_innovators"
    }
    observations_by_person: dict[str, list[str]] = defaultdict(list)
    for row in entity_observations:
        if row["entity_type"] == "person":
            observations_by_person[row["entity_id"]].append(row["observation_id"])
    decisions_by_person: dict[str, list[str]] = defaultdict(list)
    for row in identity_decisions:
        for field in ("result_entity_id", "left_entity_id", "right_entity_id"):
            person_id = row.get(field, "")
            if person_id:
                decisions_by_person[person_id].append(row["decision_id"])
    roles_by_person: dict[str, set[str]] = defaultdict(set)
    for row in person_roles:
        if row["role"] == "community_innovator":
            roles_by_person[row["person_id"]].add("community_innovator")
    for row in entrepreneur_evidence:
        roles_by_person[row["person_id"]].add("cultural_entrepreneur")

    for row in people:
        person_id = row["person_id"]
        builder.add_entity(
            source=source,
            local_id=person_id,
            entity_kind="natural_person",
            identity_basis="source_local_identity",
            display_name=row["display_name"],
            aliases=_json_list(row["aliases_json"]),
            source_ids=[str(value) for value in _json_list(row["source_ids_json"])],
            observation_ids=observations_by_person[person_id],
            identity_status=row["identity_status"],
            natural_person_status="supported_natural_person",
            eligible_roles=sorted(roles_by_person[person_id]),
            quality_flags=[row["name_quality"]] if row["name_quality"] else [],
            source_identity_decision_ids=decisions_by_person[person_id],
        )

    institution_by_observation = {
        row["observation_id"]: row["name"] for row in institutions
    }
    innovation_by_observation = {
        row["observation_id"]: row["innovation_id"] for row in innovations
    }
    work_by_person_observation = {
        (row["person_id"], row["observation_id"]): row
        for row in work_mentions
        if row["person_id"]
    }
    for row in person_roles:
        person_id = row["person_id"]
        observation_id = row["observation_id"]
        raw = raw_by_observation.get(observation_id, {})
        work = work_by_person_observation.get((person_id, observation_id), {})
        eligible = (
            ["community_innovator"] if row["role"] == "community_innovator" else []
        )
        builder.add_assertion(
            assertion_id=row["role_id"],
            assertion_kind="source_local_identity",
            source=source,
            source_entity_id=f"{source}:{person_id}",
            source_local_id=person_id,
            source_record_id=str(
                raw.get("innovator_id", _raw_source_id(builder, source, observation_id))
            ),
            observation_id=observation_id,
            source_key=_source_key(builder, source, observation_id),
            raw_name=raw.get("innovator_name", ""),
            role=row["role"],
            eligible_roles=eligible,
            institution_raw=institution_by_observation.get(observation_id, ""),
            institution_role="project_context",
            local_innovation_id=work.get("innovation_id", ""),
            relationship_id=work.get("mention_id", ""),
            source_locator=builder.locator(source, observation_id, "/innovator_name"),
            evidence_text=row["role_text"],
            natural_person_status="supported_natural_person",
            context={
                "project_code": raw.get("project", {}).get("code", ""),
                "work_link_status": work.get("link_status", ""),
            },
        )

    researcher_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in researcher_assertions:
        researcher_rows[row["researcher_id"]].append(row)
    for researcher_id, rows in researcher_rows.items():
        names = [row["full_name"] for row in rows]
        matching_names = [row["matching_name"] for row in rows]
        statuses = {row["identity_status"] for row in rows}
        unverified = "unverified_account_subject" in statuses
        entity_id = ""
        if not unverified:
            entity_id = builder.add_entity(
                source=source,
                local_id=researcher_id,
                entity_kind="natural_person",
                identity_basis="source_local_identity",
                display_name=names[0],
                aliases=names[1:] + matching_names,
                source_ids=[row["source_id"] for row in rows],
                observation_ids=[row["observation_id"] for row in rows],
                identity_status=sorted(statuses)[0],
                natural_person_status="supported_natural_person",
            )
        for row in rows:
            observation_id = row["observation_id"]
            if unverified:
                builder.add_assertion(
                    assertion_id=stable_id(
                        "person_assertion",
                        source,
                        researcher_id,
                        observation_id,
                        row["source_id"],
                    ),
                    assertion_kind="evidence_only",
                    source=source,
                    source_record_id=row["source_id"],
                    observation_id=observation_id,
                    source_key=_source_key(builder, source, observation_id),
                    raw_name=row["full_name"],
                    role="",
                    institution_raw=institution_by_observation.get(observation_id, ""),
                    institution_role="project_context",
                    local_innovation_id=innovation_by_observation.get(
                        observation_id, ""
                    ),
                    source_locator=builder.locator(
                        source, observation_id, "/researcher"
                    ),
                    natural_person_status="unverified_account_subject",
                    quality_flags=[
                        row["identity_status"],
                        "account_style_name_not_verified_person",
                    ],
                    context={"mentioned_role": "researcher"},
                    admission_decision="exclude_non_person",
                    admission_reason="The source supplies an account-style label that does not verify a natural person.",
                    subject_kind="unverified_account_subject",
                )
                continue
            builder.add_assertion(
                assertion_id=stable_id(
                    "person_assertion",
                    source,
                    researcher_id,
                    observation_id,
                    row["source_id"],
                ),
                assertion_kind="source_local_identity",
                source=source,
                source_entity_id=entity_id,
                source_local_id=researcher_id,
                source_record_id=row["source_id"],
                observation_id=observation_id,
                source_key=_source_key(builder, source, observation_id),
                raw_name=row["full_name"],
                matching_value=row["matching_name"],
                role="researcher",
                institution_raw=institution_by_observation.get(observation_id, ""),
                institution_role="project_context",
                local_innovation_id=innovation_by_observation.get(observation_id, ""),
                source_locator=builder.locator(source, observation_id, "/researcher"),
                natural_person_status="supported_natural_person",
            )

    people_by_id = {row["person_id"]: row for row in people}
    for row in entrepreneur_evidence:
        person = people_by_id[row["person_id"]]
        observation_id = row["observation_id"]
        raw = raw_by_observation.get(observation_id, {})
        work = work_by_person_observation.get((row["person_id"], observation_id), {})
        builder.add_assertion(
            assertion_id=stable_id(
                "person_assertion",
                source,
                "entrepreneur",
                row["person_id"],
                observation_id,
            ),
            assertion_kind="source_local_identity",
            source=source,
            source_entity_id=f"{source}:{row['person_id']}",
            source_local_id=row["person_id"],
            source_record_id=str(
                raw.get("innovator_id", _raw_source_id(builder, source, observation_id))
            ),
            observation_id=observation_id,
            source_key=_source_key(builder, source, observation_id),
            raw_name=raw.get("innovator_name", person["display_name"]),
            role="cultural_product_operator",
            eligible_roles=["cultural_entrepreneur"],
            institution_raw=institution_by_observation.get(observation_id, ""),
            institution_role="project_context",
            local_innovation_id=work.get("innovation_id", ""),
            relationship_id=work.get("mention_id", ""),
            source_locator=row.get("source_locator")
            or builder.locator(source, observation_id, "/community_role_raw"),
            evidence_text=row["role_passage"],
            natural_person_status="supported_natural_person",
            quality_flags=[row["eligibility"]],
            context={
                "name_source_locator": row.get("name_source_locator")
                or builder.locator(source, observation_id, "/innovator_name"),
                "review_id": row.get("review_id", ""),
                "business_name": row.get("business_name", ""),
                "supporting_evidence": _json_list(
                    row.get("supporting_evidence_json", "[]")
                ),
            },
        )

    for row in excluded:
        source_ids = [str(value) for value in _json_list(row["source_ids_json"])]
        observation_id = next(
            (
                item["observation_id"]
                for item in entity_observations
                if item["entity_type"] == "non_person_subject"
                and item["entity_id"] == row["subject_id"]
            ),
            "",
        )
        assertion_id = stable_id(
            "person_assertion", source, row["subject_id"], observation_id
        )
        builder.add_assertion(
            assertion_id=assertion_id,
            assertion_kind="evidence_only",
            source=source,
            source_record_id=source_ids[0] if source_ids else "",
            observation_id=observation_id,
            source_key=_source_key(builder, source, observation_id),
            raw_name=row["display_name"],
            role="excluded_subject",
            source_locator=builder.locator(source, observation_id, "/innovator_name"),
            evidence_text=row["exclusion_reason"],
            natural_person_status="excluded_non_person",
            quality_flags=[row["identity_status"], row["exclusion_reason"]],
            admission_decision="exclude_non_person",
            admission_reason=row["exclusion_reason"],
            subject_kind="test_or_non_person_subject",
        )


def _load_pmua(builder: _Builder) -> None:
    source = "pmua_apptech"
    pilot = "pmua-apptech-v1"
    builder.load_observations(source, pilot)
    researchers = builder.csv(f"derived/pilots/{pilot}/researchers.csv")
    profiles = builder.csv(f"derived/pilots/{pilot}/researcher_profiles.csv")
    assertions = builder.csv(f"derived/pilots/{pilot}/researcher_assertions.csv")
    universities = builder.csv(f"derived/pilots/{pilot}/university_assertions.csv")
    reviews = builder.csv(f"derived/pilots/{pilot}/researcher_identity_reviews.csv")
    builder.csv(f"derived/pilots/{pilot}/person_identity_decisions.csv")
    builder.csv(f"derived/pilots/{pilot}/aggregate_summaries.csv")

    profiles_by_person: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in profiles:
        profiles_by_person[row["researcher_id"]].append(row)
    reviews_by_source_id: dict[str, list[str]] = defaultdict(list)
    for row in reviews:
        for source_id in _json_list(row["source_ids_json"]):
            reviews_by_source_id[str(source_id)].append(row["review_group_id"])
    for row in researchers:
        researcher_id = row["researcher_id"]
        person_profiles = profiles_by_person[researcher_id]
        source_ids = [str(value) for value in _json_list(row["source_ids_json"])]
        builder.add_entity(
            source=source,
            local_id=researcher_id,
            entity_kind="natural_person",
            identity_basis="source_local_identity",
            display_name=row["display_name"],
            aliases=[profile["name_raw"] for profile in person_profiles],
            source_ids=source_ids,
            observation_ids=_json_list(row["source_observation_ids_json"]),
            identity_status=row["identity_status"],
            natural_person_status="supported_source_profile",
            source_identity_decision_ids=[
                decision_id
                for source_id in source_ids
                for decision_id in reviews_by_source_id[source_id]
            ],
        )
    for row in profiles:
        researcher_id = row["researcher_id"]
        builder.add_assertion(
            assertion_id=stable_id(
                "person_assertion", source, "profile", row["source_id"]
            ),
            assertion_kind="source_local_identity",
            source=source,
            source_entity_id=f"{source}:{researcher_id}",
            source_local_id=researcher_id,
            source_record_id=row["source_id"],
            observation_id=row["observation_id"],
            source_key=_source_key(builder, source, row["observation_id"]),
            raw_name=row["name_raw"],
            matching_value=row["name_normalized"],
            role="researcher",
            institution_raw=row["university_raw"],
            institution_role="profile_affiliation",
            source_locator=builder.locator(source, row["observation_id"], "/title"),
            natural_person_status="supported_source_profile",
            quality_flags=[row["identity_status"]],
            context={
                "profile_url": row["profile_url"],
                "expertise_raw": row["expertise_raw"],
            },
        )

    university_by_observation = {
        row["observation_id"]: row["name_raw"] for row in universities
    }
    for row in assertions:
        if row["researcher_id"]:
            entity_id = f"{source}:{row['researcher_id']}"
            kind = "source_local_identity"
            local_id = row["researcher_id"]
            status = "supported_source_profile"
        else:
            institution = university_by_observation.get(row["observation_id"], "")
            local_id = stable_id(
                "missing_profile_claim",
                row["source_researcher_id"],
                matching_name(row["embedded_name_raw"]).casefold(),
                institution,
            )
            entity_id = f"{source}:{local_id}"
            if entity_id not in builder.entities:
                builder.add_entity(
                    source=source,
                    local_id=local_id,
                    entity_kind="person_claim",
                    identity_basis="source_reference_name_institution_partition",
                    display_name=row["embedded_name_raw"],
                    source_ids=[row["source_researcher_id"]],
                    observation_ids=[row["observation_id"]],
                    identity_status=row["profile_status"],
                    natural_person_status="named_missing_profile_claim",
                    quality_flags=["missing_profile"],
                )
            else:
                entity = builder.entities[entity_id]
                entity["observation_ids"] = sorted(
                    set(entity["observation_ids"] + [row["observation_id"]])
                )
            kind = "person_claim"
            status = "named_missing_profile_claim"
        builder.add_assertion(
            assertion_id=row["assertion_id"],
            assertion_kind=kind,
            source=source,
            source_entity_id=entity_id,
            source_local_id=local_id,
            source_record_id=row["source_researcher_id"],
            observation_id=row["observation_id"],
            source_key=row["source_key"],
            raw_name=row["embedded_name_raw"],
            role="researcher",
            institution_raw=university_by_observation.get(row["observation_id"], ""),
            institution_role="innovation_institution",
            local_innovation_id=row["innovation_id"],
            relationship_id=row["assertion_id"],
            source_locator=builder.locator(
                source, row["observation_id"], "/researcher"
            ),
            natural_person_status=status,
            quality_flags=[
                row["profile_status"],
                *(["missing_profile"] if kind == "person_claim" else []),
            ],
            admission_decision="admit_person_claim" if kind == "person_claim" else None,
            admission_reason="The innovation names a researcher whose profile is absent from the supplied directory."
            if kind == "person_claim"
            else "",
            subject_kind="missing_profile_named_assertion",
        )


def _load_mru(builder: _Builder) -> None:
    source = "apptech_mru"
    pilot = "apptech-mru-v1"
    builder.load_observations(source, pilot)
    people = builder.csv(f"derived/pilots/{pilot}/people.csv")
    roles = builder.csv(f"derived/pilots/{pilot}/role_assertions.csv")
    decisions = builder.csv(f"derived/pilots/{pilot}/person_identity_decisions.csv")

    decisions_by_person: dict[str, list[str]] = defaultdict(list)
    for row in decisions:
        for field in ("left_current_person_id", "right_current_person_id"):
            if row[field]:
                decisions_by_person[row[field]].append(row["decision_id"])
    source_ids_by_person: dict[str, set[str]] = defaultdict(set)
    for row in roles:
        if row["person_id"]:
            source_ids_by_person[row["person_id"]].add(row["source_id"])
    for row in people:
        eligible = ["inventor"] if _true(row["broader_innovator_eligible"]) else []
        builder.add_entity(
            source=source,
            local_id=row["person_id"],
            entity_kind="natural_person",
            identity_basis="source_local_identity",
            display_name=row["display_name"],
            aliases=[row["name_normalized"]],
            source_ids=sorted(source_ids_by_person[row["person_id"]]),
            observation_ids=_json_list(row["source_observation_ids_json"]),
            identity_status=row["identity_status"],
            natural_person_status="supported_natural_person",
            eligible_roles=eligible,
            quality_flags=[]
            if len(row["name_normalized"].split()) > 1
            else ["incomplete_name"],
            source_identity_decision_ids=decisions_by_person[row["person_id"]],
        )
    for row in roles:
        flags = [row["field_semantic_flag"]] if row["field_semantic_flag"] else []
        if row["placeholder"] == "True":
            flags.append("placeholder")
        if row["team_unspecified"] == "True":
            flags.append("team_unspecified")
        if row["person_id"]:
            eligible = ["inventor"] if row["role"] == "inventor" else []
            builder.add_assertion(
                assertion_id=row["assertion_id"],
                assertion_kind="source_local_identity",
                source=source,
                source_entity_id=f"{source}:{row['person_id']}",
                source_local_id=row["person_id"],
                source_record_id=row["source_id"],
                observation_id=row["observation_id"],
                source_key=_source_key(builder, source, row["observation_id"]),
                raw_name=row["name_raw"],
                matching_value=row["name_normalized"],
                role=row["role"],
                eligible_roles=eligible,
                institution_raw=row["affiliation_raw"] or row["university_raw"],
                institution_role=(
                    "listing_owner_affiliation"
                    if row["role"] == "listing_account_owner"
                    else "researcher_affiliation"
                ),
                local_innovation_id=row["innovation_id"],
                relationship_id=row["assertion_id"],
                source_locator=row["source_locator"],
                evidence_text=row["role_raw"],
                natural_person_status="supported_natural_person",
                quality_flags=flags,
                context={
                    "faculty_raw": row["faculty_raw"],
                    "university_raw": row["university_raw"],
                    "account_user_id": row["account_user_id"],
                    "parsing_basis": row["parsing_basis"],
                },
            )
        elif row["subject_type"] in {"organisation", "non_person_text"}:
            reviewed_exclusions = {
                "vlog การ่องเที่ยวตำบลหลักสาม อำเภอบ้านแพ้ว จังหวัดสมุทรคร",
                "มหาวิทยาลัยราชภักภูเก็ต",
                "ร้านพลอยหินอ่อน",
                "วิสาหกิจชุมชนเครือข่ายรวมใจตามรอยพ่อ",
                "หน่วยบริหารและการจัดการทุนด้านการพัฒนาระดับพื้นที่",
            }
            is_reviewed_exclusion = (
                normalize(row["subject_name"]) in reviewed_exclusions
            )
            builder.add_assertion(
                assertion_id=row["assertion_id"],
                assertion_kind="evidence_only",
                source=source,
                source_record_id=row["source_id"],
                observation_id=row["observation_id"],
                source_key=_source_key(builder, source, row["observation_id"]),
                raw_name=row["name_raw"],
                role=row["role"],
                institution_raw=row["affiliation_raw"] or row["university_raw"],
                institution_role="source_role_context",
                local_innovation_id=row["innovation_id"],
                relationship_id=row["assertion_id"],
                source_locator=row["source_locator"],
                evidence_text=row["role_raw"],
                natural_person_status="excluded_non_person",
                quality_flags=[row["subject_type"], *flags],
                admission_decision=(
                    "exclude_non_person"
                    if is_reviewed_exclusion
                    else "retain_evidence_only"
                ),
                admission_reason=(
                    "The source correction removed this audited non-person subject from the natural-person registry."
                    if is_reviewed_exclusion
                    else f"The source classifies this role subject as {row['subject_type']}."
                ),
                subject_kind=row["subject_type"],
            )


def _load_rinmp(builder: _Builder) -> None:
    source = "rinmp"
    pilot = "rinmp-v1"
    builder.load_observations(source, pilot)
    people = builder.csv(f"derived/pilots/{pilot}/people.csv")
    person_roles = builder.csv(f"derived/pilots/{pilot}/person_role_assertions.csv")
    owner_claims = builder.csv(f"derived/pilots/{pilot}/owner_name_claims.csv")
    owner_groups = builder.csv(f"derived/pilots/{pilot}/owner_groups.csv")
    owner_links = builder.csv(f"derived/pilots/{pilot}/owner_technology_links.csv")
    disagreements = builder.csv(f"derived/pilots/{pilot}/owner_name_disagreements.csv")
    narrative = builder.csv(f"derived/pilots/{pilot}/narrative_role_mentions.csv")
    innovation_profiles = builder.csv(f"derived/pilots/{pilot}/innovation_profiles.csv")

    roles_by_person: dict[str, set[str]] = defaultdict(set)
    observations_by_person: dict[str, set[str]] = defaultdict(set)
    for row in person_roles:
        observations_by_person[row["person_id"]].add(row["observation_id"])
        if row["role"] == "inventor_and_developer":
            roles_by_person[row["person_id"]].add("inventor")
    for row in people:
        builder.add_entity(
            source=source,
            local_id=row["person_id"],
            entity_kind="natural_person",
            identity_basis="source_local_identity",
            display_name=row["display_name"],
            aliases=_json_list(row["aliases_json"]),
            observation_ids=sorted(observations_by_person[row["person_id"]]),
            identity_status=row["identity_status"],
            natural_person_status="supported_natural_person",
            eligible_roles=sorted(roles_by_person[row["person_id"]]),
        )
    for row in person_roles:
        eligible = ["inventor"] if row["role"] == "inventor_and_developer" else []
        builder.add_assertion(
            assertion_id=row["role_assertion_id"],
            assertion_kind="source_local_identity",
            source=source,
            source_entity_id=f"{source}:{row['person_id']}",
            source_local_id=row["person_id"],
            source_record_id=_raw_source_id(builder, source, row["observation_id"]),
            observation_id=row["observation_id"],
            source_key=row["source_key"],
            raw_name=builder.entities[f"{source}:{row['person_id']}"]["display_name"],
            role=row["role"],
            eligible_roles=eligible,
            local_innovation_id=row["innovation_id"],
            relationship_id=row["role_assertion_id"],
            source_locator=row["source_locator"],
            evidence_text=row["evidence_text"],
            natural_person_status="supported_natural_person",
            quality_flags=[row["confidence"]],
        )

    groups = {row["owner_group_id"]: row for row in owner_groups}
    links = {row["owner_link_id"]: row for row in owner_links}
    disagreements_by_link: dict[str, list[str]] = defaultdict(list)
    for row in disagreements:
        disagreements_by_link[row["owner_link_id"]].append(row["disagreement_id"])
    profiles_by_source_id = {row["source_id"]: row for row in innovation_profiles}
    claimed_group_ids: set[str] = set()
    for row in owner_claims:
        link = links[row["owner_link_id"]]
        group = groups[row["owner_group_id"]]
        claimed_group_ids.add(row["owner_group_id"])
        quality = [row["natural_person_status"]]
        if disagreements_by_link[row["owner_link_id"]]:
            quality.append("independent_conflicting_owner_claim")
        direct_profile_claim = row["claim_origin"] == "app_profile_owner_display"
        if not direct_profile_claim:
            quality.append(
                "collector_relationship_not_confirmed_person_innovation_link"
            )
        is_named_claim = _rinmp_owner_name_claim(row["name_raw"])
        local_id = (
            stable_id(
                "owner_profile_claim",
                row["app_source_id"],
                row["name_normalized"],
                profiles_by_source_id[row["app_source_id"]]["institute_name_raw"],
            )
            if direct_profile_claim
            else row["owner_group_id"]
        )
        entity_id = ""
        if is_named_claim:
            intended_entity_id = f"{source}:{local_id}"
            if intended_entity_id not in builder.entities:
                entity_id = builder.add_entity(
                    source=source,
                    local_id=local_id,
                    entity_kind="person_claim",
                    identity_basis=(
                        "source_profile_owner_claim"
                        if direct_profile_claim
                        else "collector_observation_name_institution_claim"
                    ),
                    display_name=row["name_raw"],
                    source_ids=[row["app_source_id"]],
                    observation_ids=[
                        link["app_observation_id"]
                        if direct_profile_claim
                        else link["owner_observation_id"]
                    ],
                    identity_status=row["natural_person_status"],
                    natural_person_status="unverified_owner_name_claim",
                    quality_flags=quality,
                )
            else:
                entity_id = intended_entity_id
                entity = builder.entities[entity_id]
                entity["source_ids"] = sorted(
                    set(entity["source_ids"] + [row["app_source_id"]])
                )
                entity["observation_ids"] = sorted(
                    set(
                        entity["observation_ids"]
                        + [
                            link["app_observation_id"]
                            if direct_profile_claim
                            else link["owner_observation_id"]
                        ]
                    )
                )
                entity["quality_flags"] = sorted(set(entity["quality_flags"] + quality))
        else:
            quality.append("non_atomic_or_non_person_owner_text")
        builder.add_assertion(
            assertion_id=row["name_claim_id"],
            assertion_kind="person_claim" if is_named_claim else "evidence_only",
            source=source,
            source_entity_id=entity_id,
            source_local_id=local_id,
            source_record_id=row["app_source_id"],
            observation_id=(
                link["app_observation_id"]
                if direct_profile_claim
                else link["owner_observation_id"]
            ),
            source_key=_source_key(
                builder,
                source,
                link["app_observation_id"]
                if direct_profile_claim
                else link["owner_observation_id"],
            ),
            raw_name=row["name_raw"],
            matching_value=row["name_normalized"],
            role=row["role"],
            institution_raw=(
                profiles_by_source_id[row["app_source_id"]]["institute_name_raw"]
                if direct_profile_claim
                else group["institute_raw"]
            ),
            institution_role=(
                "innovation_institution"
                if direct_profile_claim
                else "collector_institution"
            ),
            local_innovation_id=link["innovation_id"] if direct_profile_claim else "",
            relationship_id=row["owner_link_id"],
            source_locator=row["source_locator"],
            natural_person_status=(
                "unverified_owner_name_claim" if is_named_claim else "not_established"
            ),
            quality_flags=quality,
            context={
                "claim_origin": row["claim_origin"],
                "owner_group_id": row["owner_group_id"],
                "candidate_innovation_id": link["innovation_id"],
                "owner_link_status": link["endpoint_status"],
                "disagreement_ids": disagreements_by_link[row["owner_link_id"]],
            },
            admission_decision=(
                "admit_person_claim" if is_named_claim else "retain_evidence_only"
            ),
            admission_reason=(
                "The source names a possible owner or rights holder; it does not verify a natural person or inventor role."
                if is_named_claim
                else "The owner field is non-atomic or does not support a natural-person claim."
            ),
            subject_kind="unverified_owner_name_claim",
        )

    for group_id, group in groups.items():
        if group_id in claimed_group_ids:
            continue
        is_named_claim = _rinmp_owner_name_claim(group["fullname_raw"])
        local_id = group_id
        entity_id = ""
        if is_named_claim:
            entity_id = builder.add_entity(
                source=source,
                local_id=local_id,
                entity_kind="person_claim",
                identity_basis="collector_observation_name_institution_claim",
                display_name=group["fullname_raw"],
                source_ids=[group["owner_key"]],
                observation_ids=[group["observation_id"]],
                identity_status=group["underlying_identity_status"],
                natural_person_status="unverified_owner_name_claim",
                quality_flags=["collector_group_without_technology_link"],
            )
        builder.add_assertion(
            assertion_id=stable_id("person_assertion", source, group_id, "unlinked"),
            assertion_kind="person_claim" if is_named_claim else "evidence_only",
            source=source,
            source_entity_id=entity_id,
            source_local_id=local_id if is_named_claim else "",
            source_record_id=group["owner_key"],
            observation_id=group["observation_id"],
            source_key=_source_key(builder, source, group["observation_id"]),
            raw_name=group["fullname_raw"],
            matching_value=group["name_normalized"],
            role="owner_or_rights_holder_label" if is_named_claim else "",
            institution_raw=group["institute_raw"],
            institution_role="collector_institution",
            source_locator=builder.locator(
                source, group["observation_id"], "/fullname"
            ),
            natural_person_status=(
                "unverified_owner_name_claim" if is_named_claim else "not_established"
            ),
            quality_flags=["collector_group_without_technology_link"],
            admission_decision=(
                "admit_person_claim" if is_named_claim else "retain_evidence_only"
            ),
            admission_reason="The collector name has no linked technology; it remains an unverified source claim.",
            subject_kind="unverified_owner_name_claim",
        )

    for row in narrative:
        if row["named_person_id"]:
            assertion_kind = "source_local_identity"
            entity_id = f"{source}:{row['named_person_id']}"
            local_id = row["named_person_id"]
            decision = "admit_source_local_identity"
            reason = (
                "The source cleaner links this named passage to a source-local person."
            )
            natural_status = "supported_natural_person"
        else:
            assertion_kind = "evidence_only"
            entity_id = ""
            local_id = ""
            decision = "retain_evidence_only"
            reason = (
                "The passage supplies role context without a verified named person."
            )
            natural_status = "not_established"
        builder.add_assertion(
            assertion_id=f"person_admission_{row['mention_id']}",
            assertion_kind=assertion_kind,
            source=source,
            source_entity_id=entity_id,
            source_local_id=local_id,
            source_record_id=row["mention_id"],
            observation_id=row["observation_id"],
            source_key=row["source_key"],
            raw_name="",
            role=row["role"] if row["named_person_id"] else "",
            local_innovation_id=row["innovation_id"],
            relationship_id=row["mention_id"],
            source_locator=row["source_locator"],
            evidence_text=row["evidence_text"],
            natural_person_status=natural_status,
            quality_flags=[row["eligibility_treatment"]],
            context={
                "mentioned_role": row["role"],
                "matched_terms": _json_list(row["matched_terms_json"]),
            },
            admission_decision=decision,
            admission_reason=reason,
            subject_kind="narrative_role_mention",
        )


def _load_atlocal(builder: _Builder) -> None:
    source = "atlocal"
    pilot = "atlocal-v1"
    builder.load_observations(source, pilot)
    people = builder.csv(f"derived/pilots/{pilot}/people.csv")
    evidence = builder.csv(f"derived/pilots/{pilot}/person_evidence.csv")
    relationships = builder.csv(f"derived/pilots/{pilot}/person_sellers.csv")
    relationships_by_person = {row["person_id"]: row for row in relationships}
    evidence_by_person: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in evidence:
        evidence_by_person[row["person_id"]].append(row)
    for row in people:
        person_id = row["person_id"]
        rows = evidence_by_person[person_id]
        builder.add_entity(
            source=source,
            local_id=person_id,
            entity_kind="natural_person",
            identity_basis="source_local_identity",
            display_name=row["display_name"],
            aliases=_json_list(row["aliases_json"]),
            observation_ids=[item["observation_id"] for item in rows],
            identity_status=row["identity_status"],
            natural_person_status="supported_natural_person",
            eligible_roles=["cultural_entrepreneur"],
            quality_flags=[row["name_quality"]],
        )
        for index, item in enumerate(rows):
            relationship = relationships_by_person.get(person_id, {})
            builder.add_assertion(
                assertion_id=stable_id(
                    "person_assertion", source, person_id, item["observation_id"], index
                ),
                assertion_kind="source_local_identity",
                source=source,
                source_entity_id=f"{source}:{person_id}",
                source_local_id=person_id,
                source_record_id=_raw_source_id(
                    builder, source, item["observation_id"]
                ),
                observation_id=item["observation_id"],
                source_key=item["source_key"],
                raw_name=row["display_name"],
                role=item["role"],
                eligible_roles=["cultural_entrepreneur"],
                relationship_id=relationship.get("seller_id", ""),
                source_locator=builder.locator(source, item["observation_id"]),
                evidence_text=item["evidence"],
                natural_person_status="supported_natural_person",
                context={
                    "publication_id": item["publication_id"],
                    "seller_id": relationship.get("seller_id", ""),
                    "seller_relationship": relationship.get("relationship", ""),
                },
            )


_NON_PERSON_MARKERS = (
    "มหาวิทยาลัย",
    "เทศบาล",
    "ชุมชน",
    "โรงเรียน",
    "องค์การ",
    "สำนักงาน",
    "วิสาหกิจ",
    "บริษัท",
    "ตำบล",
    "อำเภอ",
    "จังหวัด",
    "source contact",
    "ไม่ทราบ",
    "ไม่ระบุ",
)


def _atomic_name_claim(value: str) -> bool:
    """Conservative admission only; this does not establish a natural person."""
    raw = normalize(value)
    name = re.sub(r"^(?:อ\.|อาจารย์)\s*", "", matching_name(raw), flags=re.I)
    parts = name.split()
    if len(parts) != 2 or any(len(part) < 2 for part in parts):
        return False
    if any(marker in raw.casefold() for marker in _NON_PERSON_MARKERS):
        return False
    if re.search(r"[0-9๐-๙/@:(),;\n]|และ", raw):
        return False
    if any(part.isascii() and part.isupper() for part in parts):
        return False
    return bool(re.fullmatch(r"[A-Za-zก-๙.\- ]+", name))


def _rinmp_owner_name_claim(value: str) -> bool:
    """Use the source's owner-name field, rejecting clear non-person text only."""
    raw = normalize(value)
    if not raw or any(marker in raw.casefold() for marker in _NON_PERSON_MARKERS):
        return False
    if any(marker in raw for marker in ("หจก.", "บจก.", "จำกัด", " และ ", "/", "\n")):
        return False
    return bool(re.search(r"[A-Za-zก-๙]", raw))


def _load_cultural_map(builder: _Builder) -> None:
    source = "cultural_map"
    pilot = "cultural-map-v1"
    builder.load_observations(source, pilot)
    people = builder.csv(f"derived/pilots/{pilot}/people.csv")
    person_evidence = builder.csv(f"derived/pilots/{pilot}/person_role_evidence.csv")
    mapped_roles = builder.csv(
        f"derived/pilots/{pilot}/mapped_person_role_evidence.csv"
    )
    recreation_members = builder.csv(
        f"derived/pilots/{pilot}/recreation_team_members.csv"
    )
    team_profiles = builder.csv(f"derived/pilots/{pilot}/team_profiles.csv")
    raw_path = "data/f2_culturalmap_university/20260820T142533Z/map_inspiration.json"
    raw_records = builder.json(raw_path)["data"]["records"]
    source_config = builder.json("config/cross_source_people/source_cultural_map.json")
    reviewed_recorder_aliases = source_config["reviewed_recorder_aliases"]
    retained_incomplete_claims = {
        (
            row["account_identifier"].casefold(),
            normalize(row["raw_name"]),
            normalize(row["institution"]),
        )
        for row in source_config["retained_incomplete_recorder_claims"]
    }

    evidence_by_person: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in person_evidence:
        evidence_by_person[row["person_id"]].append(row)
    for row in people:
        person_id = row["person_id"]
        rows = evidence_by_person[person_id]
        builder.add_entity(
            source=source,
            local_id=person_id,
            entity_kind="natural_person",
            identity_basis="source_local_identity",
            display_name=row["display_name"],
            aliases=_json_list(row["aliases_json"]),
            observation_ids=[item["observation_id"] for item in rows],
            identity_status=row["identity_status"],
            natural_person_status="supported_natural_person",
            eligible_roles=["cultural_entrepreneur"],
            quality_flags=[row["eligibility"]],
        )
        for item in rows:
            builder.add_assertion(
                assertion_id=item["evidence_id"],
                assertion_kind="source_local_identity",
                source=source,
                source_entity_id=f"{source}:{person_id}",
                source_local_id=person_id,
                source_record_id=_raw_source_id(
                    builder, source, item["observation_id"]
                ),
                observation_id=item["observation_id"],
                source_key=item["source_key"],
                raw_name=row["display_name"],
                role=item["role"],
                eligible_roles=["cultural_entrepreneur"],
                relationship_id=item["seller_id"],
                source_locator=builder.locator(source, item["observation_id"]),
                evidence_text=item["evidence_passage"],
                natural_person_status="supported_natural_person",
                quality_flags=[item["eligibility"]],
                context={
                    "seller_id": item["seller_id"],
                    "offering_id": item["offering_id"],
                },
            )

    account_names: dict[tuple[str, str], set[str]] = defaultdict(set)
    recorder_entity_ids_by_account: dict[tuple[str, str], set[str]] = defaultdict(set)
    raw_recorder_by_observation: dict[str, dict] = {}
    for observation in builder.observations[source].values():
        if observation["dataset"] != "map_inspiration":
            continue
        raw = raw_records[int(observation["row_locator"].split("/")[-1])]
        recorder = raw.get("data", {}).get("people", {}).get("recorder") or {}
        raw_recorder_by_observation[observation["observation_id"]] = recorder
        account_key = (
            normalize(recorder.get("account_identifier_type", "")),
            normalize(recorder.get("account_identifier", "")).casefold(),
        )
        recorder_name = normalize(recorder.get("name", ""))
        if account_key[1] and recorder_name:
            alias = reviewed_recorder_aliases.get(account_key[1])
            canonical = (
                alias["canonical_matching_name"]
                if alias and recorder_name in alias["raw_names"]
                else matching_name(recorder_name)
            )
            account_names[account_key].add(canonical.casefold())
            institution = normalize(
                (recorder.get("institution") or {}).get("name_th", "")
            )
            reviewed_incomplete = (
                account_key[1],
                recorder_name,
                institution,
            ) in retained_incomplete_claims
            if _atomic_name_claim(recorder_name) or reviewed_incomplete:
                local_id = stable_id(
                    "recorder_claim",
                    account_key[0],
                    account_key[1],
                    canonical.casefold(),
                    institution,
                )
                recorder_entity_ids_by_account[account_key].add(f"{source}:{local_id}")

    known_cultural_people = {
        entity_id: entity["matching_names"]
        for entity_id, entity in builder.entities.items()
        if entity["source"] == source
        and entity["identity_basis"] == "source_local_identity"
    }

    for row in mapped_roles:
        observation_id = row["observation_id"]
        raw_name = row["person_or_institution_raw"]
        preferred_suffix = {
            "recorder": "/data/people/recorder",
            "informant": "/data/people/informants_raw",
            "contact": "/data/people/contact_raw",
        }[row["role"]]
        recorder_context = raw_recorder_by_observation.get(observation_id, {})
        raw_people = (
            raw_records[
                int(
                    builder.observations[source][observation_id]["row_locator"].split(
                        "/"
                    )[-1]
                )
            ]
            .get("data", {})
            .get("people", {})
        )
        raw_key = preferred_suffix.rsplit("/", 1)[-1]
        locator_suffix = preferred_suffix if raw_key in raw_people else "/data/people"
        locator = builder.locator(source, observation_id, locator_suffix)
        account_identifier = ""
        account_type = ""
        institution = ""
        conflict = False
        if row["role"] == "recorder":
            recorder = recorder_context
            account_identifier = normalize(recorder.get("account_identifier", ""))
            account_type = normalize(recorder.get("account_identifier_type", ""))
            institution = normalize(
                (recorder.get("institution") or {}).get("name_th", "")
            )
            conflict = (
                len(account_names[(account_type, account_identifier.casefold())]) > 1
            )

        flags = [row["eligibility"]]
        if conflict:
            flags.append("shared_account_has_conflicting_names")
        is_reviewed_incomplete_claim = (
            account_identifier.casefold(),
            normalize(raw_name),
            institution,
        ) in retained_incomplete_claims
        is_person_claim = _atomic_name_claim(raw_name) or is_reviewed_incomplete_claim
        if is_person_claim:
            if len(matching_name(raw_name).split()) < 2:
                flags.append("incomplete_name")
            if row["role"] == "recorder" and account_identifier:
                alias = reviewed_recorder_aliases.get(account_identifier.casefold())
                canonical_name = (
                    alias["canonical_matching_name"]
                    if alias and normalize(raw_name) in alias["raw_names"]
                    else matching_name(raw_name)
                )
                local_id = stable_id(
                    "recorder_claim",
                    account_type,
                    account_identifier.casefold(),
                    canonical_name.casefold(),
                    institution,
                )
                identity_status = "account_name_institution_partition"
                basis = "account_name_institution_partition"
            else:
                local_id = f"claim_{row['evidence_id']}"
                identity_status = "assertion_grain_named_claim"
                basis = "assertion_grain_claim"
            entity_id = f"{source}:{local_id}"
            if entity_id not in builder.entities:
                builder.add_entity(
                    source=source,
                    local_id=local_id,
                    entity_kind="person_claim",
                    identity_basis=basis,
                    display_name=raw_name,
                    source_ids=[_raw_source_id(builder, source, observation_id)],
                    observation_ids=[observation_id],
                    identity_status=identity_status,
                    natural_person_status="unverified_named_person_claim",
                    quality_flags=flags,
                )
            else:
                entity = builder.entities[entity_id]
                entity["source_ids"] = sorted(
                    set(
                        entity["source_ids"]
                        + [_raw_source_id(builder, source, observation_id)]
                    )
                )
                entity["observation_ids"] = sorted(
                    set(entity["observation_ids"] + [observation_id])
                )
                entity["quality_flags"] = sorted(set(entity["quality_flags"] + flags))
                entity["aliases"] = sorted(
                    set(entity["aliases"] + [normalize(raw_name)])
                )
                entity["matching_names"] = sorted(
                    set(entity["matching_names"] + [matching_name(raw_name).casefold()])
                )
            kind = "person_claim"
            decision = "admit_person_claim"
            reason = (
                "The recorder claim is partitioned by the supplied account, name, and institution."
                if account_identifier
                else "The source field contains one atomic name; the claim stays at assertion grain."
            )
            natural_status = "unverified_named_person_claim"
        else:
            entity_id = ""
            local_id = ""
            kind = "evidence_only"
            decision = "retain_evidence_only"
            reason = (
                "The field is empty, institutional, contact-like, or non-atomic text."
            )
            natural_status = "not_established"
            flags.append("non_atomic_or_non_person_text")
        raw_name_folded = normalize(raw_name).casefold()
        known_source_entity_ids = sorted(
            entity_id
            for entity_id, names in known_cultural_people.items()
            if any(name and name in raw_name_folded for name in names)
        )
        conflicting_source_entity_ids = sorted(
            recorder_entity_ids_by_account[
                (account_type, account_identifier.casefold())
            ]
            - ({entity_id} if entity_id else set())
        )
        builder.add_assertion(
            assertion_id=f"person_admission_{row['evidence_id']}",
            assertion_kind=kind,
            source=source,
            source_entity_id=entity_id,
            source_local_id=local_id,
            source_record_id=row["evidence_id"],
            observation_id=observation_id,
            source_key=row["source_key"],
            raw_name=raw_name,
            role=row["role"] if kind == "person_claim" else "",
            institution_raw=institution,
            institution_role="recorder_affiliation" if institution else "",
            relationship_id=row["subject_id"],
            source_locator=locator,
            evidence_text=row["evidence"],
            natural_person_status=natural_status,
            quality_flags=flags,
            context={
                "mentioned_role": row["role"],
                "account_identifier": account_identifier,
                "account_identifier_type": account_type,
                "account_partition_basis": "account+name+institution"
                if entity_id and account_identifier
                else "",
                "known_source_entity_ids": known_source_entity_ids,
                "conflicting_source_entity_ids": conflicting_source_entity_ids,
            },
            admission_decision=decision,
            admission_reason=reason,
            subject_kind="mapped_person_or_institution_field",
        )

    for row in recreation_members:
        is_named_claim = _atomic_name_claim(row["member_name_raw"])
        local_id = f"claim_{row['member_id']}" if is_named_claim else ""
        entity_id = ""
        if is_named_claim:
            entity_id = builder.add_entity(
                source=source,
                local_id=local_id,
                entity_kind="person_claim",
                identity_basis="assertion_grain_claim",
                display_name=row["member_name_raw"],
                source_ids=[_raw_source_id(builder, source, row["observation_id"])],
                observation_ids=[row["observation_id"]],
                identity_status="structured_team_member_claim",
                natural_person_status="unverified_named_person_claim",
                quality_flags=[
                    row["kpi_eligibility"],
                    "no_person_affiliation_supplied",
                ],
            )
        builder.add_assertion(
            assertion_id=f"person_admission_{row['member_id']}",
            assertion_kind="person_claim" if is_named_claim else "evidence_only",
            source=source,
            source_entity_id=entity_id,
            source_local_id=local_id,
            source_record_id=row["member_id"],
            observation_id=row["observation_id"],
            source_key=row["source_key"],
            raw_name=row["member_name_raw"],
            role=row["role"] if is_named_claim else "",
            relationship_id=row["recreation_id"],
            source_locator=builder.locator(
                source,
                row["observation_id"],
                f"/data/team_members/{row['member_ordinal']}",
            ),
            natural_person_status=(
                "unverified_named_person_claim" if is_named_claim else "not_established"
            ),
            quality_flags=[
                row["kpi_eligibility"],
                "no_person_affiliation_supplied",
                *([] if is_named_claim else ["non_atomic_or_non_person_text"]),
            ],
            context={
                "member_ordinal": row["member_ordinal"],
                "mentioned_role": row["role"],
            },
            admission_decision=(
                "admit_person_claim" if is_named_claim else "retain_evidence_only"
            ),
            admission_reason=(
                "The source supplies a distinct named team-member row; repeated names remain separate claims."
                if is_named_claim
                else "The team-member field is a group, organisation, or non-atomic text."
            ),
            subject_kind="recreation_team_member",
        )

    for row in team_profiles:
        is_named_claim = _atomic_name_claim(row["profile_title"])
        team_matching_name = re.sub(
            r"^(?:อ\.|อาจารย์)\s*", "", matching_name(row["profile_title"]), flags=re.I
        ).casefold()
        overlap_entity_ids = sorted(
            entity_id
            for entity_id, entity in builder.entities.items()
            if entity["source"] == source
            and entity["source_local_id"] != f"claim_{row['team_id']}"
            and team_matching_name in entity["matching_names"]
        )
        team_flags = [
            "site_team_provenance_only",
            *(["unresolved_existing_name_overlap"] if overlap_entity_ids else []),
            *([] if is_named_claim else ["non_atomic_or_non_person_text"]),
        ]
        local_id = f"claim_{row['team_id']}" if is_named_claim else ""
        entity_id = ""
        if is_named_claim:
            entity_id = builder.add_entity(
                source=source,
                local_id=local_id,
                entity_kind="person_claim",
                identity_basis="assertion_grain_claim",
                display_name=row["profile_title"],
                aliases=[team_matching_name],
                source_ids=[row["external_id"]],
                observation_ids=[row["observation_id"]],
                identity_status=row["status"],
                natural_person_status="unverified_named_person_claim",
                quality_flags=team_flags,
            )
        builder.add_assertion(
            assertion_id=stable_id("person_assertion", source, row["team_id"]),
            assertion_kind="person_claim" if is_named_claim else "evidence_only",
            source=source,
            source_entity_id=entity_id,
            source_local_id=local_id,
            source_record_id=row["external_id"],
            observation_id=row["observation_id"],
            source_key=row["source_key"],
            raw_name=row["profile_title"],
            role="site_team_member" if is_named_claim else "",
            institution_raw=row["group_raw"],
            institution_role="site_team_group",
            source_locator=builder.locator(source, row["observation_id"]),
            natural_person_status=(
                "unverified_named_person_claim" if is_named_claim else "not_established"
            ),
            quality_flags=team_flags,
            context={
                "source_url": row["source_url"],
                "mentioned_role": "site_team_member",
                "known_source_entity_ids": overlap_entity_ids,
            },
            admission_decision=(
                "admit_person_claim" if is_named_claim else "retain_evidence_only"
            ),
            admission_reason=(
                "The site supplies a named team profile; it does not establish KPI eligibility."
                if is_named_claim
                else "The team profile title does not support an atomic person claim."
            ),
            subject_kind="site_team_profile",
        )


def load_person_sources(
    source_tables: dict, reviews: dict, raw_inputs: dict, innovation_tables: dict
) -> PersonSources:
    """Adapt current corrected source outputs without filesystem or prior-output reads."""
    builder = _Builder(source_tables, reviews, raw_inputs, innovation_tables)
    _load_icommunity(builder)
    _load_pmua(builder)
    _load_mru(builder)
    _load_rinmp(builder)
    _load_atlocal(builder)
    _load_cultural_map(builder)
    return builder.finish()
