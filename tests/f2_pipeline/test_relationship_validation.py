import pytest

from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.relationship_validation import validate_identity_tables


def _fixture():
    sources = {
        "f2_culturalmap_university": {
            "mapped_subjects": [],
            "mapped_listing_observations": [],
            "mapped_locations": [],
            "category_assertions": [],
        },
        "f2_cultural_market_civil": {"areas": [], "locations": []},
        "f2_apptech_mtr": {"innovations": [], "source_observations": []},
        "f2_icommunity": {
            "innovations": [],
            "source_observations": [],
            "locations": [],
        },
        "f2_target_household": {"innovations": [], "source_observations": []},
        "f2_apptech_mru": {"innovations": [], "source_observations": []},
    }
    domains = {
        "areas": {
            "global_cultural_areas": [],
            "area_crosswalk": [],
            "area_assertions": [],
        },
        "activities": {
            "global_activities": [],
            "activity_crosswalk": [],
            "publications": [],
            "activity_publication_links": [],
            "activity_venues": [],
            "activity_media": [],
            "activity_narrative_evidence": [],
        },
        "innovations": {
            "global_innovations": [],
            "innovation_crosswalk": [],
            "source_records": [],
            "readiness_evidence": [],
            "innovation_use_locations": [],
            "measure_contributions": [],
        },
        "people": {
            "global_people": [],
            "person_crosswalk": [],
            "person_assertions": [],
            "person_location_admission": [],
            "person_location_assertions": [],
            "assessment_observations": [],
            "development_assessments": [],
            "development_scores": [],
            "assessment_admission": [],
            "measure_contributions": [],
        },
    }
    root = {
        "entity_contributions": [],
        "evidence_links": [],
        "eligibility_evidence": [],
        "province_memberships": [],
        "category_memberships": [],
    }
    provinces = [{"province_code": "10", "province_name_th": "Bangkok"}]
    return root, sources, domains, provinces


def _root_identity(root, measure, entity, table, key):
    root["entity_contributions"].append(
        {"measure_id": measure, "entity_id": entity, "label": entity}
    )
    root["evidence_links"].append(
        {
            "measure_id": measure,
            "entity_id": entity,
            "table": table,
            "key": key,
            "record_id": entity,
            "evidence_role": "counted_identity",
        }
    )


def test_category_membership_rejects_an_assertion_for_another_subject():
    root, sources, domains, provinces = _fixture()
    sources["f2_culturalmap_university"]["mapped_subjects"] = [
        {"subject_id": "subject-1", "k12_eligible": "True"},
        {"subject_id": "subject-2", "k12_eligible": "False"},
    ]
    sources["f2_culturalmap_university"]["mapped_listing_observations"] = [
        {"listing_id": "listing-1", "subject_id": "subject-1"}
    ]
    sources["f2_culturalmap_university"]["category_assertions"] = [
        {
            "category_assertion_id": "category-2",
            "subject_id": "subject-2",
            "category_code": "CS",
            "category_kind": "primary",
        }
    ]
    _root_identity(
        root,
        "K12",
        "subject-1",
        "sources/f2_culturalmap_university/mapped_subjects",
        "subject_id",
    )
    root["eligibility_evidence"].append(
        {
            "measure_id": "K12",
            "entity_id": "subject-1",
            "evidence_table": "sources/f2_culturalmap_university/mapped_listing_observations",
            "evidence_key": "listing_id",
            "evidence_id": "listing-1",
            "evidence_role": "source_mapped_listing",
        }
    )
    root["category_memberships"] = [
        {
            "measure_id": "K12",
            "entity_id": "subject-1",
            "category_code": "CS",
            "category_kind": "primary",
            "evidence_table": "sources/f2_culturalmap_university/category_assertions",
            "evidence_key": "category_assertion_id",
            "evidence_id": "category-2",
        }
    ]

    with pytest.raises(
        PipelineError, match="category assertion preserves subject/category"
    ):
        validate_identity_tables(root, sources, domains, provinces, ["K12"])


