from __future__ import annotations

import gzip
import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, TextIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import source_config
from app.models import DashboardRecord
from app.privacy import payload_hash, sanitize_payload


def evidence_root() -> Path:
    """Evidence workspace root — ต้องตั้ง AIAT_EVIDENCE_ROOT (หรือส่ง --evidence-root) เสมอ

    ห้าม default ไปยังโฟลเดอร์แม่ของ repo: public runtime ต้อง standalone
    (บังคับโดย tools/validate_public_repo.py) การอ่าน workspace เกิดเฉพาะ
    ตอนที่ operator สั่ง import เองเท่านั้น
    """
    root_text = os.environ.get("AIAT_EVIDENCE_ROOT")
    if not root_text:
        raise RuntimeError(
            "ยังไม่ได้ตั้ง AIAT_EVIDENCE_ROOT — ชี้ไปที่ evidence workspace "
            "(โฟลเดอร์ที่มี data/raw จาก tools/evidence_pull.py) "
            "หรือส่ง --evidence-root ให้คำสั่ง import-flood-snapshots"
        )
    return Path(root_text).expanduser().resolve()


# โฟลเดอร์ snapshot เดิม → source_id; ชื่อโฟลเดอร์ยังเป็น prefix ของ dataset_key
# เพื่อให้ dashboard_records เดิม (เช่น "sukhothaicare.incidents") คงที่
FLOOD_SNAPSHOT_SOURCES = {
    "sukhothaicare": "spu_sukhothai_care",
    "sukhothai-water": "spu_sukhothai_water",
    "NSN": "spu_nsn_flood",
    "rawangphai": "spu_rawangphai_uru",
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


def latest_run_dir(source_root: Path) -> Path:
    candidates = sorted(
        path
        for path in (source_root.iterdir() if source_root.is_dir() else [])
        if path.is_dir() and (path / "manifest.json").is_file()
    )
    if not candidates:
        raise FileNotFoundError(
            f"no evidence runs found under {source_root} — "
            "รัน python tools/evidence_pull.py <source_id> ก่อน (ดู docs/evidence-storage.md)"
        )
    return candidates[-1]


def flood_snapshot_datasets(
    root: Path | None = None,
    folders: Iterable[str] | None = None,
) -> list[SnapshotDataset]:
    workspace = root if root is not None else evidence_root()
    selected = list(folders or FLOOD_SNAPSHOT_SOURCES)
    datasets: list[SnapshotDataset] = []
    for folder in selected:
        if folder not in FLOOD_SNAPSHOT_SOURCES:
            raise KeyError(f"unsupported flood snapshot folder: {folder}")
        source_id = FLOOD_SNAPSHOT_SOURCES[folder]
        run_dir = latest_run_dir(workspace / "data" / "raw" / source_id)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        run_id = str(manifest.get("run_id", run_dir.name))
        manifest_datasets = manifest.get("datasets", [])
        if not manifest_datasets:
            raise ValueError(f"manifest ของ {run_dir} ไม่มี datasets")
        prefix = f"{folder}."
        for entry in sorted(manifest_datasets, key=lambda item: str(item["dataset_key"])):
            dataset_key = str(entry["dataset_key"])
            if not dataset_key.startswith(prefix):
                raise ValueError(
                    f"dataset_key {dataset_key!r} ใน {run_dir} ไม่ขึ้นต้นด้วย {prefix!r}"
                )
            path = run_dir / str(entry["file"])
            if not path.is_file():
                raise FileNotFoundError(f"missing dataset file from manifest: {path}")
            datasets.append(
                SnapshotDataset(
                    folder=folder,
                    source_id=source_id,
                    run_id=run_id,
                    dataset_name=dataset_key[len(prefix):],
                    dataset_key=dataset_key,
                    path=path,
                    # จำนวนแถวมาจาก manifest ของ run ไม่ hardcode ในซอร์สโค้ด
                    expected_count=int(entry["row_count"]),
                )
            )
    return datasets


def _open_text(path: Path) -> TextIO:
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8-sig")


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with _open_text(path) as handle:
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
                f"manifest={dataset.expected_count}"
            )
    return counts


def import_flood_snapshots(
    session: Session,
    root: Path | None = None,
    folders: Iterable[str] | None = None,
) -> dict[str, Any]:
    datasets = flood_snapshot_datasets(root, folders)
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
