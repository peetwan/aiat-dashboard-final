"""บริบทสาธารณะต้องใช้ได้จริง โดยจำกัดสิทธิ์เฉพาะฟิลด์ที่ประกาศ."""
from __future__ import annotations

import json

import pytest

from app.connector_contracts import load_runtime_connector_contract, prepare_contract_records
from app.field_contexts import FieldContextError, validate_field_contexts
from app.privacy import sanitize_payload
from app.publication import _privacy_problems
from app.public_artifacts import ArtifactInput, validate_public_artifacts
from tools.preview_privacy import main, preview_connector


def problems(payload, contexts=None):
    return _privacy_problems(payload, artifact_path="data/public/example.json",
                             restricted_source_ids={"restricted_source"},
                             profile="aggregate_public", field_contexts=contexts)


@pytest.mark.parametrize("text", [
    "LINE ID: private_person", "ID Line: private_person", "LINE OA: @private_person",
    "ไลน์: private_person", "ไอดีไลน์ private_person", "LINE: private_person",
    "ติดต่อ LINE: private_person", "Facebook: @private_person", "Facebook handle: private_person",
    "Face book: https://facebook.com/private_person", "Instagram: private_person",
    "IG: private_person", "TikTok @private_person", "Twitter: private_person",
])
def test_social_contact_values_require_exact_public_contact_context(text, tmp_path):
    payload = {"description": text}
    changes = []
    assert "private_person" not in sanitize_payload(payload, changes=changes)["description"]
    assert changes == [("/description", "social contact value")]
    assert any("social contact value" in reason for reason in problems(payload))
    for context in ("work_attribution", "public_location", "organization"):
        assert problems(payload, {"/description": context})
    contexts = {"/description": "public_contact"}
    assert sanitize_payload(payload, field_contexts=contexts) == payload
    assert problems(payload, contexts) == []
    assert problems(payload, {"/other": "public_contact"})
    artifact = tmp_path / "undeclared.json"
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="social contact value"):
        validate_public_artifacts([ArtifactInput("candidate", "source_dataset", artifact)])


@pytest.mark.parametrize("text", [
    "BTS Green Line: Khu Khot to Kheha", "bus line 515", "production line: assembly",
    "line graph of quarterly totals", "linear regression", "The LINE API documentation",
    "https://facebook.com/public-source/posts/123", "https://line.me/R/ti/p/@public-office",
])
def test_ordinary_lines_and_provenance_urls_are_preserved(text, tmp_path):
    from app.public_artifacts import _artifact_policy_violations

    payload = {"description": text}
    assert sanitize_payload(payload) == payload
    assert problems(payload) == []
    item = ArtifactInput("candidate", "source_dataset", tmp_path / "candidate.json")
    assert _artifact_policy_violations(item, payload, set()) == []


def test_work_attribution_organization_contacts_and_location_can_be_published():
    payload = {
        "research_leads": [{"name": "ผู้วิจัยตัวอย่าง", "researcher_name": "ผู้วิจัยตัวอย่าง"}],
        "ip": {"rights_owner": "มหาวิทยาลัยตัวอย่าง"},
        "ownerContact": {"name": "ผู้รับผิดชอบผลงาน", "email": "office@example.org"},
        "address": "123 Example Road, Bangkok 10200",
    }
    contexts = {
        "/research_leads/*/name": "work_attribution",
        "/research_leads/*/researcher_name": "work_attribution",
        "/ip/rights_owner": "organization",
        "/ownerContact/name": "work_attribution",
        "/ownerContact/email": "public_contact",
        "/address": "public_location",
    }
    assert sanitize_payload(payload, field_contexts=contexts) == payload
    assert problems(payload, contexts) == []
    assert problems(payload)


def test_context_never_applies_to_sibling_fields_or_another_array():
    payload = {"items": [{"owner_name": "เจ้าของผลงาน", "email": "private@example.org"}],
               "participants": [{"owner_name": "ชื่อผู้เข้าร่วม"}]}
    contexts = {"/items/*/owner_name": "work_attribution"}
    clean = sanitize_payload(payload, field_contexts=contexts)
    assert clean == {"items": [{"owner_name": "เจ้าของผลงาน"}], "participants": [{}]}
    assert any("participants" in p for p in problems(payload, contexts))
    assert any("email" in p for p in problems(payload, contexts))


