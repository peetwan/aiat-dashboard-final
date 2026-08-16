from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_and_catalog_summary():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["database"] == "connected"

        summary = client.get("/api/summary").json()
        assert summary["sources"] == 12
        assert summary["endpoints_catalogued"] == 140
        assert summary["safe_runtime_endpoints"] == 89
        assert summary["production_approved_sources"] == 10
        assert summary["configured_connectors"] == 10
        assert summary["blocked_sources"] == 2
        assert summary["database_backend"] == "sqlite"
        assert summary["public_data_values_enabled"] is False


def test_dashboard_and_endpoint_inventory():
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "Candidate dashboard" in page.text

        sources = client.get("/api/sources").json()
        wallet = next(row for row in sources if row["source_id"] == "f2_wallet_all_realtime")
        assert wallet["cloud_policy"] == "restricted_local_only"
        assert wallet["production_values_allowed"] is False
        assert wallet["endpoint_count"] > 0
        assert wallet["restricted_endpoint_count"] == wallet["endpoint_count"]

        endpoints = client.get("/api/sources/f1_sradss_ppaos/endpoints").json()
        assert len(endpoints) == 44
        household = next(row for row in endpoints if row["url"].endswith("data_household_detail.php"))
        assert household["restricted"] is True
        assert household["runtime_enabled"] is False

        connectivity = client.get("/api/connectivity").json()
        assert len(connectivity) == 12
        pmua = next(row for row in connectivity if row["source_id"] == "f2_learning_area_based")
        assert pmua["api_plan_configured"] is True
        assert pmua["deployable"] is True
        assert pmua["database_backend"] == "sqlite"
        wallet_connection = next(
            row for row in connectivity if row["source_id"] == "f2_wallet_cluster_realtime"
        )
        assert wallet_connection["deployable"] is False


def test_payload_api_is_locked_by_default():
    with TestClient(app) as client:
        response = client.get("/api/records?include_payload=true")
        assert response.status_code == 403
