from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.public_artifacts import artifact_inputs


PROJECT_ROOT = Path(__file__).parents[1]
PUBLIC_ROOT = PROJECT_ROOT / "data" / "public"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def reviewed_catalog() -> dict:
    return read_json(PROJECT_ROOT / "config" / "source_catalog.json")


def test_health_and_catalog_summary():
    catalog = reviewed_catalog()
    sources = catalog["sources"]
    expected_artifact_count = len(artifact_inputs())
    expected_endpoint_count = sum(len(source["endpoints"]) for source in sources)
    expected_runtime_endpoint_count = sum(
        endpoint["runtime_enabled"] and not endpoint["restricted"]
        for source in sources
        for endpoint in source["endpoints"]
    )
    expected_approved = sum(
        source["production_values_allowed"] for source in sources
    )
    expected_metadata = sum(
        source["value_visibility"] == "metadata_only" for source in sources
    )
    expected_restricted = sum(
        source["value_visibility"] == "restricted_local_only" for source in sources
    )

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        health_payload = health.json()
        assert health_payload["status"] == "ok"
        assert health_payload["database"] == "connected"
        assert health_payload["public_artifacts"] == expected_artifact_count
        assert health_payload["public_artifacts_expected"] == expected_artifact_count
        assert health_payload["spatial_features"] == health_payload[
            "spatial_features_expected"
        ]
        assert health_payload["spatial_complete"] is True
        assert health_payload["housing_demand_records"] == health_payload[
            "housing_demand_records_expected"
        ]
        assert health_payload["housing_demand_complete"] is True
        assert health_payload["source_catalog_rows"] == len(sources)
        assert health_payload["public_value_sources"] == expected_approved
        assert health_payload["metadata_only_sources"] == expected_metadata
        assert health_payload["restricted_local_only_sources"] == expected_restricted
        assert health_payload["published_catalog_ids_match_approved"] is True
        assert health_payload["restricted_values_published"] == 0

        summary = client.get("/api/summary").json()
        assert summary["sources"] == len(sources)
        assert summary["endpoints_catalogued"] == expected_endpoint_count
        assert summary["safe_runtime_endpoints"] == expected_runtime_endpoint_count
        assert summary["production_approved_sources"] == expected_approved
        assert summary["configured_connectors"] == sum(
            source["acquisition_mode"] in {"api_first", "snapshot_only"}
            for source in sources
        )
        assert summary["blocked_sources"] == sum(
            source["acquisition_mode"] == "blocked" for source in sources
        )
        assert summary["database_backend"] == "sqlite"
        assert summary["public_data_values_enabled"] is False


