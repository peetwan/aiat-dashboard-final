"""Explicit, fail-closed public-detail candidates for the Phase 8 review.

This module projects only named fields from accepted release tables.  It never
serializes source rows or ``*_details_json`` cells and never exposes locators.
The result is staging input, not publication approval.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable
from urllib.parse import parse_qsl, unquote, urlsplit

from app.privacy import EMAIL_RE, PHONE_RE, SOCIAL_CONTACT_RE, sanitize_payload
from app.publication import _privacy_problems

from .common import PipelineError, TextParser, normalize, readable, stable_id
from .field_approval import (
    approved_detail_measures,
    validate_detail_owner_approval,
)

REQUIRED_MEASURES = (
    "K01B",
    "K03",
    "K04",
    "C04_LISTED",
    "K05",
    "K07",
    "C08_PARTICIPATING",
    "K12",
)
_COMMON_FIELDS = {
    "entity_id",
    "label",
    "identity_status",
    "province_codes",
    "category_codes",
    "source_ids",
    "detail_availability",
}
_PERSON_LABEL = re.compile(
    r"^(?:(?:นาย|นางสาว|นาง|เด็กชาย|เด็กหญิง|ดร\.|ศาสตราจารย์|รองศาสตราจารย์|ผู้ช่วยศาสตราจารย์)\s|(?:mr|mrs|ms|miss|dr|prof)\.\s)",
    re.I,
)
_PRIVATE_TEXT = re.compile(
    r"(?:เลขประจำตัวประชาชน|เลขบัญชี|รหัสผ่าน|password|passcode|meeting\s*id|"
    r"authorization\s*:|bearer\s+[a-z0-9._~-]+)",
    re.I,
)
_LOCAL_PATH = re.compile(
    r"(?:file://|(?:^|\s)/(?:Users|home|private|var|tmp)/|[A-Za-z]:\\|"
    r"(?:raw|normalized|evidence)://)",
    re.I,
)
_CREDENTIAL_QUERY = re.compile(
    r"(?:token|signature|credential|secret|password|passcode|api[_-]?key|authorization)",
    re.I,
)
_DATE_TEXT = re.compile(r"^[0-9TtZz:+. /-]+$")

_SOURCE_ALIASES = {
    "atlocal-v1": "atlocal",
    "cultural-map-v1": "cultural_map",
    "icommunity-v1": "icommunity",
}


def _public_readable(value: object) -> str:
    parser = TextParser()
    parser.feed(str(value or ""))
    parser.close()
    return "\n".join(
        normalize(line)
        for line in "".join(parser.parts).splitlines()
        if normalize(line)
    )


def _source_key(source: Any) -> str:
    value = str(source or "")
    return _SOURCE_ALIASES.get(value, value)


def _rows(tables: dict[str, list[dict]], name: str) -> list[dict]:
    rows = tables.get(name, [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"Public detail table is malformed: {name}")
    return rows


def _json_list(value: Any) -> list:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PipelineError("Public detail input has invalid JSON list") from exc
    if not isinstance(decoded, list):
        raise PipelineError("Public detail input JSON cell is not a list")
    return decoded


def _json_object(value: Any) -> dict:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PipelineError("Public detail input has invalid JSON object") from exc
    if not isinstance(decoded, dict):
        raise PipelineError("Public detail input JSON cell is not an object")
    return decoded


def _person_identity_core(value: Any) -> str:
    text = readable(value)
    text = re.sub(
        r"^(?:นาย|นางสาว|นาง|ดร\.?|ผศ\.?|รศ\.?|ศ\.?|ครู)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(
        r"\s+(?:ยาย|ตา|ป้า|ลุง|ครู)$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()


def _group(rows: Iterable[dict], key: str) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        value = str(row.get(key, ""))
        if value:
            result[value].append(row)
    return result


def _definition_ids(definitions: Any) -> set[str]:
    if isinstance(definitions, dict):
        definitions = definitions.get("measures", [])
    if not isinstance(definitions, list):
        raise PipelineError("Public detail measure definitions are malformed")
    return {
        str(row.get("measure_id", ""))
        for row in definitions
        if isinstance(row, dict) and row.get("measure_id")
    }


def _safe_public_scalar(key: str, value: str) -> bool:
    return not _privacy_problems(
        {key: value},
        artifact_path="staged-detail-field",
        restricted_source_ids=set(),
        profile="aggregate_public",
        field_contexts={},
    )


def _clean_text(value: Any, limit: int) -> tuple[str | None, bool, bool]:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None, False, False
    text = readable(value)
    if not text or _PRIVATE_TEXT.search(text) or _LOCAL_PATH.search(text):
        return None, False, False
    changes: list[tuple[str, str]] = []
    clean = sanitize_payload(text, changes=changes)
    if not isinstance(clean, str) or not clean.strip():
        return None, False, bool(changes)
    excerpted = len(clean) > limit
    candidate = clean[:limit] if excerpted else clean
    if not _safe_public_scalar("text", candidate):
        return None, False, bool(changes)
    return candidate, excerpted, bool(changes)


def _clean_label(value: Any, limit: int = 300) -> str | None:
    text, excerpted, sanitized = _clean_text(value, limit)
    if not text or excerpted or sanitized:
        return None
    return text


def _clean_finalized_label(value: Any, limit: int = 300) -> str | None:
    """Clean a public label after finalizing any pending HTML character reference."""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    text = _public_readable(value)
    if (
        not text
        or normalize(text) != normalize(value)
        or len(text) > limit
        or _PRIVATE_TEXT.search(text)
        or _LOCAL_PATH.search(text)
    ):
        return None
    changes: list[tuple[str, str]] = []
    clean = sanitize_payload(text, changes=changes)
    if not isinstance(clean, str) or not clean.strip() or changes:
        return None
    return clean if _safe_public_scalar("text", clean) else None


_REVIEWED_PUBLIC_TITLE_CONTEXT = "public_title"
_REVIEWED_PUBLIC_TITLE_PROBLEM = (
    "staged-reviewed-public-title.label: social contact value"
)
_EXPLICIT_CONTACT_MARKER = re.compile(
    r"(?:[:：=@]|\bhttps?://|\b(?:contact|ติดต่อ)\b)", re.I
)


def _reviewed_public_title(
    policy: dict,
    measure: str,
    entity_id: str,
    source_keys: set[str],
    value: Any,
) -> str | None:
    reviewed = policy.get("reviewed_label_contexts", {})
    by_measure = reviewed.get(measure, {}) if isinstance(reviewed, dict) else {}
    spec = by_measure.get(entity_id) if isinstance(by_measure, dict) else None
    if (
        not isinstance(spec, dict)
        or spec.get("context") != _REVIEWED_PUBLIC_TITLE_CONTEXT
        or not isinstance(value, str)
        or not source_keys
    ):
        return None
    reviewed_source_keys = spec.get("source_keys")
    if (
        not isinstance(reviewed_source_keys, list)
        or any(not isinstance(key, str) or not key for key in reviewed_source_keys)
        or len(reviewed_source_keys) != len(set(reviewed_source_keys))
        or set(reviewed_source_keys) != source_keys
        or spec.get("label_sha256") != hashlib.sha256(value.encode("utf-8")).hexdigest()
    ):
        return None
    text = _public_readable(value)
    if (
        not text
        or text != normalize(value)
        or len(text) > 300
        or _PRIVATE_TEXT.search(text)
        or _LOCAL_PATH.search(text)
        or _EXPLICIT_CONTACT_MARKER.search(text)
    ):
        return None
    problems = _privacy_problems(
        {"label": text},
        artifact_path="staged-reviewed-public-title",
        restricted_source_ids=set(),
        profile="aggregate_public",
        field_contexts={},
    )
    return text if problems == [_REVIEWED_PUBLIC_TITLE_PROBLEM] else None


_WITHHELD_MAPPED_TITLE = "Title withheld pending review"


def _reviewed_mapped_label_context(
    policy: dict,
    subject_id: str,
    source_keys: set[str],
    value: Any,
) -> str | None:
    reviewed = policy.get("reviewed_label_contexts", {})
    k12 = reviewed.get("K12", {}) if isinstance(reviewed, dict) else {}
    spec = k12.get(subject_id) if isinstance(k12, dict) else None
    if not isinstance(spec, dict) or spec.get("context") != "public_location":
        return None
    reviewed_source_keys = spec.get("source_keys")
    if (
        not isinstance(reviewed_source_keys, list)
        or any(not isinstance(key, str) or not key for key in reviewed_source_keys)
        or len(reviewed_source_keys) != len(set(reviewed_source_keys))
        or set(reviewed_source_keys) != source_keys
        or not isinstance(value, str)
    ):
        return None
    expected_hash = spec.get("label_sha256")
    actual_hash = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return "public_location" if expected_hash == actual_hash else None


def _clean_mapped_label(
    value: Any, context: str | None, limit: int = 300
) -> str | None:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    text = _public_readable(value)
    if (
        not text
        or len(text) > limit
        or _PRIVATE_TEXT.search(text)
        or _LOCAL_PATH.search(text)
    ):
        return None
    changes: list[tuple[str, str]] = []
    clean = sanitize_payload(text, changes=changes)
    if not isinstance(clean, str) or not clean.strip() or changes:
        return None
    field_contexts = {"/label": context} if context else {}
    problems = _privacy_problems(
        {"label": clean},
        artifact_path="staged-mapped-label",
        restricted_source_ids=set(),
        profile="aggregate_public",
        field_contexts=field_contexts,
    )
    return None if problems else clean


def _mapped_label(
    value: Any, context: str | None = None
) -> tuple[str | None, str, str | None]:
    label = _clean_mapped_label(value, context)
    if label is not None:
        return label, "available", None
    if (
        isinstance(value, (str, int, float))
        and not isinstance(value, bool)
        and _public_readable(value)
    ):
        return (
            _WITHHELD_MAPPED_TITLE,
            "withheld",
            "source_title_failed_public_scalar_admission",
        )
    return None, "not_provided", "missing_source_title"


def _date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text if _DATE_TEXT.fullmatch(text) else None


def _source_spec(policy: dict, source: str) -> dict:
    source = _source_key(source)
    spec = policy.get("sources", {}).get(source)
    if not isinstance(spec, dict):
        raise PipelineError(f"Public detail source policy is missing: {source}")
    return spec


def _canonical_source(policy: dict, source: str) -> str:
    source_id = _source_spec(policy, source).get("source_id")
    if not isinstance(source_id, str) or not source_id:
        raise PipelineError(f"Public detail source ID is missing: {source}")
    return source_id


def _system(policy: dict, source: str) -> str:
    value = _source_spec(policy, source).get("originating_system")
    if not isinstance(value, str) or not value:
        raise PipelineError(f"Public detail originating system is missing: {source}")
    return value


def _allowed(policy: dict, measure: str, source: str, group: str, field: str) -> bool:
    source = _source_key(source)
    topic = policy["detail_policies"][measure]
    source_policy = topic.get("source_allowlists", {}).get(source, {})
    values = source_policy.get(group, [])
    return isinstance(values, list) and field in values


def _policy_values(policy: dict, measure: str, source: str, key: str) -> set[str]:
    source = _source_key(source)
    values = (
        policy["detail_policies"][measure]
        .get("source_allowlists", {})
        .get(source, {})
        .get(key, [])
    )
    return {str(value) for value in values} if isinstance(values, list) else set()


def _price_amounts(
    row: dict, policy: dict, measure: str, source: str
) -> tuple[list[dict], str | None]:
    status = str(row.get("parse_status") or "")
    if status not in _policy_values(policy, measure, source, "price_parse_statuses"):
        return [], "unapproved_price_parse_status"
    currency = str(row.get("currency") or "")
    if currency not in _policy_values(policy, measure, source, "price_currencies"):
        return [], "missing_or_unapproved_price_currency"
    values = _json_list(row.get("amounts_json"))
    if not values:
        return [], "missing_parsed_price_amount"
    amounts = []
    for value in values:
        if (
            not isinstance(value, (int, float, str))
            or isinstance(value, bool)
            or not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d+)?", str(value))
            or EMAIL_RE.search(str(value))
            or PHONE_RE.search(str(value))
            or SOCIAL_CONTACT_RE.search(str(value))
        ):
            return [], "price_amount_admission_failed"
        try:
            decimal = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return [], "price_amount_admission_failed"
        if not decimal.is_finite() or decimal < 0:
            return [], "price_amount_admission_failed"
        amount = {
            "value": value,
            "status": "unspecified" if decimal == 0 else "source_reported",
        }
        if decimal == 0:
            amount["display_label"] = "price unspecified/source reports 0"
        amounts.append(amount)
    return amounts, None


def _reported_price_unit(
    row: dict, policy: dict, measure: str, source: str
) -> tuple[str | None, str]:
    """Admit only an allowlisted sale unit, never a qualifier or currency precision."""
    for field in ("reported_unit", "sale_unit", "price_unit", "unit"):
        if row.get(field) not in (None, "") and _allowed(
            policy, measure, source, "price", field
        ):
            value = _clean_label(row[field])
            return (value, "source_reported") if value else (None, "withheld")
    return None, "not_reported"


def _price_snapshot_contexts(
    tables: dict,
    policy: dict,
    input_manifest: list[dict] | None,
) -> tuple[dict[str, dict], dict[str, str]]:
    if input_manifest is None:
        return {}, {}
    if not isinstance(input_manifest, list) or any(
        not isinstance(row, dict) for row in input_manifest
    ):
        raise PipelineError("Verified input manifest is malformed")
    manifest_contexts: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for row in input_manifest:
        source_id = str(row.get("source_id") or "")
        dataset = str(row.get("dataset_key") or "")
        run_id = str(row.get("run_id") or "")
        captured_at = str(row.get("captured_at") or "")
        if source_id and dataset and run_id and captured_at:
            manifest_contexts[(source_id, dataset)].add((run_id, captured_at))

    observation_indexes: dict[str, dict[str, dict]] = {}
    snapshots: dict[str, dict] = {}
    price_refs: dict[str, str] = {}
    for price in _rows(tables, "domains/commerce/prices"):
        logical_source = str(price.get("source") or "")
        source_id = _canonical_source(policy, logical_source)
        if source_id not in observation_indexes:
            observations = _rows(tables, f"sources/{source_id}/source_observations")
            index = {str(row.get("observation_id") or ""): row for row in observations}
            if "" in index or len(index) != len(observations):
                raise PipelineError(
                    f"Price source observations are malformed: {source_id}"
                )
            observation_indexes[source_id] = index
        observation_id = str(price.get("observation_id") or "")
        observation = observation_indexes[source_id].get(observation_id)
        if observation is None:
            raise PipelineError(
                f"Price observation lacks verified source lineage: {source_id}"
            )
        dataset = str(observation.get("dataset") or "")
        contexts = manifest_contexts.get((source_id, dataset), set())
        if len(contexts) != 1:
            raise PipelineError(
                f"Price observation has ambiguous input snapshot: {source_id}/{dataset}"
            )
        run_id, captured_at = next(iter(contexts))
        observation_capture = str(observation.get("captured_at") or "")
        if observation_capture and observation_capture != captured_at:
            raise PipelineError(
                f"Price observation capture differs from input manifest: {source_id}"
            )
        snapshot_ref = stable_id(
            "price_snapshot", source_id, run_id, dataset, captured_at
        )
        snapshots[snapshot_ref] = {
            "source_id": source_id,
            "run_id": run_id,
            "dataset_key": dataset,
            "captured_at": captured_at,
            "capture_status": "verified_input_manifest",
            "price_as_of": None,
            "price_as_of_status": "not_reported",
        }
        price_id = str(price.get("source_price_id") or "")
        if not price_id or (
            price_id in price_refs and price_refs[price_id] != snapshot_ref
        ):
            raise PipelineError("Price assertion identity is missing or ambiguous")
        price_refs[price_id] = snapshot_ref
    return dict(sorted(snapshots.items())), price_refs


def price_source_snapshots(
    tables: dict, policy: dict, input_manifest: list[dict] | None
) -> dict[str, dict]:
    """Return compact verified capture contexts referenced by public prices."""
    snapshots, _ = _price_snapshot_contexts(tables, policy, input_manifest)
    return snapshots


def _child_disposition(
    candidate_count: int, emitted_count: int, reasons: Iterable[str]
) -> dict:
    counts = Counter(reasons)
    withheld_count = candidate_count - emitted_count
    if withheld_count < 0 or withheld_count != sum(counts.values()):
        raise PipelineError("Public detail child disposition does not reconcile")
    return {
        "candidate_count": candidate_count,
        "emitted_count": emitted_count,
        "withheld_count": withheld_count,
        "withheld_reasons": dict(sorted(counts.items())),
    }


def _merge_child_dispositions(groups: Iterable[dict]) -> dict:
    merged: dict[str, dict] = {}
    for group in groups:
        for name, disposition in group.items():
            target = merged.setdefault(
                name,
                {
                    "candidate_count": 0,
                    "emitted_count": 0,
                    "withheld_reasons": Counter(),
                },
            )
            target["candidate_count"] += int(disposition["candidate_count"])
            target["emitted_count"] += int(disposition["emitted_count"])
            target["withheld_reasons"].update(disposition["withheld_reasons"])
    return {
        name: _child_disposition(
            values["candidate_count"],
            values["emitted_count"],
            (
                reason
                for reason, count in values["withheld_reasons"].items()
                for _ in range(count)
            ),
        )
        for name, values in sorted(merged.items())
    }


def _public_url(
    value: Any,
    policy: dict,
    source: str,
    *,
    media: bool = False,
    measure: str | None = None,
) -> str | None:
    source = _source_key(source)
    if not isinstance(value, str) or not value:
        return None
    spec = _source_spec(policy, source)
    topic_spec = (
        policy["detail_policies"][measure].get("source_allowlists", {}).get(source, {})
        if measure
        else {}
    )
    hosts_key = "media_url_hosts" if media else "public_url_hosts"
    paths_key = "media_url_path_patterns" if media else "public_url_path_patterns"
    query_key = "media_query_parameters" if media else "public_query_parameters"
    hosts = topic_spec.get(hosts_key, spec.get(hosts_key, []))
    patterns = topic_spec.get(paths_key, spec.get(paths_key, []))
    query_allowlist = topic_spec.get(query_key, spec.get(query_key, []))
    if (
        not isinstance(hosts, list)
        or not isinstance(patterns, list)
        or not isinstance(query_allowlist, list)
    ):
        raise PipelineError(f"Malformed URL policy for {source}")
    try:
        parsed = urlsplit(value)
        decoded = value
        for _ in range(3):
            expanded = unquote(decoded)
            if expanded == decoded:
                break
            decoded = expanded
        expanded_url = urlsplit(decoded)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in hosts
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or parsed.fragment
            or expanded_url.fragment
            or "\\" in decoded
            or any(ord(character) < 32 for character in decoded)
            or _CREDENTIAL_QUERY.search(expanded_url.query)
            or EMAIL_RE.search(decoded)
            or PHONE_RE.search(expanded_url.path)
            or SOCIAL_CONTACT_RE.search(decoded)
        ):
            return None
        if patterns and not any(
            re.fullmatch(pattern, expanded_url.path) for pattern in patterns
        ):
            return None
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        if parsed.query and (
            not pairs or any(key not in query_allowlist for key, _ in pairs)
        ):
            return None
        if len({key for key, _ in pairs}) != len(pairs):
            return None
    except (ValueError, UnicodeError):
        return None
    return value


def _description(kind: Any, value: Any, source: str, limit: int) -> dict | None:
    text, excerpted, sanitized = _clean_text(value, limit)
    if not text:
        return None
    return {
        "kind": _clean_label(kind) or "description",
        "text": text,
        "is_excerpt": excerpted,
        "was_sanitized": sanitized,
        "source_id": source,
    }


def _location(row: dict, source_id: str, *, label_field: str | None = None) -> dict:
    result = {
        "source_id": source_id,
        "location_role": _clean_label(row.get("location_role")) or "unspecified",
        "province_code": str(row.get("province_code") or "") or None,
        "district_code": str(row.get("district_code") or "") or None,
        "subdistrict_code": str(row.get("subdistrict_code") or "") or None,
        "province": _clean_label(row.get("province_normalized")),
        "district": _clean_label(row.get("district_normalized")),
        "subdistrict": _clean_label(row.get("subdistrict_normalized")),
        "status": _clean_label(
            row.get("status")
            or row.get("resolution_status")
            or row.get("geography_status")
        ),
    }
    if label_field:
        result["label"] = _clean_label(row.get(label_field))
    return result


def _media(
    row: dict, policy: dict, source: str, *, measure: str | None = None
) -> dict | None:
    url = _public_url(
        row.get("url_or_value") or row.get("image_url"),
        policy,
        source,
        media=True,
        measure=measure,
    )
    if not url:
        return None
    raw_label = row.get("label") or row.get("caption")
    label = _clean_label(raw_label)
    return {
        "media_id": str(
            row.get("media_id")
            or row.get("image_id")
            or row.get("source_media_id")
            or ""
        ),
        "kind": _clean_label(row.get("media_kind")) or "image",
        "url": url,
        "label": label,
        "label_availability": (
            "withheld"
            if raw_label not in (None, "") and label is None
            else "available"
            if label is not None
            else "not_provided"
        ),
        "label_withholding_reason": (
            "public_scalar_admission_failed"
            if raw_label not in (None, "") and label is None
            else None
        ),
        "status": "source_reference_not_fetched",
        "reference_only": True,
        "source_id": _canonical_source(policy, source),
    }


def _identity_review(
    identity_status: Any,
    source_ids: Iterable[str],
    *,
    kept_separate: bool = False,
) -> dict[str, Any]:
    status = str(identity_status or "unknown")
    sources = {str(source_id) for source_id in source_ids if source_id}
    review = {
        "outcome": "source_record_only",
        "merge_scope": None,
        "counting": "separate",
        "name_quality": "supported",
    }
    if kept_separate:
        review["outcome"] = "kept_separate"
    elif status == "provisional_malformed_name":
        review.update(outcome="malformed_name", name_quality="unavailable")
    elif status in {
        "provisional_unresolved_candidates",
        "reviewed_possible_duplicate",
        "unresolved_possible_duplicate",
    }:
        review["outcome"] = "unresolved"
    elif status == "reviewed_product_family":
        review.update(outcome="grouped_family", counting="grouped")
    elif status in {
        "provisional_reported_activity",
        "reported_occurrence_provisional",
        "provisional_parent_occurrence",
    }:
        review["outcome"] = "reported_activity"
    elif status in {
        "accepted_cross_source_link",
        "reviewed_cross_source",
        "reviewed_identity",
        "reviewed_extended_identity",
        "supported_reviewed_merge",
        "supported_within_source_merge",
    }:
        review.update(
            outcome="merged",
            merge_scope=(
                "cross_source"
                if status
                in {"accepted_cross_source_link", "reviewed_cross_source"}
                or len(sources) > 1
                else "within_source"
            ),
            counting="merged",
        )
    elif status == "unknown":
        review.update(outcome="unknown", name_quality="unknown")
    return review


def _base_detail(
    entity_id: str,
    label: str,
    identity_status: Any,
    source_ids: Iterable[str],
    systems: Iterable[str],
    *,
    province_codes: Iterable[str] = (),
    category_codes: Iterable[str] = (),
    kept_separate: bool = False,
) -> dict:
    return {
        "entity_id": entity_id,
        "label": label,
        "identity_status": _clean_label(identity_status) or "unknown",
        "province_codes": sorted({str(value) for value in province_codes if value}),
        "category_codes": sorted({str(value) for value in category_codes if value}),
        "descriptions": [],
        "listings": [],
        "locations": [],
        "media": [],
        "relationships": [],
        "children": {},
        "flags": {
            "missing_geography": not any(province_codes),
            "unresolved_identity": "unresolved" in str(identity_status).lower()
            or "possible_duplicate" in str(identity_status).lower(),
            "limited_coverage": True,
            "owner_checkpoint_required": True,
            "additional_field_review_status": "pending_owner_acceptance",
            "identity_review": _identity_review(
                identity_status, source_ids, kept_separate=kept_separate
            ),
        },
        "source_ids": sorted(set(source_ids)),
        "originating_systems": sorted(set(systems)),
        "detail_availability": "available",
    }


def _privacy_contexts(policy: dict) -> dict[str, str]:
    contexts = policy.get("detail_field_contexts", {})
    if not isinstance(contexts, dict):
        raise PipelineError("Public detail field contexts are malformed")
    return contexts


def _finalize(
    detail: dict,
    policy: dict,
    measure: str,
    additional_field_contexts: dict[str, str] | None = None,
) -> str | None:
    expected = set(policy["detail_policies"][measure].get("detail_fields", []))
    if not _COMMON_FIELDS <= expected or set(detail) != expected:
        raise PipelineError(f"{measure} detail fields differ from policy allowlist")
    field_contexts = dict(_privacy_contexts(policy))
    for pointer, context in (additional_field_contexts or {}).items():
        if pointer in field_contexts and field_contexts[pointer] != context:
            raise PipelineError(f"Conflicting public detail field context: {pointer}")
        field_contexts[pointer] = context
    problems = _privacy_problems(
        detail,
        artifact_path=f"staged-detail/{measure}",
        restricted_source_ids=set(),
        profile="aggregate_public",
        field_contexts=field_contexts,
    )
    return "public_detail_privacy_check" if problems else None


class _Builder:
    def __init__(
        self,
        tables: dict[str, list[dict]],
        policy: dict,
        input_manifest: list[dict] | None,
    ):
        self.tables = tables
        self.policy = policy
        self.limit = int(policy.get("max_description_chars", 1000))
        self.owner_approval = validate_detail_owner_approval(policy)
        self.approved_measures = approved_detail_measures(self.owner_approval)
        _, self.price_snapshot_refs = _price_snapshot_contexts(
            tables, policy, input_manifest
        )
        self.entity_ids = {
            measure: sorted(
                {
                    str(row.get("entity_id", ""))
                    for row in _rows(tables, "entity_contributions")
                    if row.get("measure_id") == measure and row.get("entity_id")
                }
            )
            for measure in REQUIRED_MEASURES
        }
        self.mapped = {
            name: _group(
                _rows(tables, f"sources/f2_culturalmap_university/{name}"),
                "subject_id",
            )
            for name in (
                "mapped_listing_observations",
                "mapped_locations",
                "category_assertions",
                "mapped_narrative_evidence",
                "mapped_media",
            )
        }
        self.keep_separate_endpoints = {
            str(endpoint)
            for decision in _rows(
                tables, "domains/commerce/reviewed_identity_decisions"
            )
            if decision.get("decision") == "keep_separate"
            for endpoint in (decision.get("left"), decision.get("right"))
            if endpoint
        }

    def _has_keep_separate_decision(self, members: Iterable[dict]) -> bool:
        for member in members:
            candidate_id = str(
                _json_object(member.get("source_details_json")).get("candidate_id") or ""
            )
            if candidate_id and candidate_id in self.keep_separate_endpoints:
                return True
        return False

    def _store(
        self,
        result: dict,
        measure: str,
        entity_id: str,
        detail: dict | None,
        reason: str | None = None,
        additional_field_contexts: dict[str, str] | None = None,
    ) -> None:
        if detail is None:
            result[measure]["withheld"][entity_id] = (
                reason or "missing_supported_identity_record"
            )
            return
        detail["flags"]["additional_field_review_status"] = (
            "accepted_by_owner"
            if measure in self.approved_measures
            else "pending_owner_acceptance"
        )
        reason = _finalize(detail, self.policy, measure, additional_field_contexts)
        if reason:
            result[measure]["withheld"][entity_id] = reason
        else:
            result[measure]["details"][entity_id] = detail

    def _mapped_material(
        self,
        subject_id: str,
        measure: str,
        source_keys: set[str] | None = None,
    ) -> dict:
        listings = self.mapped["mapped_listing_observations"].get(subject_id, [])
        locations = self.mapped["mapped_locations"].get(subject_id, [])
        categories = self.mapped["category_assertions"].get(subject_id, [])
        narratives = self.mapped["mapped_narrative_evidence"].get(subject_id, [])
        media_rows = self.mapped["mapped_media"].get(subject_id, [])
        source = "cultural_map"
        source_id = _canonical_source(self.policy, source)
        listing_children = []
        listing_reasons = []
        source_key_to_listing: dict[str, str] = {}
        reviewed_listing_label_context = False
        person_directory_evidence = False
        for row in sorted(listings, key=lambda item: str(item.get("listing_id", ""))):
            source_key = str(row.get("source_key", ""))
            raw_label = row.get("title_normalized") or row.get("title_raw")
            if measure == "K12":
                label_context = (
                    _reviewed_mapped_label_context(
                        self.policy, subject_id, source_keys, raw_label
                    )
                    if source_keys is not None
                    else None
                )
                label, label_availability, label_withholding_reason = _mapped_label(
                    raw_label, label_context
                )
                missing_label_reason = "missing_listing_label"
            else:
                label_context = None
                label = _clean_label(raw_label)
                label_availability = None
                label_withholding_reason = None
                missing_label_reason = "unsafe_or_missing_listing_label"
            if not label:
                listing_reasons.append(missing_label_reason)
                continue
            if measure != "K12":
                people = _json_object(row.get("people_summary_json"))
                informants = people.get("informants_raw")
                title_core = _person_identity_core(label)
                informant_cores = {
                    _person_identity_core(part)
                    for part in re.split(r"[,;/\n]+", str(informants or ""))
                    if _person_identity_core(part)
                }
                if _PERSON_LABEL.search(label) or title_core in informant_cores:
                    person_directory_evidence = True
                    listing_reasons.append(
                        "source_person_context_matches_listing_identity"
                    )
                    continue
            listing_id = str(row.get("listing_id", ""))
            if not source_key or not listing_id:
                listing_reasons.append("missing_required_listing_identity")
                continue
            reviewed_listing_label_context |= label_context is not None
            source_key_to_listing[source_key] = listing_id
            dates = (
                row.get("dates_json") if isinstance(row.get("dates_json"), dict) else {}
            )
            listing_child = {
                "listing_id": listing_id,
                "label": label,
                "source_id": source_id,
                "source_url": _public_url(
                    row.get("source_url"),
                    self.policy,
                    source,
                    measure=measure,
                )
                if _allowed(self.policy, measure, source, "source_link", "source_url")
                else None,
                "source_dates": {
                    str(key): clean
                    for key, value in sorted(dates.items())
                    if (clean := _date(value)) is not None
                },
            }
            if measure == "K12":
                listing_child.update(
                    {
                        "label_availability": label_availability,
                        "label_withholding_reason": label_withholding_reason,
                    }
                )
            listing_children.append(listing_child)
        description_children = []
        narrative_reasons = []
        for row in sorted(
            narratives, key=lambda item: str(item.get("evidence_id", ""))
        ):
            field = str(row.get("field_name", ""))
            if not _allowed(self.policy, measure, source, "structured_excerpt", field):
                narrative_reasons.append("narrative_field_not_allowlisted")
                continue
            listing_id = source_key_to_listing.get(str(row.get("source_key", "")))
            if not listing_id:
                narrative_reasons.append("detached_required_listing")
                continue
            entry = _description(field, row.get("text"), source_id, self.limit)
            if not entry:
                narrative_reasons.append("unsafe_or_missing_narrative_text")
                continue
            entry["listing_id"] = listing_id
            description_children.append(entry)
        location_children = [
            _location(row, source_id)
            for row in sorted(
                locations, key=lambda item: str(item.get("location_id", ""))
            )
        ]
        media = []
        media_reasons = []
        for row in sorted(
            media_rows,
            key=lambda item: (
                str(item.get("ordinal", "")),
                str(item.get("media_id", "")),
            ),
        ):
            if not _allowed(self.policy, measure, source, "media", "url_or_value"):
                media_reasons.append("media_field_not_allowlisted")
                continue
            item = _media(row, self.policy, source, measure=measure)
            if item:
                media.append(item)
            else:
                media_reasons.append("unsafe_or_unapproved_media_reference")
        required_listing_lost = (
            not listings
            or bool(listing_reasons)
            or "detached_required_listing" in narrative_reasons
        )
        return {
            "listings": listing_children,
            "descriptions": description_children,
            "locations": location_children,
            "media": media,
            "reviewed_listing_label_context": reviewed_listing_label_context,
            "province_codes": {
                str(row.get("province_code"))
                for row in locations
                if row.get("province_code")
            },
            "category_codes": {
                str(row.get("category_code"))
                for row in categories
                if row.get("category_code")
            },
            "child_dispositions": {
                "listings": _child_disposition(
                    len(listings), len(listing_children), listing_reasons
                ),
                "narratives": _child_disposition(
                    len(narratives),
                    len(description_children),
                    narrative_reasons,
                ),
                "locations": _child_disposition(
                    len(locations), len(location_children), []
                ),
                "media": _child_disposition(len(media_rows), len(media), media_reasons),
                "categories": _child_disposition(len(categories), len(categories), []),
            },
            "fatal_reason": (
                "mapped_person_directory_record"
                if person_directory_evidence
                else "missing_or_detached_required_mapped_listing"
                if required_listing_lost
                else None
            ),
        }

    def areas(self, result: dict) -> None:
        measure = "K01B"
        globals_ = {
            str(row.get("global_area_id")): row
            for row in _rows(self.tables, "domains/areas/global_cultural_areas")
        }
        crosswalk = _group(
            _rows(self.tables, "domains/areas/area_crosswalk"), "global_area_id"
        )
        atlocal_areas = {
            str(row.get("area_id")): row
            for row in _rows(self.tables, "sources/f2_cultural_market_civil/areas")
        }
        for entity_id in self.entity_ids[measure]:
            row = globals_.get(entity_id)
            label = _clean_label(row.get("display_name")) if row else None
            if not label:
                self._store(
                    result, measure, entity_id, None, "unsafe_or_missing_public_label"
                )
                continue
            members = crosswalk.get(entity_id, [])
            if not members:
                self._store(
                    result,
                    measure,
                    entity_id,
                    None,
                    "missing_supported_source_membership",
                )
                continue
            if _PERSON_LABEL.search(label) and any(
                member.get("source") == "cultural_map" for member in members
            ):
                self._store(
                    result,
                    measure,
                    entity_id,
                    None,
                    "unapproved_person_or_person_bearing_mapped_subject",
                )
                continue
            descriptions, listings, locations, media, categories = [], [], [], [], set()
            relationships, logical_sources, mapped_dispositions = [], set(), []
            mapped_fatal_reason = None
            for member in sorted(
                members, key=lambda item: str(item.get("source_member_id", ""))
            ):
                source = str(member.get("source", ""))
                logical_sources.add(source)
                relationships.append(
                    {
                        "kind": "source_membership",
                        "source_id": _canonical_source(self.policy, source),
                        "label": _clean_label(member.get("display_name")),
                        "identity_role": "area_source_member",
                    }
                )
                categories.update(
                    str(value)
                    for value in _json_list(member.get("primary_category_codes_json"))
                    if value
                )
                if source == "atlocal":
                    local = atlocal_areas.get(str(member.get("local_entity_id", "")))
                    if local and _allowed(
                        self.policy,
                        measure,
                        source,
                        "structured_excerpt",
                        "description",
                    ):
                        entry = _description(
                            "description",
                            local.get("description"),
                            _canonical_source(self.policy, source),
                            self.limit,
                        )
                        if entry:
                            descriptions.append(entry)
                    if local and _allowed(
                        self.policy, measure, source, "media", "images_json"
                    ):
                        for index, value in enumerate(
                            _json_list(local.get("images_json"))
                        ):
                            url = value.get("url") if isinstance(value, dict) else value
                            item = _media(
                                {
                                    "media_id": f"area-image-{index}",
                                    "media_kind": "image",
                                    "url_or_value": url,
                                },
                                self.policy,
                                source,
                                measure=measure,
                            )
                            if item:
                                media.append(item)
                elif source == "cultural_map":
                    material = self._mapped_material(
                        str(member.get("local_entity_id", "")), measure
                    )
                    mapped_dispositions.append(material["child_dispositions"])
                    if material["fatal_reason"]:
                        mapped_fatal_reason = material["fatal_reason"]
                        break
                    descriptions.extend(material["descriptions"])
                    listings.extend(material["listings"])
                    locations.extend(material["locations"])
                    media.extend(material["media"])
                    categories.update(material["category_codes"])
            if mapped_fatal_reason:
                self._store(
                    result,
                    measure,
                    entity_id,
                    None,
                    mapped_fatal_reason,
                )
                continue
            source_ids = [
                _canonical_source(self.policy, source) for source in logical_sources
            ]
            detail = _base_detail(
                entity_id,
                label,
                row.get("identity_status"),
                source_ids,
                [_system(self.policy, source) for source in logical_sources],
                province_codes=[item.get("province_code") for item in locations],
                category_codes=categories,
            )
            detail.update(
                {
                    "descriptions": descriptions,
                    "listings": listings,
                    "locations": locations,
                    "media": media,
                    "relationships": relationships,
                }
            )
            detail["flags"]["child_dispositions"] = _merge_child_dispositions(
                mapped_dispositions
            )
            self._store(result, measure, entity_id, detail)

    def activities(self, result: dict) -> None:
        measure = "K03"
        activities = {
            str(row.get("global_activity_id")): row
            for row in _rows(self.tables, "domains/activities/global_activities")
        }
        publications = _group(
            _rows(self.tables, "domains/activities/publications"), "global_activity_id"
        )
        dates = _group(
            _rows(self.tables, "domains/activities/activity_dates"),
            "global_activity_id",
        )
        venues = _group(
            _rows(self.tables, "domains/activities/activity_venues"),
            "global_activity_id",
        )
        sessions = _group(
            _rows(self.tables, "domains/activities/activity_sessions"),
            "global_activity_id",
        )
        sections = _group(
            _rows(self.tables, "domains/activities/activity_sections"),
            "global_activity_id",
        )
        narratives = _group(
            _rows(self.tables, "domains/activities/activity_narrative_evidence"),
            "global_activity_id",
        )
        media_rows = _group(
            _rows(self.tables, "domains/activities/activity_media"),
            "global_activity_id",
        )
        for entity_id in self.entity_ids[measure]:
            row = activities.get(entity_id)
            label = _clean_label(row.get("name")) if row else None
            if not label:
                self._store(
                    result, measure, entity_id, None, "unsafe_or_missing_public_label"
                )
                continue
            source = _source_key(row.get("source"))
            pub_children = []
            publication_title_candidates = 0
            publication_title_reasons = []
            publication_text_candidates = 0
            publication_text_reasons = []
            publication_url_candidates = 0
            publication_url_reasons = []
            for item in sorted(
                publications.get(entity_id, []),
                key=lambda value: str(value.get("source_publication_id", "")),
            ):
                item_source = _source_key(item.get("source") or source)
                raw_title = item.get("title")
                title = _clean_label(raw_title)
                if raw_title not in (None, ""):
                    publication_title_candidates += 1
                    if title is None:
                        publication_title_reasons.append(
                            "publication_title_admission_failed"
                        )
                text = None
                if item.get("text") not in (None, ""):
                    publication_text_candidates += 1
                    if not _allowed(
                        self.policy,
                        measure,
                        item_source,
                        "structured_excerpt",
                        "text",
                    ):
                        publication_text_reasons.append(
                            "publication_text_not_allowlisted"
                        )
                    else:
                        text = _description(
                            "publication",
                            item.get("text"),
                            _canonical_source(self.policy, item_source),
                            self.limit,
                        )
                        if text is None:
                            publication_text_reasons.append(
                                "publication_text_admission_failed"
                            )
                source_url = None
                if item.get("source_url") not in (None, ""):
                    publication_url_candidates += 1
                    if not _allowed(
                        self.policy,
                        measure,
                        item_source,
                        "source_link",
                        "source_url",
                    ):
                        publication_url_reasons.append(
                            "publication_url_not_allowlisted"
                        )
                    else:
                        source_url = _public_url(
                            item.get("source_url"),
                            self.policy,
                            item_source,
                            measure=measure,
                        )
                        if source_url is None:
                            publication_url_reasons.append(
                                "publication_url_admission_failed"
                            )
                pub_children.append(
                    {
                        "publication_id": str(item.get("source_publication_id", "")),
                        "label": title or label,
                        "published_at": _date(item.get("published_at")),
                        "publication_role": _clean_label(item.get("publication_role")),
                        "source_url": source_url,
                        "description": text,
                        "source_id": _canonical_source(self.policy, item_source),
                    }
                )
            date_children = []
            date_value_candidates = 0
            date_value_reasons = []
            for item in sorted(
                dates.get(entity_id, []),
                key=lambda value: str(value.get("date_assertion_id", "")),
            ):
                start_date = _date(item.get("parsed_start_date"))
                end_date = _date(item.get("parsed_end_date"))
                for raw_value, public_value in (
                    (item.get("parsed_start_date"), start_date),
                    (item.get("parsed_end_date"), end_date),
                ):
                    if raw_value not in (None, ""):
                        date_value_candidates += 1
                        if public_value is None:
                            date_value_reasons.append("date_value_admission_failed")
                date_children.append(
                    {
                        "date_id": str(item.get("date_assertion_id", "")),
                        "role": _clean_label(item.get("date_role")),
                        "start_date": start_date,
                        "end_date": end_date,
                        "parse_status": _clean_label(item.get("parse_status")),
                        "has_conflict": str(item.get("date_conflict")).lower()
                        == "true",
                        "source_id": _canonical_source(
                            self.policy, item.get("source") or source
                        ),
                    }
                )
            venue_children = []
            venue_label_candidates = 0
            venue_label_reasons = []
            for item in sorted(
                venues.get(entity_id, []),
                key=lambda value: str(value.get("venue_assertion_id", "")),
            ):
                location = _location(
                    item,
                    _canonical_source(self.policy, item.get("source") or source),
                    label_field="location_name_raw",
                )
                if item.get("location_name_raw") not in (None, ""):
                    venue_label_candidates += 1
                    if location.get("label") is None:
                        venue_label_reasons.append("venue_label_admission_failed")
                venue_children.append(location)
            session_children = []
            session_label_candidates = 0
            session_label_reasons = []
            for item in sorted(
                sessions.get(entity_id, []),
                key=lambda value: str(value.get("session_id", "")),
            ):
                session_label = _clean_label(item.get("session_label"))
                if item.get("session_label") not in (None, ""):
                    session_label_candidates += 1
                    if session_label is None:
                        session_label_reasons.append("session_label_admission_failed")
                session_children.append(
                    {
                        "session_id": str(item.get("session_id", "")),
                        "label": session_label,
                        "start_date": _date(item.get("start_date")),
                        "end_date": _date(item.get("end_date")),
                        "status": _clean_label(item.get("status")),
                        "source_id": _canonical_source(
                            self.policy, item.get("source") or source
                        ),
                    }
                )
            section_children = []
            section_reasons = []
            section_attribution_candidates = 0
            section_attribution_emitted = 0
            section_attribution_reasons = []
            for item in sorted(
                sections.get(entity_id, []),
                key=lambda value: str(value.get("section_id", "")),
            ):
                item_source = _source_key(item.get("source") or source)
                raw_attribution = item.get("attribution")
                has_attribution = raw_attribution not in (None, "")
                if has_attribution:
                    section_attribution_candidates += 1
                if not _allowed(
                    self.policy,
                    measure,
                    item_source,
                    "structured_excerpt",
                    "section_text",
                ):
                    section_reasons.append("section_text_not_allowlisted")
                    if has_attribution:
                        section_attribution_reasons.append("parent_section_withheld")
                    continue
                description = _description(
                    "section",
                    item.get("text"),
                    _canonical_source(self.policy, item_source),
                    self.limit,
                )
                if not description:
                    section_reasons.append("section_text_admission_failed")
                    if has_attribution:
                        section_attribution_reasons.append("parent_section_withheld")
                    continue
                attribution = None
                if has_attribution:
                    if not _allowed(
                        self.policy,
                        measure,
                        item_source,
                        "attribution",
                        "attribution",
                    ):
                        section_attribution_reasons.append(
                            "section_attribution_not_allowlisted"
                        )
                    else:
                        attribution = _clean_label(raw_attribution)
                        if attribution is None:
                            section_attribution_reasons.append(
                                "section_attribution_admission_failed"
                            )
                        else:
                            section_attribution_emitted += 1
                section_children.append(
                    {
                        "section_id": str(item.get("section_id", "")),
                        "description": description,
                        "attribution": attribution,
                    }
                )
            description_children = []
            narrative_reasons = []
            for item in sorted(
                narratives.get(entity_id, []),
                key=lambda value: str(value.get("evidence_id", "")),
            ):
                item_source = _source_key(item.get("source") or source)
                field = str(item.get("field_name", ""))
                if not _allowed(
                    self.policy,
                    measure,
                    item_source,
                    "structured_excerpt",
                    field,
                ):
                    narrative_reasons.append("narrative_field_not_allowlisted")
                    continue
                entry = _description(
                    field,
                    item.get("text"),
                    _canonical_source(self.policy, item_source),
                    self.limit,
                )
                if entry:
                    description_children.append(entry)
                else:
                    narrative_reasons.append("narrative_text_admission_failed")
            media = []
            media_reasons = []
            for item in sorted(
                media_rows.get(entity_id, []),
                key=lambda value: str(value.get("media_id", "")),
            ):
                item_source = _source_key(item.get("source") or source)
                if not _allowed(
                    self.policy, measure, item_source, "media", "url_or_value"
                ):
                    media_reasons.append("media_field_not_allowlisted")
                    continue
                value = _media(item, self.policy, item_source, measure=measure)
                if value:
                    media.append(value)
                else:
                    media_reasons.append("media_reference_admission_failed")
            logical_sources = {source} | {
                str(item.get("source"))
                for item in publications.get(entity_id, [])
                if item.get("source")
            }
            provinces = [item.get("province_code") for item in venue_children]
            detail = _base_detail(
                entity_id,
                label,
                row.get("identity_status"),
                [_canonical_source(self.policy, item) for item in logical_sources],
                [_system(self.policy, item) for item in logical_sources],
                province_codes=provinces,
            )
            detail.update(
                {
                    "descriptions": description_children,
                    "listings": pub_children,
                    "locations": venue_children,
                    "media": media,
                    "children": {
                        "dates": date_children,
                        "sessions": session_children,
                        "sections": section_children,
                    },
                }
            )
            detail["flags"].update(
                {
                    "date_conflict": any(
                        item["has_conflict"] for item in date_children
                    ),
                    "source_reported_occurrence_not_completion": True,
                    "child_dispositions": {
                        "publications": _child_disposition(
                            len(publications.get(entity_id, [])),
                            len(pub_children),
                            [],
                        ),
                        "publication_titles": _child_disposition(
                            publication_title_candidates,
                            publication_title_candidates
                            - len(publication_title_reasons),
                            publication_title_reasons,
                        ),
                        "publication_texts": _child_disposition(
                            publication_text_candidates,
                            publication_text_candidates - len(publication_text_reasons),
                            publication_text_reasons,
                        ),
                        "publication_link_checks": _child_disposition(
                            publication_url_candidates,
                            publication_url_candidates - len(publication_url_reasons),
                            publication_url_reasons,
                        ),
                        "dates": _child_disposition(
                            len(dates.get(entity_id, [])),
                            len(date_children),
                            [],
                        ),
                        "date_values": _child_disposition(
                            date_value_candidates,
                            date_value_candidates - len(date_value_reasons),
                            date_value_reasons,
                        ),
                        "venues": _child_disposition(
                            len(venues.get(entity_id, [])),
                            len(venue_children),
                            [],
                        ),
                        "venue_labels": _child_disposition(
                            venue_label_candidates,
                            venue_label_candidates - len(venue_label_reasons),
                            venue_label_reasons,
                        ),
                        "sessions": _child_disposition(
                            len(sessions.get(entity_id, [])),
                            len(session_children),
                            [],
                        ),
                        "session_labels": _child_disposition(
                            session_label_candidates,
                            session_label_candidates - len(session_label_reasons),
                            session_label_reasons,
                        ),
                        "sections": _child_disposition(
                            len(sections.get(entity_id, [])),
                            len(section_children),
                            section_reasons,
                        ),
                        "section_attributions": _child_disposition(
                            section_attribution_candidates,
                            section_attribution_emitted,
                            section_attribution_reasons,
                        ),
                        "narratives": _child_disposition(
                            len(narratives.get(entity_id, [])),
                            len(description_children),
                            narrative_reasons,
                        ),
                        "media": _child_disposition(
                            len(media_rows.get(entity_id, [])),
                            len(media),
                            media_reasons,
                        ),
                    },
                }
            )
            self._store(result, measure, entity_id, detail)

    def innovations(self, result: dict) -> None:
        globals_ = {
            str(row.get("global_innovation_id")): row
            for row in _rows(self.tables, "domains/innovations/global_innovations")
        }
        crosswalk = _group(
            _rows(self.tables, "domains/innovations/innovation_crosswalk"),
            "global_innovation_id",
        )
        records = _group(
            _rows(self.tables, "domains/innovations/source_records"),
            "global_innovation_id",
        )
        readiness = _group(
            _rows(self.tables, "domains/innovations/readiness_evidence"),
            "global_innovation_id",
        )
        use_locations = _group(
            _rows(self.tables, "domains/innovations/innovation_use_locations"),
            "global_innovation_id",
        )
        local_tables = {
            "icommunity": (
                "sources/f2_icommunity/innovation_details",
                "description",
                None,
            ),
            "pmua_apptech": (
                "sources/f2_target_household/description_sections",
                "text_readable",
                "label_raw",
            ),
            "rinmp": (
                "sources/f2_apptech_mtr/description_sections",
                "text_readable",
                "label_raw",
            ),
            "apptech_mru": (
                "sources/f2_apptech_mru/description_sections",
                "text_readable",
                "label_raw",
            ),
        }
        profile_tables = {
            "pmua_apptech": (
                "sources/f2_target_household/innovation_details",
                "detail_url",
            ),
            "rinmp": ("sources/f2_apptech_mtr/innovation_profiles", "detail_url"),
            "apptech_mru": (
                "sources/f2_apptech_mru/innovation_observations",
                "detail_url",
            ),
        }
        local_descriptions = {
            source: _group(_rows(self.tables, table), "innovation_id")
            for source, (table, _, _) in local_tables.items()
        }
        local_profiles = {
            source: _group(_rows(self.tables, table), "innovation_id")
            for source, (table, _) in profile_tables.items()
        }
        innovation_ids = sorted(
            set(self.entity_ids["K04"]) | set(self.entity_ids["C04_LISTED"])
        )
        built: dict[str, dict | None] = {}
        reviewed_title_measures: dict[str, set[str]] = {}
        withheld: dict[str, str] = {}
        for entity_id in innovation_ids:
            row = globals_.get(entity_id)
            raw_label = row.get("display_name") if row else None
            label = _clean_finalized_label(raw_label)
            source_keys = {
                str(item.get("source_key"))
                for item in records.get(entity_id, [])
                if item.get("source_key")
            }
            reviewed_measures = {
                measure
                for measure in ("K04", "C04_LISTED")
                if entity_id in self.entity_ids[measure]
                and _reviewed_public_title(
                    self.policy,
                    measure,
                    entity_id,
                    source_keys,
                    raw_label,
                )
                is not None
            }
            if not label and reviewed_measures:
                label = _reviewed_public_title(
                    self.policy,
                    sorted(reviewed_measures)[0],
                    entity_id,
                    source_keys,
                    raw_label,
                )
            if not label:
                built[entity_id] = None
                withheld[entity_id] = "unsafe_or_missing_public_label"
                continue
            members = sorted(
                crosswalk.get(entity_id, []),
                key=lambda value: (
                    str(value.get("source", "")),
                    str(value.get("local_innovation_id", "")),
                ),
            )
            if not members:
                built[entity_id] = None
                withheld[entity_id] = "missing_supported_source_membership"
                continue
            logical_sources = {
                str(item.get("source")) for item in members if item.get("source")
            }
            reviewed_title_sources = {
                str(item.get("source"))
                for item in records.get(entity_id, [])
                if reviewed_measures and item.get("source_key") in source_keys
            }
            source_identities = []
            source_identity_label_candidates = 0
            source_identity_label_reasons = []
            source_identity_status_candidates = 0
            source_identity_status_reasons = []
            for item in members:
                local_label = _clean_finalized_label(item.get("local_display_name"))
                if (
                    local_label is None
                    and item.get("local_display_name") == raw_label
                    and str(item.get("source")) in reviewed_title_sources
                ):
                    local_label = label
                if item.get("local_display_name") not in (None, ""):
                    source_identity_label_candidates += 1
                    if local_label is None:
                        source_identity_label_reasons.append(
                            "source_identity_label_admission_failed"
                        )
                local_status = _clean_label(item.get("local_identity_status"))
                if item.get("local_identity_status") not in (None, ""):
                    source_identity_status_candidates += 1
                    if local_status is None:
                        source_identity_status_reasons.append(
                            "source_identity_status_admission_failed"
                        )
                source_identities.append(
                    {
                        "source_id": _canonical_source(
                            self.policy, str(item.get("source"))
                        ),
                        "label": local_label or label,
                        "identity_status": local_status or "unknown",
                    }
                )
            description_children, profile_children = [], []
            description_candidates = 0
            description_reasons = []
            profile_url_candidates = 0
            profile_url_reasons = []
            profile_link_emitted = 0
            profile_source_citation_candidates = 0
            profile_source_citation_emitted = 0
            profile_source_citation_reasons = []
            attribution_dispositions = []
            work_attributions = []
            organizations = []
            for member in members:
                source = str(member.get("source", ""))
                local_id = str(member.get("local_innovation_id", ""))
                source_id = _canonical_source(self.policy, source)
                _, text_field, kind_field = local_tables[source]
                for item in local_descriptions[source].get(local_id, []):
                    description_candidates += 1
                    field = (
                        str(item.get(kind_field) or "description")
                        if kind_field
                        else "description"
                    )
                    if not _allowed(
                        self.policy,
                        "C04_LISTED",
                        source,
                        "structured_excerpt",
                        text_field,
                    ):
                        description_reasons.append("description_field_not_allowlisted")
                        continue
                    entry = _description(
                        field, item.get(text_field), source_id, self.limit
                    )
                    if entry:
                        description_children.append(entry)
                    else:
                        description_reasons.append("description_text_admission_failed")
                for item in local_profiles.get(source, {}).get(local_id, []):
                    url_field = profile_tables[source][1]
                    if item.get(url_field) in (None, ""):
                        continue
                    profile_url_candidates += 1
                    if not _allowed(
                        self.policy,
                        "C04_LISTED",
                        source,
                        "source_link",
                        url_field,
                    ):
                        profile_url_reasons.append("profile_url_not_allowlisted")
                        continue
                    url = _public_url(
                        item.get(url_field),
                        self.policy,
                        source,
                        measure="C04_LISTED",
                    )
                    if not url:
                        profile_url_reasons.append("profile_url_admission_failed")
                        continue
                    if source == "rinmp":
                        link_reason = (
                            "record_link_withheld_unregistered_publication_route"
                        )
                        profile_url_reasons.append(link_reason)
                        profile_source_citation_candidates += 1
                        citation = _public_url(
                            _source_spec(self.policy, source).get("public_url"),
                            self.policy,
                            source,
                            measure="C04_LISTED",
                        )
                        if not citation:
                            profile_source_citation_reasons.append(
                                "pinned_source_citation_admission_failed"
                            )
                            continue
                        profile_source_citation_emitted += 1
                        profile_children.append(
                            {
                                "label": label,
                                "listing_id": stable_id(
                                    "public_innovation_profile",
                                    source,
                                    local_id,
                                    item.get(url_field),
                                ),
                                "source_id": source_id,
                                "source_url": citation,
                                "link_scope": "source",
                                "record_link_availability": "withheld",
                                "record_link_withholding_reason": link_reason,
                            }
                        )
                    else:
                        profile_link_emitted += 1
                        profile_children.append(
                            {
                                "label": label,
                                "source_id": source_id,
                                "source_url": url,
                                "link_scope": "record",
                            }
                        )
                attribution_dispositions.append(
                    self._innovation_attribution(
                        source,
                        local_id,
                        source_id,
                        work_attributions,
                        organizations,
                    )
                )
            readiness_children = []
            readiness_label_candidates = 0
            readiness_label_reasons = []
            readiness_numeric_candidates = 0
            readiness_numeric_reasons = []
            for item in sorted(
                readiness.get(entity_id, []),
                key=lambda value: str(value.get("assessment_id", "")),
            ):
                clean_fields = {}
                for field in (
                    "scale",
                    "label_raw",
                    "basis",
                    "assessment_context",
                ):
                    raw_value = item.get(field)
                    clean_value = _clean_label(raw_value)
                    clean_fields[field] = clean_value
                    if raw_value not in (None, ""):
                        readiness_label_candidates += 1
                        if clean_value is None:
                            readiness_label_reasons.append(
                                "readiness_label_admission_failed"
                            )
                raw_numeric_level = item.get("numeric_level")
                numeric_level = _clean_label(raw_numeric_level)
                if raw_numeric_level not in (None, ""):
                    readiness_numeric_candidates += 1
                    if numeric_level is None:
                        readiness_numeric_reasons.append(
                            "readiness_numeric_level_admission_failed"
                        )
                readiness_children.append(
                    {
                        "assessment_id": str(item.get("assessment_id", "")),
                        "source_id": _canonical_source(
                            self.policy, str(item.get("source"))
                        ),
                        "scale": clean_fields["scale"],
                        "numeric_level": numeric_level,
                        "label": clean_fields["label_raw"],
                        "qualifies": (str(item.get("qualifies_k04")).lower() == "true"),
                        "basis": clean_fields["basis"],
                        "assessment_context": clean_fields["assessment_context"],
                    }
                )
            location_children = [
                _location(item, _canonical_source(self.policy, str(item.get("source"))))
                for item in sorted(
                    use_locations.get(entity_id, []),
                    key=lambda value: str(value.get("location_id", "")),
                )
            ]
            location_label_values = [
                item.get(field)
                for item in use_locations.get(entity_id, [])
                for field in (
                    "province_normalized",
                    "district_normalized",
                    "subdistrict_normalized",
                )
                if item.get(field) not in (None, "")
            ]
            location_label_reasons = [
                "location_label_admission_failed"
                for value in location_label_values
                if _clean_label(value) is None
            ]
            location_metadata_values = [
                item.get(field)
                for item in use_locations.get(entity_id, [])
                for field in ("location_role", "resolution_status")
                if item.get(field) not in (None, "")
            ]
            location_metadata_reasons = [
                "location_metadata_admission_failed"
                for value in location_metadata_values
                if _clean_label(value) is None
            ]
            sorted_records = sorted(
                records.get(entity_id, []),
                key=lambda value: (
                    str(value.get("source", "")),
                    str(value.get("observation_id", "")),
                    str(value.get("row_locator", "")),
                ),
            )
            record_children = []
            record_label_values = []
            record_label_reasons = []
            for item in sorted_records:
                raw_record_label = item.get("title_raw")
                record_label = _clean_finalized_label(raw_record_label)
                if (
                    record_label is None
                    and reviewed_measures
                    and raw_record_label == raw_label
                    and item.get("source_key") in source_keys
                ):
                    record_label = label
                if raw_record_label not in (None, ""):
                    record_label_values.append(raw_record_label)
                    if record_label is None:
                        record_label_reasons.append(
                            "source_record_label_admission_failed"
                        )
                record_children.append(
                    {
                        "record_id": stable_id(
                            "public_source_record",
                            item.get("source"),
                            item.get("observation_id"),
                            item.get("row_locator"),
                        ),
                        "source_id": _canonical_source(
                            self.policy, str(item.get("source"))
                        ),
                        "label": record_label or label,
                    }
                )
            source_ids = [
                _canonical_source(self.policy, source) for source in logical_sources
            ]
            detail = _base_detail(
                entity_id,
                label,
                row.get("identity_status"),
                source_ids,
                [_system(self.policy, source) for source in logical_sources],
                province_codes=[
                    item.get("province_code") for item in location_children
                ],
            )
            detail.update(
                {
                    "descriptions": description_children,
                    "listings": profile_children,
                    "locations": location_children,
                    "relationships": source_identities,
                    "children": {
                        "source_records": record_children,
                        "readiness": readiness_children,
                        "work_attributions": work_attributions,
                        "organizations": organizations,
                    },
                }
            )
            detail["flags"].update(
                {
                    "readiness_conflict": len(
                        {
                            (item["scale"], item["numeric_level"], item["qualifies"])
                            for item in readiness_children
                        }
                    )
                    > 1,
                    "readiness_is_source_assertion_not_current_verification": True,
                    "child_dispositions": {
                        "source_identities": _child_disposition(
                            len(members), len(source_identities), []
                        ),
                        "source_identity_labels": _child_disposition(
                            source_identity_label_candidates,
                            source_identity_label_candidates
                            - len(source_identity_label_reasons),
                            source_identity_label_reasons,
                        ),
                        "source_identity_statuses": _child_disposition(
                            source_identity_status_candidates,
                            source_identity_status_candidates
                            - len(source_identity_status_reasons),
                            source_identity_status_reasons,
                        ),
                        "descriptions": _child_disposition(
                            description_candidates,
                            len(description_children),
                            description_reasons,
                        ),
                        "profile_link_checks": _child_disposition(
                            profile_url_candidates,
                            profile_link_emitted,
                            profile_url_reasons,
                        ),
                        "profile_source_citations": _child_disposition(
                            profile_source_citation_candidates,
                            profile_source_citation_emitted,
                            profile_source_citation_reasons,
                        ),
                        "readiness": _child_disposition(
                            len(readiness.get(entity_id, [])),
                            len(readiness_children),
                            [],
                        ),
                        "readiness_labels": _child_disposition(
                            readiness_label_candidates,
                            readiness_label_candidates - len(readiness_label_reasons),
                            readiness_label_reasons,
                        ),
                        "readiness_numeric_levels": _child_disposition(
                            readiness_numeric_candidates,
                            readiness_numeric_candidates
                            - len(readiness_numeric_reasons),
                            readiness_numeric_reasons,
                        ),
                        "locations": _child_disposition(
                            len(use_locations.get(entity_id, [])),
                            len(location_children),
                            [],
                        ),
                        "location_labels": _child_disposition(
                            len(location_label_values),
                            len(location_label_values) - len(location_label_reasons),
                            location_label_reasons,
                        ),
                        "source_records": _child_disposition(
                            len(sorted_records), len(record_children), []
                        ),
                        "source_record_labels": _child_disposition(
                            len(record_label_values),
                            len(record_label_values) - len(record_label_reasons),
                            record_label_reasons,
                        ),
                        "location_metadata": _child_disposition(
                            len(location_metadata_values),
                            len(location_metadata_values)
                            - len(location_metadata_reasons),
                            location_metadata_reasons,
                        ),
                        **_merge_child_dispositions(attribution_dispositions),
                    },
                }
            )
            built[entity_id] = detail
            reviewed_title_measures[entity_id] = reviewed_measures
        for measure in ("K04", "C04_LISTED"):
            for entity_id in self.entity_ids[measure]:
                detail = built.get(entity_id)
                title_contexts = None
                if detail and measure in reviewed_title_measures.get(entity_id, set()):
                    title_contexts = {
                        "/label": "public_contact",
                        "/relationships/*/label": "public_contact",
                        "/children/source_records/*/label": "public_contact",
                        "/listings/*/label": "public_contact",
                    }
                self._store(
                    result,
                    measure,
                    entity_id,
                    detail,
                    withheld.get(entity_id),
                    title_contexts,
                )

    def _innovation_attribution(
        self,
        source: str,
        local_id: str,
        source_id: str,
        people: list[dict],
        organizations: list[dict],
    ) -> dict:
        candidates: list[tuple[Any, str]] = []
        orgs: list[tuple[Any, str]] = []
        if source == "icommunity":
            observation_ids = {
                str(row.get("observation_id"))
                for row in _rows(
                    self.tables, "sources/f2_icommunity/innovation_details"
                )
                if str(row.get("innovation_id")) == local_id
            }
            for row in _rows(
                self.tables, "sources/f2_icommunity/researcher_assertions"
            ):
                if str(row.get("observation_id")) in observation_ids and not row.get(
                    "subject_kind"
                ):
                    candidates.append(
                        (row.get("full_name"), str(row.get("role") or "researcher"))
                    )
            for row in _rows(
                self.tables, "sources/f2_icommunity/institution_assertions"
            ):
                if str(row.get("observation_id")) in observation_ids:
                    orgs.append((row.get("name"), "institution"))
        elif source == "pmua_apptech":
            for row in _rows(
                self.tables, "sources/f2_target_household/innovation_details"
            ):
                if str(row.get("innovation_id")) == local_id:
                    candidates.append((row.get("researcher_name_raw"), "researcher"))
                    orgs.append((row.get("university_name_raw"), "university"))
        elif source == "rinmp":
            for row in _rows(self.tables, "sources/f2_apptech_mtr/innovation_profiles"):
                if str(row.get("innovation_id")) == local_id:
                    candidates.append(
                        (row.get("owner_display_name_raw"), "source_reported_owner")
                    )
                    orgs.append((row.get("institute_name_raw"), "institute"))
        elif source == "apptech_mru":
            for row in _rows(self.tables, "sources/f2_apptech_mru/role_assertions"):
                if (
                    str(row.get("innovation_id")) != local_id
                    or row.get("record_type") != "innovation"
                    or str(row.get("placeholder")).lower() == "true"
                    or str(row.get("team_unspecified")).lower() == "true"
                ):
                    continue
                if row.get("subject_type") == "person":
                    candidates.append(
                        (
                            row.get("subject_name") or row.get("name_raw"),
                            str(row.get("role") or "work_attribution"),
                        )
                    )
                elif row.get("subject_type") == "organisation":
                    orgs.append(
                        (
                            row.get("subject_name") or row.get("name_raw"),
                            str(row.get("role") or "organization"),
                        )
                    )
        people_candidates = [
            (value, role) for value, role in candidates if value not in (None, "")
        ]
        organization_candidates = [
            (value, role) for value, role in orgs if value not in (None, "")
        ]
        people_reasons = []
        organization_reasons = []
        role_reasons = []
        allowed = _allowed(
            self.policy,
            "C04_LISTED",
            source,
            "attribution",
            "work_attribution",
        )
        for value, role in people_candidates:
            clean_role = _clean_label(role)
            if not allowed:
                people_reasons.append("work_attribution_not_allowlisted")
                role_reasons.append("parent_attribution_withheld")
                continue
            label = _clean_label(value)
            if not label:
                people_reasons.append("work_attribution_admission_failed")
                role_reasons.append("parent_attribution_withheld")
                continue
            if clean_role is None:
                role_reasons.append("attribution_role_admission_failed")
            people.append(
                {
                    "attribution": label,
                    "role": clean_role,
                    "source_id": source_id,
                }
            )
        for value, role in organization_candidates:
            clean_role = _clean_label(role)
            if not allowed:
                organization_reasons.append("organization_not_allowlisted")
                role_reasons.append("parent_attribution_withheld")
                continue
            label = _clean_label(value)
            if not label:
                organization_reasons.append("organization_admission_failed")
                role_reasons.append("parent_attribution_withheld")
                continue
            if clean_role is None:
                role_reasons.append("attribution_role_admission_failed")
            organizations.append(
                {
                    "organization": label,
                    "role": clean_role,
                    "source_id": source_id,
                }
            )
        return {
            "work_attributions": _child_disposition(
                len(people_candidates),
                len(people_candidates) - len(people_reasons),
                people_reasons,
            ),
            "organizations": _child_disposition(
                len(organization_candidates),
                len(organization_candidates) - len(organization_reasons),
                organization_reasons,
            ),
            "attribution_roles": _child_disposition(
                len(people_candidates) + len(organization_candidates),
                len(people_candidates)
                + len(organization_candidates)
                - len(role_reasons),
                role_reasons,
            ),
        }

    def operators(self, result: dict) -> None:
        measure = "K05"
        globals_ = {
            str(row.get("global_operator_id")): row
            for row in _rows(self.tables, "domains/commerce/global_operators")
        }
        crosswalk = _group(
            _rows(self.tables, "domains/commerce/operator_crosswalk"),
            "global_operator_id",
        )
        locations = _group(
            _rows(self.tables, "domains/commerce/locations"), "global_operator_id"
        )
        edges = _group(
            _rows(self.tables, "domains/commerce/operator_offering_edges"),
            "global_operator_id",
        )
        reviewed = _group(
            _rows(self.tables, "domains/commerce/reviewed_relationships"),
            "subject_global_id",
        )
        evidence = _group(
            _rows(self.tables, "domains/commerce/reviewed_evidence"),
            "global_operator_id",
        )
        offering_rows = {
            str(row.get("global_offering_id")): row
            for row in _rows(self.tables, "domains/commerce/global_offerings")
        }
        offering_labels = {
            entity_id: _clean_label(row.get("display_name"))
            for entity_id, row in offering_rows.items()
        }
        offering_sources = _group(
            _rows(self.tables, "domains/commerce/offering_crosswalk"),
            "global_offering_id",
        )
        person_links = _group(
            _rows(self.tables, "domains/commerce/person_operator_links"),
            "global_operator_id",
        )
        for entity_id in self.entity_ids[measure]:
            row = globals_.get(entity_id)
            label = _clean_finalized_label(row.get("display_name")) if row else None
            if not label:
                self._store(
                    result, measure, entity_id, None, "unsafe_or_missing_public_label"
                )
                continue
            members = crosswalk.get(entity_id, [])
            if not members:
                self._store(
                    result,
                    measure,
                    entity_id,
                    None,
                    "missing_supported_source_membership",
                )
                continue
            logical_sources = {
                str(item.get("source")) for item in members if item.get("source")
            }
            location_children = []
            location_reasons = []
            location_label_candidates = 0
            location_label_reasons = []
            location_metadata_candidates = 0
            location_metadata_reasons = []
            for item in sorted(
                locations.get(entity_id, []),
                key=lambda value: str(value.get("source_location_id", "")),
            ):
                source = str(item.get("source", ""))
                if item.get("global_operator_id") != entity_id or not _allowed(
                    self.policy, measure, source, "location", "operator_location"
                ):
                    location_reasons.append("detached_or_unapproved_operator_location")
                    continue
                location = _location(item, _canonical_source(self.policy, source))
                for field in (
                    "province_normalized",
                    "district_normalized",
                    "subdistrict_normalized",
                ):
                    if item.get(field) not in (None, ""):
                        location_label_candidates += 1
                        output_field = field.removesuffix("_normalized")
                        if location.get(output_field) is None:
                            location_label_reasons.append(
                                "location_label_admission_failed"
                            )
                for field in ("location_role", "status"):
                    if item.get(field) not in (None, ""):
                        location_metadata_candidates += 1
                        if (
                            location.get("role" if field == "location_role" else field)
                            is None
                        ):
                            location_metadata_reasons.append(
                                "location_metadata_admission_failed"
                            )
                location_children.append(location)
            relationships = []
            relationship_reasons = []
            relationship_label_candidates = 0
            relationship_label_reasons = []
            relationship_kind_candidates = 0
            relationship_kind_reasons = []
            for item in sorted(
                edges.get(entity_id, []),
                key=lambda value: str(
                    value.get("source_operator_offering_edge_id", "")
                ),
            ):
                source = str(item.get("source", ""))
                if not _allowed(
                    self.policy, measure, source, "relationships", "operator_offering"
                ):
                    relationship_reasons.append(
                        "operator_offering_relationship_not_allowlisted"
                    )
                    continue
                offering_id = str(item.get("global_offering_id") or "")
                relationship_kind = _clean_label(item.get("relationship"))
                if item.get("relationship") not in (None, ""):
                    relationship_kind_candidates += 1
                    if relationship_kind is None:
                        relationship_kind_reasons.append(
                            "relationship_kind_admission_failed"
                        )
                if offering_id:
                    relationship_label_candidates += 1
                    if offering_labels.get(offering_id) is None:
                        relationship_label_reasons.append(
                            "relationship_target_missing_or_admission_failed"
                        )
                relationships.append(
                    {
                        "kind": relationship_kind or "operator_offering",
                        "entity_id": offering_id,
                        "label": offering_labels.get(offering_id),
                        "source_id": _canonical_source(self.policy, source),
                    }
                )
            for item in sorted(
                reviewed.get(entity_id, []),
                key=lambda value: str(value.get("relationship_id", "")),
            ):
                offering_id = str(item.get("object_global_id") or "")
                relationship_kind = _clean_label(item.get("relationship"))
                if item.get("relationship") not in (None, ""):
                    relationship_kind_candidates += 1
                    if relationship_kind is None:
                        relationship_kind_reasons.append(
                            "relationship_kind_admission_failed"
                        )
                if offering_id:
                    relationship_label_candidates += 1
                    if offering_labels.get(offering_id) is None:
                        relationship_label_reasons.append(
                            "relationship_target_missing_or_admission_failed"
                        )
                reviewed_sources = logical_sources | {
                    str(member.get("source"))
                    for member in offering_sources.get(offering_id, [])
                    if member.get("source")
                }
                relationships.append(
                    {
                        "kind": relationship_kind or "operator_offering",
                        "entity_id": offering_id,
                        "label": offering_labels.get(offering_id),
                        "source_ids": sorted(
                            {
                                _canonical_source(self.policy, source)
                                for source in reviewed_sources
                            }
                        ),
                    }
                )
            descriptions = []
            description_reasons = []
            for item in sorted(
                evidence.get(entity_id, []),
                key=lambda value: str(value.get("evidence_id", "")),
            ):
                source = str(item.get("source", ""))
                if not _allowed(
                    self.policy,
                    measure,
                    source,
                    "structured_excerpt",
                    "reviewed_evidence",
                ):
                    description_reasons.append("reviewed_evidence_not_allowlisted")
                    continue
                entry = _description(
                    item.get("relationship"),
                    item.get("evidence_text"),
                    _canonical_source(self.policy, source),
                    self.limit,
                )
                if not entry:
                    description_reasons.append("reviewed_evidence_admission_failed")
                elif _privacy_problems(
                    entry,
                    artifact_path="staged-detail/K05/descriptions[]",
                    restricted_source_ids=set(),
                    profile="aggregate_public",
                    field_contexts={},
                ):
                    description_reasons.append(
                        "reviewed_evidence_field_privacy_check_failed"
                    )
                else:
                    descriptions.append(entry)
            source_memberships = []
            membership_label_candidates = 0
            membership_label_reasons = []
            membership_status_candidates = 0
            membership_status_reasons = []
            for item in sorted(
                members,
                key=lambda value: str(value.get("source_operator_id", "")),
            ):
                member_label = _clean_finalized_label(item.get("display_name"))
                if item.get("display_name") not in (None, ""):
                    membership_label_candidates += 1
                    if member_label is None:
                        membership_label_reasons.append(
                            "source_membership_label_admission_failed"
                        )
                member_status = _clean_label(item.get("identity_status"))
                if item.get("identity_status") not in (None, ""):
                    membership_status_candidates += 1
                    if member_status is None:
                        membership_status_reasons.append(
                            "source_membership_status_admission_failed"
                        )
                source_memberships.append(
                    {
                        "source_id": _canonical_source(
                            self.policy, str(item.get("source"))
                        ),
                        "label": member_label or label,
                        "identity_status": member_status,
                    }
                )
            source_ids = [
                _canonical_source(self.policy, source) for source in logical_sources
            ]
            detail = _base_detail(
                entity_id,
                label,
                row.get("identity_status"),
                source_ids,
                [_system(self.policy, source) for source in logical_sources],
                province_codes=[
                    item.get("province_code") for item in location_children
                ],
                kept_separate=self._has_keep_separate_decision(members),
            )
            detail.update(
                {
                    "descriptions": descriptions,
                    "locations": location_children,
                    "relationships": relationships,
                    "children": {"source_memberships": source_memberships},
                }
            )
            detail["flags"].update(
                {
                    "person_relationships_withheld": bool(person_links.get(entity_id)),
                    "person_relationship_withholding_reason": (
                        "unapproved_person_directory_relationship"
                        if person_links.get(entity_id)
                        else None
                    ),
                    "geography_not_borrowed_from_offerings": True,
                    "child_dispositions": {
                        "source_memberships": _child_disposition(
                            len(members), len(source_memberships), []
                        ),
                        "source_membership_labels": _child_disposition(
                            membership_label_candidates,
                            membership_label_candidates - len(membership_label_reasons),
                            membership_label_reasons,
                        ),
                        "source_membership_statuses": _child_disposition(
                            membership_status_candidates,
                            membership_status_candidates
                            - len(membership_status_reasons),
                            membership_status_reasons,
                        ),
                        "locations": _child_disposition(
                            len(locations.get(entity_id, [])),
                            len(location_children),
                            location_reasons,
                        ),
                        "location_labels": _child_disposition(
                            location_label_candidates,
                            location_label_candidates - len(location_label_reasons),
                            location_label_reasons,
                        ),
                        "location_metadata": _child_disposition(
                            location_metadata_candidates,
                            location_metadata_candidates
                            - len(location_metadata_reasons),
                            location_metadata_reasons,
                        ),
                        "relationships": _child_disposition(
                            len(edges.get(entity_id, []))
                            + len(reviewed.get(entity_id, [])),
                            len(relationships),
                            relationship_reasons,
                        ),
                        "relationship_labels": _child_disposition(
                            relationship_label_candidates,
                            relationship_label_candidates
                            - len(relationship_label_reasons),
                            relationship_label_reasons,
                        ),
                        "relationship_kinds": _child_disposition(
                            relationship_kind_candidates,
                            relationship_kind_candidates
                            - len(relationship_kind_reasons),
                            relationship_kind_reasons,
                        ),
                        "reviewed_evidence": _child_disposition(
                            len(evidence.get(entity_id, [])),
                            len(descriptions),
                            description_reasons,
                        ),
                        "directory_relationships": _child_disposition(
                            len(person_links.get(entity_id, [])),
                            0,
                            [
                                "directory_relationship_policy_withheld"
                                for _ in person_links.get(entity_id, [])
                            ],
                        ),
                    },
                }
            )
            self._store(result, measure, entity_id, detail)

    def offerings(self, result: dict) -> None:
        measure = "K07"
        families = {
            str(row.get("family_id")): row
            for row in _rows(self.tables, "domains/commerce/offering_families")
        }
        members = _group(
            _rows(self.tables, "domains/commerce/offering_family_members"), "family_id"
        )
        offerings = {
            str(row.get("global_offering_id")): row
            for row in _rows(self.tables, "domains/commerce/global_offerings")
        }
        crosswalk = _group(
            _rows(self.tables, "domains/commerce/offering_crosswalk"),
            "global_offering_id",
        )
        listings = _group(
            _rows(self.tables, "domains/commerce/listing_evidence"),
            "global_offering_id",
        )
        prices = _group(
            _rows(self.tables, "domains/commerce/prices"), "global_offering_id"
        )
        locations = _group(
            _rows(self.tables, "domains/commerce/locations"), "global_offering_id"
        )
        media_rows = _group(
            _rows(self.tables, "domains/commerce/media"), "global_offering_id"
        )
        edges = _group(
            _rows(self.tables, "domains/commerce/operator_offering_edges"),
            "global_offering_id",
        )
        reviewed_relationships = _group(
            _rows(self.tables, "domains/commerce/reviewed_relationships"),
            "object_global_id",
        )
        reviewed_evidence = _group(
            _rows(self.tables, "domains/commerce/reviewed_evidence"),
            "global_offering_id",
        )
        operator_labels = {
            str(row.get("global_operator_id")): _clean_label(row.get("display_name"))
            for row in _rows(self.tables, "domains/commerce/global_operators")
        }
        innovation_labels = {
            str(row.get("global_innovation_id")): _clean_label(row.get("display_name"))
            for row in _rows(self.tables, "domains/innovations/global_innovations")
        }
        for entity_id in self.entity_ids[measure]:
            family = families.get(entity_id)
            label = _clean_label(family.get("display_name")) if family else None
            if not label:
                self._store(
                    result, measure, entity_id, None, "unsafe_or_missing_public_label"
                )
                continue
            family_members = members.get(entity_id, [])
            if not family_members:
                self._store(
                    result,
                    measure,
                    entity_id,
                    None,
                    "missing_preserved_offering_children",
                )
                continue
            offering_children, logical_sources, provinces = [], set(), set()
            missing_preserved_child = False
            for membership in sorted(
                family_members,
                key=lambda value: str(value.get("global_offering_id", "")),
            ):
                offering_id = str(membership.get("global_offering_id", ""))
                offering = offerings.get(offering_id)
                offering_label = (
                    _clean_label(offering.get("display_name")) if offering else None
                )
                if not offering_label:
                    missing_preserved_child = True
                    break
                source_members = crosswalk.get(offering_id, [])
                if not source_members:
                    missing_preserved_child = True
                    break
                sources = {
                    str(item.get("source"))
                    for item in source_members
                    if item.get("source")
                }
                logical_sources.update(sources)
                listing_children, descriptions = [], []
                listing_reasons, description_reasons = [], []
                description_candidate_count = 0
                for item in sorted(
                    listings.get(offering_id, []),
                    key=lambda value: str(value.get("source_listing_id", "")),
                ):
                    source = str(item.get("source", ""))
                    if not _allowed(
                        self.policy, measure, source, "relationships", "listing"
                    ):
                        listing_reasons.append("listing_source_not_allowlisted")
                        continue
                    url = (
                        _public_url(
                            item.get("source_url"), self.policy, source, measure=measure
                        )
                        if _allowed(
                            self.policy, measure, source, "source_link", "source_url"
                        )
                        else None
                    )
                    entry = {
                        "listing_id": str(item.get("source_listing_id", "")),
                        "label": _clean_label(
                            item.get("title_normalized") or item.get("title_raw")
                        )
                        or offering_label,
                        "category": _clean_label(item.get("category_raw")),
                        "source_url": url,
                        "source_id": _canonical_source(self.policy, source),
                    }
                    listing_children.append(entry)
                    if item.get("description") not in (None, ""):
                        description_candidate_count += 1
                        if not _allowed(
                            self.policy,
                            measure,
                            source,
                            "structured_excerpt",
                            "description",
                        ):
                            description_reasons.append(
                                "description_field_not_allowlisted"
                            )
                        else:
                            description = _description(
                                "listing",
                                item.get("description"),
                                _canonical_source(self.policy, source),
                                self.limit,
                            )
                            if description:
                                descriptions.append(description)
                            else:
                                description_reasons.append(
                                    "unsafe_or_missing_description"
                                )
                price_children, price_reasons = [], []
                for item in sorted(
                    prices.get(offering_id, []),
                    key=lambda value: str(value.get("source_price_id", "")),
                ):
                    source = str(item.get("source", ""))
                    if not _allowed(
                        self.policy, measure, source, "price", "amounts_json"
                    ):
                        price_reasons.append("price_source_not_allowlisted")
                        continue
                    amounts, price_reason = _price_amounts(
                        item, self.policy, measure, source
                    )
                    if price_reason:
                        price_reasons.append(price_reason)
                        continue
                    if amounts:
                        unit, unit_status = _reported_price_unit(
                            item, self.policy, measure, source
                        )
                        price_children.append(
                            {
                                "price_id": str(item.get("source_price_id", "")),
                                "amounts": amounts,
                                "currency": _clean_label(item.get("currency")),
                                "unit": unit,
                                "unit_status": unit_status,
                                "parse_status": _clean_label(item.get("parse_status")),
                                "interpretation": (
                                    "source_reported_amount_not_current_availability_or_free_claim"
                                ),
                                "price_as_of": None,
                                "price_as_of_status": "not_reported",
                                "source_snapshot_ref": self.price_snapshot_refs.get(
                                    str(item.get("source_price_id", ""))
                                ),
                                "source_id": _canonical_source(self.policy, source),
                            }
                        )
                location_children, location_reasons = [], []
                for item in sorted(
                    locations.get(offering_id, []),
                    key=lambda value: str(value.get("source_location_id", "")),
                ):
                    source = str(item.get("source", ""))
                    if item.get("global_offering_id") != offering_id or not _allowed(
                        self.policy,
                        measure,
                        source,
                        "location",
                        "offering_location",
                    ):
                        location_reasons.append(
                            "detached_or_unapproved_offering_location"
                        )
                        continue
                    location = _location(item, _canonical_source(self.policy, source))
                    location_children.append(location)
                    if location.get("province_code"):
                        provinces.add(str(location["province_code"]))
                media, media_reasons = [], []
                for item in sorted(
                    media_rows.get(offering_id, []),
                    key=lambda value: str(value.get("source_media_id", "")),
                ):
                    source = str(item.get("source", ""))
                    if not _allowed(
                        self.policy, measure, source, "media", "url_or_value"
                    ):
                        media_reasons.append("media_source_not_allowlisted")
                        continue
                    medium = _media(item, self.policy, source, measure=measure)
                    if medium:
                        media.append(medium)
                    else:
                        media_reasons.append("unsafe_or_unapproved_media_reference")
                relations = []
                for item in sorted(
                    edges.get(offering_id, []),
                    key=lambda value: str(
                        value.get("source_operator_offering_edge_id", "")
                    ),
                ):
                    source = str(item.get("source", ""))
                    if _allowed(
                        self.policy,
                        measure,
                        source,
                        "relationships",
                        "operator_offering",
                    ):
                        operator_id = str(item.get("global_operator_id", ""))
                        relations.append(
                            {
                                "kind": _clean_label(item.get("relationship"))
                                or "operator_offering",
                                "entity_id": operator_id,
                                "label": operator_labels.get(operator_id),
                                "source_id": _canonical_source(self.policy, source),
                            }
                        )
                for item in sorted(
                    reviewed_relationships.get(offering_id, []),
                    key=lambda value: str(value.get("relationship_id", "")),
                ):
                    operator_id = str(item.get("subject_global_id", ""))
                    relations.append(
                        {
                            "kind": _clean_label(item.get("relationship"))
                            or "operator_offering",
                            "entity_id": operator_id,
                            "label": operator_labels.get(operator_id),
                            "source_ids": sorted(
                                {
                                    _canonical_source(self.policy, source)
                                    for source in sources
                                }
                            ),
                        }
                    )
                innovation_context = []
                for item in sorted(
                    reviewed_evidence.get(offering_id, []),
                    key=lambda value: str(value.get("evidence_id", "")),
                ):
                    innovation_id = str(item.get("global_innovation_id", ""))
                    source = str(item.get("source", ""))
                    if innovation_id and _allowed(
                        self.policy,
                        measure,
                        source,
                        "relationships",
                        "innovation_context",
                    ):
                        innovation_context.append(
                            {
                                "entity_id": innovation_id,
                                "label": innovation_labels.get(innovation_id),
                                "relationship": _clean_label(item.get("relationship")),
                                "source_id": _canonical_source(self.policy, source),
                            }
                        )
                if listing_reasons:
                    missing_preserved_child = True
                    break
                offering_children.append(
                    {
                        "entity_id": offering_id,
                        "label": offering_label,
                        "identity_status": _clean_label(offering.get("identity_status"))
                        or "unknown",
                        "membership_role": _clean_label(
                            membership.get("membership_role")
                        ),
                        "source_ids": sorted(
                            {
                                _canonical_source(self.policy, source)
                                for source in sources
                            }
                        ),
                        "descriptions": descriptions,
                        "listings": listing_children,
                        "locations": location_children,
                        "media": media,
                        "relationships": relations,
                        "children": {
                            "prices": price_children,
                            "innovation_context": innovation_context,
                        },
                        "child_dispositions": {
                            "listings": _child_disposition(
                                len(listings.get(offering_id, [])),
                                len(listing_children),
                                listing_reasons,
                            ),
                            "descriptions": _child_disposition(
                                description_candidate_count,
                                len(descriptions),
                                description_reasons,
                            ),
                            "prices": _child_disposition(
                                len(prices.get(offering_id, [])),
                                len(price_children),
                                price_reasons,
                            ),
                            "locations": _child_disposition(
                                len(locations.get(offering_id, [])),
                                len(location_children),
                                location_reasons,
                            ),
                            "media": _child_disposition(
                                len(media_rows.get(offering_id, [])),
                                len(media),
                                media_reasons,
                            ),
                        },
                    }
                )
            if missing_preserved_child:
                self._store(
                    result,
                    measure,
                    entity_id,
                    None,
                    "unsafe_or_missing_preserved_offering_child",
                )
                continue
            source_ids = [
                _canonical_source(self.policy, source) for source in logical_sources
            ]
            detail = _base_detail(
                entity_id,
                label,
                family.get("identity_status"),
                source_ids,
                [_system(self.policy, source) for source in logical_sources],
                province_codes=provinces,
            )
            detail["children"] = {"offerings": offering_children}
            detail["flags"].update(
                {
                    "all_preserved_offerings_included": True,
                    "variants_are_children_not_entities": True,
                }
            )
            self._store(result, measure, entity_id, detail)

    def participating_businesses(self, result: dict) -> None:
        measure = "C08_PARTICIPATING"
        source, source_id = (
            "learning_area_based",
            _canonical_source(self.policy, "learning_area_based"),
        )
        businesses = {
            str(row.get("business_id")): row
            for row in _rows(self.tables, "sources/f2_learning_area_based/businesses")
        }
        participations = _group(
            _rows(self.tables, "sources/f2_learning_area_based/participations"),
            "business_id",
        )
        projects = {
            str(row.get("assertion_id")): row
            for row in _rows(
                self.tables, "sources/f2_learning_area_based/project_assertions"
            )
        }
        research_units = {
            str(row.get("assertion_id")): row
            for row in _rows(
                self.tables, "sources/f2_learning_area_based/research_unit_assertions"
            )
        }
        locations = _group(
            _rows(self.tables, "sources/f2_learning_area_based/locations"),
            "business_id",
        )
        for entity_id in self.entity_ids[measure]:
            row = businesses.get(entity_id)
            raw_label = row.get("display_name") if row else None
            label = _clean_finalized_label(raw_label)
            source_name_unavailable = bool(
                row
                and raw_label in (None, "")
                and row.get("identity_status") == "provisional_malformed_name"
                and row.get("name_quality") == "malformed_name"
            )
            if source_name_unavailable:
                label = "ไม่พบชื่อจากแหล่งข้อมูล"
            if not label:
                self._store(
                    result, measure, entity_id, None, "unsafe_or_missing_public_label"
                )
                continue
            location_children = []
            location_reasons = []
            location_label_candidates = 0
            location_label_reasons = []
            for item in sorted(
                locations.get(entity_id, []),
                key=lambda value: str(value.get("location_id", "")),
            ):
                if not _allowed(
                    self.policy, measure, source, "location", "business_location"
                ):
                    location_reasons.append("business_location_not_allowlisted")
                    continue
                location = _location(item, source_id)
                for field in (
                    "province_normalized",
                    "district_normalized",
                    "subdistrict_normalized",
                ):
                    if item.get(field) not in (None, ""):
                        location_label_candidates += 1
                        if location.get(field.removesuffix("_normalized")) is None:
                            location_label_reasons.append(
                                "location_label_admission_failed"
                            )
                location_children.append(location)
            children = []
            fiscal_year_candidates = 0
            fiscal_year_reasons = []
            project_candidates = 0
            project_reasons = []
            research_unit_candidates = 0
            research_unit_reasons = []
            for item in sorted(
                participations.get(entity_id, []),
                key=lambda value: str(value.get("participation_id", "")),
            ):
                project_id = str(item.get("project_assertion_id") or "")
                unit_id = str(item.get("research_unit_assertion_id") or "")
                project = projects.get(project_id, {})
                unit = research_units.get(unit_id, {})
                fiscal_year = (
                    int(item["fiscal_year_be"])
                    if str(item.get("fiscal_year_be", "")).isdigit()
                    else None
                )
                if item.get("fiscal_year_be") not in (None, ""):
                    fiscal_year_candidates += 1
                    if fiscal_year is None:
                        fiscal_year_reasons.append("fiscal_year_admission_failed")
                project_label = _clean_label(project.get("project_name_raw"))
                if project_id:
                    project_candidates += 1
                    if not project or project_label is None:
                        project_reasons.append(
                            "project_assertion_missing_or_admission_failed"
                        )
                research_unit_label = _clean_label(unit.get("research_unit_raw"))
                if unit_id:
                    research_unit_candidates += 1
                    if not unit or research_unit_label is None:
                        research_unit_reasons.append(
                            "research_unit_assertion_missing_or_admission_failed"
                        )
                children.append(
                    {
                        "participation_id": str(item.get("participation_id", "")),
                        "fiscal_year_be": fiscal_year,
                        "project": project_label,
                        "research_unit": research_unit_label,
                        "source_id": source_id,
                    }
                )
            detail = _base_detail(
                entity_id,
                label,
                row.get("identity_status"),
                [source_id],
                [_system(self.policy, source)],
                province_codes=[
                    item.get("province_code") for item in location_children
                ],
            )
            detail.update(
                {
                    "locations": location_children,
                    "children": {"participations": children},
                }
            )
            detail["flags"].update(
                {
                    "participation_not_improvement": True,
                    "person_assessments_withheld": True,
                    "person_assessment_withholding_reason": (
                        "individual_development_assessments_are_aggregate_only"
                    ),
                    "child_dispositions": {
                        "locations": _child_disposition(
                            len(locations.get(entity_id, [])),
                            len(location_children),
                            location_reasons,
                        ),
                        "location_labels": _child_disposition(
                            location_label_candidates,
                            location_label_candidates - len(location_label_reasons),
                            location_label_reasons,
                        ),
                        "participations": _child_disposition(
                            len(participations.get(entity_id, [])),
                            len(children),
                            [],
                        ),
                        "fiscal_years": _child_disposition(
                            fiscal_year_candidates,
                            fiscal_year_candidates - len(fiscal_year_reasons),
                            fiscal_year_reasons,
                        ),
                        "projects": _child_disposition(
                            project_candidates,
                            project_candidates - len(project_reasons),
                            project_reasons,
                        ),
                        "research_units": _child_disposition(
                            research_unit_candidates,
                            research_unit_candidates - len(research_unit_reasons),
                            research_unit_reasons,
                        ),
                    },
                }
            )
            if source_name_unavailable:
                detail["flags"].update(
                    {
                        "source_name_available": False,
                        "label_is_generated_placeholder": True,
                        "source_name_unavailability_reason": "malformed_source_name",
                    }
                )
            self._store(result, measure, entity_id, detail)

    def mapped_subjects(self, result: dict) -> None:
        measure = "K12"
        subjects = {
            str(row.get("subject_id")): row
            for row in _rows(
                self.tables,
                "sources/f2_culturalmap_university/mapped_subjects",
            )
        }
        source, source_id = (
            "cultural_map",
            _canonical_source(self.policy, "cultural_map"),
        )
        admission = _source_spec(self.policy, source).get("record_admission", {})
        explicit_withholding = admission.get("withheld_subject_ids", {})
        allowed_identity_statuses = set(admission.get("allowed_identity_statuses", []))
        for entity_id in self.entity_ids[measure]:
            row = subjects.get(entity_id)
            raw_label = row.get("display_title") if row else None
            source_keys = (
                {
                    str(value)
                    for value in _json_list(row.get("source_keys_json"))
                    if value
                }
                if row
                else set()
            )
            label_context = _reviewed_mapped_label_context(
                self.policy, entity_id, source_keys, raw_label
            )
            label, label_availability, label_withholding_reason = _mapped_label(
                raw_label, label_context
            )
            if not label:
                self._store(
                    result,
                    measure,
                    entity_id,
                    None,
                    "missing_public_label",
                )
                continue
            if entity_id in explicit_withholding:
                self._store(
                    result,
                    measure,
                    entity_id,
                    None,
                    str(explicit_withholding[entity_id]),
                )
                continue
            if (
                str(row.get("k12_eligible")).lower() != "true"
                or str(row.get("identity_status")) not in allowed_identity_statuses
            ):
                self._store(
                    result,
                    measure,
                    entity_id,
                    None,
                    "missing_required_mapped_record_admission",
                )
                continue
            material = self._mapped_material(entity_id, measure, source_keys)
            if (
                material["fatal_reason"]
                or not source_keys
                or len(source_keys)
                != material["child_dispositions"]["listings"]["candidate_count"]
            ):
                self._store(
                    result,
                    measure,
                    entity_id,
                    None,
                    material["fatal_reason"]
                    or "missing_required_mapped_record_admission",
                )
                continue
            detail = _base_detail(
                entity_id,
                label,
                row.get("identity_status"),
                [source_id],
                [_system(self.policy, source)],
                province_codes=material["province_codes"],
                category_codes=material["category_codes"],
            )
            detail.update(
                {
                    key: material[key]
                    for key in (
                        "descriptions",
                        "listings",
                        "locations",
                        "media",
                    )
                }
            )
            detail["flags"].update(
                {
                    "label_availability": label_availability,
                    "label_withholding_reason": label_withholding_reason,
                    "source_field_exclusions": [
                        "informant_and_contact_details",
                        "exact_coordinates_and_street_addresses",
                        "financial_health_and_assessment_values",
                    ],
                    "record_admission_basis": (
                        "policy_allowed_mapped_subject_with_attached_public_listing"
                    ),
                    "child_dispositions": material["child_dispositions"],
                }
            )
            additional_field_contexts = {}
            if label_context is not None:
                additional_field_contexts["/label"] = label_context
            if material["reviewed_listing_label_context"]:
                additional_field_contexts["/listings/*/label"] = "public_location"
            self._store(
                result,
                measure,
                entity_id,
                detail,
                additional_field_contexts=additional_field_contexts,
            )


def build_details(
    tables: dict,
    definitions: Any,
    policy: dict,
    input_manifest: list[dict] | None = None,
) -> dict[str, dict[str, dict]]:
    """Build staged public detail candidates keyed by measure and public entity ID.

    Every counted entity is represented exactly once, either in ``details`` or
    in ``withheld`` with a stable reason code.  K04 and C04_LISTED use one
    shared innovation adapter so a shared entity has equal detail in both.
    ``input_manifest`` is optional only for legacy synthetic callers; real
    projections pass the verified release ledger for price capture context.
    """
    if not isinstance(tables, dict) or not isinstance(policy, dict):
        raise PipelineError("Public detail inputs are malformed")
    missing_definitions = set(REQUIRED_MEASURES) - _definition_ids(definitions)
    if missing_definitions:
        raise PipelineError(
            f"Public detail definitions are missing: {sorted(missing_definitions)}"
        )
    policies = policy.get("detail_policies", {})
    if not isinstance(policies, dict) or not set(REQUIRED_MEASURES) <= set(policies):
        raise PipelineError(
            "Public detail policy is missing the complete staged-review policy"
        )
    result = {measure: {"details": {}, "withheld": {}} for measure in REQUIRED_MEASURES}
    builder = _Builder(tables, policy, input_manifest)
    builder.areas(result)
    builder.activities(result)
    builder.innovations(result)
    builder.operators(result)
    builder.offerings(result)
    builder.participating_businesses(result)
    builder.mapped_subjects(result)
    for measure in REQUIRED_MEASURES:
        represented = set(result[measure]["details"]) | set(result[measure]["withheld"])
        if represented != set(builder.entity_ids[measure]) or set(
            result[measure]["details"]
        ) & set(result[measure]["withheld"]):
            raise PipelineError(f"{measure} public detail coverage does not reconcile")
    return result
