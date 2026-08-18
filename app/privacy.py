from __future__ import annotations

import hashlib
import json
import re
from typing import Any


# Ingestion-side privacy projection.
#
# Policy (mirrors the canonical workspace rule): drop person-level contact and
# identity fields, redact phone/email values, and keep every public measure the
# source publishes — household/financial aggregates, geography, and record codes
# included.  Matching is token-bounded (after camelCase -> snake_case
# normalisation), not substring-based, so public fields whose names merely
# contain a sensitive word — `address_province` (geography), `citizen_count`
# (aggregate), `secretariat_name` (organisation) — are not silently lost.
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
PHONE_RE = re.compile(
    r"(?<!\d)(?:(?:\+?66)[\s().-]*[1-9]|0[1-9])(?:[\s().-]*\d){7,8}(?!\d)"
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
    return None


def sanitize_payload(
    value: Any,
    *,
    dropped: list[tuple[str, str]] | None = None,
) -> Any:
    """Drop forbidden keys and redact contact values.

    Pass a list as ``dropped`` to record ``(key, reason)`` for every removed
    field — dropping is otherwise silent, and "why did my field disappear?" is
    the first question a connector author asks.
    """

    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            reason = forbidden_key_reason(key)
            if reason is not None:
                if dropped is not None:
                    dropped.append((str(key), reason))
                continue
            clean[str(key)] = sanitize_payload(item, dropped=dropped)
        return clean
    if isinstance(value, list):
        return [sanitize_payload(item, dropped=dropped) for item in value]
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
