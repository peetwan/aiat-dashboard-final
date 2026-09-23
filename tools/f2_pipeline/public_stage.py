"""Validate staged F2 artifacts without changing active publication files."""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from app.publication import load_contracts, validate_workspace, write_receipt

from .common import (
    PipelineError,
    canonical_json,
    digest,
    load_json,
    local_path,
    write_json,
)
from .comparison_review import verify_comparison_review
from .full_projection import build_full_projection
from .field_approval import (
    validate_c02_field_review,
    validate_c02_geography_review,
    validate_detail_owner_approval,
    validate_embedded_detail_owner_approval,
)


def verify_public_stage(
    directory: Path,
    *,
    expected_review: dict | None = None,
    policy_sha256: str | None = None,
    policy: dict | None = None,
) -> dict:
    """Check structural consistency; field approval never authorizes promotion."""
    directory = Path(directory)
    manifest = load_json(directory / "manifest.json")
    if not isinstance(manifest, dict):
        raise PipelineError("Expected a validated full F2 stage awaiting owner review")
    embedded_approval = validate_embedded_detail_owner_approval(manifest)
    if policy is not None:
        policy_approval = validate_detail_owner_approval(policy)
        if embedded_approval != policy_approval:
            raise PipelineError("Staged field approval differs from projection policy")
    c02_field_review = (
        validate_c02_field_review(policy)
        if policy is not None
        and ("c02_projection" in policy or "c02_field_review" in policy)
        else None
    )
    c02_geography_review = (
        validate_c02_geography_review(policy)
        if c02_field_review is not None
        else None
    )
    if c02_field_review is not None and (
        manifest.get("c02_field_review") != c02_field_review
        or manifest.get("private_revision_id") != policy.get("private_revision_id")
        or (
            c02_geography_review is not None
            and manifest.get("c02_geography_review") != c02_geography_review
        )
    ):
        raise PipelineError("Staged C02 review metadata differs from projection policy")
    if (
        manifest.get("release_id") != "f2-dashboard-snapshot-v3"
        or manifest.get("complete") is not True
        or manifest.get("publication_status") != "staged_for_review"
        or manifest.get("owner_checkpoint_required") is not True
        or manifest.get("validation_status") != "passed"
        or manifest.get("staged_for_review") is not True
        or manifest.get("publication_approval_claimed") is not False
    ):
        raise PipelineError("Expected a validated full F2 stage awaiting owner review")
    snapshots = manifest.get("source_snapshots", {})
    required_snapshot = {
        "source_id",
        "run_id",
        "dataset_key",
        "captured_at",
        "capture_status",
        "price_as_of",
        "price_as_of_status",
    }
    if not isinstance(snapshots, dict) or any(
        not isinstance(snapshot_ref, str)
        or not snapshot_ref
        or not isinstance(snapshot, dict)
        or set(snapshot) != required_snapshot
        or any(
            not isinstance(snapshot.get(key), str) or not snapshot[key]
            for key in ("source_id", "run_id", "dataset_key", "captured_at")
        )
        or snapshot.get("source_id") not in manifest.get("source_ids", [])
        or snapshot.get("capture_status") != "verified_input_manifest"
        or snapshot.get("price_as_of") is not None
        or snapshot.get("price_as_of_status") != "not_reported"
        for snapshot_ref, snapshot in snapshots.items()
    ):
        raise PipelineError("Staged price snapshot metadata is malformed")
    entries = manifest.get("files", [])
    required_entry = {"path", "artifact_key", "size", "sha256", "source_ids"}
    if not isinstance(entries, list) or any(
        not isinstance(entry, dict)
        or not required_entry <= entry.keys()
        or not isinstance(entry["path"], str)
        or not isinstance(entry["artifact_key"], str)
        or type(entry["size"]) is not int
        or entry["size"] < 0
        or not isinstance(entry["sha256"], str)
        or not isinstance(entry["source_ids"], list)
        or any(not isinstance(source, str) for source in entry["source_ids"])
        for entry in entries
    ):
        raise PipelineError("Malformed staged artifact manifest entries")
    names = [entry["path"] for entry in entries]
    keys = [entry["artifact_key"] for entry in entries]
    if not names or len(names) != len(set(names)) or len(keys) != len(set(keys)):
        raise PipelineError("Duplicate or missing staged artifact paths/keys")
    proof = manifest.get("internal_review")
    if (
        not isinstance(proof, dict)
        or proof.get("release_id") != manifest["release_id"]
        or proof.get("scope") != "internal_release_only"
        or proof.get("public_promotion_approved") is not False
        or not all(
            isinstance(proof.get(key), str) and len(proof[key]) == 64
            for key in (
                "release_manifest_sha256",
                "reference_manifest_sha256",
                "comparison_sha256",
                "review_sha256",
            )
        )
        or (expected_review is not None and proof != expected_review)
        or not isinstance(manifest.get("projection_policy_sha256"), str)
        or (
            policy_sha256 is not None
            and manifest["projection_policy_sha256"] != policy_sha256
        )
    ):
        raise PipelineError(
            "Staged artifacts lack the exact internal review/policy binding"
        )
    actual = set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise PipelineError("Staged artifacts must not contain symlinks")
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    if actual != set(names) | {"manifest.json"}:
        raise PipelineError("Staged file set differs from its manifest")
    for entry in entries:
        path = local_path(directory, entry["path"])
        if path.stat().st_size != entry["size"] or digest(path) != entry["sha256"]:
            raise PipelineError("Staged artifact bytes differ from their manifest")
        payload = load_json(path)
        if (
            not isinstance(payload, dict)
            or payload.get("release_id") != manifest["release_id"]
        ):
            raise PipelineError("Mixed release IDs in staged artifacts")
        for key in (
            "publication_status",
            "staged_for_review",
            "owner_checkpoint_required",
            "additional_field_review_status",
            "detail_owner_approval",
            "publication_approval_claimed",
            "internal_review",
            "projection_policy_sha256",
        ):
            if payload.get(key) != manifest.get(key):
                raise PipelineError(
                    "Mixed review or policy metadata in staged artifacts"
                )
        price_artifact = entry["path"] == "topics/k07.json" or entry["path"].startswith(
            "details/k07-"
        )
        if (
            snapshots
            and price_artifact
            and payload.get("source_snapshots") != snapshots
        ):
            raise PipelineError("Price snapshot registry is missing from K07")
        if snapshots and not price_artifact and "source_snapshots" in payload:
            raise PipelineError("Price snapshot registry appears outside K07")
        if not snapshots and "source_snapshots" in payload:
            raise PipelineError("Empty price snapshot registry must not be duplicated")
    required = {"overview.json", "geography.json"} | {
        f"topics/{topic}.json"
        for topic in (
            "k01a",
            "k01b",
            "k02",
            "k03",
            "k04",
            "k05",
            "k06",
            "k07",
            "k08",
            "k09",
            "k10",
            "k11a",
            "k11b",
            "k12",
        )
    }
    if not required <= actual:
        raise PipelineError("Incomplete F2 overview/geography/topic stage")
    return manifest


