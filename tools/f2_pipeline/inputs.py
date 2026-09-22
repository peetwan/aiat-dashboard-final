"""Validate explicitly pinned local evidence. This module never downloads data."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from .common import (
    PipelineError,
    digest,
    load_json,
    local_path,
    parse_json,
    stream_digest,
)


def validate_manifest(source: dict, directory: Path, exceptions: list[dict]) -> None:
    metadata = source.get("manifest_validation")
    if not metadata:
        raise PipelineError("Source lacks canonical manifest validation metadata")
    manifest = load_json(local_path(directory, metadata["path"]))
    if (
        manifest.get("source_id") != source["source_id"]
        or manifest.get("run_id") != source["run_id"]
    ):
        raise PipelineError("Canonical manifest source/run identity mismatch")
    declared = manifest.get("datasets", []) + manifest.get("extra_files", [])
    names = [row.get("file", row.get("path")) for row in declared]
    if None in names or len(names) != len(set(names)):
        raise PipelineError("Canonical manifest has duplicate or missing filenames")
    locked = {row["path"]: row for row in source["files"]}
    used_exceptions = set()
    for row, name in zip(declared, names):
        if name not in locked:
            raise PipelineError("Canonical manifest references an unlocked file")
        if row["sha256"] == locked[name]["sha256"]:
            continue
        matching = [
            index
            for index, exception in enumerate(exceptions)
            if exception["source_id"] == source["source_id"]
            and exception["run_id"] == source["run_id"]
            and exception["path"] == name
            and exception["original_declared_sha256"] == row["sha256"]
            and exception["actual_pinned_sha256"] == locked[name]["sha256"]
            and exception.get("reason")
            and exception.get("acceptance_reference")
        ]
        if len(matching) != 1:
            raise PipelineError("Undocumented canonical manifest hash mismatch")
        used_exceptions.add(matching[0])
    expected_exceptions = {
        index
        for index, exception in enumerate(exceptions)
        if exception["source_id"] == source["source_id"]
        and exception["run_id"] == source["run_id"]
    }
    if used_exceptions != expected_exceptions:
        raise PipelineError("Unused or stale source integrity exception")


def validate_sources(
    lock: dict, evidence_root: Path, source_ids: list[str] | None = None
) -> list[dict]:
    if lock.get("schema_version") != 1 or not isinstance(lock.get("sources"), list):
        raise PipelineError("Unsupported input lock schema")
    sources = lock["sources"]
    ids = [source.get("source_id") for source in sources]
    if len(ids) != len(set(ids)) or None in ids:
        raise PipelineError("Duplicate or missing source in input lock")
    requested = set(ids if source_ids is None else source_ids)
    if not requested <= set(ids):
        raise PipelineError("Enabled source is absent from input lock")
    manifest_rows = []
    for source in sources:
        source_id, run_id = source["source_id"], source["run_id"]
        if source_id not in requested:
            continue
        if source["relative_dir"] != f"{source_id}/{run_id}":
            raise PipelineError(
                "Locked source/run directory does not match its identity"
            )
        directory = local_path(evidence_root, source["relative_dir"])
        if not directory.is_dir():
            raise PipelineError(f"Missing pinned evidence bundle: {source_id}/{run_id}")
        files = source["files"]
        names = [row["path"] for row in files]
        if len(names) != len(set(names)) or not names:
            raise PipelineError(f"Duplicate or empty file set: {source_id}")
        observed = set()
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise PipelineError(f"Symlink in pinned evidence bundle: {source_id}")
            if path.is_file():
                observed.add(path.relative_to(directory).as_posix())
        if observed != set(names):
            raise PipelineError(
                f"Pinned file set differs: {source_id}; missing={len(set(names) - observed)}, unexpected={len(observed - set(names))}"
            )
        for metadata in files:
            path = local_path(directory, metadata["path"])
            if (
                path.stat().st_size != metadata["size"]
                or digest(path) != metadata["sha256"]
            ):
                raise PipelineError(
                    f"Pinned bytes changed: {source_id}/{metadata['path']}"
                )
            manifest_rows.append(
                {
                    "input_kind": metadata["kind"],
                    "source_id": source_id,
                    "run_id": run_id,
                    "path": f"evidence/{source['relative_dir']}/{metadata['path']}",
                    "sha256": metadata["sha256"],
                    "size": metadata["size"],
                    "dataset_key": metadata.get("dataset_key", ""),
                    "captured_at": metadata.get("captured_at", ""),
                    "originating_system": metadata.get(
                        "originating_system", source.get("originating_system", "")
                    ),
                    "grain": metadata.get("grain", ""),
                }
            )
        validate_manifest(source, directory, lock.get("integrity_exceptions", []))
        # A prepared copy may be in a subdirectory unlike its canonical gzip.
        equivalents = {
            (row["path"], row["canonical_evidence_path"])
            for row in files
            if row.get("canonical_evidence_path")
        }
        equivalents.update(
            (name[:-3], name)
            for name in names
            if name.endswith(".gz") and name[:-3] in names
        )
        for expanded, compressed in sorted(equivalents):
            if compressed not in names or expanded not in names:
                raise PipelineError(
                    "Expanded capture references an unlocked canonical file"
                )
            try:
                with gzip.open(local_path(directory, compressed), "rb") as stream:
                    expanded_hash = stream_digest(stream)
            except (OSError, EOFError) as exc:
                raise PipelineError(
                    f"Invalid gzip evidence: {source_id}/{compressed}"
                ) from exc
            if expanded_hash != digest(local_path(directory, expanded)):
                raise PipelineError(f"Expanded capture differs: {source_id}/{expanded}")
    return manifest_rows


def load_source(
    lock: dict, evidence_root: Path, source_id: str, *, include_support: bool = False
) -> tuple[dict, dict]:
    """Read declared captures; optionally include normalized JSON/JSONL support inputs."""
    source = next(
        (row for row in lock["sources"] if row["source_id"] == source_id), None
    )
    if source is None:
        raise PipelineError("Source is not locked")
    directory = local_path(evidence_root, source["relative_dir"])
    canonical_manifest_path = source.get("manifest_validation", {}).get("path")
    canonical_manifest_key = next(
        (
            row.get("dataset_key")
            for row in source["files"]
            if row["path"] == canonical_manifest_path
        ),
        None,
    )
    datasets, metadata_by_dataset = {}, {}
    for metadata in source["files"]:
        name, dataset_key = metadata["path"], metadata.get("dataset_key")
        is_capture = (
            metadata["kind"] == "evidence"
            or metadata.get("provenance_class")
            == "local_expanded_copy_of_canonical_evidence"
        )
        if not include_support and not is_capture:
            continue
        if not dataset_key or not name.endswith((".json", ".jsonl")):
            continue
        # Composite runs retain source-local manifests as locked evidence. Only the
        # explicitly designated canonical manifest represents a shared dataset key.
        if (
            metadata["kind"] == "manifest"
            and canonical_manifest_key is not None
            and dataset_key == canonical_manifest_key
            and name != canonical_manifest_path
        ):
            continue
        if dataset_key in datasets:
            raise PipelineError(
                f"Multiple expanded captures declared for one dataset: {source_id}/{dataset_key}"
            )
        path = local_path(directory, name)
        # Recheck when consumed, so a change between validation and loading fails.
        if digest(path) != metadata["sha256"]:
            raise PipelineError("Evidence changed after validation")
        if name.endswith(".jsonl"):
            payload = []
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if line.strip():
                    try:
                        payload.append(parse_json(line))
                    except (json.JSONDecodeError, PipelineError) as exc:
                        raise PipelineError(
                            f"Invalid JSONL support record at line {line_number}"
                        ) from exc
        else:
            payload = load_json(path)
        datasets[dataset_key] = payload
        metadata_by_dataset[dataset_key] = {
            **metadata,
            "source_id": source_id,
            "run_id": source["run_id"],
            "file": name,
            "captured_at": metadata.get("captured_at", ""),
            "originating_system": metadata.get(
                "originating_system", source.get("originating_system", "")
            ),
        }
    if not datasets:
        raise PipelineError("Source has no expanded JSON captures")
    return datasets, metadata_by_dataset


def load_build_config(config_path: Path) -> tuple[dict, dict, list[dict]]:
    config_path = Path(config_path).resolve()
    config = load_json(config_path)
    if config.get("schema_version") != 1:
        raise PipelineError("Unsupported release configuration schema")
    if config.get("profile") != "full" or config.get("complete") is not True:
        raise PipelineError("Only complete full F2 release configurations are supported")
    expected_measures = [
        "K01B",
        "K03",
        "K04",
        "C04_LISTED",
        "C02_COMMUNITY",
        "C08_ASSESSED_PEOPLE",
        "C08_INCREASED_PEOPLE",
        "K12",
        "K01A",
        "K05",
        "K07",
        "K02",
        "K06",
        "K08",
        "K09",
        "K10",
        "K11A",
        "K11B",
        "C08_PARTICIPATING",
        "C08_REPORTED_BUSINESSES",
        "C10_ALTERNATIVE",
    ]
    # The earliest complete build lock retains this superseded companion measure.
    if "C02_BROADER" in config.get("enabled_measures", []):
        expected_measures.append("C02_BROADER")
    expected_sources = [
        "f2_apptech_mru",
        "f2_apptech_mtr",
        "f2_cultural_market_civil",
        "f2_culturalmap_university",
        "f2_icommunity",
        "f2_learning_area_based",
        "f2_learning_dashboard",
        "f2_target_household",
    ]
    if sorted(config.get("enabled_measures", [])) != sorted(
        expected_measures
    ) or sorted(config.get("enabled_sources", [])) != sorted(expected_sources):
        raise PipelineError(
            "Release sources/measures differ from the complete implemented scope"
        )
    if config.get("release_id") != "f2-dashboard-snapshot-v3":
        raise PipelineError("Full release must use the exact v3 release identity")
    if config.get("publication_status") != "internal_only":
        raise PipelineError("Full release must be marked internal_only")
    files = config.get("config_files", [])
    names = [row["path"] for row in files]
    if not files or len(names) != len(set(names)):
        raise PipelineError("Invalid configuration lock")
    loaded, rows = {}, []
    for item in files:
        path = local_path(config_path.parent, item["path"])
        if not path.is_file() or digest(path) != item["sha256"]:
            raise PipelineError(
                f"Changed or missing locked configuration: {item['path']}"
            )
        if item.get("role"):
            if item["role"] in loaded:
                raise PipelineError("Duplicate configuration role")
            loaded[item["role"]] = load_json(path)
        rows.append(
            {
                "input_kind": "configuration",
                "source_id": "",
                "run_id": "",
                "path": "config/" + item["path"],
                "sha256": item["sha256"],
                "size": path.stat().st_size,
            }
        )
    required = {
        "input_lock",
        "measures",
        "reviews",
        "dashboard_provinces",
        "projection_policy",
        "source_resolution_lock",
        "migration_inventory",
    }
    if not required <= loaded.keys():
        raise PipelineError("Missing required configuration role")
    rows.append(
        {
            "input_kind": "configuration",
            "source_id": "",
            "run_id": "",
            "path": "config/" + config_path.name,
            "sha256": digest(config_path),
            "size": config_path.stat().st_size,
        }
    )
    return config, loaded, rows
