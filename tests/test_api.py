from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app, build_candidate_disaster_tracking_artifact
from app.database import SessionLocal
from app.models import DashboardRecord, PublicArtifact
from app.public_artifacts import artifact_inputs


PROJECT_ROOT = Path(__file__).parents[1]
PUBLIC_ROOT = PROJECT_ROOT / "data" / "public"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def reviewed_catalog() -> dict:
    return read_json(PROJECT_ROOT / "config" / "source_catalog.json")


def catalog_with_default_disaster_fields(dashboard: dict) -> list[dict]:
    rows = []
    for province in dashboard["provinces"]:
        item = dict(province)
        item.setdefault("disaster_source_count", 0)
        item.setdefault("disaster_record_count", 0)
        item.setdefault("disaster_sources", [])
        rows.append(item)
    return rows


def boundaries_with_default_disaster_fields(boundary_artifact: dict) -> dict:
    payload = json.loads(json.dumps(boundary_artifact))
    for feature in payload["features"]:
        props = feature.setdefault("properties", {})
        props.setdefault("disaster_source_count", 0)
        props.setdefault("disaster_record_count", 0)
        props.setdefault("disaster_sources", [])
    return payload


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
        assert "AIAT แผนที่ข้อมูลจังหวัด" in page.text
        assert "เลือกภาคหรือจังหวัด" in page.text
        assert "Anuphan" in page.text
        for mode in ("f1", "f2", "f3", "f4", "executive"):
            assert f'data-map-mode="{mode}"' in page.text
        for removed_mode in ("projects", "sra", "innovation", "coverage", "disaster"):
            assert f'data-map-mode="{removed_mode}"' not in page.text
        assert 'id="provincePanelTabs"' not in page.text
        assert 'data-panel-tab=' not in page.text
        assert "ฝ่าย 1 ขจัดความยากจน" in page.text
        assert "ฝ่าย 2" in page.text
        assert "ฝ่าย 3" in page.text
        assert "ฝ่าย 4" in page.text
        assert "ผู้บริหาร" in page.text
        assert 'id="workspacePanel"' in page.text
        assert 'data-panel-view="department"' in page.text
        assert 'id="overviewFlow"' in page.text
        assert 'id="dataQualitySummary"' in page.text
        assert 'href="/insights"' not in page.text
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
        assert "AIAT ภาพรวมข้อมูล" in insights_page.text
        assert "โดยไม่ต้องไล่เปิด" in insights_page.text
        assert "ทีละชุด" in insights_page.text
        assert 'id="workDirectorySource"' in insights_page.text
        assert 'id="workDirectorySearch"' in insights_page.text
        assert "→" not in insights_page.text

        sources = client.get("/api/sources").json()
        wallet = next(row for row in sources if row["source_id"] == "f2_wallet_all_realtime")
        assert wallet["cloud_policy"] == "team_approved_public"
        assert wallet["production_values_allowed"] is True

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
        assert wallet_connection["deployable"] is True


def test_f1_overview_aggregates_only_reviewed_province_artifacts():
    dashboard = read_json(PUBLIC_ROOT / "public_dashboard.json")
    target_codes = {
        row["province_code"]
        for row in dashboard["provinces"]
        if str(row.get("sra_scope_status") or "").startswith("in_scope")
    }
    expected = {
        "om_count": 0,
        "chain_count": 0,
        "om_capital_baht": 0,
        "people": 0,
        "households": 0,
        "assistance_households": 0,
        "assistance_episodes": 0,
    }
    for code in target_codes:
        briefing = read_json(PUBLIC_ROOT / "provincial_briefings" / f"{code}.json")
        sra = briefing["sections"]["sra"]
        ppp = briefing["sections"]["pppconnext"]
        om = sra.get("om_total") or {}
        expected["om_count"] += om.get("om_count") or 0
        expected["chain_count"] += om.get("chain_count") or 0
        expected["om_capital_baht"] += om.get("capital_baht") or 0
        ppp_values = {item["metric_key"]: item["value"] for item in ppp.get("items", [])}
        expected["people"] += ppp_values.get("members_total") or 0
        expected["households"] += ppp_values.get("households_total") or 0
        assistance = sorted(
            sra.get("assistance_trend", []),
            key=lambda item: int(item.get("year") or 0),
        )
        if assistance:
            expected["assistance_households"] += assistance[-1].get("households") or 0
            expected["assistance_episodes"] += assistance[-1].get("episodes") or 0

    with TestClient(app) as client:
        response = client.get("/api/public/v1/f1/overview")
        assert response.status_code == 200
        payload = response.json()

    assert set(payload["scope"]["province_codes"]) == target_codes
    assert len(payload["provinces"]) == len(target_codes)
    assert payload["totals"]["province_count"] == len(target_codes)
    for key, value in expected.items():
        assert payload["totals"][key] == value
    assert sum(region["totals"]["province_count"] for region in payload["regions"]) == len(target_codes)
    assert {row["province_code"] for row in payload["provinces"]} == target_codes
    assert payload["quality"]["note_th"]
    assert payload["national_profile"]["fetched_at"]
    assert len(payload["national_profile"]["capital_dimensions"]) == 5
    assert payload["national_profile"]["assistance_all_years"]["households"] > 0
    assert len(payload["totals"]["assistance_dimensions_latest"]) == 5
    assert all(
        {"dimension_key", "households", "episodes", "budget_baht"}.issubset(item)
        for item in payload["totals"]["assistance_dimensions_latest"]
    )
    assert all("project_metrics" in row for row in payload["provinces"])
    assert all(
        {"metric_key", "value", "unit"}.issubset(metric)
        for row in payload["provinces"]
        for metric in row["project_metrics"]
    )
    assert all("items" not in row for row in payload["provinces"])


