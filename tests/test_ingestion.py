from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.catalog import load_ingestion_plans, source_config, sync_catalog
from app.database import SessionLocal
from app.ingestion import (
    IngestionFetchError,
    IngestionPipeline,
    PolicyViolation,
    ResponseRecorder,
)
from app.models import DashboardRecord, IngestionRun, Source
from app.settings import Settings


class StubJsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class StubRecorder:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return StubJsonResponse(self.payload), None


class SequenceRecorder:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return StubJsonResponse(next(self.payloads)), None


def test_snapshot_ingestion_sanitizes_contact_fields(tmp_path):
    source_root = tmp_path / "f2_rmutdb"
    source_root.mkdir()
    with (source_root / "data.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "title", "email", "phone", "note"])
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "title": "ตัวอย่าง",
                "email": "person@example.com",
                "phone": "0812345678",
                "note": "ติดต่อ person@example.com หรือ 0899999999",
            }
        )

    settings = Settings(
        app_env="local",
        database_url="sqlite:///unused.sqlite",
        snapshot_root=tmp_path,
        max_records_per_source=100,
    )
    with SessionLocal() as session:
        sync_catalog(session)
        result = IngestionPipeline(session, settings).ingest_source(
            "f2_rmutdb",
            strategy="snapshot",
        )
        assert result["records_loaded"] == 1
        record = session.scalar(select(DashboardRecord))
        assert record is not None
        assert "email" not in record.payload
        assert "phone" not in record.payload
        assert "person@example.com" not in record.payload["note"]
        assert "0899999999" not in record.payload["note"]


def test_operational_candidate_removes_person_name_containers_and_fields():
    from app.privacy import sanitize_payload

    payload = sanitize_payload(
        {
            "id": 1,
            "name": "ชื่อนวัตกรรมที่เผยแพร่ได้",
            "ownerContact": {
                "name": "ชื่อบุคคล",
                "lastname": "นามสกุลบุคคล",
                "email": "person@example.com",
            },
            "researcherName": "ชื่อผู้วิจัย",
        }
    )

    assert payload == {"id": 1, "name": "ชื่อนวัตกรรมที่เผยแพร่ได้"}


def test_apptech_mtr_driver_rejects_incomplete_or_duplicate_pagination():
    plan = {
        "url": "https://example.test/apptech",
        "page_size": 2,
        "query_params": {
            "__template": "appTech.public.list",
            "offset": "$OFFSET",
            "max": "$PAGE_SIZE",
        },
    }
    settings = Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=10)
    with SessionLocal() as session:
        pipeline = IngestionPipeline(session, settings)
        incomplete = SequenceRecorder(
            [
                {"data": [{"id": 1}, {"id": 2}], "totalCount": 3},
                {"data": [], "totalCount": 3},
            ]
        )
        with pytest.raises(RuntimeError, match="incomplete pagination"):
            pipeline._fetch_apptech_mtr(plan, incomplete)

        duplicate = SequenceRecorder(
            [
                {"data": [{"id": 1}, {"id": 2}], "totalCount": 3},
                {"data": [{"id": 2}], "totalCount": 3},
            ]
        )
        with pytest.raises(RuntimeError, match="duplicate id=2"):
            pipeline._fetch_apptech_mtr(plan, duplicate)


def test_restricted_sources_are_blocked_and_approved_public_sources_pass_guard():
    settings = Settings(
        app_env="local",
        database_url="sqlite:///unused.sqlite",
        allow_pending_owner_sources=False,
    )
    with SessionLocal() as session:
        sync_catalog(session)
        pipeline = IngestionPipeline(session, settings)
        with pytest.raises(PolicyViolation):
            pipeline.ingest_source("f3_healthcare_nonthaburi")
        pipeline._guard_source(source_config("f3_city_capital_open_data"))
        pipeline._guard_source(source_config("f2_wallet_all_realtime"))
        pipeline._guard_source(source_config("f2_target_household"))


def test_production_allows_approved_source_but_blocks_nonthaburi():
    settings = Settings(
        app_env="production",
        database_url="sqlite:///unused.sqlite",
        allow_pending_owner_sources=False,
    )
    with SessionLocal() as session:
        sync_catalog(session)
        pipeline = IngestionPipeline(session, settings)
        pipeline._guard_source(source_config("f2_apptech_mtr"))
        pipeline._guard_source(source_config("f2_wallet_cluster_realtime"))
        with pytest.raises(PolicyViolation):
            pipeline.ingest_source("f3_nonthaburi_city_learning")


