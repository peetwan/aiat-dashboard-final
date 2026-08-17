from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal, engine
from app.models import (
    DashboardRecord,
    Endpoint,
    HousingDemandRecord,
    HousingDemandSnapshot,
    IngestionRun,
    PublicArtifact,
    Source,
    SpatialFeature,
    SpatialLayerSnapshot,
)
from explorer.source_profiles import SOURCE_PROFILES, validate_profile_coverage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPLORER_ROOT = Path(__file__).resolve().parent
CATALOG_PATH = PROJECT_ROOT / "config" / "source_catalog.json"
REFRESH_INTERVAL_SECONDS = 30
ARTIFACT_PREVIEW_MAX_DEPTH = 6
ARTIFACT_PREVIEW_MAX_DICT_KEYS = 40
ARTIFACT_PREVIEW_MAX_LIST_ITEMS = 12
ARTIFACT_PREVIEW_MAX_STRING_LENGTH = 800
ARTIFACT_PREVIEW_NODE_BUDGET = 320

SENSITIVE_JSON_KEYS = {
    "citizen_id",
    "contact",
    "contact_name",
    "e_mail",
    "email",
    "first_name",
    "full_name",
    "last_name",
    "line_id",
    "mobile",
    "national_id",
    "phone",
    "respondent_name",
    "tel_no",
    "telephone",
}

app = FastAPI(
    title="AIAT Database Explorer",
    version="1.0.0",
    description="Read-only live metadata explorer for the AIAT Dashboard serving database.",
)
app.mount("/static", StaticFiles(directory=EXPLORER_ROOT / "static"), name="static")
templates = Jinja2Templates(directory=EXPLORER_ROOT / "templates")


