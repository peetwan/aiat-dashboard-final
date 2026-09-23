from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
import pytest

from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.field_approval import (
    ALL_FIELDS_FIELD_APPROVAL_STATUS,
    APPROVAL_CONDITIONS,
    APPROVAL_ID,
    APPROVAL_V2_ID,
    APPROVED_DETAIL_MEASURES,
    PARTIAL_FIELD_APPROVAL_STATUS,
    V2_APPROVAL_CONDITIONS,
    V2_APPROVED_DETAIL_MEASURES,
    approval_scope_sha256,
    validate_detail_owner_approval,
    validate_embedded_detail_owner_approval,
)

from tools.f2_pipeline.public_details import (
    REQUIRED_MEASURES,
    build_details,
    price_source_snapshots,
)


POLICY_PATH = Path("config/f2_pipeline/public_projection_policy.json")


def _policy():
    policy = json.loads(POLICY_PATH.read_text())
    policy.pop("detail_owner_approval", None)
    policy["additional_field_review_status"] = "pending_owner_acceptance"
    policy["publication_approval_claimed"] = False
    return policy


def _approved_policy(*, version: int = 1):
    policy = _policy()
    if version == 1:
        approval_id = APPROVAL_ID
        measures = APPROVED_DETAIL_MEASURES
        conditions = APPROVAL_CONDITIONS
        review_status = PARTIAL_FIELD_APPROVAL_STATUS
    elif version == 2:
        approval_id = APPROVAL_V2_ID
        measures = V2_APPROVED_DETAIL_MEASURES
        conditions = V2_APPROVAL_CONDITIONS
        review_status = ALL_FIELDS_FIELD_APPROVAL_STATUS
    else:
        raise AssertionError(f"Unsupported approval test version: {version}")
    policy["additional_field_review_status"] = review_status
    policy["detail_owner_approval"] = {
        "approval_id": approval_id,
        "status": "accepted",
        "approved_measures": sorted(measures),
        "public_promotion_approved": False,
        "conditions": conditions,
        "scope_sha256": "",
    }
    policy["detail_owner_approval"]["scope_sha256"] = approval_scope_sha256(policy)
    return policy


def _definitions():
    return {"measures": [{"measure_id": measure} for measure in REQUIRED_MEASURES]}


def _add_mapped_subject(
    tables: dict,
    *,
    subject_id: str,
    display_title: str,
    source_keys: list[str],
    listing_titles: list[str] | None = None,
    identity_status: str = "source_listing_identity",
) -> None:
    titles = listing_titles or [display_title] * len(source_keys)
    assert len(titles) == len(source_keys)
    tables["entity_contributions"].append(
        {"measure_id": "K12", "entity_id": subject_id, "label": display_title}
    )
    tables["sources/f2_culturalmap_university/mapped_subjects"].append(
        {
            "subject_id": subject_id,
            "display_title": display_title,
            "identity_status": identity_status,
            "k12_eligible": True,
            "aliases_json": titles,
            "source_keys_json": source_keys,
        }
    )
    tables["sources/f2_culturalmap_university/mapped_listing_observations"].extend(
        {
            "listing_id": f"listing-{subject_id}-{index}",
            "subject_id": subject_id,
            "source_key": source_key,
            "title_normalized": title,
        }
        for index, (source_key, title) in enumerate(zip(source_keys, titles))
    )


