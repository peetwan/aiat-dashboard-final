from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import io
import json
import math
import posixpath
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import parse_qsl, unquote, urlsplit


CONTRACT_VERSION = "1.0"
RECEIPT_VERSION = "1.0"
PUBLIC_PREFIX = "data/public/"
RECEIPT_PATH = f"{PUBLIC_PREFIX}publication_receipt.json"
SERVING_MANIFEST_PATH = f"{PUBLIC_PREFIX}serving_manifest.json"
PUBLICATION_CONTROL_PATHS = {RECEIPT_PATH, SERVING_MANIFEST_PATH}
PRODUCTION_SEED_PREFIXES = (PUBLIC_PREFIX, "data/spatial/", "data/demand/")
ALLOWED_FORMATS = {"json", "geojson", "csv"}
ALLOWED_ROLES = {"database", "download", "provenance", "support"}
ALLOWED_PRIVACY_PROFILES = {
    "aggregate_public",
    "catalog_metadata",
    "provenance_metadata",
    "reference_geography",
}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SAFE_SOURCE_ID_RE = re.compile(r"^[a-z0-9_]+$")
SAFE_PUBLIC_PATH_RE = re.compile(r"^data/public/[A-Za-z0-9_./\[\]*?-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
# High-confidence Thai telephone tokens.  Requiring either +66 or a local 0
# prefix, realistic fixed/mobile lengths, and non-word boundaries prevents a
# run of digits inside a hash, decimal, or prefixed machine identifier from
# being mistaken for contact data.  There is deliberately no field-name
# bypass: an exact phone-shaped value is unsafe even under *_id/*_code/*_hash.
PHONE_RE = re.compile(
    r"(?<![\w.])(?:"
    r"\+66(?:[\s.-]*\(0\))?[\s().-]*"
    r"(?:(?:[2-5]|7)(?:[\s().-]*\d){7}|[689](?:[\s().-]*\d){8})|"
    r"66[\s()-]*(?:(?:[2-5]|7)(?:[\s()-]*\d){7}|[689](?:[\s()-]*\d){8})|"
    r"0(?:[2-5]|7)(?:[\s().-]*\d){7}|0[689](?:[\s().-]*\d){8}"
    r")(?![\w.])"
)
LABELLED_CONTACT_RE = re.compile(
    r"(?i)(?:\b(?:phone|telephone|mobile|tel|email)\s*(?:no\.?|number)?\s*[:：]|"
    r"(?:โทรศัพท์|เบอร์โทร|อีเมล|อีเมล์)\s*[:：])"
)
ADDRESS_VALUE_RE = re.compile(
    r"(?i)(?:\b(?:home|residential|mailing)\s+address\b|"
    r"^\s*\d{1,5}(?:/\d{1,5})?\s+[A-Z0-9 .'-]{1,80}"
    r"(?:Road|Rd\.?|Street|St\.?|Avenue|Ave\.?|Lane)\s*[,\s]+"
    r"[A-Z .'-]{2,60}\s+\d{5}\s*$|"
    r"ที่อยู่(?:บ้าน|ปัจจุบัน|ตามทะเบียนบ้าน)|บ้านเลขที่|"
    r"^\s*(?:(?:ที่อยู่|เลขที่)\s*[:：]?\s*)?"
    r"\d{1,5}(?:/\d{1,5})?\s+.{0,30}?"
    r"(?:ถนน|ถ\.|ซอย|ซ\.|หมู่(?:ที่)?\s*\d+|แขวง).{0,140}?(?:\s|,)+"
    r"(?:ตำบล|แขวง|อำเภอ|เขต|จังหวัด|กรุงเทพ(?:มหานคร|ฯ)|\d{5}\b))"
)
SIGNED_URL_RE = re.compile(
    r"(?i)[?&](?:access_token|api_?key|key|sig|signature|token|"
    r"x-amz-credential|x-amz-signature)="
)
SECRET_VALUE_RE = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b|"
    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b|"
    r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}\b|"
    r"\bAKIA[A-Z0-9]{16}\b|"
    r"\bAIza[A-Za-z0-9_-]{35}\b)"
)
CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?i)(?:"
    r"\bauthorization\s*:\s*(?:basic|bearer)\s+"
    r"(?!(?:redacted|removed|unknown|none|null|not_available)\b)"
    r"[A-Za-z0-9._~+/=-]{8,}|"
    r"\b(?:password|passwd|pwd|client_secret|api_?key|access_token|token)"
    r"\s*[:=]\s*"
    r"(?!(?:redacted|removed|unknown|none|null|false|not_available)\b)"
    r"[^\s,;]{8,}"
    r")"
)
NUMERIC_CELL_RE = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)
SENSITIVE_KEY_PARTS = {
    "api_key",
    "apikey",
    "authorization",
    "birth_date",
    "citizen_id",
    "contact_name",
    "contact_person",
    "cookie",
    "date_of_birth",
    "email",
    "e_mail",
    "first_name",
    "full_name",
    "household_id",
    "id_card",
    "last_name",
    "member_id",
    "mobile",
    "national_id",
    "owner_name",
    "password",
    "patient_id",
    "person_id",
    "person_name",
    "phone",
    "respondent_id",
    "researcher_name",
    "secret",
    "social_security",
    "student_id",
    "telephone",
    "token",
    "user_id",
}
EXACT_SENSITIVE_KEYS = {"address", "contact", "credential"}
SENSITIVE_THAI_KEY_PARTS = (
    "ชื่อบุคคล",
    "เลขบัตร",
    "เบอร์โทร",
    "อีเมล",
    "อีเมล์",
    "ที่อยู่บ้าน",
    "วันเกิด",
)
NEGATIVE_AUDIT_KEY_SUFFIXES = (
    "_excluded",
    "_fields_in_source_schema",
    "_fields_included",
    "_field_count",
    "_values_redacted",
)
MAX_DEFAULT_FILE_BYTES = 25 * 1024 * 1024
MAX_DEFAULT_TOTAL_BYTES = 40 * 1024 * 1024
MAX_DEFAULT_DEPTH = 40
MAX_DEFAULT_NODES = 2_000_000

SAFE_REPORT_KEY_RE = re.compile(
    r"^[A-Za-z_\u0E00-\u0E7F][A-Za-z0-9_\-\u0E00-\u0E7F]{0,79}$"
)
ENCODED_PATH_CONTROL_RE = re.compile(r"(?i)%(?:2e|2f|3b|5c)")
PERCENT_ESCAPE_RE = re.compile(r"%([0-9A-Fa-f]{2})")
INVALID_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
URL_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)
CREDENTIAL_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "client_secret",
    "credential",
    "key",
    "secret",
    "sig",
    "signature",
    "token",
    "x_amz_credential",
    "x_amz_signature",
}
APPROVED_EXCLUDED_AUDIT_KEYS = {
    "restricted_source_ids_excluded",
    "restricted_sources_excluded",
    "restricted_values_excluded",
}

SEMANTIC_VALUE_KEYS = {
    "aggregation_level",
    "calculation_method",
    "calculation_method_th",
    "candidate_not_fact",
    "classification",
    "data_grain",
    "data_grain_th",
    "definition",
    "definition_th",
    "denominator",
    "denominator_th",
    "geographic_level",
    "geographic_meaning",
    "geographic_scope",
    "geography_level",
    "geography_meaning",
    "geography_scope",
    "grain",
    "grain_th",
    "indicator_name",
    "indicator_name_th",
    "measure_name",
    "measure_name_th",
    "methodology",
    "methodology_th",
    "metric_label",
    "metric_label_th",
    "metric_name",
    "metric_name_th",
    "province_join_method",
    "quality_label",
    "quality_label_th",
    "record_grain",
    "review_state",
    "scope_warning",
    "scope_warning_th",
    "status",
    "publication_state",
    "unit",
    "unit_th",
    "verification_state",
}
SEMANTIC_SUFFIXES = (
    "_denominator",
    "_definition",
    "_definition_th",
    "_grain",
    "_method",
    "_method_th",
    "_status",
    "_unit",
)
GEOGRAPHY_CONTEXT_KEYS = {"definition", "fields", "grain", "level", "meaning", "scope"}
TEMPORAL_VALUE_KEYS = {"as_of", "observed_as_of"}
GOVERNANCE_KEY_TOKENS = {
    "accepted",
    "candidate",
    "classification",
    "review",
    "verification",
}
GOVERNANCE_VALUE_TOKENS = {
    "accepted",
    "candidate",
    "needs_review",
    "provisional",
    "public_candidate",
    "restricted",
    "reviewed",
}


class PublicationError(RuntimeError):
    """The reviewed publication contract or release is invalid."""


@dataclass(frozen=True)
class FileEntry:
    path: str
    data: bytes
    mode: str = "100644"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True)
class OutputBinding:
    contract_path: Path
    contract: dict[str, Any]
    output: dict[str, Any]


@dataclass(frozen=True)
class CanonicalUrl:
    scheme: str
    host: str
    port: int
    path: str
    query: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SourceUrlRule:
    address: CanonicalUrl
    allow_descendants: bool
    restricted: bool = False


@dataclass(frozen=True)
class ProvenanceUrlReference:
    address: CanonicalUrl
    source_ids: frozenset[str]
    path: str


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            # A JSON object key may itself contain contact data or a secret.
            raise PublicationError("duplicate JSON key")
        result[key] = value
    return result


def load_json_bytes(data: bytes, *, path: str) -> Any:
    if data.startswith(b"\xef\xbb\xbf"):
        raise PublicationError(f"{path} must use canonical UTF-8 without a BOM")
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_json_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                PublicationError(f"non-finite JSON number in {path}: {value}")
            ),
        )
    except UnicodeDecodeError as exc:
        raise PublicationError(f"{path} is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise PublicationError(f"invalid JSON in {path}: {exc.msg}") from exc


def _read_json_file(path: Path) -> dict[str, Any]:
    payload = load_json_bytes(path.read_bytes(), path=path.as_posix())
    if not isinstance(payload, dict):
        raise PublicationError(f"JSON object required: {path.as_posix()}")
    return payload


def _normalise_key(value: object) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value))
    return re.sub(r"[^a-z0-9ก-๙]+", "_", text.lower()).strip("_")