TABLE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "sources",
        "group": "Control plane",
        "role_th": "รายชื่อแหล่งข้อมูล",
        "meaning_th": "รายชื่อเว็บไซต์และระบบต้นทางทั้ง 28 แหล่ง พร้อมสถานะว่าเราใช้ข้อมูลได้แค่ไหน",
        "grain_th": "1 แถว = 1 แหล่งข้อมูล",
        "primary_key": "source_id",
        "key_fields": ["source_id (PK)", "name_th", "source_url", "cloud_policy", "readiness_status"],
        "count_mode": "row_count",
    },
    {
        "name": "endpoints",
        "group": "Control plane",
        "role_th": "ช่องทางที่ใช้ดึงข้อมูล",
        "meaning_th": "URL ของหน้าเว็บ API หรือไฟล์ที่ระบบใช้ดึงข้อมูลจากแต่ละแหล่ง",
        "grain_th": "1 แถว = 1 ช่องทางที่ใช้ดึงข้อมูล",
        "primary_key": "endpoint_id",
        "key_fields": ["endpoint_id (PK)", "source_id (FK)", "method", "kind", "runtime_enabled"],
        "foreign_keys": ["source_id → sources.source_id"],
        "count_mode": "row_count",
    },
    {
        "name": "ingestion_runs",
        "group": "Operational",
        "role_th": "ประวัติการนำเข้า",
        "meaning_th": "บันทึกว่าเราดึงข้อมูลจากแหล่งไหน เมื่อไร ได้กี่รายการ และสำเร็จหรือไม่",
        "grain_th": "1 แถว = 1 ครั้งที่ระบบดึงข้อมูล",
        "primary_key": "run_id",
        "key_fields": ["run_id (PK)", "source_id (FK)", "status", "records_loaded", "finished_at"],
        "foreign_keys": ["source_id → sources.source_id"],
        "count_mode": "row_count",
    },
    {
        "name": "dashboard_records",
        "group": "Candidate staging",
        "role_th": "ข้อมูลที่ยังรอตรวจ",
        "meaning_th": "ข้อมูลที่ดึงมาแล้ว แต่ยังไม่ให้ Dashboard ใช้จนกว่าจะตรวจความหมายและความถูกต้อง",
        "grain_th": "1 แถว = 1 รายการจากแหล่งข้อมูลในรอบนั้น",
        "primary_key": "id",
        "key_fields": ["id (PK)", "source_id (FK)", "dataset_key", "record_hash", "quality_status"],
        "foreign_keys": ["source_id → sources.source_id"],
        "count_mode": "row_count",
    },
    {
        "name": "public_artifacts",
        "group": "Public serving",
        "role_th": "JSON ที่ Dashboard ใช้",
        "meaning_th": "ไฟล์ JSON ที่ตรวจและสร้างเสร็จแล้ว พร้อมให้ API และ Dashboard อ่าน",
        "grain_th": "1 แถว = 1 ไฟล์ JSON เช่น สรุปจังหวัดหรือข้อมูลแผนที่",
        "primary_key": "artifact_key",
        "key_fields": ["artifact_key (PK)", "artifact_group", "province_code", "item_count", "updated_at"],
        "count_mode": "row_count",
    },
    {
        "name": "spatial_layer_snapshots",
        "group": "Spatial serving",
        "role_th": "ชุดข้อมูลแผนที่",
        "meaning_th": "บอกว่าแผนที่ที่อยู่อาศัยแต่ละชั้นใช้ข้อมูลชุดไหนและมีจุดหรือพื้นที่กี่รายการ",
        "grain_th": "1 แถว = 1 ชั้นข้อมูลบนแผนที่",
        "primary_key": "layer_id",
        "key_fields": ["layer_id (PK)", "source_id (FK)", "feature_count", "content_hash", "quality_status"],
        "foreign_keys": ["source_id → sources.source_id"],
        "count_mode": "row_count",
    },
    {
        "name": "spatial_features",
        "group": "Spatial serving",
        "role_th": "จุดและพื้นที่บนแผนที่",
        "meaning_th": "พิกัด รูปร่าง และรายละเอียดที่ปลอดภัยสำหรับแสดงบนแผนที่",
        "grain_th": "1 แถว = 1 จุด เส้น หรือพื้นที่บนแผนที่",
        "primary_key": "id",
        "key_fields": ["id (PK)", "source_id (FK)", "layer_id", "geometry_type", "quality_status"],
        "foreign_keys": ["source_id → sources.source_id", "layer_id → logical spatial snapshot"],
        "count_mode": "snapshot_contract",
    },
    {
        "name": "housing_demand_snapshots",
        "group": "Housing serving",
        "role_th": "ชุดข้อมูลความต้องการที่อยู่อาศัย",
        "meaning_th": "บอกว่า Dashboard กำลังใช้แบบสอบถามชุดไหนและมีคำตอบกี่รายการ",
        "grain_th": "1 แถว = 1 ชุดข้อมูลแบบสอบถามที่ตรวจแล้ว",
        "primary_key": "snapshot_id",
        "key_fields": ["snapshot_id (PK)", "source_id (FK)", "record_count", "content_hash", "quality_status"],
        "foreign_keys": ["source_id → sources.source_id"],
        "count_mode": "row_count",
    },
    {
        "name": "housing_demand_records",
        "group": "Housing serving",
        "role_th": "คำตอบแบบสอบถามที่อยู่อาศัย",
        "meaning_th": "คำตอบแบบสอบถามที่ตัดรหัสต้นทาง ชื่อ เบอร์โทร และอีเมลแล้ว",
        "grain_th": "1 แถว = 1 คำตอบแบบสอบถามที่ปลอดภัยสำหรับนำมาสรุป",
        "primary_key": "source_row_number",
        "key_fields": ["source_row_number (PK)", "source_id (FK)", "living_province_code", "preferred_province_code", "quality_status"],
        "foreign_keys": ["source_id → sources.source_id"],
        "count_mode": "snapshot_contract",
    },
]

RELATIONSHIPS = [
    {"from": "sources", "to": "endpoints", "cardinality": "1 → many", "label_th": "หนึ่ง source มีหลาย endpoint"},
    {"from": "sources", "to": "ingestion_runs", "cardinality": "1 → many", "label_th": "หนึ่ง source มีหลายรอบดึง"},
    {"from": "sources", "to": "dashboard_records", "cardinality": "1 → many", "label_th": "หนึ่ง source มี candidate records หลายแถว"},
    {"from": "sources", "to": "spatial_layer_snapshots", "cardinality": "1 → many", "label_th": "Housing source มีหลาย spatial layers"},
    {"from": "spatial_layer_snapshots", "to": "spatial_features", "cardinality": "1 → many", "label_th": "หนึ่ง layer มีหลาย GIS features"},
    {"from": "sources", "to": "housing_demand_snapshots", "cardinality": "1 → many", "label_th": "Housing source มี validated snapshots"},
    {"from": "housing_demand_snapshots", "to": "housing_demand_records", "cardinality": "1 → many", "label_th": "หนึ่ง snapshot มีหลายคำตอบ"},
    {"from": "validated public files", "to": "public_artifacts", "cardinality": "build → sync", "label_th": "Public artifacts มาจาก deterministic builders ไม่ auto-promote จาก staging"},
]


