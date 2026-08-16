from __future__ import annotations

import csv

import pytest
from sqlalchemy import select

from app.catalog import source_config, sync_catalog
from app.database import SessionLocal
from app.ingestion import IngestionPipeline, PolicyViolation
from app.models import DashboardRecord
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
