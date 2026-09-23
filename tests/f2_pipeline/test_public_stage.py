import json
import shutil
from pathlib import Path

import pytest

from tools.f2_pipeline.common import (
    PipelineError,
    digest,
    ensure_new_output,
    write_json,
)
from tools.f2_pipeline import public_stage as stage_module
from tools.f2_pipeline import promotion as promotion_module
from tools.f2_pipeline.c02_projection import apply_c02_projection_policy
from tools.f2_pipeline.field_approval import (
    ALL_FIELDS_FIELD_APPROVAL_STATUS,
    APPROVAL_V1_ID,
    APPROVAL_V2_ID,
    C02_ACCEPTED_FIELD_REVIEW_STATUS,
    PARTIAL_FIELD_APPROVAL_STATUS,
    V1_APPROVAL_CONDITIONS,
    V1_APPROVED_DETAIL_MEASURES,
    V2_APPROVAL_CONDITIONS,
    V2_APPROVED_DETAIL_MEASURES,
    approval_scope_sha256,
)
from tools.f2_pipeline.promotion import (
    build_local_promotion,
    verify_local_promotion,
)
from tools.f2_pipeline.public_stage import (
    make_staged_contract,
    staged_serving_entries,
    validate_public_stage,
    verify_public_stage,
)


@pytest.fixture
def public_stage(tmp_path, monkeypatch):
    repository = Path(__file__).resolve().parents[2]
    definitions = json.loads(
        (repository / "config/f2_pipeline/measures.json").read_text()
    )["measures"]
    sources = [
        row["source_id"]
        for row in json.loads(
            (repository / "config/f2_pipeline/source_permissions.json").read_text()
        )["sources"]
    ]
    directory = tmp_path / "stage"
    release = tmp_path / "release"
    policy = {
        key: 1048576
        for key in (
            "max_overview_bytes",
            "max_geography_bytes",
            "max_topic_bytes",
            "max_detail_child_bytes",
        )
    }
    write_json(release / "projection_policy.json", policy)
    write_json(release / "definitions.json", {"measures": definitions})
    proof = {
        "release_id": "f2-dashboard-snapshot-v3",
        "scope": "internal_release_only",
        "public_promotion_approved": False,
        "accepted_differences": 0,
        **{
            key: "a" * 64
            for key in (
                "release_manifest_sha256",
                "reference_manifest_sha256",
                "comparison_sha256",
                "review_sha256",
            )
        },
    }
    paths = {
        "release_dir": release,
        "comparison_path": tmp_path / "comparison.json",
        "review_path": tmp_path / "review.json",
    }
    monkeypatch.setattr(stage_module, "verify_comparison_review", lambda *args: proof)

    def rederive(release_dir, output, *, comparison_proof):
        assert release_dir == release and comparison_proof == proof
        shutil.copytree(directory, output)

    monkeypatch.setattr(stage_module, "build_full_projection", rederive)
    metadata = {
        "release_id": "f2-dashboard-snapshot-v3",
        "complete": True,
        "publication_status": "staged_for_review",
        "owner_checkpoint_required": True,
        "source_ids": sources,
        "staged_for_review": True,
        "additional_field_review_status": "pending_owner_acceptance",
        "publication_approval_claimed": False,
        "internal_review": proof,
        "projection_policy_sha256": digest(release / "projection_policy.json"),
    }
    outputs = {
        "overview.json": {
            **metadata,
            "headlines": [
                {"measure_id": row["measure_id"]}
                for row in definitions
                if row["kind"] == "headline"
            ],
        },
        "geography.json": {
            **metadata,
            "provinces": {
                f"{index:02d}": {"province_code": f"{index:02d}"}
                for index in range(1, 78)
            },
        },
    }
    for topic in sorted({row["topic_id"] for row in definitions}):
        outputs[f"topics/{topic}.json"] = {
            **metadata,
            "topic_id": topic,
            "items_by_id": {},
            "details_by_id": {},
        }
    entries = []
    for path, payload in outputs.items():
        write_json(directory / path, payload)
        key = (
            "f2/topic/" + Path(path).stem
            if path.startswith("topics/")
            else "f2/" + Path(path).stem
        )
        entries.append(
            {
                "path": path,
                "artifact_key": key,
                "source_ids": sources,
                "sha256": digest(directory / path),
                "size": (directory / path).stat().st_size,
            }
        )
    write_json(
        directory / "manifest.json",
        {**metadata, "validation_status": "passed", "files": entries},
    )
    contract_path = tmp_path / "contracts/f2_dashboard.json"
    write_json(contract_path, make_staged_contract(directory, definitions, policy))
    return directory, contract_path, repository, paths


