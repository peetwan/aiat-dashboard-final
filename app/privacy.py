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
MAX_RECORD_ID_LENGTH = 200


class RecordIdentityError(ValueError):
    """A connector record cannot produce a safe, stable database identity."""


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


def payload_field_value(payload: dict, field_path: str) -> Any:
    """Read an exact dotted field path without guessing similar field names."""

    current: Any = payload
    for part in field_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def contract_record_id(
    payload: dict,
    identity_options: list[list[str]],
    fallback_hash: str,
) -> str:
    """Resolve the first complete contract identity alternative.

    Each inner list is a composite key.  A single-field key remains readable;
    composite keys are hashed into a fixed-width identifier.  Payload hashing
    is only used when the contract explicitly opts in with ``$payload_hash``.
    """

    for option in identity_options:
        if option == ["$payload_hash"]:
            return fallback_hash
        values: list[Any] = []
        complete = True
        for field_path in option:
            value = payload_field_value(payload, field_path)
            if value in (None, "") or isinstance(value, (dict, list)):
                complete = False
                break
            values.append(value)
        if not complete:
            continue
        if len(values) == 1:
            record_id = str(values[0])
            if len(record_id) > MAX_RECORD_ID_LENGTH:
                raise RecordIdentityError(
                    f"identity field {option[0]} exceeds {MAX_RECORD_ID_LENGTH} characters"
                )
            return record_id
        encoded = json.dumps(values, ensure_ascii=False, sort_keys=False, separators=(",", ":"))
        return "composite:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    raise RecordIdentityError("none of the contract identity_options is complete")


def contract_as_of(payload: dict, as_of_fields: list[str]) -> str | None:
    """Return the first non-empty, scalar as-of field declared by the contract."""

    for field_path in as_of_fields:
        value = payload_field_value(payload, field_path)
        if value in (None, "") or isinstance(value, (dict, list)):
            continue
        as_of = str(value)
        if len(as_of) > 100:
            raise RecordIdentityError(f"as_of field {field_path} exceeds 100 characters")
        return as_of
    return None


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