def test_learning_dashboard_driver_keeps_all_source_grains_separate():
    payload = {
        "provinces": [["Province", "ธุรกิจชุมชน"], ["สงขลา", 10]],
        "entityTypes": [["Entity Type", "Popularity"], ["กลุ่ม", 2]],
        "categories": [["Category", "Popularity"], ["อาหาร", 3]],
        "geography": [["Geography", "Popularity"], ["ภาคใต้", 4]],
        "geographyImpact": [{"geography": "ภาคใต้", "employee": 5}],
        "impactSummary": {"totalEmployeeAmount": 5},
        "excludedResourceExpense": {"value": 1},
    }
    plan = {
        "url": "https://lesuper.app/api/opendata/pmua",
        "body_mode": "json_empty",
        "expected_keys": list(payload),
        "scope_warning_th": "selected project scope",
    }
    recorder = StubRecorder(payload)
    settings = Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0)
    with SessionLocal() as session:
        records = IngestionPipeline(session, settings)._fetch_learning_dashboard(plan, recorder)

    assert recorder.calls[0][0] == "POST"
    assert recorder.calls[0][2]["json_body"] == {}
    assert [dataset for dataset, _ in records] == [
        "provinces",
        "entityTypes",
        "categories",
        "geography",
        "geographyImpact",
        "impactSummary",
        "excludedResourceExpense",
    ]
    assert all(record["unit"] is None and record["as_of"] is None for _, record in records)
    assert all(record["scope_warning_th"] == "selected project scope" for _, record in records)


def test_pmua_area_based_driver_keeps_rows_and_all_visible_aggregate_grains():
    payload = {
        "data": [
            {
                "id": "a",
                "region": "เหนือ",
                "province": "เชียงใหม่",
                "district": "เมือง",
                "subDistrict": "ช้างคลาน",
                "researchUnit": "มรภ.",
                "fiscalYear": "2567",
            },
            {
                "id": "b",
                "region": "ใต้",
                "province": None,
                "district": None,
                "subDistrict": None,
                "researchUnit": "มทร.",
                "fiscalYear": "2566",
            },
        ],
        "stats": {
            "totalRecords": 2,
            "byRegion": {"เหนือ": 1, "ใต้": 1},
            "byProvince": {"เชียงใหม่": 1},
            "byDistrict": {"เมือง": 1},
            "bySubDistrict": {"ช้างคลาน": 1},
            "byBusinessType": {"เกษตรกรรม": 1, "อื่นๆ": 1},
            "byResearchUnit": {"มรภ.": 1, "มทร.": 1},
            "byFiscalYear": {"2567": 1, "2566": 1},
        },
    }
    recorder = StubRecorder(payload)
    settings = Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0)
    with SessionLocal() as session:
        records = IngestionPipeline(session, settings)._fetch_pmua(
            {"url": "https://lesuper.app/api/opendata/pmua/area-based"}, recorder
        )

    assert [row for dataset, row in records if dataset == "area_based"] == payload["data"]
    business_types = {
        row["label"]: row["value"]
        for dataset, row in records
        if dataset == "aggregate_byBusinessType"
    }
    assert business_types == {"เกษตรกรรม": 1, "อื่นๆ": 1}
    assert any(
        dataset == "aggregate_summary" and row["value"] == 2
        for dataset, row in records
    )


def test_pmua_area_based_driver_rejects_count_mismatch():
    payload = {
        "data": [{"id": "a"}],
        "stats": {
            "totalRecords": 2,
            "byRegion": {},
            "byProvince": {},
            "byDistrict": {},
            "bySubDistrict": {},
            "byBusinessType": {},
            "byResearchUnit": {},
            "byFiscalYear": {},
        },
    }
    recorder = StubRecorder(payload)
    settings = Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0)
    with SessionLocal() as session:
        with pytest.raises(RuntimeError, match=r"incomplete: rows=1, totalRecords=2"):
            IngestionPipeline(session, settings)._fetch_pmua(
                {"url": "https://lesuper.app/api/opendata/pmua/area-based"}, recorder
            )


