from __future__ import annotations

import gzip
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


RUN_IDS = {
    "sukhothaicare": "20260815T070131Z",
    "sukhothai-water": "20260815T063848Z",
    "NSN": "20260815T054925Z",
    "rawangphai": "20260815T060958Z",
}


def write_run(
    root: Path,
    folder: str,
    run_id: str,
    datasets: dict[str, list[dict]],
    row_count_override: dict[str, int] | None = None,
) -> Path:
    """สร้าง run ตาม layout ของ evidence workspace (หลัง tools/evidence_pull.py)"""
    source_id = FLOOD_SNAPSHOT_SOURCES[folder]
    run_dir = root / "data" / "raw" / source_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_datasets = []
    for name, rows in datasets.items():
        file_name = f"{name}.jsonl.gz"
        payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        with gzip.open(run_dir / file_name, "wt", encoding="utf-8") as handle:
            handle.write(payload)
        row_count = len(rows)
        if row_count_override and name in row_count_override:
            row_count = row_count_override[name]
        manifest_datasets.append(
            {
                "dataset_key": f"{folder}.{name}",
                "file": file_name,
                "row_count": row_count,
                "as_of": "2026-08-15T07:00:00+00:00",
                "grain": f"หนึ่งแถว = หนึ่งรายการของ {name}",
                "identity_fields": ["id"],
            }
        )
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "source_id": source_id,
                "run_id": run_id,
                "fetched_at": "2026-08-15T07:00:00+00:00",
                "fetched_by": "tester",
                "datasets": manifest_datasets,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return run_dir


def create_small_snapshots(root: Path, row_count_override: dict[str, int] | None = None) -> None:
    write_run(
        root,
        "sukhothaicare",
        RUN_IDS["sukhothaicare"],
        {
            "incidents": [
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
            "incident_stats": [
                {"metric_group": "total", "metric_name": "all", "value": 2}
            ],
        },
    )
    write_run(
        root,
        "sukhothai-water",
        RUN_IDS["sukhothai-water"],
        {
            "water_levels": [
                {"station_id": 2986, "waterlevel_datetime": "2026-08-15 12:00"}
            ],
            "rain_24h": [{"station_id": 1, "rainfall_datetime": "2026-08-15 12:00"}],
        },
    )
    write_run(
        root,
        "NSN",
        RUN_IDS["NSN"],
        {
            "water_stations": [{"station_code": "P.17", "updated_at": "15/08 11:00"}],
            "forecast_daily": [{"date": "2026-08-15", "rain_sum_mm": 10}],
        },
    )
    write_run(
        root,
        "rawangphai",
        RUN_IDS["rawangphai"],
        {
            "water_levels": [
                {"station_id": 642750, "measured_at": "2026-08-15 12:50"}
            ],
            "shelters": [{"id": "s1", "name": "ศูนย์พักพิง"}],
        },
        row_count_override=row_count_override,
    )


def test_latest_run_dir_selects_newest_manifest_folder(tmp_path):
    older = write_run(tmp_path, "NSN", "20250101T000000Z", {"pages": []})
    newer = write_run(tmp_path, "NSN", "20260815T054925Z", {"pages": []})

    source_root = tmp_path / "data" / "raw" / FLOOD_SNAPSHOT_SOURCES["NSN"]
    assert latest_run_dir(source_root) == newer
    assert older.exists()


def test_latest_run_dir_error_points_to_evidence_pull(tmp_path):
    with pytest.raises(FileNotFoundError, match="evidence_pull"):
        latest_run_dir(tmp_path / "data" / "raw" / "spu_nsn_flood")


def test_flood_snapshot_datasets_map_folders_to_source_ids(tmp_path):
    create_small_snapshots(tmp_path)

    datasets = flood_snapshot_datasets(tmp_path)
    by_folder = {dataset.folder: dataset.source_id for dataset in datasets}

    assert by_folder == dict(FLOOD_SNAPSHOT_SOURCES)
    assert {dataset.run_id for dataset in datasets} == set(RUN_IDS.values())
    # expected_count มาจาก manifest ของ run ไม่ใช่ hardcode ในซอร์ส
    incidents = next(d for d in datasets if d.dataset_key == "sukhothaicare.incidents")
    assert incidents.expected_count == 2
    assert incidents.path.name == "incidents.jsonl.gz"


def test_import_flood_snapshots_sanitizes_and_is_idempotent(tmp_path):
    create_small_snapshots(tmp_path)

    with SessionLocal() as session:
        sync_catalog(session)
        first = import_flood_snapshots(session, root=tmp_path)
        second = import_flood_snapshots(session, root=tmp_path)

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


def test_import_flood_snapshots_rejects_count_mismatch(tmp_path):
    # manifest บอก 3 แถว แต่ไฟล์จริงมี 1 แถว → ต้อง fail ก่อนเขียน database
    create_small_snapshots(tmp_path, row_count_override={"shelters": 3})

    with SessionLocal() as session:
        sync_catalog(session)
        with pytest.raises(RuntimeError, match="rawangphai.shelters row count mismatch"):
            import_flood_snapshots(session, root=tmp_path)


def test_plain_jsonl_dataset_is_still_supported(tmp_path):
    run_dir = write_run(tmp_path, "NSN", "20260815T054925Z", {})
    (run_dir / "pages.jsonl").write_text(
        json.dumps({"url": "https://example.invalid"}) + "\n", encoding="utf-8"
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260815T054925Z",
                "datasets": [
                    {
                        "dataset_key": "NSN.pages",
                        "file": "pages.jsonl",
                        "row_count": 1,
                        "as_of": "2026-08-15T07:00:00+00:00",
                        "grain": "หนึ่งแถว = หนึ่งหน้าเว็บ",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    datasets = flood_snapshot_datasets(tmp_path, folders=["NSN"])
    assert [d.dataset_key for d in datasets] == ["NSN.pages"]
    assert datasets[0].expected_count == 1


def test_missing_evidence_root_gives_actionable_error(monkeypatch):
    monkeypatch.delenv("AIAT_EVIDENCE_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="AIAT_EVIDENCE_ROOT"):
        flood_snapshot_datasets()


def test_default_flood_source_mapping_stays_on_selected_four_folders():
    assert FLOOD_SNAPSHOT_SOURCES == {
        "sukhothaicare": "spu_sukhothai_care",
        "sukhothai-water": "spu_sukhothai_water",
        "NSN": "spu_nsn_flood",
        "rawangphai": "spu_rawangphai_uru",
    }
