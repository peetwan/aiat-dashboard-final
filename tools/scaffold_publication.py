"""Create a fail-closed starter for one reviewed public dataset.

The scaffold deliberately does not read an upstream response, Candidate table, or raw
evidence.  It records semantics supplied by a reviewer and creates a builder that stays
disabled until the dataset-specific projection has been implemented and reviewed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.field_contexts import context_allows_key, validate_field_contexts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNKNOWN = "ไม่ระบุ"
DATASET_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SOURCE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
FIELD_PATH_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)
OUTPUT_PATH_RE = re.compile(r"^data/public/[A-Za-z0-9][A-Za-z0-9_./-]*$")
CONTROL_OUTPUTS = {
    "data/public/publication_receipt.json",
    "data/public/serving_manifest.json",
}
ALLOWED_FORMATS = {"json", "geojson", "csv"}
ALLOWED_ROLES = {"database", "download", "provenance", "support"}
ALLOWED_SOURCE_SCOPES = {
    "approved_values",
    "catalog_metadata",
    "reference_geography",
}
ALLOWED_PRIVACY_PROFILES = {
    "aggregate_public",
    "catalog_metadata",
    "provenance_metadata",
    "reference_geography",
}
FORBIDDEN_FIELD_PARTS = {
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
    "home_address",
    "household_id",
    "id_card",
    "last_name",
    "mailing_address",
    "mobile",
    "national_id",
    "owner_name",
    "password",
    "person_name",
    "phone",
    "researcher_name",
    "residential_address",
    "secret",
    "social_security",
    "telephone",
    "token",
}


class ScaffoldError(ValueError):
    """The requested scaffold is unsafe, ambiguous, or would overwrite a file."""


@dataclass(frozen=True)
class PublicationSpec:
    dataset_key: str
    source_ids: tuple[str, ...]
    source_scope: str
    grain: str
    identity_fields: tuple[str, ...]
    geography_level: str
    geography_fields: tuple[str, ...]
    as_of_status: str
    as_of_fields: tuple[str, ...]
    measure_name: str
    measure_field: str
    measure_unit: str
    measure_denominator: str
    output_path: str
    output_format: str
    output_role: str
    downloadable: bool
    records_pointer: str
    privacy_profile: str
    max_bytes: int
    minimum_count: int
    max_count_drop_ratio: float
    max_count_increase_ratio: float
    max_identity_churn_ratio: float
    expected_count: int | None = None
    as_of_pointer: str | None = None
    csv_headers: tuple[str, ...] = ()
    field_contexts: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PlannedFile:
    relative_path: str
    content: str


@dataclass(frozen=True)
class ScaffoldResult:
    paths: tuple[str, ...]
    dry_run: bool


def _safe_text(value: str, *, label: str, maximum: int = 500) -> str:
    if value != value.strip() or not value or len(value) > maximum:
        raise ScaffoldError(f"{label} must be 1-{maximum} characters without edge spaces")
    if any(character in value for character in ("\0", "\r", "\n")):
        raise ScaffoldError(f"{label} must not contain control characters")
    return value


def _normalise_field_part(value: str) -> str:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return re.sub(r"[^a-z0-9]+", "_", separated.lower()).strip("_")


def _safe_field(value: str, *, label: str, allow_map_key: bool = False, context: str | None = None) -> str:
    if allow_map_key and value == "$key":
        return value
    if not FIELD_PATH_RE.fullmatch(value):
        raise ScaffoldError(f"{label} must be a field name or dotted field path: {value!r}")
    for segment in value.split("."):
        normalised = _normalise_field_part(segment)
        padded = f"_{normalised}_"
        blocked = sorted(
            item for item in FORBIDDEN_FIELD_PARTS if f"_{item}_" in padded
        )
        if blocked and not context_allows_key(segment, context):
            raise ScaffoldError(
                f"{label} contains forbidden personal/contact/secret field: {blocked[0]}"
            )
    return value


def _semantic_fields(
    values: Sequence[str], *, label: str, allow_map_key: bool = False, contexts: dict[str, str] | None = None
) -> tuple[str, ...]:
    fields = tuple(values)
    if not fields:
        raise ScaffoldError(f"{label} is required; use {UNKNOWN!r} when the source is unclear")
    if UNKNOWN in fields:
        if fields != (UNKNOWN,):
            raise ScaffoldError(f"{label}: {UNKNOWN!r} must be the only value")
        return ()
    for field in fields:
        _safe_field(field, label=label, allow_map_key=allow_map_key, context=(contexts or {}).get(field))
    if len(fields) != len(set(fields)):
        raise ScaffoldError(f"{label} contains duplicate fields")
    return fields


def _safe_json_pointer(value: str, *, label: str) -> str:
    if value == "$":
        return value
    if not value.startswith("/") or any(
        character in value for character in ("\0", "\r", "\n", "\\")
    ):
        raise ScaffoldError(f"{label} must be '$' or an RFC 6901 JSON pointer")
    for part in value.split("/")[1:]:
        if part in {".", ".."}:
            raise ScaffoldError(f"{label} must not contain path traversal segments")
        if re.search(r"~(?![01])", part):
            raise ScaffoldError(f"{label} contains an invalid JSON pointer escape")
    return value


def _safe_output_path(value: str, output_format: str) -> str:
    if not OUTPUT_PATH_RE.fullmatch(value) or "\\" in value:
        raise ScaffoldError("output_path must be an exact safe path below data/public/")
    parsed = PurePosixPath(value)
    if str(parsed) != value or ".." in parsed.parts or value in CONTROL_OUTPUTS:
        raise ScaffoldError("output_path is reserved, non-canonical, or escapes data/public/")
    if any(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", part) is None
        for part in parsed.parts[2:]
    ):
        raise ScaffoldError("output_path contains an unsafe directory or filename")
    if any(character in value for character in "*?[]"):
        raise ScaffoldError("output_path must be exact; glob selectors are not scaffolded")
    suffix = parsed.suffix.lower()
    allowed_suffixes = {
        "json": {".json"},
        "geojson": {".geojson", ".json"},
        "csv": {".csv"},
    }
    if suffix not in allowed_suffixes[output_format]:
        raise ScaffoldError(
            f"output_path extension {suffix!r} does not match format {output_format!r}"
        )
    return value


def _field_paths_do_not_conflict(fields: Sequence[str]) -> None:
    # A field may legitimately play two semantic roles (for example,
    # ``province_code`` can be both identity and geography).  Only nested
    # prefix collisions are impossible to encode as one synthetic JSON value.
    ordinary = sorted({field for field in fields if field != "$key"})
    for index, left in enumerate(ordinary):
        for right in ordinary[index + 1 :]:
            if left.startswith(f"{right}.") or right.startswith(f"{left}."):
                raise ScaffoldError(
                    f"fixture fields overlap and cannot be represented safely: {left!r}, {right!r}"
                )


def _validate_map_key_identity_shape(spec: PublicationSpec) -> None:
    if "$key" not in spec.identity_fields:
        return
    if spec.output_format == "csv":
        raise ScaffoldError("$key identity is unavailable for CSV records")
    if spec.records_pointer in {"$", "/"}:
        raise ScaffoldError(
            "$key identity requires a non-root records_pointer that resolves to an object map"
        )
    if spec.output_format == "geojson" and spec.records_pointer == "/features":
        raise ScaffoldError(
            "$key identity is unavailable for the GeoJSON /features array"
        )


def validate_spec(spec: PublicationSpec) -> PublicationSpec:
    try:
        contexts = validate_field_contexts(dict(spec.field_contexts))
    except ValueError as exc:
        raise ScaffoldError(str(exc)) from exc
    if contexts and spec.source_scope != "approved_values":
        raise ScaffoldError("field contexts require approved_values")
    prefix = "" if spec.records_pointer == "$" else spec.records_pointer
    def field_context(field: str) -> str | None:
        return contexts.get(prefix + "/*/" + field.replace(".", "/"))
    if not DATASET_KEY_RE.fullmatch(spec.dataset_key):
        raise ScaffoldError("dataset_key must match ^[a-z][a-z0-9_]{0,63}$")
    if not spec.source_ids and spec.source_scope != "reference_geography":
        raise ScaffoldError(
            "at least one source_id is required outside reference_geography"
        )
    for source_id in spec.source_ids:
        if not SOURCE_ID_RE.fullmatch(source_id):
            raise ScaffoldError(f"unsafe source_id: {source_id!r}")
    if len(spec.source_ids) != len(set(spec.source_ids)):
        raise ScaffoldError("source_ids must be unique")
    if spec.source_scope not in ALLOWED_SOURCE_SCOPES:
        raise ScaffoldError(f"invalid source_scope: {spec.source_scope!r}")
    if spec.privacy_profile not in ALLOWED_PRIVACY_PROFILES:
        raise ScaffoldError(f"invalid privacy_profile: {spec.privacy_profile!r}")
    if spec.output_format not in ALLOWED_FORMATS:
        raise ScaffoldError(f"invalid output_format: {spec.output_format!r}")
    if spec.output_role not in ALLOWED_ROLES:
        raise ScaffoldError(f"invalid output_role: {spec.output_role!r}")

    for label, value in (
        ("grain", spec.grain),
        ("geography_level", spec.geography_level),
        ("as_of_status", spec.as_of_status),
        ("measure_name", spec.measure_name),
        ("measure_unit", spec.measure_unit),
        ("measure_denominator", spec.measure_denominator),
    ):
        _safe_text(value, label=label)

    if not spec.identity_fields:
        raise ScaffoldError("identity_fields is required and cannot be unknown")
    for field in spec.identity_fields:
        _safe_field(field, label="identity_fields", allow_map_key=True, context=field_context(field))
    if len(spec.identity_fields) != len(set(spec.identity_fields)):
        raise ScaffoldError("identity_fields contains duplicate fields")
    for field in (*spec.geography_fields, *spec.as_of_fields):
        _safe_field(field, label="semantic field", context=field_context(field))
    _safe_field(spec.measure_field, label="measure_field", context=field_context(spec.measure_field))
    _field_paths_do_not_conflict(
        (*spec.identity_fields, *spec.geography_fields, *spec.as_of_fields, spec.measure_field)
    )

    _safe_output_path(spec.output_path, spec.output_format)
    _safe_json_pointer(spec.records_pointer, label="records_pointer")
    _validate_map_key_identity_shape(spec)
    if spec.as_of_pointer is not None:
        _safe_json_pointer(spec.as_of_pointer, label="as_of_pointer")
    if spec.output_format == "csv":
        if spec.records_pointer != "$":
            raise ScaffoldError("CSV records_pointer must be '$'")
        if spec.as_of_pointer is not None:
            raise ScaffoldError("CSV does not support as_of_pointer; declare as_of_fields only")
        if not spec.csv_headers:
            raise ScaffoldError("csv_headers is required for CSV output")
        for header in spec.csv_headers:
            _safe_field(header, label="csv_headers", context=field_context(header))
            if "." in header:
                raise ScaffoldError("CSV headers must be simple field names, not dotted paths")
        if len(spec.csv_headers) != len(set(spec.csv_headers)):
            raise ScaffoldError("csv_headers contains duplicates")
        required_headers = {
            field
            for field in (
                *spec.identity_fields,
                *spec.geography_fields,
                *spec.as_of_fields,
                spec.measure_field,
            )
            if field != "$key"
        }
        missing_headers = required_headers - set(spec.csv_headers)
        if missing_headers:
            raise ScaffoldError(
                f"csv_headers omits declared fields: {sorted(missing_headers)}"
            )
    elif spec.csv_headers:
        raise ScaffoldError("csv_headers is only valid for CSV output")

    if type(spec.max_bytes) is not int or not 1 <= spec.max_bytes <= 25 * 1024 * 1024:
        raise ScaffoldError("max_bytes must be between 1 and 26214400")
    if type(spec.minimum_count) is not int or spec.minimum_count < 0:
        raise ScaffoldError("minimum_count must be a non-negative integer")
    if spec.expected_count is not None and (
        type(spec.expected_count) is not int
        or spec.expected_count < spec.minimum_count
    ):
        raise ScaffoldError("expected_count must be at least minimum_count")
    for label, ratio in (
        ("max_count_drop_ratio", spec.max_count_drop_ratio),
        ("max_count_increase_ratio", spec.max_count_increase_ratio),
    ):
        if isinstance(ratio, bool) or not 0 <= float(ratio) <= 10:
            raise ScaffoldError(f"{label} must be between 0 and 10")
    if isinstance(spec.max_identity_churn_ratio, bool) or not 0 <= float(
        spec.max_identity_churn_ratio
    ) <= 1:
        raise ScaffoldError("max_identity_churn_ratio must be between 0 and 1")
    return spec


def _load_catalog(project_root: Path) -> dict[str, dict[str, object]]:
    path = project_root / "config" / "source_catalog.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScaffoldError(f"cannot read source catalog: {path}") from exc
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        raise ScaffoldError("source catalog must contain a sources array")
    result: dict[str, dict[str, object]] = {}
    for source in sources:
        if isinstance(source, dict) and isinstance(source.get("source_id"), str):
            result[source["source_id"]] = source
    return result


def _validate_catalog_sources(spec: PublicationSpec, project_root: Path) -> None:
    catalog = _load_catalog(project_root)
    unknown = sorted(set(spec.source_ids) - set(catalog))
    if unknown:
        raise ScaffoldError(f"source_ids are not in generated source catalog: {unknown}")
    if spec.source_scope == "approved_values":
        disallowed = sorted(
            source_id
            for source_id in spec.source_ids
            if catalog[source_id].get("production_values_allowed") is not True
            or catalog[source_id].get("cloud_policy") != "team_approved_public"
        )
        if disallowed:
            raise ScaffoldError(
                f"approved_values requires team-approved public sources: {disallowed}"
            )


def _needs_review(spec: PublicationSpec) -> list[str]:
    review: list[str] = []
    if spec.grain == UNKNOWN:
        review.append("grain")
    if spec.geography_level == UNKNOWN or not spec.geography_fields:
        review.append("geography")
    if spec.as_of_status == UNKNOWN or not spec.as_of_fields:
        review.append("as_of")
    if spec.measure_unit == UNKNOWN:
        review.append("measure.unit")
    if spec.measure_denominator == UNKNOWN:
        review.append("measure.denominator")
    return review


def _contract(spec: PublicationSpec) -> dict[str, object]:
    review_items = _needs_review(spec)
    output: dict[str, object] = {
        "path": spec.output_path,
        "format": spec.output_format,
        "role": spec.output_role,
        "downloadable": spec.downloadable,
        "max_bytes": spec.max_bytes,
        "records_pointer": spec.records_pointer,
        "identity_fields": list(spec.identity_fields),
        "minimum_count": spec.minimum_count,
        "max_count_drop_ratio": spec.max_count_drop_ratio,
        "max_count_increase_ratio": spec.max_count_increase_ratio,
        "max_identity_churn_ratio": spec.max_identity_churn_ratio,
        "schema_policy": "stable",
    }
    if spec.expected_count is not None:
        output["expected_count"] = spec.expected_count
    if spec.as_of_pointer is not None:
        output["as_of_pointer"] = spec.as_of_pointer
    if spec.csv_headers:
        output["headers"] = list(spec.csv_headers)
    if spec.field_contexts:
        output["field_contexts"] = dict(spec.field_contexts)
    return {
        "contract_version": "1.0",
        "contract_id": spec.dataset_key,
        "dataset_key": spec.dataset_key,
        "source_scope": spec.source_scope,
        "source_ids": list(spec.source_ids),
        "builder": f"tools.publication_builders.{spec.dataset_key}:build",
        "grain_th": spec.grain,
        "identity": {
            "fields": list(spec.identity_fields),
            "needs_review": False,
        },
        "geography": {
            "level": spec.geography_level,
            "fields": list(spec.geography_fields),
            "needs_review": spec.geography_level == UNKNOWN or not spec.geography_fields,
        },
        "as_of": {
            "status": spec.as_of_status,
            "fields": list(spec.as_of_fields),
            "needs_review": spec.as_of_status == UNKNOWN or not spec.as_of_fields,
        },
        "measures": [
            {
                "name": spec.measure_name,
                "unit": spec.measure_unit,
                "denominator": spec.measure_denominator,
            }
        ],
        "completeness": {
            "policy": "output_contracts",
            "needs_review": bool(review_items),
            "review_items": review_items,
        },
        "privacy_profile": spec.privacy_profile,
        "outputs": [output],
    }


def _set_nested(record: dict[str, object], path: str, value: object) -> None:
    current = record
    parts = path.split(".")
    for part in parts[:-1]:
        child: dict[str, object] = {}
        current[part] = child
        current = child
    current[parts[-1]] = value


def _fixture(spec: PublicationSpec) -> dict[str, object]:
    record: dict[str, object] = {}
    for field in spec.identity_fields:
        if field != "$key":
            _set_nested(record, field, f"synthetic-{field.split('.')[-1]}-001")
    for field in spec.geography_fields:
        _set_nested(record, field, "synthetic-geography")
    for field in spec.as_of_fields:
        _set_nested(record, field, "2000-01-01T00:00:00Z")
    _set_nested(record, spec.measure_field, 0)
    return {
        "fixture_version": "1.0",
        "dataset_key": spec.dataset_key,
        "synthetic": True,
        "redacted": True,
        "source_ids": list(spec.source_ids),
        "reviewed_records": [record],
    }


def _builder_source(spec: PublicationSpec) -> str:
    return f'''"""Dataset-specific public projection for {spec.dataset_key}.