def test_housing_ckan_driver_requires_complete_packages_resources_and_rows():
    class HousingResponse:
        def __init__(self, *, payload=None, content=b"", content_type="application/json"):
            self._payload = payload
            self.content = content
            self.headers = {"content-type": content_type}

        def json(self):
            return self._payload

    class HousingRecorder:
        def request(self, _method, url, *, name, params=None):
            if name.startswith("package_"):
                return (
                    HousingResponse(
                        payload={
                            "success": True,
                            "result": {
                                "name": params["id"],
                                "resources": [
                                    {
                                        "id": "resource-1",
                                        "url": "https://example.test/data.csv",
                                        "name": "sample",
                                    }
                                ],
                            },
                        }
                    ),
                    Path("package.json"),
                )
            assert url == "https://example.test/data.csv"
            return (
                HousingResponse(
                    content=b"id,value\n1,alpha\n2,beta\n",
                    content_type="text/csv",
                ),
                Path("data.csv"),
            )

    plan = {
        "package_show_url": "https://example.test/package_show",
        "expected_dataset_count": 1,
        "expected_resource_count": 1,
        "expected_value_resource_count": 1,
        "expected_value_record_count": 2,
        "datasets": [{"id": "sample", "value_policy": "values"}],
    }
    settings = Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0)
    with SessionLocal() as session:
        pipeline = IngestionPipeline(session, settings)
        records = pipeline._fetch_housing(
            {"expected_record_count": 2},
            plan,
            HousingRecorder(),
        )
        assert records == [
            (
                "sample:resource-1",
                {
                    "resource_id": "resource-1",
                    "resource_name": "sample",
                    "row_number": 1,
                    "source_fields": {"id": "1", "value": "alpha"},
                },
            ),
            (
                "sample:resource-1",
                {
                    "resource_id": "resource-1",
                    "resource_name": "sample",
                    "row_number": 2,
                    "source_fields": {"id": "2", "value": "beta"},
                },
            ),
        ]

        incomplete_plan = {**plan, "expected_value_record_count": 3}
        with pytest.raises(RuntimeError, match=r"value records=2; expected 3"):
            pipeline._fetch_housing(
                {"expected_record_count": 3},
                incomplete_plan,
                HousingRecorder(),
            )


def test_city_capital_snapshot_gate_requires_complete_city_metric_cartesian_product():
    source = {"expected_record_count": 2}
    complete = [
        ("latest.cities", {"city_id": "c1"}),
        ("latest.metrics", {"metric_id": "m1"}),
        ("latest.metrics", {"metric_id": "m2"}),
        ("latest.observations", {"city_id": "c1", "metric_id": "m1", "value": 1}),
        ("latest.observations", {"city_id": "c1", "metric_id": "m2", "value": None}),
    ]
    IngestionPipeline._validate_city_capital_snapshot(source, complete)

    with pytest.raises(RuntimeError, match=r"observations=1 but cities\*metrics=2"):
        IngestionPipeline._validate_city_capital_snapshot(source, complete[:-1])


def test_ruamthiao_snapshot_gate_normalizes_all_visible_content():
    project_root = Path(__file__).resolve().parents[2]
    snapshot_root = (
        project_root
        / "data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01"
        / "16_f3_ruamthiao_lamphun/data"
    )
    if not snapshot_root.is_dir():
        pytest.skip("full tourism snapshot evidence is not included in the public clone")
    files = sorted(snapshot_root.glob("*.json"))
    records = IngestionPipeline._read_ruamthiao_snapshot(
        {"expected_record_count": 54},
        files,
    )

    counts = Counter(dataset for dataset, _ in records)
    assert counts == {
        "tourism_stations": 12,
        "tourism_venues": 97,
        "recommendations": 13,
        "transport_services": 13,
        "lantern_groups": 10,
        "emergency_numbers": 6,
        "service_contacts": 3,
        "resources": 3,
    }
    assert len(records) == 157

    with pytest.raises(RuntimeError, match="missing pages: travel"):
        IngestionPipeline._read_ruamthiao_snapshot(
            {"expected_record_count": 54},
            [path for path in files if path.name != "travel.json"],
        )