PREVIEW_TABLES: dict[str, dict[str, Any]] = {
    "sources": {
        "model": Source,
        "columns": [
            "source_id",
            "ordinal",
            "name_th",
            "source_url",
            "acquisition_mode",
            "readiness_status",
            "cloud_policy",
            "production_values_allowed",
            "expected_record_count",
            "updated_at",
        ],
        "order_by": "ordinal",
        "source_scoped": True,
    },
    "endpoints": {
        "model": Endpoint,
        "columns": [
            "endpoint_id",
            "source_id",
            "method",
            "url",
            "kind",
            "access_status",
            "restricted",
            "runtime_enabled",
        ],
        "order_by": "endpoint_id",
        "source_scoped": True,
    },
    "ingestion_runs": {
        "model": IngestionRun,
        "columns": [
            "run_id",
            "source_id",
            "strategy",
            "status",
            "started_at",
            "finished_at",
            "as_of",
            "records_seen",
            "records_loaded",
            "records_skipped",
        ],
        "order_by": "started_at",
        "source_scoped": True,
        "descending": True,
    },
    "dashboard_records": {
        "model": DashboardRecord,
        "columns": [
            "id",
            "source_id",
            "dataset_key",
            "source_record_id",
            "quality_status",
            "fetched_at",
            "as_of",
        ],
        "order_by": "id",
        "source_scoped": True,
        "descending": True,
    },
    "public_artifacts": {
        "model": PublicArtifact,
        "columns": [
            "artifact_key",
            "artifact_group",
            "province_code",
            "item_count",
            "updated_at",
        ],
        "order_by": "updated_at",
        "source_scoped": False,
        "descending": True,
    },
    "spatial_layer_snapshots": {
        "model": SpatialLayerSnapshot,
        "columns": [
            "layer_id",
            "source_id",
            "feature_count",
            "quality_status",
            "updated_at",
        ],
        "order_by": "layer_id",
        "source_scoped": True,
    },
    "spatial_features": {
        "model": SpatialFeature,
        "columns": [
            "id",
            "source_id",
            "layer_id",
            "feature_id",
            "geometry_type",
            "adm3_pcode",
            "as_of",
            "quality_status",
            "fetched_at",
        ],
        "order_by": "id",
        "source_scoped": True,
    },
    "housing_demand_snapshots": {
        "model": HousingDemandSnapshot,
        "columns": [
            "snapshot_id",
            "source_id",
            "record_count",
            "quality_status",
            "updated_at",
        ],
        "order_by": "updated_at",
        "source_scoped": True,
        "descending": True,
    },
    "housing_demand_records": {
        "model": HousingDemandRecord,
        "columns": [
            "source_row_number",
            "source_id",
            "living_province_code",
            "preferred_province_code",
            "as_of",
            "quality_status",
            "fetched_at",
        ],
        "order_by": "source_row_number",
        "source_scoped": True,
    },
}


def _catalog() -> dict[str, Any]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    source_ids = {str(item["source_id"]) for item in payload["sources"]}
    validate_profile_coverage(source_ids)
    return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _policy_label(policy: str) -> str:
    return {
        "team_approved_public": "Public candidate",
        "metadata_only": "Metadata only",
        "restricted_local_only": "Restricted local-only",
    }.get(policy, policy)


def _connection_status(item: dict[str, Any], runtime_endpoint_count: int) -> tuple[str, str]:
    policy = str(item.get("cloud_policy") or "")
    mode = str(item.get("acquisition_mode") or "")
    if policy == "restricted_local_only":
        return "local_only", "Local only"
    if policy == "metadata_only":
        return "catalog_only", "Catalog only"
    if runtime_endpoint_count:
        return "api_connected", "API connected"
    if mode == "snapshot_only":
        return "snapshot_connected", "Snapshot connected"
    return "public_projection", "Public projection"


