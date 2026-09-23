"""Build and verify an explicitly authorized local-only F2 publication bundle."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator

from .common import (
    PipelineError,
    canonical_json,
    digest,
    local_path,
    load_json,
    output_directory,
    write_json,
)
from .comparison_review import verify_comparison_review
from .field_approval import (
    ALL_FIELDS_FIELD_APPROVAL_STATUS,
    APPROVAL_V2_ID,
    C02_ACCEPTED_FIELD_REVIEW_STATUS,
    validate_c02_field_review,
    validate_c02_geography_review,
    validate_detail_owner_approval,
)
from .full_projection import build_full_projection
from .public_stage import (
    make_staged_contract,
    staged_serving_entries,
    verify_public_stage,
)

_DECISION_KEYS = {
    "schema_version",
    "decision_id",
    "decision_status",
    "release_id",
    "source_stage_manifest_sha256",
    "scope",
    "local_publication_approved",
    "deployment_approved",
}
_RELEASE_ID = "f2-dashboard-snapshot-v3"
_PUBLICATION_STATUS = "approved_local_publication"
_ARTIFACT_METADATA_CHANGES = (
    "/publication_status",
    "/staged_for_review",
    "/owner_checkpoint_required",
    "/publication_approval_claimed",
)


@dataclass(frozen=True)
class PromotionReport:
    release_id: str
    output: str
    publication_status: str
    artifact_count: int
    source_stage_manifest_sha256: str
    publication_manifest_sha256: str
    decision_sha256: str
    unchanged_content_files: int
    deployment_approved: bool
    status: str


@dataclass(frozen=True)
class _VerifiedSource:
    stage_dir: Path
    manifest: dict
    policy: dict
    definitions: list[dict]
    hashes: dict[str, str]


def _encoded(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _write_compact(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_encoded(value))


def _sha256_value(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _validate_decision(path: Path, stage_manifest_sha256: str) -> tuple[dict, str]:
    decision = load_json(path)
    if not isinstance(decision, dict) or set(decision) != _DECISION_KEYS:
        raise PipelineError("Local promotion decision has an unexpected schema")
    if (
        decision.get("schema_version") != 1
        or decision.get("decision_id")
        not in {
            "f2-local-promotion-v1",
            "f2-c02-province-local-promotion-v1",
            "f2-c02-map-local-promotion-v1",
        }
        or decision.get("decision_status") != "accepted"
        or decision.get("release_id") != _RELEASE_ID
        or decision.get("source_stage_manifest_sha256") != stage_manifest_sha256
        or decision.get("scope") != "local_publication_only"
        or decision.get("local_publication_approved") is not True
        or decision.get("deployment_approved") is not False
    ):
        raise PipelineError(
            "Local promotion decision is missing, stale, broader than local publication, or not accepted"
        )
    return decision, digest(path)


def _source_hashes(
    stage_dir: Path,
    release_dir: Path,
    comparison_path: Path,
    review_path: Path,
) -> dict[str, str]:
    return {
        "stage_manifest_sha256": digest(stage_dir / "manifest.json"),
        "release_manifest_sha256": digest(release_dir / "manifest.json"),
        "projection_policy_sha256": digest(release_dir / "projection_policy.json"),
        "definitions_sha256": digest(release_dir / "definitions.json"),
        "comparison_sha256": digest(comparison_path),
        "comparison_review_sha256": digest(review_path),
    }


@contextmanager
def _verified_source(
    stage_dir: Path,
    release_dir: Path,
    comparison_path: Path,
    review_path: Path,
) -> Iterator[_VerifiedSource]:
    hashes = _source_hashes(stage_dir, release_dir, comparison_path, review_path)
    proof = verify_comparison_review(release_dir, comparison_path, review_path)
    policy_path = release_dir / "projection_policy.json"
    policy = load_json(policy_path)
    definitions = load_json(release_dir / "definitions.json").get("measures")
    if not isinstance(definitions, list):
        raise PipelineError("Reviewed release definitions are missing")
    manifest = verify_public_stage(
        stage_dir,
        expected_review=proof,
        policy_sha256=hashes["projection_policy_sha256"],
        policy=policy,
    )
    approval = validate_detail_owner_approval(policy)
    c02_geography_review = None
    if "c02_projection" in policy or "c02_field_review" in policy:
        c02_review = validate_c02_field_review(policy)
        if c02_review.get("status") != C02_ACCEPTED_FIELD_REVIEW_STATUS:
            raise PipelineError(
                "Pending C02 person-field review cannot be promoted without separate authorization"
            )
        c02_geography_review = validate_c02_geography_review(policy)
        if (
            c02_geography_review is not None
            and c02_geography_review.get("status")
            != C02_ACCEPTED_FIELD_REVIEW_STATUS
        ):
            raise PipelineError(
                "Pending C02 geography review cannot be promoted without separate authorization"
            )
    expected_review_status = (
        C02_ACCEPTED_FIELD_REVIEW_STATUS
        if c02_geography_review is not None
        else ALL_FIELDS_FIELD_APPROVAL_STATUS
    )
    if (
        manifest.get("additional_field_review_status") != expected_review_status
        or not isinstance(approval, dict)
        or approval.get("approval_id") != APPROVAL_V2_ID
        or manifest.get("detail_owner_approval") != approval
    ):
        raise PipelineError(
            "Local promotion requires the complete all-eight-field owner-approved stage"
        )
    with TemporaryDirectory(prefix="f2-promotion-rederive-") as temporary:
        expected = Path(temporary) / "stage"
        build_full_projection(release_dir, expected, comparison_proof=proof)
        expected_manifest = verify_public_stage(
            expected,
            expected_review=proof,
            policy_sha256=hashes["projection_policy_sha256"],
            policy=policy,
        )
        if digest(expected / "manifest.json") != hashes[
            "stage_manifest_sha256"
        ] or expected_manifest.get("files") != manifest.get("files"):
            raise PipelineError(
                "Promotion source differs from deterministic projection of the reviewed release"
            )
        if (
            _source_hashes(stage_dir, release_dir, comparison_path, review_path)
            != hashes
        ):
            raise PipelineError("Promotion source changed while it was being verified")
        yield _VerifiedSource(
            stage_dir=expected,
            manifest=expected_manifest,
            policy=policy,
            definitions=definitions,
            hashes=hashes,
        )


def _promoted_payload(payload: dict) -> dict:
    promoted = deepcopy(payload)
    promoted.update(
        publication_status=_PUBLICATION_STATUS,
        staged_for_review=False,
        owner_checkpoint_required=False,
        publication_approval_claimed=True,
    )
    return promoted


def _content_sha256(payload: dict) -> str:
    content = deepcopy(payload)
    for pointer in _ARTIFACT_METADATA_CHANGES:
        content.pop(pointer.removeprefix("/"), None)
    return _sha256_value(content)


def _promoted_contract(stage_dir: Path, definitions: list[dict], policy: dict) -> dict:
    contract = make_staged_contract(stage_dir, definitions, policy)
    contract["completeness"] = {
        "policy": "output_contracts",
        "needs_review": False,
        "review_items": [],
    }
    return contract


def _serving_fragment(manifest: dict) -> dict:
    return {"artifacts": staged_serving_entries(manifest)}


def _attestation(
    *,
    source_hashes: dict[str, str],
    source_manifest: dict,
    publication_manifest_path: Path,
    decision: dict,
    decision_sha256: str,
    file_attestations: list[dict],
) -> dict:
    return {
        "schema_version": 1,
        "attestation_id": "f2-local-promotion-attestation-v1",
        "release_id": _RELEASE_ID,
        "publication_status": _PUBLICATION_STATUS,
        "scope": decision["scope"],
        "local_publication_approved": True,
        "deployment_approved": False,
        "builder": "tools.f2_pipeline.promotion:build_local_promotion",
        "decision_sha256": decision_sha256,
        "source_candidate": {
            **source_hashes,
            "internal_review": source_manifest["internal_review"],
        },
        "publication_manifest_sha256": digest(publication_manifest_path),
        "allowed_metadata_changes": {
            "all_artifacts": list(_ARTIFACT_METADATA_CHANGES),
            "manifest_only": [
                "/files/*/sha256",
                "/files/*/size",
                "/local_promotion",
            ],
        },
        "file_attestations": file_attestations,
    }


def _expected_bundle(
    stage_dir: Path,
    release_dir: Path,
    comparison_path: Path,
    review_path: Path,
    decision_path: Path,
    destination: Path,
) -> PromotionReport:
    with _verified_source(
        stage_dir, release_dir, comparison_path, review_path
    ) as source:
        source_manifest = source.manifest
        source_stage_sha = source.hashes["stage_manifest_sha256"]
        decision, decision_sha = _validate_decision(decision_path, source_stage_sha)
        public_dir = destination / "data/public/f2"
        promoted_entries: list[dict[str, Any]] = []
        file_attestations = []
        for entry in source_manifest["files"]:
            source_path = local_path(source.stage_dir, entry["path"])
            source_payload = load_json(source_path)
            promoted_payload = _promoted_payload(source_payload)
            output_path = local_path(public_dir, entry["path"])
            _write_compact(output_path, promoted_payload)
            promoted_entries.append(
                {
                    **entry,
                    "sha256": digest(output_path),
                    "size": output_path.stat().st_size,
                }
            )
            source_content_sha = _content_sha256(source_payload)
            publication_content_sha = _content_sha256(promoted_payload)
            if source_content_sha != publication_content_sha:
                raise PipelineError(
                    "Promotion changed content outside approved metadata paths"
                )
            file_attestations.append(
                {
                    "path": entry["path"],
                    "source_sha256": entry["sha256"],
                    "publication_sha256": digest(output_path),
                    "unchanged_content_sha256": source_content_sha,
                }
            )
        publication_manifest = _promoted_payload(source_manifest)
        publication_manifest["files"] = promoted_entries
        publication_manifest["local_promotion"] = {
            "decision_id": decision["decision_id"],
            "decision_sha256": decision_sha,
            "source_stage_manifest_sha256": source_stage_sha,
            "scope": decision["scope"],
            "deployment_approved": False,
        }
        manifest_path = public_dir / "manifest.json"
        _write_compact(manifest_path, publication_manifest)
        write_json(
            destination / "config/publication_contracts/f2_dashboard.json",
            _promoted_contract(source.stage_dir, source.definitions, source.policy),
        )
        write_json(
            destination / "serving-entries.json",
            _serving_fragment(source_manifest),
        )
        write_json(
            destination / "promotion-attestation.json",
            _attestation(
                source_hashes=source.hashes,
                source_manifest=source_manifest,
                publication_manifest_path=manifest_path,
                decision=decision,
                decision_sha256=decision_sha,
                file_attestations=file_attestations,
            ),
        )
        return PromotionReport(
            release_id=_RELEASE_ID,
            output=str(destination),
            publication_status=_PUBLICATION_STATUS,
            artifact_count=len(promoted_entries) + 1,
            source_stage_manifest_sha256=source_stage_sha,
            publication_manifest_sha256=digest(manifest_path),
            decision_sha256=decision_sha,
            unchanged_content_files=len(file_attestations),
            deployment_approved=False,
            status="valid",
        )


def _protected_paths(
    stage_dir: Path,
    release_dir: Path,
    comparison_path: Path,
    review_path: Path,
    decision_path: Path,
) -> tuple[Path, ...]:
    repository = Path(__file__).resolve().parents[2]
    return (
        stage_dir,
        release_dir,
        comparison_path,
        review_path,
        decision_path,
        repository / "data/public",
        repository / "data/current",
        repository / "config/publication_contracts",
        repository / "config/f2_pipeline",
        repository / "data/runtime/f2/raw",
        repository / "data/runtime/f2/releases",
        repository / "data/runtime/f2/public-projections",
        repository / "data/runtime/f2/comparisons",
        repository / "data/runtime/f2/checkpoints",
    )


def build_local_promotion(
    stage_dir: Path,
    release_dir: Path,
    comparison_path: Path,
    review_path: Path,
    decision_path: Path,
    output_dir: Path,
) -> PromotionReport:
    """Build a new activation bundle; never modify active public files."""
    paths = tuple(
        map(
            Path,
            (
                stage_dir,
                release_dir,
                comparison_path,
                review_path,
                decision_path,
            ),
        )
    )
    stage_dir, release_dir, comparison_path, review_path, decision_path = paths
    protected = _protected_paths(*paths)
    with output_directory(output_dir, protected) as destination:
        report = _expected_bundle(
            stage_dir,
            release_dir,
            comparison_path,
            review_path,
            decision_path,
            destination,
        )
    return PromotionReport(
        **{**asdict(report), "output": str(Path(output_dir).absolute())}
    )


def verify_local_promotion(
    bundle_dir: Path,
    *,
    stage_dir: Path,
    release_dir: Path,
    comparison_path: Path,
    review_path: Path,
    decision_path: Path,
) -> PromotionReport:
    """Rebuild independently and require every bundle byte to match."""
    bundle_dir = Path(bundle_dir)
    if not bundle_dir.is_dir() or bundle_dir.is_symlink():
        raise PipelineError("Local promotion bundle is missing or not a directory")
    with TemporaryDirectory(prefix="f2-promotion-verify-") as temporary:
        expected = Path(temporary) / "bundle"
        expected.mkdir()
        report = _expected_bundle(
            Path(stage_dir),
            Path(release_dir),
            Path(comparison_path),
            Path(review_path),
            Path(decision_path),
            expected,
        )
        actual_files = {
            path.relative_to(bundle_dir).as_posix()
            for path in bundle_dir.rglob("*")
            if path.is_file()
        }
        expected_files = {
            path.relative_to(expected).as_posix()
            for path in expected.rglob("*")
            if path.is_file()
        }
        if any(path.is_symlink() for path in bundle_dir.rglob("*")):
            raise PipelineError("Local promotion bundle must not contain symlinks")
        if actual_files != expected_files:
            raise PipelineError(
                "Local promotion bundle file set differs from expected output"
            )
        for relative in sorted(expected_files):
            if digest(bundle_dir / relative) != digest(expected / relative):
                raise PipelineError(f"Local promotion bundle differs at {relative}")
    return PromotionReport(**{**asdict(report), "output": str(bundle_dir.absolute())})
