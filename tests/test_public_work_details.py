from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from tools.build_housing_place_details import merge_place_details
from tools.build_provincial_briefings import project_tourism_payload, sanitize_public_text
from tools.public_work_details import project_cultural_supporting, project_mtr_work, project_rmutdb_work
from tools.public_work_details import mtr_public_contacts


def mtr_evidence(tmp_path, pages):
    rows = []
    for index, payload in enumerate(pages):
        raw = json.dumps(payload).encode()
        path = tmp_path / f"page-{index}.json"
        path.write_bytes(raw)
        rows.append({"source_record_id": f"work-{index + 1}",
                     "normalized_fields": {"innovation_id": index + 1},
                     "provenance": {"raw_evidence_uri": path.name, "raw_sha256": hashlib.sha256(raw).hexdigest()}})
    return rows


def test_mtr_directory_requires_complete_stable_totals_and_matching_id_sets(tmp_path):
    pages = [{"totalCount": 2, "data": [{"id": identifier, "ownerContact": {"email": "office@example.org"}}]}
             for identifier in (1, 2)]
    rows = mtr_evidence(tmp_path, pages)
    contacts = mtr_public_contacts(tmp_path, rows)
    assert set(contacts) == {"work-1", "work-2"}
    assert contacts["work-1"]["email"] == "office@example.org"


@pytest.mark.parametrize("drift", [
    "larger_total", "changing_total", "missing_total", "invalid_total", "boolean_total",
    "duplicate_across_pages", "duplicate_within_page", "missing_id", "omitted_silver_id",
    "duplicate_silver_id", "missing_record_id", "duplicate_record_id", "missing_page", "empty_silver",
])
def test_mtr_directory_rejects_partial_or_inconsistent_snapshots(tmp_path, drift):
    pages = [{"totalCount": 2, "data": [{"id": identifier}]} for identifier in (1, 2)]
    if drift == "larger_total":
        for page in pages: page["totalCount"] = 3
    elif drift == "changing_total": pages[1]["totalCount"] = 3
    elif drift == "missing_total": pages[1].pop("totalCount")
    elif drift == "invalid_total": pages[1]["totalCount"] = "2"
    elif drift == "boolean_total": pages[1]["totalCount"] = True
    elif drift == "duplicate_across_pages": pages[1]["data"] = [{"id": 1}]
    elif drift == "duplicate_within_page": pages[1]["data"] = [{"id": 2}, {"id": 2}]
    elif drift == "missing_id": pages[1]["data"] = [{"id": None}]
    elif drift == "omitted_silver_id":
        for page in pages: page["totalCount"] = 3
        pages[1]["data"].append({"id": 3})
    rows = mtr_evidence(tmp_path, pages)
    if drift == "duplicate_silver_id": rows[1]["normalized_fields"]["innovation_id"] = 1
    elif drift == "missing_record_id": rows[1].pop("source_record_id")
    elif drift == "duplicate_record_id": rows[1]["source_record_id"] = rows[0]["source_record_id"]
    elif drift == "missing_page": rows.pop()
    elif drift == "empty_silver": rows.clear()
    with pytest.raises(ValueError, match="MTR"):
        mtr_public_contacts(tmp_path, rows)


@pytest.mark.parametrize("dataset_id", ["map_inspiration", "products", "activities", "recreation", "team"])
@pytest.mark.parametrize("identities", [["same", "same"], ["one", None], ["one", ""], ["one", " "]])
def test_cultural_dataset_rejects_missing_or_duplicate_identities(monkeypatch, dataset_id, identities):
    from tools import build_source_insights as builder

    monkeypatch.setattr(builder, "CULTURAL_DATASETS", {dataset_id: ("fixture.json", 2, "test")})
    monkeypatch.setattr(builder, "read_json", lambda path: {"data": {"records": [
        {"external_id": identifier} for identifier in identities
    ]}})
    with pytest.raises(RuntimeError, match="external_id"):
        builder.build_cultural_supporting_coverage()


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


@pytest.mark.parametrize("suffix", [
    "Face book : กลุ่มตัวอย่าง https://example.org ติดต่อผู้ดูแล เข้าชม : 20 ครั้ง",
    "ID Line : work-example เข้าชม : 20 ครั้ง",
    "มือถือ 0812345678 ผู้ประสานงานตัวอย่าง",
    "เข้าชม : 20 ครั้ง ผลิตภัณฑ์จากวัฒนธรรม รายละเอียดซ้ำ",
])
def test_cultural_address_stops_before_contact_and_footer_sections(suffix):
    address = "123 หมู่ 4 ต.ตัวอย่าง อ.ตัวอย่าง จ.ตัวอย่าง 10000"
    item = project_cultural_supporting({"external_id": "product-fixture", "title": "ผลิตภัณฑ์ตัวอย่าง", "data": {
        "address_text": address + " " + suffix, "sales_channels": "office@example.org โทร 0812345678",
    }}, "products")
    assert item["address"] == address
    assert item["sales_channels"] == "office@example.org โทร 0812345678"


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