def _live_snapshot(session) -> dict[str, Any]:
    source_total = session.scalar(select(func.count()).select_from(Source)) or 0
    endpoint_total = session.scalar(select(func.count()).select_from(Endpoint)) or 0
    runtime_endpoints = (
        session.scalar(
            select(func.count()).select_from(Endpoint).where(Endpoint.runtime_enabled.is_(True))
        )
        or 0
    )
    run_total = session.scalar(select(func.count()).select_from(IngestionRun)) or 0
    candidate_total = session.scalar(select(func.count()).select_from(DashboardRecord)) or 0
    artifact_total = session.scalar(select(func.count()).select_from(PublicArtifact)) or 0
    artifact_groups = dict(
        session.execute(
            select(PublicArtifact.artifact_group, func.count())
            .group_by(PublicArtifact.artifact_group)
            .order_by(PublicArtifact.artifact_group)
        ).all()
    )
    spatial_layers = session.scalar(select(func.count()).select_from(SpatialLayerSnapshot)) or 0
    spatial_features = session.scalar(select(func.sum(SpatialLayerSnapshot.feature_count))) or 0
    demand_snapshots = session.scalar(select(func.count()).select_from(HousingDemandSnapshot)) or 0
    housing_demand_records = session.scalar(select(func.sum(HousingDemandSnapshot.record_count))) or 0
    latest_artifact_at = session.scalar(select(func.max(PublicArtifact.updated_at)))
    latest_run_at = session.scalar(select(func.max(IngestionRun.finished_at)))
    policy_counts = dict(
        session.execute(select(Source.cloud_policy, func.count()).group_by(Source.cloud_policy)).all()
    )
    run_status_counts = dict(
        session.execute(select(IngestionRun.status, func.count()).group_by(IngestionRun.status)).all()
    )
    return {
        "database_connected": True,
        "database_backend": engine.dialect.name,
        "checked_at": _utc_now(),
        "refresh_interval_seconds": REFRESH_INTERVAL_SECONDS,
        "source_total": source_total,
        "public_candidate_sources": policy_counts.get("team_approved_public", 0),
        "metadata_only_sources": policy_counts.get("metadata_only", 0),
        "restricted_sources": policy_counts.get("restricted_local_only", 0),
        "endpoint_total": endpoint_total,
        "runtime_endpoint_total": runtime_endpoints,
        "ingestion_run_total": run_total,
        "run_status_counts": run_status_counts,
        "operational_candidate_records": candidate_total,
        "public_artifact_total": artifact_total,
        "public_artifact_groups": artifact_groups,
        "spatial_layer_total": spatial_layers,
        "spatial_feature_total": spatial_features,
        "housing_demand_snapshot_total": demand_snapshots,
        "housing_demand_record_total": housing_demand_records,
        "latest_public_artifact_at": latest_artifact_at.isoformat() if latest_artifact_at else None,
        "latest_ingestion_run_at": latest_run_at.isoformat() if latest_run_at else None,
        "serving_mode": "read_only_live_shared_postgresql",
    }