def _tables():
    contributions = [
        {"measure_id": "K01B", "entity_id": "area-1", "label": "พื้นที่หนึ่ง"},
        {"measure_id": "K03", "entity_id": "activity-1", "label": "กิจกรรมหนึ่ง"},
        {"measure_id": "K04", "entity_id": "innovation-1", "label": "นวัตกรรมหนึ่ง"},
        {
            "measure_id": "C04_LISTED",
            "entity_id": "innovation-1",
            "label": "นวัตกรรมหนึ่ง",
        },
        {"measure_id": "K05", "entity_id": "operator-1", "label": "กลุ่มผู้ผลิตหนึ่ง"},
        {"measure_id": "K07", "entity_id": "family-1", "label": "ผลิตภัณฑ์หนึ่ง"},
        {
            "measure_id": "C08_PARTICIPATING",
            "entity_id": "business-1",
            "label": "ธุรกิจหนึ่ง",
        },
        {"measure_id": "K12", "entity_id": "subject-1", "label": "เรื่องวัฒนธรรมหนึ่ง"},
        {"measure_id": "K12", "entity_id": "subject-person", "label": "นาย บุคคลตัวอย่าง"},
        {
            "measure_id": "K12",
            "entity_id": "subject-work",
            "label": "การทอผ้าไหม นางปณภัช ศิริภัทรเดชากร",
        },
    ]
    return {
        "entity_contributions": contributions,
        "domains/areas/global_cultural_areas": [
            {
                "global_area_id": "area-1",
                "display_name": "พื้นที่หนึ่ง",
                "identity_status": "source_local_identity",
            }
        ],
        "domains/areas/area_crosswalk": [
            {
                "global_area_id": "area-1",
                "source_member_id": "area-member-1",
                "source": "atlocal",
                "local_entity_id": "area-local-1",
                "display_name": "พื้นที่หนึ่ง",
                "primary_category_codes_json": [],
            }
        ],
        "sources/f2_cultural_market_civil/areas": [
            {
                "area_id": "area-local-1",
                "name": "พื้นที่หนึ่ง",
                "description": "<p>เรื่องพื้นที่ ติดต่อ owner@example.test</p><script>secret</script>",
                "images_json": ["https://atlocalthailand.com/media/area.jpg"],
                "unknown_field": "do-not-publish",
            }
        ],
        "domains/activities/global_activities": [
            {
                "global_activity_id": "activity-1",
                "source": "atlocal-v1",
                "name": "กิจกรรมหนึ่ง",
                "identity_status": "source_local_identity",
            }
        ],
        "domains/activities/publications": [
            {
                "source_publication_id": "publication-1",
                "global_activity_id": "activity-1",
                "source": "atlocal-v1",
                "title": "ประกาศกิจกรรมหนึ่ง",
                "text": "รายละเอียดกิจกรรม",
                "published_at": "2026-01-01",
                "source_url": "https://atlocalthailand.com/festival/1",
                "publication_role": "parent",
            }
        ],
        "domains/activities/activity_dates": [
            {
                "date_assertion_id": "activity-date-1",
                "global_activity_id": "activity-1",
                "source": "atlocal-v1",
                "date_role": "occurrence",
                "parsed_start_date": "2026-02-01",
                "parsed_end_date": "2026-02-02",
                "parse_status": "parsed",
                "date_conflict": "False",
            }
        ],
        "domains/activities/activity_venues": [
            {
                "venue_assertion_id": "venue-1",
                "global_activity_id": "activity-1",
                "source": "atlocal-v1",
                "location_name_raw": "ศูนย์วัฒนธรรม",
                "location_role": "activity_venue",
                "province_code": "10",
                "province_normalized": "กรุงเทพมหานคร",
                "geography_status": "resolved",
            }
        ],
        "domains/activities/activity_sessions": [
            {
                "session_id": "session-1",
                "global_activity_id": "activity-1",
                "source": "atlocal-v1",
                "session_label": "ช่วงเช้า",
                "start_date": "2026-02-01",
                "end_date": "2026-02-01",
                "status": "source_reported",
            }
        ],
        "domains/activities/activity_sections": [
            {
                "section_id": "section-1",
                "global_activity_id": "activity-1",
                "source": "atlocal-v1",
                "text": "การสาธิตงานช่าง",
                "attribution": "อาจารย์ ผู้สาธิต",
            }
        ],
        "domains/innovations/global_innovations": [
            {
                "global_innovation_id": "innovation-1",
                "display_name": "นวัตกรรมหนึ่ง",
                "identity_status": "accepted_identity",
            }
        ],
        "domains/innovations/innovation_crosswalk": [
            {
                "global_innovation_id": "innovation-1",
                "source": "pmua_apptech",
                "local_innovation_id": "innovation-local-1",
                "local_display_name": "นวัตกรรมหนึ่ง",
                "local_identity_status": "source_local_identity",
            }
        ],
        "domains/innovations/source_records": [
            {
                "global_innovation_id": "innovation-1",
                "source": "pmua_apptech",
                "observation_id": "observation-innovation-1",
                "title_raw": "นวัตกรรมหนึ่ง",
                "raw_file": "/Users/private/raw.json",
                "row_locator": "/data/0",
            }
        ],
        "domains/innovations/readiness_evidence": [
            {
                "global_innovation_id": "innovation-1",
                "source": "pmua_apptech",
                "assessment_id": "readiness-1",
                "scale": "TRL",
                "numeric_level": "8",
                "label_raw": "พร้อมใช้",
                "qualifies_k04": "True",
                "basis": "valid_numeric_level",
                "assessment_context": "public_listing",
            }
        ],
        "domains/innovations/innovation_use_locations": [
            {
                "global_innovation_id": "innovation-1",
                "source": "pmua_apptech",
                "location_id": "innovation-location-1",
                "location_role": "declared_innovation_use",
                "province_code": "20",
                "province_normalized": "ชลบุรี",
                "resolution_status": "resolved",
            }
        ],
        "sources/f2_target_household/description_sections": [
            {
                "innovation_id": "innovation-local-1",
                "label_raw": "overview",
                "text_readable": "คำอธิบายนวัตกรรม",
                "unknown_blob": {"secret": "do-not-publish"},
            }
        ],
        "sources/f2_target_household/innovation_details": [
            {
                "innovation_id": "innovation-local-1",
                "detail_url": "https://pmua-apptech.com/product/10",
                "researcher_name_raw": "ดร. ผู้วิจัย ตัวอย่าง",
                "university_name_raw": "มหาวิทยาลัยตัวอย่าง",
            }
        ],
        "domains/commerce/global_operators": [
            {
                "global_operator_id": "operator-1",
                "display_name": "กลุ่มผู้ผลิตหนึ่ง",
                "identity_status": "accepted_identity",
            }
        ],
        "domains/commerce/operator_crosswalk": [
            {
                "global_operator_id": "operator-1",
                "source_operator_id": "atlocal:operator-local-1",
                "source": "atlocal",
                "display_name": "กลุ่มผู้ผลิตหนึ่ง",
                "identity_status": "source_local_identity",
            }
        ],
        "domains/commerce/global_offerings": [
            {
                "global_offering_id": "offering-1",
                "display_name": "ผลิตภัณฑ์รสเดิม",
                "identity_status": "accepted_identity",
            },
            {
                "global_offering_id": "offering-2",
                "display_name": "ผลิตภัณฑ์รสใหม่",
                "identity_status": "accepted_identity",
            },
        ],
        "domains/commerce/offering_crosswalk": [
            {
                "global_offering_id": "offering-1",
                "source_offering_id": "atlocal:offering-local-1",
                "source": "atlocal",
                "display_name": "ผลิตภัณฑ์รสเดิม",
                "identity_status": "source_local_identity",
            },
            {
                "global_offering_id": "offering-2",
                "source_offering_id": "cultural_map:offering-local-2",
                "source": "cultural_map",
                "display_name": "ผลิตภัณฑ์รสใหม่",
                "identity_status": "source_local_identity",
            },
        ],
        "domains/commerce/locations": [
            {
                "source_location_id": "operator-location-1",
                "global_operator_id": "operator-1",
                "global_offering_id": "",
                "source": "atlocal",
                "location_role": "operator_place",
                "province_code": "10",
                "province_normalized": "กรุงเทพมหานคร",
                "status": "resolved",
            },
            {
                "source_location_id": "offering-location-1",
                "global_operator_id": "",
                "global_offering_id": "offering-1",
                "source": "atlocal",
                "location_role": "offering_place",
                "province_code": "20",
                "province_normalized": "ชลบุรี",
                "status": "resolved",
            },
        ],
        "domains/commerce/operator_offering_edges": [
            {
                "source_operator_offering_edge_id": "edge-1",
                "global_operator_id": "operator-1",
                "global_offering_id": "offering-1",
                "source": "atlocal",
                "relationship": "seller_of",
            }
        ],
        "domains/commerce/reviewed_evidence": [
            {
                "evidence_id": "reviewed-operator-1",
                "global_operator_id": "operator-1",
                "global_offering_id": "",
                "global_innovation_id": "",
                "source": "atlocal",
                "relationship": "public_business_listing",
                "evidence_text": "รายชื่อธุรกิจจากหน้าสาธารณะ",
            },
            {
                "evidence_id": "reviewed-offering-1",
                "global_operator_id": "",
                "global_offering_id": "offering-1",
                "global_innovation_id": "innovation-1",
                "source": "atlocal",
                "relationship": "reviewed_output_of",
                "evidence_text": "ผลงานที่ตรวจหลักฐานแล้ว",
            },
        ],
        "domains/commerce/person_operator_links": [
            {
                "global_operator_id": "operator-1",
                "global_person_id": "private-person",
                "evidence_text": "do-not-publish-person",
            }
        ],
        "domains/commerce/offering_families": [
            {
                "family_id": "family-1",
                "display_name": "ผลิตภัณฑ์หนึ่ง",
                "identity_status": "reviewed_product_family",
            }
        ],
        "domains/commerce/offering_family_members": [
            {
                "family_id": "family-1",
                "global_offering_id": "offering-1",
                "membership_role": "family_representation",
            },
            {
                "family_id": "family-1",
                "global_offering_id": "offering-2",
                "membership_role": "variant",
            },
        ],
        "domains/commerce/listing_evidence": [
            {
                "source_listing_id": "listing-offering-1",
                "global_offering_id": "offering-1",
                "source": "atlocal",
                "title_normalized": "ผลิตภัณฑ์รสเดิม",
                "description": "รายละเอียดสินค้า",
                "category_raw": "อาหาร",
                "source_url": "https://atlocalthailand.com/product/1?token=unsafe",
                "raw_locator": "/Users/private/raw.json#/0",
                "unknown_field": "do-not-publish",
            }
        ],
        "domains/commerce/prices": [
            {
                "source_price_id": "price-1",
                "global_offering_id": "offering-1",
                "source": "atlocal",
                "amounts_json": [0, 125],
                "currency": "THB",
                "parse_status": "source_reported_price",
                "price_text_raw": "private raw price text",
            },
            {
                "source_price_id": "price-2",
                "global_offering_id": "offering-1",
                "source": "atlocal",
                "amounts_json": ["12.50"],
                "currency": "THB",
                "parse_status": "source_reported_price",
            },
            {
                "source_price_id": "price-3",
                "global_offering_id": "offering-1",
                "source": "atlocal",
                "amounts_json": ["0812345678"],
                "currency": "THB",
                "parse_status": "source_reported_price",
            },
            {
                "source_price_id": "price-4",
                "global_offering_id": "offering-1",
                "source": "atlocal",
                "amounts_json": ["250"],
                "currency": "",
                "parse_status": "source_reported_price",
            },
            {
                "source_price_id": "price-5",
                "global_offering_id": "offering-1",
                "source": "atlocal",
                "amounts_json": ["300"],
                "currency": "THB",
                "parse_status": "unreviewed_parser_result",
            },
        ],
        "domains/commerce/media": [
            {
                "source_media_id": "media-offering-1",
                "global_offering_id": "offering-1",
                "source": "atlocal",
                "media_kind": "image",
                "url_or_value": "https://atlocalthailand.com/media/product.jpg",
                "status": "source_reference",
            }
        ],
        "sources/f2_learning_area_based/businesses": [
            {
                "business_id": "business-1",
                "display_name": "ธุรกิจหนึ่ง",
                "identity_status": "provisional_unit",
            }
        ],
        "sources/f2_learning_area_based/participations": [
            {
                "participation_id": "participation-1",
                "business_id": "business-1",
                "project_assertion_id": "project-1",
                "research_unit_assertion_id": "unit-1",
                "fiscal_year_be": "2568",
            }
        ],
        "sources/f2_learning_area_based/project_assertions": [
            {
                "assertion_id": "project-1",
                "project_name_raw": "โครงการหนึ่ง",
                "unknown_field": "do-not-publish",
            }
        ],
        "sources/f2_learning_area_based/research_unit_assertions": [
            {"assertion_id": "unit-1", "research_unit_raw": "หน่วยวิจัยหนึ่ง"}
        ],
        "sources/f2_learning_area_based/locations": [
            {
                "location_id": "business-location-1",
                "business_id": "business-1",
                "location_role": "programme_business_location",
                "province_code": "30",
                "province_normalized": "นครราชสีมา",
                "resolution_status": "resolved",
            }
        ],
        "sources/f2_culturalmap_university/mapped_subjects": [
            {
                "subject_id": "subject-1",
                "display_title": "เรื่องวัฒนธรรมหนึ่ง",
                "identity_status": "source_listing_identity",
                "k12_eligible": True,
                "aliases_json": ["เรื่องวัฒนธรรมหนึ่ง"],
                "source_keys_json": ["map:1"],
            },
            {
                "subject_id": "subject-person",
                "display_title": "กมลชนก จาระรัมย์ ยาย",
                "identity_status": "source_listing_identity",
                "k12_eligible": True,
                "aliases_json": ["กมลชนก จาระรัมย์ ยาย"],
                "source_keys_json": ["map:person"],
            },
            {
                "subject_id": "subject-work",
                "display_title": "การทอผ้าไหม นางปณภัช ศิริภัทรเดชากร",
                "identity_status": "source_listing_identity",
                "k12_eligible": True,
                "aliases_json": ["การทอผ้าไหม นางปณภัช ศิริภัทรเดชากร"],
                "source_keys_json": ["map:work"],
            },
        ],
        "sources/f2_culturalmap_university/mapped_listing_observations": [
            {
                "listing_id": "mapped-listing-1",
                "subject_id": "subject-1",
                "source_key": "map:1",
                "title_normalized": "เรื่องวัฒนธรรมหนึ่ง",
                "source_url": "https://www.culturalmapthailand.info/CD-1",
                "dates_json": {"published": "2026-01-01"},
                "unknown_field": "do-not-publish",
            },
            {
                "listing_id": "mapped-listing-person",
                "subject_id": "subject-person",
                "source_key": "map:person",
                "title_normalized": "กมลชนก จาระรัมย์ ยาย",
                "people_summary_json": {"informants_raw": "นางกมลชนก จาระรัมย์"},
            },
            {
                "listing_id": "mapped-listing-work",
                "subject_id": "subject-work",
                "source_key": "map:work",
                "title_normalized": "การทอผ้าไหม นางปณภัช ศิริภัทรเดชากร",
                "people_summary_json": {"informants_raw": "นางปณภัช ศิริภัทรเดชากร"},
            },
        ],
        "sources/f2_culturalmap_university/mapped_locations": [
            {
                "location_id": "mapped-location-1",
                "subject_id": "subject-1",
                "source_key": "map:1",
                "location_role": "mapped_subject",
                "province_code": "40",
                "province_normalized": "ขอนแก่น",
                "status": "resolved",
                "latitude": "16.0",
                "longitude": "102.0",
                "address_raw": "do-not-publish",
            }
        ],
        "sources/f2_culturalmap_university/category_assertions": [
            {
                "category_assertion_id": "category-1",
                "subject_id": "subject-1",
                "category_code": "CS",
            }
        ],
        "sources/f2_culturalmap_university/mapped_narrative_evidence": [
            {
                "evidence_id": "narrative-1",
                "subject_id": "subject-1",
                "source_key": "map:1",
                "field_name": "history",
                "text": "ประวัติชุมชน",
            },
            {
                "evidence_id": "narrative-private",
                "subject_id": "subject-1",
                "source_key": "map:1",
                "field_name": "identity",
                "text": "file:///Users/private/evidence.html",
            },
            {
                "evidence_id": "narrative-address",
                "subject_id": "subject-1",
                "source_key": "map:1",
                "field_name": "history",
                "text": "บ้านเลขที่ 123 หมู่ 4",
            },
        ],
        "sources/f2_culturalmap_university/mapped_media": [
            {
                "media_id": "mapped-media-1",
                "subject_id": "subject-1",
                "media_kind": "image",
                "url_or_value": "https://dp.culturalmapthailand.info/image.jpg",
                "label": "บ้านเลขที่ 123 หมู่ 4",
                "status": "source_reference",
            }
        ],
        "domains/people/development_assessments": [
            {
                "assessment_id": "private-assessment",
                "global_person_id": "private-person",
                "complete": "True",
            }
        ],
        "domains/people/development_scores": [
            {
                "assessment_id": "private-assessment",
                "dimension": "income",
                "current_score": "10",
            }
        ],
    }