def test_staged_receipt_and_publication_contract_without_active_changes(public_stage):
    directory, contract, repository, paths = public_stage
    active_manifest = (repository / "data/public/serving_manifest.json").read_bytes()
    report = validate_public_stage(
        directory, contract, repository, include_existing=False, **paths
    )
    assert report["status"] == "valid", report["problems"]
    assert report["contract_count"] == 1
    assert report["artifact_count"] == 17
    assert report["active_files_modified"] is False
    assert report["owner_promotion_approval_required"] is True
    completeness = json.loads(contract.read_text())["completeness"]
    assert completeness["needs_review"] is True
    assert completeness["review_items"] == [
        "Cleaning and scoped owner field approval do not authorize promotion",
        "Separate explicit owner promotion approval is required",
    ]
    as_of = json.loads(contract.read_text())["as_of"]
    assert as_of["fields"] == ["source_dates", "source_snapshots", "price_as_of"]
    assert "not price effective dates" in as_of["note"]
    assert "No invented year" in as_of["note"]
    assert report["derivation_byte_identical_files"] == 17
    assert (
        repository / "data/public/serving_manifest.json"
    ).read_bytes() == active_manifest
    assert len(staged_serving_entries(verify_public_stage(directory))) == 16


def test_stage_hash_drift_and_undeclared_files_fail(public_stage):
    directory, _, _, _ = public_stage
    original = (directory / "overview.json").read_bytes()
    (directory / "overview.json").write_bytes(original + b"\n")
    with pytest.raises(PipelineError, match="bytes differ"):
        verify_public_stage(directory)
    (directory / "overview.json").write_bytes(original)
    write_json(directory / "unreviewed.json", {"unexpected": True})
    with pytest.raises(PipelineError, match="file set"):
        verify_public_stage(directory)


def test_rehashed_public_status_cannot_pass_as_an_owner_review_candidate(public_stage):
    directory, _, _, _ = public_stage
    payload = json.loads((directory / "overview.json").read_text())
    payload["publication_approval_claimed"] = True
    write_json(directory / "overview.json", payload)
    manifest = json.loads((directory / "manifest.json").read_text())
    entry = next(row for row in manifest["files"] if row["path"] == "overview.json")
    entry.update(
        sha256=digest(directory / "overview.json"),
        size=(directory / "overview.json").stat().st_size,
    )
    write_json(directory / "manifest.json", manifest)
    with pytest.raises(PipelineError, match="Mixed review"):
        verify_public_stage(directory)


def test_stage_rejects_a_broadened_contract(public_stage):
    directory, contract, repository, paths = public_stage
    changed = json.loads(contract.read_text())
    changed["outputs"][0]["max_bytes"] += 1
    write_json(contract, changed)
    with pytest.raises(PipelineError, match="contract differs"):
        validate_public_stage(
            directory, contract, repository, include_existing=False, **paths
        )


