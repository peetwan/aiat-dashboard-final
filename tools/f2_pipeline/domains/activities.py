"""Reviewed activity occurrences and their publications, without programme coverage."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..common import PipelineError
from .raw_inputs import SOURCE_IDS, observation_uri, resolve_evidence

SOURCE_ALIASES = {
    "icommunity-v1": "icommunity",
    "atlocal-v1": "atlocal",
    "cultural-map-v1": "cultural_map",
}


def stable_id(prefix, *parts):
    # Preserve the accepted activity namespace's unit-separator encoding.
    return f"{prefix}_{hashlib.sha256(chr(31).join(parts).encode()).hexdigest()[:20]}"


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


TABLE_COLUMNS = {
    "global_activities": [
        "global_activity_id",
        "source",
        "source_activity_id",
        "source_key",
        "source_publication_id",
        "observation_id",
        "name",
        "start_date",
        "end_date",
        "status",
        "identity_status",
        "cross_source_status",
        "source_details_json",
    ],
    "activity_crosswalk": [
        "global_activity_id",
        "source",
        "source_activity_id",
        "source_key",
        "observation_id",
        "identity_status",
        "cross_source_status",
    ],
    "publications": [
        "source_publication_id",
        "source",
        "source_key",
        "observation_id",
        "global_activity_id",
        "title",
        "text",
        "published_at",
        "source_url",
        "publication_role",
        "raw_locator",
        "source_details_json",
    ],
    "activity_publication_links": [
        "source_publication_id",
        "global_activity_id",
        "source",
        "link_status",
        "parent_or_session_role",
        "reason",
    ],
    "activity_dates": [
        "date_assertion_id",
        "global_activity_id",
        "source",
        "observation_id",
        "date_role",
        "raw_value",
        "parsed_start_date",
        "parsed_end_date",
        "parse_status",
        "date_conflict",
        "source_locator",
        "raw_locator",
    ],
    "activity_venues": [
        "venue_assertion_id",
        "global_activity_id",
        "source",
        "observation_id",
        "location_name_raw",
        "country",
        "province_normalized",
        "province_code",
        "location_role",
        "coverage_eligibility",
        "geography_status",
        "raw_locator",
        "source_details_json",
    ],
    "activity_sessions": [
        "session_id",
        "global_activity_id",
        "source",
        "source_publication_id",
        "observation_id",
        "source_key",
        "session_label",
        "start_date",
        "end_date",
        "date_evidence_json",
        "status",
        "raw_locator",
    ],
    "activity_sections": [
        "section_id",
        "global_activity_id",
        "source",
        "source_publication_id",
        "observation_id",
        "line_index",
        "text",
        "attribution",
        "raw_locator",
    ],
    "activity_media": [
        "media_id",
        "global_activity_id",
        "observation_id",
        "source_key",
        "media_kind",
        "ordinal",
        "url_or_value",
        "caption",
        "status",
        "source_locator",
        "raw_locator",
    ],
    "activity_narrative_evidence": [
        "evidence_id",
        "global_activity_id",
        "observation_id",
        "source_key",
        "field_name",
        "text",
        "source_locator",
        "raw_locator",
    ],
    "activity_identity_decisions": [
        "review_id",
        "decision",
        "reason",
        "source_members_json",
        "global_members_json",
        "application",
    ],
    "source_quality_treatments": ["source", "source_key", "treatment", "reason"],
    "measure_results": ["measure", "value", "scope", "status"],
    "measure_contributions": [
        "measure",
        "entity_id",
        "source",
        "province_code",
        "contributor_ids_json",
        "reason",
    ],
}


class Activities:
    def __init__(self, source_tables, review, raw_inputs, geography):
        self.sources = source_tables
        self.review = review
        self.raw_inputs = raw_inputs
        self.observations = {}
        self.raw_checks = set()
        self.publication_inputs = {}
        self.provinces = {
            str(row["provinceCode"]): row["provinceNameTh"]
            for row in geography.provinces
        }
        self.province_codes = {name: code for code, name in self.provinces.items()}
        self.sessions, self.sections, self.media, self.narratives = [], [], [], []

    def table(self, source, name):
        source_id = SOURCE_IDS[SOURCE_ALIASES[source]]
        if name not in self.sources[source_id]:
            raise PipelineError(f"Missing activity source table: {source}/{name}")
        return [dict(row) for row in self.sources[source_id][name]]

    def observation_index(self, source):
        if source not in self.observations:
            rows = self.table(source, "source_observations")
            self.observations[source] = {row["observation_id"]: row for row in rows}
            if len(rows) != len(self.observations[source]):
                raise PipelineError("Duplicate activity source observation")
        return self.observations[source]

    def resolve_raw(self, source, observation_id, locator=""):
        observation = self.observation_index(source).get(observation_id)
        if observation is None:
            raise PipelineError("Activity evidence observation is absent")
        source_id = SOURCE_IDS[SOURCE_ALIASES[source]]
        original = observation_uri(self.raw_inputs, source_id, observation)
        if locator.startswith("evidence://"):
            uri = locator
            if not uri.startswith(f"evidence://{source_id}/"):
                raise PipelineError("Activity evidence belongs to another source")
        elif locator:
            if "#" in locator:
                raise PipelineError("Activity review still uses an unrebased raw path")
            base, _, original_pointer = original.partition("#")
            pointer = locator.lstrip("/")
            if pointer != original_pointer and not pointer.startswith(
                original_pointer.rstrip("/") + "/"
            ):
                pointer = original_pointer.rstrip("/") + "/" + pointer
            uri = base + "#" + pointer
        else:
            uri = original
        resolve_evidence(self.raw_inputs, uri)
        self.raw_checks.add(uri)
        return uri

    def source_activity_data(
        self,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        activities: list[dict[str, Any]] = []
        publications: list[dict[str, Any]] = []
        publication_links: list[dict[str, Any]] = []
        dates: list[dict[str, Any]] = []
        venues: list[dict[str, Any]] = []
        source_key_to_global: dict[tuple[str, str], str] = {}

        def add_activity(
            source: str,
            local_id: str,
            publication_id: str,
            observation_id: str,
            source_key: str,
            name: str,
            start: str,
            end: str,
            status: str,
            identity_status: str,
            details: dict[str, str],
        ) -> str:
            global_id = stable_id("activity", source, local_id)
            if (source, source_key) in source_key_to_global:
                raise ValueError(
                    f"Duplicate activity source key: {source}:{source_key}"
                )
            source_key_to_global[source, source_key] = global_id
            self.resolve_raw(source, observation_id)
            activities.append(
                {
                    "global_activity_id": global_id,
                    "source": source,
                    "source_activity_id": local_id,
                    "source_key": source_key,
                    "source_publication_id": publication_id,
                    "observation_id": observation_id,
                    "name": name,
                    "start_date": start,
                    "end_date": end,
                    "status": status,
                    "identity_status": identity_status,
                    "cross_source_status": "source_local_identity_no_supported_merge",
                    "source_details_json": json_text(details),
                }
            )
            return global_id

        # iCommunity: activity and publication identities are one-to-one, but the programme
        # background page deliberately remains a publication with no occurrence.
        source = "icommunity-v1"
        icom_pubs = self.table(source, "publications")
        icom_activities = self.table(source, "activities")
        icom_venues = self.table(source, "activity_venue_evidence")
        by_pub = {row["publication_id"]: row for row in icom_pubs}
        expected = set(self.review["activity_source_keys"]["icommunity"])
        actual = {by_pub[row["publication_id"]]["source_id"] for row in icom_activities}
        if actual != expected:
            raise ValueError("iCommunity reviewed activity membership changed")
        activity_by_pub: dict[str, str] = {}
        for row in icom_activities:
            pub = by_pub[row["publication_id"]]
            source_key = pub["source_id"]
            global_id = add_activity(
                source,
                row["activity_id"],
                row["publication_id"],
                row["observation_id"],
                source_key,
                row["name"],
                row["start_date"],
                row["end_date"],
                row["status"],
                row["identity_status"],
                row,
            )
            activity_by_pub[row["publication_id"]] = global_id
            dates.append(
                {
                    "date_assertion_id": stable_id(
                        "activity_date", global_id, "source_activity_register"
                    ),
                    "global_activity_id": global_id,
                    "source": source,
                    "observation_id": row["observation_id"],
                    "date_role": "source_activity_register",
                    "raw_value": row["evidence_excerpt"],
                    "parsed_start_date": row["start_date"],
                    "parsed_end_date": row["end_date"],
                    "parse_status": "reviewed_source_activity",
                    "date_conflict": "",
                    "source_locator": self.resolve_raw(
                        source, row["observation_id"], "content_html"
                    ),
                }
            )
        reviewed_venue_by_activity = {row["activity_id"]: row for row in icom_venues}
        if not reviewed_venue_by_activity or any(
            activity_id not in {row["activity_id"] for row in icom_activities}
            for activity_id in reviewed_venue_by_activity
        ):
            raise ValueError("iCommunity venue review cites an unknown activity")
        online_source_keys = {
            item["source_key"]
            for item in self.review["source_quality"]
            if item["source"] == "icommunity"
            and item["treatment"] == "online_no_physical_province"
        }
        for activity in icom_activities:
            global_id = activity_by_pub[activity["publication_id"]]
            review_venue = reviewed_venue_by_activity.get(activity["activity_id"])
            source_key = by_pub[activity["publication_id"]]["source_id"]
            if review_venue:
                raw_locator = self.resolve_raw(
                    source, activity["observation_id"], review_venue["raw_locator"]
                )
                venues.append(
                    {
                        "venue_assertion_id": stable_id(
                            "activity_venue",
                            global_id,
                            review_venue["venue_evidence_id"],
                        ),
                        "global_activity_id": global_id,
                        "source": source,
                        "observation_id": activity["observation_id"],
                        "location_name_raw": review_venue["venue_name_raw"],
                        "country": "Thailand",
                        "province_normalized": review_venue["province_raw"],
                        "province_code": self.province_codes[
                            review_venue["province_raw"]
                        ],
                        "location_role": review_venue["location_role"],
                        "coverage_eligibility": "qualifying_explicit_activity_venue",
                        "geography_status": "resolved_thai_province",
                        "raw_locator": raw_locator,
                        "source_details_json": json_text(review_venue),
                    }
                )
            elif activity["province"]:
                venues.append(
                    {
                        "venue_assertion_id": stable_id(
                            "activity_venue", global_id, "source_activity_province"
                        ),
                        "global_activity_id": global_id,
                        "source": source,
                        "observation_id": activity["observation_id"],
                        "location_name_raw": activity["province"],
                        "country": "Thailand",
                        "province_normalized": activity["province"],
                        "province_code": self.province_codes[activity["province"]],
                        "location_role": "reported_activity_province",
                        "coverage_eligibility": "qualifying_explicit_activity_venue",
                        "geography_status": "resolved_thai_province",
                        "raw_locator": self.resolve_raw(
                            source, activity["observation_id"], "content_html"
                        ),
                        "source_details_json": "",
                    }
                )
            else:
                status = (
                    "online_no_physical_province"
                    if source_key in online_source_keys
                    else "unknown_venue"
                )
                venues.append(
                    {
                        "venue_assertion_id": stable_id(
                            "activity_venue", global_id, status
                        ),
                        "global_activity_id": global_id,
                        "source": source,
                        "observation_id": activity["observation_id"],
                        "location_name_raw": "",
                        "country": "",
                        "province_normalized": "",
                        "province_code": "",
                        "location_role": "online_delivery"
                        if status.startswith("online")
                        else "venue_not_stated",
                        "coverage_eligibility": "qualifying_unknown_province",
                        "geography_status": status,
                        "raw_locator": self.resolve_raw(
                            source, activity["observation_id"], "content_html"
                        ),
                        "source_details_json": "",
                    }
                )
        for pub in icom_pubs:
            self.publication_inputs[source, pub["publication_id"]] = pub
            global_id = activity_by_pub.get(pub["publication_id"], "")
            publications.append(
                {
                    "source_publication_id": pub["publication_id"],
                    "source": source,
                    "source_key": pub["source_id"],
                    "observation_id": pub["observation_id"],
                    "global_activity_id": global_id,
                    "title": pub["title"],
                    "text": pub["content"],
                    "published_at": pub["published_at"],
                    "source_url": pub["source_url"],
                    "publication_role": "activity_publication"
                    if global_id
                    else "programme_context",
                    "raw_locator": self.resolve_raw(source, pub["observation_id"]),
                    "source_details_json": json_text(pub),
                }
            )
            publication_links.append(
                {
                    "source_publication_id": pub["publication_id"],
                    "global_activity_id": global_id,
                    "source": source,
                    "link_status": "source_reported_activity_link"
                    if global_id
                    else "no_identifiable_activity",
                    "parent_or_session_role": "publication",
                    "reason": "Source activity register"
                    if global_id
                    else "Programme background page",
                }
            )

        # AtLocal retains every publication and every section; only its eight reviewed festival rows
        # are activities.
        source = "atlocal-v1"
        atl_pubs = self.table(source, "publications")
        atl_activities = self.table(source, "activities")
        atl_sections = self.table(source, "activity_sections")
        by_pub = {row["publication_id"]: row for row in atl_pubs}
        expected = set(self.review["activity_source_keys"]["atlocal"])
        actual = {by_pub[row["publication_id"]]["source_key"] for row in atl_activities}
        if actual != expected:
            raise ValueError("AtLocal reviewed activity membership changed")
        activity_by_pub = {}
        for row in atl_activities:
            pub = by_pub[row["publication_id"]]
            global_id = add_activity(
                source,
                row["activity_id"],
                row["publication_id"],
                row["observation_id"],
                pub["source_key"],
                row["name"],
                row["start_date"],
                row["end_date"],
                row["status"],
                row["identity_status"],
                row,
            )
            activity_by_pub[row["publication_id"]] = global_id
            dates.append(
                {
                    "date_assertion_id": stable_id(
                        "activity_date", global_id, "source_activity_register"
                    ),
                    "global_activity_id": global_id,
                    "source": source,
                    "observation_id": row["observation_id"],
                    "date_role": "source_activity_register",
                    "raw_value": row["date_evidence_json"],
                    "parsed_start_date": row["start_date"],
                    "parsed_end_date": row["end_date"],
                    "parse_status": "reviewed_source_activity",
                    "date_conflict": "source_date_conflict"
                    if pub["source_key"] == "festivals:phanatnikhom/event1"
                    else "",
                    "source_locator": self.resolve_raw(source, row["observation_id"]),
                }
            )
            venues.append(
                {
                    "venue_assertion_id": stable_id(
                        "activity_venue", global_id, "source_activity_province"
                    ),
                    "global_activity_id": global_id,
                    "source": source,
                    "observation_id": row["observation_id"],
                    "location_name_raw": row["province"],
                    "country": "Thailand",
                    "province_normalized": row["province"],
                    "province_code": self.province_codes[row["province"]],
                    "location_role": "source_activity_locality",
                    "coverage_eligibility": "qualifying_explicit_activity_venue",
                    "geography_status": "resolved_thai_province",
                    "raw_locator": self.resolve_raw(source, row["observation_id"]),
                    "source_details_json": "",
                }
            )
        for pub in atl_pubs:
            self.publication_inputs[source, pub["publication_id"]] = pub
            global_id = activity_by_pub.get(pub["publication_id"], "")
            publications.append(
                {
                    "source_publication_id": pub["publication_id"],
                    "source": source,
                    "source_key": pub["source_key"],
                    "observation_id": pub["observation_id"],
                    "global_activity_id": global_id,
                    "title": pub["title"],
                    "text": pub["content"],
                    "published_at": pub["published_at"],
                    "source_url": pub["source_url"],
                    "publication_role": "activity_publication"
                    if global_id
                    else "context_or_quality_review",
                    "raw_locator": self.resolve_raw(source, pub["observation_id"]),
                    "source_details_json": json_text(pub),
                }
            )
            publication_links.append(
                {
                    "source_publication_id": pub["publication_id"],
                    "global_activity_id": global_id,
                    "source": source,
                    "link_status": "source_reported_activity_link"
                    if global_id
                    else "no_identifiable_activity",
                    "parent_or_session_role": "publication",
                    "reason": "Reviewed festival register"
                    if global_id
                    else "Retained source publication",
                }
            )
        self.sections = [
            {
                "section_id": stable_id("activity_section", row["section_id"]),
                "global_activity_id": activity_by_pub[row["publication_id"]],
                "source": source,
                "source_publication_id": row["publication_id"],
                "observation_id": row["observation_id"],
                "line_index": row["line_index"],
                "text": row["text"],
                "attribution": row["attribution"],
                "raw_locator": self.resolve_raw(source, row["observation_id"]),
            }
            for row in atl_sections
        ]

        # Cultural Map has one parent (G-340), six sessions, and 29 other occurrences.
        source = "cultural-map-v1"
        cm_occurrences = self.table(source, "activity_occurrences")
        cm_pubs = self.table(source, "activity_publications")
        cm_dates = self.table(source, "activity_dates")
        cm_venues = self.table(source, "activity_locations")
        cm_sessions = self.table(source, "activity_sessions")
        cm_media = self.table(source, "activity_media")
        cm_narratives = self.table(source, "activity_narrative_evidence")
        pub_by_id = {row["publication_id"]: row for row in cm_pubs}
        expected = set(self.review["activity_source_keys"]["cultural_map"])
        actual = {
            pub_by_id[row["publication_id"]]["external_id"] for row in cm_occurrences
        }
        if actual != expected:
            raise ValueError("Cultural Map reviewed activity membership changed")
        activity_by_local: dict[str, str] = {}
        for row in cm_occurrences:
            pub = pub_by_id[row["publication_id"]]
            global_id = add_activity(
                source,
                row["activity_id"],
                row["publication_id"],
                row["observation_id"],
                pub["external_id"],
                row["name"],
                row["start_date"],
                row["end_date"],
                row["status"],
                row["identity_status"],
                row,
            )
            activity_by_local[row["activity_id"]] = global_id
        cm_key_to_global = {
            pub["external_id"]: activity_by_local.get(pub["activity_id"], "")
            for pub in cm_pubs
        }

        def materialize_evidence(rows, table):
            materialized = []
            for row in rows:
                enriched = {
                    **row,
                    "global_activity_id": cm_key_to_global.get(
                        row["source_key"].split(":", 1)[1], ""
                    ),
                    "raw_locator": self.resolve_raw(
                        source, row["observation_id"], row["source_locator"]
                    ),
                }
                materialized.append(
                    {
                        column: enriched.get(column, "")
                        for column in TABLE_COLUMNS[table]
                    }
                )
            return materialized

        self.media = materialize_evidence(cm_media, "activity_media")
        self.narratives = materialize_evidence(
            cm_narratives, "activity_narrative_evidence"
        )

        for pub in cm_pubs:
            self.publication_inputs[source, pub["publication_id"]] = pub
            global_id = activity_by_local.get(pub["activity_id"], "")
            role = pub["disposition"]
            publications.append(
                {
                    "source_publication_id": pub["publication_id"],
                    "source": source,
                    "source_key": pub["external_id"],
                    "observation_id": pub["observation_id"],
                    "global_activity_id": global_id,
                    "title": pub["title"],
                    "text": pub["description"],
                    "published_at": "",
                    "source_url": pub["source_url"],
                    "publication_role": role,
                    "raw_locator": self.resolve_raw(source, pub["observation_id"]),
                    "source_details_json": json_text(pub),
                }
            )
            publication_links.append(
                {
                    "source_publication_id": pub["publication_id"],
                    "global_activity_id": global_id,
                    "source": source,
                    "link_status": "source_reported_activity_link"
                    if global_id
                    else "context_only",
                    "parent_or_session_role": role,
                    "reason": pub["parent_key"] or "No identifiable occurrence",
                }
            )
        for row in cm_dates:
            global_id = activity_by_local.get(row["activity_id"], "")
            raw_locator = (
                self.resolve_raw(source, row["observation_id"], row["source_locator"])
                if row["source_locator"].startswith("data/")
                else self.resolve_raw(source, row["observation_id"])
            )
            dates.append(
                {
                    "date_assertion_id": stable_id(
                        "activity_date", row["date_assertion_id"]
                    ),
                    "global_activity_id": global_id,
                    "source": source,
                    "observation_id": row["observation_id"],
                    "date_role": row["date_role"],
                    "raw_value": row["raw_value"],
                    "parsed_start_date": row["parsed_start_date"],
                    "parsed_end_date": row["parsed_end_date"],
                    "parse_status": row["parse_status"],
                    "date_conflict": row["date_conflict"],
                    "source_locator": row["source_locator"],
                    "raw_locator": raw_locator,
                }
            )
        for row in cm_venues:
            global_id = activity_by_local.get(row["activity_id"], "")
            raw_locator = self.resolve_raw(source, row["observation_id"])
            status = row["status"]
            venues.append(
                {
                    "venue_assertion_id": stable_id(
                        "activity_venue", row["location_id"]
                    ),
                    "global_activity_id": global_id,
                    "source": source,
                    "observation_id": row["observation_id"],
                    "location_name_raw": row["location_name_raw"],
                    "country": row["country"],
                    "province_normalized": row["province_normalized"],
                    "province_code": row["province_code"],
                    "location_role": row["location_role"],
                    "coverage_eligibility": "qualifying_explicit_activity_venue"
                    if row["qualifies_target_province"] == "True"
                    else "non_thai_or_unresolved",
                    "geography_status": status,
                    "raw_locator": raw_locator,
                    "source_details_json": json_text(row),
                }
            )
        self.sessions = [
            {
                "session_id": stable_id("activity_session", row["session_id"]),
                "global_activity_id": activity_by_local[row["activity_id"]],
                "source": source,
                "source_publication_id": row["publication_id"],
                "observation_id": row["observation_id"],
                "source_key": row["source_key"],
                "session_label": row["session_label"],
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "date_evidence_json": row["date_evidence_json"],
                "status": row["status"],
                "raw_locator": self.resolve_raw(source, row["observation_id"]),
            }
            for row in cm_sessions
        ]
        if {row["source_key"].split(":", 1)[1] for row in self.sessions} != set(
            self.review["session_publication_keys"]
        ):
            raise ValueError("Cultural Map session membership changed")

        activity_ids_with_venue = {row["global_activity_id"] for row in venues}
        for activity in activities:
            if activity["global_activity_id"] not in activity_ids_with_venue:
                venues.append(
                    {
                        "venue_assertion_id": stable_id(
                            "activity_venue",
                            activity["global_activity_id"],
                            "venue_not_stated",
                        ),
                        "global_activity_id": activity["global_activity_id"],
                        "source": activity["source"],
                        "observation_id": activity["observation_id"],
                        "location_name_raw": "",
                        "country": "",
                        "province_normalized": "",
                        "province_code": "",
                        "location_role": "venue_not_stated",
                        "coverage_eligibility": "qualifying_unknown_province",
                        "geography_status": "unknown_venue",
                        "raw_locator": self.resolve_raw(
                            activity["source"], activity["observation_id"]
                        ),
                        "source_details_json": "",
                    }
                )

        self.source_key_to_global = source_key_to_global
        self.cm_key_to_global = cm_key_to_global
        return activities, publications, publication_links, dates, venues


def build_tables(source_tables, review_inputs, raw_inputs, geography):
    review = review_inputs["cross_source_activities_coverage/reviewed_evidence.json"]
    if review.get("schema_version") != 1:
        raise PipelineError("Unsupported activity review schema")
    builder = Activities(source_tables, review, raw_inputs, geography)
    activities, publications, publication_links, dates, venues = (
        builder.source_activity_data()
    )
    activity_ids = {row["global_activity_id"] for row in activities}
    publication_ids = {row["source_publication_id"] for row in publications}
    boundaries = []
    aliases = {alias: producer for producer, alias in SOURCE_ALIASES.items()}
    for item in review["protected_boundaries"]:
        members = [tuple(member.split(":", 1)) for member in item["members"]]
        resolved = []
        for alias, key in members:
            member = (aliases[alias], key)
            if member not in builder.source_key_to_global:
                raise PipelineError("Stale protected activity boundary")
            resolved.append(builder.source_key_to_global[member])
        if len(set(resolved)) != len(resolved):
            raise PipelineError("Protected activity identities collapsed")
        boundaries.append(
            dict(
                review_id=item["review_id"],
                decision=item["decision"],
                reason=item["reason"],
                source_members_json=json_text(item["members"]),
                global_members_json=json_text(resolved),
                application="protected_separation",
            )
        )
    crosswalk = [
        {key: row[key] for key in TABLE_COLUMNS["activity_crosswalk"]}
        for row in activities
    ]
    contributions = [
        dict(
            measure="K03_reported_activities",
            entity_id=row["global_activity_id"],
            source=row["source"],
            province_code="",
            contributor_ids_json=json_text([row["source_activity_id"]]),
            reason="One source-local activity identity; no supported cross-source merge.",
        )
        for row in activities
    ]
    tables = {
        "global_activities": activities,
        "activity_crosswalk": crosswalk,
        "publications": publications,
        "activity_publication_links": publication_links,
        "activity_dates": dates,
        "activity_venues": venues,
        "activity_sessions": builder.sessions,
        "activity_sections": builder.sections,
        "activity_media": builder.media,
        "activity_narrative_evidence": builder.narratives,
        "activity_identity_decisions": boundaries,
        "source_quality_treatments": [
            {key: row[key] for key in ("source", "source_key", "treatment", "reason")}
            for row in review["source_quality"]
        ],
        "measure_contributions": contributions,
        "measure_results": [
            dict(
                measure="K03_reported_activities",
                value=len(activities),
                scope="distinct source-local reported activities",
                status="substitute_measure",
            )
        ],
    }
    primary_keys = {
        "global_activities": "global_activity_id",
        "activity_crosswalk": "global_activity_id",
        "publications": "source_publication_id",
        "activity_publication_links": "source_publication_id",
        "activity_dates": "date_assertion_id",
        "activity_venues": "venue_assertion_id",
        "activity_sessions": "session_id",
        "activity_sections": "section_id",
        "activity_media": "media_id",
        "activity_narrative_evidence": "evidence_id",
        "activity_identity_decisions": "review_id",
        "measure_contributions": "entity_id",
    }
    known_observations = {
        key for index in builder.observations.values() for key in index
    }
    for name, rows in tables.items():
        key = primary_keys.get(name)
        if key and len({row[key] for row in rows}) != len(rows):
            raise PipelineError(f"Duplicate activity domain identity: {name}")
        for row in rows:
            if (
                row.get("global_activity_id")
                and row["global_activity_id"] not in activity_ids
            ):
                raise PipelineError(f"Unknown activity domain endpoint: {name}")
            if (
                row.get("observation_id")
                and row["observation_id"] not in known_observations
            ):
                raise PipelineError(f"Unknown activity evidence endpoint: {name}")
            if (
                row.get("source_publication_id")
                and row["source_publication_id"] not in publication_ids
            ):
                raise PipelineError(f"Unknown activity publication endpoint: {name}")
    if {(row["source"], row["source_publication_id"]) for row in publications} != set(
        builder.publication_inputs
    ):
        raise PipelineError("Activity publications were dropped")
    if any(
        json.loads(row["source_details_json"])
        != builder.publication_inputs[row["source"], row["source_publication_id"]]
        for row in publications
    ):
        raise PipelineError("Activity publication detail changed during adaptation")
    return tables
