from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app import f2_data


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE_ROOT = (
    ROOT
    / "data/runtime/f2/public-projections/f2-dashboard-snapshot-v3-c02-review-v2"
)
DEFAULT_CHECKPOINT_ROOT = ROOT / "data/runtime/f2/checkpoints/c02-review-v2"
_C02_MEASURES = {"C02_COMMUNITY"}
_SHA256 = re.compile(r"[0-9a-f]{64}")


class CandidateIntegrityError(AssertionError):
    """The private candidate no longer matches its review metadata."""


def _read_object(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError, TypeError) as error:
        raise CandidateIntegrityError(f"invalid candidate JSON: {path}") from error
    if not isinstance(payload, dict):
        raise CandidateIntegrityError(f"candidate JSON is not an object: {path}")
    return payload, raw


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateIntegrityError(message)


@dataclass
class VerifiedF2Candidate:
    """Test-only reader for a staged F2 candidate with a verified inventory."""

    root: Path
    checkpoint_root: Path
    manifest: dict[str, Any]
    verification: dict[str, Any]
    snapshot: f2_data.RevisionSnapshot
    reads: list[str] = field(default_factory=list)
    _payloads: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def open(
        cls,
        root: Path = DEFAULT_CANDIDATE_ROOT,
        checkpoint_root: Path = DEFAULT_CHECKPOINT_ROOT,
    ) -> "VerifiedF2Candidate":
        root = root.resolve()
        checkpoint_root = checkpoint_root.resolve()
        manifest, manifest_raw = _read_object(root / "manifest.json")
        verification, _ = _read_object(checkpoint_root / "verification.json")
        serving, _ = _read_object(checkpoint_root / "proposed-serving-manifest.json")
        receipt, _ = _read_object(checkpoint_root / "proposed-publication-receipt.json")

        manifest_digest = hashlib.sha256(manifest_raw).hexdigest()
        _require(manifest.get("complete") is True, "candidate is incomplete")
        _require(manifest.get("validation_status") == "passed", "candidate validation did not pass")
        _require(
            manifest.get("publication_status") == "staged_for_review"
            and manifest.get("staged_for_review") is True,
            "candidate is not staged for review",
        )
        _require(
            manifest.get("publication_approval_claimed") is False,
            "test adapter must not load a candidate claiming publication approval",
        )
        c02_review = manifest.get("c02_field_review") or {}
        _require(
            set(c02_review.get("reviewed_measures") or []) == _C02_MEASURES,
            "candidate C02 review scope is inconsistent",
        )
        _require(
            c02_review.get("status") == "pending_owner_acceptance"
            and c02_review.get("public_promotion_approved") is False,
            "candidate unexpectedly claims C02 field acceptance or promotion approval",
        )
        _require(
            verification.get("publication_manifest_sha256") == manifest_digest,
            "verification report does not identify this candidate manifest",
        )
        _require(
            verification.get("status") == "private_candidate_validated"
            and verification.get("semantic_assertions") == "passed",
            "candidate verification status is not usable for integration tests",
        )
        _require(
            verification.get("active_files_modified") is False
            and verification.get("promotion_performed") is False,
            "candidate review crossed the active-publication boundary",
        )

        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise CandidateIntegrityError("candidate has no file inventory")
        by_key: dict[str, dict[str, Any]] = {}
        expected_paths: set[str] = set()
        for item in files:
            if not isinstance(item, dict):
                raise CandidateIntegrityError(
                    "candidate file inventory contains a non-object"
                )
            key = item.get("artifact_key")
            relative = item.get("path")
            digest = item.get("sha256")
            size = item.get("size")
            _require(
                isinstance(key, str)
                and key.startswith("f2/")
                and key not in by_key,
                "candidate artifact key is invalid or duplicated",
            )
            _require(
                isinstance(relative, str)
                and relative not in expected_paths
                and not Path(relative).is_absolute(),
                f"candidate path is invalid or duplicated: {relative}",
            )
            _require(
                isinstance(digest, str) and _SHA256.fullmatch(digest) is not None,
                f"candidate digest is invalid: {key}",
            )
            _require(
                isinstance(size, int) and size >= 0,
                f"candidate size is invalid: {key}",
            )
            artifact_path = (root / relative).resolve()
            try:
                artifact_path.relative_to(root)
            except ValueError as error:
                raise CandidateIntegrityError(
                    f"candidate path escapes its workspace: {relative}"
                ) from error
            raw = artifact_path.read_bytes()
            _require(len(raw) == size, f"candidate size mismatch: {key}")
            _require(
                hashlib.sha256(raw).hexdigest() == digest,
                f"candidate hash mismatch: {key}",
            )
            by_key[key] = dict(item)
            expected_paths.add(relative)

        actual_paths = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*.json")
            if path.name != "manifest.json"
        }
        _require(
            actual_paths == expected_paths,
            "candidate workspace and manifest file inventories disagree",
        )

        serving_entries = {
            item.get("key"): item
            for item in serving.get("artifacts", [])
            if isinstance(item, dict) and str(item.get("key", "")).startswith("f2/")
        }
        _require(
            set(serving_entries) == set(by_key),
            "candidate manifest and proposed serving manifest disagree",
        )
        for key, item in by_key.items():
            _require(
                serving_entries[key].get("path") == f"f2/{item['path']}",
                f"proposed serving path mismatch: {key}",
            )

        receipt_entries = {
            item.get("path"): item
            for item in receipt.get("artifacts", [])
            if isinstance(item, dict)
            and str(item.get("path", "")).startswith("data/public/f2/")
        }
        manifest_receipt = receipt_entries.get("data/public/f2/manifest.json") or {}
        _require(
            manifest_receipt.get("sha256") == manifest_digest
            and manifest_receipt.get("bytes") == len(manifest_raw),
            "proposed receipt does not match the candidate manifest",
        )
        for key, item in by_key.items():
            receipt_item = receipt_entries.get(f"data/public/f2/{item['path']}") or {}
            _require(
                receipt_item.get("sha256") == item["sha256"]
                and receipt_item.get("bytes") == item["size"],
                f"proposed receipt does not match candidate artifact: {key}",
            )

        snapshot = f2_data.RevisionSnapshot(
            revision=manifest_digest,
            release_id=str(manifest.get("release_id", "")),
            release_date=str(manifest.get("release_date", "")),
            files=by_key,
            source_ids=list(manifest.get("source_ids") or []),
        )
        return cls(
            root=root,
            checkpoint_root=checkpoint_root,
            manifest=manifest,
            verification=verification,
            snapshot=snapshot,
        )

    def load_artifact(
        self, snapshot: f2_data.RevisionSnapshot, artifact_key: str
    ) -> dict[str, Any]:
        _require(snapshot == self.snapshot, "candidate adapter received another revision")
        declared = self.snapshot.files.get(artifact_key)
        if declared is None:
            raise CandidateIntegrityError(
                f"undeclared candidate artifact: {artifact_key}"
            )
        self.reads.append(artifact_key)
        cached = self._payloads.get(artifact_key)
        if cached is not None:
            return cached

        payload, raw = _read_object(self.root / str(declared["path"]))
        _require(len(raw) == declared["size"], f"candidate size changed: {artifact_key}")
        _require(
            hashlib.sha256(raw).hexdigest() == declared["sha256"],
            f"candidate hash changed: {artifact_key}",
        )
        _require(
            payload.get("release_id") == self.snapshot.release_id,
            f"candidate artifact has another release id: {artifact_key}",
        )
        self._payloads[artifact_key] = payload
        return payload

    def install(self, monkeypatch: Any) -> None:
        """Replace only the test process's revision and artifact I/O seams."""

        self.reads.clear()
        monkeypatch.setattr(f2_data, "_active_revision", lambda: self.snapshot)
        monkeypatch.setattr(f2_data, "_load_artifact", self.load_artifact)