def test_apptech_mru_driver_uses_nested_json_contract_and_browser_origin_headers():
    payload = {"data": {"data": [{"innovationid": "1"}], "totaldata": 1}}
    plan = {
        "page_size": 12,
        "datasets": [
            {
                "name": "innovation",
                "url": "https://38rat.nstru.ac.th/backend/ajax/public/innovation.php",
                "json_body": {
                    "action": "fetch_innovationAll_JSON",
                    "filter": {
                        "innovationgroup": "All",
                        "orderby": 1,
                        "startlimit": "$OFFSET",
                        "endlimit": "$PAGE_SIZE",
                        "maxpage": 0,
                        "targetpagenumber": "$PAGE_NUMBER",
                    },
                },
            }
        ],
    }
    recorder = StubRecorder(payload)
    settings = Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0)
    with SessionLocal() as session:
        records = IngestionPipeline(session, settings)._fetch_apptech_mru(plan, recorder)

    request = recorder.calls[0][2]
    assert request["json_body"]["action"] == "fetch_innovationAll_JSON"
    assert "action" not in request["json_body"]["filter"]
    assert request["json_body"]["filter"]["startlimit"] == 0
    assert request["headers"]["Origin"] == "https://38rat.nstru.ac.th"
    assert records == [("innovation", {"innovationid": "1"})]


def test_apptech_mru_driver_rejects_incomplete_pagination_before_database_commit():
    plan = {
        "page_size": 12,
        "datasets": [
            {
                "name": "innovation",
                "url": "https://38rat.nstru.ac.th/backend/ajax/public/innovation.php",
                "json_body": {
                    "action": "fetch_innovationAll_JSON",
                    "filter": {
                        "startlimit": "$OFFSET",
                        "endlimit": "$PAGE_SIZE",
                        "maxpage": 0,
                        "targetpagenumber": "$PAGE_NUMBER",
                    },
                },
            }
        ],
    }
    recorder = SequenceRecorder(
        [
            {
                "data": {
                    "data": [{"innovationid": str(index)} for index in range(1, 13)],
                    "totaldata": 13,
                }
            },
            {"data": {"data": [], "totaldata": 13}},
        ]
    )
    settings = Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0)
    with SessionLocal() as session:
        with pytest.raises(RuntimeError, match=r"incomplete: unique=12.*reported_total=13"):
            IngestionPipeline(session, settings)._fetch_apptech_mru(plan, recorder)


def test_response_recorder_keeps_http_error_body_before_raising(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.PROJECT_ROOT", tmp_path)
    settings = Settings(
        database_url="sqlite:///unused.sqlite",
        http_delay_seconds=0,
    )
    recorder = ResponseRecorder("sample", "failed-run", settings)
    recorder.client.close()
    recorder.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                400,
                json={"status": False, "message": "invalid request"},
                request=request,
            )
        )
    )

    with pytest.raises(httpx.HTTPStatusError):
        recorder.request("POST", "https://example.test/api", name="bad_request")
    manifest_path = recorder.write_manifest(
        "sample",
        "failed-run",
        0,
        status="failed",
        error="HTTPStatusError: 400",
    )
    recorder.close()

    response_path = tmp_path / "data/runtime/raw/sample/failed-run/0001_bad_request.json"
    assert json.loads(response_path.read_text(encoding="utf-8"))["message"] == "invalid request"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["artifacts"][0]["http_status"] == 400
    assert manifest["artifacts"][0]["sha256"]


