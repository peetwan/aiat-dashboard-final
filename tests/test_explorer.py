from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.catalog import sync_catalog
from app.database import SessionLocal
from app.models import PublicArtifact
from explorer.main import _safe_json_preview, app
from explorer.source_profiles import SOURCE_PROFILES, validate_profile_coverage


ROOT = Path(__file__).resolve().parents[1]


def seed_catalog() -> None:
    with SessionLocal() as session:
        sync_catalog(session)


def test_source_profiles_cover_the_full_catalog() -> None:
    catalog = json.loads((ROOT / "config/source_catalog.json").read_text(encoding="utf-8"))
    source_ids = {item["source_id"] for item in catalog["sources"]}
    validate_profile_coverage(source_ids)
    assert len(SOURCE_PROFILES) == 28


def test_explorer_health_and_overview_read_live_database() -> None:
    seed_catalog()
    with TestClient(app) as client:
        health = client.get("/health")
        overview = client.get("/api/overview")

    assert health.status_code == 200
    assert health.json()["database"] == "connected"
    assert health.json()["source_total"] == 28
    assert overview.status_code == 200
    assert overview.json()["source_total"] == 28
    assert overview.json()["public_candidate_sources"] == 11
    assert overview.json()["metadata_only_sources"] == 12
    assert overview.json()["restricted_sources"] == 5


def test_explorer_sources_explain_data_and_grain_for_all_28_sources() -> None:
    seed_catalog()
    with TestClient(app) as client:
        response = client.get("/api/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_count"] == 28
    assert len(payload["sources"]) == 28
    assert all(item["what_we_use_th"] for item in payload["sources"])
    assert all(item["grain_th"] for item in payload["sources"])
    assert all(item["database_targets"] for item in payload["sources"])
    assert payload["policy_counts"] == {
        "metadata_only": 12,
        "team_approved_public": 11,
        "restricted_local_only": 5,
    }


def test_explorer_schema_lists_current_nine_serving_tables_without_payloads() -> None:
    seed_catalog()
    with TestClient(app) as client:
        response = client.get("/api/schema")

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_only"] is True
    assert len(payload["tables"]) == 9
    assert all(item["role_th"] for item in payload["tables"])
    assert all(item["key_fields"] for item in payload["tables"])
    assert {item["name"] for item in payload["tables"]} == {
        "sources",
        "endpoints",
        "ingestion_runs",
        "dashboard_records",
        "public_artifacts",
        "spatial_layer_snapshots",
        "spatial_features",
        "housing_demand_snapshots",
        "housing_demand_records",
    }
    assert "payload" not in response.text


def test_data_preview_returns_only_safe_physical_rows_and_supports_source_filter() -> None:
    seed_catalog()
    with TestClient(app) as client:
        source_preview = client.get(
            "/api/data-preview/sources",
            params={"source_id": "f1_sradss_ppaos", "limit": 3},
        )
        staging_preview = client.get("/api/data-preview/dashboard_records", params={"limit": 3})
        missing_preview = client.get("/api/data-preview/not_a_table")

    assert source_preview.status_code == 200
    payload = source_preview.json()
    assert payload["safe_preview"] is True
    assert payload["source_filter_applied"] is True
    assert payload["physical_row_count"] == 1
    assert payload["rows"][0]["source_id"] == "f1_sradss_ppaos"
    assert "payload" not in source_preview.text
    assert "request_template" not in source_preview.text
    assert "evidence_path" not in source_preview.text
    assert staging_preview.status_code == 200
    assert "payload" not in staging_preview.text
    assert missing_preview.status_code == 404


def test_json_preview_is_bounded_and_hides_sensitive_values() -> None:
    preview, truncated = _safe_json_preview(
        {
            "indicator_name": "จำนวนตัวอย่าง",
            "email": "sensitive",
            "nested": {"phone": "sensitive", "values": list(range(20))},
        }
    )

    assert preview["indicator_name"] == "จำนวนตัวอย่าง"
    assert preview["email"] == "[hidden]"
    assert preview["nested"]["phone"] == "[hidden]"
    assert "sensitive" not in json.dumps(preview)
    assert truncated is True


def test_artifact_gallery_lists_metadata_and_returns_safe_json_preview() -> None:
    artifact_key = "__test_safe_json_gallery__"
    with SessionLocal() as session:
        session.merge(
            PublicArtifact(
                artifact_key=artifact_key,
                artifact_group="test_gallery",
                province_code="10",
                content_hash="0" * 64,
                source_path="data/public/test/gallery-preview.json",
                item_count=2,
                payload={"summary": {"value": 42}, "contact_name": "sensitive"},
            )
        )
        session.commit()

    try:
        with TestClient(app) as client:
            listing = client.get("/api/artifacts")
            preview = client.get("/api/artifact-preview", params={"artifact_key": artifact_key})
            missing = client.get("/api/artifact-preview", params={"artifact_key": "missing"})

        assert listing.status_code == 200
        listed = next(item for item in listing.json()["artifacts"] if item["artifact_key"] == artifact_key)
        assert listed["file_name"] == "gallery-preview.json"
        assert listed["source_path"] == "data/public/test/gallery-preview.json"
        assert listed["database_table"] == "public_artifacts"
        assert listed["database_column"] == "payload"
        assert "payload_preview" not in listing.text

        assert preview.status_code == 200
        payload = preview.json()
        assert payload["safe_preview"] is True
        assert payload["payload_preview"]["summary"]["value"] == 42
        assert payload["payload_preview"]["contact_name"] == "[hidden]"
        assert "sensitive" not in preview.text
        assert missing.status_code == 404
    finally:
        with SessionLocal() as session:
            artifact = session.get(PublicArtifact, artifact_key)
            if artifact is not None:
                session.delete(artifact)
                session.commit()


def test_explorer_home_uses_plain_thai_for_the_database_map() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "AIAT Database Explorer" in response.text
    assert "ข้อมูลมาจากไหน และไปอยู่ที่ไหน" in response.text
    assert response.text.index('id="database-map"') < response.text.index('id="sources"')
    assert "ดูข้อมูลอย่างเดียว" in response.text
    assert "กดดูแถวตัวอย่างในฐานข้อมูล" in response.text
    assert "ไฟล์ JSON ที่ Dashboard ใช้" in response.text
    assert 'id="artifact-gallery"' in response.text
    assert "ELI5 GLOSSARY" not in response.text
    assert "Candidate" not in response.text
    assert "Grain" not in response.text
    assert "QUALITY GATE" not in response.text
    assert "Public candidate" not in response.text
    assert 'href="/static/styles.css?v=plain-language-1"' in response.text
    assert 'src="/static/app.js?v=plain-language-1"' in response.text
    assert "http://testserver/static" not in response.text