Generated fail-closed: implement ``build`` only after reviewing the source-specific
mapping.  Never pass raw responses or Candidate rows through unchanged.
"""

from __future__ import annotations

from typing import Any, Sequence


DATASET_KEY = {spec.dataset_key!r}
SOURCE_IDS = {spec.source_ids!r}
OUTPUT_PATH = {spec.output_path!r}
OUTPUT_FORMAT = {spec.output_format!r}
RECORDS_POINTER = {spec.records_pointer!r}
IDENTITY_FIELDS = {spec.identity_fields!r}


class PublicationMappingRequired(RuntimeError):
    """The reviewed dataset-specific public projection is not implemented yet."""


def build(reviewed_records: Sequence[dict[str, Any]]) -> object:
    """Return a deterministic public artifact after explicit field-level review.

    ``reviewed_records`` must already exclude raw payloads, personal/contact values,
    secrets, and restricted values.  Replace this exception with a source-specific
    projection and focused semantic/completeness tests; do not implement a generic copy.
    """

    del reviewed_records
    raise PublicationMappingRequired(
        "Implement and review the {spec.dataset_key} public projection before publishing"
    )
'''


def _generated_test_source(spec: PublicationSpec) -> str:
    return f'''from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.publication_builders.{spec.dataset_key} import (
    DATASET_KEY,
    OUTPUT_PATH,
    PublicationMappingRequired,
    build,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/publication/{spec.dataset_key}.json"


def test_{spec.dataset_key}_fixture_is_synthetic_and_redacted():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert fixture["dataset_key"] == DATASET_KEY == {spec.dataset_key!r}
    assert fixture["synthetic"] is True
    assert fixture["redacted"] is True
    assert fixture["reviewed_records"]
    assert OUTPUT_PATH == {spec.output_path!r}


def test_{spec.dataset_key}_builder_fails_closed_until_mapping_is_reviewed():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    with pytest.raises(PublicationMappingRequired):
        build(fixture["reviewed_records"])
'''


def plan_scaffold(spec: PublicationSpec) -> tuple[PlannedFile, ...]:
    validate_spec(spec)
    contract = json.dumps(_contract(spec), ensure_ascii=False, indent=2) + "\n"
    fixture = json.dumps(_fixture(spec), ensure_ascii=False, indent=2) + "\n"
    return (
        PlannedFile(
            f"tools/publication_builders/{spec.dataset_key}.py",
            _builder_source(spec),
        ),
        PlannedFile(
            f"config/publication_contracts/{spec.dataset_key}.json",
            contract,
        ),
        PlannedFile(
            f"tests/fixtures/publication/{spec.dataset_key}.json",
            fixture,
        ),
        PlannedFile(
            f"tests/generated/test_publication_{spec.dataset_key}.py",
            _generated_test_source(spec),
        ),
    )


def _destination(project_root: Path, relative_path: str) -> Path:
    root = project_root.resolve()
    candidate = project_root.joinpath(*PurePosixPath(relative_path).parts)
    resolved = candidate.resolve(strict=False)
    if resolved == root or root not in resolved.parents:
        raise ScaffoldError(f"scaffold destination escapes project root: {relative_path}")
    return candidate


def scaffold(
    spec: PublicationSpec,
    *,
    project_root: Path = PROJECT_ROOT,
    dry_run: bool = False,
) -> ScaffoldResult:
    spec = validate_spec(spec)
    project_root = project_root.resolve()
    _validate_catalog_sources(spec, project_root)
    planned = plan_scaffold(spec)
    destinations = [
        (_destination(project_root, item.relative_path), item) for item in planned
    ]
    output_destination = _destination(project_root, spec.output_path)
    collisions = [
        item.relative_path for path, item in destinations if path.exists()
    ]
    if output_destination.exists():
        collisions.append(spec.output_path)
    if collisions:
        raise ScaffoldError(
            "refusing to overwrite existing scaffold/public output: "
            + ", ".join(sorted(collisions))
        )
    if not dry_run:
        for destination, item in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                with destination.open("x", encoding="utf-8", newline="\n") as handle:
                    handle.write(item.content)
            except FileExistsError as exc:
                raise ScaffoldError(
                    f"refusing to overwrite file created concurrently: {item.relative_path}"
                ) from exc
    return ScaffoldResult(
        paths=tuple(item.relative_path for item in planned),
        dry_run=dry_run,
    )


def _parse_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scaffold a fail-closed reviewed publication dataset"
    )
    parser.add_argument("dataset_key")
    parser.add_argument("--source-ids", nargs="*", default=())
    parser.add_argument("--source-scope", choices=sorted(ALLOWED_SOURCE_SCOPES), required=True)
    parser.add_argument("--grain", required=True)
    parser.add_argument("--identity-fields", nargs="+", required=True)
    parser.add_argument("--geography-level", required=True)
    parser.add_argument("--geography-fields", nargs="+", required=True)
    parser.add_argument("--as-of-status", required=True)
    parser.add_argument("--as-of-fields", nargs="+", required=True)
    parser.add_argument("--measure-name", required=True)
    parser.add_argument("--measure-field", required=True)
    parser.add_argument("--measure-unit", required=True)
    parser.add_argument("--measure-denominator", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--output-format", choices=sorted(ALLOWED_FORMATS), required=True)
    parser.add_argument("--output-role", choices=sorted(ALLOWED_ROLES), required=True)
    parser.add_argument("--downloadable", type=_parse_bool, required=True)
    parser.add_argument("--records-pointer", required=True)
    parser.add_argument(
        "--privacy-profile", choices=sorted(ALLOWED_PRIVACY_PROFILES), required=True
    )
    parser.add_argument("--max-bytes", type=int, required=True)
    parser.add_argument("--minimum-count", type=int, required=True)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--max-count-drop-ratio", type=float, required=True)
    parser.add_argument("--max-count-increase-ratio", type=float, required=True)
    parser.add_argument("--max-identity-churn-ratio", type=float, required=True)
    parser.add_argument("--as-of-pointer")
    parser.add_argument("--csv-headers", nargs="+")
    parser.add_argument("--field-context", action="append", nargs=2, metavar=("POINTER", "CONTEXT"), default=[],
                        help="บริบทฟิลด์ เช่น --field-context /items/*/owner_name work_attribution")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _spec_from_namespace(args: argparse.Namespace) -> PublicationSpec:
    prefix = "" if args.records_pointer == "$" else args.records_pointer
    contexts = validate_field_contexts(dict(args.field_context))
    field_contexts = {pointer.removeprefix(prefix + "/*/").replace("/", "."): context
                      for pointer, context in contexts.items() if pointer.startswith(prefix + "/*/")}
    geography_fields = _semantic_fields(
        args.geography_fields, label="geography_fields", contexts=field_contexts
    )
    as_of_fields = _semantic_fields(args.as_of_fields, label="as_of_fields", contexts=field_contexts)
    identity_fields = _semantic_fields(
        args.identity_fields,
        label="identity_fields",
        allow_map_key=True,
        contexts=field_contexts,
    )
    return PublicationSpec(
        dataset_key=args.dataset_key,
        source_ids=tuple(args.source_ids),
        source_scope=args.source_scope,
        grain=args.grain,
        identity_fields=identity_fields,
        geography_level=args.geography_level,
        geography_fields=geography_fields,
        as_of_status=args.as_of_status,
        as_of_fields=as_of_fields,
        measure_name=args.measure_name,
        measure_field=args.measure_field,
        measure_unit=args.measure_unit,
        measure_denominator=args.measure_denominator,
        output_path=args.output_path,
        output_format=args.output_format,
        output_role=args.output_role,
        downloadable=args.downloadable,
        records_pointer=args.records_pointer,
        privacy_profile=args.privacy_profile,
        max_bytes=args.max_bytes,
        minimum_count=args.minimum_count,
        expected_count=args.expected_count,
        max_count_drop_ratio=args.max_count_drop_ratio,
        max_count_increase_ratio=args.max_count_increase_ratio,
        max_identity_churn_ratio=args.max_identity_churn_ratio,
        as_of_pointer=args.as_of_pointer,
        csv_headers=tuple(args.csv_headers or ()),
        field_contexts=tuple(contexts.items()),
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    project_root: Path = PROJECT_ROOT,
) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = scaffold(
            _spec_from_namespace(args),
            project_root=project_root,
            dry_run=args.dry_run,
        )
    except (ScaffoldError, ValueError) as exc:
        parser.error(str(exc))
    mode = "DRY RUN" if result.dry_run else "CREATED"
    print(f"{mode}: publication scaffold for {args.dataset_key}")
    for path in result.paths:
        print(f"- {path}")
    if not result.dry_run:
        print("Builder remains fail-closed until its dataset-specific projection is reviewed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