def staged_serving_entries(manifest: dict) -> list[dict]:
    """Return candidate entries, never modify the active serving manifest."""
    return [
        {
            "key": entry["artifact_key"],
            "group": "source_dataset" if entry["source_ids"] else "methodology",
            "path": "f2/" + entry["path"],
            "source_ids": entry["source_ids"],
        }
        for entry in manifest["files"]
    ]


def make_staged_contract(
    directory: Path, definitions: list[dict], policy: dict
) -> dict:
    """Prepare a fixed contract candidate; refreshes do not regenerate it implicitly."""
    directory = Path(directory)
    manifest = verify_public_stage(
        directory, policy=policy if "staged_for_review" in policy else None
    )
    outputs = []
    for entry in manifest["files"]:
        path = entry["path"]
        payload = load_json(local_path(directory, path))
        if path == "overview.json":
            pointer, identities, count = "/headlines", ["measure_id"], 14
            limit = policy["max_overview_bytes"]
        elif path == "geography.json":
            pointer, identities, count = "/provinces", ["$key"], 77
            limit = policy["max_geography_bytes"]
        elif path.startswith("topics/"):
            pointer, identities = "/items_by_id", ["$key"]
            count = len(payload["items_by_id"])
            limit = policy["max_topic_bytes"]
        elif path.startswith("details/"):
            pointer, identities = "/details_by_id", ["$key"]
            count = len(payload["details_by_id"])
            limit = policy["max_detail_child_bytes"]
        else:
            raise PipelineError("Unknown public output type in F2 contract candidate")
        output = {
            "path": "data/public/f2/" + path,
            "expected_files": 1,
            "format": "json",
            "role": "database",
            "downloadable": True,
            "max_bytes": limit,
            "records_pointer": pointer,
            "identity_fields": identities,
            "expected_count": count,
            "minimum_count": count,
            "max_identity_churn_ratio": 0,
            "schema_policy": "stable",
        }
        if path.startswith(("topics/", "details/")):
            output["field_contexts"] = policy.get("publication_field_contexts", {})
            media_prefixes = {
                source_id: prefixes
                for source_id, prefixes in policy.get(
                    "publication_media_source_prefixes", {}
                ).items()
                if source_id in entry["source_ids"]
            }
            if media_prefixes:
                output["media_source_prefixes"] = media_prefixes
        outputs.append(output)
    outputs.append(
        {
            "path": "data/public/f2/manifest.json",
            "expected_files": 1,
            "format": "json",
            "role": "provenance",
            "downloadable": False,
            "max_bytes": 1048576,
            "schema_policy": "stable",
        }
    )
    return {
        "contract_version": "1.0",
        "contract_id": "f2_dashboard",
        "dataset_key": "f2_dashboard",
        "source_scope": "approved_values",
        "source_ids": manifest["source_ids"],
        "builder": "tools.f2_pipeline.cli:main",
        "grain_th": "ผลตัวชี้วัดตามขอบเขตพื้นที่ และรายละเอียดหน่วยนับที่ผ่านการคัดเลือกฟิลด์",
        "identity": {"result": ["measure_id", "scope_key"], "detail": ["entity_id"]},
        "geography": {
            "level": "national_province_and_separate_source_regions",
            "fields": ["province_code", "scope_key"],
            "note": "77 canonical provinces; unknown geography remains national; overlapping memberships are nonadditive.",
        },
        "as_of": {
            "status": "source_snapshot_specific",
            "fields": ["source_dates", "source_snapshots", "price_as_of"],
            "note": (
                "Capture/run timestamps are snapshot lineage, not price effective "
                "dates. Unknown price as_of remains explicit. No invented year or "
                "calendar-month filter."
            ),
        },
        "measures": [
            {
                "name": row["measure_id"] + ": " + row["label_th"],
                "unit": row["unit"],
                "denominator": row["formula"],
            }
            for row in definitions
        ],
        "completeness": {
            "policy": "output_contracts",
            "needs_review": True,
            "review_items": [
                "Cleaning and scoped owner field approval do not authorize promotion",
                "Separate explicit owner promotion approval is required",
            ],
        },
        "privacy_profile": "aggregate_public",
        "outputs": outputs,
    }