def test_response_recorder_rejects_url_outside_runtime_endpoint_allowlist(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.PROJECT_ROOT", tmp_path)
    settings = Settings(database_url="sqlite:///unused.sqlite", http_delay_seconds=0)
    recorder = ResponseRecorder(
        "sample",
        "endpoint-policy",
        settings,
        runtime_endpoints=[
            {
                "method": "GET",
                "url": "https://example.test/allowed?catalog=query",
                "runtime_enabled": True,
            },
            {
                "method": "GET",
                "url": "https://example.test/dynamic",
                "runtime_enabled": True,
                "request_template": {
                    "query_or_body": "page=<value>&year=2569",
                },
            },
            {
                "method": "POST",
                "url": "https://example.test/read",
                "runtime_enabled": True,
                "request_template": {
                    "query_or_body": "action=read",
                    "json_body": {
                        "action": "read",
                        "filter": {"offset": "<value>", "scope": "public"},
                    },
                },
            },
            {
                "method": "POST",
                "url": "https://example.test/empty",
                "runtime_enabled": True,
                "request_template": {"query_or_body": "", "json_body": {}},
            },
            {
                "method": "POST",
                "url": "https://example.test/post-query",
                "runtime_enabled": True,
                "request_template": {"query": "version=1", "json_body": {}},
            },
            {
                "method": "GET",
                "url": "https://example.test/restricted-but-misconfigured",
                "runtime_enabled": True,
                "restricted": True,
            },
            {
                "method": "GET",
                "url": "https://example.test/disabled",
                "runtime_enabled": False,
            },
        ],
    )
    recorder.client.close()
    recorder.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ok": True}, request=request)
        )
    )
    try:
        with pytest.raises(PolicyViolation, match="outside the enabled endpoint allowlist"):
            recorder.request("GET", "https://example.test/not-allowed", name="blocked")
        with pytest.raises(PolicyViolation, match="outside the enabled endpoint allowlist"):
            recorder.request("POST", "https://example.test/allowed", name="wrong-method")
        with pytest.raises(PolicyViolation, match="outside the enabled endpoint allowlist"):
            recorder.request(
                "GET",
                "https://example.test/allowed?runtime=different-query",
                name="wrong-static-query",
            )
        response, _ = recorder.request(
            "GET",
            "https://example.test/allowed",
            params={"catalog": "query"},
            name="allowed",
        )
        assert response.status_code == 200
        dynamic, _ = recorder.request(
            "GET",
            "https://example.test/dynamic",
            params={"page": 2, "year": "2569"},
            name="allowed-dynamic",
        )
        assert dynamic.status_code == 200
        with pytest.raises(PolicyViolation, match="outside the enabled endpoint allowlist"):
            recorder.request(
                "GET",
                "https://example.test/dynamic",
                params={"page": 2, "year": "2569", "admin": "true"},
                name="extra-query-key",
            )
        with pytest.raises(PolicyViolation, match="outside the enabled endpoint allowlist"):
            recorder.request(
                "GET",
                "https://example.test/dynamic",
                params={"page": 2},
                name="missing-query-key",
            )
        with pytest.raises(PolicyViolation, match="outside the enabled endpoint allowlist"):
            recorder.request(
                "GET",
                "https://example.test/dynamic",
                params={"page": 2, "year": "2570"},
                name="wrong-static-value",
            )
        post_response, _ = recorder.request(
            "POST",
            "https://example.test/read",
            json_body={"action": "read", "filter": {"offset": 0, "scope": "public"}},
            name="allowed-json-body",
        )
        assert post_response.status_code == 200
        with pytest.raises(PolicyViolation, match="outside the enabled endpoint allowlist"):
            recorder.request(
                "POST",
                "https://example.test/read",
                json_body={"action": "write", "filter": {"offset": 0, "scope": "public"}},
                name="wrong-json-action",
            )
        with pytest.raises(PolicyViolation, match="outside the enabled endpoint allowlist"):
            recorder.request(
                "POST",
                "https://example.test/read",
                json_body={
                    "action": "read",
                    "filter": {"offset": 0, "scope": "public", "admin": True},
                },
                name="extra-json-field",
            )
        empty_response, _ = recorder.request(
            "POST",
            "https://example.test/empty",
            json_body={},
            name="allowed-empty-json",
        )
        assert empty_response.status_code == 200
        with pytest.raises(PolicyViolation, match="outside the enabled endpoint allowlist"):
            recorder.request(
                "POST",
                "https://example.test/empty",
                json_body={"unexpected": True},
                name="wrong-empty-json",
            )
        queried_post, _ = recorder.request(
            "POST",
            "https://example.test/post-query",
            params={"version": "1"},
            json_body={},
            name="allowed-post-query",
        )
        assert queried_post.status_code == 200
        with pytest.raises(PolicyViolation, match="outside the enabled endpoint allowlist"):
            recorder.request(
                "POST",
                "https://example.test/post-query",
                params={"version": "2"},
                json_body={},
                name="wrong-post-query",
            )
        with pytest.raises(PolicyViolation, match="outside the enabled endpoint allowlist"):
            recorder.request(
                "GET",
                "https://example.test/restricted-but-misconfigured",
                name="restricted-endpoint",
            )
        assert ResponseRecorder._body_matches(1, True) is False
        assert ResponseRecorder._body_matches(0, False) is False
    finally:
        recorder.close()


