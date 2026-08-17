from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import source_config
from app.models import DashboardRecord
from app.privacy import payload_hash, sanitize_payload


DEFAULT_PIPELINE_ROOT = Path("/Users/mister1st/Documents/AIAT/pipeline")

FLOOD_SNAPSHOT_SOURCES = {
    "sukhothaicare": {
        "source_id": "spu_sukhothai_care",
        "expected_counts": {
            "announcements": 131,
            "api_endpoints": 40,
            "app_routes": 14,
            "incident_map": 189,
            "incident_stats": 9,
            "incidents": 211,
            "page_assets": 31,
            "pages": 1,
            "roads": 0,
            "shelters": 0,
            "site_links": 0,
        },
    },
    "sukhothai-water": {
        "source_id": "spu_sukhothai_water",
        "expected_counts": {
            "api_endpoints": 3,
            "dams": 20,
            "page_assets": 37,
            "pages": 1,
            "rain_24h": 70,
            "site_links": 9,
            "water_levels": 28,
        },
    },
    "NSN": {
        "source_id": "spu_nsn_flood",
        "expected_counts": {
            "data_source_tables": 25,
            "forecast_chart": 7,
            "forecast_daily": 7,
            "pages": 18,
            "site_links": 737,
            "station_details": 10,
            "station_tables": 18,
            "water_stations": 10,
        },
    },
    "rawangphai": {
        "source_id": "spu_rawangphai_uru",
        "expected_counts": {
            "api_endpoints": 18,
            "geojson_assets": 4,
            "pages": 1,
            "rain_analysis": 750,
            "shelters": 507,
            "site_links": 0,
            "water_levels": 32,
        },
    },
}

IDENTITY_FIELDS = (
    "source_record_id",
    "record_id",
    "id",
    "station_id",
    "station_code",
    "station_url",
    "dam_id",
    "dam_code",
    "layer_id",
    "path",
    "route",
    "url",
    "source_url",
    "table_index",
    "metric_group",
    "metric_name",
)
TIME_FIELDS = (
    "waterlevel_datetime",
    "rainfall_datetime",
    "dam_date",
    "measured_at",
    "updated_at",
    "created_at",
    "date",
    "date_time",
    "timestamp",
    "fetched_at",
)
EXTRA_FORBIDDEN_KEYS = {
    "reporterName",
    "reporter_name",
    "phone",
    "mobile",
    "email",
    "token",
    "cookie",
    "authorization",
}


@dataclass(frozen=True)
class SnapshotDataset:
    folder: str
    source_id: str
    run_id: str
    dataset_name: str
    dataset_key: str
    path: Path
    expected_count: int


def latest_run_dir(folder_root: Path) -> Path:
    output_root = folder_root / "output"
    candidates = sorted(
        path
        for path in output_root.iterdir()
        if path.is_dir() and (path / "manifest.json").is_file()
    )
    if not candidates:
        raise FileNotFoundError(f"no snapshot runs found under {output_root}")
    return candidates[-1]


def flood_snapshot_datasets(
    pipeline_root: Path = DEFAULT_PIPELINE_ROOT,
    folders: Iterable[str] | None = None,
) -> list[SnapshotDataset]:
    selected = list(folders or FLOOD_SNAPSHOT_SOURCES)
    datasets: list[SnapshotDataset] = []
    for folder in selected:
        if folder not in FLOOD_SNAPSHOT_SOURCES:
            raise KeyError(f"unsupported flood snapshot folder: {folder}")
        config = FLOOD_SNAPSHOT_SOURCES[folder]
        run_dir = latest_run_dir(pipeline_root / folder)
        run_id = run_dir.name
        for dataset_name, expected_count in sorted(config["expected_counts"].items()):
            path = run_dir / f"{dataset_name}.jsonl"
            if not path.is_file():
                raise FileNotFoundError(f"missing expected JSONL file: {path}")
            datasets.append(
                SnapshotDataset(
                    folder=folder,
                    source_id=str(config["source_id"]),
                    run_id=run_id,
                    dataset_name=dataset_name,
                    dataset_key=f"{folder}.{dataset_name}",
                    path=path,
                    expected_count=int(expected_count),
                )
            )
    return datasets


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            yield payload


