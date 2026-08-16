from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_health_and_catalog_summary():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        health_payload = health.json()
        assert health_payload["status"] == "ok"
        assert health_payload["database"] == "connected"
        assert health_payload["public_artifacts"] == 161
        assert health_payload["public_artifacts_expected"] == 161
        assert health_payload["source_catalog_rows"] == 28
        assert health_payload["public_value_sources"] == 11
        assert health_payload["metadata_only_sources"] == 12
        assert health_payload["restricted_local_only_sources"] == 5
        assert health_payload["published_catalog_ids_match_approved"] is True
        assert health_payload["restricted_values_published"] == 0

        summary = client.get("/api/summary").json()
        assert summary["sources"] == 28
        assert summary["endpoints_catalogued"] == 141
        assert summary["safe_runtime_endpoints"] == 90
        assert summary["production_approved_sources"] == 11
        assert summary["configured_connectors"] == 11
        assert summary["blocked_sources"] == 5
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
        assert "มิติการพัฒนาตามหลักฐานที่มี" in page.text
        assert "โครงการและงบ" in page.text
        assert "คนและพื้นที่" in page.text
        assert "คุณภาพข้อมูล" in page.text
        assert 'id="decisionChain"' in page.text
        assert 'id="dataQualitySummary"' in page.text
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
        assert len(connectivity) == 28
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
        assert payload["summary"]["public_sources"] == 11
        catalog = json.loads(
            (Path(__file__).parents[1] / "config/source_catalog.json").read_text(encoding="utf-8")
        )
        expected_restricted = sum(
            source.get("cloud_policy") == "restricted_local_only"
            for source in catalog["sources"]
        )
        assert payload["summary"]["restricted_sources_excluded"] == expected_restricted
        assert payload["summary"]["geocoded_cultural_points"] == 5258
        assert payload["summary"]["cultural_supporting_records"] == 361
        assert payload["summary"]["unmapped_public_records"] == 312
        public_sources = client.get("/api/public/v1/sources").json()
        learning_source = next(
            source
            for source in public_sources
            if source["source_id"] == "f2_learning_dashboard"
        )
        assert learning_source["projection_coverage"]["linked_provinces"] == 66

        provinces = client.get("/api/public/v1/provinces?has_evidence=true").json()
        assert len(provinces) == 77
        assert all(row["quality_status"] == "candidate_needs_review" for row in provinces)

        roi_et = client.get("/api/public/v1/provinces/45")
        assert roi_et.status_code == 200
        assert roi_et.json()["province_name_th"] == "ร้อยเอ็ด"
        assert roi_et.json()["evidence_source_count"] == 9

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
        learning = songkhla_briefing["sections"]["learning_dashboard"]["items"]
        assert len(learning) == 1
        assert learning[0]["province_code"] == "90"
        assert learning[0]["unit"] is None
        assert learning[0]["as_of"] is None

        coverage = {item["source_id"]: item for item in songkhla_briefing["source_coverage"]}
        assert coverage["f3_housing_portal"]["status"] == "available"
        assert coverage["f2_rmutdb"]["status"] == "not_province_scoped"
        assert coverage["f2_apptech_mtr"]["status"] == "available"
        assert coverage["f2_learning_dashboard"]["status"] == "available"
        assert "f2_wallet_all_realtime" not in coverage

        summary_response = client.get("/api/public/v1/provinces/90/summary")
        assert summary_response.status_code == 200
        assert len(summary_response.content) < 30_000
        executive = summary_response.json()
        assert executive["schema_version"] == "1.0.0"
        assert executive["province"]["province_name_th"] == "สงขลา"
        assert executive["coverage"]["available_source_count"] == 6
        dimensions = {item["key"]: item for item in executive["dimensions"]}
        assert set(dimensions) == {"housing", "risk", "development", "culture"}
        assert any(metric["key"] == "house_price_income_ratio" for metric in dimensions["housing"]["metrics"])
        assert any(metric["comparison"] == "above" for metric in dimensions["housing"]["metrics"])
        assert executive["methodology"]["raw_rows_included"] is False
        assert executive["methodology"]["unknown_value_policy"] == "null_and_not_found_are_never_rendered_as_zero"
        assert [stage["key"] for stage in executive["decision_chain"]] == [
            "need",
            "input",
            "activity",
            "output",
            "outcome",
        ]
        assert executive["data_quality_overview"]["accepted_source_count"] == 0
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
        assert insight_payload["audit_summary"]["supplemental_geo_linkable_source_ids"] == [
            "f2_learning_dashboard"
        ]
        assert insight_payload["audit_summary"]["unmapped_public_records"] == {
            "f2_learning_area_based": {
                "records": 6,
                "reason": "source_province_missing",
            }
        }
        assert insight_payload["sources"]["f1_pppconnext"]["coverage"]["linked_provinces"] == 21
        assert insight_payload["sources"]["f2_apptech_mtr"]["statistics"]["registered_users"] == 2356
        assert insight_payload["sources"]["f3_city_capital_open_data"]["coverage"]["linked_cities"] == 18
        assert insight_payload["sources"]["f2_rmutdb"]["statistics"]["detailed_records"] == 1006
        learning_insight = insight_payload["sources"]["f2_learning_dashboard"]
        assert learning_insight["coverage"]["linked_provinces"] == 66
        assert learning_insight["coverage"]["unmatched_province_rows"] == 0
        assert learning_insight["non_province_tables"]["categories"]["row_count"] == 7
        cultural_insight = insight_payload["sources"]["f2_culturalmap_university"]
        assert cultural_insight["coverage"]["supporting_records"] == 361
        assert cultural_insight["coverage"]["total_records"] == 5619
        assert cultural_insight["privacy_projection"]["contact_fields_exposed"] is False

        for province_code, title in (
            ("33", "นวัตกรรมโรงอบแห้งพริกพลังงานแสงอาทิตย์"),
            ("73", "ระบบแจ้งเตือนภัยแผ่นดินไหว ประเทศไทย"),
        ):
            province_briefing = client.get(
                f"/api/public/v1/provinces/{province_code}/briefing"
            ).json()
            requirements = province_briefing["sections"]["requirements"]["items"]
            assert len(requirements) == 1
            assert requirements[0]["title"] == title
            assert requirements[0]["record_grain"] == "one_public_requirement"
            assert requirements[0]["provenance"]["as_of"] is None
            requirement_coverage = next(
                item
                for item in province_briefing["source_coverage"]
                if item["source_id"] == "f2_apptech_mru"
            )
            assert requirement_coverage["record_breakdown"]["requirements"] == 1

            province_summary = client.get(
                f"/api/public/v1/provinces/{province_code}/summary"
            ).json()
            development = next(
                item for item in province_summary["dimensions"] if item["key"] == "development"
            )
            assert any(
                item["kind"] == "requirement" and item["title_th"] == title
                for item in development["highlights"]
            )

        lampang = client.get("/api/public/v1/provinces/52/summary").json()
        lampang_dimensions = {item["key"]: item for item in lampang["dimensions"]}
        assert "livelihood" in lampang_dimensions
        assert "urban" in lampang_dimensions
        assert lampang_dimensions["urban"]["metrics"][0]["benchmark_label_th"] == "ค่ากลาง 18 เมือง"

        portfolio = executive["research_portfolio"]
        assert portfolio["project_count"] == len(
            songkhla_briefing["sections"]["project_master"]["items"]
        )
        assert portfolio["participant_record_count"] == len(
            songkhla_briefing["sections"]["area_based"]["items"]
        )
        assert portfolio["innovation_count"] == len(
            songkhla_briefing["sections"]["innovation"]["items"]
        )
        assert portfolio["project_count"] == sum(
            entry["value"] for entry in portfolio["fiscal_years"]
        )
        assert portfolio["scope_note_th"]
        assert portfolio["data_gaps_th"]
        assert all(
            district["value"] >= 1 and district["label_th"] for district in portfolio["districts"]
        )
        funding = portfolio["funding"]
        assert funding["pmua_funded_innovation_count"] <= funding["pmua_funding_entry_count"]
        assert funding["pmua_amount_known_entries"] <= funding["pmua_funding_entry_count"]
        assert funding["allocation_status"] == "linked_innovation_funding_not_provincial_allocation"
        assert "note_th" in funding

        phetchaburi = client.get("/api/public/v1/provinces/76/briefing").json()
        assert phetchaburi["sections"]["area_based"]["total_records"] == 30
        assert phetchaburi["sections"]["project_master"]["total_records"] == 1

        sra_states = client.get("/api/public/v1/provinces").json()
        scope_counts = {
            state: sum(item["sra_scope_status"] == state for item in sra_states)
            for state in {
                "in_scope_value_available",
                "in_scope_no_current_value",
                "out_of_scope",
            }
        }
        assert scope_counts == {
            "in_scope_value_available": 15,
            "in_scope_no_current_value": 5,
            "out_of_scope": 57,
        }
        missing_score_names = {
            item["province_name_th"]
            for item in sra_states
            if item["sra_scope_status"] == "in_scope_no_current_value"
        }
        assert missing_score_names == {
            "นครราชสีมา",
            "ยโสธร",
            "ลำปาง",
            "พิษณุโลก",
            "พัทลุง",
        }
        assert all(
            item["sra_overall_score"] is None
            for item in sra_states
            if item["sra_scope_status"] == "in_scope_no_current_value"
        )

        boundary = client.get("/api/public/v1/map/provinces").json()
        assert boundary["type"] == "FeatureCollection"
        assert len(boundary["features"]) == 77

        points = client.get("/api/public/v1/map/cultural-points").json()
        assert len(points["features"]) == 5258

        download = client.get("/downloads/province_evidence.csv")
        assert download.status_code == 200
        assert "province_code" in download.text

        unmapped = client.get("/downloads/unmapped_records.json")
        assert unmapped.status_code == 200
        unmapped_payload = unmapped.json()
        assert unmapped_payload["total_records"] == 312
        assert unmapped_payload["sources"]["f2_learning_area_based"]["record_count"] == 6
        housing_unmapped = unmapped_payload["sources"]["f3_housing_portal"]
        assert housing_unmapped["record_count"] == 306
        assert housing_unmapped["approved_projection_records"] == 7259
        assert housing_unmapped["province_linked_records"] == 6953
        assert housing_unmapped["reason_counts"] == {
            "source_geography_missing": 3,
            "source_geography_not_at_province_grain": 248,
            "source_province_code_not_in_official_crosswalk": 55,
        }


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