def _tainted_report_key(text: str, restricted_source_ids: set[str]) -> bool:
    return (
        text in restricted_source_ids
        or EMAIL_RE.search(text) is not None
        or PHONE_RE.search(text) is not None
        or LABELLED_CONTACT_RE.search(text) is not None
        or ADDRESS_VALUE_RE.search(text) is not None
        or SIGNED_URL_RE.search(text) is not None
        or SECRET_VALUE_RE.search(text) is not None
        or CREDENTIAL_ASSIGNMENT_RE.search(text) is not None
        or _has_credential_query_url(text)
    )


def _report_key_path(
    parent: str,
    key: object,
    *,
    redact: bool = False,
    restricted_source_ids: set[str] | None = None,
) -> str:
    """Build an actionable path without ever echoing an opaque map key."""

    text = str(key)
    if (
        redact
        or SAFE_REPORT_KEY_RE.fullmatch(text) is None
        or _tainted_report_key(text, restricted_source_ids or set())
    ):
        return f"{parent}.<map-key>"
    return f"{parent}.{text}"


def _canonical_url(value: Any, *, catalog: bool) -> CanonicalUrl:
    label = "source catalog URL" if catalog else "embedded provenance URL"
    if not isinstance(value, str) or not value or value != value.strip():
        raise PublicationError(f"{label} must be a non-empty absolute HTTP(S) URL")
    if any(ord(character) < 32 for character in value) or "\\" in value:
        raise PublicationError(f"{label} contains unsafe characters")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise PublicationError(f"{label} is malformed") from exc
    scheme = parsed.scheme.lower()
    if (
        scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise PublicationError(f"{label} must be an uncredentialed absolute HTTP(S) URL")
    try:
        host = parsed.hostname.rstrip(".").lower().encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise PublicationError(f"{label} has an invalid host") from exc
    if not host:
        raise PublicationError(f"{label} has an invalid host")
    if port is None:
        port = 443 if scheme == "https" else 80
    raw_path = parsed.path or "/"
    if (
        ENCODED_PATH_CONTROL_RE.search(raw_path)
        or INVALID_PERCENT_RE.search(raw_path)
        or re.search(r"(?i)%25", raw_path)
    ):
        raise PublicationError(f"{label} contains an ambiguous encoded path")

    def decode_unreserved(match: re.Match[str]) -> str:
        character = chr(int(match.group(1), 16))
        return character if character in URL_UNRESERVED else match.group(0).upper()

    decoded_path = PERCENT_ESCAPE_RE.sub(decode_unreserved, raw_path)
    if "//" in decoded_path or any(
        segment in {".", ".."} for segment in decoded_path.split("/")
    ):
        raise PublicationError(f"{label} contains ambiguous path traversal")
    path = posixpath.normpath(decoded_path)
    if not path.startswith("/"):
        path = f"/{path}"
    query = tuple(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    if not catalog and _query_has_credential_parameter(parsed.query):
        raise PublicationError(
            "embedded provenance URL contains a credential query parameter"
        )
    return CanonicalUrl(scheme, host, port, path, query)


def _query_has_credential_parameter(raw_query: str) -> bool:
    """Detect credential parameters across ordinary and encoded separators."""

    candidate = raw_query
    for _ in range(3):
        for segment in re.split(r"[&;]", candidate):
            key = segment.partition("=")[0]
            normalized = key.strip().lower().replace("-", "_")
            if "%" in key or normalized in CREDENTIAL_QUERY_KEYS:
                return True
        decoded = unquote(candidate)
        if decoded == candidate:
            break
        candidate = decoded
    return False


def _has_credential_query_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"}:
            return False
        _canonical_url(value, catalog=False)
    except PublicationError as exc:
        return "credential query parameter" in str(exc)
    except ValueError:
        return False
    return False


def _url_matches_rule(address: CanonicalUrl, rule: SourceUrlRule) -> bool:
    registered = rule.address
    if (address.scheme, address.host, address.port) != (
        registered.scheme,
        registered.host,
        registered.port,
    ):
        return False
    if rule.allow_descendants:
        path_matches = (
            registered.path == "/"
            or address.path == registered.path
            or address.path.startswith(registered.path.rstrip("/") + "/")
        )
        if not path_matches:
            return False
        # A query-bearing canonical landing URL is exact; an ordinary landing
        # path may receive harmless tracking/filter parameters.
        return not registered.query or address.query == registered.query
    return address.path == registered.path and address.query == registered.query


def _is_negative_audit(key: str, value: Any) -> bool:
    if key.endswith("_exposed") and value is False:
        return True
    if key.endswith(NEGATIVE_AUDIT_KEY_SUFFIXES):
        if value in (False, None, 0):
            return True
        if key.endswith("_values_redacted") and type(value) is int and value >= 0:
            return True
        if key in APPROVED_EXCLUDED_AUDIT_KEYS and isinstance(value, list):
            return True
    return False


def _sensitive_key(key: str, value: Any) -> bool:
    normalized = _normalise_key(key)
    if normalized == "mobile_home_park":
        return False
    if _is_negative_audit(normalized, value):
        return False
    if normalized in EXACT_SENSITIVE_KEYS:
        return True
    padded = f"_{normalized}_"
    return any(f"_{part}_" in padded for part in SENSITIVE_KEY_PARTS) or any(
        part in str(key) for part in SENSITIVE_THAI_KEY_PARTS
    )


def _privacy_reasons_for_text(
    value: str,
    *,
    restricted_source_ids: set[str],
    allow_restricted: bool,
) -> list[str]:
    reasons: list[str] = []
    if value in restricted_source_ids and not allow_restricted:
        reasons.append("restricted source identifier")
    if EMAIL_RE.search(value):
        reasons.append("email-like value")
    if LABELLED_CONTACT_RE.search(value):
        reasons.append("labelled contact value")
    if ADDRESS_VALUE_RE.search(value):
        reasons.append("home-address-like value")
    if SIGNED_URL_RE.search(value):
        reasons.append("signed/credential URL")
    elif _has_credential_query_url(value):
        reasons.append("signed/credential URL")
    if SECRET_VALUE_RE.search(value) or CREDENTIAL_ASSIGNMENT_RE.search(value):
        reasons.append("credential-like value")
    if PHONE_RE.search(value):
        reasons.append("Thai phone-like value")
    return reasons


def _privacy_problems(
    payload: Any,
    *,
    artifact_path: str,
    restricted_source_ids: set[str],
    profile: str,
) -> list[str]:
    problems: list[str] = []

    def restricted_allowed(path: str) -> bool:
        return (
            profile == "catalog_metadata"
            or "restricted_source_ids_excluded" in path
            or ".excluded_source_ids[]" in path
        )

    def append(path: str, reason: str) -> None:
        if len(problems) < 50:
            problems.append(f"{path}: {reason}")

    def walk(value: Any, path: str) -> None:
        if len(problems) >= 50:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                provisional_path = _report_key_path(
                    path,
                    key,
                    restricted_source_ids=restricted_source_ids,
                )
                normalized_key = _normalise_key(key)
                key_reasons = _privacy_reasons_for_text(
                    str(key),
                    restricted_source_ids=restricted_source_ids,
                    allow_restricted=restricted_allowed(provisional_path),
                )
                # A suspicious map key is data, not a safe field label.  Never
                # include it in the diagnostic path or in a later child error.
                child_path = _report_key_path(
                    path,
                    key,
                    redact=bool(key_reasons),
                    restricted_source_ids=restricted_source_ids,
                )
                for reason in key_reasons:
                    append(child_path, f"{reason} in object key")
                if normalized_key == "restricted_source_ids_excluded" and (
                    not isinstance(child, list)
                    or any(
                        not isinstance(item, str) or item not in restricted_source_ids
                        for item in child
                    )
                ):
                    append(child_path, "invalid restricted-source exclusion audit")
                if _sensitive_key(str(key), child):
                    append(child_path, "private/contact field")
                walk(child, child_path)
            return
        if isinstance(value, list):
            for child in value:
                walk(child, f"{path}[]")
            return
        if type(value) is int or (
            type(value) is float and math.isfinite(value) and value.is_integer()
        ):
            numeric_text = str(int(value))
            if PHONE_RE.fullmatch(numeric_text):
                append(path, "Thai phone-like numeric value")
            return
        if not isinstance(value, str):
            return
        for reason in _privacy_reasons_for_text(
            value,
            restricted_source_ids=restricted_source_ids,
            allow_restricted=restricted_allowed(path),
        ):
            append(path, reason)

    walk(payload, artifact_path)
    return problems


def _embedded_source_provenance(
    payload: Any,
    *,
    artifact_path: str,
    declared_source_ids: set[str],
    restricted_source_ids: set[str],
) -> tuple[set[str], list[ProvenanceUrlReference]]:
    """Collect provenance IDs/URLs and bind each URL to its nearest source context."""

    found: set[str] = set()
    url_references: list[ProvenanceUrlReference] = []

    def walk(value: Any, path: str, inherited_source_ids: set[str]) -> None:
        if isinstance(value, dict):
            local_source_ids: set[str] = set()
            for key, child in value.items():
                child_path = _report_key_path(
                    path,
                    key,
                    restricted_source_ids=restricted_source_ids,
                )
                normalised = _normalise_key(key)
                if normalised == "source_id":
                    if not isinstance(child, str) or not child:
                        raise PublicationError(
                            f"embedded source_id must be a non-empty string at {child_path}"
                        )
                    local_source_ids.add(child)
                elif normalised == "source_ids":
                    if not isinstance(child, list) or any(
                        not isinstance(item, str) or not item for item in child
                    ):
                        raise PublicationError(
                            f"embedded source_ids must be non-empty strings at {child_path}"
                        )
                    local_source_ids.update(child)

            found.update(local_source_ids)
            active_source_ids = local_source_ids or inherited_source_ids
            for key, child in value.items():
                normalised = _normalise_key(key)
                child_path = _report_key_path(
                    path,
                    key,
                    restricted_source_ids=restricted_source_ids,
                )
                is_singular_url = normalised == "url" or normalised.endswith("_url")
                is_plural_url = normalised == "urls" or normalised.endswith("_urls")
                link_alias = normalised in {
                    "link",
                    "links",
                    "href",
                    "hrefs",
                    "uri",
                    "uris",
                    "website",
                    "websites",
                } or normalised.endswith(
                    (
                        "_link",
                        "_links",
                        "_href",
                        "_hrefs",
                        "_uri",
                        "_uris",
                        "_website",
                        "_websites",
                    )
                )
                is_singular_link = link_alias and isinstance(child, str)
                is_plural_link = link_alias and isinstance(child, list)
                if is_singular_url or is_singular_link:
                    if child is not None:
                        try:
                            address = _canonical_url(child, catalog=False)
                        except PublicationError as exc:
                            raise PublicationError(f"{exc} at {child_path}") from exc
                        url_references.append(
                            ProvenanceUrlReference(
                                address,
                                frozenset(active_source_ids),
                                child_path,
                            )
                        )
                elif is_plural_url or is_plural_link:
                    if child is not None:
                        if not isinstance(child, list) or any(
                            not isinstance(item, str) or not item for item in child
                        ):
                            raise PublicationError(
                                f"embedded provenance URL list is invalid at {child_path}"
                            )
                        for item in child:
                            try:
                                address = _canonical_url(item, catalog=False)
                            except PublicationError as exc:
                                raise PublicationError(f"{exc} at {child_path}") from exc
                            url_references.append(
                                ProvenanceUrlReference(
                                    address,
                                    frozenset(active_source_ids),
                                    child_path,
                                )
                            )
                elif link_alias and child is not None and not isinstance(child, dict):
                    raise PublicationError(
                        f"embedded provenance URL value is invalid at {child_path}"
                    )
                map_source_ids = (
                    {str(key)} if str(key) in declared_source_ids else active_source_ids
                )
                if str(key) in declared_source_ids:
                    found.add(str(key))
                walk(child, child_path, map_source_ids)
        elif isinstance(value, list):
            for child in value:
                walk(child, f"{path}[]", inherited_source_ids)

    walk(payload, artifact_path, declared_source_ids)
    return found, url_references


def _provenance_rule_signature(
    references: list[ProvenanceUrlReference],
    *,
    declared_source_ids: set[str],
    source_url_rules: dict[str, tuple[SourceUrlRule, ...]],
    source_scope: str,
) -> str:
    """Hash registered rule bindings, never the refreshable descendant URL itself."""

    entries: set[str] = set()
    for reference in references:
        contextual_source_ids = set(reference.source_ids) or declared_source_ids
        restricted_route_match = any(
            rule.restricted
            and (
                reference.address.scheme,
                reference.address.host,
                reference.address.port,
            )
            == (
                rule.address.scheme,
                rule.address.host,
                rule.address.port,
            )
            and (
                reference.address.path == rule.address.path
                or reference.address.path.startswith(
                    rule.address.path.rstrip("/") + "/"
                )
                or reference.address.path.startswith(
                    rule.address.path.rstrip("/") + ";"
                )
            )
            for source_id in contextual_source_ids
            for rule in source_url_rules.get(source_id, ())
        )
        if source_scope == "approved_values" and restricted_route_match:
            raise PublicationError(
                "restricted catalog endpoint cannot be value provenance"
            )
        matches: list[tuple[str, SourceUrlRule]] = [
            (source_id, rule)
            for source_id in contextual_source_ids
            for rule in source_url_rules.get(source_id, ())
            if _url_matches_rule(reference.address, rule)
        ]
        if not contextual_source_ids or not matches:
            raise PublicationError(
                "embedded provenance URL is not registered for its declared source"
            )
        # Prefer an exact endpoint over a broader landing-page prefix, then the
        # longest registered prefix.  This makes the binding deterministic
        # when a source landing URL and one of its endpoints share an origin.
        matches.sort(
            key=lambda item: (
                item[1].allow_descendants,
                -len(item[1].address.path),
                -len(item[1].address.query),
                item[0],
                item[1].address.path,
                item[1].address.query,
            )
        )
        source_id, rule = matches[0]
        registered = rule.address
        binding = {
            "path": reference.path,
            "context_source_ids": sorted(contextual_source_ids),
            "matched_source_id": source_id,
            "rule": {
                "scheme": registered.scheme,
                "host": registered.host,
                "port": registered.port,
                "path": registered.path,
                "query": list(registered.query),
                "allow_descendants": rule.allow_descendants,
                "restricted": rule.restricted,
            },
        }
        encoded = json.dumps(
            binding,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        entries.add(hashlib.sha256(encoded).hexdigest())
    return hashlib.sha256("\n".join(sorted(entries)).encode("ascii")).hexdigest()


def _shape_signature(payload: Any, *, restricted_source_ids: set[str]) -> str:
    shapes: set[str] = set()

    def walk(value: Any, path: str, depth: int) -> tuple[int, int]:
        if depth > MAX_DEFAULT_DEPTH:
            raise PublicationError(f"payload exceeds depth {MAX_DEFAULT_DEPTH}: {path}")
        nodes = 1
        if value is None:
            kind = "null"
        elif isinstance(value, bool):
            kind = "boolean"
        elif isinstance(value, int):
            kind = "integer"
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise PublicationError(f"non-finite number: {path}")
            kind = "number"
        elif isinstance(value, str):
            kind = "string"
        elif isinstance(value, list):
            kind = "array"
            for child in value:
                child_nodes, _ = walk(child, f"{path}[]", depth + 1)
                nodes += child_nodes
        elif isinstance(value, dict):
            kind = "object"
            for key, child in value.items():
                child_path = _report_key_path(
                    path,
                    key,
                    restricted_source_ids=restricted_source_ids,
                ).replace(".", "/", 1)
                child_nodes, _ = walk(child, child_path, depth + 1)
                nodes += child_nodes
        else:
            raise PublicationError(f"unsupported JSON value at {path}")
        shapes.add(f"{path}:{kind}")
        if nodes > MAX_DEFAULT_NODES:
            raise PublicationError(f"payload exceeds {MAX_DEFAULT_NODES} nodes")
        return nodes, depth

    walk(payload, "$", 0)
    encoded = "\n".join(sorted(shapes)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _semantic_signature(payload: Any) -> str:
    """Hash meaning-bearing metadata without freezing ordinary record values.

    Province codes, names, coordinates, measures, and other observations are
    intentionally absent.  Only explicit unit/denominator/grain/status fields
    and geography *meaning* metadata participate.  A nearest non-personal
    record identifier is hashed into the entry so units/statuses cannot be
    silently swapped between otherwise stable records.
    """

    # A set deliberately ignores repeated rows carrying the same reviewed
    # semantics. Routine refreshes may add observations without changing what
    # their unit/status means.
    entries: set[str] = set()

    def context_for(value: dict[str, Any], inherited: str) -> str:
        identifiers: list[tuple[str, Any]] = []
        for key, child in value.items():
            normalised = _normalise_key(key)
            # Bind semantics only to stable semantic namespaces. Generic
            # record IDs must not make a count-only refresh look like a change
            # of meaning.
            is_identifier = normalised in {
                "dataset_key",
                "indicator_id",
                "indicator_key",
                "measure_id",
                "measure_key",
                "metric_id",
                "metric_key",
                "section_key",
                "source_id",
            }
            if is_identifier and not isinstance(child, (dict, list)) and child not in (None, ""):
                identifiers.append((normalised, child))
        if not identifiers:
            return inherited
        encoded = json.dumps(
            sorted(identifiers, key=lambda item: item[0]),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def is_semantic_key(key: str, *, geography_context: bool) -> bool:
        padded = f"_{key}_"
        generic_governance_key = not key.endswith(
            ("_count", "_label", "_name", "_rows", "_total", "_value")
        ) and any(f"_{token}_" in padded for token in GOVERNANCE_KEY_TOKENS)
        return (
            key in SEMANTIC_VALUE_KEYS
            or key.endswith(SEMANTIC_SUFFIXES)
            or generic_governance_key
            or (
                key.startswith(("geographic_", "geography_"))
                and key.endswith(("_level", "_meaning", "_scope"))
            )
            or (geography_context and key in GEOGRAPHY_CONTEXT_KEYS)
        )

    def is_governance_value(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        normalised = _normalise_key(value)
        padded = f"_{normalised}_"
        return (
            any(f"_{token}_" in padded for token in GOVERNANCE_VALUE_TOKENS)
            or any(token in value for token in ("ทดลอง", "ต้องตรวจ", "รับรอง"))
        )

    def walk(value: Any, path: str, context: str, geography_context: bool) -> None:
        if isinstance(value, dict):
            local_context = context_for(value, context)
            normalised_keys = {_normalise_key(key) for key in value}
            geometry_object = bool(
                normalised_keys.intersection({"coordinates", "geometries"})
            )
            for key, child in value.items():
                normalised = _normalise_key(key)
                segment = (
                    normalised
                    if SAFE_REPORT_KEY_RE.fullmatch(str(key)) is not None
                    else "<map-key>"
                )
                child_path = f"{path}/{segment}"
                child_geography_context = geography_context or normalised in {
                    "geographic_semantics",
                    "geography",
                    "geography_semantics",
                }
                if is_semantic_key(
                    normalised,
                    geography_context=geography_context,
                ) or (geometry_object and normalised == "type") or is_governance_value(
                    child
                ):
                    canonical_value = json.dumps(
                        child,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    entry = b"\0".join(
                        (
                            child_path.encode("utf-8"),
                            local_context.encode("ascii"),
                            canonical_value,
                        )
                    )
                    entries.add(hashlib.sha256(entry).hexdigest())
                walk(child, child_path, local_context, child_geography_context)
        elif isinstance(value, list):
            for child in value:
                walk(child, f"{path}[]", context, geography_context)

    walk(payload, "$", "", False)
    return hashlib.sha256("\n".join(sorted(entries)).encode("ascii")).hexdigest()


def _record_temporal_values(record: Any) -> dict[str, str | None]:
    """Collect nested as-of fields without exposing their paths or values.

    The map is kept only in memory for a base/head comparison.  Stable array
    positions are included in the path digest as a fail-closed fallback when a
    nested object does not publish its own identity.
    """

    values: dict[str, str | None] = {}

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalised = _normalise_key(key)
                child_path = f"{path}/{normalised}"
                if normalised in TEMPORAL_VALUE_KEYS or normalised.endswith("_as_of"):
                    slot = hashlib.sha256(child_path.encode("utf-8")).hexdigest()
                    parsed = _parse_datetime(child)
                    values[slot] = parsed.isoformat() if parsed is not None else None
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(record, "$")
    return values


def _geojson_number(value: Any, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PublicationError(f"GeoJSON coordinate must be a number at {path}")
    if isinstance(value, float) and not math.isfinite(value):
        raise PublicationError(f"GeoJSON coordinate must be finite at {path}")


def _geojson_position(value: Any, path: str) -> None:
    if not isinstance(value, list) or len(value) < 2:
        raise PublicationError(
            f"GeoJSON position must contain longitude and latitude at {path}"
        )
    for index, coordinate in enumerate(value):
        _geojson_number(coordinate, f"{path}[{index}]")
    if not -180 <= value[0] <= 180:
        raise PublicationError(f"GeoJSON longitude is outside WGS84 range at {path}[0]")
    if not -90 <= value[1] <= 90:
        raise PublicationError(f"GeoJSON latitude is outside WGS84 range at {path}[1]")


def _geojson_line(value: Any, path: str, *, linear_ring: bool = False) -> None:
    minimum = 4 if linear_ring else 2
    label = "linear ring" if linear_ring else "line string"
    if not isinstance(value, list) or len(value) < minimum:
        raise PublicationError(
            f"GeoJSON {label} must contain at least {minimum} positions at {path}"
        )
    for index, position in enumerate(value):
        _geojson_position(position, f"{path}[{index}]")
    if linear_ring and value[0] != value[-1]:
        raise PublicationError(f"GeoJSON linear ring must be closed at {path}")


def _geojson_array(value: Any, path: str, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise PublicationError(f"GeoJSON {label} must be an array at {path}")
    return value


def _validate_geojson_bbox(value: Any, path: str) -> None:
    bbox = _geojson_array(value, path, "bbox")
    if len(bbox) < 4 or len(bbox) % 2:
        raise PublicationError(
            f"GeoJSON bbox must contain two positions of equal dimension at {path}"
        )
    for index, coordinate in enumerate(bbox):
        _geojson_number(coordinate, f"{path}[{index}]")
    dimensions = len(bbox) // 2
    for index in (0, dimensions):
        if not -180 <= bbox[index] <= 180:
            raise PublicationError(
                f"GeoJSON bbox longitude is outside WGS84 range at {path}[{index}]"
            )
    for index in (1, dimensions + 1):
        if not -90 <= bbox[index] <= 90:
            raise PublicationError(
                f"GeoJSON bbox latitude is outside WGS84 range at {path}[{index}]"
            )


def _validate_geojson_geometry(value: Any, path: str, depth: int = 0) -> None:
    if depth > MAX_DEFAULT_DEPTH:
        raise PublicationError(f"GeoJSON geometry exceeds maximum depth at {path}")
    if not isinstance(value, dict):
        raise PublicationError(f"GeoJSON geometry must be an object at {path}")
    if "bbox" in value:
        _validate_geojson_bbox(value["bbox"], f"{path}.bbox")

    geometry_type = value.get("type")
    if geometry_type == "GeometryCollection":
        if "coordinates" in value:
            raise PublicationError(
                f"GeoJSON GeometryCollection must not contain coordinates at {path}"
            )
        geometries = _geojson_array(
            value.get("geometries"), f"{path}.geometries", "geometries"
        )
        for index, geometry in enumerate(geometries):
            _validate_geojson_geometry(
                geometry, f"{path}.geometries[{index}]", depth + 1
            )
        return

    if not isinstance(geometry_type, str) or geometry_type not in (
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
    ):
        raise PublicationError(f"GeoJSON geometry type is unsupported at {path}")
    if "geometries" in value:
        raise PublicationError(f"GeoJSON geometry must not contain geometries at {path}")
    if "coordinates" not in value:
        raise PublicationError(f"GeoJSON geometry is missing coordinates at {path}")
    coordinates = value["coordinates"]
    coordinate_path = f"{path}.coordinates"

    if geometry_type == "Point":
        _geojson_position(coordinates, coordinate_path)
    elif geometry_type == "MultiPoint":
        for index, position in enumerate(
            _geojson_array(coordinates, coordinate_path, "MultiPoint coordinates")
        ):
            _geojson_position(position, f"{coordinate_path}[{index}]")
    elif geometry_type == "LineString":
        _geojson_line(coordinates, coordinate_path)
    elif geometry_type == "MultiLineString":
        for index, line in enumerate(
            _geojson_array(coordinates, coordinate_path, "MultiLineString coordinates")
        ):
            _geojson_line(line, f"{coordinate_path}[{index}]")
    elif geometry_type == "Polygon":
        for index, ring in enumerate(
            _geojson_array(coordinates, coordinate_path, "Polygon coordinates")
        ):
            _geojson_line(ring, f"{coordinate_path}[{index}]", linear_ring=True)
    else:
        for polygon_index, polygon in enumerate(
            _geojson_array(coordinates, coordinate_path, "MultiPolygon coordinates")
        ):
            polygon_path = f"{coordinate_path}[{polygon_index}]"
            for ring_index, ring in enumerate(
                _geojson_array(polygon, polygon_path, "Polygon coordinates")
            ):
                _geojson_line(
                    ring,
                    f"{polygon_path}[{ring_index}]",
                    linear_ring=True,
                )


def _validate_geojson(payload: Any) -> None:
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise PublicationError("GeoJSON root must be a FeatureCollection")
    if "bbox" in payload:
        _validate_geojson_bbox(payload["bbox"], "$.bbox")
    features = _geojson_array(payload.get("features"), "$.features", "features")
    for index, feature in enumerate(features):
        feature_path = f"$.features[{index}]"
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise PublicationError(f"GeoJSON feature must be a Feature object at {feature_path}")
        if "bbox" in feature:
            _validate_geojson_bbox(feature["bbox"], f"{feature_path}.bbox")
        if "geometry" not in feature:
            raise PublicationError(f"GeoJSON feature is missing geometry at {feature_path}")
        geometry = feature["geometry"]
        if geometry is not None:
            _validate_geojson_geometry(geometry, f"{feature_path}.geometry")
        if "properties" not in feature or (
            feature["properties"] is not None
            and not isinstance(feature["properties"], dict)
        ):
            raise PublicationError(
                f"GeoJSON feature properties must be an object or null at {feature_path}"
            )
        if "id" in feature:
            feature_id = feature["id"]
            if (
                isinstance(feature_id, bool)
                or not isinstance(feature_id, (str, int, float))
                or (isinstance(feature_id, float) and not math.isfinite(feature_id))
            ):
                raise PublicationError(
                    f"GeoJSON feature id must be a finite number or string at {feature_path}"
                )


def _pointer(payload: Any, pointer: str) -> Any:
    if pointer in ("", "/", "$", None):
        return payload
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise PublicationError(f"records_pointer must be a JSON pointer: {pointer}")
    current = payload
    for raw_part in pointer.split("/")[1:]:
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise PublicationError(f"records_pointer not found: {pointer}")
    return current


def _field(record: Any, field_path: str, map_key: str | None) -> Any:
    if field_path == "$key":
        return map_key
    if field_path == "$artifact":
        return "artifact"
    current = record
    for part in field_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _records(payload: Any, pointer: str) -> list[tuple[str | None, Any]]:
    selected = _pointer(payload, pointer)
    if pointer in ("", "/", "$"):
        if isinstance(selected, list):
            return [(None, item) for item in selected]
        return [(None, selected)]
    if isinstance(selected, list):
        return [(None, item) for item in selected]
    if isinstance(selected, dict):
        return [(str(key), item) for key, item in selected.items()]
    raise PublicationError(f"records_pointer must resolve to an array or object: {pointer}")


def _completeness_summary(payload: Any, output: dict[str, Any]) -> dict[str, int]:
    """Execute trusted secondary collection-count rules for one output."""

    counts: dict[str, int] = {}
    for rule in output.get("completeness_rules", []):
        pointer = rule["pointer"]
        selected = _pointer(payload, pointer)
        if not isinstance(selected, (list, dict)):
            raise PublicationError(
                f"completeness pointer must resolve to an array or object: {pointer}"
            )
        count = len(selected)
        expected = rule.get("expected_count")
        minimum = rule.get("minimum_count")
        if expected is not None and count != expected:
            raise PublicationError(
                f"completeness count {count} does not equal expected_count at {pointer}"
            )
        if minimum is not None and count < minimum:
            raise PublicationError(
                f"completeness count {count} is below minimum_count at {pointer}"
            )
        rule_key = hashlib.sha256(pointer.encode("utf-8")).hexdigest()
        counts[rule_key] = count
    return counts


def _record_summary(
    payload: Any,
    output: dict[str, Any],
    *,
    restricted_source_ids: set[str],
) -> dict[str, Any]:
    pointer = output.get("records_pointer")
    if pointer is None:
        return {
            "count": None,
            "identity_hash": None,
            "_identity_digests": None,
            "_record_schema_digests": None,
            "_record_semantic_digests": None,
            "_record_as_of_values": None,
        }
    records = _records(payload, pointer)
    identities: set[str] = set()
    record_schemas: dict[str, str] = {}
    record_semantics: dict[str, str] = {}
    record_as_of_values: dict[str, dict[str, str | None]] = {}
    fields = output.get("identity_fields", [])
    if not fields:
        raise PublicationError("identity_fields is required when records_pointer is present")
    for map_key, record in records:
        values = [_field(record, field, map_key) for field in fields]
        if any(value in (None, "") or isinstance(value, (dict, list)) for value in values):
            raise PublicationError(f"record identity is missing for fields {fields}")
        encoded = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        if digest in identities:
            raise PublicationError(f"duplicate record identity for fields {fields}")
        identities.add(digest)
        record_schemas[digest] = _shape_signature(
            record,
            restricted_source_ids=restricted_source_ids,
        )
        record_semantics[digest] = _semantic_signature(record)
        record_as_of_values[digest] = _record_temporal_values(record)
    count = len(records)
    expected = output.get("expected_count")
    minimum = output.get("minimum_count", 1)
    if expected is not None and count != expected:
        raise PublicationError(f"record count {count} does not equal expected_count {expected}")
    if count < minimum:
        raise PublicationError(f"record count {count} is below minimum_count {minimum}")
    as_of: str | None = None
    as_of_pointer = output.get("as_of_pointer")
    if as_of_pointer is not None:
        raw_as_of = _pointer(payload, as_of_pointer)
        parsed_as_of = _parse_datetime(raw_as_of)
        if parsed_as_of is None:
            raise PublicationError(f"as_of_pointer is missing or not ISO-8601: {as_of_pointer}")
        as_of = parsed_as_of.isoformat()
    return {
        "count": count,
        "identity_hash": hashlib.sha256("\n".join(sorted(identities)).encode()).hexdigest(),
        # Kept only in-memory for Jaccard churn calculation. Reports expose the
        # aggregate hash and ratio, never source identity values or per-row hashes.
        "_identity_digests": tuple(sorted(identities)),
        "_record_schema_digests": record_schemas,
        "_record_semantic_digests": record_semantics,
        "_record_as_of_values": record_as_of_values,
        "as_of": as_of,
    }


def _csv_payload(
    data: bytes,
    output: dict[str, Any],
    path: str,
    *,
    restricted_source_ids: set[str],
) -> tuple[list[dict[str, str]], str]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PublicationError(f"{path} is not UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text), strict=True)
    headers = reader.fieldnames or []
    if len(headers) != len(set(headers)):
        raise PublicationError(f"duplicate CSV header in {path}")
    expected_headers = output.get("headers")
    if expected_headers is not None and headers != expected_headers:
        raise PublicationError(f"CSV headers changed in {path}")
    rows = list(reader)
    if any(None in row for row in rows):
        raise PublicationError(f"CSV row has extra cells in {path}")
    for row_index, row in enumerate(rows, start=2):
        for header, value in row.items():
            column_path = _report_key_path(
                "column",
                header,
                restricted_source_ids=restricted_source_ids,
            )
            if not isinstance(value, str):
                raise PublicationError(
                    f"CSV cell is missing at row {row_index}, {column_path}"
                )
            normalised = value.lstrip("\ufeff \t\r\n\v\f")
            if normalised.startswith(("=", "@")) or (
                normalised.startswith(("+", "-"))
                and NUMERIC_CELL_RE.fullmatch(normalised) is None
            ):
                raise PublicationError(
                    f"spreadsheet formula-like cell at row {row_index}, {column_path}"
                )
    signature = hashlib.sha256(
        json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return rows, signature


def _validate_contract(contract: dict[str, Any], path: Path) -> None:
    required = {
        "contract_version",
        "contract_id",
        "dataset_key",
        "source_scope",
        "source_ids",
        "builder",
        "grain_th",
        "identity",
        "geography",
        "as_of",
        "measures",
        "completeness",
        "privacy_profile",
        "outputs",
    }
    unknown = set(contract) - required
    missing = required - set(contract)
    if unknown or missing:
        raise PublicationError(
            f"invalid contract fields in {path.name}: missing={sorted(missing)}, "
            f"unknown={sorted(unknown)}"
        )
    if contract["contract_version"] != CONTRACT_VERSION:
        raise PublicationError(f"{path.name} must use contract_version {CONTRACT_VERSION}")
    for key in ("contract_id", "dataset_key"):
        if not isinstance(contract[key], str) or not SAFE_ID_RE.fullmatch(contract[key]):
            raise PublicationError(f"{path.name}.{key} must be a safe id")
    if contract["source_scope"] not in {
        "approved_values",
        "catalog_metadata",
        "reference_geography",
    }:
        raise PublicationError(f"invalid source_scope in {path.name}")
    source_ids = contract["source_ids"]
    if not isinstance(source_ids, list) or any(
        not isinstance(value, str) or not SAFE_SOURCE_ID_RE.fullmatch(value)
        for value in source_ids
    ):
        raise PublicationError(f"invalid source_ids in {path.name}")
    if len(source_ids) != len(set(source_ids)):
        raise PublicationError(f"duplicate source_ids in {path.name}")
    if contract["source_scope"] != "reference_geography" and not source_ids:
        raise PublicationError(f"source_ids is required in {path.name}")
    for text_key in ("builder", "grain_th"):
        if not isinstance(contract[text_key], str) or not contract[text_key].strip():
            raise PublicationError(f"{path.name}.{text_key} must be non-empty")
    for object_key in ("identity", "geography", "as_of", "completeness"):
        if not isinstance(contract[object_key], dict) or not contract[object_key]:
            raise PublicationError(f"{path.name}.{object_key} must be a non-empty object")
    completeness = contract["completeness"]
    completeness_allowed = {"policy", "needs_review", "review_items"}
    if set(completeness) - completeness_allowed:
        raise PublicationError(f"unexpected completeness fields in {path.name}")
    if completeness.get("policy") != "output_contracts":
        raise PublicationError(f"{path.name}.completeness policy must be output_contracts")
    if "needs_review" in completeness and type(completeness["needs_review"]) is not bool:
        raise PublicationError(f"{path.name}.completeness.needs_review must be boolean")
    review_items = completeness.get("review_items", [])
    if (
        not isinstance(review_items, list)
        or any(not isinstance(item, str) or not item.strip() for item in review_items)
        or len(review_items) != len(set(review_items))
    ):
        raise PublicationError(f"{path.name}.completeness.review_items is invalid")
    measures = contract["measures"]
    if not isinstance(measures, list) or not measures:
        raise PublicationError(f"{path.name}.measures must be non-empty")
    for measure in measures:
        if not isinstance(measure, dict) or set(measure) != {"name", "unit", "denominator"}:
            raise PublicationError(f"invalid measure semantics in {path.name}")
        if any(not isinstance(measure[key], str) or not measure[key].strip() for key in measure):
            raise PublicationError(f"blank measure semantics in {path.name}")
    if contract["privacy_profile"] not in ALLOWED_PRIVACY_PROFILES:
        raise PublicationError(f"invalid privacy_profile in {path.name}")
    outputs = contract["outputs"]
    if not isinstance(outputs, list) or not outputs:
        raise PublicationError(f"{path.name}.outputs must be non-empty")
    for index, output in enumerate(outputs):
        if not isinstance(output, dict):
            raise PublicationError(f"{path.name}.outputs[{index}] must be an object")
        if ("path" in output) == ("path_glob" in output):
            raise PublicationError(f"{path.name}.outputs[{index}] needs path or path_glob")
        allowed = {
            "path",
            "path_glob",
            "expected_files",
            "format",
            "role",
            "downloadable",
            "max_bytes",
            "records_pointer",
            "identity_fields",
            "expected_count",
            "minimum_count",
            "max_count_drop_ratio",
            "max_count_increase_ratio",
            "max_identity_churn_ratio",
            "as_of_pointer",
            "headers",
            "completeness_rules",
            "schema_policy",
        }
        extra = set(output) - allowed
        if extra:
            raise PublicationError(f"unexpected output fields in {path.name}: {sorted(extra)}")
        selector = output.get("path", output.get("path_glob"))
        if not isinstance(selector, str) or not SAFE_PUBLIC_PATH_RE.fullmatch(selector):
            raise PublicationError(f"unsafe public path selector in {path.name}: {selector}")
        if ".." in PurePosixPath(selector).parts or not selector.startswith(PUBLIC_PREFIX):
            raise PublicationError(f"public path escapes data/public in {path.name}")
        if output.get("format") not in ALLOWED_FORMATS:
            raise PublicationError(f"invalid output format in {path.name}")
        if output.get("role") not in ALLOWED_ROLES:
            raise PublicationError(f"invalid output role in {path.name}")
        if type(output.get("downloadable")) is not bool:
            raise PublicationError(f"downloadable must be boolean in {path.name}")
        max_bytes = output.get("max_bytes")
        if type(max_bytes) is not int or max_bytes < 1 or max_bytes > MAX_DEFAULT_FILE_BYTES:
            raise PublicationError(f"invalid max_bytes in {path.name}")
        if output.get("schema_policy") != "stable":
            raise PublicationError(f"schema_policy must be stable in {path.name}")
        for number_key in ("expected_files", "expected_count", "minimum_count"):
            if number_key in output and (
                type(output[number_key]) is not int or output[number_key] < 0
            ):
                raise PublicationError(f"invalid {number_key} in {path.name}")
        for ratio_key in ("max_count_drop_ratio", "max_count_increase_ratio"):
            if ratio_key in output and (
                not isinstance(output[ratio_key], (int, float))
                or isinstance(output[ratio_key], bool)
                or not 0 <= float(output[ratio_key]) <= 10
            ):
                raise PublicationError(f"invalid {ratio_key} in {path.name}")
        has_records = "records_pointer" in output
        has_identity_limit = "max_identity_churn_ratio" in output
        if has_records != has_identity_limit:
            raise PublicationError(
                f"{path.name}.outputs[{index}] must pair records_pointer with "
                "max_identity_churn_ratio"
            )
        if has_identity_limit and (
            not isinstance(output["max_identity_churn_ratio"], (int, float))
            or isinstance(output["max_identity_churn_ratio"], bool)
            or not 0 <= float(output["max_identity_churn_ratio"]) <= 1
        ):
            raise PublicationError(f"invalid max_identity_churn_ratio in {path.name}")
        completeness_rules = output.get("completeness_rules", [])
        if not isinstance(completeness_rules, list):
            raise PublicationError(f"completeness_rules must be an array in {path.name}")
        seen_pointers: set[str] = set()
        for rule_index, rule in enumerate(completeness_rules):
            if not isinstance(rule, dict):
                raise PublicationError(
                    f"{path.name}.outputs[{index}].completeness_rules[{rule_index}] "
                    "must be an object"
                )
            rule_allowed = {
                "pointer",
                "expected_count",
                "minimum_count",
                "max_count_drop_ratio",
                "max_count_increase_ratio",
            }
            if set(rule) - rule_allowed:
                raise PublicationError(f"unexpected completeness rule fields in {path.name}")
            pointer = rule.get("pointer")
            if (
                not isinstance(pointer, str)
                or pointer not in {"$", "/"}
                and not pointer.startswith("/")
                or pointer in seen_pointers
            ):
                raise PublicationError(f"invalid completeness rule pointer in {path.name}")
            seen_pointers.add(pointer)
            if "expected_count" not in rule and "minimum_count" not in rule:
                raise PublicationError(
                    f"completeness rule needs expected_count or minimum_count in {path.name}"
                )
            for number_key in ("expected_count", "minimum_count"):
                if number_key in rule and (
                    type(rule[number_key]) is not int or rule[number_key] < 0
                ):
                    raise PublicationError(f"invalid completeness {number_key} in {path.name}")
            for ratio_key in ("max_count_drop_ratio", "max_count_increase_ratio"):
                if ratio_key in rule and (
                    not isinstance(rule[ratio_key], (int, float))
                    or isinstance(rule[ratio_key], bool)
                    or not 0 <= float(rule[ratio_key]) <= 10
                ):
                    raise PublicationError(f"invalid completeness {ratio_key} in {path.name}")


def load_contracts(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    paths = sorted(root.glob("*.json"))
    if not paths:
        raise PublicationError(f"no publication contracts found under {root}")
    contracts: list[tuple[Path, dict[str, Any]]] = []
    ids: set[str] = set()
    for path in paths:
        contract = _read_json_file(path)
        _validate_contract(contract, path)
        contract_id = contract["contract_id"]
        if contract_id in ids:
            raise PublicationError(f"duplicate publication contract_id: {contract_id}")
        ids.add(contract_id)
        contracts.append((path, contract))
    return contracts


def _catalog_sets(
    catalog_path: Path,
) -> tuple[
    set[str],
    set[str],
    set[str],
    dict[str, tuple[SourceUrlRule, ...]],
]:
    catalog = _read_json_file(catalog_path)
    sources = catalog.get("sources")
    if not isinstance(sources, list):
        raise PublicationError("source catalog has no sources array")
    all_ids: set[str] = set()
    approved: set[str] = set()
    restricted: set[str] = set()
    url_rules: dict[str, tuple[SourceUrlRule, ...]] = {}
    for item in sources:
        if not isinstance(item, dict):
            raise PublicationError("source catalog entries must be objects")
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or not SAFE_SOURCE_ID_RE.fullmatch(source_id):
            raise PublicationError("source catalog entry has an invalid source_id")
        if source_id in all_ids:
            raise PublicationError("source catalog has a duplicate source_id")
        all_ids.add(source_id)
        if (
            item.get("production_values_allowed") is True
            and item.get("cloud_policy") == "team_approved_public"
        ):
            approved.add(source_id)
        if item.get("cloud_policy") == "restricted_local_only":
            restricted.add(source_id)

        source_url = item.get("url")
        if not isinstance(source_url, str):
            raise PublicationError("source catalog entry has no canonical URL")
        rules = [SourceUrlRule(_canonical_url(source_url, catalog=True), True)]
        endpoints = item.get("endpoints", [])
        if not isinstance(endpoints, list):
            raise PublicationError("source catalog endpoints must be an array")
        for endpoint in endpoints:
            if not isinstance(endpoint, dict) or not isinstance(endpoint.get("url"), str):
                raise PublicationError("source catalog endpoint has no canonical URL")
            rules.append(
                SourceUrlRule(
                    _canonical_url(endpoint["url"], catalog=True),
                    False,
                    endpoint.get("restricted") is True,
                )
            )
        url_rules[source_id] = tuple(rules)
    return all_ids, approved, restricted, url_rules


def _contract_hash(path: Path) -> str:
    return hashlib.sha256(_canonical_text_bytes(path.read_bytes())).hexdigest()


def _canonical_text_bytes(data: bytes) -> bytes:
    """Hash repository text identically on Windows and Linux checkouts."""

    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _matches(path: str, selector: str) -> bool:
    return fnmatch.fnmatchcase(path, selector)


def bind_outputs(
    paths: Iterable[str],
    contracts: list[tuple[Path, dict[str, Any]]],
) -> dict[str, OutputBinding]:
    available = sorted(paths)
    bindings: dict[str, OutputBinding] = {}
    for contract_path, contract in contracts:
        for output in contract["outputs"]:
            selector = output.get("path", output.get("path_glob"))
            matched = [path for path in available if _matches(path, selector)]
            if "path" in output and matched != [selector]:
                raise PublicationError(f"required publication output is missing: {selector}")
            expected_files = output.get("expected_files")
            if expected_files is not None and len(matched) != expected_files:
                raise PublicationError(
                    f"{selector} matched {len(matched)} files; expected {expected_files}"
                )
            if not matched:
                raise PublicationError(f"publication selector matched no files: {selector}")
            for path in matched:
                if path in bindings:
                    raise PublicationError(f"publication output has two contracts: {path}")
                bindings[path] = OutputBinding(contract_path, contract, output)
    return bindings


def snapshot_from_workspace(root: Path) -> dict[str, FileEntry]:
    public_root = root / "data" / "public"
    entries: dict[str, FileEntry] = {}
    for path in sorted(public_root.rglob("*")):
        if not path.is_file() and not path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries[relative] = FileEntry(relative, b"", mode="120000")
        else:
            entries[relative] = FileEntry(relative, path.read_bytes())
    return entries


@lru_cache(maxsize=8)
def downloadable_public_files(
    root: Path,
    contracts_root: Path,
) -> dict[str, Path]:
    """Return only contract-declared browser downloads.

    This intentionally does not expose provenance, receipts, serving policy, or
    a future orphan file merely because it happens to live in data/public.
    """

    public_root = (root / "data" / "public").resolve()
    paths = {
        path.relative_to(root).as_posix()
        for path in public_root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    contracts = load_contracts(contracts_root)
    bindings = bind_outputs(paths - PUBLICATION_CONTROL_PATHS, contracts)
    result: dict[str, Path] = {}
    for repository_path, binding in bindings.items():
        if binding.output["downloadable"] is not True:
            continue
        local_path = (root / repository_path).resolve()
        if public_root not in local_path.parents:
            raise PublicationError(f"download path escapes data/public: {repository_path}")
        relative = local_path.relative_to(public_root).as_posix()
        result[relative] = local_path
    return result


def _git(repository: Path, args: list[str]) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repository,
        check=False,
        capture_output=True,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise PublicationError(f"git {' '.join(args[:2])} failed: {detail}")
    return result.stdout


def snapshot_from_git(repository: Path, sha: str) -> tuple[dict[str, FileEntry], dict[str, str]]:
    if not SHA_RE.fullmatch(sha):
        raise PublicationError(f"invalid git SHA: {sha}")
    raw = _git(repository, ["ls-tree", "-r", "-z", "--full-tree", sha])
    tree: dict[str, str] = {}
    public_meta: dict[str, tuple[str, str]] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8")
        tree[path] = f"{mode}:{kind}:{object_id}"
        if path.startswith(PUBLIC_PREFIX):
            public_meta[path] = (mode, kind)
    entries: dict[str, FileEntry] = {}
    for path, (mode, kind) in public_meta.items():
        if kind != "blob":
            entries[path] = FileEntry(path, b"", mode=mode)
            continue
        data = _git(repository, ["show", f"{sha}:{path}"])
        entries[path] = FileEntry(path, data, mode=mode)
    return entries, tree


def _receipt_entries(
    entries: dict[str, FileEntry],
    bindings: dict[str, OutputBinding],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted(bindings):
        item = entries[path]
        binding = bindings[path]
        canonical = _canonical_text_bytes(item.data)
        result.append(
            {
                "path": path,
                "contract_id": binding.contract["contract_id"],
                "dataset_key": binding.contract["dataset_key"],
                "role": binding.output["role"],
                "format": binding.output["format"],
                "bytes": len(canonical),
                "sha256": hashlib.sha256(canonical).hexdigest(),
                "contract_sha256": _contract_hash(binding.contract_path),
            }
        )
    return result


def build_receipt(
    root: Path,
    contracts_root: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    entries = snapshot_from_workspace(root)
    contracts = load_contracts(contracts_root)
    _validate_contract_sources(contracts, catalog_path)
    data_paths = set(entries) - PUBLICATION_CONTROL_PATHS
    bindings = bind_outputs(data_paths, contracts)
    unclassified = sorted(data_paths - set(bindings))
    if unclassified:
        raise PublicationError(f"unclassified public files: {unclassified}")
    artifacts = _receipt_entries(entries, bindings)
    digest = hashlib.sha256(
        json.dumps(artifacts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return {
        "receipt_version": RECEIPT_VERSION,
        "release_digest": digest,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def write_receipt(
    root: Path,
    contracts_root: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    receipt = build_receipt(root, contracts_root, catalog_path)
    path = root / RECEIPT_PATH
    path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return receipt


def _validate_contract_sources(
    contracts: list[tuple[Path, dict[str, Any]]], catalog_path: Path
) -> tuple[set[str], set[str], dict[str, tuple[SourceUrlRule, ...]]]:
    all_ids, approved, restricted, url_rules = _catalog_sets(catalog_path)
    for path, contract in contracts:
        ids = set(contract["source_ids"])
        unknown = ids - all_ids
        if unknown:
            raise PublicationError(f"unknown source_ids in {path.name}: {sorted(unknown)}")
        if contract["source_scope"] == "approved_values":
            disallowed = ids - approved
            if disallowed:
                raise PublicationError(
                    f"non-approved value sources in {path.name}: {sorted(disallowed)}"
                )
    return approved, restricted, url_rules


def _validate_receipt(
    entries: dict[str, FileEntry], bindings: dict[str, OutputBinding]
) -> None:
    receipt_entry = entries.get(RECEIPT_PATH)
    if receipt_entry is None:
        raise PublicationError(f"missing {RECEIPT_PATH}")
    receipt = load_json_bytes(receipt_entry.data, path=RECEIPT_PATH)
    if not isinstance(receipt, dict) or set(receipt) != {
        "receipt_version",
        "release_digest",
        "artifact_count",
        "artifacts",
    }:
        raise PublicationError("publication receipt fields are invalid")
    if receipt.get("receipt_version") != RECEIPT_VERSION:
        raise PublicationError(f"publication receipt must use version {RECEIPT_VERSION}")
    expected = _receipt_entries(entries, bindings)
    if receipt.get("artifact_count") != len(expected) or receipt.get("artifacts") != expected:
        raise PublicationError("publication receipt does not match public files/contracts")
    digest = hashlib.sha256(
        json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    if receipt.get("release_digest") != digest:
        raise PublicationError("publication receipt release_digest mismatch")


def _validate_serving_manifest(
    entries: dict[str, FileEntry],
    bindings: dict[str, OutputBinding],
) -> None:
    manifest_entry = entries.get(SERVING_MANIFEST_PATH)
    if manifest_entry is None:
        raise PublicationError(f"missing {SERVING_MANIFEST_PATH}")
    manifest = load_json_bytes(manifest_entry.data, path=SERVING_MANIFEST_PATH)
    if not isinstance(manifest, dict) or set(manifest) != {"manifest_version", "artifacts"}:
        raise PublicationError("serving manifest fields are invalid")
    if manifest.get("manifest_version") != "1.0":
        raise PublicationError("serving manifest must use version 1.0")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise PublicationError("serving manifest artifacts must be non-empty")
    public_paths = set(entries)
    serving_paths: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise PublicationError(f"serving manifest artifacts[{index}] must be an object")
        has_path = "path" in artifact
        has_glob = "path_glob" in artifact
        if has_path == has_glob:
            raise PublicationError(
                f"serving manifest artifacts[{index}] must use path or path_glob"
            )
        selector = artifact.get("path", artifact.get("path_glob"))
        if not isinstance(selector, str):
            raise PublicationError(f"invalid serving selector at artifacts[{index}]")
        repository_selector = f"{PUBLIC_PREFIX}{selector}"
        if ".." in PurePosixPath(repository_selector).parts:
            raise PublicationError(f"serving selector escapes data/public: {selector}")
        matched = sorted(path for path in public_paths if _matches(path, repository_selector))
        if has_path and matched != [repository_selector]:
            raise PublicationError(f"serving artifact is missing: {selector}")
        expected_count = artifact.get("expected_count")
        if has_glob and (type(expected_count) is not int or len(matched) != expected_count):
            raise PublicationError(
                f"serving glob {selector} matched {len(matched)}; expected {expected_count}"
            )
        for path in matched:
            if path in serving_paths:
                raise PublicationError(f"duplicate serving artifact path: {path}")
            serving_paths.add(path)
    database_paths = {
        path for path, binding in bindings.items() if binding.output["role"] == "database"
    }
    if serving_paths != database_paths:
        missing_contract = sorted(serving_paths - database_paths)
        missing_serving = sorted(database_paths - serving_paths)
        raise PublicationError(
            "serving/contract database paths differ: "
            f"without_database_contract={missing_contract}, not_served={missing_serving}"
        )


def _validate_snapshot(
    entries: dict[str, FileEntry],
    contracts: list[tuple[Path, dict[str, Any]]],
    catalog_path: Path,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    _, restricted, source_url_rules = _validate_contract_sources(contracts, catalog_path)
    problems: list[str] = []
    if sum(len(entry.data) for entry in entries.values()) > MAX_DEFAULT_TOTAL_BYTES:
        problems.append(f"{PUBLIC_PREFIX}: total bytes exceed {MAX_DEFAULT_TOTAL_BYTES}")
    for path, entry in entries.items():
        if entry.mode != "100644":
            problems.append(f"{path}: git mode must be 100644")
        if not SAFE_PUBLIC_PATH_RE.fullmatch(path):
            problems.append(f"{path}: unsafe or unsupported public filename")
        if entry.data.startswith(b"version https://git-lfs.github.com/spec/v1"):
            problems.append(f"{path}: Git LFS pointer is not a publication artifact")

    data_paths = set(entries) - PUBLICATION_CONTROL_PATHS
    bindings = bind_outputs(data_paths, contracts)
    unclassified = sorted(data_paths - set(bindings))
    if unclassified:
        problems.extend(f"{path}: no trusted publication contract" for path in unclassified)
    summaries: dict[str, dict[str, Any]] = {}
    for path, binding in sorted(bindings.items()):
        entry = entries[path]
        output = binding.output
        if len(entry.data) > output["max_bytes"]:
            problems.append(f"{path}: exceeds contract max_bytes")
            continue
        if b"\x00" in entry.data:
            problems.append(f"{path}: binary/NUL payload is not allowed")
            continue
        try:
            if output["format"] in {"json", "geojson"}:
                payload = load_json_bytes(entry.data, path=path)
                if not isinstance(payload, dict):
                    raise PublicationError(f"{path} must contain a JSON object")
                privacy = _privacy_problems(
                    payload,
                    artifact_path=path,
                    restricted_source_ids=restricted,
                    profile=binding.contract["privacy_profile"],
                )
                problems.extend(privacy)
                if output["format"] == "geojson":
                    _validate_geojson(payload)
                schema_hash = _shape_signature(
                    payload,
                    restricted_source_ids=restricted,
                )
                record_summary = _record_summary(
                    payload,
                    output,
                    restricted_source_ids=restricted,
                )
            else:
                rows, schema_hash = _csv_payload(
                    entry.data,
                    output,
                    path,
                    restricted_source_ids=restricted,
                )
                privacy = _privacy_problems(
                    rows,
                    artifact_path=path,
                    restricted_source_ids=restricted,
                    profile=binding.contract["privacy_profile"],
                )
                problems.extend(privacy)
                record_summary = _record_summary(
                    rows,
                    output,
                    restricted_source_ids=restricted,
                )
                payload = rows
            completeness_counts = _completeness_summary(payload, output)
            semantic_hash = _semantic_signature(payload)
            declared_source_ids = set(binding.contract["source_ids"])
            embedded_source_ids, source_urls = _embedded_source_provenance(
                payload,
                artifact_path=path,
                declared_source_ids=declared_source_ids,
                restricted_source_ids=restricted,
            )
            if not embedded_source_ids.issubset(declared_source_ids):
                raise PublicationError(
                    "embedded source provenance is not declared by its publication contract"
                )
            provenance_hash = _provenance_rule_signature(
                source_urls,
                declared_source_ids=declared_source_ids,
                source_url_rules=source_url_rules,
                source_scope=binding.contract["source_scope"],
            )
            canonical = _canonical_text_bytes(entry.data)
            summaries[path] = {
                "path": path,
                "contract_id": binding.contract["contract_id"],
                "bytes": len(canonical),
                "sha256": hashlib.sha256(canonical).hexdigest(),
                "schema_sha256": schema_hash,
                "semantic_sha256": semantic_hash,
                "provenance_sha256": provenance_hash,
                "_completeness_counts": completeness_counts,
                **record_summary,
            }
        except PublicationError as exc:
            problems.append(f"{path}: {exc}")
    try:
        _validate_receipt(entries, bindings)
    except PublicationError as exc:
        problems.append(str(exc))
    try:
        _validate_serving_manifest(entries, bindings)
    except PublicationError as exc:
        problems.append(str(exc))
    return summaries, problems


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip() or value == "ไม่ระบุ":
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _semantic_diff(
    base: dict[str, dict[str, Any]],
    head: dict[str, dict[str, Any]],
    changed_public_paths: set[str],
    bindings: dict[str, OutputBinding],
) -> tuple[list[dict[str, Any]], list[str]]:
    diffs: list[dict[str, Any]] = []
    problems: list[str] = []
    for path in sorted(changed_public_paths - PUBLICATION_CONTROL_PATHS):
        before = base.get(path)
        after = head.get(path)
        if before is None:
            problems.append(f"{path}: new artifact requires manual contract review")
            continue
        if after is None:
            problems.append(f"{path}: artifact deletion requires manual review")
            continue
        binding = bindings.get(path)
        if binding is None:
            problems.append(f"{path}: no trusted contract for semantic diff")
            continue
        schema_changed = before["schema_sha256"] != after["schema_sha256"]
        before_record_schemas = before.get("_record_schema_digests") or {}
        after_record_schemas = after.get("_record_schema_digests") or {}
        common_identities = before_record_schemas.keys() & after_record_schemas.keys()
        if any(
            before_record_schemas[identity_digest]
            != after_record_schemas[identity_digest]
            for identity_digest in common_identities
        ):
            schema_changed = True
        reviewed_record_shapes = set(before_record_schemas.values())
        added_identities = after_record_schemas.keys() - before_record_schemas.keys()
        if any(
            after_record_schemas[identity_digest] not in reviewed_record_shapes
            for identity_digest in added_identities
        ):
            schema_changed = True
        if schema_changed:
            problems.append(f"{path}: schema changed under stable contract")
        semantic_changed = before["semantic_sha256"] != after["semantic_sha256"]
        before_record_semantics = before.get("_record_semantic_digests") or {}
        after_record_semantics = after.get("_record_semantic_digests") or {}
        for identity_digest in before_record_semantics.keys() & after_record_semantics.keys():
            if before_record_semantics[identity_digest] != after_record_semantics[identity_digest]:
                semantic_changed = True
                break
        if semantic_changed:
            problems.append(f"{path}: semantic meaning changed under stable contract")
        if before["provenance_sha256"] != after["provenance_sha256"]:
            problems.append(f"{path}: provenance rule changed under stable contract")
        before_count = before.get("count")
        after_count = after.get("count")
        if before_count is not None and after_count is not None:
            if before_count > 0 and after_count < before_count:
                drop = (before_count - after_count) / before_count
                if drop > float(binding.output.get("max_count_drop_ratio", 0)):
                    problems.append(f"{path}: record count drop exceeds contract")
            if before_count > 0 and after_count > before_count:
                increase = (after_count - before_count) / before_count
                if increase > float(binding.output.get("max_count_increase_ratio", 1)):
                    problems.append(f"{path}: record count increase exceeds contract")
        before_completeness = before.get("_completeness_counts") or {}
        after_completeness = after.get("_completeness_counts") or {}
        completeness_rules = {
            hashlib.sha256(rule["pointer"].encode("utf-8")).hexdigest(): rule
            for rule in binding.output.get("completeness_rules", [])
        }
        for rule_key, rule in completeness_rules.items():
            base_secondary_count = before_completeness.get(rule_key)
            head_secondary_count = after_completeness.get(rule_key)
            if base_secondary_count is None or head_secondary_count is None:
                problems.append(f"{path}: secondary completeness rule is unavailable")
                continue
            if base_secondary_count > 0 and head_secondary_count < base_secondary_count:
                drop = (base_secondary_count - head_secondary_count) / base_secondary_count
                if drop > float(rule.get("max_count_drop_ratio", 0)):
                    problems.append(f"{path}: secondary completeness count drop exceeds contract")
            if base_secondary_count > 0 and head_secondary_count > base_secondary_count:
                increase = (head_secondary_count - base_secondary_count) / base_secondary_count
                if increase > float(rule.get("max_count_increase_ratio", 1)):
                    problems.append(
                        f"{path}: secondary completeness count increase exceeds contract"
                    )
        identity_churn: float | None = None
        max_identity_churn: float | None = None
        if before.get("_identity_digests") is not None:
            before_identities = set(before["_identity_digests"])
            after_identities = set(after.get("_identity_digests") or ())
            identity_union = before_identities | after_identities
            identity_churn = (
                1 - (len(before_identities & after_identities) / len(identity_union))
                if identity_union
                else 0.0
            )
            max_identity_churn = float(binding.output["max_identity_churn_ratio"])
            if identity_churn > max_identity_churn:
                problems.append(f"{path}: record identity churn exceeds contract")
        before_as_of = _parse_datetime(before.get("as_of"))
        after_as_of = _parse_datetime(after.get("as_of"))
        if before_as_of is not None and after_as_of is not None and after_as_of < before_as_of:
            problems.append(f"{path}: as_of moved backwards")
        temporal_regressed = False
        before_record_times = before.get("_record_as_of_values") or {}
        after_record_times = after.get("_record_as_of_values") or {}
        for identity_digest in before_record_times.keys() & after_record_times.keys():
            base_slots = before_record_times[identity_digest]
            head_slots = after_record_times[identity_digest]
            for slot_digest, base_value in base_slots.items():
                parsed_base = _parse_datetime(base_value)
                if parsed_base is None:
                    continue
                parsed_head = _parse_datetime(head_slots.get(slot_digest))
                if parsed_head is None or parsed_head < parsed_base:
                    temporal_regressed = True
                    break
            if temporal_regressed:
                break
        if temporal_regressed:
            problems.append(f"{path}: per-record as_of moved backwards or became unavailable")
        diffs.append(
            {
                "path": path,
                "contract_id": after["contract_id"],
                "before": {
                    "bytes": before["bytes"],
                    "sha256": before["sha256"],
                    "schema_sha256": before["schema_sha256"],
                    "semantic_sha256": before["semantic_sha256"],
                    "provenance_sha256": before["provenance_sha256"],
                    "count": before_count,
                    "identity_sha256": before.get("identity_hash"),
                },
                "after": {
                    "bytes": after["bytes"],
                    "sha256": after["sha256"],
                    "schema_sha256": after["schema_sha256"],
                    "semantic_sha256": after["semantic_sha256"],
                    "provenance_sha256": after["provenance_sha256"],
                    "count": after_count,
                    "identity_sha256": after.get("identity_hash"),
                },
                "identity_churn_ratio": (
                    round(identity_churn, 6) if identity_churn is not None else None
                ),
                "max_identity_churn_ratio": max_identity_churn,
            }
        )
    return diffs, problems


def validate_workspace(
    root: Path,
    contracts_root: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    entries = snapshot_from_workspace(root)
    contracts = load_contracts(contracts_root)
    summaries, problems = _validate_snapshot(entries, contracts, catalog_path)
    return {
        "status": "valid" if not problems else "invalid",
        "lane": "workspace",
        "public_file_count": len(entries),
        "contract_count": len(contracts),
        "artifact_count": len(summaries),
        "problems": problems,
    }


def validate_git_revision(
    repository: Path,
    contracts_root: Path,
    catalog_path: Path,
    base_sha: str,
    head_sha: str,
) -> tuple[dict[str, Any], bool]:
    base_entries, base_tree = snapshot_from_git(repository, base_sha)
    head_entries, head_tree = snapshot_from_git(repository, head_sha)
    changed_paths = {
        path
        for path in set(base_tree) | set(head_tree)
        if base_tree.get(path) != head_tree.get(path)
    }
    changed_public = {path for path in changed_paths if path.startswith(PUBLIC_PREFIX)}
    changed_seeds = {
        path
        for path in changed_paths
        if path.startswith(PRODUCTION_SEED_PREFIXES)
    }
    contracts = load_contracts(contracts_root)
    head_summaries, head_problems = _validate_snapshot(
        head_entries, contracts, catalog_path
    )
    if not changed_public:
        lane = "manual_seed_review" if changed_seeds else "not_applicable"
        report = {
            "status": "pass" if not head_problems else "blocked",
            "lane": lane,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "changed_paths": sorted(changed_paths),
            "public_file_count": len(head_entries),
            "contract_count": len(contracts),
            "semantic_diff": [],
            "problems": head_problems,
        }
        return report, not head_problems

    manual_paths = {
        path for path in changed_paths if not path.startswith(PUBLIC_PREFIX)
    }
    manual_paths.update(changed_public & {SERVING_MANIFEST_PATH})
    lane = "manual_onboarding" if manual_paths else "routine_refresh"

    if lane == "manual_onboarding":
        # The trusted base cannot validate a newly introduced contract.  It still
        # scans every already classified public file and exposes a clear manual
        # lane; the privileged auto-merge workflow refuses every non-data path.
        report = {
            "status": "manual_review_required" if not head_problems else "blocked",
            "lane": lane,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "changed_paths": sorted(changed_paths),
            "manual_paths": sorted(manual_paths),
            "public_file_count": len(head_entries),
            "contract_count": len(contracts),
            "semantic_diff": [],
            "problems": head_problems,
        }
        return report, not head_problems

    base_summaries, base_problems = _validate_snapshot(
        base_entries, contracts, catalog_path
    )
    bindings = bind_outputs(set(head_entries) - PUBLICATION_CONTROL_PATHS, contracts)
    semantic_diff, diff_problems = _semantic_diff(
        base_summaries,
        head_summaries,
        changed_public,
        bindings,
    )
    problems = base_problems + head_problems + diff_problems
    report = {
        "status": "pass" if not problems else "blocked",
        "lane": lane,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "changed_paths": sorted(changed_paths),
        "public_file_count": len(head_entries),
        "contract_count": len(contracts),
        "semantic_diff": semantic_diff,
        "problems": problems,
    }
    return report, not problems


def _write_report(report: dict[str, Any], path: Path | None) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if path is not None:
        path.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate reviewed public-data releases")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--contracts-root", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--base-sha")
    parser.add_argument("--head-sha")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--write-receipt", action="store_true")
    args = parser.parse_args(argv)
    root = args.repository.resolve()
    contracts_root = (args.contracts_root or root / "config/publication_contracts").resolve()
    catalog_path = (args.catalog or root / "config/source_catalog.json").resolve()
    try:
        if args.write_receipt:
            receipt = write_receipt(root, contracts_root, catalog_path)
            _write_report(
                {
                    "status": "written",
                    "path": RECEIPT_PATH,
                    "artifact_count": receipt["artifact_count"],
                    "release_digest": receipt["release_digest"],
                },
                args.report,
            )
            return 0
        if bool(args.base_sha) != bool(args.head_sha):
            raise PublicationError("--base-sha and --head-sha must be provided together")
        if args.base_sha:
            report, valid = validate_git_revision(
                root,
                contracts_root,
                catalog_path,
                args.base_sha,
                args.head_sha,
            )
        else:
            report = validate_workspace(root, contracts_root, catalog_path)
            valid = report["status"] == "valid"
        _write_report(report, args.report)
        return 0 if valid else 1
    except (OSError, PublicationError) as exc:
        _write_report(
            {"status": "blocked", "lane": "error", "problems": [str(exc)]},
            args.report,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
