from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.field_contexts import (
    FieldContextError, context_allows_key, context_allows_value_reason,
    key_kind, pointer_child, validate_field_contexts,
)


# Ingestion-side privacy projection.
#
# field_contexts ใน contract ระบุชื่อเจ้าของงานและข้อมูลติดต่องานที่เก็บได้
# ช่องส่วนตัวที่ไม่ได้ระบุบริบทยังถูกตัดหรือปิดค่า โดยคง aggregate พื้นที่
# และรหัสระเบียนไว้ การจับชื่อ key ใช้ขอบเขตคำหลังแปลง camelCase เป็น
# snake_case จึงไม่ตัด address_province, citizen_count หรือ secretariat_name
# เพียงเพราะมีคำบางส่วนคล้ายชื่อฟิลด์ส่วนตัว
_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")


def normalise_key(key: object) -> str:
    text = _CAMEL_BOUNDARY.sub(r"\1_\2", str(key))
    return re.sub(r"[^a-z0-9ก-๙]+", "_", text.lower()).strip("_")


# Administrative-geography keys prefixed with `address_` are location metadata,
# not a person's street address.  A map-first dashboard cannot place records
# without them.
_ADMIN_GEO_ADDRESS = re.compile(
    r"^address_(?:province|district|subdistrict|sub_district|tambon|amphoe|amphur|"
    r"region|zone|zipcode|postcode|postal_code)$"
)

# Each rule matches whole `_`-bounded tokens.  Concatenated legacy spellings the
# previous substring set caught explicitly (ownercontact, researchername,
# firstname, apikey, ...) are covered by the optional `_?` in each alternative.
# A bare `citizen` key stays: it is usually an aggregate count, and if it is a
# container its person-level sub-keys are still dropped recursively.
FORBIDDEN_KEY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "contact key",
        re.compile(
            r"(?:^|_)(?:phone|telephone|tel|mobile|e_?mail|contact|"
            r"owner_?contact|contact_?person)(?:_|$)"
        ),
    ),
    (
        "person name key",
        re.compile(
            r"(?:^|_)(?:first|last|person|owner|researcher|contact)_?name(?:_|$)"
        ),
    ),
    (
        "person id key",
        re.compile(r"(?:^|_)(?:citizen_?id|national_?id|id_?card)(?:_|$)"),
    ),
    (
        "credential key",
        re.compile(
            r"(?:^|_)(?:password|secret|token|cookie|authorization|api_?key)(?:_|$)"
        ),
    ),
    (
        "address key",
        re.compile(
            r"(?:^|_)(?:(?:home|residential|mailing|postal)_?address|address)(?:_|$)"
        ),
    ),
)

EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
# Thai phone numbers are 9-10 digits domestically (or 8-9 digits after +66),
# and mobile/landline prefixes never have 0 as their second digit.  Requiring
# that shape keeps Buddhist-era-prefixed record codes (e.g. procurement IDs
# starting with 66/67) and other numeric measures out of the redaction.
# ASCII identifier boundaries protect hashes/codes while Thai prose may touch a phone.
PHONE_RE = re.compile(
    r"(?<![A-Za-z0-9_.])(?:"
    r"\+66(?:[\s.-]*\(0\))?[\s().-]*"
    r"(?:(?:[2-5]|7)(?:[\s().-]*\d){7}|[689](?:[\s().-]*\d){8})|"
    r"66[\s()-]*(?:(?:[2-5]|7)(?:[\s()-]*\d){7}|[689](?:[\s()-]*\d){8})|"
    r"0(?:[2-5]|7)(?:[\s().-]*\d){7}|0[689](?:[\s().-]*\d){8}"
    r")(?![A-Za-z0-9_.])"
)
MAX_RECORD_ID_LENGTH = 200


class RecordIdentityError(ValueError):
    """A connector record cannot produce a safe, stable database identity."""


def forbidden_key_reason(key: object) -> str | None:
    """Explain why a key is dropped, or return None when it is allowed."""

    normalised = normalise_key(key)
    if _ADMIN_GEO_ADDRESS.fullmatch(normalised):
        return None
    for reason, rule in FORBIDDEN_KEY_RULES:
        if rule.search(normalised):
            return reason
    kind = key_kind(str(key))
    if kind in {"private", "name", "contact"}:
        return {"private": "private key", "name": "person name key", "contact": "contact key"}[kind]
    return None


def sanitize_payload(
    value: Any,
    *,
    dropped: list[tuple[str, str]] | None = None,
    field_contexts: dict[str, str] | None = None,
    changes: list[tuple[str, str]] | None = None,
) -> Any:
    """Project a record using optional, exact field contexts from its contract.

    ``changes`` reports paths and reasons without logging values. ``dropped``
    retains the existing key/reason interface for connector authors.
    """
    contexts = validate_field_contexts({} if field_contexts is None else field_contexts)

    def report_pointer(pointer: str) -> str:
        # Object-map keys can themselves contain contact values.
        return "/".join(
            "{key}" if EMAIL_RE.search(part) or PHONE_RE.search(part) else part
            for part in pointer.split("/")
        )

    def walk(item: Any, pointer: str, protected: bool = False) -> Any:
        context = contexts.get(pointer)
        if context and isinstance(item, (dict, list)):
            raise FieldContextError("field_contexts must target scalar values, not containers")
        if isinstance(item, dict):
            clean = {}
            for key, child in item.items():
                child_pointer = pointer_child(pointer, key)
                child_context = contexts.get(child_pointer)
                reason = forbidden_key_reason(key)
                allowed = not isinstance(child, (dict, list)) and context_allows_key(str(key), child_context)
                descend = isinstance(child, (dict, list)) and key_kind(str(key)) != "private" and any(
                    p.startswith(child_pointer + "/") for p in contexts
                )
                if (reason or protected) and not allowed and not descend:
                    reason = reason or "undeclared field in private/contact container"
                    if dropped is not None:
                        dropped.append((str(key), reason))
                    if changes is not None:
                        changes.append((report_pointer(child_pointer), reason))
                    continue
                clean[str(key)] = walk(child, child_pointer, protected or bool(reason and not allowed))
            return clean
        if isinstance(item, list):
            return [walk(child, pointer + "/*", protected) for child in item]
        if isinstance(item, str):
            for regex, reason, replacement in (
                (EMAIL_RE, "email-like value", "[redacted-email]"),
                (PHONE_RE, "Thai phone-like value", "[redacted-phone]"),
            ):
                if regex.search(item) and not context_allows_value_reason(context, reason, item):
                    item = regex.sub(replacement, item)
                    if changes is not None:
                        changes.append((report_pointer(pointer), reason))
        return item

    return walk(value, "")


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
