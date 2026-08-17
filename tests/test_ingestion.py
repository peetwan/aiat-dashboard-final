from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.catalog import source_config, sync_catalog
from app.database import SessionLocal
from app.ingestion import (
    IngestionFetchError,
    IngestionPipeline,
    PolicyViolation,
    ResponseRecorder,
)
from app.models import DashboardRecord, IngestionRun
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
    plan = {"url": "https://example.test/apptech", "page_size": 2}
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
            pipeline.ingest_source("f2_wallet_all_realtime")
        pipeline._guard_source(source_config("f3_city_capital_open_data"))


def test_production_allows_approved_source_but_blocks_wallet():
    settings = Settings(
        app_env="production",
        database_url="sqlite:///unused.sqlite",
        allow_pending_owner_sources=False,
    )
    with SessionLocal() as session:
        sync_catalog(session)
        pipeline = IngestionPipeline(session, settings)
        pipeline._guard_source(source_config("f2_apptech_mtr"))
        with pytest.raises(PolicyViolation):
            pipeline.ingest_source("f2_wallet_cluster_realtime")


def test_learning_dashboard_driver_keeps_all_source_grains_separate():
    payload = {
        "provinces": [["Province", "ธุรกิจชุมชน"], ["สงขลา", 10]],
        "entityTypes": [["Entity Type", "Popularity"], ["กลุ่ม", 2]],
        "categories": [["Category", "Popularity"], ["อาหาร", 3]],
        "geography": [["Geography", "Popularity"], ["ภาคใต้", 4]],
        "geographyImpact": [{"geography": "ภาคใต้", "employee": 5}],
        "impactSummary": {"totalEmployeeAmount": 5},
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
                "form": {
                    "action": "fetch_innovationAll_JSON",
                    "innovationgroup": "All",
                    "orderby": 1,
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
                "form": {"action": "fetch_innovationAll_JSON"},
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