def test_response_recorder_does_not_follow_redirect_outside_allowlist(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.PROJECT_ROOT", tmp_path)
    settings = Settings(database_url="sqlite:///unused.sqlite", http_delay_seconds=0)
    recorder = ResponseRecorder(
        "sample",
        "redirect-policy",
        settings,
        runtime_endpoints=[
            {
                "method": "GET",
                "url": "https://example.test/allowed",
                "runtime_enabled": True,
            }
        ],
    )
    requested_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        if request.url.host == "example.test":
            return httpx.Response(
                302,
                headers={"location": "http://127.0.0.1/internal"},
                request=request,
            )
        return httpx.Response(200, json={"secret": "must-not-be-read"}, request=request)

    recorder.client.close()
    recorder.client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    try:
        with pytest.raises(httpx.HTTPStatusError, match="302"):
            recorder.request("GET", "https://example.test/allowed", name="redirect")
        assert requested_hosts == ["example.test"]
        assert recorder.artifacts[0]["http_status"] == 302
    finally:
        recorder.close()


def test_all_executable_plan_requests_match_the_generated_runtime_allowlist():
    plans = load_ingestion_plans()["sources"]

    def recorder_for(source_id: str) -> ResponseRecorder:
        source = source_config(source_id)
        recorder = object.__new__(ResponseRecorder)
        recorder.allowed_endpoints = [
            ResponseRecorder._endpoint_rule(endpoint)
            for endpoint in source["endpoints"]
            if endpoint.get("runtime_enabled") is True
        ]
        return recorder

    def resolve(value, replacements):
        if isinstance(value, dict):
            return {key: resolve(item, replacements) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item, replacements) for item in value]
        return replacements.get(value, value) if isinstance(value, str) else value

    sra_recorder = recorder_for("f1_sradss_ppaos")
    for request in plans["f1_sradss_ppaos"]["requests"]:
        params = {
            key: ("2569" if value == "$SRA_YEAR" else value)
            for key, value in request.get("params", {}).items()
        }
        assert sra_recorder._request_is_allowed("GET", request["url"], params)

    ppp_recorder = recorder_for("f1_pppconnext")
    for request in plans["f1_pppconnext"]["requests"]:
        assert ppp_recorder._request_is_allowed("GET", request["url"], None)
    assert not ppp_recorder._request_is_allowed(
        "GET",
        "https://ppaos.com/2026/api/khm/v1/dashboard/ppaos-province-analytics",
        {"prov_code": "18"},
    )
    assert not ppp_recorder._request_is_allowed(
        "GET",
        "https://ppaos.com/2026/api/khm/v1/areas/provinces",
        None,
    )

    apptech_recorder = recorder_for("f2_apptech_mtr")
    apptech_plan = plans["f2_apptech_mtr"]
    apptech_params = {
        key: (0 if value == "$OFFSET" else 99 if value == "$PAGE_SIZE" else value)
        for key, value in apptech_plan["query_params"].items()
    }
    assert apptech_recorder._request_is_allowed(
        "GET",
        apptech_plan["url"],
        apptech_params,
    )
    assert not apptech_recorder._request_is_allowed(
        "GET",
        apptech_plan["url"],
        {**apptech_params, "scope": "unreviewed"},
    )

    mru_recorder = recorder_for("f2_apptech_mru")
    for dataset in plans["f2_apptech_mru"]["datasets"]:
        body = resolve(
            dataset["json_body"],
            {"$OFFSET": 0, "$PAGE_SIZE": 12, "$PAGE_NUMBER": 1},
        )
        assert mru_recorder._request_is_allowed(
            "POST", dataset["url"], None, None, body
        )
        assert not mru_recorder._request_is_allowed(
            "POST",
            dataset["url"],
            None,
            None,
            {**body, "action": "unreviewed_write_action"},
        )

    learning_plan = plans["f2_learning_dashboard"]
    learning_recorder = recorder_for("f2_learning_dashboard")
    assert learning_recorder._request_is_allowed(
        "POST", learning_plan["url"], None, None, {}
    )
    assert not learning_recorder._request_is_allowed(
        "POST", learning_plan["url"], None, None, {"scope": "unreviewed"}
    )

    area_plan = plans["f2_learning_area_based"]
    area_recorder = recorder_for("f2_learning_area_based")
    assert area_recorder._request_is_allowed("GET", area_plan["url"], None)

    target_plan = plans["f2_target_household"]
    target_recorder = recorder_for("f2_target_household")
    assert target_recorder._request_is_allowed(
        "GET",
        target_plan["url"],
        {"page": 1},
    )
    assert not target_recorder._request_is_allowed("GET", target_plan["url"], None)
    for dashboard_url in [
        "https://pmua-apptech.com/dashboard",
        "https://pmua-apptech.com/dashboard/innovatordashboard",
        "https://pmua-apptech.com/dashboard/familydashboard",
    ]:
        assert target_recorder._request_is_allowed("GET", dashboard_url, None)
        assert target_recorder._request_is_allowed("GET", dashboard_url, {"year_filter": "2025"})
        assert not target_recorder._request_is_allowed("GET", dashboard_url, {"scope": "unreviewed"})

    wallet_all_recorder = recorder_for("f2_wallet_all_realtime")
    for request in plans["f2_wallet_all_realtime"]["requests"]:
        assert wallet_all_recorder._request_is_allowed(
            "POST",
            request["url"],
            None,
            None,
            request["json_body"],
        )
        assert not wallet_all_recorder._request_is_allowed(
            "POST",
            request["url"],
            None,
            None,
            {"date": "2026-08-31"},
        )
        assert not wallet_all_recorder._request_is_allowed("GET", request["url"], None)

    wallet_cluster_recorder = recorder_for("f2_wallet_cluster_realtime")
    for request in plans["f2_wallet_cluster_realtime"]["requests"]:
        assert wallet_cluster_recorder._request_is_allowed(
            "POST",
            request["url"],
            None,
            None,
            request["json_body"],
        )
        assert not wallet_cluster_recorder._request_is_allowed(
            "POST",
            request["url"],
            None,
            None,
            {"date": ""},
        )

    housing_source = source_config("f3_housing_portal")
    housing_recorder = recorder_for("f3_housing_portal")
    housing_plan = plans["f3_housing_portal"]
    allowed_dataset_ids = {dataset["id"] for dataset in housing_plan["datasets"]}
    for dataset_id in allowed_dataset_ids:
        assert housing_recorder._request_is_allowed(
            "GET",
            housing_plan["package_show_url"],
            {"id": dataset_id},
        )
    assert not housing_recorder._request_is_allowed(
        "GET",
        housing_plan["package_show_url"],
        {"id": "unreviewed-package"},
    )
    resource_endpoints = [
        endpoint
        for endpoint in housing_source["endpoints"]
        if endpoint.get("kind") == "ckan_resource_download"
    ]
    enabled_resource_urls = {
        endpoint["url"]
        for endpoint in resource_endpoints
        if endpoint.get("runtime_enabled") is True
    }
    assert len(resource_endpoints) == housing_plan["expected_resource_count"]
    assert len(enabled_resource_urls) == housing_plan["expected_value_resource_count"]
    assert not (set(housing_plan["runtime_excluded_urls"]) & enabled_resource_urls)
    for url in enabled_resource_urls:
        assert housing_recorder._request_is_allowed("GET", url, None)
    for url in housing_plan["runtime_excluded_urls"]:
        assert not housing_recorder._request_is_allowed("GET", url, None)


