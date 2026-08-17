from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import PublicArtifact
from app.public_artifacts import artifact_inputs, sync_public_artifacts


def test_public_artifact_sync_is_complete_and_idempotent():
    with TestClient(app) as client:
        with SessionLocal() as session:
            count = session.scalar(select(func.count()).select_from(PublicArtifact))
            assert count == len(artifact_inputs()) == 163
            second_sync = sync_public_artifacts(session)
            assert second_sync == {
                "expected": 163,
                "inserted": 0,
                "updated": 0,
                "unchanged": 163,
            }

        coverage = client.get("/api/public/v1/database-coverage")
        assert coverage.status_code == 200
        payload = coverage.json()
        assert payload["status"] == "complete"
        assert payload["source_catalog_rows"] == 28
        assert payload["endpoint_catalog_rows"] == 144
        assert payload["runtime_enabled_endpoints"] == 94
        assert payload["province_briefings"] == 77
        assert payload["executive_summaries"] == 77
        assert payload["restricted_values_published"] == 0


def test_public_api_reads_the_serving_database_before_file_fallback():
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
