"""Resolve evidence pointers only against validated, injected capture bundles."""

from __future__ import annotations

from ..common import PipelineError

SOURCE_IDS = {
    "apptech_mru": "f2_apptech_mru",
    "rinmp": "f2_apptech_mtr",
    "atlocal": "f2_cultural_market_civil",
    "cultural_map": "f2_culturalmap_university",
    "icommunity": "f2_icommunity",
    "learning_area_based": "f2_learning_area_based",
    "learning_dashboard": "f2_learning_dashboard",
    "pmua_apptech": "f2_target_household",
}


def pointer_value(document, pointer):
    current = document
    for token in pointer.lstrip("/").split("/") if pointer.lstrip("/") else ():
        token = token.replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(current, list):
                if not token.isdigit():
                    raise ValueError("Array pointer must be a nonnegative index")
                current = current[int(token)]
            else:
                current = current[token]
        except (IndexError, KeyError, ValueError, TypeError) as exc:
            raise PipelineError("Domain evidence pointer does not resolve") from exc
    return current


def resolve_evidence(raw_inputs, uri):
    if not isinstance(uri, str) or not uri.startswith("evidence://"):
        raise PipelineError("Domain evidence requires a canonical evidence URI")
    base, _, pointer = uri.partition("#")
    parts = base[len("evidence://") :].split("/", 2)
    if (
        len(parts) != 3
        or not all(parts)
        or any(part in {"..", "."} for part in parts[2].split("/"))
    ):
        raise PipelineError("Malformed domain evidence URI")
    source_id, run_id, filename = parts
    if source_id not in raw_inputs:
        raise PipelineError("Domain evidence source is not supplied")
    bundle = raw_inputs[source_id]
    files = {row["path"]: row for row in bundle.get("files", [])}
    file_entry = files.get(filename)
    candidates = []
    for key, metadata in bundle["metadata"].items():
        if metadata["source_id"] != source_id or metadata["run_id"] != run_id:
            continue
        matches = filename in {
            metadata["file"],
            metadata.get("canonical_evidence_path"),
        }
        if file_entry and file_entry.get("dataset_key") == key:
            matches = True
        if matches:
            candidates.append(key)
    if len(candidates) != 1:
        raise PipelineError("Domain evidence filename is absent or ambiguous")
    return pointer_value(bundle["datasets"][candidates[0]], pointer)


def observation_uri(raw_inputs, source_id, observation):
    bundle = raw_inputs[source_id]
    locator = observation.get("row_locator", "")
    raw_file = observation["raw_file"]
    metadata = list(bundle["metadata"].values())
    if raw_file.startswith("evidence://"):
        base = raw_file.split("#", 1)[0]
    else:
        matches = [row for row in metadata if row["file"] == raw_file]
        if len(matches) != 1:
            raise PipelineError("Observation raw file is not a declared source input")
        row = matches[0]
        base = f"evidence://{source_id}/{row['run_id']}/{row['file']}"
    if not base.startswith(f"evidence://{source_id}/"):
        raise PipelineError("Observation belongs to a different evidence source")
    filename = base.split("/", 4)[-1]
    declared_files = {row["path"]: row for row in bundle.get("files", [])}
    expected_hash = declared_files.get(filename, {}).get("sha256")
    if expected_hash is None:
        expected_hash = next(
            (row["sha256"] for row in metadata if row["file"] == filename), None
        )
    # Learning Area retains the original raw_file_sha256 column; other source
    # producers use file_sha256. Both describe the same declared file bytes.
    observed_hashes = [
        observation[key]
        for key in ("file_sha256", "raw_file_sha256")
        if observation.get(key)
    ]
    if (
        not expected_hash
        or not observed_hashes
        or any(value != expected_hash for value in observed_hashes)
    ):
        raise PipelineError("Observation evidence hash differs from the declared file")
    if locator.startswith("evidence://"):
        if locator.split("#", 1)[0] != base:
            raise PipelineError("Observation pointer and raw file disagree")
        return locator
    return base + "#" + locator.lstrip("#")


def observation_record(raw_inputs, source_id, observation):
    return resolve_evidence(
        raw_inputs, observation_uri(raw_inputs, source_id, observation)
    )