def test_dashboard_and_endpoint_inventory():
    catalog = reviewed_catalog()
    catalog_by_id = {source["source_id"]: source for source in catalog["sources"]}
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "Provincial Evidence Map" in page.text
        assert "เลือกจังหวัดเพื่อเปิดข้อมูล" in page.text
        assert "Anuphan" in page.text
        assert "ความครอบคลุมข้อมูล" in page.text
        assert 'data-panel-tab="dimensions"' in page.text
        assert "ภาพรวมรายมิติ" in page.text
        assert "โครงการและงบ" in page.text
        assert "คนและพื้นที่" in page.text
        assert "คุณภาพข้อมูล" in page.text
        assert 'id="overviewFlow"' in page.text
        assert 'id="dataQualitySummary"' in page.text
        assert 'href="/insights"' in page.text
        assert "สำรวจรายละเอียดตามมิติ" not in page.text
        assert "↗" not in page.text

        province_page = client.get("/province/76")
        assert province_page.status_code == 200
        assert "เพชรบุรี" in province_page.text
        assert "ข้อมูลจังหวัดฉบับเต็ม" in province_page.text
        assert 'id="operations"' in province_page.text
        assert "/static/province.js" in province_page.text
        assert client.get("/province/999").status_code == 404

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

        endpoints = client.get("/api/sources/f1_sradss_ppaos/endpoints").json()
        assert len(endpoints) == len(catalog_by_id["f1_sradss_ppaos"]["endpoints"])
        household = next(row for row in endpoints if row["url"].endswith("data_household_detail.php"))
        assert household["restricted"] is True
        assert household["runtime_enabled"] is False

        connectivity = client.get("/api/connectivity").json()
        assert len(connectivity) == len(catalog["sources"])
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
    dashboard = read_json(PUBLIC_ROOT / "public_dashboard.json")
    insights = read_json(PUBLIC_ROOT / "source_insights.json")
    unmapped_artifact = read_json(PUBLIC_ROOT / "unmapped_records.json")
    learning_artifact = read_json(PUBLIC_ROOT / "learning_dashboard.json")
    boundary_artifact = read_json(PUBLIC_ROOT / "thailand_provinces.geojson")
    cultural_artifact = read_json(PUBLIC_ROOT / "cultural_points.geojson")
    spatial_summary = read_json(PUBLIC_ROOT / "housing_spatial_summary.json")
    demand_summary = read_json(PUBLIC_ROOT / "housing_demand_summary.json")
    dashboard_contract = read_json(
        PROJECT_ROOT / "config" / "publication_contracts" / "dashboard_core.json"
    )
    expected_province_count = dashboard_contract["completeness"]["province_count"]
    executive_contract = read_json(
        PROJECT_ROOT
        / "config"
        / "publication_contracts"
        / "executive_summaries.json"
    )
    executive_response_limit = next(
        output["max_bytes"]
        for output in executive_contract["outputs"]
        if "path_glob" in output
    )
    catalog = reviewed_catalog()
    approved_source_ids = {
        source["source_id"]
        for source in catalog["sources"]
        if source["production_values_allowed"]
    }
    restricted_source_ids = {
        source["source_id"]
        for source in catalog["sources"]
        if source["value_visibility"] == "restricted_local_only"
    }

    with TestClient(app) as client:
        overview = client.get("/api/public/v1/overview")
        assert overview.status_code == 200
        payload = overview.json()
        assert payload == {
            key: dashboard[key]
            for key in (
                "schema_version",
                "generated_at",
                "publication_status",
                "warning_th",
                "summary",
                "themes",
                "metrics",
                "methodology",
            )
        }
        assert payload["publication_status"] == "public_candidate_projection"
        assert payload["summary"]["public_sources"] == len(dashboard["sources"])
        expected_restricted = sum(
            source.get("cloud_policy") == "restricted_local_only"
            for source in catalog["sources"]
        )
        assert payload["summary"]["restricted_sources_excluded"] == expected_restricted
        public_sources = client.get("/api/public/v1/sources").json()
        assert {source["source_id"] for source in public_sources} == {
            source["source_id"] for source in dashboard["sources"]
        }
        learning_source = next(
            source
            for source in public_sources
            if source["source_id"] == "f2_learning_dashboard"
        )
        assert learning_source["projection_coverage"] == learning_artifact["coverage"]

        all_provinces = client.get("/api/public/v1/provinces").json()
        assert len(all_provinces) == expected_province_count
        assert all_provinces == dashboard["provinces"]
        provinces_with_evidence = client.get(
            "/api/public/v1/provinces?has_evidence=true"
        ).json()
        assert len(provinces_with_evidence) == dashboard["summary"][
            "provinces_with_evidence"
        ]
        assert all(row["evidence_source_count"] > 0 for row in provinces_with_evidence)
        assert all(
            row["quality_status"] == "candidate_needs_review"
            for row in all_provinces
        )

        roi_et = client.get("/api/public/v1/provinces/45")
        assert roi_et.status_code == 200
        assert roi_et.json()["province_name_th"] == "ร้อยเอ็ด"
        assert roi_et.json() == next(
            row for row in dashboard["provinces"] if row["province_code"] == "45"
        )

        songkhla = client.get("/api/public/v1/provinces/90")
        assert songkhla.status_code == 200
        songkhla_payload = songkhla.json()
        assert songkhla_payload["province_name_th"] == "สงขลา"
        assert songkhla_payload == next(
            row for row in dashboard["provinces"] if row["province_code"] == "90"
        )

        briefing = client.get("/api/public/v1/provinces/90/briefing")
        assert briefing.status_code == 200
        songkhla_briefing = briefing.json()
        expected_songkhla_briefing = read_json(
            PUBLIC_ROOT / "provincial_briefings" / "90.json"
        )
        for key in (
            "schema_version",
            "generated_at",
            "publication_status",
            "province",
            "executive_signals",
            "sections",
            "quality",
            "available_source_ids",
        ):
            assert songkhla_briefing[key] == expected_songkhla_briefing[key]
        assert [item["source_id"] for item in songkhla_briefing["source_coverage"]] == [
            item["source_id"] for item in expected_songkhla_briefing["source_coverage"]
        ]
        assert songkhla_briefing["province"]["province_name_th"] == "สงขลา"
        for section in songkhla_briefing["sections"].values():
            if "items" in section and "total_records" in section:
                assert section["total_records"] >= len(section["items"])

        coverage = {item["source_id"]: item for item in songkhla_briefing["source_coverage"]}
        assert coverage["f2_rmutdb"]["status"] == "not_province_scoped"
        assert set(coverage) <= approved_source_ids
        assert not restricted_source_ids.intersection(coverage)
        demand = songkhla_briefing["sections"]["housing"]["demand_summary"]
        assert demand["respondents_living"] >= 0
        assert demand["single_choice_distributions"]["future_housing_demand"]["answered"] >= 0

        summary_response = client.get("/api/public/v1/provinces/90/summary")
        assert summary_response.status_code == 200
        assert len(summary_response.content) <= executive_response_limit
        executive = summary_response.json()
        expected_executive = read_json(PUBLIC_ROOT / "executive_summaries" / "90.json")
        for key in (
            "schema_version",
            "generated_at",
            "publication_status",
            "province",
            "readout",
            "research_portfolio",
            "decision_chain",
            "data_quality_overview",
            "dimensions",
            "missing_dimensions",
            "coverage",
            "quality",
            "methodology",
        ):
            assert executive[key] == expected_executive[key]
        assert executive["province"]["province_name_th"] == "สงขลา"
        dimensions = {item["key"]: item for item in executive["dimensions"]}
        assert len(dimensions) == len(executive["dimensions"])
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
        assert insight_payload == insights
        audit_summary = insight_payload["audit_summary"]
        assert set(audit_summary["all_geo_linkable_source_ids"]) == set(
            audit_summary["geo_linkable_source_ids"]
        ) | set(audit_summary["supplemental_geo_linkable_source_ids"])
        assert not set(audit_summary["all_geo_linkable_source_ids"]).intersection(
            audit_summary["non_geo_source_ids"]
        )
        learning_insight = insight_payload["sources"]["f2_learning_dashboard"]
        assert learning_insight["coverage"]["linked_provinces"] == learning_artifact[
            "coverage"
        ]["linked_provinces"]
        assert learning_insight["coverage"]["unmatched_province_rows"] == len(
            learning_artifact["unmatched_province_rows"]
        )
        cultural_insight = insight_payload["sources"]["f2_culturalmap_university"]
        assert cultural_insight["coverage"]["map_records"] == len(
            cultural_artifact["features"]
        )
        assert cultural_insight["coverage"]["total_records"] == (
            cultural_insight["coverage"]["map_records"]
            + cultural_insight["coverage"]["supporting_records"]
        )
        assert cultural_insight["privacy_projection"]["contact_fields_exposed"] is False
        portfolio = insight_payload["executive_portfolio"]
        assert portfolio["audit"]["source_count"] == len(
            portfolio["audit"]["status_rows"]
        )
        assert portfolio["audit"]["source_count"] == sum(
            portfolio["audit"][f"{status}_source_count"]
            for status in ("complete", "partial", "mixed")
        )
        headline = {item["key"]: item for item in portfolio["headline_metrics"]}
        assert headline["housing_demand_responses"]["value"] == demand_summary[
            "record_count"
        ]
        assert headline["housing_points"]["value"] == spatial_summary["counts"][
            "housing_points"
        ]
        assert headline["cultural_records"]["value"] == cultural_insight[
            "coverage"
        ]["total_records"]
        assert all(
            item["value"] is None
            or (isinstance(item["value"], (int, float)) and item["value"] >= 0)
            for item in headline.values()
        )
        assert sorted(
            item["value"]
            for item in portfolio["charts"]["housing_spatial"]["items"]
        ) == sorted(spatial_summary["counts"].values())

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

        sra_states = client.get("/api/public/v1/provinces").json()
        allowed_scope_states = {
            "in_scope_value_available",
            "in_scope_no_current_value",
            "out_of_scope",
        }
        assert {item["sra_scope_status"] for item in sra_states} <= allowed_scope_states
        scope_counts = {
            state: sum(item["sra_scope_status"] == state for item in sra_states)
            for state in allowed_scope_states
        }
        assert sum(scope_counts.values()) == expected_province_count
        assert all(
            item["sra_overall_score"] is None
            for item in sra_states
            if item["sra_scope_status"] == "in_scope_no_current_value"
        )

        boundary = client.get("/api/public/v1/map/provinces").json()
        assert boundary == boundary_artifact
        assert len(boundary["features"]) == expected_province_count

        points = client.get("/api/public/v1/map/cultural-points").json()
        assert points == cultural_artifact
        assert len(points["features"]) == payload["summary"][
            "geocoded_cultural_points"
        ]

        download = client.get("/downloads/province_evidence.csv")
        assert download.status_code == 200
        assert "province_code" in download.text

        for internal_path in (
            "publication_receipt.json",
            "serving_manifest.json",
            "manifest.json",
            "source_insights_manifest.json",
            "provincial_briefings/index.json",
        ):
            assert client.get(f"/downloads/{internal_path}").status_code == 404

        unmapped = client.get("/downloads/unmapped_records.json")
        assert unmapped.status_code == 200
        unmapped_payload = unmapped.json()
        assert unmapped_payload == unmapped_artifact
        assert unmapped_payload["total_records"] == sum(
            source["record_count"] for source in unmapped_payload["sources"].values()
        )
        assert all(
            source["record_count"] == len(source["items"])
            for source in unmapped_payload["sources"].values()
        )
        housing_unmapped = unmapped_payload["sources"]["f3_housing_portal"]
        assert housing_unmapped["approved_projection_records"] == (
            housing_unmapped["province_linked_records"]
            + housing_unmapped["record_count"]
        )
        assert sum(housing_unmapped["reason_counts"].values()) == housing_unmapped[
            "record_count"
        ]


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