def _remove_extra_forbidden(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _remove_extra_forbidden(item)
            for key, item in value.items()
            if str(key) not in EXTRA_FORBIDDEN_KEYS
        }
    if isinstance(value, list):
        return [_remove_extra_forbidden(item) for item in value]
    return value


def clean_snapshot_payload(row: dict[str, Any], dataset: SnapshotDataset) -> dict[str, Any]:
    payload = sanitize_payload(_remove_extra_forbidden(row))
    if not isinstance(payload, dict):
        raise ValueError(f"sanitized payload is not an object: {dataset.path}")
    payload.setdefault("_candidate_source_folder", dataset.folder)
    payload.setdefault("_candidate_run_id", dataset.run_id)
    payload.setdefault("_candidate_dataset", dataset.dataset_name)
    return payload


def source_record_id(dataset: SnapshotDataset, payload: dict[str, Any], digest: str) -> str:
    parts: list[str] = [dataset.dataset_name]
    for key in IDENTITY_FIELDS:
        value = payload.get(key)
        if value not in (None, "", []):
            parts.append(str(value))
    for key in TIME_FIELDS:
        value = payload.get(key)
        if value not in (None, "", []):
            parts.append(str(value))
            break
    if len(parts) == 1:
        parts.append(digest)
    return ":".join(parts)[:200]


def validate_dataset_counts(datasets: Iterable[SnapshotDataset]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for dataset in datasets:
        count = sum(1 for _ in iter_jsonl(dataset.path))
        counts[dataset.dataset_key] = count
        if count != dataset.expected_count:
            raise RuntimeError(
                f"{dataset.dataset_key} row count mismatch: actual={count}, "
                f"expected={dataset.expected_count}"
            )
    return counts


def import_flood_snapshots(
    session: Session,
    pipeline_root: Path = DEFAULT_PIPELINE_ROOT,
    folders: Iterable[str] | None = None,
) -> dict[str, Any]:
    datasets = flood_snapshot_datasets(pipeline_root, folders)
    validate_dataset_counts(datasets)

    existing = {
        (source_id, dataset_key, source_record_id, record_hash)
        for source_id, dataset_key, source_record_id, record_hash in session.execute(
            select(
                DashboardRecord.source_id,
                DashboardRecord.dataset_key,
                DashboardRecord.source_record_id,
                DashboardRecord.record_hash,
            )
        )
    }

    inserted = 0
    skipped = 0
    dataset_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    for dataset in datasets:
        source = source_config(dataset.source_id)
        for row in iter_jsonl(dataset.path):
            payload = clean_snapshot_payload(row, dataset)
            digest = payload_hash(payload)
            record_id = source_record_id(dataset, payload, digest)
            key = (dataset.source_id, dataset.dataset_key[:200], record_id, digest)
            if key in existing:
                skipped += 1
                continue
            session.add(
                DashboardRecord(
                    source_id=dataset.source_id,
                    dataset_key=dataset.dataset_key[:200],
                    source_record_id=record_id,
                    record_hash=digest,
                    quality_status=source["readiness_status"],
                    payload=payload,
                )
            )
            existing.add(key)
            inserted += 1
            dataset_counts[dataset.dataset_key] += 1
            source_counts[dataset.source_id] += 1
            if inserted % 1000 == 0:
                session.flush()

    session.commit()
    return {
        "status": "complete",
        "datasets": len(datasets),
        "inserted": inserted,
        "skipped": skipped,
        "inserted_by_source": dict(sorted(source_counts.items())),
        "inserted_by_dataset": dict(sorted(dataset_counts.items())),
    }