def _approved_promotion_inputs(
    public_stage,
    tmp_path,
    monkeypatch,
    *,
    all_fields=True,
    c02_status=None,
    c02_owner_acceptance=None,
):
    directory, _, _, paths = public_stage
    release = paths["release_dir"]
    comparison = paths["comparison_path"]
    review = paths["review_path"]
    write_json(comparison, {})
    write_json(review, {})
    write_json(release / "manifest.json", {"release_id": "f2-dashboard-snapshot-v3"})
    if c02_status is not None:
        base = json.loads(
            Path("config/f2_pipeline/public_projection_policy.json").read_text()
        )
        extension_name = (
            "c02-projection-policy.accepted-v1.json"
            if c02_status == C02_ACCEPTED_FIELD_REVIEW_STATUS
            else "c02-projection-policy.v2.json"
        )
        extension = json.loads(
            (Path("config/f2_pipeline") / extension_name).read_text()
        )
        evidence = (
            c02_owner_acceptance
            if c02_status == C02_ACCEPTED_FIELD_REVIEW_STATUS
            else None
        )
        policy = apply_c02_projection_policy(base, extension, evidence)
        status = policy["additional_field_review_status"]
    else:
        policy = json.loads((release / "projection_policy.json").read_text())
        measures = (
            V2_APPROVED_DETAIL_MEASURES if all_fields else V1_APPROVED_DETAIL_MEASURES
        )
        conditions = V2_APPROVAL_CONDITIONS if all_fields else V1_APPROVAL_CONDITIONS
        status = (
            ALL_FIELDS_FIELD_APPROVAL_STATUS
            if all_fields
            else PARTIAL_FIELD_APPROVAL_STATUS
        )
        approval_id = APPROVAL_V2_ID if all_fields else APPROVAL_V1_ID
        policy.update(
            staged_for_review=True,
            owner_checkpoint_required=True,
            publication_approval_claimed=False,
            additional_field_review_status=status,
            detail_policies={measure: {} for measure in measures},
            reviewed_label_contexts={},
            excluded_fields=[],
            detail_field_contexts={},
            publication_field_contexts={},
            publication_media_source_prefixes={},
            sources={},
        )
        policy["detail_owner_approval"] = {
            "approval_id": approval_id,
            "status": "accepted",
            "approved_measures": sorted(measures),
            "public_promotion_approved": False,
            "conditions": conditions,
            "scope_sha256": "",
        }
        policy["detail_owner_approval"]["scope_sha256"] = approval_scope_sha256(policy)
    write_json(release / "projection_policy.json", policy)
    manifest = json.loads((directory / "manifest.json").read_text())
    proof = manifest["internal_review"]
    metadata = {
        "additional_field_review_status": status,
        "detail_owner_approval": policy["detail_owner_approval"],
        "projection_policy_sha256": digest(release / "projection_policy.json"),
    }
    for entry in manifest["files"]:
        path = directory / entry["path"]
        payload = json.loads(path.read_text())
        payload.update(metadata)
        write_json(path, payload)
        entry.update(sha256=digest(path), size=path.stat().st_size)
    manifest.update(metadata)
    if c02_status is not None:
        manifest.update(
            private_revision_id=policy["private_revision_id"],
            c02_field_review=policy["c02_field_review"],
        )
    write_json(directory / "manifest.json", manifest)
    reviewed = tmp_path / "reviewed-stage"
    shutil.copytree(directory, reviewed)
    monkeypatch.setattr(
        promotion_module, "verify_comparison_review", lambda *args: proof
    )

    def rederive(release_dir, output, *, comparison_proof):
        assert release_dir == release
        assert comparison_proof == proof
        shutil.copytree(reviewed, output)

    monkeypatch.setattr(promotion_module, "build_full_projection", rederive)
    decision = tmp_path / "promotion-decision.json"
    write_json(
        decision,
        {
            "schema_version": 1,
            "decision_id": "f2-local-promotion-v1",
            "decision_status": "accepted",
            "release_id": "f2-dashboard-snapshot-v3",
            "source_stage_manifest_sha256": digest(directory / "manifest.json"),
            "scope": "local_publication_only",
            "local_publication_approved": True,
            "deployment_approved": False,
        },
    )
    return directory, release, comparison, review, decision


def test_authorized_local_promotion_is_new_explicit_and_content_preserving(
    public_stage, tmp_path, monkeypatch
):
    stage, release, comparison, review, decision = _approved_promotion_inputs(
        public_stage, tmp_path, monkeypatch
    )
    output = tmp_path / "promotion"
    report = build_local_promotion(stage, release, comparison, review, decision, output)
    verified = verify_local_promotion(
        output,
        stage_dir=stage,
        release_dir=release,
        comparison_path=comparison,
        review_path=review,
        decision_path=decision,
    )
    source_manifest = json.loads((stage / "manifest.json").read_text())
    public_manifest = json.loads((output / "data/public/f2/manifest.json").read_text())
    assert report.status == verified.status == "valid"
    assert report.deployment_approved is False
    assert public_manifest["publication_status"] == "approved_local_publication"
    assert public_manifest["staged_for_review"] is False
    assert public_manifest["owner_checkpoint_required"] is False
    assert public_manifest["publication_approval_claimed"] is True
    assert (
        public_manifest["detail_owner_approval"]
        == source_manifest["detail_owner_approval"]
    )
    assert (
        public_manifest["detail_owner_approval"]["public_promotion_approved"] is False
    )
    contract = json.loads(
        (output / "config/publication_contracts/f2_dashboard.json").read_text()
    )
    assert contract["completeness"] == {
        "policy": "output_contracts",
        "needs_review": False,
        "review_items": [],
    }
    serving = json.loads((output / "serving-entries.json").read_text())
    assert len(serving["artifacts"]) == len(source_manifest["files"])
    assert not (output / "data/public/publication_receipt.json").exists()
    attestation = json.loads((output / "promotion-attestation.json").read_text())
    assert attestation["allowed_metadata_changes"] == {
        "all_artifacts": [
            "/publication_status",
            "/staged_for_review",
            "/owner_checkpoint_required",
            "/publication_approval_claimed",
        ],
        "manifest_only": [
            "/files/*/sha256",
            "/files/*/size",
            "/local_promotion",
        ],
    }
    assert attestation["source_candidate"]["stage_manifest_sha256"] == digest(
        stage / "manifest.json"
    )
    for entry in source_manifest["files"]:
        source = json.loads((stage / entry["path"]).read_text())
        published = json.loads((output / "data/public/f2" / entry["path"]).read_text())
        for key in (
            "publication_status",
            "staged_for_review",
            "owner_checkpoint_required",
            "publication_approval_claimed",
        ):
            source.pop(key)
            published.pop(key)
        assert published == source