def test_operational_records_always_filter_non_public_sources(monkeypatch):
    from app.database import SessionLocal
    from app.main import settings
    from app.models import DashboardRecord

    with TestClient(app) as client:
        with SessionLocal() as session:
            session.add_all(
                [
                    DashboardRecord(
                        source_id="f1_pppconnext",
                        dataset_key="approved",
                        source_record_id="approved-1",
                        record_hash="a" * 64,
                        payload={"value": "public"},
                    ),
                    DashboardRecord(
                        source_id="f2_cultural_market_civil",
                        dataset_key="metadata-only",
                        source_record_id="metadata-1",
                        record_hash="b" * 64,
                        payload={"value": "must-not-serve"},
                    ),
                    DashboardRecord(
                        source_id="f2_wallet_all_realtime",
                        dataset_key="restricted",
                        source_record_id="restricted-1",
                        record_hash="c" * 64,
                        payload={"value": "must-not-serve"},
                    ),
                ]
            )
            session.commit()

        metadata_only = client.get("/api/records")
        assert metadata_only.status_code == 200
        assert [row["source_id"] for row in metadata_only.json()] == ["f1_pppconnext"]
        assert "payload" not in metadata_only.json()[0]
        assert client.get(
            "/api/records?source_id=f2_wallet_all_realtime"
        ).json() == []

        monkeypatch.setattr(settings, "public_data_values_enabled", True)
        with_payload = client.get("/api/records?include_payload=true")
        assert with_payload.status_code == 200
        assert with_payload.json() == [
            {
                **metadata_only.json()[0],
                "payload": {"value": "public"},
            }
        ]