def test_f4_public_api_uses_r2_backed_loaders(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "_preflight_publication_release", lambda: None)
    monkeypatch.setattr(
            main,
            "f4_overview",
            lambda province_codes_by_name=None: {
                "cards": [
                    {"key": "target_provinces", "value": 67},
                    {"key": "innovations", "value": 1172},
                    {"key": "policy_projects", "value": 107},
                    {"key": "local_innovators", "value": 12059},
                ],
                "target_province_codes": sorted((province_codes_by_name or {}).values())[:1],
                "economic_impact_rows": [
                    {
                        "year_filter": "all",
                        "label": "รวมทั้งหมด",
                        "cost_reduced_baht": 10,
                        "income_increased_baht": 20,
                        "net_income_increased_baht": 30,
                    }
                ],
                "evidence_notes": [],
            },
        )
    monkeypatch.setattr(
        main,
        "f4_innovations",
        lambda province_code=None, province_codes=None, province_names_by_code=None: {
            "total": 1,
            "rows": [
                {
                    "title": "เทคโนโลยี A",
                    "product_id": 1,
                    "provinces": [province_code or (province_codes or ["90"])[0]],
                }
            ],
        },
    )
    monkeypatch.setattr(
        main,
        "f4_policy_projects",
        lambda province_name_th=None, province_names_th=None: {
            "total": 1,
            "rows": [
                {
                    "project_title": f"โครงการ {province_name_th or (province_names_th or ['ประเทศ'])[0]}",
                    "project_id": "p1",
                }
            ],
            "status_summary": [{"label": "อยู่ระหว่างดำเนินการ", "count": 1}],
            "budget_baht_total": 100,
            "budget_known_rows": 1,
        },
    )
    monkeypatch.setattr(
        main,
        "f4_region_summary",
        lambda region_name_th, province_codes, province_names_by_code: {
            "region_name_th": region_name_th,
            "province_codes": province_codes,
            "cards": [
                {"key": "target_provinces", "value": len(province_codes)},
                {"key": "innovations", "value": 1},
                {"key": "policy_projects", "value": 1},
                {"key": "local_innovators", "value": None},
            ],
        },
    )
    monkeypatch.setattr(
        main,
        "f4_province_summary",
        lambda province_code, province_name_th, province_names_by_code: {
            "province_code": province_code,
            "province_name_th": province_name_th,
            "is_target_province": True,
            "target_membership_source": "raw/f2/f2_learning_dashboard/learning_dashboard.json",
            "cards": [
                {"key": "target_membership", "value": 1},
                {"key": "innovations", "value": 1},
                {"key": "policy_projects", "value": 1},
            ],
        },
    )

    with TestClient(app) as client:
        overview = client.get("/api/public/v1/f4/overview")
        assert overview.status_code == 200
        assert [card["key"] for card in overview.json()["cards"]] == [
            "target_provinces",
            "innovations",
            "policy_projects",
            "local_innovators",
        ]
        assert overview.json()["economic_impact_rows"][0]["label"] == "รวมทั้งหมด"

        innovations = client.get("/api/public/v1/f4/innovations")
        assert innovations.status_code == 200
        assert innovations.json()["rows"][0]["title"] == "เทคโนโลยี A"

        clig = client.get("/api/public/v1/f4/policy-projects")
        assert clig.status_code == 200
        assert clig.json()["rows"][0]["project_id"] == "p1"

        province = client.get("/api/public/v1/f4/provinces/90")
        assert province.status_code == 200
        assert province.json()["province_name_th"] == "สงขลา"
        assert province.json()["is_target_province"] is True
        assert province.json()["cards"][0]["key"] == "target_membership"

        province_innovations = client.get("/api/public/v1/f4/provinces/90/innovations")
        assert province_innovations.status_code == 200
        assert province_innovations.json()["rows"][0]["provinces"] == ["90"]

        province_projects = client.get("/api/public/v1/f4/provinces/90/policy-projects")
        assert province_projects.status_code == 200
        assert "สงขลา" in province_projects.json()["rows"][0]["project_title"]
        assert province_projects.json()["status_summary"][0]["count"] == 1
        assert province_projects.json()["budget_baht_total"] == 100

        region = client.get("/api/public/v1/f4/regions/ภาคใต้")
        assert region.status_code == 200
        assert region.json()["region_name_th"] == "ภาคใต้"

        region_innovations = client.get("/api/public/v1/f4/regions/ภาคใต้/innovations")
        assert region_innovations.status_code == 200
        assert region_innovations.json()["rows"][0]["title"] == "เทคโนโลยี A"

        region_projects = client.get("/api/public/v1/f4/regions/ภาคใต้/policy-projects")
        assert region_projects.status_code == 200
        assert region_projects.json()["rows"][0]["project_id"] == "p1"

        assert client.get("/api/public/v1/f4/regions/ภาคไม่มีจริง").status_code == 404
        assert client.get("/api/public/v1/f4/provinces/999").status_code == 404