def _source_rows(session) -> list[dict[str, Any]]:
    catalog = _catalog()
    live_sources = {item.source_id: item for item in session.scalars(select(Source)).all()}
    endpoint_rows = session.scalars(select(Endpoint).order_by(Endpoint.source_id, Endpoint.endpoint_id)).all()
    endpoint_map: dict[str, list[Endpoint]] = defaultdict(list)
    for endpoint in endpoint_rows:
        endpoint_map[endpoint.source_id].append(endpoint)

    record_counts = dict(
        session.execute(
            select(DashboardRecord.source_id, func.count()).group_by(DashboardRecord.source_id)
        ).all()
    )
    runs = session.scalars(
        select(IngestionRun).order_by(IngestionRun.source_id, IngestionRun.started_at.desc())
    ).all()
    latest_runs: dict[str, IngestionRun] = {}
    for run in runs:
        latest_runs.setdefault(run.source_id, run)

    result: list[dict[str, Any]] = []
    for item in sorted(catalog["sources"], key=lambda row: int(row["ordinal"])):
        source_id = str(item["source_id"])
        live = live_sources.get(source_id)
        endpoints = endpoint_map.get(source_id, [])
        runtime_count = sum(bool(endpoint.runtime_enabled) for endpoint in endpoints)
        connection_key, connection_label = _connection_status(item, runtime_count)
        latest = latest_runs.get(source_id)
        profile = SOURCE_PROFILES[source_id]
        result.append(
            {
                "ordinal": int(item["ordinal"]),
                "source_id": source_id,
                "group": item.get("group"),
                "name_th": live.name_th if live else item["name_th"],
                "url": live.source_url if live else item["url"],
                "source_type": item.get("source_type"),
                "sensitivity_lane": item.get("sensitivity_lane"),
                "acquisition_mode": live.acquisition_mode if live else item.get("acquisition_mode"),
                "readiness_status": live.readiness_status if live else item.get("readiness_status"),
                "cloud_policy": live.cloud_policy if live else item.get("cloud_policy"),
                "policy_label": _policy_label(str(item.get("cloud_policy") or "")),
                "production_values_allowed": bool(
                    live.production_values_allowed if live else item.get("production_values_allowed")
                ),
                "expected_record_count": int(
                    live.expected_record_count if live else item.get("expected_record_count", 0)
                ),
                "notes_th": live.notes_th if live else item.get("notes_th", ""),
                "what_we_use_th": profile["what_we_use_th"],
                "grain_th": profile["grain_th"],
                "dashboard_use_th": profile["dashboard_use_th"],
                "excluded_th": profile["excluded_th"],
                "database_targets": profile["database_targets"],
                "connection_status": connection_key,
                "connection_label": connection_label,
                "endpoint_count": len(endpoints),
                "runtime_endpoint_count": runtime_count,
                "operational_candidate_records": int(record_counts.get(source_id, 0)),
                "latest_run": (
                    {
                        "run_id": latest.run_id,
                        "status": latest.status,
                        "strategy": latest.strategy,
                        "started_at": latest.started_at.isoformat() if latest.started_at else None,
                        "finished_at": latest.finished_at.isoformat() if latest.finished_at else None,
                        "records_seen": latest.records_seen,
                        "records_loaded": latest.records_loaded,
                        "records_skipped": latest.records_skipped,
                    }
                    if latest
                    else None
                ),
                "endpoints": [
                    {
                        "endpoint_id": endpoint.endpoint_id,
                        "method": endpoint.method,
                        "url": endpoint.url,
                        "kind": endpoint.kind,
                        "access_status": endpoint.access_status,
                        "restricted": endpoint.restricted,
                        "runtime_enabled": endpoint.runtime_enabled,
                    }
                    for endpoint in endpoints
                ],
            }
        )
    return result


def _table_counts(session) -> dict[str, int]:
    spatial_contract_count = session.scalar(select(func.sum(SpatialLayerSnapshot.feature_count))) or 0
    demand_contract_count = session.scalar(select(func.sum(HousingDemandSnapshot.record_count))) or 0
    return {
        "sources": session.scalar(select(func.count()).select_from(Source)) or 0,
        "endpoints": session.scalar(select(func.count()).select_from(Endpoint)) or 0,
        "ingestion_runs": session.scalar(select(func.count()).select_from(IngestionRun)) or 0,
        "dashboard_records": session.scalar(select(func.count()).select_from(DashboardRecord)) or 0,
        "public_artifacts": session.scalar(select(func.count()).select_from(PublicArtifact)) or 0,
        "spatial_layer_snapshots": session.scalar(select(func.count()).select_from(SpatialLayerSnapshot)) or 0,
        "spatial_features": spatial_contract_count,
        "housing_demand_snapshots": session.scalar(select(func.count()).select_from(HousingDemandSnapshot)) or 0,
        "housing_demand_records": demand_contract_count,
    }


def _preview_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _artifact_file_name(source_path: str) -> str:
    return source_path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def _safe_artifact_source_path(source_path: str) -> str:
    normalized = source_path.replace("\\", "/")
    if normalized.startswith("data/public/"):
        return normalized
    marker = "/data/public/"
    if marker in normalized:
        return f"data/public/{normalized.split(marker, 1)[1]}"
    return _artifact_file_name(normalized)


