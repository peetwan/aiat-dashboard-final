from __future__ import annotations

from copy import deepcopy

import pytest

from tools.build_housing_place_details import merge_place_details
from tools.build_provincial_briefings import project_tourism_payload, sanitize_public_text
from tools.public_work_details import project_cultural_supporting, project_mtr_work, project_rmutdb_work


def test_work_projections_keep_owner_and_work_contact_but_omit_account_credentials():
    item = project_mtr_work({"source_record_id": "work-1", "normalized_fields": {
        "innovation_name": "ผลงานตัวอย่าง", "owner_name": "เจ้าของผลงานตัวอย่าง",
        "user_id": "private-account", "password": "never-export",
    }})
    assert item["owner_name"] == "เจ้าของผลงานตัวอย่าง"
    assert "user_id" not in item and "password" not in item
    cultural = project_cultural_supporting({"external_id": "product-1", "title": "ผลิตภัณฑ์ตัวอย่าง",
        "data": {"sales_channels": "office@example.org", "address_text": "123 Example Road",
                 "account_identifier": "private-account", "informants_raw": "private-person"}}, "products")
    assert cultural["sales_channels"] == "office@example.org"
    assert cultural["address"] == "123 Example Road"
    assert "account_identifier" not in cultural and "informants_raw" not in cultural


def test_rmutdb_work_preserves_pdf_contact_and_attribution_without_person_id():
    row = {"source_record_id": "energy:p7", "record_type": "rmutdb_ebook_innovation_detail",
           "normalized_fields": {"inventor": "ผู้ประดิษฐ์ตัวอย่าง", "coordinator": "ผู้ประสานงานตัวอย่าง",
                                 "contact_address": "123 Example Road", "citizen_id": "private-id"},
           "source_fields": {"pdf_page_index": 7},
           "provenance": {"source_url": "https://example.org/book.pdf", "raw_sha256": "a" * 64}}
    item = project_rmutdb_work(row, {"phone": "0812345678", "email": "office@example.org"})
    assert item["inventor"] == "ผู้ประดิษฐ์ตัวอย่าง"
    assert item["phone"] == "0812345678" and item["email"] == "office@example.org"
    assert item["pdf_page"] == 7 and "citizen_id" not in item


def test_service_projection_separates_hours_and_preserves_work_phone_extensions():
    projected = project_tourism_payload({"page_id": "contact", "data": {
        "service_contacts": [{"name": {"TH": "ศูนย์บริการตัวอย่าง"}, "opening_hours_raw": "07.30 - 18.00 น.", "phones": [
            {"label": {"TH": "เปิดทำการ"}, "phone_display": "07.30 - 18.00 น."},
            {"phone_display": "053-569100"},
            {"label": "สำนักงาน", "phone_display": "053 - 511013 ต่อ 109"},
            {"phone_display": "1111"},
            {"phone_display": "ไม่ระบุ"},
            {"phone_display": "08:00 - 17:00"},
        ]}],
    }})
    centre = projected["data"]["service_centres"][0]
    assert centre["opening_hours"] == "07.30 - 18.00 น.; 08:00 - 17:00"
    assert [entry["phone"] for entry in centre["phones"]] == ["053-569100", "053 - 511013 ต่อ 109", "1111"]
    assert centre["phones"][1]["label"] == "สำนักงาน"


@pytest.mark.parametrize("text", ["ผู้จัดทำfoo@example.org", "foo@example.orgผู้จัดทำ", "ผู้จัดทำfoo@example.orgติดต่อ"])
def test_descriptive_projection_removes_emails_adjacent_to_thai(text):
    assert "foo@example.org" not in (sanitize_public_text(text) or "")


def place_pair():
    geometry = {"type": "Point", "coordinates": [100.0, 13.0]}
    seed = {"source_id": "f3_housing_portal", "layer_id": "housing_points", "feature_id": "place-1",
            "geometry_type": "Point", "bbox": [100., 13., 100., 13.], "geometry": geometry,
            "properties": {"province_code": "10"}, "evidence_path": "data/raw/example.json",
            "evidence_sha256": "a" * 64, "fetched_at": "2026-08-17T00:00:00+00:00",
            "as_of": "ไม่ระบุ", "quality_status": "needs_review"}
    source = {"type": "Feature", "geometry": deepcopy(geometry), "properties": {
        "place_id": "place-1", "name": "ที่พักตัวอย่าง", "address": "123 Example Road",
        "rating": 4.1, "user_ratings_total": 20, "contact_email": "private@example.org"}}
    return seed, source


def test_housing_place_projection_keeps_places_and_preserves_evidence_identity():
    seed, source = place_pair()
    result = merge_place_details([seed], [source])[0]
    assert result["properties"]["name"] == "ที่พักตัวอย่าง"
    assert result["properties"]["address"] == "123 Example Road"
    assert result["properties"]["rating"] == 4.1
    assert "contact_email" not in result["properties"]
    assert result["evidence_sha256"] == seed["evidence_sha256"]
    assert "name" not in seed["properties"]


@pytest.mark.parametrize("drift", ["missing", "duplicate", "geometry"])
def test_housing_enrichment_fails_on_partial_or_changed_evidence(drift):
    seed, source = place_pair()
    features = [source]
    if drift == "missing": features = []
    elif drift == "duplicate": features.append(deepcopy(source))
    else: source["geometry"]["coordinates"][0] = 101.0
    with pytest.raises(ValueError):
        merge_place_details([seed], features)
