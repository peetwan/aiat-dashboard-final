"""Create a safe, reviewable connector starter without touching registries."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.privacy import FORBIDDEN_KEY_PARTS, sanitize_payload  # noqa: E402


TEMPLATE_ROOT = PROJECT_ROOT / "templates" / "connector"
SOURCE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
TRANSPORT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
FIELD_PATH_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)
PLACEHOLDER_PATTERN = re.compile(r"__[A-Z0-9_]+__")
class ScaffoldError(ValueError):
    pass


@dataclass(frozen=True)
class ScaffoldSpec:
    source_id: str
    transport: str
    dataset_key: str
    grain_th: str
    identity_options: tuple[tuple[str, ...], ...]
    geography_fields: tuple[str, ...] = ()
    as_of_fields: tuple[str, ...] = ()
    driver_name: str | None = None

    @property
    def class_name(self) -> str:
        stem = "".join(part[:1].upper() + part[1:] for part in self.source_id.split("_"))
        return f"{stem}Connector"

    @property
    def driver(self) -> str:
        return self.driver_name or self.source_id


def _validate_field_path(path: str, *, label: str) -> str:
    if path == "$payload_hash":
        return path
    if not FIELD_PATH_PATTERN.fullmatch(path):
        raise ScaffoldError(
            f"{label} must be a field name or dotted field path, got {path!r}"
        )
    segments = {
        part.lower().replace("-", "_")
        for part in path.split(".")
    }
    blocked = sorted(
        forbidden
        for forbidden in FORBIDDEN_KEY_PARTS
        if any(forbidden in segment for segment in segments)
    )
    if blocked:
        raise ScaffoldError(f"{label} uses a forbidden personal/contact field: {blocked[0]}")
    return path


def parse_identity_options(values: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    options: list[tuple[str, ...]] = []
    for index, raw in enumerate(values, start=1):
        fields = tuple(part.strip() for part in raw.split(",") if part.strip())
        if not fields:
            raise ScaffoldError(f"identity option {index} is empty")
        for field in fields:
            _validate_field_path(field, label=f"identity option {index}")
        if "$payload_hash" in fields and fields != ("$payload_hash",):
            raise ScaffoldError("$payload_hash must be the only field in its identity option")
        if len(fields) != len(set(fields)):
            raise ScaffoldError(f"identity option {index} contains duplicate fields")
        options.append(fields)
    if not options:
        raise ScaffoldError("at least one identity option is required")
    if len(options) != len(set(options)):
        raise ScaffoldError("identity options must be unique")
    return tuple(options)


def validate_spec(spec: ScaffoldSpec) -> ScaffoldSpec:
    if not SOURCE_ID_PATTERN.fullmatch(spec.source_id):
        raise ScaffoldError("source_id must match ^[a-z][a-z0-9_]*$")
    if not TRANSPORT_PATTERN.fullmatch(spec.transport):
        raise ScaffoldError("transport must match ^[a-z][a-z0-9_]*$")
    if not TRANSPORT_PATTERN.fullmatch(spec.driver):
        raise ScaffoldError("driver_name must match ^[a-z][a-z0-9_]*$")
    if (
        not spec.dataset_key
        or spec.dataset_key != spec.dataset_key.strip()
        or len(spec.dataset_key) > 200
        or any(character in spec.dataset_key for character in ("/", "\\", "\r", "\n", "\0"))
    ):
        raise ScaffoldError(
            "dataset_key must be 1-200 characters without slashes, control characters, or edge spaces"
        )
    if not spec.grain_th.strip():
        raise ScaffoldError("grain_th must explain what one record represents")
    if not spec.identity_options:
        raise ScaffoldError("at least one identity option is required")
    parse_identity_options([",".join(option) for option in spec.identity_options])
    for label, fields in (
        ("geography field", spec.geography_fields),
        ("as-of field", spec.as_of_fields),
    ):
        if len(fields) != len(set(fields)):
            raise ScaffoldError(f"{label}s must be unique")
        for field in fields:
            if field == "$payload_hash":
                raise ScaffoldError(f"{label} cannot be $payload_hash")
            _validate_field_path(field, label=label)
    return spec


def _set_fixture_path(payload: dict, path: str, value: str) -> None:
    current = payload
    parts = path.split(".")
    for part in parts[:-1]:
        existing = current.get(part)
        if existing is None:
            existing = {}
            current[part] = existing
        if not isinstance(existing, dict):
            raise ScaffoldError(f"fixture field paths conflict at {path!r}")
        current = existing
    existing = current.get(parts[-1])
    if isinstance(existing, dict):
        raise ScaffoldError(f"fixture field paths conflict at {path!r}")
    current.setdefault(parts[-1], value)


def _fixture_payload(spec: ScaffoldSpec) -> dict:
    payload: dict = {}
    first_identity = spec.identity_options[0]
    if first_identity == ("$payload_hash",):
        payload["example_value"] = "sample"
    else:
        for index, field in enumerate(first_identity, start=1):
            _set_fixture_path(payload, field, f"example-{index}")
    for field in spec.geography_fields:
        _set_fixture_path(payload, field, "จังหวัดตัวอย่าง")
    for field in spec.as_of_fields:
        _set_fixture_path(payload, field, "2026-01-01")
    if sanitize_payload(payload) != payload:
        raise ScaffoldError("generated fixture contains a field rejected by runtime privacy rules")
    return payload


def _render_template(path: Path, replacements: dict[str, str]) -> str:
    try:
        rendered = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScaffoldError(f"cannot read template {path}: {exc}") from exc
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    unresolved = sorted(set(PLACEHOLDER_PATTERN.findall(rendered)))
    if unresolved:
        raise ScaffoldError(f"template {path.name} has unresolved placeholders: {unresolved}")
    return rendered


def _safe_target(root: Path, relative_path: Path) -> Path:
    target = (root / relative_path).resolve()
    if target == root or root not in target.parents:
        raise ScaffoldError(f"generated path escapes repository root: {relative_path}")
    return target


def scaffold_connector(
    spec: ScaffoldSpec,
    *,
    output_root: Path = PROJECT_ROOT,
    template_root: Path = TEMPLATE_ROOT,
    dry_run: bool = False,
) -> list[Path]:
    spec = validate_spec(spec)
    root = output_root.resolve()
    templates = template_root.resolve()
    fixture_relative = Path("tests") / "fixtures" / "connectors" / f"{spec.source_id}.json"
    relative_targets = {
        Path("app") / "connectors" / f"{spec.source_id}.py": "connector.py",
        Path("config") / "connector_contracts" / f"{spec.source_id}.json": "contract.json",
        fixture_relative: "fixture.json",
        Path("tests") / f"test_{spec.source_id}_connector.py": "connector_test.py.tmpl",
    }
    targets = {_safe_target(root, relative): template for relative, template in relative_targets.items()}
    conflicts = sorted(path for path in targets if path.exists())
    if conflicts:
        formatted = ", ".join(str(path.relative_to(root)) for path in conflicts)
        raise ScaffoldError(f"refusing to overwrite existing files: {formatted}")

    fixture_path = fixture_relative.as_posix()
    entrypoint = f"app.connectors.{spec.source_id}:{spec.class_name}"
    json_text = lambda value: json.dumps(value, ensure_ascii=False)
    replacements = {
        "__SOURCE_ID__": spec.source_id,
        "__SOURCE_ID_JSON__": json_text(spec.source_id),
        "__SOURCE_ID_PY__": repr(spec.source_id),
        "__MODULE_NAME__": spec.source_id,
        "__CLASS_NAME__": spec.class_name,
        "__DRIVER_NAME_PY__": repr(spec.driver),
        "__CONNECTOR_ENTRYPOINT_JSON__": json_text(entrypoint),
        "__TRANSPORT_JSON__": json_text(spec.transport),
        "__DATASET_KEY_JSON__": json_text(spec.dataset_key),
        "__DATASET_KEY_PY__": repr(spec.dataset_key),
        "__KEY_PATTERN_JSON__": json_text(f"^{re.escape(spec.dataset_key)}$"),
        "__GRAIN_TH_JSON__": json_text(spec.grain_th.strip()),
        "__IDENTITY_OPTIONS_JSON__": json_text([list(option) for option in spec.identity_options]),
        "__IDENTITY_OPTIONS_PY__": repr(spec.identity_options),
        "__GEOGRAPHY_FIELDS_JSON__": json_text(list(spec.geography_fields)),
        "__AS_OF_FIELDS_JSON__": json_text(list(spec.as_of_fields)),
        "__FIXTURE_PATH_JSON__": json_text(fixture_path),
        "__FIXTURE_PAYLOAD_JSON__": json_text(_fixture_payload(spec)),
    }
    rendered = {
        target: _render_template(templates / template_name, replacements)
        for target, template_name in targets.items()
    }
    if dry_run:
        return sorted(rendered)

    written: list[Path] = []
    created_directories: list[Path] = []
    current_target: Path | None = None
    try:
        for target in sorted(rendered):
            current_target = target
            missing_parents: list[Path] = []
            parent = target.parent
            while parent != root and not parent.exists():
                missing_parents.append(parent)
                parent = parent.parent
            target.parent.mkdir(parents=True, exist_ok=True)
            created_directories.extend(reversed(missing_parents))
            target.write_text(rendered[target], encoding="utf-8", newline="\n")
            written.append(target)
            current_target = None
    except OSError as exc:
        if current_target is not None and current_target not in written:
            current_target.unlink(missing_ok=True)
        for path in reversed(written):
            path.unlink(missing_ok=True)
        for directory in reversed(created_directories):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise ScaffoldError(f"cannot create connector scaffold: {exc}") from exc
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create connector, contract 1.1, redacted fixture, and offline test skeleton."
    )
    parser.add_argument("source_id", help="lower_snake_case source ID already planned for the catalog")
    parser.add_argument("--transport", required=True, help="lower_snake_case transport metadata")
    parser.add_argument("--dataset-key", required=True, help="exact dataset key emitted by the connector")
    parser.add_argument("--grain-th", required=True, help="Thai explanation of what one record represents")
    parser.add_argument(
        "--identity-fields",
        action="append",
        required=True,
        metavar="FIELD[,FIELD]",
        help="one composite identity option; repeat to add fallback options",
    )
    parser.add_argument("--geography-field", action="append", default=[], metavar="FIELD")
    parser.add_argument("--as-of-field", action="append", default=[], metavar="FIELD")
    parser.add_argument("--driver", help="connector driver name; defaults to source_id")
    parser.add_argument("--dry-run", action="store_true", help="show target files without writing")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        spec = ScaffoldSpec(
            source_id=args.source_id,
            transport=args.transport,
            dataset_key=args.dataset_key,
            grain_th=args.grain_th,
            identity_options=parse_identity_options(args.identity_fields),
            geography_fields=tuple(args.geography_field),
            as_of_fields=tuple(args.as_of_field),
            driver_name=args.driver,
        )
        created = scaffold_connector(spec, dry_run=args.dry_run)
    except ScaffoldError as exc:
        parser.exit(2, f"error: {exc}\n")

    prefix = "would create" if args.dry_run else "created"
    for path in created:
        print(f"{prefix}: {path.relative_to(PROJECT_ROOT)}")
    if not args.dry_run:
        print("next: edit parser/completeness checks, then add catalog + ingestion plan in a reviewed PR")
        print("next: run python -m app.cli validate-pipeline and python -m pytest -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
