from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import io
import json
import math
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


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
PHONE_RE = re.compile(
    r"(?<!\d)(?:(?:\+?66)[\s().-]*[1-9]|0[1-9])(?:[\s().-]*\d){7,8}(?!\d)"
)
LABELLED_CONTACT_RE = re.compile(
    r"(?i)(?:\b(?:phone|telephone|mobile|tel|email)\s*(?:no\.?|number)?\s*[:：]|"
    r"(?:โทรศัพท์|เบอร์โทร|อีเมล|อีเมล์)\s*[:：])"
)
ADDRESS_VALUE_RE = re.compile(
    r"(?i)(?:\b(?:home|residential|mailing)\s+address\b|"
    r"ที่อยู่(?:บ้าน|ปัจจุบัน|ตามทะเบียนบ้าน)|บ้านเลขที่)"
)
SIGNED_URL_RE = re.compile(
    r"(?i)[?&](?:access_token|api_?key|key|sig|signature|token|"
    r"x-amz-credential|x-amz-signature)="
)
SECRET_VALUE_RE = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b|"
    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b|\bAKIA[A-Z0-9]{16}\b)"
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


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PublicationError(f"duplicate JSON key: {key}")
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


def _is_negative_audit(key: str, value: Any) -> bool:
    if key.endswith("_exposed") and value is False:
        return True
    if key.endswith(NEGATIVE_AUDIT_KEY_SUFFIXES):
        if value in (False, None, 0):
            return True
        if key.endswith("_values_redacted") and type(value) is int and value >= 0:
            return True
        if key.endswith("_excluded") and isinstance(value, list):
            return True
    return False


def _sensitive_key(key: str, value: Any) -> bool:
    normalized = _normalise_key(key)
    if normalized == "mobile_home_park":
        return False
    if _is_negative_audit(normalized, value):
        return False
    padded = f"_{normalized}_"
    return any(f"_{part}_" in padded for part in SENSITIVE_KEY_PARTS) or any(
        part in str(key) for part in SENSITIVE_THAI_KEY_PARTS
    )


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

    def walk(value: Any, path: str, leaf_key: str | None = None) -> None:
        if len(problems) >= 50:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if _sensitive_key(str(key), child):
                    problems.append(f"{child_path}: private/contact field")
                walk(child, child_path, _normalise_key(key))
            return
        if isinstance(value, list):
            for child in value:
                walk(child, f"{path}[]", leaf_key)
            return
        if not isinstance(value, str):
            return
        if value in restricted_source_ids and not restricted_allowed(path):
            problems.append(f"{path}: restricted source identifier")
        if EMAIL_RE.search(value):
            problems.append(f"{path}: email-like value")
        if LABELLED_CONTACT_RE.search(value):
            problems.append(f"{path}: labelled contact value")
        if ADDRESS_VALUE_RE.search(value):
            problems.append(f"{path}: home-address-like value")
        if SIGNED_URL_RE.search(value):
            problems.append(f"{path}: signed/credential URL")
        if SECRET_VALUE_RE.search(value):
            problems.append(f"{path}: credential-like value")
        opaque = leaf_key is not None and (
            leaf_key.endswith(("_id", "_code", "_hash", "_count", "_year", "_url"))
            or bool(
                set(leaf_key.split("_"))
                & {
                    "amount",
                    "average",
                    "avg",
                    "count",
                    "hash",
                    "index",
                    "mean",
                    "median",
                    "percent",
                    "rate",
                    "ratio",
                    "score",
                    "share",
                    "sum",
                    "total",
                    "value",
                }
            )
            or leaf_key
            in {
                "amount",
                "as_of",
                "code",
                "count",
                "date",
                "generated_at",
                "id",
                "latitude",
                "longitude",
                "province_code",
                "record_hash",
                "sha256",
                "time",
                "updated_at",
                "value",
                "year",
            }
        )
        if not opaque and PHONE_RE.search(value):
            problems.append(f"{path}: Thai phone-like value")

    walk(payload, artifact_path)
    return problems


def _embedded_source_ids(payload: Any, *, artifact_path: str) -> set[str]:
    """Collect explicit provenance IDs without exposing untrusted values in errors."""

    found: set[str] = set()

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                normalised = _normalise_key(key)
                if normalised == "source_id":
                    if not isinstance(child, str) or not child:
                        raise PublicationError(
                            f"embedded source_id must be a non-empty string at {child_path}"
                        )
                    found.add(child)
                elif normalised == "source_ids":
                    if not isinstance(child, list) or any(
                        not isinstance(item, str) or not item for item in child
                    ):
                        raise PublicationError(
                            f"embedded source_ids must be non-empty strings at {child_path}"
                        )
                    found.update(child)
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(payload, artifact_path)
    return found


