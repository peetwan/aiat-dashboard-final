from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.reviews import validate_review_inputs


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path: Path):
    evidence_root = tmp_path / "evidence"
    evidence = evidence_root / "source" / "run"
    evidence.mkdir(parents=True)
    raw = json.dumps({"data": [{"value": "synthetic"}]}).encode()
    with gzip.open(evidence / "capture.json.gz", "wb") as stream:
        stream.write(raw)
    evidence_lock = {"schema_version": 1, "sources": [{"source_id": "source", "run_id": "run", "relative_dir": "source/run", "files": [{"path": "capture.json.gz", "sha256": sha(evidence / "capture.json.gz"), "size": (evidence / "capture.json.gz").stat().st_size, "kind": "evidence"}]}]}
    review_root = tmp_path / "review"
    runtime = review_root / "data/runtime/f2/reviews/runtime.json"
    runtime.parent.mkdir(parents=True)
    payload = {"candidates": [{"status": "supported", "evidence": [{"raw_locator": "evidence://source/run/capture.json.gz#/data/0/value"}]}], "identity_decisions": [], "relationships": [], "aggregate_claims": [], "normalized": "normalized://source_local/source-v1/table.csv", "migration": {"source_locator_scheme": "evidence://<source_id>/<run_id>/<file>#<json-pointer>"}}
    runtime.write_text(json.dumps(payload))
    lock = {"schema_version": 1, "entries": [{"runtime_path": "data/runtime/f2/reviews/runtime.json", "runtime_sha256": sha(runtime), "runtime_size": runtime.stat().st_size, "candidate_count": 1, "candidate_status_counts": {"supported": 1}, "identity_decision_count": 0, "relationship_count": 0, "aggregate_claim_count": 0}]}
    lock_path = review_root / "lock.json"
    lock_path.write_text(json.dumps(lock))
    return lock_path, review_root, evidence_lock, evidence_root, {"normalized_producer_declarations": ["normalized://source_local/source-v1/table.csv"]}


def test_validates_hashes_evidence_pointers_and_declared_future_producers(tmp_path):
    args = fixture(tmp_path)
    assert validate_review_inputs([args[0]], *args[1:]) == {"locks": 1, "runtime_files": 1, "evidence_bindings": 1, "resolved_evidence_locators": 1, "normalized_references": 1, "semantic_references": 0, "candidate_count": 1, "disposition_counts": {"supported": 1}}


def test_rejects_unknown_evidence_binding(tmp_path):
    lock_path, review_root, evidence_lock, evidence_root, inventory = fixture(tmp_path)
    runtime = review_root / "data/runtime/f2/reviews/runtime.json"
    payload = json.loads(runtime.read_text())
    payload["candidates"][0]["evidence"][0]["raw_locator"] = "evidence://source/run/missing.json.gz#/data/0"
    runtime.write_text(json.dumps(payload))
    lock = json.loads(lock_path.read_text())
    lock["entries"][0].update(runtime_sha256=sha(runtime), runtime_size=runtime.stat().st_size)
    lock_path.write_text(json.dumps(lock))
    with pytest.raises(PipelineError, match="Unknown review evidence binding"):
        validate_review_inputs([lock_path], review_root, evidence_lock, evidence_root, inventory)
