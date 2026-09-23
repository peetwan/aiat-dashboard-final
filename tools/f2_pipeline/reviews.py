"""Fail-closed validation for private, hash-locked F2 review inputs."""
from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .common import PipelineError, digest, load_json, local_path


def _pointer(document: Any, pointer: str) -> Any:
    current = document
    for token in pointer.lstrip("/").split("/") if pointer.lstrip("/") else ():
        token = token.replace("~1", "/").replace("~0", "~")
        try:
            current = current[int(token)] if isinstance(current, list) else current[token]
        except (IndexError, KeyError, ValueError, TypeError) as exc:
            raise PipelineError("Review evidence JSON pointer does not resolve") from exc
    return current


def _evidence_index(lock: dict, root: Path) -> dict[tuple[str, str, str], Path]:
    if lock.get("schema_version") != 1 or not isinstance(lock.get("sources"), list):
        raise PipelineError("Unsupported evidence lock")
    result = {}
    for source in lock["sources"]:
        source_id, run_id = source.get("source_id"), source.get("run_id")
        if not source_id or not run_id or source.get("relative_dir") != f"{source_id}/{run_id}":
            raise PipelineError("Invalid evidence source identity")
        for item in source.get("files", []):
            name = item.get("path")
            if not name or item.get("kind") != "evidence":
                continue
            key = (source_id, run_id, name)
            if key in result:
                raise PipelineError("Duplicate locked evidence binding")
            path = local_path(root, f"{source['relative_dir']}/{name}")
            if not path.is_file() or digest(path) != item.get("sha256"):
                raise PipelineError("Locked review evidence bytes changed")
            result[key] = path
    return result


def _strings(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


def _evidence_uri(value: str) -> tuple[tuple[str, str, str], str] | None:
    if not value.startswith("evidence://"):
        return None
    base, marker, pointer = value.partition("#")
    parts = base[len("evidence://"):].split("/")
    # Lock metadata documents the URI grammar literally.  It is not a binding.
    if value in {"evidence://<source_id>/<run_id>/<file>", "evidence://<source_id>/<run_id>/<file>#<json-pointer>"}:
        return None
    if len(parts) != 3 or not all(parts):
        raise PipelineError("Malformed review evidence URI")
    return (parts[0], parts[1], parts[2]), pointer if marker else ""


def _document(path: Path, cache: dict[Path, Any]) -> Any:
    if path not in cache:
        try:
            raw = gzip.open(path, "rt", encoding="utf-8").read() if path.suffix == ".gz" else path.read_text(encoding="utf-8")
            cache[path] = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PipelineError("Review evidence is not readable JSON") from exc
    return cache[path]


def _entry_counts(payload: Any) -> tuple[int, Counter[str], dict[str, int]]:
    if not isinstance(payload, dict):
        return 0, Counter(), {}
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        raise PipelineError("Review candidates must be a list")
    statuses = Counter(row.get("status", "") for row in candidates if isinstance(row, dict))
    return len(candidates), statuses, {
        "identity_decision_count": len(payload.get("identity_decisions", [])),
        "relationship_count": len(payload.get("relationships", [])),
        "aggregate_claim_count": len(payload.get("aggregate_claims", [])),
    }


def validate_review_inputs(
    lock_paths: list[Path], review_root: Path, evidence_lock: dict, evidence_root: Path, inventory: dict
) -> dict:
    """Verify private review ledgers and their declared immutable/rebuild references.

    ``evidence://`` bindings are fully resolved against local, hash-locked evidence.
    ``normalized://`` bindings are checked only against the inventory's producer
    declarations: they intentionally describe future rebuild products.
    """
    review_root, evidence_root = Path(review_root), Path(evidence_root)
    evidence = _evidence_index(evidence_lock, evidence_root)
    declared_normalized = set(inventory.get("normalized_producer_declarations", []))
    if not declared_normalized:
        raise PipelineError("Inventory lacks normalized producer declarations")
    documents: dict[Path, Any] = {}
    seen_runtime, summary_statuses = set(), Counter()
    summary = {"locks": 0, "runtime_files": 0, "evidence_bindings": 0, "resolved_evidence_locators": 0, "normalized_references": 0, "semantic_references": 0, "candidate_count": 0, "disposition_counts": {}}
    for requested_lock in lock_paths:
        lock_path = Path(requested_lock)
        if not lock_path.is_absolute():
            lock_path = local_path(review_root, lock_path.as_posix())
        lock = load_json(lock_path)
        if lock.get("schema_version") != 1 or not isinstance(lock.get("entries"), list):
            raise PipelineError("Unsupported review lock")
        summary["locks"] += 1
        for entry in lock["entries"]:
            relative = entry.get("runtime_path")
            if not isinstance(relative, str) or relative in seen_runtime:
                raise PipelineError("Duplicate or missing runtime review path")
            if ".scratch" in Path(relative).parts:
                raise PipelineError("Scratch review input is prohibited")
            runtime = local_path(review_root, relative)
            if not runtime.is_file() or runtime.stat().st_size != entry.get("runtime_size") or digest(runtime) != entry.get("runtime_sha256"):
                raise PipelineError("Private review ledger changed")
            seen_runtime.add(relative)
            payload = load_json(runtime)
            count, statuses, counts = _entry_counts(payload)
            for key, actual in {"candidate_count": count, **counts}.items():
                if key in entry and entry[key] != actual:
                    raise PipelineError("Review ledger row count differs from lock")
            if "candidate_status_counts" in entry and entry["candidate_status_counts"] != dict(sorted(statuses.items())):
                raise PipelineError("Review ledger disposition totals differ from lock")
            summary["runtime_files"] += 1
            summary["candidate_count"] += count
            summary_statuses.update(statuses)
            for value in _strings(payload):
                if ".scratch/" in value or value.startswith(("derived/", "/Users/", "external/")):
                    raise PipelineError("Review has a prohibited external dependency")
                reference = _evidence_uri(value)
                if reference:
                    key, pointer = reference
                    if key not in evidence:
                        raise PipelineError("Unknown review evidence binding")
                    summary["evidence_bindings"] += 1
                    if pointer:
                        _pointer(_document(evidence[key], documents), pointer)
                        summary["resolved_evidence_locators"] += 1
                elif value.startswith("normalized://"):
                    if value.split("#", 1)[0] not in declared_normalized:
                        raise PipelineError("Unknown normalized producer reference")
                    summary["normalized_references"] += 1
                elif value.startswith("data/"):
                    parts = value.split("/")
                    if len(parts) < 3 or not parts[1].isdigit():
                        raise PipelineError("Review has an unrebased data path")
                    summary["semantic_references"] += 1
    summary["disposition_counts"] = dict(sorted(summary_statuses.items()))
    return summary