def test_each_required_entity_topic_has_a_useful_candidate_or_honest_withholding():
    details = build_details(_tables(), _definitions(), _policy())

    assert set(details) == set(REQUIRED_MEASURES)
    for measure in REQUIRED_MEASURES:
        assert details[measure]["details"] or details[measure]["withheld"]
        assert not (
            set(details[measure]["details"]) & set(details[measure]["withheld"])
        )
    assert details["K12"]["withheld"] == {}
    assert set(details["K12"]["details"]) == {
        "subject-1",
        "subject-person",
        "subject-work",
    }


def test_owner_field_approval_is_scoped_and_cannot_authorize_promotion():
    policy = _approved_policy()
    details = build_details(_tables(), _definitions(), policy)

    for measure in APPROVED_DETAIL_MEASURES:
        assert {
            row["flags"]["additional_field_review_status"]
            for row in details[measure]["details"].values()
        } == {"accepted_by_owner"}
    for measure in ("K01B", "K12"):
        assert {
            row["flags"]["additional_field_review_status"]
            for row in details[measure]["details"].values()
        } == {"pending_owner_acceptance"}
    assert policy["detail_owner_approval"]["public_promotion_approved"] is False
    assert (
        details["K04"]["details"]["innovation-1"]
        == details["C04_LISTED"]["details"]["innovation-1"]
    )

    broadened = deepcopy(policy)
    broadened["detail_policies"]["K03"]["detail_fields"].append("future_field")
    with pytest.raises(PipelineError, match="scope hash"):
        validate_detail_owner_approval(broadened)

    promotion_claim = deepcopy(policy)
    promotion_claim["publication_approval_claimed"] = True
    with pytest.raises(PipelineError, match="cannot authorize"):
        validate_detail_owner_approval(promotion_claim)


def test_v2_approves_all_detail_measures_without_expanding_content_or_promotion():
    tables = deepcopy(_tables())
    _add_mapped_subject(
        tables,
        subject_id="CD-5342",
        display_title="CD-5342 080-000-0000",
        source_keys=["map:CD-5342"],
    )
    v1_details = build_details(tables, _definitions(), _approved_policy())
    v2_policy = _approved_policy(version=2)
    v2_details = build_details(tables, _definitions(), v2_policy)

    v1_policy = _approved_policy()
    assert validate_detail_owner_approval(v1_policy) is not None
    assert validate_detail_owner_approval(v2_policy) is not None
    for policy in (v1_policy, v2_policy):
        assert (
            validate_embedded_detail_owner_approval(
                {
                    "additional_field_review_status": policy[
                        "additional_field_review_status"
                    ],
                    "detail_owner_approval": policy["detail_owner_approval"],
                }
            )
            == policy["detail_owner_approval"]
        )
    for measure in V2_APPROVED_DETAIL_MEASURES:
        assert {
            row["flags"]["additional_field_review_status"]
            for row in v2_details[measure]["details"].values()
        } == {"accepted_by_owner"}
    assert v2_policy["detail_owner_approval"]["public_promotion_approved"] is False
    assert v2_policy["publication_approval_claimed"] is False
    cd5342 = v2_details["K12"]["details"]["CD-5342"]
    assert cd5342["label"] == "Title withheld pending review"
    assert cd5342["listings"][0]["label"] == "Title withheld pending review"

    for details in (v1_details, v2_details):
        for by_id in details.values():
            for detail in by_id["details"].values():
                detail["flags"].pop("additional_field_review_status", None)
    assert v2_details == v1_details

    broadened = deepcopy(v2_policy)
    broadened["detail_policies"]["K12"]["detail_fields"].append("future_field")
    with pytest.raises(PipelineError, match="scope hash"):
        validate_detail_owner_approval(broadened)

    promotion_claim = deepcopy(v2_policy)
    promotion_claim["detail_owner_approval"]["public_promotion_approved"] = True
    with pytest.raises(PipelineError, match="accepted scope"):
        validate_detail_owner_approval(promotion_claim)

    weakened_title_condition = deepcopy(v2_policy)
    weakened_title_condition["detail_owner_approval"]["conditions"][
        "cultural_title"
    ] = "title_available"
    with pytest.raises(PipelineError, match="accepted scope"):
        validate_detail_owner_approval(weakened_title_condition)


def test_cultural_area_and_activity_adapters_keep_supported_children_not_child_entities():
    details = build_details(_tables(), _definitions(), _policy())

    area = details["K01B"]["details"]["area-1"]
    assert area["relationships"][0]["kind"] == "source_membership"
    assert area["media"][0]["url"].endswith("/media/area.jpg")
    assert area["media"][0]["reference_only"] is True
    assert area["media"][0]["status"] == "source_reference_not_fetched"
    assert "owner@example.test" not in area["descriptions"][0]["text"]

    activity = details["K03"]["details"]["activity-1"]
    assert activity["province_codes"] == ["10"]
    assert activity["locations"][0]["location_role"] == "activity_venue"
    assert activity["listings"][0]["publication_id"] == "publication-1"
    assert activity["children"]["dates"][0]["date_id"] == "activity-date-1"
    assert activity["children"]["sessions"][0]["session_id"] == "session-1"
    assert activity["children"]["sections"][0]["attribution"] == "อาจารย์ ผู้สาธิต"
    assert set(details["K03"]["details"]) == {"activity-1"}
    assert activity["source_ids"] == ["f2_cultural_market_civil"]


def test_activity_domain_source_aliases_use_canonical_policy_sources():
    activity_tables = (
        "domains/activities/global_activities",
        "domains/activities/publications",
        "domains/activities/activity_dates",
        "domains/activities/activity_venues",
        "domains/activities/activity_sessions",
        "domains/activities/activity_sections",
    )
    for domain_source, expected_source_id in (
        ("atlocal-v1", "f2_cultural_market_civil"),
        ("cultural-map-v1", "f2_culturalmap_university"),
        ("icommunity-v1", "f2_icommunity"),
    ):
        tables = deepcopy(_tables())
        for table_name in activity_tables:
            for row in tables[table_name]:
                row["source"] = domain_source

        detail = build_details(tables, _definitions(), _policy())["K03"]["details"][
            "activity-1"
        ]

        assert detail["source_ids"] == [expected_source_id]


