from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.catalog import load_catalog
from app.database import SessionLocal
from app.main import app
from app.models import PublicArtifact
from app.public_artifacts import (
    ArtifactInput,
    REQUIRED_ARTIFACT_COUNT,
    REQUIRED_GROUP_COUNTS,
    artifact_inputs,
    required_group_counts,
    sync_public_artifacts,
    validate_public_artifacts,
)


def test_public_artifact_sync_is_complete_and_idempotent():
    expected_artifacts = len(artifact_inputs())
    catalog = load_catalog()
    catalog_sources = catalog["sources"]
    with TestClient(app) as client:
        with SessionLocal() as session:
            count = session.scalar(select(func.count()).select_from(PublicArtifact))
            assert count == expected_artifacts == REQUIRED_ARTIFACT_COUNT
            second_sync = sync_public_artifacts(session)
            assert second_sync == {
                "expected": expected_artifacts,
                "inserted": 0,
                "updated": 0,
                "unchanged": expected_artifacts,
            }

        coverage = client.get("/api/public/v1/database-coverage")
        assert coverage.status_code == 200
        payload = coverage.json()
        assert payload["status"] == "complete"
        assert payload["source_catalog_rows"] == len(catalog_sources)
        assert payload["endpoint_catalog_rows"] == sum(
            len(source["endpoints"]) for source in catalog_sources
        )
        assert payload["runtime_enabled_endpoints"] == sum(
            endpoint["runtime_enabled"] and not endpoint["restricted"]
            for source in catalog_sources
            for endpoint in source["endpoints"]
        )
        assert payload["province_briefings"] == REQUIRED_GROUP_COUNTS[
            "provincial_briefing"
        ]
        assert payload["executive_summaries"] == REQUIRED_GROUP_COUNTS[
            "executive_summary"
        ]
        assert payload["restricted_values_published"] == 0


def test_public_api_reads_the_serving_database_before_file_fallback():
    expected_artifacts = len(artifact_inputs())
    with TestClient(app) as client:
        marker = "database-serving-proof"
        with SessionLocal() as session:
            artifact = session.get(PublicArtifact, "catalog")
            assert artifact is not None
            payload = dict(artifact.payload)
            payload["warning_th"] = marker
            artifact.payload = payload
            session.add(artifact)
            session.commit()

        overview = client.get("/api/public/v1/overview")
        assert overview.status_code == 200
        assert overview.json()["warning_th"] == marker

        index = client.get("/api/public/v1/artifacts")
        assert index.status_code == 200
        assert len(index.json()) == expected_artifacts
        assert any(row["artifact_key"] == "learning-dashboard" for row in index.json())

        generic_artifact = client.get("/api/public/v1/artifacts/learning-dashboard")
        assert generic_artifact.status_code == 200
        assert generic_artifact.json()["source"]["source_id"] == "f2_learning_dashboard"

        missing = client.get("/api/public/v1/artifacts/not-found")
        assert missing.status_code == 404


