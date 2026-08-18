from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.catalog import sync_catalog
from app.database import SessionLocal
from app.flood_snapshot_importer import (
    FLOOD_SNAPSHOT_SOURCES,
    flood_snapshot_datasets,
    import_flood_snapshots,
    latest_run_dir,
)
from app.models import DashboardRecord


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_manifest(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text("{}\n", encoding="utf-8")


@pytest.fixture
def small_flood_config(monkeypatch):
    config = {
        "sukhothaicare": {
            "source_id": "spu_sukhothai_care",
            "expected_counts": {"incidents": 2, "incident_stats": 1},
        },
        "sukhothai-water": {
            "source_id": "spu_sukhothai_water",
            "expected_counts": {"water_levels": 1, "rain_24h": 1},
        },
        "NSN": {
            "source_id": "spu_nsn_flood",
            "expected_counts": {"water_stations": 1, "forecast_daily": 1},
        },
        "rawangphai": {
            "source_id": "spu_rawangphai_uru",
            "expected_counts": {"water_levels": 1, "shelters": 1},
        },
    }
    monkeypatch.setattr(
        "app.flood_snapshot_importer.FLOOD_SNAPSHOT_SOURCES",
        config,
    )
    return config


def create_small_snapshots(root: Path) -> None:
    run_ids = {
        "sukhothaicare": "20260815T070131Z",
        "sukhothai-water": "20260815T063848Z",
        "NSN": "20260815T054925Z",
        "rawangphai": "20260815T060958Z",
    }
    for folder, run_id in run_ids.items():
        write_manifest(root / folder / "output" / "20250101T000000Z")
        write_manifest(root / folder / "output" / run_id)

    write_jsonl(
        root / "sukhothaicare/output/20260815T070131Z/incidents.jsonl",
        [
            {
                "id": "i1",
                "type": "LEVEE_BREACH",
                "reporterName": "บุคคลตัวอย่าง",
                "phone": "0812345678",
                "address": "บ้านเลขที่ 1",
                "description": "ติดต่อ test@example.com",
            },
            {"id": "i2", "type": "ROAD_BLOCKED"},
        ],
    )
    write_jsonl(
        root / "sukhothaicare/output/20260815T070131Z/incident_stats.jsonl",
        [{"metric_group": "total", "metric_name": "all", "value": 2}],
    )
    write_jsonl(
        root / "sukhothai-water/output/20260815T063848Z/water_levels.jsonl",
        [{"station_id": 2986, "waterlevel_datetime": "2026-08-15 12:00"}],
    )
    write_jsonl(
        root / "sukhothai-water/output/20260815T063848Z/rain_24h.jsonl",
        [{"station_id": 1, "rainfall_datetime": "2026-08-15 12:00"}],
    )
    write_jsonl(
        root / "NSN/output/20260815T054925Z/water_stations.jsonl",
        [{"station_code": "P.17", "updated_at": "15/08 11:00"}],
    )
    write_jsonl(
        root / "NSN/output/20260815T054925Z/forecast_daily.jsonl",
        [{"date": "2026-08-15", "rain_sum_mm": 10}],
    )
    write_jsonl(
        root / "rawangphai/output/20260815T060958Z/water_levels.jsonl",
        [{"station_id": 642750, "measured_at": "2026-08-15 12:50"}],
    )
    write_jsonl(
        root / "rawangphai/output/20260815T060958Z/shelters.jsonl",
        [{"id": "s1", "name": "ศูนย์พักพิง"}],
    )


def test_latest_run_dir_selects_newest_manifest_folder(tmp_path):
    older = tmp_path / "source/output/20250101T000000Z"
    newer = tmp_path / "source/output/20260815T000000Z"
    write_manifest(older)
    write_manifest(newer)

    assert latest_run_dir(tmp_path / "source") == newer


def test_flood_snapshot_datasets_map_folders_to_source_ids(tmp_path, small_flood_config):
    create_small_snapshots(tmp_path)

    datasets = flood_snapshot_datasets(tmp_path)
    by_folder = {dataset.folder: dataset.source_id for dataset in datasets}

    assert by_folder == {
        folder: config["source_id"]
        for folder, config in small_flood_config.items()
    }
    assert {dataset.run_id for dataset in datasets} == {
        "20260815T070131Z",
        "20260815T063848Z",
        "20260815T054925Z",
        "20260815T060958Z",
    }


def test_import_flood_snapshots_sanitizes_and_is_idempotent(tmp_path, small_flood_config):
    create_small_snapshots(tmp_path)

    with SessionLocal() as session:
        sync_catalog(session)
        first = import_flood_snapshots(session, pipeline_root=tmp_path)
        second = import_flood_snapshots(session, pipeline_root=tmp_path)

        assert first["inserted"] == 9
        assert first["skipped"] == 0
        assert second["inserted"] == 0
        assert second["skipped"] == 9
        assert session.scalar(select(func.count()).select_from(DashboardRecord)) == 9

        incident = session.scalar(
            select(DashboardRecord).where(
                DashboardRecord.dataset_key == "sukhothaicare.incidents",
                DashboardRecord.source_record_id.like("incidents:i1%"),
            )
        )
        assert incident is not None
        assert "reporterName" not in incident.payload
        assert "phone" not in incident.payload
        assert "address" not in incident.payload
        assert "test@example.com" not in json.dumps(incident.payload, ensure_ascii=False)
        assert incident.payload["_candidate_run_id"] == "20260815T070131Z"


def test_import_flood_snapshots_rejects_count_mismatch(tmp_path, small_flood_config):
    create_small_snapshots(tmp_path)
    write_jsonl(
        tmp_path / "rawangphai/output/20260815T060958Z/shelters.jsonl",
        [],
    )

    with SessionLocal() as session:
        sync_catalog(session)
        with pytest.raises(RuntimeError, match="rawangphai.shelters row count mismatch"):
            import_flood_snapshots(session, pipeline_root=tmp_path)


def test_default_flood_source_mapping_stays_on_selected_four_folders():
    assert FLOOD_SNAPSHOT_SOURCES.keys() == {
        "sukhothaicare",
        "sukhothai-water",
        "NSN",
        "rawangphai",
    }