def test_shared_innovation_detail_keeps_readiness_sources_use_and_work_context():
    details = build_details(_tables(), _definitions(), _policy())

    k04 = details["K04"]["details"]["innovation-1"]
    listed = details["C04_LISTED"]["details"]["innovation-1"]
    assert k04 == listed
    assert k04["province_codes"] == ["20"]
    assert k04["locations"][0]["location_role"] == "declared_innovation_use"
    assert k04["children"]["readiness"][0]["numeric_level"] == "8"
    assert k04["children"]["readiness"][0]["qualifies"] is True
    assert k04["children"]["source_records"][0]["source_id"] == "f2_target_household"
    assert k04["children"]["work_attributions"][0]["attribution"] == "ดร. ผู้วิจัย ตัวอย่าง"
    assert k04["children"]["organizations"][0]["organization"] == "มหาวิทยาลัยตัวอย่าง"
    assert k04["listings"][0]["source_url"] == "https://pmua-apptech.com/product/10"
    assert k04["listings"][0]["link_scope"] == "record"


def test_operator_and_offering_geography_remain_owned_and_all_variants_survive():
    details = build_details(_tables(), _definitions(), _policy())

    operator = details["K05"]["details"]["operator-1"]
    assert operator["province_codes"] == ["10"]
    assert operator["locations"][0]["location_role"] == "operator_place"
    assert operator["flags"]["geography_not_borrowed_from_offerings"] is True
    assert operator["flags"]["person_relationships_withheld"] is True
    assert "do-not-publish-person" not in json.dumps(operator, ensure_ascii=False)
    assert operator["flags"]["identity_review"] == {
        "outcome": "source_record_only",
        "merge_scope": None,
        "counting": "separate",
        "name_quality": "supported",
    }

    family = details["K07"]["details"]["family-1"]
    offerings = family["children"]["offerings"]
    assert [item["membership_role"] for item in offerings] == [
        "family_representation",
        "variant",
    ]
    assert family["flags"]["all_preserved_offerings_included"] is True
    assert family["flags"]["variants_are_children_not_entities"] is True
    assert family["flags"]["identity_review"] == {
        "outcome": "grouped_family",
        "merge_scope": None,
        "counting": "grouped",
        "name_quality": "supported",
    }
    assert family["province_codes"] == ["20"]
    assert offerings[0]["locations"][0]["location_role"] == "offering_place"
    assert offerings[0]["children"]["prices"][0]["amounts"] == [
        {
            "value": 0,
            "status": "unspecified",
            "display_label": "price unspecified/source reports 0",
        },
        {"value": 125, "status": "source_reported"},
    ]
    assert offerings[0]["children"]["prices"][0]["currency"] == "THB"
    assert offerings[0]["children"]["prices"][0]["unit"] is None
    assert offerings[0]["children"]["prices"][0]["unit_status"] == "not_reported"
    assert offerings[0]["children"]["prices"][1]["amounts"] == [
        {"value": "12.50", "status": "source_reported"}
    ]
    assert offerings[0]["children"]["prices"][1]["currency"] == "THB"
    assert offerings[0]["child_dispositions"]["prices"] == {
        "candidate_count": 5,
        "emitted_count": 2,
        "withheld_count": 3,
        "withheld_reasons": {
            "price_amount_admission_failed": 1,
            "missing_or_unapproved_price_currency": 1,
            "unapproved_price_parse_status": 1,
        },
    }
    assert (
        offerings[0]["children"]["innovation_context"][0]["entity_id"] == "innovation-1"
    )
    assert offerings[0]["listings"][0]["source_url"] is None


def test_operator_identity_review_marks_explicit_keep_separate_decision():
    tables = deepcopy(_tables())
    tables["domains/commerce/operator_crosswalk"][0]["source_details_json"] = json.dumps(
        {"candidate_id": "operator-candidate-1"}
    )
    tables["domains/commerce/reviewed_identity_decisions"] = [
        {
            "review_id": "keep-separate-1",
            "left": "operator-candidate-1",
            "right": "operator-candidate-2",
            "decision": "keep_separate",
        }
    ]

    operator = build_details(tables, _definitions(), _policy())["K05"]["details"][
        "operator-1"
    ]

    assert operator["flags"]["identity_review"] == {
        "outcome": "kept_separate",
        "merge_scope": None,
        "counting": "separate",
        "name_quality": "supported",
    }


def test_identity_review_distinguishes_cross_and_within_source_merges():
    tables = deepcopy(_tables())
    tables["domains/innovations/global_innovations"][0]["identity_status"] = (
        "reviewed_cross_source"
    )
    tables["sources/f2_learning_area_based/businesses"][0]["identity_status"] = (
        "supported_within_source_merge"
    )

    details = build_details(tables, _definitions(), _policy())

    assert details["K04"]["details"]["innovation-1"]["flags"]["identity_review"] == {
        "outcome": "merged",
        "merge_scope": "cross_source",
        "counting": "merged",
        "name_quality": "supported",
    }
    assert details["C08_PARTICIPATING"]["details"]["business-1"]["flags"][
        "identity_review"
    ] == {
        "outcome": "merged",
        "merge_scope": "within_source",
        "counting": "merged",
        "name_quality": "supported",
    }


def test_attributed_media_references_reject_credential_urls_without_fetch_claims():
    tables = deepcopy(_tables())
    tables["domains/commerce/media"].append(
        {
            "source_media_id": "media-token",
            "global_offering_id": "offering-1",
            "source": "atlocal",
            "media_kind": "image",
            "url_or_value": "https://atlocalthailand.com/media/product.jpg?token=private",
            "status": "source_reference",
        }
    )

    offering = build_details(tables, _definitions(), _policy())["K07"]["details"][
        "family-1"
    ]["children"]["offerings"][0]
    assert offering["media"] == [
        {
            "media_id": "media-offering-1",
            "kind": "image",
            "url": "https://atlocalthailand.com/media/product.jpg",
            "label": None,
            "label_availability": "not_provided",
            "label_withholding_reason": None,
            "status": "source_reference_not_fetched",
            "reference_only": True,
            "source_id": "f2_cultural_market_civil",
        }
    ]
    assert "token" not in json.dumps(offering["media"], ensure_ascii=False)
    assert offering["child_dispositions"]["media"]["withheld_reasons"] == {
        "unsafe_or_unapproved_media_reference": 1
    }


def test_member_prices_keep_distinct_source_snapshots_and_no_invented_as_of_or_unit():
    tables = deepcopy(_tables())
    for price in tables["domains/commerce/prices"]:
        price["observation_id"] = "observation-atlocal-price"
    tables["domains/commerce/prices"].append(
        {
            "source_price_id": "price-cultural-member",
            "global_offering_id": "offering-2",
            "observation_id": "observation-cultural-price",
            "source": "cultural_map",
            "amounts_json": ["999"],
            "currency": "THB",
            "parse_status": "parsed",
            "qualifier_raw": "ตามไซส์",
        }
    )
    tables["sources/f2_cultural_market_civil/source_observations"] = [
        {
            "observation_id": "observation-atlocal-price",
            "dataset": "marketplace_products",
            "captured_at": "2026-08-25T07:05:10.401066+00:00",
        }
    ]
    tables["sources/f2_culturalmap_university/source_observations"] = [
        {
            "observation_id": "observation-cultural-price",
            "dataset": "products",
            "captured_at": "2026-08-20T14:32:52.774837+00:00",
        }
    ]
    manifest = [
        {
            "source_id": "f2_cultural_market_civil",
            "dataset_key": "marketplace_products",
            "run_id": "20260825T070510Z",
            "captured_at": "2026-08-25T07:05:10.401066+00:00",
        },
        {
            "source_id": "f2_culturalmap_university",
            "dataset_key": "products",
            "run_id": "20260820T142533Z",
            "captured_at": "2026-08-20T14:32:52.774837+00:00",
        },
    ]

    family = build_details(
        tables, _definitions(), _approved_policy(), input_manifest=manifest
    )["K07"]["details"]["family-1"]
    original, variant = family["children"]["offerings"]
    original_prices = original["children"]["prices"]
    variant_prices = variant["children"]["prices"]

    assert [price["price_id"] for price in original_prices] == ["price-1", "price-2"]
    assert [price["price_id"] for price in variant_prices] == ["price-cultural-member"]
    assert variant_prices[0]["amounts"] == [
        {"value": "999", "status": "source_reported"}
    ]
    assert variant_prices[0]["unit"] is None
    assert variant_prices[0]["unit_status"] == "not_reported"
    assert "ตามไซส์" not in json.dumps(variant_prices[0], ensure_ascii=False)
    assert all(
        price["price_as_of"] is None for price in original_prices + variant_prices
    )
    assert all(
        price["price_as_of_status"] == "not_reported"
        for price in original_prices + variant_prices
    )
    assert (
        original_prices[0]["source_snapshot_ref"]
        != variant_prices[0]["source_snapshot_ref"]
    )
    snapshots = price_source_snapshots(tables, _approved_policy(), manifest)
    assert {
        (
            row["source_id"],
            row["run_id"],
            row["captured_at"],
            row["price_as_of"],
        )
        for row in snapshots.values()
    } == {
        (
            "f2_cultural_market_civil",
            "20260825T070510Z",
            "2026-08-25T07:05:10.401066+00:00",
            None,
        ),
        (
            "f2_culturalmap_university",
            "20260820T142533Z",
            "2026-08-20T14:32:52.774837+00:00",
            None,
        ),
    }