def test_province_membership_rejects_a_location_owned_by_another_innovation():
    root, sources, domains, provinces = _fixture()
    innovations = domains["innovations"]
    innovations["global_innovations"] = [
        {"global_innovation_id": "innovation-1", "qualifies_k04": "True"},
        {"global_innovation_id": "innovation-2", "qualifies_k04": "False"},
    ]
    innovations["innovation_crosswalk"] = [
        {
            "source": "rinmp",
            "local_innovation_id": "local-1",
            "global_innovation_id": "innovation-1",
        },
        {
            "source": "rinmp",
            "local_innovation_id": "local-2",
            "global_innovation_id": "innovation-2",
        },
    ]
    sources["f2_apptech_mtr"]["innovations"] = [
        {"innovation_id": "local-1"},
        {"innovation_id": "local-2"},
    ]
    sources["f2_apptech_mtr"]["source_observations"] = [
        {
            "observation_id": "observation-1",
            "source_id": "source-1",
            "row_locator": "evidence://f2_apptech_mtr/run/items.json#data/0",
        },
        {
            "observation_id": "observation-2",
            "source_id": "source-2",
            "row_locator": "evidence://f2_apptech_mtr/run/items.json#data/1",
        },
    ]
    innovations["readiness_evidence"] = [
        {
            "assessment_id": "assessment-1",
            "source": "rinmp",
            "local_innovation_id": "local-1",
            "global_innovation_id": "innovation-1",
            "qualifies_k04": "True",
        }
    ]
    innovations["source_records"] = [
        {
            "source": "rinmp",
            "local_innovation_id": "local-1",
            "global_innovation_id": "innovation-1",
            "observation_id": "observation-1",
            "source_id": "source-1",
            "raw_file": "evidence://f2_apptech_mtr/run/items.json",
            "row_locator": "data/0",
        },
        {
            "source": "rinmp",
            "local_innovation_id": "local-2",
            "global_innovation_id": "innovation-2",
            "observation_id": "observation-2",
            "source_id": "source-2",
            "raw_file": "evidence://f2_apptech_mtr/run/items.json",
            "row_locator": "data/1",
        },
    ]
    sources["f2_apptech_mtr"]["location_assertions"] = [
        {
            "location_id": "location-2",
            "innovation_id": "local-2",
            "observation_id": "observation-2",
            "province_code": "10",
            "location_role": "declared_innovation_use",
            "coverage_eligibility": "eligible_innovation_use",
        }
    ]
    innovations["innovation_use_locations"] = [
        {
            "location_id": "location-2",
            "source": "rinmp",
            "local_innovation_id": "local-2",
            "global_innovation_id": "innovation-2",
            "observation_id": "observation-2",
            "province_code": "10",
            "location_role": "declared_innovation_use",
            "coverage_eligibility": "eligible_innovation_use",
        }
    ]
    innovations["measure_contributions"] = [
        {"measure": "C04_LISTED", "global_innovation_id": "innovation-1"},
        {"measure": "C04_LISTED", "global_innovation_id": "innovation-2"},
        {
            "measure": "K04",
            "global_innovation_id": "innovation-1",
            "qualifying_assessment_ids_json": '["assessment-1"]',
        },
    ]
    _root_identity(
        root,
        "K04",
        "innovation-1",
        "domains/innovations/global_innovations",
        "global_innovation_id",
    )
    root["eligibility_evidence"].append(
        {
            "measure_id": "K04",
            "entity_id": "innovation-1",
            "evidence_table": "domains/innovations/readiness_evidence",
            "evidence_key": "assessment_id",
            "evidence_id": "assessment-1",
            "evidence_role": "qualifying_readiness_assessment",
        }
    )
    root["province_memberships"] = [
        {
            "measure_id": "K04",
            "entity_id": "innovation-1",
            "province_code": "10",
            "location_role": "declared_innovation_use",
            "evidence_table": "domains/innovations/innovation_use_locations",
            "evidence_key": "location_id",
            "evidence_id": "location-2",
        }
    ]

    with pytest.raises(
        PipelineError, match="province evidence preserves entity/location/role"
    ):
        validate_identity_tables(root, sources, domains, provinces, ["K04"])


