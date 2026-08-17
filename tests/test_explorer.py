from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.catalog import sync_catalog
from app.database import SessionLocal
from explorer.main import app
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
        "project_owner_approved_public": 11,
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


def test_explorer_home_is_a_thai_read_only_database_map() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "AIAT Database Explorer" in response.text
    assert "DATABASE MAP" in response.text
    assert "AIAT Serving Database" in response.text
    assert response.text.index('id="database-map"') < response.text.index('id="sources"')
    assert "READ ONLY" in response.text
    assert "LIVE DATA PREVIEW" in response.text
    assert "ตัวอย่างข้อมูลจริงใน Database" in response.text
    assert "ELI5 GLOSSARY" not in response.text
    assert 'href="/static/styles.css?v=live-data-preview-1"' in response.text
    assert 'src="/static/app.js?v=live-data-preview-1"' in response.text
    assert "http://testserver/static" not in response.text