def test_explicit_allowlisted_sale_unit_is_reported_without_per_item_inference():
    tables = deepcopy(_tables())
    tables["domains/commerce/prices"][1]["unit"] = "ชิ้น"
    policy = _approved_policy()
    policy["detail_policies"]["K07"]["source_allowlists"]["atlocal"]["price"].append(
        "unit"
    )
    policy["detail_owner_approval"]["scope_sha256"] = approval_scope_sha256(policy)

    prices = build_details(tables, _definitions(), policy)["K07"]["details"][
        "family-1"
    ]["children"]["offerings"][0]["children"]["prices"]

    assert prices[0]["unit"] is None
    assert prices[0]["unit_status"] == "not_reported"
    assert prices[1]["unit"] == "ชิ้น"
    assert prices[1]["unit_status"] == "source_reported"


def test_mapped_person_subjects_and_credited_works_keep_identity_and_safe_material():
    tables = deepcopy(_tables())
    person_listing = next(
        row
        for row in tables[
            "sources/f2_culturalmap_university/mapped_listing_observations"
        ]
        if row["subject_id"] == "subject-person"
    )
    person_listing["people_summary_json"] = {
        "informants_raw": "นางกมลชนก จาระรัมย์",
        "contact_raw": "private-person@example.invalid",
    }
    person_listing["assessment_json"] = {
        "financial_health": "synthetic-private-assessment"
    }
    tables["sources/f2_culturalmap_university/mapped_locations"].append(
        {
            "location_id": "mapped-location-person",
            "subject_id": "subject-person",
            "source_key": "map:person",
            "location_role": "mapped_subject",
            "province_code": "40",
            "province_normalized": "ขอนแก่น",
            "latitude": "16.1000",
            "longitude": "102.1000",
            "address_raw": "synthetic-private-address",
            "status": "resolved",
        }
    )

    details = build_details(tables, _definitions(), _policy())

    assert details["K12"]["withheld"] == {}
    assert set(details["K12"]["details"]) == {
        row["entity_id"]
        for row in tables["entity_contributions"]
        if row["measure_id"] == "K12"
    }
    person = details["K12"]["details"]["subject-person"]
    assert person["entity_id"] == "subject-person"
    assert person["identity_status"] == "source_listing_identity"
    assert person["label"] == "กมลชนก จาระรัมย์ ยาย"
    assert person["listings"] == [
        {
            "listing_id": "mapped-listing-person",
            "label": "กมลชนก จาระรัมย์ ยาย",
            "label_availability": "available",
            "label_withholding_reason": None,
            "source_id": "f2_culturalmap_university",
            "source_url": None,
            "source_dates": {},
        }
    ]
    assert person["locations"][0] == {
        "source_id": "f2_culturalmap_university",
        "location_role": "mapped_subject",
        "province_code": "40",
        "district_code": None,
        "subdistrict_code": None,
        "province": "ขอนแก่น",
        "district": None,
        "subdistrict": None,
        "status": "resolved",
    }
    assert "person_directory_withheld" not in person["flags"]
    assert person["flags"]["source_field_exclusions"] == [
        "informant_and_contact_details",
        "exact_coordinates_and_street_addresses",
        "financial_health_and_assessment_values",
    ]
    work = details["K12"]["details"]["subject-work"]
    assert work["label"] == "การทอผ้าไหม นางปณภัช ศิริภัทรเดชากร"
    assert work["listings"][0]["label"] == work["label"]
    encoded_person = json.dumps(person, ensure_ascii=False)
    assert "private-person@example.invalid" not in encoded_person
    assert "synthetic-private-assessment" not in encoded_person
    assert "synthetic-private-address" not in encoded_person
    assert "latitude" not in encoded_person
    assert "longitude" not in encoded_person

    narrative_disposition = details["K12"]["details"]["subject-1"]["flags"][
        "child_dispositions"
    ]["narratives"]
    assert narrative_disposition == {
        "candidate_count": 3,
        "emitted_count": 1,
        "withheld_count": 2,
        "withheld_reasons": {"unsafe_or_missing_narrative_text": 2},
    }
    medium = details["K12"]["details"]["subject-1"]["media"][0]
    assert medium["label"] is None
    assert medium["label_availability"] == "withheld"
    assert medium["label_withholding_reason"] == ("public_scalar_admission_failed")
    assert medium["source_id"] == "f2_culturalmap_university"
    assert medium["status"] == "source_reference_not_fetched"
    assert medium["reference_only"] is True
    assert "token" not in medium["url"]


def test_unresolved_mapped_subjects_remain_separate_provisional_identities():
    tables = deepcopy(_tables())
    for suffix in ("a", "b"):
        _add_mapped_subject(
            tables,
            subject_id=f"subject-provisional-{suffix}",
            display_title="ผู้ทรงภูมิปัญญาตัวอย่าง",
            source_keys=[f"map:provisional-{suffix}"],
            identity_status="unresolved_possible_duplicate",
        )

    details = build_details(tables, _definitions(), _policy())

    counted_ids = {
        row["entity_id"]
        for row in tables["entity_contributions"]
        if row["measure_id"] == "K12"
    }
    assert set(details["K12"]["details"]) == counted_ids
    assert details["K12"]["withheld"] == {}
    for suffix in ("a", "b"):
        entity_id = f"subject-provisional-{suffix}"
        provisional = details["K12"]["details"][entity_id]
        assert provisional["entity_id"] == entity_id
        assert provisional["identity_status"] == "unresolved_possible_duplicate"
        assert provisional["flags"]["unresolved_identity"] is True


def test_mapped_ampersand_titles_finalize_without_exposing_markup_or_contacts():
    tables = deepcopy(_tables())
    first_title = "พิพิธภัณฑ์ตัวอย่าง&ท้องฟ้าจำลอง"
    second_title = "อาหารตัวอย่าง&ชาบู"
    private_contact = "private-title@example.invalid"
    _add_mapped_subject(
        tables,
        subject_id="subject-ampersands",
        display_title=f"<script>private-script</script>{first_title}",
        source_keys=["map:amp-1", "map:amp-2", "map:amp-contact"],
        listing_titles=[
            first_title,
            f"<style>private-style</style>{second_title}",
            f"หัวข้อตัวอย่าง & {private_contact}",
        ],
    )

    detail = build_details(tables, _definitions(), _policy())["K12"]["details"][
        "subject-ampersands"
    ]

    assert detail["label"] == first_title
    assert [listing["label"] for listing in detail["listings"]] == [
        first_title,
        second_title,
        "Title withheld pending review",
    ]
    assert detail["listings"][2]["label_availability"] == "withheld"
    assert detail["listings"][2]["label_withholding_reason"] == (
        "source_title_failed_public_scalar_admission"
    )
    assert detail["flags"]["child_dispositions"]["listings"] == {
        "candidate_count": 3,
        "emitted_count": 3,
        "withheld_count": 0,
        "withheld_reasons": {},
    }
    encoded = json.dumps(detail, ensure_ascii=False)
    assert "private-script" not in encoded
    assert "private-style" not in encoded
    assert private_contact not in encoded


def test_reviewed_mapped_heritage_title_context_requires_exact_hash_and_source_keys():
    tables = deepcopy(_tables())
    subject_id = "subject-reviewed-heritage"
    source_key = "map:reviewed-heritage"
    title = "บ้านเลขที่ 9 เรือนมรดกตัวอย่าง"
    _add_mapped_subject(
        tables,
        subject_id=subject_id,
        display_title=title,
        source_keys=[source_key],
    )
    policy = _policy()
    policy.setdefault("reviewed_label_contexts", {}).setdefault("K12", {})[
        subject_id
    ] = {
        "context": "public_location",
        "source_keys": [source_key],
        "label_sha256": hashlib.sha256(title.encode("utf-8")).hexdigest(),
    }

    detail = build_details(tables, _definitions(), policy)["K12"]["details"][subject_id]

    assert detail["label"] == title
    assert detail["flags"]["label_availability"] == "available"
    assert detail["listings"][0]["label"] == title
    assert detail["listings"][0]["label_availability"] == "available"

    mismatched_policy = deepcopy(policy)
    mismatched_policy["reviewed_label_contexts"]["K12"][subject_id]["source_keys"] = [
        "map:different-subject"
    ]
    mismatched = build_details(tables, _definitions(), mismatched_policy)["K12"][
        "details"
    ][subject_id]
    assert mismatched["label"] == "Title withheld pending review"
    assert mismatched["flags"]["label_availability"] == "withheld"
    assert mismatched["listings"][0]["label"] == "Title withheld pending review"

    mismatched_policy = deepcopy(policy)
    mismatched_policy["reviewed_label_contexts"]["K12"][subject_id]["label_sha256"] = (
        "0" * 64
    )
    mismatched = build_details(tables, _definitions(), mismatched_policy)["K12"][
        "details"
    ][subject_id]
    assert mismatched["label"] == "Title withheld pending review"
    assert mismatched["listings"][0]["label"] == "Title withheld pending review"


