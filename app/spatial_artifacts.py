from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.models import SpatialFeature, SpatialLayerSnapshot, utc_now
from app.privacy import sanitize_payload
from app.settings import PROJECT_ROOT


SPATIAL_ROOT = PROJECT_ROOT / "data" / "spatial"
SPATIAL_MANIFEST_PATH = SPATIAL_ROOT / "manifest.json"
SOURCE_ID = "f3_housing_portal"
REQUIRED_SPATIAL_COUNTS = {
    "subdistrict_boundaries": 169,
    "housing_points": 28_694,
    "accessibility_grid": 6_543,
    "flood_grid": 159_126,
}
REQUIRED_SPATIAL_TOTAL = sum(REQUIRED_SPATIAL_COUNTS.values())
INSERT_BATCH_SIZE = 2_000
# housing_points เป็นทะเบียนสถานที่จาก public place feed มี place_id/type;
# Public place listings embed booking contacts in their name/address text.
# Contexts apply only to these two place fields, never demand respondent data.
HOUSING_POINT_CONTEXTS = {"/name": "public_contact", "/address": "public_contact"}


def load_spatial_manifest(path: Path = SPATIAL_MANIFEST_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("validation_status") != "pass":
        raise RuntimeError("housing spatial serving manifest did not pass validation")
    if payload.get("source_id") != SOURCE_ID:
        raise RuntimeError("housing spatial serving manifest source_id mismatch")
    actual = {
        layer_id: int((payload.get("layers", {}).get(layer_id) or {}).get("feature_count", -1))
        for layer_id in REQUIRED_SPATIAL_COUNTS
    }
    if actual != REQUIRED_SPATIAL_COUNTS:
        raise RuntimeError(
            f"housing spatial counts do not match contract: actual={actual}, "
            f"expected={REQUIRED_SPATIAL_COUNTS}"
        )
    privacy = payload.get("privacy_projection") or {}
    if privacy.get("demand_respondent_rows_included") != 0:
        raise RuntimeError("respondent-level demand rows must not enter Railway")
    details = payload["layers"]["housing_points"].get("detail_projection")
    expected_contacts = len(HOUSING_POINT_CONTEXTS) if details else 0
    if privacy.get("contact_fields_included") != expected_contacts:
        raise RuntimeError("public place contact fields do not match the reviewed projection")
    if details and details.get("field_contexts") != HOUSING_POINT_CONTEXTS:
        raise RuntimeError("public place field contexts do not match the reviewed projection")
    root = path.parent.resolve()
    for layer_id in REQUIRED_SPATIAL_COUNTS:
        layer = payload["layers"][layer_id]
        artifact_path = (root / Path(str(layer.get("artifact_path"))).name).resolve()
        if root not in artifact_path.parents or not artifact_path.is_file():
            raise RuntimeError(f"housing spatial artifact is missing: {layer_id}")
        raw = artifact_path.read_bytes()
        if len(raw) != int(layer.get("artifact_bytes", -1)):
            raise RuntimeError(f"housing spatial artifact byte count mismatch: {layer_id}")
        if hashlib.sha256(raw).hexdigest() != str(layer.get("artifact_sha256", "")):
            raise RuntimeError(f"housing spatial artifact hash mismatch: {layer_id}")
    return payload


def iter_layer_rows(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"spatial row {line_number} is not an object: {path.name}")
            yield payload


def parse_datetime(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def database_spatial_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(SpatialFeature.layer_id, func.count())
        .group_by(SpatialFeature.layer_id)
        .order_by(SpatialFeature.layer_id)
    ).all()
    return {str(layer_id): int(count) for layer_id, count in rows}


def database_spatial_snapshot_hashes(session: Session) -> dict[str, str]:
    return {
        str(layer_id): str(content_hash)
        for layer_id, content_hash in session.execute(
            select(SpatialLayerSnapshot.layer_id, SpatialLayerSnapshot.content_hash)
        ).all()
    }


def _mapping(row: dict[str, Any], layer_id: str) -> dict[str, Any]:
    bbox = row.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError(f"invalid bbox in {layer_id}:{row.get('feature_id')}")
    properties = row.get("properties") or {}
    geometry = row.get("geometry")
    if not isinstance(properties, dict) or not isinstance(geometry, dict):
        raise ValueError(f"invalid spatial payload in {layer_id}:{row.get('feature_id')}")
    contexts = HOUSING_POINT_CONTEXTS if layer_id == "housing_points" else {}
    if sanitize_payload(properties, field_contexts=contexts) != properties:
        raise ValueError(
            f"private/contact value leaked into spatial properties: "
            f"{layer_id}:{row.get('feature_id')}"
        )
    if row.get("source_id") != SOURCE_ID or row.get("layer_id") != layer_id:
        raise ValueError(f"spatial source/layer mismatch: {layer_id}:{row.get('feature_id')}")
    return {
        "source_id": SOURCE_ID,
        "layer_id": layer_id,
        "feature_id": str(row["feature_id"]),
        "geometry_type": str(row["geometry_type"]),
        "adm3_pcode": properties.get("adm3_pcode"),
        "min_lon": float(bbox[0]),
        "min_lat": float(bbox[1]),
        "max_lon": float(bbox[2]),
        "max_lat": float(bbox[3]),
        "properties": properties,
        "geometry_json": json.dumps(
            geometry,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "evidence_path": str(row["evidence_path"]),
        "evidence_sha256": str(row["evidence_sha256"]),
        "fetched_at": parse_datetime(row.get("fetched_at")),
        "as_of": str(row.get("as_of") or "ไม่ระบุ"),
        "quality_status": str(row.get("quality_status") or "needs_review"),
    }


def sync_spatial_layers(
    session: Session,
    manifest_path: Path = SPATIAL_MANIFEST_PATH,
) -> dict[str, Any]:
    """Transactionally replace changed layers after exact count/privacy gates."""

    manifest = load_spatial_manifest(manifest_path)
    root = manifest_path.parent
    before_counts = database_spatial_counts(session)
    before_hashes = database_spatial_snapshot_hashes(session)
    changed_layers: list[str] = []
    unchanged_layers: list[str] = []

    for layer_id, expected_count in REQUIRED_SPATIAL_COUNTS.items():
        layer = manifest["layers"][layer_id]
        content_hash = str(layer["artifact_sha256"])
        if (
            before_hashes.get(layer_id) == content_hash
            and before_counts.get(layer_id) == expected_count
        ):
            unchanged_layers.append(layer_id)
        else:
            changed_layers.append(layer_id)

    if not changed_layers:
        return {
            "expected": REQUIRED_SPATIAL_TOTAL,
            "loaded": 0,
            "changed_layers": [],
            "unchanged_layers": unchanged_layers,
            "counts": before_counts,
        }

    loaded = 0
    try:
        for layer_id in changed_layers:
            layer = manifest["layers"][layer_id]
            path = root / Path(str(layer["artifact_path"])).name
            expected_count = REQUIRED_SPATIAL_COUNTS[layer_id]
            session.execute(delete(SpatialFeature).where(SpatialFeature.layer_id == layer_id))
            session.execute(
                delete(SpatialLayerSnapshot).where(SpatialLayerSnapshot.layer_id == layer_id)
            )
            batch: list[dict[str, Any]] = []
            seen: set[str] = set()
            row_count = 0
            for row in iter_layer_rows(path):
                mapping = _mapping(row, layer_id)
                feature_id = mapping["feature_id"]
                if feature_id in seen:
                    raise ValueError(f"duplicate feature_id in {layer_id}: {feature_id}")
                seen.add(feature_id)
                batch.append(mapping)
                row_count += 1
                if len(batch) >= INSERT_BATCH_SIZE:
                    session.execute(insert(SpatialFeature), batch)
                    batch.clear()
            if batch:
                session.execute(insert(SpatialFeature), batch)
            if row_count != expected_count or len(seen) != expected_count:
                raise ValueError(
                    f"spatial layer count gate failed for {layer_id}: "
                    f"rows={row_count}, unique={len(seen)}, expected={expected_count}"
                )
            session.add(SpatialLayerSnapshot(
                layer_id=layer_id,
                source_id=SOURCE_ID,
                content_hash=str(layer["artifact_sha256"]),
                feature_count=expected_count,
                source_path=str(layer["artifact_path"]),
                quality_status="needs_review",
                updated_at=utc_now(),
            ))
            loaded += row_count
        session.flush()
        final_counts = database_spatial_counts(session)
        if final_counts != REQUIRED_SPATIAL_COUNTS:
            raise ValueError(
                f"database spatial count contract failed: actual={final_counts}, "
                f"expected={REQUIRED_SPATIAL_COUNTS}"
            )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return {
        "expected": REQUIRED_SPATIAL_TOTAL,
        "loaded": loaded,
        "changed_layers": changed_layers,
        "unchanged_layers": unchanged_layers,
        "counts": REQUIRED_SPATIAL_COUNTS,
    }


def spatial_contract_snapshot(session: Session, *, required: bool) -> dict[str, Any]:
    counts = database_spatial_counts(session)
    exact = counts == REQUIRED_SPATIAL_COUNTS
    return {
        "required": required,
        "complete": exact if required else True,
        "counts": counts,
        "feature_total": sum(counts.values()),
        "expected_counts": REQUIRED_SPATIAL_COUNTS if required else {},
        "expected_total": REQUIRED_SPATIAL_TOTAL if required else 0,
        "snapshot_hashes": database_spatial_snapshot_hashes(session),
        "unexpected_layers": dict(Counter(counts) - Counter(REQUIRED_SPATIAL_COUNTS)),
    }