@pytest.mark.parametrize("key", [
    "inventor", "coordinator", "recorder_name", "recorded_by", "userfullname",
    "userFullName", "co_owner", "full_name", "inventor_name",
])
def test_person_aliases_require_their_exact_declared_context(key, tmp_path):
    payload = {"items": [{key: "ผู้รับผิดชอบตัวอย่าง"}]}
    assert sanitize_payload(payload) == {"items": [{}]}
    assert problems(payload)
    contexts = {f"/items/*/{key}": "work_attribution"}
    assert sanitize_payload(payload, field_contexts=contexts) == payload
    assert problems(payload, contexts) == []
    assert problems(payload, {f"/other/*/{key}": "work_attribution"})
    artifact = tmp_path / "undeclared.json"
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="public artifact policy rejected"):
        validate_public_artifacts([ArtifactInput("candidate", "source_dataset", artifact)])


def test_person_role_counts_remain_aggregate_fields():
    payload = {"inventor_count": 4, "coordinator_count": 2,
               "scores": {"social": 7.5, "social_sd": 1.2},
               "expenses": {"exp_pct_medical": 10, "pct_medical": 5}}
    assert sanitize_payload(payload) == payload
    assert problems(payload) == []


@pytest.mark.parametrize("key", ["diagnosis", "birthdate", "medical", "medical_history", "medical_condition", "patient_id", "user_id", "line_id", "facebook", "instagram", "social_account"])
def test_private_and_contact_aliases_are_enforced_at_all_boundaries(key, tmp_path):
    payload = {key: "example-value"}
    assert sanitize_payload(payload) == {}
    assert problems(payload)
    artifact = tmp_path / "undeclared.json"
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="public artifact policy rejected"):
        validate_public_artifacts([ArtifactInput("candidate", "source_dataset", artifact)])
    if key in {"line_id", "facebook", "instagram", "social_account"}:
        contexts = {f"/{key}": "public_contact"}
        assert sanitize_payload(payload, field_contexts=contexts) == payload
        assert problems(payload, contexts) == []
    else:
        with pytest.raises(FieldContextError):
            validate_field_contexts({f"/{key}": "public_contact"})


@pytest.mark.parametrize("text", ["โทร0812345678", "0812345678คุณตัวอย่าง", "ติดต่อ+66812345678ได้"])
def test_phones_adjacent_to_thai_prose_require_public_contact_context(text):
    payload = {"note": text}
    assert "[redacted-phone]" in sanitize_payload(payload)["note"]
    assert problems(payload)
    contexts = {"/note": "public_contact"}
    assert sanitize_payload(payload, field_contexts=contexts) == payload
    assert problems(payload, contexts) == []


def test_public_contact_container_only_keeps_declared_leaves():
    payload = {"contact": {"email": "office@example.org", "note": "ชื่อส่วนตัว", "phone": "0812345678"}}
    contexts = {"/contact/email": "public_contact"}
    assert sanitize_payload(payload, field_contexts=contexts) == {"contact": {"email": "office@example.org"}}
    assert any(".note" in p for p in problems(payload, contexts))


def test_catalog_contact_exposure_metadata_is_boolean_and_path_scoped(tmp_path):
    from app.public_artifacts import _artifact_policy_violations

    item = ArtifactInput("catalog", "catalog", tmp_path / "catalog.json")
    def report(value):
        return _artifact_policy_violations(item, {"sources": [{"privacy_projection": {"contact_fields_exposed": value}}]}, set())
    assert report(True) == []
    assert report(False) == []
    metadata = {"privacy_projection": {"contact_fields_exposed": True}}
    assert sanitize_payload(metadata) == metadata
    assert problems(metadata) == []
    assert problems({"privacy_projection": {"contact_fields_exposed": "office@example.org"}})
    assert report("office@example.org")
    assert report("true")
    assert _artifact_policy_violations(item, {"contact_fields_exposed": True}, set())


