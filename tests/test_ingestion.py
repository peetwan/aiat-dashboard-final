from __future__ import annotations

import csv

import pytest
from sqlalchemy import select

from app.catalog import source_config, sync_catalog
from app.database import SessionLocal
from app.ingestion import IngestionPipeline, PolicyViolation
from app.models import DashboardRecord
from app.settings import Settings


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
