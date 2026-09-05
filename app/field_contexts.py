"""บริบทของฟิลด์สาธารณะ ใช้ร่วมกันระหว่าง ingestion และ publication.

ประกาศเฉพาะ leaf ที่ต้องอธิบายเพิ่มใน contract โดยใช้ JSON pointer;
* แทนสมาชิก array เท่านั้น ไม่ได้อนุญาตทั้ง object หรือทั้ง source.
"""
from __future__ import annotations

import math
import re
from typing import Any

CONTEXTS = frozenset({
    "work_attribution", "organization", "public_contact", "public_location",
    "record_identifier", "public_measure",
})
_HARD_KEY = re.compile(
    r"(?:^|_)(?:password|passwd|secret|token|cookie|authorization|credential|api_?key|"
    r"citizen_?id|national_?id|id_?card|person_?id|patient_?id|household_?id|"
    r"respondent_?id|member_?id|student_?id|user_?id|social_security|"
    r"birth|birthdate|birthday|date_of_birth|dob|medical|diagnosis|"
    r"personal_income|household_debt|home_address|residential_address)(?:_|$)"
)
_NAME_KEY = re.compile(
    r"(?:^|_)(?:(?:first|last|full|person|owner|researcher|contact)_?name|"
    r"rights_owner|contact_person)(?:_|$)"
)
_CONTACT_KEY = re.compile(
    r"(?:^|_)(?:phone|telephone|tel|mobile|e_?mail|contact|owner_?contact|"
    r"line_id|line_oa|line_account|facebook|instagram|social)(?:_|$)"
)


class FieldContextError(ValueError):
    pass


def key_kind(key: str) -> str | None:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    text = re.sub(r"[^a-z0-9ก-๙]+", "_", text.lower()).strip("_")
    if _HARD_KEY.search(text) or any(x in text for x in (
        "เลขบัตร", "วันเกิด", "วันเดือนปีเกิด", "ที่อยู่บ้าน", "โรคประจำตัว",
    )):
        return "private"
    if _NAME_KEY.search(text) or "ชื่อบุคคล" in text or "ชื่อ_นามสกุล" in text:
        return "name"
    if _CONTACT_KEY.search(text) or any(x in text for x in (
        "โทรศัพท์", "เบอร์โทร", "อีเมล", "อีเมล์", "ผู้ติดต่อ", "ช่องทางติดต่อ",
    )):
        return "contact"
    if re.search(r"(?:^|_)address(?:_|$)", text) or "ที่อยู่" in text:
        return "address"
    return None


def pointer_child(pointer: str, key: object) -> str:
    # ~2 is an internal sentinel: literal object key '*' cannot match array '*'.
    token = str(key).replace("~", "~0").replace("/", "~1").replace("*", "~2")
    return pointer + "/" + token


def validate_field_contexts(value: Any, label: str = "field_contexts") -> dict[str, str]:
    if not isinstance(value, dict):
        raise FieldContextError(f"{label} must be an object of JSON pointers and contexts")
    for pointer, context in value.items():
        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise FieldContextError(f"{label}: use a JSON pointer such as /researcher_name")
        parts = pointer.split("/")[1:]
        if any(not p or re.search(r"~(?![01])|[\x00-\x1f]", p) for p in parts) or parts[-1] == "*":
            raise FieldContextError(f"{label}: context must identify a scalar field")
        if not isinstance(context, str) or context not in CONTEXTS:
            raise FieldContextError(f"{label}: unknown field context")
        decoded = [p.replace("~1", "/").replace("~0", "~") for p in parts]
        if any(key_kind(p) == "private" for p in decoded):
            raise FieldContextError(f"{label}: credentials/private identifiers cannot have public contexts")
        if not context_allows_key(decoded[-1], context):
            raise FieldContextError(f"{label}: field kind does not match {context}")
    return dict(value)


def context_allows_key(key: str, context: str | None) -> bool:
    if context not in CONTEXTS:
        return False
    kind = key_kind(key)
    if kind == "private":
        return False
    if kind == "name":
        return context in {"work_attribution", "organization", "public_contact"}
    if kind == "contact":
        return context == "public_contact"
    if kind == "address":
        return context in {"public_location", "public_contact"}
    return True


def context_allows_value_reason(context: str | None, reason: str, value: Any) -> bool:
    if context == "public_contact":
        return reason in {"email-like value", "labelled contact value", "Thai phone-like value", "Thai phone-like numeric value", "home-address-like value"}
    if context == "public_location":
        return reason == "home-address-like value"
    if context in {"record_identifier", "public_measure"}:
        numeric = type(value) in (int, float) and math.isfinite(value)
        if isinstance(value, str):
            numeric = bool(re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value))
        return numeric and reason in {"Thai phone-like value", "Thai phone-like numeric value"}
    return False