def test_unsafe_mapped_title_uses_transparent_label_without_losing_safe_detail():
    tables = deepcopy(_tables())
    subject_id = "subject-withheld-title"
    source_key = "map:withheld-title"
    raw_title = "หัวข้อสาธิต 080-000-0000"
    _add_mapped_subject(
        tables,
        subject_id=subject_id,
        display_title=raw_title,
        source_keys=[source_key],
    )
    tables["sources/f2_culturalmap_university/mapped_narrative_evidence"].append(
        {
            "evidence_id": "narrative-withheld-title",
            "subject_id": subject_id,
            "source_key": source_key,
            "field_name": "history",
            "text": "รายละเอียดหัวข้อสาธิตที่ปลอดภัย",
        }
    )

    policy = _policy()
    policy.setdefault("reviewed_label_contexts", {}).setdefault("K12", {})[
        subject_id
    ] = {
        "context": "public_location",
        "source_keys": [source_key],
        "label_sha256": hashlib.sha256(raw_title.encode("utf-8")).hexdigest(),
    }
    k12 = build_details(tables, _definitions(), policy)["K12"]

    assert subject_id in k12["details"]
    assert subject_id not in k12["withheld"]
    detail = k12["details"][subject_id]
    assert detail["label"] == "Title withheld pending review"
    assert detail["flags"]["label_availability"] == "withheld"
    assert detail["flags"]["label_withholding_reason"] == (
        "source_title_failed_public_scalar_admission"
    )
    assert detail["listings"][0]["label"] == "Title withheld pending review"
    assert detail["listings"][0]["label_availability"] == "withheld"
    assert detail["descriptions"][0]["text"] == "รายละเอียดหัวข้อสาธิตที่ปลอดภัย"
    assert raw_title not in json.dumps(detail, ensure_ascii=False)


def test_detached_required_mapped_listing_withholds_parent():
    tables = deepcopy(_tables())
    tables["sources/f2_culturalmap_university/mapped_listing_observations"][0][
        "source_key"
    ] = ""

    details = build_details(tables, _definitions(), _policy())

    assert details["K12"]["withheld"]["subject-1"] == (
        "missing_or_detached_required_mapped_listing"
    )


def test_participation_adapter_keeps_projects_units_and_business_owned_location_only():
    tables = _tables()
    tables["sources/f2_learning_area_based/locations"][0].update(
        {
            "district_code": "3001",
            "district_normalized": "เมืองนครราชสีมา",
            "subdistrict_code": "300101",
            "subdistrict_normalized": "ในเมือง",
        }
    )
    details = build_details(tables, _definitions(), _policy())
    business = details["C08_PARTICIPATING"]["details"]["business-1"]

    assert business["province_codes"] == ["30"]
    assert business["locations"][0]["location_role"] == "programme_business_location"
    assert business["flags"]["identity_review"] == {
        "outcome": "source_record_only",
        "merge_scope": None,
        "counting": "separate",
        "name_quality": "supported",
    }
    assert business["locations"][0]["district_code"] == "3001"
    assert business["locations"][0]["subdistrict_code"] == "300101"
    assert business["children"]["participations"] == [
        {
            "participation_id": "participation-1",
            "fiscal_year_be": 2568,
            "project": "โครงการหนึ่ง",
            "research_unit": "หน่วยวิจัยหนึ่ง",
            "source_id": "f2_learning_area_based",
        }
    ]
    assert business["flags"]["participation_not_improvement"] is True
    assert business["flags"]["person_assessments_withheld"] is True


def test_projection_excludes_unknown_raw_person_assessment_and_locator_fields():
    payload = build_details(_tables(), _definitions(), _policy())
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    for forbidden in (
        "do-not-publish",
        "private-assessment",
        "do-not-publish-person",
        "/Users/private",
        "raw_locator",
        "row_locator",
        "latitude",
        "longitude",
        "price_text_raw",
    ):
        assert forbidden not in encoded
    assert "K02" not in payload
    assert "C08_ASSESSED_PEOPLE" not in payload
    assert "C08_INCREASED_PEOPLE" not in payload


def test_legacy_pending_policy_keeps_promotion_and_aggregate_person_boundaries():
    policy = _policy()

    assert policy["staged_for_review"] is True
    assert policy["owner_checkpoint_required"] is True
    assert policy["additional_field_review_status"] == "pending_owner_acceptance"
    assert policy["publication_approval_claimed"] is False
    assert policy["aggregate_only_measures"]["K02"]
    assert policy["aggregate_only_measures"]["C08_ASSESSED_PEOPLE"]
    assert policy["aggregate_only_measures"]["C08_INCREASED_PEOPLE"]
    assert policy["sources"]["learning_dashboard"]["source_id"] == (
        "f2_learning_dashboard"
    )
    cultural_admission = policy["sources"]["cultural_map"]["record_admission"]
    assert cultural_admission["withheld_subject_ids"] == {}
    assert (
        "unresolved_possible_duplicate"
        in cultural_admission["allowed_identity_statuses"]
    )


def test_scalar_child_omissions_are_reason_counted_without_losing_safe_parents():
    tables = deepcopy(_tables())
    publication = tables["domains/activities/publications"][0]
    publication["title"] = "owner@example.test"
    publication["text"] = "บ้านเลขที่ 123 หมู่ 4"
    publication["source_url"] = "https://atlocalthailand.com/item?token=secret"
    tables["domains/activities/activity_venues"][0]["location_name_raw"] = (
        "บ้านเลขที่ 123 หมู่ 4"
    )
    tables["domains/activities/activity_sessions"][0]["session_label"] = (
        "owner@example.test"
    )
    tables["domains/activities/activity_sections"][0]["text"] = "บ้านเลขที่ 123 หมู่ 4"
    tables["domains/activities/activity_narrative_evidence"] = [
        {
            "evidence_id": "activity-private-narrative",
            "global_activity_id": "activity-1",
            "source": "atlocal-v1",
            "field_name": "text",
            "text": "บ้านเลขที่ 123 หมู่ 4",
        }
    ]
    tables["domains/activities/activity_media"] = [
        {
            "media_id": "activity-unapproved-media",
            "global_activity_id": "activity-1",
            "source": "atlocal-v1",
            "url_or_value": "https://atlocalthailand.com/media/activity.jpg",
        }
    ]
    tables["sources/f2_target_household/description_sections"][0]["text_readable"] = (
        "บ้านเลขที่ 123 หมู่ 4"
    )
    innovation_profile = tables["sources/f2_target_household/innovation_details"][0]
    innovation_profile["detail_url"] = (
        "https://pmua-apptech.com/product/10?token=secret"
    )
    innovation_profile["researcher_name_raw"] = "owner@example.test"
    tables["domains/innovations/innovation_crosswalk"][0]["local_identity_status"] = (
        "owner@example.test"
    )
    tables["domains/innovations/readiness_evidence"][0]["numeric_level"] = (
        "owner@example.test"
    )
    tables["domains/innovations/readiness_evidence"][0]["basis"] = "owner@example.test"
    tables["domains/innovations/innovation_use_locations"][0]["location_role"] = (
        "owner@example.test"
    )
    tables["domains/innovations/source_records"][0]["title_raw"] = "owner@example.test"
    tables["domains/commerce/operator_crosswalk"][0]["display_name"] = (
        "owner@example.test"
    )
    tables["domains/commerce/operator_crosswalk"][0]["identity_status"] = (
        "owner@example.test"
    )
    tables["domains/commerce/locations"][0]["province_normalized"] = "บ้านเลขที่ 123 หมู่ 4"
    tables["domains/commerce/locations"][0]["location_role"] = "owner@example.test"
    tables["domains/commerce/global_offerings"][0]["display_name"] = (
        "owner@example.test"
    )
    tables["domains/commerce/operator_offering_edges"][0]["relationship"] = (
        "owner@example.test"
    )
    tables["domains/commerce/reviewed_evidence"][0]["evidence_text"] = (
        "บ้านเลขที่ 123 หมู่ 4"
    )
    tables["sources/f2_learning_area_based/participations"][0]["fiscal_year_be"] = (
        "not-a-year"
    )
    tables["sources/f2_learning_area_based/project_assertions"][0][
        "project_name_raw"
    ] = "บ้านเลขที่ 123 หมู่ 4"
    tables["sources/f2_learning_area_based/research_unit_assertions"][0][
        "research_unit_raw"
    ] = "owner@example.test"
    tables["sources/f2_learning_area_based/locations"][0]["province_normalized"] = (
        "บ้านเลขที่ 123 หมู่ 4"
    )

    details = build_details(tables, _definitions(), _policy())

    activity_audit = details["K03"]["details"]["activity-1"]["flags"][
        "child_dispositions"
    ]
    assert activity_audit["publication_titles"]["withheld_count"] == 1
    assert activity_audit["publication_texts"]["withheld_count"] == 1
    assert activity_audit["publication_link_checks"]["withheld_count"] == 1
    assert activity_audit["venue_labels"]["withheld_count"] == 1
    assert activity_audit["session_labels"]["withheld_count"] == 1
    assert activity_audit["sections"]["withheld_count"] == 1
    assert activity_audit["section_attributions"]["withheld_reasons"] == {
        "parent_section_withheld": 1
    }
    assert activity_audit["narratives"]["withheld_count"] == 1
    assert activity_audit["media"]["withheld_count"] == 1

    innovation_audit = details["K04"]["details"]["innovation-1"]["flags"][
        "child_dispositions"
    ]
    assert innovation_audit["descriptions"]["withheld_count"] == 1
    assert innovation_audit["profile_link_checks"]["withheld_count"] == 1
    assert innovation_audit["work_attributions"]["withheld_count"] == 1
    assert innovation_audit["source_identity_statuses"]["withheld_count"] == 1
    assert innovation_audit["readiness_labels"]["withheld_count"] == 1
    assert innovation_audit["readiness_numeric_levels"]["withheld_count"] == 1
    assert innovation_audit["location_metadata"]["withheld_count"] == 1
    assert innovation_audit["source_record_labels"]["withheld_count"] == 1

    operator_audit = details["K05"]["details"]["operator-1"]["flags"][
        "child_dispositions"
    ]
    assert operator_audit["source_membership_labels"]["withheld_count"] == 1
    assert operator_audit["source_membership_statuses"]["withheld_count"] == 1
    assert operator_audit["location_labels"]["withheld_count"] == 1
    assert operator_audit["location_metadata"]["withheld_count"] == 1
    assert operator_audit["relationship_labels"]["withheld_count"] == 1
    assert operator_audit["relationship_kinds"]["withheld_count"] == 1
    assert operator_audit["reviewed_evidence"]["withheld_count"] == 1

    participation_audit = details["C08_PARTICIPATING"]["details"]["business-1"][
        "flags"
    ]["child_dispositions"]
    assert participation_audit["fiscal_years"]["withheld_count"] == 1
    assert participation_audit["projects"]["withheld_count"] == 1
    assert participation_audit["research_units"]["withheld_count"] == 1
    assert participation_audit["location_labels"]["withheld_count"] == 1


