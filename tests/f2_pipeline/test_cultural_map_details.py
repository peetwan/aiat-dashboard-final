from collections import defaultdict

from tools.f2_pipeline.common import stable_id
from tools.f2_pipeline.sources.cultural_map_details import (
    TABLE_COLUMNS,
    CulturalMapDetails,
)


def test_mapped_people_fields_restore_legacy_role_evidence_without_admitting_people():
    key = "map_inspiration:CD-1"
    builder = object.__new__(CulturalMapDetails)
    builder.data = {
        "map_inspiration": [
            {
                "external_id": "CD-1",
                "data": {
                    "people": {
                        "recorder": {"name": "Recorder Name"},
                        "informants_raw": "Informant Name",
                        "contact_raw": "contact@example.invalid",
                    }
                },
            },
            {"external_id": "CD-2", "data": {"people": {}}},
        ]
    }
    builder.subject_for_source = {
        key: "subject-1",
        "map_inspiration:CD-2": "subject-2",
    }
    builder.observations = {
        key: "observation-1",
        "map_inspiration:CD-2": "observation-2",
    }
    mapped_subjects = [{"subject_id": "subject-1"}, {"subject_id": "subject-2"}]
    mapped_listings = [{"source_key": key}, {"source_key": "map_inspiration:CD-2"}]
    builder.tables = defaultdict(
        list,
        {
            "mapped_subjects": mapped_subjects,
            "mapped_listing_observations": mapped_listings,
            "people": [],
        },
    )

    builder.clean_mapped_people()

    rows = builder.tables["mapped_person_role_evidence"]
    assert {row["role"] for row in rows} == {"recorder", "informant", "contact"}
    assert all(
        set(row) == set(TABLE_COLUMNS["mapped_person_role_evidence"]) for row in rows
    )
    assert all(row["subject_id"] == "subject-1" for row in rows)
    assert all(row["observation_id"] == "observation-1" for row in rows)
    assert all(row["eligibility"] == "not_eligible_from_role_alone" for row in rows)
    assert {row["role"]: row["evidence_id"] for row in rows} == {
        role: stable_id("cultural_map_person_role", key, role)
        for role in ("recorder", "informant", "contact")
    }
    assert {row["role"]: row["source_locator"] for row in rows} == {
        "recorder": "data/people/recorder",
        "informant": "data/people/informant",
        "contact": "data/people/contact",
    }
    assert next(row for row in rows if row["role"] == "contact") == {
        "evidence_id": stable_id("cultural_map_person_role", key, "contact"),
        "subject_id": "subject-1",
        "observation_id": "observation-1",
        "source_key": key,
        "role": "contact",
        "person_or_institution_raw": "source contact reference",
        "evidence": "[email omitted]",
        "eligibility": "not_eligible_from_role_alone",
        "source_locator": "data/people/contact",
    }
    assert builder.tables["mapped_subjects"] is mapped_subjects
    assert builder.tables["mapped_listing_observations"] is mapped_listings
    assert builder.tables["people"] == []