def test_person_assertion_rejects_an_orphan_source_entity():
    root, sources, domains, provinces = _fixture()
    people = domains["people"]
    people["global_people"] = [
        {
            "global_person_id": "person-1",
            "community_innovator_eligible": "True",
        }
    ]
    people["person_crosswalk"] = [
        {"source_entity_id": "entity-1", "global_person_id": "person-1"}
    ]
    people["person_assertions"] = [
        {
            "assertion_id": "assertion-1",
            "source_entity_id": "orphan-entity",
            "global_person_id": "person-1",
            "attached_global_person_ids_json": "[]",
            "identity_treatment": "source_role_assertion",
        }
    ]
    people["measure_contributions"] = [
        {"measure_id": "C02_COMMUNITY", "global_person_id": "person-1"},
    ]
    _root_identity(
        root,
        "C02_COMMUNITY",
        "person-1",
        "domains/people/global_people",
        "global_person_id",
    )

    with pytest.raises(PipelineError, match="person assertion ownership"):
        validate_identity_tables(root, sources, domains, provinces, ["C02_COMMUNITY"])


def test_counted_identity_requires_criterion_evidence():
    root, sources, domains, provinces = _fixture()
    sources["f2_culturalmap_university"]["mapped_subjects"] = [
        {"subject_id": "subject-1", "k12_eligible": "True"}
    ]
    sources["f2_culturalmap_university"]["mapped_listing_observations"] = [
        {"listing_id": "listing-1", "subject_id": "subject-1"}
    ]
    _root_identity(
        root,
        "K12",
        "subject-1",
        "sources/f2_culturalmap_university/mapped_subjects",
        "subject_id",
    )

    with pytest.raises(PipelineError, match="exact eligibility evidence set"):
        validate_identity_tables(root, sources, domains, provinces, ["K12"])


def test_attached_assertion_cannot_supply_person_role_eligibility():
    root, sources, domains, provinces = _fixture()
    people = domains["people"]
    people["global_people"] = [
        {
            "global_person_id": "person-1",
            "community_innovator_eligible": "True",
        }
    ]
    people["person_crosswalk"] = [
        {
            "source_entity_id": "entity-1",
            "global_person_id": "person-1",
        }
    ]
    people["person_assertions"] = [
        {
            "assertion_id": "attached-role",
            "source_entity_id": "entity-1",
            "global_person_id": "person-1",
            "attached_global_person_ids_json": '["person-1"]',
            "identity_treatment": "reviewed_evidence_attachment_only",
            "eligible_roles_json": '["community_innovator"]',
        }
    ]
    people["measure_contributions"] = [
        {
            "measure_id": "C02_COMMUNITY",
            "global_person_id": "person-1",
            "qualifying_assertion_ids_json": '["attached-role"]',
        },
    ]
    _root_identity(
        root,
        "C02_COMMUNITY",
        "person-1",
        "domains/people/global_people",
        "global_person_id",
    )
    root["eligibility_evidence"].append(
        {
            "measure_id": "C02_COMMUNITY",
            "entity_id": "person-1",
            "evidence_table": "domains/people/person_assertions",
            "evidence_key": "assertion_id",
            "evidence_id": "attached-role",
            "evidence_role": "source_supported_person_role",
        }
    )
    with pytest.raises(PipelineError, match="C02 eligibility assertion support"):
        validate_identity_tables(root, sources, domains, provinces, ["C02_COMMUNITY"])