def test_c02_pending_stage_still_cannot_be_promoted(
    public_stage, tmp_path, monkeypatch
):
    stage, release, comparison, review, decision = _approved_promotion_inputs(
        public_stage,
        tmp_path,
        monkeypatch,
        c02_status="pending_owner_acceptance",
    )

    with pytest.raises(PipelineError, match="Pending C02"):
        build_local_promotion(
            stage,
            release,
            comparison,
            review,
            decision,
            tmp_path / "pending-c02-output",
        )


def test_c02_pending_geography_stage_cannot_be_promoted(
    public_stage, tmp_path, monkeypatch, c02_owner_acceptance
):
    stage, release, comparison, review, decision = _approved_promotion_inputs(
        public_stage,
        tmp_path,
        monkeypatch,
        c02_status=C02_ACCEPTED_FIELD_REVIEW_STATUS,
        c02_owner_acceptance=c02_owner_acceptance,
    )
    monkeypatch.setattr(
        promotion_module,
        "validate_c02_geography_review",
        lambda _policy: {"status": "pending_owner_acceptance"},
    )

    with pytest.raises(PipelineError, match="Pending C02 geography review"):
        build_local_promotion(
            stage,
            release,
            comparison,
            review,
            decision,
            tmp_path / "pending-c02-geography-output",
        )


def test_c02_accepted_stage_requires_local_decision_and_keeps_deployment_disabled(
    public_stage, tmp_path, monkeypatch, c02_owner_acceptance
):
    stage, release, comparison, review, decision = _approved_promotion_inputs(
        public_stage,
        tmp_path,
        monkeypatch,
        c02_status=C02_ACCEPTED_FIELD_REVIEW_STATUS,
        c02_owner_acceptance=c02_owner_acceptance,
    )
    with pytest.raises(PipelineError, match="Cannot read declared JSON"):
        build_local_promotion(
            stage,
            release,
            comparison,
            review,
            tmp_path / "missing-c02-decision.json",
            tmp_path / "missing-c02-decision-output",
        )

    changed = json.loads(decision.read_text())
    changed["deployment_approved"] = True
    write_json(decision, changed)
    with pytest.raises(PipelineError, match="missing, stale, broader"):
        build_local_promotion(
            stage,
            release,
            comparison,
            review,
            decision,
            tmp_path / "deployment-c02-output",
        )

    changed["deployment_approved"] = False
    write_json(decision, changed)
    output = tmp_path / "accepted-c02-output"
    report = build_local_promotion(
        stage, release, comparison, review, decision, output
    )
    assert report.status == "valid"
    public_manifest = json.loads(
        (output / "data/public/f2/manifest.json").read_text()
    )
    assert public_manifest["c02_field_review"]["status"] == "accepted"
    assert public_manifest["local_promotion"]["deployment_approved"] is False


def test_local_promotion_rejects_missing_and_tampered_authorization(
    public_stage, tmp_path, monkeypatch
):
    stage, release, comparison, review, decision = _approved_promotion_inputs(
        public_stage, tmp_path, monkeypatch
    )
    with pytest.raises(PipelineError, match="Cannot read declared JSON"):
        build_local_promotion(
            stage,
            release,
            comparison,
            review,
            tmp_path / "missing-decision.json",
            tmp_path / "missing-output",
        )
    changed = json.loads(decision.read_text())
    changed["source_stage_manifest_sha256"] = "0" * 64
    write_json(decision, changed)
    with pytest.raises(PipelineError, match="missing, stale, broader"):
        build_local_promotion(
            stage,
            release,
            comparison,
            review,
            decision,
            tmp_path / "tampered-output",
        )
    write_json(
        decision,
        {
            "receipt_version": "1.0",
            "release_digest": digest(stage / "manifest.json"),
            "artifact_count": 1,
            "artifacts": [],
        },
    )
    with pytest.raises(PipelineError, match="unexpected schema"):
        build_local_promotion(
            stage,
            release,
            comparison,
            review,
            decision,
            tmp_path / "receipt-output",
        )