def validate_public_stage(
    directory: Path,
    contract_path: Path,
    repository: Path,
    *,
    release_dir: Path,
    comparison_path: Path,
    review_path: Path,
    include_existing: bool = True,
) -> dict:
    """Exercise the real receipt/publication path in a disposable local workspace."""
    directory, contract_path, repository = map(
        Path, (directory, contract_path, repository)
    )
    proof = verify_comparison_review(release_dir, comparison_path, review_path)
    projection_policy = load_json(Path(release_dir) / "projection_policy.json")
    policy_contract = (
        projection_policy if "staged_for_review" in projection_policy else None
    )
    manifest = verify_public_stage(
        directory,
        expected_review=proof,
        policy_sha256=digest(Path(release_dir) / "projection_policy.json"),
        policy=policy_contract,
    )
    catalog = repository / "config/source_catalog.json"
    with TemporaryDirectory(prefix="f2-publication-overlay-") as temporary:
        root = Path(temporary)
        expected = root / "rederived"
        build_full_projection(release_dir, expected, comparison_proof=proof)
        expected_manifest = verify_public_stage(expected, expected_review=proof)
        if (
            digest(expected / "manifest.json") != digest(directory / "manifest.json")
            or expected_manifest["files"] != manifest["files"]
        ):
            raise PipelineError(
                "Stage differs from deterministic projection of the reviewed release"
            )
        expected_contract = make_staged_contract(
            expected,
            load_json(Path(release_dir) / "definitions.json")["measures"],
            load_json(Path(release_dir) / "projection_policy.json"),
        )
        if canonical_json(load_json(contract_path)) != canonical_json(
            expected_contract
        ):
            raise PipelineError(
                "Staged contract differs from its reviewed release and policy"
            )
        public = root / "data/public"
        contracts = root / "config/publication_contracts"
        public.mkdir(parents=True)
        contracts.mkdir(parents=True)
        if include_existing:
            if (repository / "data/public/f2").exists():
                raise PipelineError(
                    "Existing F2 public data needs an explicit promotion/refresh plan"
                )
            if any(
                path.is_symlink() for path in (repository / "data/public").rglob("*")
            ):
                raise PipelineError("Existing public workspace contains a symlink")
            shutil.copytree(repository / "data/public", public, dirs_exist_ok=True)
            for path in (repository / "config/publication_contracts").glob("*.json"):
                if path.is_symlink():
                    raise PipelineError(
                        "Active publication contract must not be a symlink"
                    )
                shutil.copyfile(path, contracts / path.name)
            serving = load_json(public / "serving_manifest.json")
        else:
            serving = {"manifest_version": "1.0", "artifacts": []}
        shutil.copytree(directory, public / "f2")
        destination = contracts / "f2_dashboard.json"
        if destination.exists():
            raise PipelineError(
                "F2 contract is already active; no implicit replacement"
            )
        shutil.copyfile(contract_path, destination)
        load_contracts(contracts)
        serving["artifacts"].extend(staged_serving_entries(manifest))
        write_json(public / "serving_manifest.json", serving)
        receipt = write_receipt(root, contracts, catalog)
        report = validate_workspace(root, contracts, catalog)
        return {
            **report,
            "release_id": manifest["release_id"],
            "validation_scope": "existing_plus_staged"
            if include_existing
            else "staged_only",
            "receipt_release_digest": receipt["release_digest"],
            "internal_review": proof,
            "derivation_byte_identical_files": len(manifest["files"]) + 1,
            "f2_bytes": sum(entry["size"] for entry in manifest["files"])
            + (directory / "manifest.json").stat().st_size,
            "workspace_bytes": sum(
                path.stat().st_size for path in public.rglob("*") if path.is_file()
            ),
            "active_files_modified": False,
            "owner_promotion_approval_required": True,
        }