def test_rinmp_record_route_uses_pinned_source_citation_with_disposition():
    from app.publication import (
        _catalog_sets,
        _embedded_source_provenance,
        _url_matches_rule,
    )

    tables = deepcopy(_tables())
    member = tables["domains/innovations/innovation_crosswalk"][0]
    member["source"] = "rinmp"
    member["local_innovation_id"] = "rinmp-local-1"
    tables["domains/innovations/source_records"][0]["source"] = "rinmp"
    tables["domains/innovations/readiness_evidence"][0]["source"] = "rinmp"
    tables["domains/innovations/innovation_use_locations"][0]["source"] = "rinmp"
    tables["sources/f2_apptech_mtr/description_sections"] = [
        {
            "innovation_id": "rinmp-local-1",
            "label_raw": "overview",
            "text_readable": "คำอธิบายนวัตกรรม",
        }
    ]
    tables["sources/f2_apptech_mtr/innovation_profiles"] = [
        {
            "innovation_id": "rinmp-local-1",
            "detail_url": ("https://app.rinmp.com/api/appTechPublic/rinmp-local-1"),
        },
        {
            "innovation_id": "rinmp-local-1",
            "detail_url": ("https://app.rinmp.com/api/appTechPublic/rinmp-local-2"),
        },
    ]

    details = build_details(tables, _definitions(), _policy())
    detail = details["K04"]["details"]["innovation-1"]

    assert detail == details["C04_LISTED"]["details"]["innovation-1"]
    listings = detail["listings"]
    assert len(listings) == 2
    assert len({listing["listing_id"] for listing in listings}) == 2
    for listing in listings:
        assert listing["label"] == "นวัตกรรมหนึ่ง"
        assert listing["source_id"] == "f2_apptech_mtr"
        assert listing["source_url"] == "https://rinmp.com/"
        assert listing["link_scope"] == "source"
        assert listing["record_link_availability"] == "withheld"
        assert listing["record_link_withholding_reason"] == (
            "record_link_withheld_unregistered_publication_route"
        )
    dispositions = detail["flags"]["child_dispositions"]
    assert dispositions["profile_link_checks"] == {
        "candidate_count": 2,
        "emitted_count": 0,
        "withheld_count": 2,
        "withheld_reasons": {"record_link_withheld_unregistered_publication_route": 2},
    }
    assert dispositions["profile_source_citations"] == {
        "candidate_count": 2,
        "emitted_count": 2,
        "withheld_count": 0,
        "withheld_reasons": {},
    }
    _, _, restricted_source_ids, rules = _catalog_sets(
        Path("config/source_catalog.json")
    )
    _, references = _embedded_source_provenance(
        detail,
        artifact_path="staged/details/k04-000.json",
        declared_source_ids={"f2_apptech_mtr"},
        restricted_source_ids=restricted_source_ids,
    )
    assert len(references) == 2
    assert all(
        reference.source_ids == frozenset({"f2_apptech_mtr"})
        for reference in references
    )
    assert all(
        any(
            _url_matches_rule(reference.address, rule)
            for rule in rules["f2_apptech_mtr"]
        )
        for reference in references
    )


def test_disposition_audits_are_not_collected_as_provenance_url_fields():
    from app.publication import _embedded_source_provenance

    policy = _policy()
    details = build_details(_tables(), _definitions(), policy)
    declared_source_ids = {
        str(source["source_id"]) for source in policy["sources"].values()
    }

    found_source_ids, references = _embedded_source_provenance(
        details,
        artifact_path="staged/public_details.json",
        declared_source_ids=declared_source_ids,
        restricted_source_ids=set(),
    )

    assert found_source_ids
    assert references
    assert all("child_dispositions" not in reference.path for reference in references)


def test_unlisted_source_fields_do_not_enter_detail_even_when_populated():
    tables = deepcopy(_tables())
    tables["sources/f2_target_household/description_sections"][0]["future_field"] = (
        "future-unknown"
    )
    tables["domains/commerce/listing_evidence"][0]["future_field"] = "future-unknown"
    payload = build_details(tables, _definitions(), _policy())

    assert "future-unknown" not in json.dumps(payload, ensure_ascii=False)


def test_business_labels_finalize_ampersands_without_admitting_contacts_or_tokens():
    tables = deepcopy(_tables())
    k05_labels = [
        "Workshop A&B",
        "Farm/Retail O&R",
        "Craft&Co.",
        "Fruit&Grill",
        "Design&Textile",
        "Food&Farm",
        "Studio&Market",
    ]
    for index, label in enumerate(k05_labels):
        entity_id = f"operator-amp-{index}"
        tables["entity_contributions"].append(
            {"measure_id": "K05", "entity_id": entity_id, "label": label}
        )
        tables["domains/commerce/global_operators"].append(
            {
                "global_operator_id": entity_id,
                "display_name": label,
                "identity_status": "source_local_identity",
            }
        )
        tables["domains/commerce/operator_crosswalk"].append(
            {
                "global_operator_id": entity_id,
                "source_operator_id": f"atlocal:operator-amp-{index}",
                "source": "atlocal",
                "display_name": label,
                "identity_status": "source_local_identity",
            }
        )
    c08_labels = ["Kitchen A&B", "Farm/Shop O&R"]
    for index, label in enumerate(c08_labels):
        entity_id = f"business-amp-{index}"
        tables["entity_contributions"].append(
            {
                "measure_id": "C08_PARTICIPATING",
                "entity_id": entity_id,
                "label": label,
            }
        )
        tables["sources/f2_learning_area_based/businesses"].append(
            {
                "business_id": entity_id,
                "display_name": label,
                "identity_status": "provisional_source_unit",
                "name_quality": "source_reported_name",
            }
        )
    unsafe_labels = [
        "Line OA: @sample_business",
        "Workshop A&B token=synthetic-value",
        "Workshop owner@example.invalid",
        "Workshop 080-000-0000",
    ]
    for index, label in enumerate(unsafe_labels):
        entity_id = f"operator-unsafe-{index}"
        tables["entity_contributions"].append(
            {"measure_id": "K05", "entity_id": entity_id, "label": label}
        )
        tables["domains/commerce/global_operators"].append(
            {
                "global_operator_id": entity_id,
                "display_name": label,
                "identity_status": "source_local_identity",
            }
        )
        tables["domains/commerce/operator_crosswalk"].append(
            {
                "global_operator_id": entity_id,
                "source_operator_id": f"atlocal:operator-unsafe-{index}",
                "source": "atlocal",
                "display_name": label,
                "identity_status": "source_local_identity",
            }
        )

    details = build_details(tables, _definitions(), _policy())

    for index, label in enumerate(k05_labels):
        detail = details["K05"]["details"][f"operator-amp-{index}"]
        assert detail["label"] == label
        assert detail["identity_status"] == "source_local_identity"
        assert detail["children"]["source_memberships"][0]["label"] == label
    for index, label in enumerate(c08_labels):
        detail = details["C08_PARTICIPATING"]["details"][f"business-amp-{index}"]
        assert detail["label"] == label
        assert detail["identity_status"] == "provisional_source_unit"
    assert set(details["K05"]["withheld"]) >= {
        f"operator-unsafe-{index}" for index in range(len(unsafe_labels))
    }