def _shape_signature(payload: Any) -> str:
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
                child_nodes, _ = walk(child, f"{path}/{key}", depth + 1)
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


def _record_summary(payload: Any, output: dict[str, Any]) -> dict[str, Any]:
    pointer = output.get("records_pointer")
    if pointer is None:
        return {"count": None, "identity_hash": None, "_identity_digests": None}
    records = _records(payload, pointer)
    identities: set[str] = set()
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
        "as_of": as_of,
    }


def _csv_payload(data: bytes, output: dict[str, Any], path: str) -> tuple[list[dict[str, str]], str]:
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
            if not isinstance(value, str):
                raise PublicationError(f"CSV cell is missing at row {row_index}, column {header}")
            normalised = value.lstrip("\ufeff \t\r\n\v\f")
            if normalised.startswith(("=", "@")) or (
                normalised.startswith(("+", "-"))
                and NUMERIC_CELL_RE.fullmatch(normalised) is None
            ):
                raise PublicationError(
                    f"spreadsheet formula-like cell at row {row_index}, column {header}"
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


def _catalog_sets(catalog_path: Path) -> tuple[set[str], set[str], set[str]]:
    catalog = _read_json_file(catalog_path)
    sources = catalog.get("sources")
    if not isinstance(sources, list):
        raise PublicationError("source catalog has no sources array")
    all_ids = {str(item.get("source_id")) for item in sources}
    approved = {
        str(item.get("source_id"))
        for item in sources
        if item.get("production_values_allowed") is True
        and item.get("cloud_policy") == "team_approved_public"
    }
    restricted = {
        str(item.get("source_id"))
        for item in sources
        if item.get("cloud_policy") == "restricted_local_only"
    }
    return all_ids, approved, restricted


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
) -> tuple[set[str], set[str]]:
    all_ids, approved, restricted = _catalog_sets(catalog_path)
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
    return approved, restricted


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
    _, restricted = _validate_contract_sources(contracts, catalog_path)
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
        if b"\x00" in entry.data[:8192]:
            problems.append(f"{path}: binary/NUL payload is not allowed")
            continue
        try:
            if output["format"] in {"json", "geojson"}:
                payload = load_json_bytes(entry.data, path=path)
                if not isinstance(payload, dict):
                    raise PublicationError(f"{path} must contain a JSON object")
                if output["format"] == "geojson":
                    _validate_geojson(payload)
                schema_hash = _shape_signature(payload)
                record_summary = _record_summary(payload, output)
                privacy = _privacy_problems(
                    payload,
                    artifact_path=path,
                    restricted_source_ids=restricted,
                    profile=binding.contract["privacy_profile"],
                )
            else:
                rows, schema_hash = _csv_payload(entry.data, output, path)
                record_summary = _record_summary(rows, output)
                privacy = _privacy_problems(
                    rows,
                    artifact_path=path,
                    restricted_source_ids=restricted,
                    profile=binding.contract["privacy_profile"],
                )
                payload = rows
            embedded_source_ids = _embedded_source_ids(payload, artifact_path=path)
            if not embedded_source_ids.issubset(set(binding.contract["source_ids"])):
                raise PublicationError(
                    "embedded source provenance is not declared by its publication contract"
                )
            problems.extend(privacy)
            canonical = _canonical_text_bytes(entry.data)
            summaries[path] = {
                "path": path,
                "contract_id": binding.contract["contract_id"],
                "bytes": len(canonical),
                "sha256": hashlib.sha256(canonical).hexdigest(),
                "schema_sha256": schema_hash,
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
        if before["schema_sha256"] != after["schema_sha256"]:
            problems.append(f"{path}: schema changed under stable contract")
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
        diffs.append(
            {
                "path": path,
                "contract_id": after["contract_id"],
                "before": {
                    "bytes": before["bytes"],
                    "sha256": before["sha256"],
                    "schema_sha256": before["schema_sha256"],
                    "count": before_count,
                    "identity_sha256": before.get("identity_hash"),
                },
                "after": {
                    "bytes": after["bytes"],
                    "sha256": after["sha256"],
                    "schema_sha256": after["schema_sha256"],
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
