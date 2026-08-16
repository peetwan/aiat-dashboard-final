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
        assert "Provincial Evidence Map" in page.text
        assert "เลือกจังหวัดเพื่อเปิดข้อมูล" in page.text
        assert "Anuphan" in page.text
        assert "ความครอบคลุมข้อมูล" in page.text
        assert 'data-panel-tab="dimensions"' in page.text
        assert "ภาพสถานการณ์รายมิติ" in page.text
        assert 'href="/insights"' in page.text
        assert "สำรวจรายละเอียดตามมิติ" not in page.text
        assert "↗" not in page.text

        insights_page = client.get("/insights")
        assert insights_page.status_code == 200
        assert "AIAT Data Insights" in insights_page.text
        assert "โดยไม่ต้องไล่เปิด" in insights_page.text
        assert "ทีละชุด" in insights_page.text
        assert "select" not in insights_page.text.lower()
        assert "→" not in insights_page.text

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


def test_public_projection_and_downloads_are_available():
    with TestClient(app) as client:
        overview = client.get("/api/public/v1/overview")
        assert overview.status_code == 200
        payload = overview.json()
        assert payload["publication_status"] == "public_candidate_projection"
        assert payload["summary"]["public_sources"] == 10
        assert payload["summary"]["restricted_sources_excluded"] == 2
        assert payload["summary"]["geocoded_cultural_points"] == 5258

        provinces = client.get("/api/public/v1/provinces?has_evidence=true").json()
        assert len(provinces) == 77
        assert all(row["quality_status"] == "candidate_needs_review" for row in provinces)

        roi_et = client.get("/api/public/v1/provinces/45")
        assert roi_et.status_code == 200
        assert roi_et.json()["province_name_th"] == "ร้อยเอ็ด"
        assert roi_et.json()["evidence_source_count"] == 8

        songkhla = client.get("/api/public/v1/provinces/90")
        assert songkhla.status_code == 200
        songkhla_payload = songkhla.json()
        assert songkhla_payload["province_name_th"] == "สงขลา"

        briefing = client.get("/api/public/v1/provinces/90/briefing")
        assert briefing.status_code == 200
        songkhla_briefing = briefing.json()
        assert songkhla_briefing["schema_version"] == "2.0.0"
        assert songkhla_briefing["province"]["province_name_th"] == "สงขลา"
        signals = {item["key"]: item for item in songkhla_briefing["executive_signals"]}
        assert signals["house_price_income_ratio"]["display_value"] == "3.20"
        assert signals["overcrowding_pct"]["display_value"] == "9.24%"
        assert signals["housing_loan_pass_share"]["display_value"] == "56.59%"
        assert signals["flood_risk_area_level_4_5"]["display_value"] == "26.84%"

        projects = songkhla_briefing["sections"]["area_based"]["items"]
        assert {item["project_name"] for item in projects} == {
            "เครื่องแกงฮาลาลันตอยยีบัน",
            "AHSAN Trustmark",
        }
        innovations = songkhla_briefing["sections"]["innovation"]["items"]
        assert any(item["title"] == "ลวดลายจากชุดลูกปัดโนรา" for item in innovations)
        assert any(item["trl_level"] == 7 for item in innovations)
        assert songkhla_briefing["sections"]["sra"]["status"] == "source_has_no_record_for_province"

        coverage = {item["source_id"]: item for item in songkhla_briefing["source_coverage"]}
        assert coverage["f3_housing_portal"]["status"] == "available"
        assert coverage["f2_rmutdb"]["status"] == "not_province_scoped"
        assert coverage["f2_apptech_mtr"]["status"] == "available"
        assert "f2_wallet_all_realtime" not in coverage

        summary_response = client.get("/api/public/v1/provinces/90/summary")
        assert summary_response.status_code == 200
        assert len(summary_response.content) < 30_000
        executive = summary_response.json()
        assert executive["schema_version"] == "1.0.0"
        assert executive["province"]["province_name_th"] == "สงขลา"
        assert executive["coverage"]["available_source_count"] == 5
        dimensions = {item["key"]: item for item in executive["dimensions"]}
        assert set(dimensions) == {"housing", "risk", "development", "culture"}
        assert any(metric["key"] == "house_price_income_ratio" for metric in dimensions["housing"]["metrics"])
        assert any(metric["comparison"] == "above" for metric in dimensions["housing"]["metrics"])
        assert executive["methodology"]["raw_rows_included"] is False
        assert "sections" not in executive
        assert "f2_wallet_all_realtime" not in {
            item["source_id"] for item in executive["source_coverage"]
        }

        source_insights = client.get("/api/public/v1/source-insights")
        assert source_insights.status_code == 200
        insight_payload = source_insights.json()
        assert insight_payload["audit_summary"]["geo_linkable_source_ids"] == [
            "f1_pppconnext",
            "f2_apptech_mtr",
            "f3_city_capital_open_data",
        ]
        assert insight_payload["audit_summary"]["non_geo_source_ids"] == ["f2_rmutdb"]
        assert insight_payload["sources"]["f1_pppconnext"]["coverage"]["linked_provinces"] == 21
        assert insight_payload["sources"]["f2_apptech_mtr"]["statistics"]["registered_users"] == 2356
        assert insight_payload["sources"]["f3_city_capital_open_data"]["coverage"]["linked_cities"] == 18
        assert insight_payload["sources"]["f2_rmutdb"]["statistics"]["detailed_records"] == 1006

        lampang = client.get("/api/public/v1/provinces/52/summary").json()
        lampang_dimensions = {item["key"]: item for item in lampang["dimensions"]}
        assert "livelihood" in lampang_dimensions
        assert "urban" in lampang_dimensions
        assert lampang_dimensions["urban"]["metrics"][0]["benchmark_label_th"] == "ค่ากลาง 18 เมือง"

        boundary = client.get("/api/public/v1/map/provinces").json()
        assert boundary["type"] == "FeatureCollection"
        assert len(boundary["features"]) == 77

        points = client.get("/api/public/v1/map/cultural-points").json()
        assert len(points["features"]) == 5258

        download = client.get("/downloads/province_evidence.csv")
        assert download.status_code == 200
        assert "province_code" in download.text


def test_public_cors_and_restricted_sources_excluded():
    with TestClient(app) as client:
        response = client.get(
            "/api/public/v1/sources",
            headers={"Origin": "https://example.org"},
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "*"
        source_ids = {row["source_id"] for row in response.json()}
        assert "f2_wallet_all_realtime" not in source_ids
        assert "f2_wallet_cluster_realtime" not in source_ids