def test_business_labels_preserve_safe_source_line_breaks():
    tables = deepcopy(_tables())
    label = "Community enterprise\nFood processing group"
    for table in (
        "domains/commerce/global_operators",
        "domains/commerce/operator_crosswalk",
        "sources/f2_learning_area_based/businesses",
    ):
        tables[table][0]["display_name"] = label

    details = build_details(tables, _definitions(), _policy())

    assert details["K05"]["details"]["operator-1"]["label"] == label
    assert details["C08_PARTICIPATING"]["details"]["business-1"]["label"] == label
    assert details["K05"]["withheld"] == {}
    assert details["C08_PARTICIPATING"]["withheld"] == {}


def test_reviewed_innovation_title_requires_exact_entity_source_key_and_hash():
    tables = deepcopy(_tables())
    title = "Line OA อาหารสุขภาพสูงอายุ"
    source_key = "2:synthetic-source-record"
    tables["entity_contributions"] = [
        row
        for row in tables["entity_contributions"]
        if not (row["measure_id"] == "K04" and row["entity_id"] == "innovation-1")
    ]
    tables["domains/innovations/global_innovations"][0]["display_name"] = title
    member = tables["domains/innovations/innovation_crosswalk"][0]
    member.update(
        {
            "source": "icommunity",
            "local_innovation_id": "innovation-local-reviewed",
            "local_display_name": title,
        }
    )
    record = tables["domains/innovations/source_records"][0]
    record.update(
        {
            "source": "icommunity",
            "local_innovation_id": "innovation-local-reviewed",
            "source_key": source_key,
            "title_raw": title,
        }
    )
    tables["domains/innovations/readiness_evidence"] = []
    tables["domains/innovations/innovation_use_locations"] = []
    policy = _policy()
    policy.setdefault("reviewed_label_contexts", {}).setdefault("C04_LISTED", {})[
        "innovation-1"
    ] = {
        "context": "public_title",
        "source_keys": [source_key],
        "label_sha256": hashlib.sha256(title.encode("utf-8")).hexdigest(),
    }

    detail = build_details(tables, _definitions(), policy)["C04_LISTED"]["details"][
        "innovation-1"
    ]

    assert detail["label"] == title
    assert detail["identity_status"] == "accepted_identity"
    assert detail["source_ids"] == ["f2_icommunity"]
    assert detail["relationships"][0]["label"] == title
    assert detail["children"]["source_records"][0]["label"] == title
    for group in ("source_identity_labels", "source_record_labels"):
        assert detail["flags"]["child_dispositions"][group]["withheld_count"] == 0

    mismatched_source_policy = deepcopy(policy)
    mismatched_source_policy["reviewed_label_contexts"]["C04_LISTED"]["innovation-1"][
        "source_keys"
    ] = ["2:different-source-record"]
    assert (
        "innovation-1"
        in build_details(tables, _definitions(), mismatched_source_policy)[
            "C04_LISTED"
        ]["withheld"]
    )

    mismatched_hash_policy = deepcopy(policy)
    mismatched_hash_policy["reviewed_label_contexts"]["C04_LISTED"]["innovation-1"][
        "label_sha256"
    ] = "0" * 64
    assert (
        "innovation-1"
        in build_details(tables, _definitions(), mismatched_hash_policy)["C04_LISTED"][
            "withheld"
        ]
    )

    contact_tables = deepcopy(tables)
    contact_title = "Line OA: @sample_business"
    contact_tables["domains/innovations/global_innovations"][0]["display_name"] = (
        contact_title
    )
    contact_tables["domains/innovations/innovation_crosswalk"][0][
        "local_display_name"
    ] = contact_title
    contact_tables["domains/innovations/source_records"][0]["title_raw"] = contact_title
    contact_policy = deepcopy(policy)
    contact_policy["reviewed_label_contexts"]["C04_LISTED"]["innovation-1"][
        "label_sha256"
    ] = hashlib.sha256(contact_title.encode("utf-8")).hexdigest()
    contact_payload = build_details(contact_tables, _definitions(), contact_policy)
    assert "innovation-1" in contact_payload["C04_LISTED"]["withheld"]
    assert contact_title not in json.dumps(contact_payload, ensure_ascii=False)


def test_malformed_c08_names_use_placeholders_without_merging_provisional_units():
    tables = deepcopy(_tables())
    malformed_ids = [f"business-malformed-{index}" for index in range(4)]
    for index, entity_id in enumerate(malformed_ids):
        tables["entity_contributions"].append(
            {
                "measure_id": "C08_PARTICIPATING",
                "entity_id": entity_id,
                "label": "",
            }
        )
        tables["sources/f2_learning_area_based/businesses"].append(
            {
                "business_id": entity_id,
                "display_name": "",
                "identity_status": "provisional_malformed_name",
                "name_quality": "malformed_name",
            }
        )
        tables["sources/f2_learning_area_based/participations"].append(
            {
                "participation_id": f"participation-malformed-{index}",
                "business_id": entity_id,
                "project_assertion_id": "project-1",
                "research_unit_assertion_id": "unit-1",
                "fiscal_year_be": "2568",
            }
        )
        tables["sources/f2_learning_area_based/locations"].append(
            {
                "location_id": f"business-location-malformed-{index}",
                "business_id": entity_id,
                "location_role": "programme_business_location",
                "province_code": "30",
                "province_normalized": "นครราชสีมา",
                "resolution_status": "resolved",
            }
        )
    tables["entity_contributions"].append(
        {
            "measure_id": "C08_PARTICIPATING",
            "entity_id": "business-unreviewed-blank",
            "label": "",
        }
    )
    tables["sources/f2_learning_area_based/businesses"].append(
        {
            "business_id": "business-unreviewed-blank",
            "display_name": "",
            "identity_status": "provisional_source_unit",
            "name_quality": "source_reported_name",
        }
    )

    c08 = build_details(tables, _definitions(), _policy())["C08_PARTICIPATING"]

    assert set(malformed_ids) <= set(c08["details"])
    for entity_id in malformed_ids:
        detail = c08["details"][entity_id]
        assert detail["entity_id"] == entity_id
        assert detail["label"] == "ไม่พบชื่อจากแหล่งข้อมูล"
        assert detail["identity_status"] == "provisional_malformed_name"
        assert detail["source_ids"] == ["f2_learning_area_based"]
        assert detail["province_codes"] == ["30"]
        assert len(detail["children"]["participations"]) == 1
        assert detail["flags"]["source_name_available"] is False
        assert detail["flags"]["label_is_generated_placeholder"] is True
        assert detail["flags"]["identity_review"] == {
            "outcome": "malformed_name",
            "merge_scope": None,
            "counting": "separate",
            "name_quality": "unavailable",
        }
        assert detail["flags"]["source_name_unavailability_reason"] == (
            "malformed_source_name"
        )
    assert c08["withheld"]["business-unreviewed-blank"] == (
        "unsafe_or_missing_public_label"
    )


def test_operator_evidence_omits_health_risk_field_but_keeps_safe_business_detail():
    tables = deepcopy(_tables())
    tables["domains/commerce/reviewed_evidence"].extend(
        [
            {
                "evidence_id": "reviewed-operator-safe-risk",
                "global_operator_id": "operator-1",
                "source": "atlocal",
                "relationship": "business_risk",
                "evidence_text": "Synthetic seasonal supply risk.",
            },
            {
                "evidence_id": "reviewed-operator-private-risk",
                "global_operator_id": "operator-1",
                "source": "atlocal",
                "relationship": "business_risk",
                "evidence_text": "Synthetic health condition detail.",
            },
        ]
    )

    detail = build_details(tables, _definitions(), _policy())["K05"]["details"][
        "operator-1"
    ]

    texts = {item["text"] for item in detail["descriptions"]}
    assert "Synthetic seasonal supply risk." in texts
    assert "Synthetic health condition detail." not in texts
    disposition = detail["flags"]["child_dispositions"]["reviewed_evidence"]
    assert disposition["candidate_count"] == 3
    assert disposition["emitted_count"] == 2
    assert disposition["withheld_reasons"] == {
        "reviewed_evidence_field_privacy_check_failed": 1
    }