def test_contract_batch_is_fully_validated_before_candidate_rows_are_added():
    source = source_config("f2_apptech_mtr")
    settings = Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0)
    with SessionLocal() as session:
        pipeline = IngestionPipeline(session, settings)
        with pytest.raises(ValueError, match="none of the contract identity_options"):
            pipeline._store_records(
                source,
                [
                    ("innovations", {"id": "valid-first", "year": "2569"}),
                    ("innovations", {"name": "missing identity"}),
                ],
            )
        assert session.scalars(select(DashboardRecord)).all() == []

        loaded, skipped, as_of = pipeline._store_records(
            source,
            [("innovations", {"id": "valid-first", "year": "2569"})],
        )
        session.flush()
        record = session.scalar(select(DashboardRecord))
        assert (loaded, skipped, as_of) == (1, 0, "2569")
        assert record is not None
        assert record.source_record_id == "valid-first"
        assert record.as_of == "2569"


@pytest.mark.parametrize(
    ("strategy", "expected_strategy"),
    [("snapshot", "snapshot"), ("auto", "api_then_snapshot")],
)
def test_api_source_snapshot_paths_keep_legacy_dataset_normalization(
    tmp_path,
    monkeypatch,
    strategy,
    expected_strategy,
):
    snapshot_root = tmp_path / "snapshots"
    source_root = snapshot_root / "f2_apptech_mtr"
    source_root.mkdir(parents=True)
    (source_root / "apptech_public_innovation.jsonl").write_text(
        json.dumps({"id": "snapshot-record-1", "year": "2568"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.settings.PROJECT_ROOT", tmp_path)
    settings = Settings(
        database_url="sqlite:///unused.sqlite",
        snapshot_root=snapshot_root,
        max_records_per_source=0,
    )

    with SessionLocal() as session:
        sync_catalog(session)
        pipeline = IngestionPipeline(session, settings)
        if strategy == "auto":
            monkeypatch.setattr(
                pipeline,
                "_fetch_api",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("upstream failed")),
            )

        result = pipeline.ingest_source("f2_apptech_mtr", strategy=strategy)

        record = session.scalar(select(DashboardRecord))
        assert result["strategy"] == expected_strategy
        assert result["records_loaded"] == 1
        assert record is not None
        assert record.dataset_key == "apptech_public_innovation"
        assert record.source_record_id == "snapshot-record-1"


def test_failed_ingestion_rolls_back_candidate_rows_before_marking_run_failed(
    tmp_path,
    monkeypatch,
):
    failed_manifest = tmp_path / "manifest.json"
    failed_manifest.write_text("{}\n", encoding="utf-8")
    source = source_config("f2_apptech_mtr")
    settings = Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0)

    with SessionLocal() as session:
        session.add(
            Source(
                source_id=source["source_id"],
                ordinal=source["ordinal"],
                name_th=source["name_th"],
                source_url=source["url"],
                acquisition_mode=source["acquisition_mode"],
                readiness_status=source["readiness_status"],
                cloud_policy=source["cloud_policy"],
                production_values_allowed=True,
                expected_record_count=source["expected_record_count"],
                notes_th="",
            )
        )
        session.commit()
        pipeline = IngestionPipeline(session, settings)
        monkeypatch.setattr(
            pipeline,
            "_fetch_api",
            lambda *_args, **_kwargs: (
                [("innovations", {"id": "will-rollback"})],
                failed_manifest,
            ),
        )

        def add_then_fail(_source, _records, **_kwargs):
            session.add(
                DashboardRecord(
                    source_id=source["source_id"],
                    dataset_key="innovations",
                    source_record_id="will-rollback",
                    record_hash="a" * 64,
                    quality_status="needs_review",
                    payload={"id": "will-rollback"},
                )
            )
            session.flush()
            raise RuntimeError("database-stage failure")

        monkeypatch.setattr(pipeline, "_store_records", add_then_fail)
        with pytest.raises(RuntimeError, match="database-stage failure"):
            pipeline.ingest_source(source["source_id"], strategy="api")

        assert session.scalars(select(DashboardRecord)).all() == []
        run = session.scalar(select(IngestionRun))
        assert run is not None
        assert run.status == "failed"
        assert "database-stage failure" in run.error_message


def test_api_record_limit_fails_instead_of_committing_a_possible_partial_batch(
    tmp_path,
    monkeypatch,
):
    class LimitConnector:
        driver_name = "limit-test"

        def fetch(self, _context):
            return [("innovations", {"id": "record-at-limit"})]

    monkeypatch.setattr("app.settings.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("app.ingestion.load_connector", lambda _entrypoint: LimitConnector())
    settings = Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=1)
    source = source_config("f2_apptech_mtr")
    with SessionLocal() as session:
        pipeline = IngestionPipeline(session, settings)
        pipeline.plans[source["source_id"]] = {
            "driver": "limit-test",
            "connector": "app.connectors.apptech_mtr:ApptechMtrConnector",
        }
        with pytest.raises(IngestionFetchError, match="partial candidate commits are forbidden"):
            pipeline._fetch_api(source, "limit-run")

    manifest = json.loads(
        (tmp_path / "data/runtime/raw/f2_apptech_mtr/limit-run/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "failed"
    assert manifest["records_seen"] == 1


def test_explicit_api_strategy_never_hides_failure_with_snapshot_fallback(tmp_path, monkeypatch):
    failed_manifest = tmp_path / "manifest.json"
    failed_manifest.write_text("{}\n", encoding="utf-8")
    settings = Settings(database_url="sqlite:///unused.sqlite")

    with SessionLocal() as session:
        sync_catalog(session)
        pipeline = IngestionPipeline(session, settings)

        def fail_api(*_args, **_kwargs):
            raise IngestionFetchError("upstream failed", failed_manifest)

        monkeypatch.setattr(pipeline, "_fetch_api", fail_api)
        monkeypatch.setattr(
            pipeline,
            "_load_snapshot",
            lambda *_args, **_kwargs: pytest.fail("explicit api must not use snapshot fallback"),
        )

        with pytest.raises(IngestionFetchError):
            pipeline.ingest_source("f2_apptech_mtr", strategy="api")

        run = session.scalar(select(IngestionRun))
        assert run is not None
        assert run.status == "failed"
        assert run.strategy == "api"
        assert run.manifest_path
