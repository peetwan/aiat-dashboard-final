from __future__ import annotations

import copy

import pytest

from tools.f2_pipeline.common import (
    PipelineError,
    digest,
    load_json,
    local_path,
    stable_id,
    write_json,
)
from tools.f2_pipeline.inputs import load_source, validate_sources


def test_locked_bundle_validates_and_changed_bytes_fail(build_inputs):
    fixture = build_inputs()
    assert len(validate_sources(fixture["lock"], fixture["evidence_root"])) == 11
    path = fixture["source_dir"] / "map_inspiration.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(PipelineError, match="Pinned bytes changed"):
        validate_sources(fixture["lock"], fixture["evidence_root"])


@pytest.mark.parametrize(
    "mode", ["missing", "extra", "duplicate", "wrong_source", "symlink"]
)
def test_input_contract_rejects_incomplete_or_misattributed_bundle(build_inputs, mode):
    fixture = build_inputs()
    lock = copy.deepcopy(fixture["lock"])
    source = lock["sources"][0]
    if mode == "missing":
        (fixture["source_dir"] / "team.json").unlink()
    elif mode == "extra":
        (fixture["source_dir"] / "unexpected.json").write_text("{}")
    elif mode == "duplicate":
        source["files"].append(source["files"][0])
    elif mode == "wrong_source":
        source["source_id"] = "another_source"
    else:
        (fixture["source_dir"] / "linked.json").symlink_to(
            fixture["source_dir"] / "team.json"
        )
    with pytest.raises(PipelineError):
        validate_sources(lock, fixture["evidence_root"])


def test_manifest_source_identity_is_not_just_a_file_hash(build_inputs):
    fixture = build_inputs()
    path = fixture["source_dir"] / "manifest.json"
    manifest = load_json(path)
    manifest["source_id"] = "another_source"
    write_json(path, manifest)
    item = next(
        row
        for row in fixture["lock"]["sources"][0]["files"]
        if row["path"] == "manifest.json"
    )
    item.update(sha256=digest(path), size=path.stat().st_size)
    with pytest.raises(PipelineError, match="identity mismatch"):
        validate_sources(fixture["lock"], fixture["evidence_root"])


def test_independently_pinned_gzip_must_expand_to_declared_copy(build_inputs):
    fixture = build_inputs()
    source = fixture["lock"]["sources"][0]
    path = fixture["source_dir"] / "team.json"
    write_json(path, {"changed": True})
    item = next(row for row in source["files"] if row["path"] == path.name)
    item.update(sha256=digest(path), size=path.stat().st_size)
    with pytest.raises(PipelineError, match="Expanded capture differs"):
        validate_sources(fixture["lock"], fixture["evidence_root"])


def test_exact_integrity_exception_is_not_a_source_wide_bypass(build_inputs):
    fixture = build_inputs()
    source = fixture["lock"]["sources"][0]
    path = fixture["source_dir"] / "manifest.json"
    manifest = load_json(path)
    original = manifest["datasets"][0]["sha256"]
    manifest["datasets"][0]["sha256"] = "0" * 64
    write_json(path, manifest)
    manifest_item = next(
        row for row in source["files"] if row["path"] == "manifest.json"
    )
    manifest_item.update(sha256=digest(path), size=path.stat().st_size)
    with pytest.raises(PipelineError, match="Undocumented"):
        validate_sources(fixture["lock"], fixture["evidence_root"])
    fixture["lock"]["integrity_exceptions"] = [
        {
            "source_id": source["source_id"],
            "run_id": source["run_id"],
            "path": manifest["datasets"][0]["file"],
            "original_declared_sha256": "0" * 64,
            "actual_pinned_sha256": original,
            "reason": "Synthetic documented exception",
            "acceptance_reference": "synthetic-review",
        }
    ]
    assert validate_sources(fixture["lock"], fixture["evidence_root"])
    fixture["lock"]["integrity_exceptions"][0]["actual_pinned_sha256"] = "1" * 64
    with pytest.raises(PipelineError, match="Undocumented"):
        validate_sources(fixture["lock"], fixture["evidence_root"])


