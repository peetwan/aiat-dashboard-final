from __future__ import annotations

import hashlib
import json
import re
from typing import Any


FORBIDDEN_KEY_PARTS = {
    "email",
    "phone",
    "mobile",
    "telephone",
    "address",
    "citizen",
    "id_card",
    "national_id",
    "password",
    "secret",
    "token",
    "cookie",
    "authorization",
    "api_key",
    "apikey",
    "ownercontact",
    "owner_name",
    "ownername",
    "contactperson",
    "contact_name",
    "firstname",
    "first_name",
    "lastname",
    "last_name",
    "person_name",
    "personname",
    "researcher_name",
    "researchername",
}
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?66|0)\d[\d -]{7,12}\d(?!\d)")


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(part in normalized for part in FORBIDDEN_KEY_PARTS):
                continue
            clean[str(key)] = sanitize_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, str):
        value = EMAIL_RE.sub("[redacted-email]", value)
        return PHONE_RE.sub("[redacted-phone]", value)
    return value


def payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def stable_record_id(payload: dict, fallback_hash: str) -> str:
    for key in (
        "source_record_id",
        "record_id",
        "innovationid",
        "requirementid",
        "resource_id",
        "id",
        "code",
    ):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)[:200]
    return fallback_hash