def _is_sensitive_json_key(key: Any) -> bool:
    normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in SENSITIVE_JSON_KEYS:
        return True
    return normalized.endswith(("_email", "_phone", "_telephone", "_mobile", "_citizen_id"))


def _safe_json_preview(payload: Any) -> tuple[Any, bool]:
    """Return a bounded JSON preview with contact/identity values suppressed."""

    budget = {"remaining": ARTIFACT_PREVIEW_NODE_BUDGET}

    def visit(value: Any, depth: int) -> tuple[Any, bool]:
        if budget["remaining"] <= 0:
            return "[preview truncated]", True
        budget["remaining"] -= 1

        if depth >= ARTIFACT_PREVIEW_MAX_DEPTH and isinstance(value, (dict, list)):
            return "[preview truncated]", True

        if isinstance(value, dict):
            result: dict[str, Any] = {}
            truncated = len(value) > ARTIFACT_PREVIEW_MAX_DICT_KEYS
            for index, (key, item) in enumerate(value.items()):
                if index >= ARTIFACT_PREVIEW_MAX_DICT_KEYS:
                    break
                output_key = str(key)
                if _is_sensitive_json_key(output_key):
                    result[output_key] = "[hidden]"
                    continue
                preview_item, item_truncated = visit(item, depth + 1)
                result[output_key] = preview_item
                truncated = truncated or item_truncated
            return result, truncated

        if isinstance(value, list):
            result_list: list[Any] = []
            truncated = len(value) > ARTIFACT_PREVIEW_MAX_LIST_ITEMS
            for item in value[:ARTIFACT_PREVIEW_MAX_LIST_ITEMS]:
                preview_item, item_truncated = visit(item, depth + 1)
                result_list.append(preview_item)
                truncated = truncated or item_truncated
            return result_list, truncated

        if isinstance(value, str) and len(value) > ARTIFACT_PREVIEW_MAX_STRING_LENGTH:
            return f"{value[:ARTIFACT_PREVIEW_MAX_STRING_LENGTH]}…", True
        if isinstance(value, datetime):
            return value.isoformat(), False
        return value, False

    return visit(payload, 0)


def _artifact_metadata(artifact: PublicArtifact | Mapping[str, Any]) -> dict[str, Any]:
    def field(name: str) -> Any:
        return artifact[name] if isinstance(artifact, Mapping) else getattr(artifact, name)

    source_path = str(field("source_path"))
    updated_at = field("updated_at")
    return {
        "artifact_key": field("artifact_key"),
        "artifact_group": field("artifact_group"),
        "province_code": field("province_code"),
        "item_count": int(field("item_count") or 0),
        "updated_at": updated_at.isoformat() if updated_at else None,
        "file_name": _artifact_file_name(source_path),
        "source_path": _safe_artifact_source_path(source_path),
        "database_table": "public_artifacts",
        "database_column": "payload",
        "database_type": "JSON / JSONB",
        "database_location": "PostgreSQL → public_artifacts.payload",
    }


def _preview_rows(
    session,
    table_name: str,
    source_id: str | None,
    limit: int,
) -> dict[str, Any]:
    preview = PREVIEW_TABLES.get(table_name)
    if not preview:
        raise HTTPException(status_code=404, detail="preview table not found")

    model = preview["model"]
    column_names = list(preview["columns"])
    columns = [getattr(model, name).label(name) for name in column_names]
    source_scoped = bool(preview["source_scoped"])
    filter_applied = bool(source_id and source_scoped)

    count_statement = select(func.count()).select_from(model)
    row_statement = select(*columns)
    if filter_applied:
        source_column = getattr(model, "source_id")
        count_statement = count_statement.where(source_column == source_id)
        row_statement = row_statement.where(source_column == source_id)

    order_column = getattr(model, preview["order_by"])
    row_statement = row_statement.order_by(
        order_column.desc() if preview.get("descending") else order_column.asc()
    ).limit(limit)

    physical_row_count = session.scalar(count_statement) or 0
    rows = [
        {key: _preview_value(value) for key, value in row.items()}
        for row in session.execute(row_statement).mappings().all()
    ]
    table_definition = next(item for item in TABLE_DEFINITIONS if item["name"] == table_name)
    contract_count = _table_counts(session)[table_name]
    relationships = [
        item
        for item in RELATIONSHIPS
        if item["from"] == table_name or item["to"] == table_name
    ]
    return {
        "generated_at": _utc_now(),
        "table": table_name,
        "role_th": table_definition["role_th"],
        "meaning_th": table_definition["meaning_th"],
        "columns": column_names,
        "rows": rows,
        "sample_size": len(rows),
        "physical_row_count": int(physical_row_count),
        "serving_or_contract_count": int(contract_count),
        "count_mode": table_definition["count_mode"],
        "source_filter_supported": source_scoped,
        "source_filter_requested": source_id,
        "source_filter_applied": filter_applied,
        "safe_preview": True,
        "relationships": relationships,
    }


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "dashboard_url": os.getenv(
                "DASHBOARD_URL", "https://aiat-dashboard-web-production.up.railway.app"
            ),
            "refresh_interval_seconds": REFRESH_INTERVAL_SECONDS,
        },
    )