def test_payload_api_is_locked_by_default():
    with TestClient(app) as client:
        response = client.get("/api/records?include_payload=true")
        assert response.status_code == 403


def _seed_disaster_record(source_id: str, dataset_key: str, payload: dict, index: int) -> None:
    """Seed a candidate and explicitly publish the resulting reviewed test projection."""

    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        session.add(
            DashboardRecord(
                source_id=source_id,
                dataset_key=dataset_key,
                source_record_id=f"{source_id}-{index}",
                record_hash=f"{index:064x}",
                quality_status="needs_review",
                fetched_at=now,
                as_of=None,
                payload=payload,
            )
        )
        session.flush()
        reviewed_payload = build_candidate_disaster_tracking_artifact(session)
        encoded = json.dumps(
            reviewed_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        artifact = session.get(PublicArtifact, "disaster-tracking")
        if artifact is None:
            artifact = PublicArtifact(artifact_key="disaster-tracking")
        artifact.artifact_group = "source_dataset"
        artifact.province_code = None
        artifact.content_hash = hashlib.sha256(encoded).hexdigest()
        artifact.source_path = "data/public/disaster_tracking.json"
        artifact.item_count = len(reviewed_payload["provinces"])
        artifact.payload = reviewed_payload
        session.add(artifact)
        session.commit()


def test_disaster_candidate_rows_are_not_public_without_publication_review():
    with TestClient(app) as client:
        now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            session.add(
                DashboardRecord(
                    source_id="spu_sukhothai_water",
                    dataset_key="water_levels.row",
                    source_record_id="unreviewed-candidate",
                    record_hash="f" * 64,
                    quality_status="needs_review",
                    fetched_at=now,
                    payload={
                        "province_th": "สุโขทัย",
                        "station_name_th": "candidate ที่ยังไม่ review",
                        "waterlevel_msl": 42.1,
                    },
                )
            )
            session.commit()

        tracking = client.get("/api/public/v1/provinces/64/disaster-tracking").json()
        assert tracking["source_count"] == 0
        assert tracking["record_count"] == 0
        assert "candidate ที่ยังไม่ review" not in json.dumps(tracking, ensure_ascii=False)


def test_disaster_tracking_uses_correct_province_mapping_and_safe_preview():
    with TestClient(app) as client:
        _seed_disaster_record(
            "spu_sukhothai_water",
            "water_levels.row",
            {
                "province_th": "สุโขทัย",
                "station_name_th": "สถานีทดสอบสุโขทัย",
                "amphoe_th": "เมืองสุโขทัย",
                "waterlevel_datetime": "2026-08-19T01:00:00+07:00",
                "waterlevel_msl": 42.1,
                "address": "hidden address",
                "phone": "0800000000",
                "email": "hidden@example.com",
                "token": "secret",
                "cookie": "secret",
            },
            1,
        )
        _seed_disaster_record(
            "spu_nsn_flood",
            "stations.row",
            {
                "station_name": "สถานีนครสวรรค์",
                "station_code": "NSN-1",
                "station_url": "https://nsn-flood.nsru.ac.th/water-station/1",
            },
            2,
        )
        _seed_disaster_record(
            "spu_rawangphai_uru",
            "rain_analysis.row",
            {
                "province": "อุตรดิตถ์",
                "timestamp": "2026-08-19T02:00:00+07:00",
                "avg_rain_mm": 12.5,
            },
            3,
        )

        provinces = client.get("/api/public/v1/disaster/provinces").json()["provinces"]
        assert provinces["64"]["sources"] == ["spu_sukhothai_water"]
        assert provinces["60"]["sources"] == ["spu_nsn_flood"]
        assert provinces["53"]["sources"] == ["spu_rawangphai_uru"]
        assert "68" not in provinces
        assert "69" not in provinces

        sukhothai = client.get("/api/public/v1/provinces/64/disaster-tracking")
        assert sukhothai.status_code == 200
        payload = sukhothai.json()
        assert payload["province_name"] == "สุโขทัย"
        assert payload["source_count"] == 1
        assert payload["record_count"] == 1
        response_text = json.dumps(payload, ensure_ascii=False)
        for sensitive in ("hidden address", "0800000000", "hidden@example.com", "secret"):
            assert sensitive not in response_text
        for forbidden_key in ("address", "phone", "email", "token", "cookie"):
            assert forbidden_key not in response_text

        assert client.get("/api/public/v1/provinces/68/disaster-tracking").json()[
            "source_count"
        ] == 0
        assert client.get("/api/public/v1/provinces/69/disaster-tracking").json()[
            "source_count"
        ] == 0


def test_public_catalog_exposes_live_disaster_counts():
    with TestClient(app) as client:
        _seed_disaster_record(
            "spu_sukhothai_care",
            "incidents.row",
            {"title": "ประกาศทดสอบ", "_fetched_at": "2026-08-19T01:00:00+00:00"},
            4,
        )
        _seed_disaster_record(
            "spu_sukhothai_water",
            "rain_24h.row",
            {"province_th": "สุโขทัย", "station_name_th": "สถานีฝน", "rainfall_datetime": "2026-08-19T02:00:00+00:00", "rain_24h": 4},
            5,
        )

        provinces = client.get("/api/public/v1/provinces").json()
        assert all("disaster_source_count" in row for row in provinces)
        assert all("disaster_record_count" in row for row in provinces)
        sukhothai = next(row for row in provinces if row["province_code"] == "64")
        assert sukhothai["disaster_source_count"] == 2
        assert sukhothai["disaster_record_count"] == 2
        assert sukhothai["disaster_sources"] == [
            "spu_sukhothai_care",
            "spu_sukhothai_water",
        ]


def test_sukhothai_water_filters_national_rows_to_sukhothai():
    with TestClient(app) as client:
        _seed_disaster_record(
            "spu_sukhothai_water",
            "water_levels.row",
            {
                "province_th": "สุโขทัย",
                "station_name_th": "สถานีสุโขทัย",
                "waterlevel_datetime": "2026-08-19T02:00:00+00:00",
                "waterlevel_msl": 31.2,
            },
            6,
        )
        _seed_disaster_record(
            "spu_sukhothai_water",
            "water_levels.row",
            {
                "province_th": "สุราษฎร์ธานี",
                "station_name_th": "สถานีนอกพื้นที่",
                "waterlevel_datetime": "2026-08-19T02:00:00+00:00",
                "waterlevel_msl": 4.7,
            },
            7,
        )

        payload = client.get("/api/public/v1/provinces/64/disaster-tracking").json()
        assert payload["source_count"] == 1
        assert payload["record_count"] == 1
        response_text = json.dumps(payload, ensure_ascii=False)
        assert "สถานีสุโขทัย" in response_text
        assert "สถานีนอกพื้นที่" not in response_text


def test_thaiwater_maps_national_rows_to_catalog_provinces():
    with TestClient(app) as client:
        _seed_disaster_record(
            "spu_sukhothai_water",
            "water_levels.row",
            {
                "province_th": "เชียงใหม่",
                "station_name_th": "สถานีเชียงใหม่",
                "waterlevel_datetime": "2026-08-19T01:00:00+00:00",
                "waterlevel_msl": 11.5,
            },
            8,
        )
        _seed_disaster_record(
            "spu_sukhothai_water",
            "water_levels.row",
            {
                "province_th": "สุโขทัย",
                "station_name_th": "สถานีสุโขทัย",
                "waterlevel_datetime": "2026-08-19T01:00:00+00:00",
                "waterlevel_msl": 22.5,
            },
            9,
        )

        provinces = client.get("/api/public/v1/disaster/provinces").json()["provinces"]
        assert "50" in provinces
        assert provinces["50"]["sources"] == ["spu_sukhothai_water"]

        chiang_mai = client.get("/api/public/v1/provinces/50/disaster-tracking").json()
        assert chiang_mai["province_name"] == "เชียงใหม่"
        assert chiang_mai["source_count"] == 1
        assert chiang_mai["record_count"] == 1
        response_text = json.dumps(chiang_mai, ensure_ascii=False)
        assert "ThaiWater ระดับน้ำ/ฝน/เขื่อน" in response_text
        assert "สถานีเชียงใหม่" in response_text
        assert "สถานีสุโขทัย" not in response_text


def test_disaster_station_history_aggregates_water_grains_without_raw_fields():
    with TestClient(app) as client:
        rows = [
            ("2026-06-01T07:00:00+00:00", 10.0),
            ("2026-06-02T07:00:00+00:00", 12.0),
            ("2026-07-01T07:00:00+00:00", 14.0),
        ]
        for offset, (timestamp, value) in enumerate(rows, start=20):
            _seed_disaster_record(
                "spu_sukhothai_water",
                "water_levels.row",
                {
                    "province_th": "เชียงใหม่",
                    "station_id": 900,
                    "station_name_th": "สถานีประวัติน้ำ",
                    "waterlevel_datetime": timestamp,
                    "waterlevel_msl": value,
                    "phone": "0800000000",
                },
                offset,
            )

        daily = client.get(
            "/api/public/v1/provinces/50/disaster-stations/900/history?metric=water&grain=daily&days=90"
        )
        assert daily.status_code == 200
        payload = daily.json()
        assert payload["history_status"] == "snapshot_only"
        assert payload["unit"] == "ม.รทก."
        assert payload["station_name"] == "สถานีประวัติน้ำ"
        assert [point["v"] for point in payload["points"]] == [10.0, 12.0, 14.0]
        assert "0800000000" not in json.dumps(payload, ensure_ascii=False)
        assert "phone" not in json.dumps(payload, ensure_ascii=False)

        monthly = client.get(
            "/api/public/v1/provinces/50/disaster-stations/900/history?metric=water&grain=monthly&days=90"
        ).json()
        assert monthly["points"] == [
            {"t": "2026-06", "v": 11.0, "samples": 2},
            {"t": "2026-07", "v": 14.0, "samples": 1},
        ]


def test_disaster_station_history_uses_stable_station_code_identity():
    with TestClient(app) as client:
        _seed_disaster_record(
            "spu_sukhothai_water",
            "water_levels.row",
            {
                "province_th": "สุโขทัย",
                "station_id": 2972,
                "station_code": "Y.15",
                "station_name_th": "บ้านกง",
                "waterlevel_datetime": "2026-08-19T16:00:00+00:00",
                "waterlevel_msl": 41.33,
            },
            40,
        )
        _seed_disaster_record(
            "spu_sukhothai_water",
            "water_levels.row",
            {
                "province_th": "สุโขทัย",
                "station_id": 11688944,
                "station_code": "ridhydro_Y.15",
                "station_name_th": "บ้านกง",
                "waterlevel_datetime": "2026-08-19T21:00:00+00:00",
                "waterlevel_msl": 41.30,
            },
            41,
        )

        detail = client.get("/api/public/v1/provinces/64/disaster-tracking").json()
        water = detail["sources"]["spu_sukhothai_water"]["insights"]["trends"][0]
        station = next(item for item in water["series"] if item["station_id"] == "Y.15")
        assert station["label"] == "บ้านกง"
        assert len(station["points"]) == 2

        history = client.get(
            "/api/public/v1/provinces/64/disaster-stations/Y.15/history?metric=water&grain=daily&days=90"
        ).json()
        assert history["history_status"] == "snapshot_only"
        assert history["points"] == [{"t": "2026-08-19", "v": 41.315, "samples": 2}]


def test_disaster_station_history_aggregates_rain_totals_and_unavailable():
    with TestClient(app) as client:
        rows = [
            ("2026-06-01T07:00:00+00:00", 2.0),
            ("2026-06-02T07:00:00+00:00", 3.0),
            ("2026-06-09T07:00:00+00:00", 5.0),
        ]
        for offset, (timestamp, value) in enumerate(rows, start=30):
            _seed_disaster_record(
                "spu_sukhothai_water",
                "rain_24h.row",
                {
                    "province_th": "เชียงใหม่",
                    "station_id": 901,
                    "station_name_th": "สถานีประวัติฝน",
                    "rainfall_datetime": timestamp,
                    "rain_24h": value,
                },
                offset,
            )

        weekly = client.get(
            "/api/public/v1/provinces/50/disaster-stations/901/history?metric=rain&grain=weekly&days=90"
        ).json()
        assert weekly["unit"] == "มม."
        assert weekly["history_status"] == "snapshot_only"
        assert [point["v"] for point in weekly["points"]] == [5.0, 5.0]

        unavailable = client.get(
            "/api/public/v1/provinces/50/disaster-stations/missing/history?metric=rain&grain=daily&days=90"
        ).json()
        assert unavailable["history_status"] == "unavailable"
        assert unavailable["points"] == []


def test_reviewed_downloads_support_head_without_exposing_internal_paths():
    download_path = PUBLIC_ROOT / "province_evidence.csv"

    with TestClient(app) as client:
        get_response = client.get("/downloads/province_evidence.csv")
        head_response = client.head("/downloads/province_evidence.csv")

        assert get_response.status_code == 200
        assert head_response.status_code == 200
        assert head_response.content == b""
        assert head_response.headers["content-length"] == str(download_path.stat().st_size)
        assert head_response.headers["content-type"] == get_response.headers["content-type"]
        assert head_response.headers["etag"] == get_response.headers["etag"]

        for blocked_path in (
            "publication_receipt.json",
            "serving_manifest.json",
            "%2e%2e%2fpublication_receipt.json",
            "%2e%2e%5cserving_manifest.json",
        ):
            assert client.head(f"/downloads/{blocked_path}").status_code == 404


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
    expected_province_count = next(
        output["expected_count"]
        for output in dashboard_contract["outputs"]
        if output.get("path") == "data/public/public_dashboard.json"
    )
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
        assert all_provinces == catalog_with_default_disaster_fields(dashboard)
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
            row
            for row in catalog_with_default_disaster_fields(dashboard)
            if row["province_code"] == "45"
        )

        songkhla = client.get("/api/public/v1/provinces/90")
        assert songkhla.status_code == 200
        songkhla_payload = songkhla.json()
        assert songkhla_payload["province_name_th"] == "สงขลา"
        assert songkhla_payload == next(
            row
            for row in catalog_with_default_disaster_fields(dashboard)
            if row["province_code"] == "90"
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
        assert cultural_insight["privacy_projection"]["public_work_details"] is True
        assert cultural_insight["privacy_projection"]["account_identifiers_exposed"] is False
        assert len(cultural_insight["public_records"]) == cultural_insight["coverage"]["supporting_records"]
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
        assert boundary == boundaries_with_default_disaster_fields(boundary_artifact)
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
        assert "f2_target_household" not in source_ids
        assert "f3_healthcare_nonthaburi" not in source_ids
        assert "f3_nonthaburi_city_learning" not in source_ids


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
                        source_id="f3_healthcare_nonthaburi",
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
            "/api/records?source_id=f3_healthcare_nonthaburi"
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
        dashboard_contract = read_json(
            PROJECT_ROOT / "config" / "publication_contracts" / "dashboard_core.json"
        )
        published_dashboard_ids = set(dashboard_contract["source_ids"])
        assert baseline_payload["published_catalog_source_count"] == len(
            published_dashboard_ids
        )
        assert baseline_payload["published_catalog_source_count"] <= approved_count
        assert baseline_payload["published_catalog_ids_match_approved"] is True
        assert baseline_payload["restricted_catalog_sources_published"] == 0
        assert baseline_payload["restricted_values_published"] == 0

        with SessionLocal() as session:
            catalog = session.get(PublicArtifact, "catalog")
            payload = dict(catalog.payload)
            sources = [dict(source) for source in payload["sources"]]
            sources[0]["source_id"] = "f3_healthcare_nonthaburi"
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
    assert len(public_operations) == 35
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