def test_context_publication_and_evidence_are_retained_without_k03_contribution():
    root, sources, domains, provinces = _fixture()
    observation_id = "context-observation"
    sources["f2_culturalmap_university"]["source_observations"] = [
        {"observation_id": observation_id}
    ]
    activities = domains["activities"]
    activities["publications"] = [
        {
            "source_publication_id": "context-publication",
            "source": "cultural-map-v1",
            "source_key": "G-364",
            "observation_id": observation_id,
            "global_activity_id": "",
            "publication_role": "context_only",
            "raw_locator": "evidence://f2_culturalmap_university/run/activities.json#data/364",
        }
    ]
    activities["activity_publication_links"] = [
        {
            "source_publication_id": "context-publication",
            "global_activity_id": "",
            "source": "cultural-map-v1",
            "link_status": "context_only",
            "parent_or_session_role": "context_only",
            "reason": "No identifiable occurrence",
        }
    ]
    activities["activity_media"] = [
        {
            "media_id": "context-media",
            "global_activity_id": "",
            "observation_id": observation_id,
            "source_key": "activities:G-364",
            "raw_locator": "evidence://f2_culturalmap_university/run/activities.json#data/364/gallery_images/0",
        }
    ]
    activities["activity_narrative_evidence"] = [
        {
            "evidence_id": "context-narrative",
            "global_activity_id": "",
            "observation_id": observation_id,
            "source_key": "activities:G-364",
            "raw_locator": "evidence://f2_culturalmap_university/run/activities.json#data/364/description",
        }
    ]

    validate_identity_tables(root, sources, domains, provinces, [])

    assert activities["global_activities"] == []
    assert activities.get("measure_contributions", []) == []
    assert len(activities["publications"]) == 1
    assert len(activities["activity_media"]) == 1
    assert len(activities["activity_narrative_evidence"]) == 1


def test_rinmp_target_or_use_location_retains_source_role_and_lineage():
    root, sources, domains, provinces = _fixture()
    observation_id = "rinmp-observation"
    location_id = "rinmp-target-location"
    source_role = "target_or_use_address_party_name_match"
    coverage = "eligible_programme_target_or_use_coverage"
    sources["f2_apptech_mtr"]["innovations"] = [{"innovation_id": "rinmp-local"}]
    sources["f2_apptech_mtr"]["source_observations"] = [
        {
            "observation_id": observation_id,
            "source_id": "rinmp-source-record",
            "row_locator": "evidence://f2_apptech_mtr/run/app_tech.json#data/records/0",
        }
    ]
    sources["f2_apptech_mtr"]["location_assertions"] = [
        {
            "location_id": location_id,
            "innovation_id": "rinmp-local",
            "observation_id": observation_id,
            "location_role": source_role,
            "coverage_eligibility": coverage,
            "province_normalized": "Bangkok",
            "province_code": "10",
            "district_normalized": "",
            "district_code": "",
            "subdistrict_normalized": "",
            "subdistrict_code": "",
            "resolution_status": "resolved_thai_province",
        }
    ]
    innovations = domains["innovations"]
    innovations["global_innovations"] = [
        {
            "global_innovation_id": "rinmp-global",
            "qualifies_k04": "False",
        }
    ]
    innovations["innovation_crosswalk"] = [
        {
            "source": "rinmp",
            "local_innovation_id": "rinmp-local",
            "global_innovation_id": "rinmp-global",
        }
    ]
    innovations["source_records"] = [
        {
            "source": "rinmp",
            "local_innovation_id": "rinmp-local",
            "global_innovation_id": "rinmp-global",
            "observation_id": observation_id,
            "source_id": "rinmp-source-record",
            "raw_file": "evidence://f2_apptech_mtr/run/app_tech.json",
            "row_locator": "data/records/0",
        }
    ]
    innovations["innovation_use_locations"] = [
        {
            "global_innovation_id": "rinmp-global",
            "source": "rinmp",
            "local_innovation_id": "rinmp-local",
            "observation_id": observation_id,
            "location_id": location_id,
            "location_role": source_role,
            "coverage_eligibility": coverage,
            "province_normalized": "Bangkok",
            "province_code": "10",
            "district_normalized": "",
            "district_code": "",
            "subdistrict_normalized": "",
            "subdistrict_code": "",
            "resolution_status": "resolved_thai_province",
        }
    ]
    innovations["measure_contributions"] = [
        {
            "measure": "C04_LISTED",
            "global_innovation_id": "rinmp-global",
        }
    ]

    validate_identity_tables(root, sources, domains, provinces, [])

    assert innovations["innovation_use_locations"][0]["location_role"] == source_role
    assert (
        innovations["innovation_use_locations"][0]["coverage_eligibility"] == coverage
    )

    innovations["source_records"][0]["source_id"] = "another-source-record"
    with pytest.raises(PipelineError, match="pointer and observation ownership"):
        validate_identity_tables(root, sources, domains, provinces, [])