@app.get("/health")
def health():
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
            source_total = session.scalar(select(func.count()).select_from(Source)) or 0
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {
        "status": "ok",
        "database": "connected",
        "database_backend": engine.dialect.name,
        "source_total": source_total,
        "checked_at": _utc_now(),
    }


@app.get("/api/overview")
def overview():
    try:
        with SessionLocal() as session:
            return _live_snapshot(session)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/api/sources")
def sources():
    try:
        with SessionLocal() as session:
            rows = _source_rows(session)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {
        "generated_at": _utc_now(),
        "source_count": len(rows),
        "policy_counts": dict(Counter(row["cloud_policy"] for row in rows)),
        "connection_counts": dict(Counter(row["connection_status"] for row in rows)),
        "sources": rows,
    }


@app.get("/api/schema")
def schema():
    try:
        with SessionLocal() as session:
            counts = _table_counts(session)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    tables = [{**item, "live_row_count": int(counts[item["name"]])} for item in TABLE_DEFINITIONS]
    return {
        "generated_at": _utc_now(),
        "database_backend": engine.dialect.name,
        "read_only": True,
        "tables": tables,
        "relationships": RELATIONSHIPS,
    }


@app.get("/api/data-preview/{table_name}")
def data_preview(table_name: str, source_id: str | None = None, limit: int = 6):
    safe_limit = min(max(limit, 1), 10)
    try:
        with SessionLocal() as session:
            return _preview_rows(session, table_name, source_id, safe_limit)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/api/artifacts")
def artifacts():
    try:
        with SessionLocal() as session:
            rows = session.execute(
                select(
                    PublicArtifact.artifact_key,
                    PublicArtifact.artifact_group,
                    PublicArtifact.province_code,
                    PublicArtifact.item_count,
                    PublicArtifact.updated_at,
                    PublicArtifact.source_path,
                ).order_by(
                    PublicArtifact.artifact_group,
                    PublicArtifact.province_code,
                    PublicArtifact.artifact_key,
                )
            ).mappings().all()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {
        "generated_at": _utc_now(),
        "artifact_count": len(rows),
        "database_location": "PostgreSQL → public_artifacts.payload",
        "payload_included": False,
        "artifacts": [_artifact_metadata(artifact) for artifact in rows],
    }


@app.get("/api/artifact-preview")
def artifact_preview(artifact_key: str):
    try:
        with SessionLocal() as session:
            artifact = session.scalar(
                select(PublicArtifact).where(PublicArtifact.artifact_key == artifact_key)
            )
            if artifact is None:
                raise HTTPException(status_code=404, detail="artifact not found")
            payload_preview, truncated = _safe_json_preview(artifact.payload)
            return {
                "generated_at": _utc_now(),
                **_artifact_metadata(artifact),
                "payload_preview": payload_preview,
                "truncated": truncated,
                "safe_preview": True,
            }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/api/source/{source_id}")
def source_detail(source_id: str):
    try:
        with SessionLocal() as session:
            rows = _source_rows(session)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    for row in rows:
        if row["source_id"] == source_id:
            return row
    raise HTTPException(status_code=404, detail="source not found")
