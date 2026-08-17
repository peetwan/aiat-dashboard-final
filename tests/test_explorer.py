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


def test_explorer_home_is_a_thai_read_only_database_map() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "AIAT Database Explorer" in response.text
    assert "ทั้ง 28 แหล่ง" in response.text
    assert "read-only" in response.text
    assert 'href="/static/styles.css"' in response.text
    assert 'src="/static/app.js"' in response.text
    assert "http://testserver/static" not in response.text
