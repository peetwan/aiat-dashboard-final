"""Ingestion privacy must drop person data without losing public fields.

The team's recurring failure mode is the opposite of a leak: an over-broad
filter silently deleting geography, aggregate counts, or record codes, which
then surface as "missing data" on the dashboard.  These tests pin both
directions — real contact/identity data is removed, public measures survive.
"""

from __future__ import annotations

import pytest

from app.privacy import forbidden_key_reason, sanitize_payload
from tools.scaffold_connector import ScaffoldError, ScaffoldSpec, validate_spec


def test_admin_geography_and_aggregate_keys_survive():
    payload = {
        "address_province": "เชียงใหม่",
        "address_district": "เมืองเชียงใหม่",
        "address_subdistrict": "ศรีภูมิ",
        "address_postal_code": "50200",
        "citizen_count": 1250,
        "household_total": 13696,
        "budget_amount": 4500000.75,
        "secretariat_name": "สำนักงานเลขานุการ",
        "province_name": "เชียงใหม่",
        "contactless_payment_supported": True,
    }
    dropped: list[tuple[str, str]] = []
    assert sanitize_payload(payload, dropped=dropped) == payload
    assert dropped == []


def test_person_contact_and_identity_keys_are_dropped_with_reasons():
    dropped: list[tuple[str, str]] = []
    clean = sanitize_payload(
        {
            "id": 7,
            "name": "ชื่อนวัตกรรมที่เผยแพร่ได้",
            "ownerContact": {"name": "ชื่อบุคคล", "email": "person@example.com"},
            "researcherName": "ชื่อผู้วิจัย",
            "firstname": "ชื่อ",
            "lastname": "นามสกุล",
            "citizen_id": "1234567890123",
            "national_id": "1234567890123",
            "id_card": "1234567890123",
            "home_address": "99/1 หมู่ 4",
            "address": "99/1 หมู่ 4 ต.ศรีภูมิ",
            "api_key": "not-a-real-key-just-a-test-value",
            "access_token": "not-a-real-token-just-a-test-value",
        },
        dropped=dropped,
    )
    assert clean == {"id": 7, "name": "ชื่อนวัตกรรมที่เผยแพร่ได้"}
    assert {key for key, _ in dropped} == {
        "ownerContact",
        "researcherName",
        "firstname",
        "lastname",
        "citizen_id",
        "national_id",
        "id_card",
        "home_address",
        "address",
        "api_key",
        "access_token",
    }
    reasons = dict(dropped)
    assert reasons["ownerContact"] == "contact key"
    assert reasons["citizen_id"] == "person id key"
    assert reasons["home_address"] == "address key"
    assert reasons["api_key"] == "credential key"


def test_buddhist_era_record_codes_and_measures_are_not_phones():
    payload = {
        "project_code": "66079123456",
        "procurement_id": "67017000021",
        "fiscal_year": "2566",
        "as_of": "25660101",
        "latitude": "13.7563309",
        "amount": "660791234.56",
    }
    assert sanitize_payload(payload) == payload


def test_real_thai_phones_and_emails_are_redacted_in_values():
    clean = sanitize_payload(
        {
            "note": "ติดต่อ 081-234-5678 หรือ person@example.com",
            "hotline": "02-141-1234",
            "intl": "+66 81 234 5678",
        }
    )
    assert clean["note"] == "ติดต่อ [redacted-phone] หรือ [redacted-email]"
    assert clean["hotline"] == "[redacted-phone]"
    assert clean["intl"] == "[redacted-phone]"


def test_forbidden_key_reason_boundaries():
    assert forbidden_key_reason("address_province") is None
    assert forbidden_key_reason("citizen_count") is None
    assert forbidden_key_reason("secretariat_name") is None
    assert forbidden_key_reason("address") == "address key"
    assert forbidden_key_reason("home_address") == "address key"
    assert forbidden_key_reason("citizenId") == "person id key"
    assert forbidden_key_reason("ownercontact") == "contact key"
    assert forbidden_key_reason("apikey") == "credential key"


def _spec(**overrides) -> ScaffoldSpec:
    values = {
        "source_id": "f9_privacy_demo",
        "transport": "rest_json",
        "dataset_key": "records.list",
        "grain_th": "หนึ่งแถวแทนหนึ่ง record ตัวอย่าง",
        "identity_options": (("record_id",),),
    }
    values.update(overrides)
    return ScaffoldSpec(**values)


def test_scaffold_accepts_admin_geography_fields():
    validate_spec(_spec(geography_fields=("address_province", "address_district")))


def test_scaffold_still_rejects_contact_fields():
    with pytest.raises(ScaffoldError, match="forbidden"):
        validate_spec(_spec(geography_fields=("owner_email",)))
    with pytest.raises(ScaffoldError, match="forbidden"):
        validate_spec(_spec(identity_options=(("contact.phone",),)))