def test_local_promotion_rejects_partial_field_approval(
    public_stage, tmp_path, monkeypatch
):
    stage, release, comparison, review, decision = _approved_promotion_inputs(
        public_stage, tmp_path, monkeypatch, all_fields=False
    )
    with pytest.raises(PipelineError, match="all-eight-field"):
        build_local_promotion(
            stage, release, comparison, review, decision, tmp_path / "partial-output"
        )


def test_local_promotion_rejects_rehashed_source_tampering(
    public_stage, tmp_path, monkeypatch
):
    stage, release, comparison, review, decision = _approved_promotion_inputs(
        public_stage, tmp_path, monkeypatch
    )
    overview = json.loads((stage / "overview.json").read_text())
    overview["unreviewed_content"] = True
    write_json(stage / "overview.json", overview)
    manifest = json.loads((stage / "manifest.json").read_text())
    entry = next(row for row in manifest["files"] if row["path"] == "overview.json")
    entry.update(
        sha256=digest(stage / "overview.json"),
        size=(stage / "overview.json").stat().st_size,
    )
    write_json(stage / "manifest.json", manifest)
    with pytest.raises(PipelineError, match="deterministic projection"):
        build_local_promotion(
            stage, release, comparison, review, decision, tmp_path / "tampered-source"
        )


def test_local_promotion_uses_private_verified_snapshot_if_callers_mutate(
    public_stage, tmp_path, monkeypatch
):
    stage, release, comparison, review, decision = _approved_promotion_inputs(
        public_stage, tmp_path, monkeypatch
    )
    expected_overview = json.loads((stage / "overview.json").read_text())
    definitions_path = release / "definitions.json"
    policy_path = release / "projection_policy.json"
    expected_definitions_sha = digest(definitions_path)
    expected_policy_sha = digest(policy_path)
    expected_first_measure = json.loads(definitions_path.read_text())["measures"][0]
    validate_decision = promotion_module._validate_decision

    def mutate_after_verification(path, stage_manifest_sha256):
        overview = json.loads((stage / "overview.json").read_text())
        overview["unverified_late_mutation"] = True
        write_json(stage / "overview.json", overview)
        definitions = json.loads(definitions_path.read_text())
        definitions["measures"][0]["label_th"] = "late mutation"
        write_json(definitions_path, definitions)
        policy = json.loads(policy_path.read_text())
        policy["max_overview_bytes"] += 1
        write_json(policy_path, policy)
        return validate_decision(path, stage_manifest_sha256)

    monkeypatch.setattr(
        promotion_module, "_validate_decision", mutate_after_verification
    )
    output = tmp_path / "snapshot-output"
    build_local_promotion(stage, release, comparison, review, decision, output)
    assert json.loads((output / "data/public/f2/overview.json").read_text()) == {
        **expected_overview,
        "publication_status": "approved_local_publication",
        "staged_for_review": False,
        "owner_checkpoint_required": False,
        "publication_approval_claimed": True,
    }
    contract = json.loads(
        (output / "config/publication_contracts/f2_dashboard.json").read_text()
    )
    assert contract["measures"][0]["name"] == (
        expected_first_measure["measure_id"] + ": " + expected_first_measure["label_th"]
    )
    source = json.loads((output / "promotion-attestation.json").read_text())[
        "source_candidate"
    ]
    assert source["definitions_sha256"] == expected_definitions_sha
    assert source["projection_policy_sha256"] == expected_policy_sha


def test_local_promotion_never_replaces_existing_output(
    public_stage, tmp_path, monkeypatch
):
    stage, release, comparison, review, decision = _approved_promotion_inputs(
        public_stage, tmp_path, monkeypatch
    )
    output = tmp_path / "already-exists"
    output.mkdir()
    with pytest.raises(PipelineError, match="new directory"):
        build_local_promotion(stage, release, comparison, review, decision, output)


def test_promotion_runtime_output_is_limited_to_non_input_lane(tmp_path):
    repository = Path(__file__).resolve().parents[2]
    inputs = tuple(
        tmp_path / name
        for name in ("stage", "release", "comparison", "review", "decision")
    )
    protected = promotion_module._protected_paths(*inputs)
    promotion_output = (
        repository
        / "data/runtime/f2/promotions"
        / f"test-output-not-created-{tmp_path.name}"
    )

    assert ensure_new_output(promotion_output, protected) == promotion_output.absolute()
    with pytest.raises(PipelineError, match="protected input"):
        ensure_new_output(
            repository / "data/runtime/f2/raw/test-output-must-not-exist",
            protected,
        )
