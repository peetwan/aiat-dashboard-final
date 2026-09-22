"""Fail-closed validation for F2 entity relationships and measure populations."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .common import PipelineError
from .domains.raw_inputs import SOURCE_IDS


TABLE_PRIMARY_KEYS: dict[str, str | tuple[str, ...]] = {
    "entity_contributions": ("measure_id", "entity_id"),
    "evidence_links": ("measure_id", "entity_id"),
    "province_memberships": (
        "measure_id",
        "entity_id",
        "evidence_table",
        "evidence_id",
    ),
    "category_memberships": ("measure_id", "entity_id", "category_code", "evidence_id"),
    "eligibility_evidence": (
        "measure_id",
        "entity_id",
        "evidence_table",
        "evidence_id",
    ),
    "domains/areas/global_cultural_areas": "global_area_id",
    "domains/areas/area_crosswalk": "source_member_id",
    "domains/areas/area_assertions": "assertion_id",
    "domains/areas/identity_decisions": "decision_id",
    "domains/areas/measure_contributions": ("measure_id", "source_member_id"),
    "domains/areas/measure_results": "measure_id",
    "domains/people/assessment_observations": ("assessment_id", "observation_id"),
    "domains/activities/global_activities": "global_activity_id",
    "domains/activities/activity_crosswalk": ("source", "source_activity_id"),
    "domains/activities/publications": "source_publication_id",
    "domains/activities/activity_publication_links": (
        "source",
        "source_publication_id",
    ),
    "domains/activities/activity_venues": "venue_assertion_id",
    "domains/activities/activity_media": "media_id",
    "domains/activities/activity_narrative_evidence": "evidence_id",
    "domains/activities/activity_dates": "date_assertion_id",
    "domains/activities/activity_sessions": "session_id",
    "domains/activities/activity_sections": "section_id",
    "domains/activities/activity_identity_decisions": "review_id",
    "domains/activities/measure_contributions": "entity_id",
    "domains/activities/measure_results": "measure",
    "domains/innovations/global_innovations": "global_innovation_id",
    "domains/innovations/innovation_crosswalk": ("source", "local_innovation_id"),
    "domains/innovations/source_records": ("source", "observation_id", "row_locator"),
    "domains/innovations/readiness_evidence": "assessment_id",
    "domains/innovations/innovation_use_locations": "location_id",
    "domains/innovations/measure_contributions": ("measure", "global_innovation_id"),
    "domains/innovations/measure_results": "measure",
    "domains/innovations/province_k04_contributions": (
        "measure",
        "province_code",
        "global_innovation_id",
    ),
    "domains/innovations/province_k04_results": ("measure", "province_code"),
    "domains/people/global_people": "global_person_id",
    "domains/people/person_crosswalk": "source_entity_id",
    "domains/people/person_assertions": "assertion_id",
    "domains/people/person_location_admission": "location_admission_id",
    "domains/people/person_location_assertions": "location_assertion_id",
    "domains/people/development_assessments": "assessment_id",
    "domains/people/development_scores": ("assessment_id", "dimension"),
    "domains/people/assessment_admission": "assessment_id",
    "domains/people/measure_contributions": ("measure_id", "global_person_id"),
    "domains/people/measure_results": "measure_id",
}

ENTITY_MEASURES = {
    "K12",
    "K01B",
    "K03",
    "K04",
    "C04_LISTED",
    "C02_COMMUNITY",
    "C08_ASSESSED_PEOPLE",
    "C08_INCREASED_PEOPLE",
}
_USE_COVERAGE = {"eligible_innovation_use", "eligible_programme_target_or_use_coverage"}


def _truth(value: Any) -> bool:
    return value is True or str(value) == "True"


def _json_list(value: Any, context: str) -> list:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PipelineError(
            f"Identity validation invalid JSON list: {context}"
        ) from exc
    if not isinstance(decoded, list):
        raise PipelineError(f"Identity validation invalid JSON list: {context}")
    return decoded


def validate_identity_tables(
    root: dict[str, list[dict]],
    source_tables: dict[str, dict[str, list[dict]]],
    domain_tables: dict[str, dict[str, list[dict]]],
    province_rows: list[dict],
    enabled_measures: list[str],
) -> list[dict]:
    """Validate identities, evidence membership and exact measure populations."""
    checks: list[dict] = []

    def check(name: str, passed: bool, actual: int | str = "") -> None:
        if not passed:
            raise PipelineError(f"Identity relationship validation failed: {name}")
        checks.append({"check": name, "status": "passed", "actual": actual})

    def table(group: str, name: str) -> list[dict]:
        rows = domain_tables.get(group, {}).get(name)
        if not isinstance(rows, list):
            raise PipelineError(
                f"Identity validation missing domain table: {group}/{name}"
            )
        return rows

    def unique(
        name: str, rows: list[dict], key: str | tuple[str, ...]
    ) -> dict[Any, dict]:
        keys = (key,) if isinstance(key, str) else key
        values = []
        for row in rows:
            value = tuple(row.get(part, "") for part in keys)
            if any(part == "" for part in value):
                raise PipelineError(
                    f"Identity relationship validation failed: {name} complete primary key"
                )
            values.append(value[0] if len(value) == 1 else value)
        check(f"{name}: unique primary key", len(values) == len(set(values)), len(rows))
        return dict(zip(values, rows))

    enabled = set(enabled_measures)
    check(
        "enabled identity measures recognized",
        enabled <= ENTITY_MEASURES,
        len(enabled),
    )
    province_codes = [str(row.get("province_code", "")) for row in province_rows]
    check(
        "province reference keys complete and unique",
        all(province_codes) and len(province_codes) == len(set(province_codes)),
        len(province_codes),
    )
    province_set = set(province_codes)

    # Source endpoints used directly by root K12/category/province membership.
    cultural = source_tables.get(SOURCE_IDS["cultural_map"])
    atlocal = source_tables.get(SOURCE_IDS["atlocal"])
    if not isinstance(cultural, dict) or not isinstance(atlocal, dict):
        raise PipelineError("Identity validation missing cultural source tables")
    subjects = unique(
        "cultural mapped subjects", cultural.get("mapped_subjects", []), "subject_id"
    )
    cultural_locations = unique(
        "cultural mapped locations", cultural.get("mapped_locations", []), "location_id"
    )
    atlocal_locations = unique(
        "AtLocal locations", atlocal.get("locations", []), "location_id"
    )
    atlocal_areas = unique("AtLocal areas", atlocal.get("areas", []), "area_id")
    cultural_listings = unique(
        "cultural mapped listings",
        cultural.get("mapped_listing_observations", []),
        "listing_id",
    )
    categories = unique(
        "cultural category assertions",
        cultural.get("category_assertions", []),
        "category_assertion_id",
    )

    # Cultural area graph.
    areas = unique(
        "global cultural areas",
        table("areas", "global_cultural_areas"),
        "global_area_id",
    )
    area_members = unique(
        "area crosswalk", table("areas", "area_crosswalk"), "source_member_id"
    )
    area_assertions = unique(
        "area assertions", table("areas", "area_assertions"), "assertion_id"
    )
    check(
        "area crosswalk global endpoints",
        all(row.get("global_area_id") in areas for row in area_members.values()),
        len(area_members),
    )
    check(
        "area assertion member and global endpoints",
        all(
            row.get("source_member_id") in area_members
            and area_members[row["source_member_id"]]["global_area_id"]
            == row.get("global_area_id")
            for row in area_assertions.values()
        ),
        len(area_assertions),
    )
    check(
        "area source member endpoints",
        all(
            (
                row.get("source") == "cultural_map"
                and row.get("local_entity_id") in subjects
            )
            or (
                row.get("source") == "atlocal"
                and row.get("local_entity_id") in atlocal_areas
            )
            for row in area_members.values()
        ),
        len(area_members),
    )
    check(
        "area eligibility matches eligible members",
        all(
            _truth(row.get("k01b_eligible"))
            == any(
                _truth(member.get("k01b_eligible"))
                for member in area_members.values()
                if member.get("global_area_id") == area_id
            )
            for area_id, row in areas.items()
        ),
        len(areas),
    )

    # Activity/publication graph.
    activities = unique(
        "global activities",
        table("activities", "global_activities"),
        "global_activity_id",
    )
    activity_crosswalk = unique(
        "activity crosswalk",
        table("activities", "activity_crosswalk"),
        ("source", "source_activity_id"),
    )
    publications = unique(
        "activity publications",
        table("activities", "publications"),
        "source_publication_id",
    )
    publication_links = unique(
        "activity publication links",
        table("activities", "activity_publication_links"),
        ("source", "source_publication_id"),
    )
    venues = unique(
        "activity venues", table("activities", "activity_venues"), "venue_assertion_id"
    )
    media = unique("activity media", table("activities", "activity_media"), "media_id")
    narratives = unique(
        "activity narrative evidence",
        table("activities", "activity_narrative_evidence"),
        "evidence_id",
    )
    activity_source_ids = {
        "icommunity-v1": SOURCE_IDS["icommunity"],
        "icommunity": SOURCE_IDS["icommunity"],
        "atlocal-v1": SOURCE_IDS["atlocal"],
        "atlocal": SOURCE_IDS["atlocal"],
        "cultural-map-v1": SOURCE_IDS["cultural_map"],
        "cultural_map": SOURCE_IDS["cultural_map"],
    }
    activity_observations = {
        source_id: {
            row.get("observation_id")
            for row in source_tables.get(source_id, {}).get("source_observations", [])
        }
        for source_id in set(activity_source_ids.values())
    }
    publications_by_source = {
        (row.get("source"), row.get("source_publication_id")): row
        for row in publications.values()
    }
    cultural_publications_by_key = {
        row.get("source_key"): row
        for row in publications.values()
        if row.get("source") in {"cultural-map-v1", "cultural_map"}
    }
    accepted_context_links = {
        (
            "icommunity-v1",
            "programme_context",
            "no_identifiable_activity",
            "publication",
        ),
        ("icommunity", "programme_context", "no_identifiable_activity", "publication"),
        (
            "atlocal-v1",
            "context_or_quality_review",
            "no_identifiable_activity",
            "publication",
        ),
        (
            "atlocal",
            "context_or_quality_review",
            "no_identifiable_activity",
            "publication",
        ),
        ("cultural-map-v1", "context_only", "context_only", "context_only"),
        ("cultural_map", "context_only", "context_only", "context_only"),
    }

    def valid_publication_link(key: tuple[str, str], link: dict) -> bool:
        publication = publications_by_source.get(key)
        if publication is None or publication.get("global_activity_id", "") != link.get(
            "global_activity_id", ""
        ):
            return False
        global_id = str(link.get("global_activity_id", ""))
        if global_id:
            activity = activities.get(global_id)
            return bool(
                activity
                and link.get("link_status") == "source_reported_activity_link"
                and link.get("source")
                == publication.get("source")
                == activity.get("source")
            )
        context = (
            str(link.get("source", "")),
            str(publication.get("publication_role", "")),
            str(link.get("link_status", "")),
            str(link.get("parent_or_session_role", "")),
        )
        return context in accepted_context_links and link.get(
            "source"
        ) == publication.get("source")

    check(
        "activity crosswalk global endpoints",
        all(
            row.get("global_activity_id") in activities
            for row in activity_crosswalk.values()
        ),
        len(activity_crosswalk),
    )
    check(
        "activity-publication link endpoints and dispositions",
        all(valid_publication_link(key, row) for key, row in publication_links.items()),
        len(publication_links),
    )
    check(
        "every activity publication is linked",
        set(publications_by_source) == set(publication_links),
        len(publications),
    )
    check(
        "activity venue endpoints",
        all(row.get("global_activity_id") in activities for row in venues.values()),
        len(venues),
    )
    check(
        "global activity publication membership",
        all(
            (row.get("source"), row.get("source_publication_id")) in publication_links
            and publication_links[
                row.get("source"), row.get("source_publication_id")
            ].get("global_activity_id")
            == activity_id
            for activity_id, row in activities.items()
        ),
        len(activities),
    )

    def activity_observation_owned(row: dict) -> bool:
        source_id = activity_source_ids.get(str(row.get("source", "")))
        return bool(
            source_id and row.get("observation_id") in activity_observations[source_id]
        )

    def activity_child_owned(row: dict) -> bool:
        global_id = str(row.get("global_activity_id", ""))
        activity = activities.get(global_id)
        if activity:
            source_id = activity_source_ids.get(str(activity.get("source", "")))
            return bool(
                source_id
                and row.get("observation_id") in activity_observations[source_id]
                and str(row.get("raw_locator", "")).startswith(
                    f"evidence://{source_id}/"
                )
            )
        source_id = SOURCE_IDS["cultural_map"]
        source_key = str(row.get("source_key", "")).split(":", 1)[-1]
        publication = cultural_publications_by_key.get(source_key)
        return bool(
            not global_id
            and publication
            and not publication.get("global_activity_id")
            and publication.get("publication_role") == "context_only"
            and publication.get("observation_id") == row.get("observation_id")
            and row.get("observation_id") in activity_observations[source_id]
            and str(row.get("raw_locator", "")).startswith(f"evidence://{source_id}/")
        )

    check(
        "activity source-aware observation ownership",
        all(activity_observation_owned(row) for row in activities.values())
        and all(activity_observation_owned(row) for row in activity_crosswalk.values())
        and all(
            activity_observation_owned(row)
            and str(row.get("raw_locator", "")).startswith(
                f"evidence://{activity_source_ids[row['source']]}/"
            )
            for row in publications.values()
        ),
        len(activities) + len(activity_crosswalk) + len(publications),
    )
    check(
        "activity publication source ownership",
        all(
            row.get("source") == publications_by_source[key].get("source")
            for key, row in publication_links.items()
        ),
        len(publication_links),
    )
    check(
        "activity media graph and locators",
        all(activity_child_owned(row) for row in media.values()),
        len(media),
    )
    check(
        "activity narrative graph and locators",
        all(activity_child_owned(row) for row in narratives.values()),
        len(narratives),
    )

    # Innovation identity/readiness/use graph.
    innovations = unique(
        "global innovations",
        table("innovations", "global_innovations"),
        "global_innovation_id",
    )
    innovation_crosswalk = unique(
        "innovation crosswalk",
        table("innovations", "innovation_crosswalk"),
        ("source", "local_innovation_id"),
    )
    innovation_records = unique(
        "innovation source records",
        table("innovations", "source_records"),
        ("source", "observation_id", "row_locator"),
    )
    readiness = unique(
        "innovation readiness",
        table("innovations", "readiness_evidence"),
        "assessment_id",
    )
    use_locations = unique(
        "innovation use locations",
        table("innovations", "innovation_use_locations"),
        "location_id",
    )
    check(
        "innovation crosswalk global endpoints",
        all(
            row.get("global_innovation_id") in innovations
            for row in innovation_crosswalk.values()
        ),
        len(innovation_crosswalk),
    )
    check(
        "innovation source record membership",
        all(
            (row.get("source"), row.get("local_innovation_id")) in innovation_crosswalk
            and innovation_crosswalk[row["source"], row["local_innovation_id"]].get(
                "global_innovation_id"
            )
            == row.get("global_innovation_id")
            for row in innovation_records.values()
        ),
        len(innovation_records),
    )
    check(
        "readiness innovation membership",
        all(
            (row.get("source"), row.get("local_innovation_id")) in innovation_crosswalk
            and innovation_crosswalk[row["source"], row["local_innovation_id"]].get(
                "global_innovation_id"
            )
            == row.get("global_innovation_id")
            for row in readiness.values()
        ),
        len(readiness),
    )
    qualifying_innovations = {
        row["global_innovation_id"]
        for row in readiness.values()
        if _truth(row.get("qualifies_k04"))
    }
    check(
        "innovation K04 flag matches readiness evidence",
        qualifying_innovations
        == {
            key for key, row in innovations.items() if _truth(row.get("qualifies_k04"))
        },
        len(qualifying_innovations),
    )
    innovation_source_ids = {
        "icommunity": SOURCE_IDS["icommunity"],
        "pmua_apptech": SOURCE_IDS["pmua_apptech"],
        "rinmp": SOURCE_IDS["rinmp"],
        "apptech_mru": SOURCE_IDS["apptech_mru"],
    }
    source_innovations = {
        source: {
            row.get("innovation_id")
            for row in source_tables.get(source_id, {}).get("innovations", [])
        }
        for source, source_id in innovation_source_ids.items()
    }
    source_observations = {
        source: {
            row.get("observation_id"): row
            for row in source_tables.get(source_id, {}).get("source_observations", [])
        }
        for source, source_id in innovation_source_ids.items()
    }
    source_location_tables = {
        "icommunity": source_tables.get(innovation_source_ids["icommunity"], {}).get(
            "locations", []
        ),
        "rinmp": source_tables.get(innovation_source_ids["rinmp"], {}).get(
            "location_assertions", []
        ),
        "pmua_apptech": source_tables.get(
            innovation_source_ids["pmua_apptech"], {}
        ).get("innovation_area_assertions", []),
    }
    source_locations: dict[str, dict[str, dict[str, Any]]] = {}
    for source, rows in source_location_tables.items():
        indexed: dict[str, dict[str, Any]] = {}
        for source_row in rows:
            if source == "pmua_apptech":
                pairs = _json_list(
                    source_row.get("hierarchy_pairs_json"),
                    f"PMUA location {source_row.get('assertion_id')}",
                ) or [{}]
                expanded = []
                for ordinal, pair in enumerate(pairs):
                    row = dict(source_row)
                    row.update(
                        {
                            "location_id": f"{source_row.get('assertion_id', '')}:{ordinal}",
                            "district_normalized": pair.get("district_name", ""),
                            "district_code": pair.get("district_code", ""),
                            "subdistrict_normalized": pair.get("subdistrict_name", ""),
                            "subdistrict_code": pair.get("subdistrict_code", ""),
                        }
                    )
                    expanded.append(row)
            else:
                expanded = [source_row]
            for row in expanded:
                location_id = str(row.get("location_id", ""))
                if not location_id or location_id in indexed:
                    raise PipelineError(
                        f"Identity relationship validation failed: duplicate {source} source location"
                    )
                indexed[location_id] = row
        source_locations[source] = indexed

    def use_location_owned(row: dict) -> bool:
        source = str(row.get("source", ""))
        member = (source, row.get("local_innovation_id"))
        if member not in innovation_crosswalk or innovation_crosswalk[member].get(
            "global_innovation_id"
        ) != row.get("global_innovation_id"):
            return False
        source_row = source_locations.get(source, {}).get(
            str(row.get("location_id", ""))
        )
        if source_row is None:
            return False
        local_field = "entity_id" if source == "icommunity" else "innovation_id"
        status_field = "status" if source == "icommunity" else "resolution_status"
        expected = {
            "local_innovation_id": source_row.get(local_field),
            "observation_id": source_row.get("observation_id"),
            "location_role": source_row.get("location_role", "declared_innovation_use"),
            "coverage_eligibility": source_row.get(
                "coverage_eligibility", "eligible_innovation_use"
            ),
            "province_normalized": source_row.get("province_normalized", ""),
            "province_code": source_row.get("province_code", ""),
            "district_normalized": source_row.get("district_normalized", ""),
            "district_code": source_row.get("district_code", ""),
            "subdistrict_normalized": source_row.get("subdistrict_normalized", ""),
            "subdistrict_code": source_row.get("subdistrict_code", ""),
            "resolution_status": source_row.get(status_field, ""),
        }
        return all(
            str(row.get(field, "")) == str(value or "")
            for field, value in expected.items()
        )

    check(
        "use-location innovation membership and source lineage",
        all(use_location_owned(row) for row in use_locations.values()),
        len(use_locations),
    )

    def source_observation_locator(source: str, observation: dict) -> str:
        locator = str(observation.get("row_locator", ""))
        if locator.startswith("evidence://"):
            return locator
        raw_file = str(observation.get("raw_file", ""))
        if raw_file.startswith("evidence://"):
            base = raw_file.split("#", 1)[0]
        else:
            run_id = str(observation.get("run_id", ""))
            if not run_id or not raw_file:
                raise PipelineError(
                    "Identity relationship validation failed: innovation observation locator"
                )
            base = f"evidence://{innovation_source_ids[source]}/{run_id}/{raw_file}"
        return base + "#" + locator.lstrip("#/")

    def compatible_record_locator(record: dict) -> bool:
        source = str(record.get("source", ""))
        observation = source_observations.get(source, {}).get(
            record.get("observation_id")
        )
        record_locator = (
            str(record.get("raw_file", ""))
            + "#"
            + str(record.get("row_locator", "")).lstrip("#/")
        )
        if (
            observation is None
            or not record.get("row_locator")
            or not record_locator.startswith(
                f"evidence://{innovation_source_ids.get(source, '')}/"
            )
        ):
            return False
        if source == "rinmp" and (
            not record.get("source_id")
            or str(record["source_id"]) != str(observation.get("source_id", ""))
        ):
            return False
        observation_locator = source_observation_locator(source, observation)
        observation_base, observation_pointer = observation_locator.split("#", 1)
        record_base, record_pointer = record_locator.split("#", 1)
        same_file = observation_base.removesuffix(".gz") == record_base.removesuffix(
            ".gz"
        )
        if not same_file:
            return False
        if record_pointer == observation_pointer.strip("/"):
            return True
        if source != "pmua_apptech" or observation_pointer.strip("/"):
            return False
        return any(
            row.get("map_observation_id") == record.get("observation_id")
            and row.get("innovation_id") == record.get("local_innovation_id")
            and str(row.get("source_id")) == str(record.get("source_id"))
            and str(row.get("source_locator", "")).strip("/") == record_pointer
            for row in source_tables[innovation_source_ids[source]].get(
                "map_area_items", []
            )
        )

    check(
        "innovation source record pointer and observation ownership",
        all(compatible_record_locator(row) for row in innovation_records.values()),
        len(innovation_records),
    )
    records_by_member = {
        (row.get("source"), row.get("local_innovation_id"))
        for row in innovation_records.values()
    }
    check(
        "innovation crosswalk source-local ownership and record coverage",
        all(
            source in source_innovations
            and local_id in source_innovations[source]
            and (source, local_id) in records_by_member
            for source, local_id in innovation_crosswalk
        ),
        len(innovation_crosswalk),
    )
    check(
        "every global innovation has source membership",
        set(innovations)
        == {row.get("global_innovation_id") for row in innovation_crosswalk.values()},
        len(innovations),
    )

    # People identities, attached assertions and paired assessments.
    people = unique(
        "global people", table("people", "global_people"), "global_person_id"
    )
    person_crosswalk = unique(
        "person crosswalk", table("people", "person_crosswalk"), "source_entity_id"
    )
    assertions = unique(
        "person assertions", table("people", "person_assertions"), "assertion_id"
    )
    location_admissions = unique(
        "person location admission",
        table("people", "person_location_admission"),
        "location_admission_id",
    )
    location_assertions = unique(
        "person location assertions",
        table("people", "person_location_assertions"),
        "location_assertion_id",
    )
    assessments = unique(
        "development assessments",
        table("people", "development_assessments"),
        "assessment_id",
    )
    assessment_observations = unique(
        "assessment observations",
        table("people", "assessment_observations"),
        ("assessment_id", "observation_id"),
    )
    scores = unique(
        "development scores",
        table("people", "development_scores"),
        ("assessment_id", "dimension"),
    )
    admissions = unique(
        "assessment admission", table("people", "assessment_admission"), "assessment_id"
    )
    check(
        "person crosswalk global endpoints",
        all(row.get("global_person_id") in people for row in person_crosswalk.values()),
        len(person_crosswalk),
    )
    for assertion in assertions.values():
        global_id = assertion.get("global_person_id", "")
        source_entity = assertion.get("source_entity_id", "")
        attached = _json_list(
            assertion.get("attached_global_person_ids_json"),
            f"person assertion {assertion['assertion_id']}",
        )
        if global_id:
            if (
                source_entity not in person_crosswalk
                or person_crosswalk[source_entity].get("global_person_id") != global_id
            ):
                raise PipelineError(
                    "Identity relationship validation failed: person assertion ownership"
                )
        elif source_entity:
            raise PipelineError(
                "Identity relationship validation failed: person assertion has unowned source entity"
            )
        if any(item not in people for item in attached):
            raise PipelineError(
                "Identity relationship validation failed: person assertion attachment endpoint"
            )
        if (
            attached
            and assertion.get("identity_treatment")
            != "reviewed_evidence_attachment_only"
        ):
            raise PipelineError(
                "Identity relationship validation failed: attached assertion treatment"
            )
    checks.append(
        {
            "check": "person assertion ownership and attachments",
            "status": "passed",
            "actual": len(assertions),
        }
    )
    icommunity_locations = {
        row.get("location_id"): row
        for row in source_tables.get(SOURCE_IDS["icommunity"], {}).get("locations", [])
        if row.get("location_role") == "source_person_location"
    }
    province_names = {
        str(row.get("province_code", "")): str(row.get("province_name_th", ""))
        for row in province_rows
    }
    admission_by_location = {
        row.get("source_location_id"): row for row in location_admissions.values()
    }
    check(
        "person location admission covers source person locations",
        set(admission_by_location) == set(icommunity_locations),
        len(admission_by_location),
    )
    allowed_location_decisions = {
        "accept_exact_source_province",
        "exclude_source_geocode_conflict",
        "exclude_missing_global_person",
        "exclude_unknown_province",
    }
    for location_id, source_location in icommunity_locations.items():
        row = admission_by_location[location_id]
        source_entity_id = f"icommunity:{source_location.get('entity_id', '')}"
        crosswalk = person_crosswalk.get(source_entity_id)
        global_person_id = crosswalk.get("global_person_id", "") if crosswalk else ""
        province_code = str(source_location.get("province_code", "")).zfill(2)
        if not source_location.get("province_code"):
            province_code = ""
        expected_decision = (
            "exclude_missing_global_person"
            if not global_person_id
            else "exclude_source_geocode_conflict"
            if source_location.get("status") == "source_geocode_conflict"
            else "exclude_unknown_province"
            if province_code not in province_names
            else "accept_exact_source_province"
        )
        if (
            row.get("decision") not in allowed_location_decisions
            or row.get("decision") != expected_decision
            or row.get("source") != SOURCE_IDS["icommunity"]
            or row.get("source_entity_id") != source_entity_id
            or row.get("global_person_id") != global_person_id
            or row.get("source_observation_id")
            != source_location.get("observation_id")
            or row.get("source_location_role") != "source_person_location"
            or row.get("source_resolution_status") != source_location.get("status")
            or row.get("province_code")
            != (province_code if province_code in province_names else "")
            or row.get("province_name_th")
            != province_names.get(province_code, "")
        ):
            raise PipelineError(
                "Identity relationship validation failed: person location admission"
            )
    accepted_location_ids = {
        location_id
        for location_id, row in admission_by_location.items()
        if row.get("decision") == "accept_exact_source_province"
    }
    asserted_location_ids = set()
    asserted_person_provinces = set()
    for assertion in location_assertions.values():
        global_person_id = assertion.get("global_person_id")
        province_code = str(assertion.get("province_code", ""))
        source_entity_ids = set(
            _json_list(
                assertion.get("source_entity_ids_json"),
                f"person location assertion entities {assertion['location_assertion_id']}",
            )
        )
        source_location_ids = set(
            _json_list(
                assertion.get("source_location_ids_json"),
                f"person location assertion locations {assertion['location_assertion_id']}",
            )
        )
        source_observation_ids = set(
            _json_list(
                assertion.get("source_observation_ids_json"),
                f"person location assertion observations {assertion['location_assertion_id']}",
            )
        )
        support = [admission_by_location.get(value) for value in source_location_ids]
        if (
            global_person_id not in people
            or not source_location_ids
            or any(row is None for row in support)
            or any(
                row.get("decision") != "accept_exact_source_province"
                or row.get("global_person_id") != global_person_id
                or row.get("province_code") != province_code
                for row in support
            )
            or source_entity_ids != {row.get("source_entity_id") for row in support}
            or source_observation_ids
            != {row.get("source_observation_id") for row in support}
            or assertion.get("province_name_th")
            != province_names.get(province_code)
            or assertion.get("location_role")
            != "source_reported_innovator_location"
            or assertion.get("source") != SOURCE_IDS["icommunity"]
            or assertion.get("evidence_basis")
            != "exact_source_province_name_lookup"
            or assertion.get("province_resolution_status")
            != "exact_source_province"
            or assertion.get("review_status") != "accepted"
        ):
            raise PipelineError(
                "Identity relationship validation failed: person province assertion"
            )
        asserted_location_ids |= source_location_ids
        asserted_person_provinces.add((global_person_id, province_code))
    check(
        "person province assertions exactly reconcile accepted evidence",
        asserted_location_ids == accepted_location_ids
        and len(asserted_person_provinces) == len(location_assertions),
        len(location_assertions),
    )
    check(
        "assessment global/source membership",
        all(
            row.get("global_person_id") in people
            and row.get("source_entity_id") in person_crosswalk
            and person_crosswalk[row["source_entity_id"]].get("global_person_id")
            == row.get("global_person_id")
            for row in assessments.values()
        ),
        len(assessments),
    )
    check(
        "assessment observations endpoints",
        all(
            key[0] in assessments
            and row.get("source_entity_id")
            == assessments[key[0]].get("source_entity_id")
            and row.get("global_person_id")
            == assessments[key[0]].get("global_person_id")
            for key, row in assessment_observations.items()
        ),
        len(assessment_observations),
    )
    check(
        "development score endpoints",
        all(
            key[0] in assessments
            and row.get("source_entity_id")
            == assessments[key[0]].get("source_entity_id")
            and row.get("global_person_id")
            == assessments[key[0]].get("global_person_id")
            for key, row in scores.items()
        ),
        len(scores),
    )
    check(
        "assessment admission coverage",
        set(admissions) == set(assessments)
        and all(
            row.get("global_person_id") == assessments[key].get("global_person_id")
            and row.get("source_entity_id") == assessments[key].get("source_entity_id")
            for key, row in admissions.items()
        ),
        len(admissions),
    )
    complete_assessments = {
        key for key, row in assessments.items() if _truth(row.get("complete"))
    }
    check(
        "complete assessment evidence graph",
        all(
            len([key for key in scores if key[0] == assessment_id]) == 3
            and any(key[0] == assessment_id for key in assessment_observations)
            for assessment_id in complete_assessments
        ),
        len(complete_assessments),
    )
    assertions_by_global = defaultdict(list)
    for row in assertions.values():
        if (
            row.get("global_person_id")
            and row.get("identity_treatment") != "reviewed_evidence_attachment_only"
        ):
            assertions_by_global[row["global_person_id"]].append(row)
    for global_id, row in people.items():
        supported_roles = {
            role
            for assertion in assertions_by_global[global_id]
            for role in _json_list(
                assertion.get("eligible_roles_json"),
                f"person assertion roles {assertion['assertion_id']}",
            )
        }
        if _truth(row.get("community_innovator_eligible")) != bool(
            supported_roles & {"community_innovator", "inventor"}
        ):
            raise PipelineError(
                "Identity relationship validation failed: C02 eligibility assertion support"
            )
    checks.append(
        {
            "check": "people eligibility has non-attached assertion support",
            "status": "passed",
            "actual": len(people),
        }
    )

    # Domain contributions must be unique and describe their own eligible populations.
    innovation_contributions = table("innovations", "measure_contributions")
    innovation_keys = [
        (row.get("measure"), row.get("global_innovation_id"))
        for row in innovation_contributions
        if row.get("measure") in {"K04", "C04_LISTED"}
    ]
    check(
        "unique innovation measure contributions",
        len(innovation_keys) == len(set(innovation_keys)),
        len(innovation_keys),
    )
    expected = {
        "K12": {
            key for key, row in subjects.items() if _truth(row.get("k12_eligible"))
        },
        "K01B": {key for key, row in areas.items() if _truth(row.get("k01b_eligible"))},
        "K03": set(activities),
        "C04_LISTED": set(innovations),
        "K04": qualifying_innovations,
        "C02_COMMUNITY": {
            key
            for key, row in people.items()
            if _truth(row.get("community_innovator_eligible"))
        },
        "C08_ASSESSED_PEOPLE": {
            row["global_person_id"]
            for row in assessments.values()
            if _truth(row.get("complete"))
        },
        "C08_INCREASED_PEOPLE": {
            row["global_person_id"]
            for row in assessments.values()
            if _truth(row.get("complete")) and _truth(row.get("any_increase"))
        },
    }
    check(
        "domain innovation C04 population",
        {entity for measure, entity in innovation_keys if measure == "C04_LISTED"}
        == expected["C04_LISTED"],
        len(expected["C04_LISTED"]),
    )
    check(
        "domain innovation K04 population",
        {entity for measure, entity in innovation_keys if measure == "K04"}
        == expected["K04"],
        len(expected["K04"]),
    )
    person_contributions = table("people", "measure_contributions")
    person_keys = [
        (row.get("measure_id"), row.get("global_person_id"))
        for row in person_contributions
        if row.get("measure_id") in expected
    ]
    check(
        "unique people measure contributions",
        len(person_keys) == len(set(person_keys)),
        len(person_keys),
    )
    for measure in (
        "C02_COMMUNITY",
        "C08_ASSESSED_PEOPLE",
        "C08_INCREASED_PEOPLE",
    ):
        check(
            f"domain {measure} population",
            {entity for name, entity in person_keys if name == measure}
            == expected[measure],
            len(expected[measure]),
        )

    # Root contribution and evidence populations are exact for the enabled slice.
    contributions = root.get("entity_contributions")
    evidence_links = root.get("evidence_links")
    eligibility_evidence = root.get("eligibility_evidence")
    province_memberships = root.get("province_memberships")
    category_memberships = root.get("category_memberships")
    if not all(
        isinstance(rows, list)
        for rows in (
            contributions,
            evidence_links,
            eligibility_evidence,
            province_memberships,
            category_memberships,
        )
    ):
        raise PipelineError("Identity validation missing root relationship tables")
    contribution_index = unique(
        "root contributions", contributions, ("measure_id", "entity_id")
    )
    check(
        "root contributions use enabled measures only",
        {key[0] for key in contribution_index} <= enabled,
        len(contribution_index),
    )
    for measure in enabled:
        check(
            f"root {measure} exact eligible population",
            {key[1] for key in contribution_index if key[0] == measure}
            == expected[measure],
            len(expected[measure]),
        )
    evidence_index = unique(
        "root evidence links", evidence_links, ("measure_id", "entity_id")
    )
    check(
        "one root evidence link per contribution",
        set(evidence_index) == set(contribution_index),
        len(evidence_index),
    )
    root_targets = {
        "K12": (
            "sources/f2_culturalmap_university/mapped_subjects",
            "subject_id",
            subjects,
        ),
        "K01B": ("domains/areas/global_cultural_areas", "global_area_id", areas),
        "K03": (
            "domains/activities/global_activities",
            "global_activity_id",
            activities,
        ),
        "K04": (
            "domains/innovations/global_innovations",
            "global_innovation_id",
            innovations,
        ),
        "C04_LISTED": (
            "domains/innovations/global_innovations",
            "global_innovation_id",
            innovations,
        ),
        "C02_COMMUNITY": ("domains/people/global_people", "global_person_id", people),
        "C08_ASSESSED_PEOPLE": (
            "domains/people/global_people",
            "global_person_id",
            people,
        ),
        "C08_INCREASED_PEOPLE": (
            "domains/people/global_people",
            "global_person_id",
            people,
        ),
    }
    check(
        "root evidence links preserve counted identity",
        all(
            row.get("table") == root_targets[key[0]][0]
            and row.get("key") == root_targets[key[0]][1]
            and row.get("record_id") == key[1]
            and key[1] in root_targets[key[0]][2]
            and row.get("evidence_role") == "counted_identity"
            for key, row in evidence_index.items()
        ),
        len(evidence_index),
    )
    eligibility_index = unique(
        "root eligibility evidence",
        eligibility_evidence,
        ("measure_id", "entity_id", "evidence_table", "evidence_id"),
    )
    eligibility_by_contribution = defaultdict(list)
    for key, row in eligibility_index.items():
        contribution_key = key[:2]
        if (
            contribution_key not in contribution_index
            or not row.get("evidence_key")
            or not row.get("evidence_role")
        ):
            raise PipelineError(
                "Identity relationship validation failed: eligibility evidence contribution endpoint"
            )
        eligibility_by_contribution[contribution_key].append(row)
    innovation_contribution_rows = {
        (row.get("measure"), row.get("global_innovation_id")): row
        for row in innovation_contributions
        if row.get("measure") in {"K04", "C04_LISTED"}
    }
    person_contribution_rows = {
        (row.get("measure_id"), row.get("global_person_id")): row
        for row in person_contributions
        if row.get("measure_id")
        in {
            "C02_COMMUNITY",
            "C08_ASSESSED_PEOPLE",
            "C08_INCREASED_PEOPLE",
        }
    }
    listings_by_subject = defaultdict(set)
    for listing_id, row in cultural_listings.items():
        listings_by_subject[row.get("subject_id")].add(listing_id)
    area_assertions_by_global = defaultdict(set)
    for assertion_id, row in area_assertions.items():
        if _truth(row.get("k01b_eligible")):
            area_assertions_by_global[row.get("global_area_id")].add(assertion_id)
    publications_by_activity = defaultdict(set)
    for (_, publication_id), link in publication_links.items():
        if link.get("global_activity_id"):
            publications_by_activity[link["global_activity_id"]].add(publication_id)
    for contribution_key in contribution_index:
        measure, entity_id = contribution_key
        if measure == "K12":
            expected_endpoint = (
                "sources/f2_culturalmap_university/mapped_listing_observations",
                "listing_id",
            )
            expected_ids = listings_by_subject[entity_id]
            expected_role = "source_mapped_listing"
        elif measure == "K01B":
            expected_endpoint = ("domains/areas/area_assertions", "assertion_id")
            expected_ids = area_assertions_by_global[entity_id]
            expected_role = "source_supported_cultural_area"
        elif measure == "K03":
            expected_endpoint = (
                "domains/activities/activity_publication_links",
                "source_publication_id",
            )
            expected_ids = publications_by_activity[entity_id]
            expected_role = "activity_publication"
        elif measure == "K04":
            expected_endpoint = (
                "domains/innovations/readiness_evidence",
                "assessment_id",
            )
            expected_ids = set(
                _json_list(
                    innovation_contribution_rows[contribution_key].get(
                        "qualifying_assessment_ids_json"
                    ),
                    f"K04 contribution {entity_id}",
                )
            )
            expected_role = "qualifying_readiness_assessment"
            if expected_ids != {
                assessment_id
                for assessment_id, row in readiness.items()
                if row.get("global_innovation_id") == entity_id
                and _truth(row.get("qualifies_k04"))
            }:
                raise PipelineError(
                    "Identity relationship validation failed: K04 qualifying assessment set"
                )
        elif measure == "C04_LISTED":
            expected_endpoint = (
                "domains/innovations/global_innovations",
                "global_innovation_id",
            )
            expected_ids = {entity_id}
            expected_role = "listed_innovation_identity"
        elif measure == "C02_COMMUNITY":
            expected_endpoint = ("domains/people/person_assertions", "assertion_id")
            expected_ids = set(
                _json_list(
                    person_contribution_rows[contribution_key].get(
                        "qualifying_assertion_ids_json"
                    ),
                    f"{measure} contribution {entity_id}",
                )
            )
            expected_role = "source_supported_person_role"
            qualifying_roles = {"community_innovator", "inventor"}
            actual_qualifying_ids = {
                assertion_id
                for assertion_id, assertion in assertions.items()
                if assertion.get("global_person_id") == entity_id
                and assertion.get("identity_treatment")
                != "reviewed_evidence_attachment_only"
                and (
                    set(
                        _json_list(
                            assertion.get("eligible_roles_json"),
                            f"person assertion roles {assertion_id}",
                        )
                    )
                    & qualifying_roles
                    or assertion.get("role") in qualifying_roles
                )
            }
            if expected_ids != actual_qualifying_ids:
                raise PipelineError(
                    "Identity relationship validation failed: C02 qualifying assertion set"
                )
        else:
            expected_endpoint = (
                "domains/people/development_assessments",
                "assessment_id",
            )
            expected_ids = set(
                _json_list(
                    person_contribution_rows[contribution_key].get(
                        "qualifying_assertion_ids_json"
                    ),
                    f"{measure} contribution {entity_id}",
                )
            )
            expected_role = (
                "complete_paired_assessment"
                if measure == "C08_ASSESSED_PEOPLE"
                else "complete_paired_assessment_with_increase"
            )
            actual_qualifying_ids = {
                assessment_id
                for assessment_id, assessment in assessments.items()
                if assessment.get("global_person_id") == entity_id
                and _truth(assessment.get("complete"))
                and (
                    measure == "C08_ASSESSED_PEOPLE"
                    or _truth(assessment.get("any_increase"))
                )
            }
            if expected_ids != actual_qualifying_ids:
                raise PipelineError(
                    "Identity relationship validation failed: C08 qualifying assessment set"
                )
        actual_rows = eligibility_by_contribution.get(contribution_key, [])
        actual_ids = {
            row.get("evidence_id")
            for row in actual_rows
            if (row.get("evidence_table"), row.get("evidence_key")) == expected_endpoint
        }
        if (
            not expected_ids
            or actual_ids != expected_ids
            or len(actual_rows) != len(expected_ids)
            or any(row.get("evidence_role") != expected_role for row in actual_rows)
        ):
            raise PipelineError(
                "Identity relationship validation failed: exact eligibility evidence set"
            )
    check(
        "eligibility evidence exact qualifying endpoints",
        True,
        len(eligibility_evidence),
    )

    # Province evidence must retain its source entity, province and allowed role.
    area_by_local = defaultdict(set)
    for row in area_members.values():
        if _truth(row.get("k01b_eligible")):
            area_by_local[row.get("source"), row.get("local_entity_id")].add(
                row.get("global_area_id")
            )
    for row in province_memberships:
        key = (row.get("measure_id"), row.get("entity_id"))
        if (
            key not in contribution_index
            or str(row.get("province_code", "")) not in province_set
        ):
            raise PipelineError(
                "Identity relationship validation failed: province contribution endpoint"
            )
        measure, evidence_id = key[0], row.get("evidence_id")
        if measure == "K12":
            source = "cultural_map"
            evidence = cultural_locations.get(evidence_id)
            valid = evidence is not None and evidence.get("subject_id") == key[1]
        elif measure == "K01B":
            cultural_path = f"sources/{SOURCE_IDS['cultural_map']}/mapped_locations"
            atlocal_path = f"sources/{SOURCE_IDS['atlocal']}/locations"
            if row.get("evidence_table") == cultural_path:
                source, evidence = "cultural_map", cultural_locations.get(evidence_id)
            elif row.get("evidence_table") == atlocal_path:
                source, evidence = "atlocal", atlocal_locations.get(evidence_id)
            else:
                source, evidence = "", None
            local_id = (
                evidence.get("subject_id")
                if source == "cultural_map" and evidence
                else evidence.get("entity_id")
                if evidence
                else ""
            )
            valid = evidence is not None and key[1] in area_by_local[source, local_id]
        elif measure == "K03":
            source = ""
            evidence = venues.get(evidence_id)
            valid = (
                evidence is not None and evidence.get("global_activity_id") == key[1]
            )
        elif measure in {"K04", "C04_LISTED"}:
            source = ""
            evidence = use_locations.get(evidence_id)
            valid = (
                evidence is not None
                and evidence.get("global_innovation_id") == key[1]
                and evidence.get("coverage_eligibility") in _USE_COVERAGE
            )
        elif measure == "C02_COMMUNITY":
            source = ""
            evidence = location_assertions.get(evidence_id)
            valid = (
                evidence is not None
                and evidence.get("global_person_id") == key[1]
                and evidence.get("review_status") == "accepted"
            )
        else:
            source, evidence, valid = "", None, False
        valid = (
            valid
            and str(evidence.get("province_code", ""))
            == str(row.get("province_code", ""))
            and evidence.get("location_role") == row.get("location_role")
        )
        expected_table = {
            "K12": f"sources/{SOURCE_IDS['cultural_map']}/mapped_locations",
            "K03": "domains/activities/activity_venues",
            "K04": "domains/innovations/innovation_use_locations",
            "C04_LISTED": "domains/innovations/innovation_use_locations",
            "C02_COMMUNITY": "domains/people/person_location_assertions",
        }.get(measure)
        if measure == "K01B":
            expected_table = (
                f"sources/{SOURCE_IDS[source]}/"
                + ("mapped_locations" if source == "cultural_map" else "locations")
                if source
                else ""
            )
        expected_key = (
            "venue_assertion_id"
            if measure == "K03"
            else "location_assertion_id"
            if measure == "C02_COMMUNITY"
            else "location_id"
        )
        if (
            not valid
            or row.get("evidence_table") != expected_table
            or row.get("evidence_key") != expected_key
        ):
            raise PipelineError(
                "Identity relationship validation failed: province evidence preserves entity/location/role"
            )
    checks.append(
        {
            "check": "province evidence preserves entity/location/role",
            "status": "passed",
            "actual": len(province_memberships),
        }
    )

    for row in category_memberships:
        key = (row.get("measure_id"), row.get("entity_id"))
        evidence = categories.get(row.get("evidence_id"))
        if (
            key not in contribution_index
            or key[0] != "K12"
            or evidence is None
            or evidence.get("subject_id") != key[1]
            or evidence.get("category_code") != row.get("category_code")
            or evidence.get("category_kind") != row.get("category_kind")
            or row.get("evidence_table")
            != f"sources/{SOURCE_IDS['cultural_map']}/category_assertions"
            or row.get("evidence_key") != "category_assertion_id"
        ):
            raise PipelineError(
                "Identity relationship validation failed: category assertion preserves subject/category"
            )
    checks.append(
        {
            "check": "category assertion preserves subject/category",
            "status": "passed",
            "actual": len(category_memberships),
        }
    )

    for smaller, larger in (
        ("K04", "C04_LISTED"),
        ("C08_INCREASED_PEOPLE", "C08_ASSESSED_PEOPLE"),
    ):
        if smaller in enabled and larger in enabled:
            check(
                f"required subset {smaller}/{larger}",
                expected[smaller] <= expected[larger],
                len(expected[smaller]),
            )
    return checks
