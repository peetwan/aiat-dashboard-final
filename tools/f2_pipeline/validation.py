"""Fail-closed validation of immutable F2 release files."""

from __future__ import annotations

from pathlib import Path

from .common import PipelineError, digest, load_json, local_path, parse_json, read_csv



def verify_release(directory: Path, *, require_complete: bool = False) -> dict:
    directory = Path(directory)
    manifest = load_json(directory / "manifest.json")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("validation_status") != "passed"
    ):
        raise PipelineError("Release is not validated")
    enabled_measures = manifest.get("enabled_measures", [])
    expected_measure_count = 22 if "C02_BROADER" in enabled_measures else 21
    if require_complete and (
        manifest.get("complete") is not True
        or len(enabled_measures) != expected_measure_count
        or len(set(enabled_measures)) != expected_measure_count
    ):
        raise PipelineError("Incomplete development release cannot be published")
    if (
        not manifest.get("complete")
        and manifest.get("publication_status") != "development_only"
    ):
        raise PipelineError("Incomplete release lacks development-only boundary")
    entries = manifest.get("files", [])
    names = [row["path"] for row in entries]
    if not names or len(names) != len(set(names)):
        raise PipelineError("Invalid release file manifest")
    actual = set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise PipelineError("Release contains symlink")
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    if actual != set(names) | {"manifest.json"}:
        raise PipelineError(
            "Release file set is incomplete or contains undeclared files"
        )
    for entry in entries:
        path = local_path(directory, entry["path"])
        if path.stat().st_size != entry["size"] or digest(path) != entry["sha256"]:
            raise PipelineError(f"Release bytes changed: {entry['path']}")
    return manifest


def load_release_tables(directory: Path) -> dict[str, list[dict]]:
    directory = Path(directory)
    catalog = read_csv(directory / "table_catalog.csv")
    tables = {}
    for spec in catalog:
        path = local_path(directory, spec["path"])
        rows = read_csv(path)
        if len(rows) != int(spec["row_count"]):
            raise PipelineError("Release table row count mismatch")
        for row_number, row in enumerate(rows, 1):
            for key, value in tuple(row.items()):
                if key.endswith("_json") and value:
                    try:
                        row[key] = parse_json(value)
                    except (ValueError, TypeError) as exc:
                        raise PipelineError(
                            f"Invalid release JSON cell: {spec['table']}:{row_number}/{key}"
                        ) from exc
                elif key in {
                    "k12_eligible",
                    "cultural_area_eligible",
                    "additive_to_headline",
                    "reconciles_with_headline",
                }:
                    if value not in {"True", "False"}:
                        raise PipelineError("Invalid release boolean")
                    row[key] = value == "True"
        tables[spec["table"]] = rows
    return tables