@pytest.mark.parametrize("text", ["ผู้จัดทำfoo@example.org", "foo@example.orgผู้จัดทำ", "ผู้จัดทำfoo@example.orgติดต่อ"])
def test_emails_adjacent_to_thai_prose_require_public_contact_context(text, tmp_path):
    from app.demand_artifacts import _assert_public_fields

    payload = {"owner_name": text}
    attribution = {"/owner_name": "work_attribution"}
    assert "[redacted-email]" in sanitize_payload(payload, field_contexts=attribution)["owner_name"]
    assert any("email" in problem for problem in problems(payload, attribution))
    contact = {"/owner_name": "public_contact"}
    assert sanitize_payload(payload, field_contexts=contact) == payload
    assert problems(payload, contact) == []
    artifact = tmp_path / "undeclared.json"
    artifact.write_text(json.dumps({"note": text}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="email"):
        validate_public_artifacts([ArtifactInput("candidate", "source_dataset", artifact)])
    with pytest.raises(ValueError, match="contact value"):
        _assert_public_fields({"note": text}, 1)


def test_public_contact_can_include_a_postal_contact_address():
    payload = {"address": "ที่อยู่ 123 Example Road โทรศัพท์ 0812345678", "home_address": "ที่อยู่บ้านส่วนตัว"}
    contexts = {"/address": "public_contact"}
    assert sanitize_payload(payload, field_contexts=contexts) == {"address": payload["address"]}
    assert problems({"address": payload["address"]}, contexts) == []
    assert problems(payload, contexts)


def test_preview_diagnostics_do_not_echo_contacts_in_dictionary_keys():
    changes = []
    sanitize_payload({"private@example.org": {"phone": "0812345678"}}, changes=changes)
    assert changes == [("/{key}/phone", "contact key")]


@pytest.mark.parametrize("pointer,context", [
    ("/api_key", "public_contact"), ("/national_id", "record_identifier"),
    ("/personId", "work_attribution"), ("/household_id/name", "work_attribution"),
    ("/home_address", "public_location"), ("/phone", "work_attribution"),
    ("/email", "organization"), ("/owner_name", "public_measure"),
    ("/research_leads/*", "work_attribution"), ("/x", "allow_everything"),
    ("", "work_attribution"), ("/x~2name", "work_attribution"),
])
def test_invalid_or_private_field_declarations_are_rejected(pointer, context):
    with pytest.raises(FieldContextError):
        validate_field_contexts({pointer: context})


def test_public_attribution_does_not_allow_contact_values_or_private_finances():
    contexts = {"/owner_name": "work_attribution"}
    assert problems({"owner_name": "office@example.org"}, contexts)
    assert problems({"owner_name": "record 42 personal income 8000"}, contexts)
    assert problems({"owner_name": "restricted_source"}, contexts)


@pytest.mark.parametrize("value", [
    "password=visible-value", "https://example.org/?access_token=visible-value",
    "case 22 medical condition diabetes",
])
def test_public_contact_does_not_exempt_credentials_or_health(value):
    assert problems({"contact": value}, {"/contact": "public_contact"})


def test_parent_object_cannot_receive_blanket_context():
    payload = {"owner": {"name": "ตัวอย่าง", "email": "private@example.org"}}
    contexts = {"/owner": "work_attribution"}
    with pytest.raises(FieldContextError, match="scalar"):
        sanitize_payload(payload, field_contexts=contexts)
    assert any("scalar" in p for p in problems(payload, contexts))


def test_numeric_measures_and_record_codes_have_explicit_context():
    payload = {"count": 66812345678, "project_code": "0812345678"}
    contexts = {"/count": "public_measure", "/project_code": "record_identifier"}
    assert sanitize_payload(payload, field_contexts=contexts) == payload
    assert problems(payload, contexts) == []
    assert problems(payload)
    assert problems({"project_code": "โทรศัพท์: 0812345678"}, contexts)


def test_array_wildcard_is_not_an_object_map_wildcard():
    contexts = {"/items/*/owner_name": "work_attribution"}
    payload = {"items": {"*": {"owner_name": "ชื่อส่วนตัว"}}}
    assert sanitize_payload(payload, field_contexts=contexts) != payload
    assert problems(payload, contexts)


def test_context_is_scoped_to_connector_dataset():
    contract = load_runtime_connector_contract("clig_projects")
    contract["dataset_grains"][1].pop("field_contexts")
    row = {"project_id": "example", "researcher_name_th": "ผู้วิจัยตัวอย่าง"}
    prepared = prepare_contract_records(contract, [("projects", row), ("policy_candidates", row)])
    assert "researcher_name_th" in prepared[0].payload
    assert "researcher_name_th" not in prepared[1].payload


def test_preview_reports_changes_without_contact_values(capsys, tmp_path):
    private = "private@example.org"
    row = {"project_id": "example", "researcher_name_th": "ผู้วิจัยตัวอย่าง", "email": private}
    report = preview_connector([row], "clig_projects", "projects")
    assert report["status"] == "candidate_valid"
    assert report["changes"] == [{"pointer": "/email", "reason": "contact key", "occurrences": 1}]
    path = tmp_path / "records.json"
    path.write_text(json.dumps([row]), encoding="utf-8")
    assert main([str(path), "--source", "clig_projects", "--dataset-key", "projects"]) == 0
    assert private not in capsys.readouterr().out