def test_operational_debug_routes_are_hidden_outside_local_sqlite(monkeypatch):
    from app.main import settings

    monkeypatch.setattr(settings, "app_env", "production")
    with TestClient(app) as client:
        for path in (
            "/api/summary",
            "/api/sources",
            "/api/connectivity",
            "/api/sources/f1_sradss_ppaos/endpoints",
            "/api/runs",
            "/api/records",
        ):
            response = client.get(path)
            assert response.status_code == 404, path
            assert "manifest" not in response.text.lower()
            assert "data_household_detail" not in response.text.lower()

        assert client.get("/health").status_code == 200
        assert client.get("/api/public/v1/overview").status_code == 200


def test_health_and_database_coverage_fail_closed_on_catalog_drift():
    from app.database import SessionLocal
    from app.models import PublicArtifact

    with TestClient(app) as client:
        baseline = client.get("/api/public/v1/database-coverage")
        assert baseline.status_code == 200
        baseline_payload = baseline.json()
        assert baseline_payload["status"] == "complete"
        assert baseline_payload["public_artifacts_in_database"] == 161
        assert baseline_payload["source_catalog_rows"] == 28
        assert baseline_payload["public_value_sources"] == 11
        assert baseline_payload["metadata_only_sources"] == 12
        assert baseline_payload["restricted_local_only_sources"] == 5
        assert baseline_payload["published_catalog_source_count"] == 11
        assert baseline_payload["published_catalog_ids_match_approved"] is True
        assert baseline_payload["restricted_catalog_sources_published"] == 0
        assert baseline_payload["restricted_values_published"] == 0

        with SessionLocal() as session:
            catalog = session.get(PublicArtifact, "catalog")
            payload = dict(catalog.payload)
            sources = [dict(source) for source in payload["sources"]]
            sources[0]["source_id"] = "f2_wallet_all_realtime"
            catalog.payload = {**payload, "sources": sources}
            session.commit()

        unhealthy = client.get("/health")
        assert unhealthy.status_code == 503
        assert unhealthy.json()["status"] == "unhealthy"
        assert unhealthy.json()["published_catalog_ids_match_approved"] is False

        incomplete = client.get("/api/public/v1/database-coverage")
        assert incomplete.status_code == 200
        assert incomplete.json()["status"] == "incomplete"
        assert incomplete.json()["published_catalog_ids_match_approved"] is False
        assert incomplete.json()["restricted_catalog_sources_published"] == 1


def test_every_public_v1_route_has_an_explicit_openapi_response_schema():
    with TestClient(app) as client:
        document = client.get("/openapi.json").json()

    public_operations = {
        path: item["get"]
        for path, item in document["paths"].items()
        if path.startswith("/api/public/v1/")
    }
    assert len(public_operations) == 14
    for path, operation in public_operations.items():
        response_schema = operation["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema != {}, path
        assert any(key in response_schema for key in ("$ref", "type", "anyOf")), path
        if "$ref" in response_schema:
            component_name = response_schema["$ref"].rsplit("/", 1)[-1]
            component = document["components"]["schemas"][component_name]
            assert component.get("properties"), path
        elif response_schema.get("type") == "array":
            assert response_schema.get("items"), path