def test_public_artifact_manifest_can_add_a_reviewed_source_dataset(tmp_path):
    (tmp_path / "example.json").write_text('{"items":[{"id":1}]}', encoding="utf-8")
    (tmp_path / "serving_manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "artifacts": [
                    {
                        "key": "source/example",
                        "group": "source_dataset",
                        "path": "example.json",
                        "source_ids": ["f2_learning_dashboard"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    inputs = artifact_inputs(tmp_path, enforce_core=False)

    assert [item.key for item in inputs] == ["source/example"]
    assert inputs[0].source_ids == ("f2_learning_dashboard",)
    assert required_group_counts(tmp_path, enforce_core=False) == {"source_dataset": 1}
    assert REQUIRED_GROUP_COUNTS["provincial_briefing"] == 77
    with pytest.raises(RuntimeError, match="public serving core is incomplete"):
        artifact_inputs(tmp_path)


def test_public_artifact_manifest_rejects_path_traversal(tmp_path):
    (tmp_path / "serving_manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "artifacts": [
                    {
                        "key": "escape",
                        "group": "source_dataset",
                        "path": "../secret.json",
                        "source_ids": ["f2_learning_dashboard"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="stay under data/public"):
        artifact_inputs(tmp_path, enforce_core=False)


def _write_manifest(tmp_path, entry):
    (tmp_path / "example.json").write_text('{"items":[]}', encoding="utf-8")
    (tmp_path / "serving_manifest.json").write_text(
        json.dumps({"manifest_version": "1.0", "artifacts": [entry]}),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (
            {"key": "example", "group": "catalog", "path": "example.json", "typo": True},
            "unexpected fields",
        ),
        (
            {
                "key": "a" * 201,
                "group": "catalog",
                "path": "example.json",
                "source_ids": ["f2_learning_dashboard"],
            },
            "exceeds 200",
        ),
        (
            {"key": "example", "group": "a" * 61, "path": "example.json"},
            "exceeds 60",
        ),
        (
            {"key": "example", "group": "source_dataset", "path": "example.json"},
            "source_ids is required for a non-core artifact",
        ),
        (
            {"key": "example", "group": "other", "path": "example.json"},
            "source_ids is required for a non-core artifact",
        ),
        (
            {
                "key": "example",
                "group": "source_dataset",
                "path": "example.json",
                "source_ids": ["f3_healthcare_nonthaburi"],
            },
            "non-approved sources",
        ),
    ],
)
def test_public_artifact_manifest_rejects_unsafe_entries(tmp_path, entry, message):
    _write_manifest(tmp_path, entry)

    with pytest.raises(RuntimeError, match=message):
        artifact_inputs(tmp_path, enforce_core=False)


def test_province_core_glob_requires_codes_from_stems(tmp_path):
    province_dir = tmp_path / "briefings"
    province_dir.mkdir()
    (province_dir / "10.json").write_text("{}", encoding="utf-8")
    _write_manifest(
        tmp_path,
        {
            "key_template": "province/{stem}/briefing",
            "group": "provincial_briefing",
            "path_glob": "briefings/*.json",
            "expected_count": 1,
        },
    )

    with pytest.raises(RuntimeError, match="province_code_from must be stem"):
        artifact_inputs(tmp_path, enforce_core=False)


def test_public_artifact_manifest_rejects_unknown_top_level_fields(tmp_path):
    (tmp_path / "serving_manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "artifacts": [],
                "typo": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="unexpected fields"):
        artifact_inputs(tmp_path, enforce_core=False)


@pytest.mark.parametrize(
    "payload",
    [
        {"items": [{"email": "redacted"}]},
        {"items": [{"note": "email: person@example.test"}]},
        {"items": [{"note": "โทรศัพท์: 081-234-5678"}]},
        {"items": [{"value": "0812345678"}]},
        {"items": [{"note": "บ้านเลขที่ 1"}]},
        {"items": [{"source_id": "f3_healthcare_nonthaburi"}]},
    ],
)
def test_generic_public_artifact_policy_rejects_private_or_restricted_values(
    tmp_path, payload
):
    artifact_path = tmp_path / "candidate.json"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    item = ArtifactInput("candidate", "source_dataset", artifact_path)

    with pytest.raises(RuntimeError, match="public artifact policy rejected"):
        validate_public_artifacts([item])


def test_restricted_ids_are_allowed_only_in_explicit_audit_path(tmp_path):
    allowed_path = tmp_path / "allowed.json"
    allowed_path.write_text(
        json.dumps(
            {
                "quality": {
                    "restricted_source_ids_excluded": ["f3_healthcare_nonthaburi"]
                }
            }
        ),
        encoding="utf-8",
    )
    allowed = ArtifactInput(
        "province/10/briefing",
        "provincial_briefing",
        allowed_path,
        "10",
    )
    assert validate_public_artifacts([allowed])

    leaked_path = tmp_path / "leaked.json"
    leaked_path.write_text(
        json.dumps({"sections": {"source_id": "f3_healthcare_nonthaburi"}}),
        encoding="utf-8",
    )
    leaked = ArtifactInput(
        "province/10/briefing",
        "provincial_briefing",
        leaked_path,
        "10",
    )
    with pytest.raises(RuntimeError, match="restricted source identifier"):
        validate_public_artifacts([leaked])
