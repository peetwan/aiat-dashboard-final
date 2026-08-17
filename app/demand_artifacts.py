from __future__ import annotations

import gzip
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.models import HousingDemandRecord, HousingDemandSnapshot, utc_now
from app.settings import PROJECT_ROOT


DEMAND_ROOT = PROJECT_ROOT / "data" / "demand"
DEMAND_MANIFEST_PATH = DEMAND_ROOT / "manifest.json"
SOURCE_ID = "f3_housing_portal"
SNAPSHOT_ID = "housing_demand_current"
REQUIRED_DEMAND_COUNT = 25_919
INSERT_BATCH_SIZE = 1_000
FORBIDDEN_FIELD_RE = re.compile(
    r"(?i)(?:^|_)(?:first_name|last_name|full_name|person_name|name|"
    r"phone|telephone|tel|mobile|email|e_mail|contact)(?:_|$)"
)
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(
    r"(?<![\dA-Za-z])(?:\+?66|0)\s*\d(?:[\s().-]*\d){7,9}(?!\d)"
)


def load_demand_manifest(path: Path = DEMAND_MANIFEST_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("validation_status") != "pass":
        raise RuntimeError("housing demand serving manifest did not pass validation")
    if payload.get("source_id") != SOURCE_ID:
        raise RuntimeError("housing demand serving manifest source_id mismatch")
    if int(payload.get("record_count", -1)) != REQUIRED_DEMAND_COUNT:
        raise RuntimeError("housing demand serving manifest record count mismatch")
    privacy = payload.get("privacy_projection") or {}
    if privacy.get("excluded_source_fields") != ["id"]:
        raise RuntimeError("housing demand source identifier exclusion is missing")
    if privacy.get("source_identifier_published") is not False:
        raise RuntimeError("housing demand source identifier must not be published")
    for field in (
        "name_fields_in_source_schema",
        "phone_fields_in_source_schema",
        "email_fields_in_source_schema",
    ):
        if int(privacy.get(field, -1)) != 0:
            raise RuntimeError(f"housing demand privacy gate failed: {field}")
    return payload


def iter_demand_rows(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"housing demand row {line_number} is not an object")
            yield payload


def parse_datetime(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _assert_public_fields(fields: dict[str, Any], row_number: int) -> None:
    if "id" in fields:
        raise ValueError(f"source identifier leaked into housing demand row {row_number}")
    forbidden = sorted(key for key in fields if FORBIDDEN_FIELD_RE.search(key))
    if forbidden:
        raise ValueError(
            f"identity/contact fields leaked into housing demand row {row_number}: {forbidden}"
        )
    for key, value in fields.items():
        if not isinstance(value, str):
            continue
        if EMAIL_RE.search(value) or PHONE_RE.search(value):
            raise ValueError(
                f"contact value leaked into housing demand row {row_number}:{key}"
            )


def _mapping(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("source_id") != SOURCE_ID or row.get("dataset_key") != "housing_demand":
        raise ValueError("housing demand source/dataset mismatch")
    row_number = int(row["source_row_number"])
    fields = row.get("fields") or {}
    if not isinstance(fields, dict):
        raise ValueError(f"housing demand fields must be an object: {row_number}")
    _assert_public_fields(fields, row_number)
    return {
        "source_row_number": row_number,
        "source_id": SOURCE_ID,
        "living_province_code": row.get("living_province_code"),
        "preferred_province_code": row.get("preferred_province_code"),
        "record_hash": str(row["record_hash"]),
        "payload": fields,
        "evidence_path": str(row["evidence_path"]),
        "evidence_sha256": str(row["evidence_sha256"]),
        "fetched_at": parse_datetime(row.get("fetched_at")),
        "as_of": str(row.get("as_of") or "ไม่ระบุ"),
        "quality_status": str(row.get("quality_status") or "needs_review"),
    }


def database_demand_count(session: Session) -> int:
    return int(
        session.scalar(select(func.count()).select_from(HousingDemandRecord)) or 0
    )


def database_demand_snapshot_hash(session: Session) -> str | None:
    value = session.scalar(
        select(HousingDemandSnapshot.content_hash).where(
            HousingDemandSnapshot.snapshot_id == SNAPSHOT_ID
        )
    )
    return str(value) if value else None


def sync_housing_demand(
    session: Session,
    manifest_path: Path = DEMAND_MANIFEST_PATH,
) -> dict[str, Any]:
    """Transactionally synchronize the validated respondent privacy projection."""

    manifest = load_demand_manifest(manifest_path)
    artifact = manifest["artifacts"]["records"]
    content_hash = str(artifact["sha256"])
    before_count = database_demand_count(session)
    if (
        before_count == REQUIRED_DEMAND_COUNT
        and database_demand_snapshot_hash(session) == content_hash
    ):
        return {
            "expected": REQUIRED_DEMAND_COUNT,
            "loaded": 0,
            "count": before_count,
            "changed": False,
        }

    path = manifest_path.parent / Path(str(artifact["path"])).name
    seen_rows: set[int] = set()
    seen_hashes: set[str] = set()
    loaded = 0
    try:
        session.execute(delete(HousingDemandRecord))
        session.execute(delete(HousingDemandSnapshot))
        batch: list[dict[str, Any]] = []
        for row in iter_demand_rows(path):
            mapping = _mapping(row)
            row_number = mapping["source_row_number"]
            record_hash = mapping["record_hash"]
            if row_number in seen_rows:
                raise ValueError(f"duplicate housing demand row number: {row_number}")
            if record_hash in seen_hashes:
                raise ValueError(f"duplicate housing demand record hash: {record_hash}")
            seen_rows.add(row_number)
            seen_hashes.add(record_hash)
            batch.append(mapping)
            loaded += 1
            if len(batch) >= INSERT_BATCH_SIZE:
                session.execute(insert(HousingDemandRecord), batch)
                batch.clear()
        if batch:
            session.execute(insert(HousingDemandRecord), batch)
        if loaded != REQUIRED_DEMAND_COUNT or len(seen_rows) != REQUIRED_DEMAND_COUNT:
            raise ValueError(
                "housing demand count gate failed: "
                f"rows={loaded}, unique={len(seen_rows)}, expected={REQUIRED_DEMAND_COUNT}"
            )
        session.add(
            HousingDemandSnapshot(
                snapshot_id=SNAPSHOT_ID,
                source_id=SOURCE_ID,
                content_hash=content_hash,
                record_count=REQUIRED_DEMAND_COUNT,
                source_path=str(artifact["path"]),
                quality_status="needs_review",
                updated_at=utc_now(),
            )
        )
        session.flush()
        final_count = database_demand_count(session)
        if final_count != REQUIRED_DEMAND_COUNT:
            raise ValueError(
                f"database housing demand count failed: {final_count}"
            )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return {
        "expected": REQUIRED_DEMAND_COUNT,
        "loaded": loaded,
        "count": REQUIRED_DEMAND_COUNT,
        "changed": True,
    }


def demand_contract_snapshot(session: Session, *, required: bool) -> dict[str, Any]:
    count = database_demand_count(session)
    exact = count == REQUIRED_DEMAND_COUNT
    return {
        "required": required,
        "complete": exact if required else True,
        "count": count,
        "expected": REQUIRED_DEMAND_COUNT if required else 0,
        "snapshot_hash": database_demand_snapshot_hash(session),
    }