def test_public_operations_contract_reports_live_audit_without_claiming_automation():
    catalog = reviewed_catalog()
    plans = read_json(PROJECT_ROOT / "config" / "ingestion_plans.json")["sources"]
    with TestClient(app) as client:
        response = client.get("/api/public/v1/operations")
        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["registered_sources"] == len(catalog["sources"])
        assert payload["summary"]["public_candidate_sources"] == sum(
            source["production_values_allowed"] for source in catalog["sources"]
        )
        assert payload["summary"]["executable_connectors"] == len(plans)
        assert payload["summary"]["automatic_refresh_enabled"] is False
        assert payload["summary"]["automatic_public_promotion_enabled"] is False
        audit = payload["last_connectivity_audit"]
        assert audit["configured_connectors"] == len(audit["results"])
        assert audit["successful_connectors"] + audit["failed_connectors"] == audit[
            "configured_connectors"
        ]
        assert audit["records_seen_total"] == sum(
            row["records_seen"] for row in audit["results"]
        )
        public_source_ids = {row["source_id"] for row in audit["results"]}
        assert "f2_wallet_all_realtime" not in public_source_ids
        assert "f3_healthcare_nonthaburi" not in public_source_ids


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

    catalog_config = reviewed_catalog()
    catalog_sources = catalog_config["sources"]
    approved_count = sum(
        source["production_values_allowed"] for source in catalog_sources
    )
    metadata_count = sum(
        source["value_visibility"] == "metadata_only" for source in catalog_sources
    )
    restricted_count = sum(
        source["value_visibility"] == "restricted_local_only"
        for source in catalog_sources
    )

    with TestClient(app) as client:
        baseline = client.get("/api/public/v1/database-coverage")
        assert baseline.status_code == 200
        baseline_payload = baseline.json()
        assert baseline_payload["status"] == "complete"
        assert baseline_payload["public_artifacts_in_database"] == len(artifact_inputs())
        assert baseline_payload["public_artifacts_in_database"] == baseline_payload[
            "public_artifacts_expected"
        ]
        assert baseline_payload["source_catalog_rows"] == len(catalog_sources)
        assert baseline_payload["public_value_sources"] == approved_count
        assert baseline_payload["metadata_only_sources"] == metadata_count
        assert baseline_payload["restricted_local_only_sources"] == restricted_count
        assert baseline_payload["published_catalog_source_count"] == approved_count
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
    assert len(public_operations) == 20
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