def test_duplicate_json_keys_and_traversal_fail(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"a": 1, "a": 2}')
    with pytest.raises(PipelineError, match="Duplicate JSON"):
        load_json(path)
    with pytest.raises(PipelineError):
        local_path(tmp_path, "../escape")
    with pytest.raises(PipelineError):
        local_path(tmp_path, ".scratch/decision.json")
    assert stable_id("entity", "x", "y") == stable_id("entity", "x", "y")


def _add_support_rows(fixture, text):
    path = fixture["source_dir"] / "support.jsonl"
    path.write_text(text, encoding="utf-8")
    fixture["lock"]["sources"][0]["files"].append(
        {
            "path": path.name,
            "dataset_key": "support_rows",
            "kind": "support",
            "sha256": digest(path),
            "size": path.stat().st_size,
        }
    )
    return fixture["lock"]["sources"][0]["source_id"]


def test_support_records_require_explicit_loading_and_preserve_json_types(build_inputs):
    fixture = build_inputs()
    source_id = _add_support_rows(
        fixture, '{"id": 1, "eligible": true}\n\n{"id": 2, "eligible": false}\n'
    )
    captures, _ = load_source(fixture["lock"], fixture["evidence_root"], source_id)
    assert "support_rows" not in captures
    captures, metadata = load_source(
        fixture["lock"], fixture["evidence_root"], source_id, include_support=True
    )
    assert captures["support_rows"] == [
        {"id": 1, "eligible": True},
        {"id": 2, "eligible": False},
    ]
    assert metadata["support_rows"]["source_id"] == source_id
    assert metadata["support_rows"]["sha256"] == digest(
        fixture["source_dir"] / "support.jsonl"
    )


@pytest.mark.parametrize(
    "text", ['{"id": 1, "id": 2}\n', '{"value": NaN}\n', '{"broken":\n']
)
def test_jsonl_support_rejects_ambiguous_or_invalid_records(build_inputs, text):
    fixture = build_inputs()
    source_id = _add_support_rows(fixture, text)
    with pytest.raises(PipelineError, match="JSONL support record at line 1"):
        load_source(
            fixture["lock"], fixture["evidence_root"], source_id, include_support=True
        )


def test_distinct_support_files_cannot_silently_share_a_dataset_key(build_inputs):
    fixture = build_inputs()
    source_id = _add_support_rows(fixture, '{"id": 1}\n')
    source = fixture["lock"]["sources"][0]
    second = fixture["source_dir"] / "other.json"
    write_json(second, {"id": 2})
    source["files"].append(
        {
            "path": second.name,
            "dataset_key": "support_rows",
            "kind": "support",
            "sha256": digest(second),
            "size": second.stat().st_size,
        }
    )
    with pytest.raises(PipelineError, match="Multiple expanded captures.*support_rows"):
        load_source(
            fixture["lock"], fixture["evidence_root"], source_id, include_support=True
        )


def test_composite_run_selects_its_explicit_canonical_manifest(build_inputs):
    fixture = build_inputs()
    source = fixture["lock"]["sources"][0]
    nested = fixture["source_dir"] / "nested.manifest.json"
    write_json(nested, {"source_id": "independent-capture"})
    source["files"].insert(
        0,
        {
            "path": nested.name,
            "dataset_key": "capture_manifest",
            "kind": "manifest",
            "sha256": digest(nested),
            "size": nested.stat().st_size,
        },
    )
    captures, metadata = load_source(
        fixture["lock"],
        fixture["evidence_root"],
        source["source_id"],
        include_support=True,
    )
    assert captures["capture_manifest"] == load_json(
        fixture["source_dir"] / "manifest.json"
    )
    assert metadata["capture_manifest"]["file"] == "manifest.json"
    assert "map_inspiration" in captures
