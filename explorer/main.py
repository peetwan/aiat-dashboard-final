from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
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
    HousingDemandSnapshot,
    IngestionRun,
    PublicArtifact,
    Source,
    SpatialLayerSnapshot,
)
from explorer.source_profiles import SOURCE_PROFILES, validate_profile_coverage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPLORER_ROOT = Path(__file__).resolve().parent
CATALOG_PATH = PROJECT_ROOT / "config" / "source_catalog.json"
REFRESH_INTERVAL_SECONDS = 30

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
        "role_th": "ทะเบียนต้นทาง",
        "meaning_th": "ทะเบียนแหล่งข้อมูลทั้ง 28 แหล่ง พร้อม policy และสถานะ",
        "grain_th": "หนึ่งแถว = หนึ่ง source/URL",
        "primary_key": "source_id",
        "key_fields": ["source_id (PK)", "name_th", "source_url", "cloud_policy", "readiness_status"],
        "count_mode": "row_count",
    },
    {
        "name": "endpoints",
        "group": "Control plane",
        "role_th": "ประตูเชื่อมข้อมูล",
        "meaning_th": "รายการ API/หน้า/ไฟล์ที่ตรวจพบและสถานะ runtime",
        "grain_th": "หนึ่งแถว = หนึ่ง endpoint ของ source",
        "primary_key": "endpoint_id",
        "key_fields": ["endpoint_id (PK)", "source_id (FK)", "method", "kind", "runtime_enabled"],
        "foreign_keys": ["source_id → sources.source_id"],
        "count_mode": "row_count",
    },
    {
        "name": "ingestion_runs",
        "group": "Operational",
        "role_th": "ประวัติการนำเข้า",
        "meaning_th": "ประวัติรอบดึงข้อมูล เวลา จำนวน record และ error",
        "grain_th": "หนึ่งแถว = หนึ่งรอบดึงของ source",
        "primary_key": "run_id",
        "key_fields": ["run_id (PK)", "source_id (FK)", "status", "records_loaded", "finished_at"],
        "foreign_keys": ["source_id → sources.source_id"],
        "count_mode": "row_count",
    },
    {
        "name": "dashboard_records",
        "group": "Candidate staging",
        "role_th": "พื้นที่พักตรวจ",
        "meaning_th": "ข้อมูลจาก operational refresh ที่ยังไม่ถูก promote ไปหน้า Public Dashboard",
        "grain_th": "หนึ่งแถว = หนึ่ง version ของ source record",
        "primary_key": "id",
        "key_fields": ["id (PK)", "source_id (FK)", "dataset_key", "record_hash", "quality_status"],
        "foreign_keys": ["source_id → sources.source_id"],
        "count_mode": "row_count",
    },
    {
        "name": "public_artifacts",
        "group": "Public serving",
        "role_th": "ชุดข้อมูลที่เผยแพร่",
        "meaning_th": "JSON ที่ผ่าน build/test แล้วและ Public API อ่านจริง",
        "grain_th": "หนึ่งแถว = หนึ่ง artifact เช่น summary/briefing/map",
        "primary_key": "artifact_key",
        "key_fields": ["artifact_key (PK)", "artifact_group", "province_code", "item_count", "updated_at"],
        "count_mode": "row_count",
    },
    {
        "name": "spatial_layer_snapshots",
        "group": "Spatial serving",
        "role_th": "เวอร์ชันชั้นแผนที่",
        "meaning_th": "เวอร์ชันและจำนวน feature ของแต่ละ Housing spatial layer",
        "grain_th": "หนึ่งแถว = หนึ่ง spatial layer snapshot",
        "primary_key": "layer_id",
        "key_fields": ["layer_id (PK)", "source_id (FK)", "feature_count", "content_hash", "quality_status"],
        "foreign_keys": ["source_id → sources.source_id"],
        "count_mode": "row_count",
    },
    {
        "name": "spatial_features",
        "group": "Spatial serving",
        "role_th": "ข้อมูล GIS",
        "meaning_th": "Geometry/properties ที่ผ่าน privacy projection สำหรับค้นหาตามพื้นที่",
        "grain_th": "หนึ่งแถว = หนึ่ง GIS feature",
        "primary_key": "id",
        "key_fields": ["id (PK)", "source_id (FK)", "layer_id", "geometry_type", "quality_status"],
        "foreign_keys": ["source_id → sources.source_id", "layer_id → logical spatial snapshot"],
        "count_mode": "snapshot_contract",
    },
    {
        "name": "housing_demand_snapshots",
        "group": "Housing serving",
        "role_th": "เวอร์ชัน Demand",
        "meaning_th": "เวอร์ชันและ hash ของ Housing Demand ชุดปัจจุบัน",
        "grain_th": "หนึ่งแถว = หนึ่ง validated demand snapshot",
        "primary_key": "snapshot_id",
        "key_fields": ["snapshot_id (PK)", "source_id (FK)", "record_count", "content_hash", "quality_status"],
        "foreign_keys": ["source_id → sources.source_id"],
        "count_mode": "row_count",
    },
    {
        "name": "housing_demand_records",
        "group": "Housing serving",
        "role_th": "คำตอบ Demand",
        "meaning_th": "คำตอบ Housing Demand ที่ตัด source ID และข้อมูลติดต่อแล้ว",
        "grain_th": "หนึ่งแถว = หนึ่งคำตอบแบบสอบถามที่ผ่าน privacy projection",
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


def _catalog() -> dict[str, Any]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    source_ids = {str(item["source_id"]) for item in payload["sources"]}
    validate_profile_coverage(source_ids)
    return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _policy_label(policy: str) -> str:
    return {
        "project_owner_approved_public": "Public candidate",
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
        "public_candidate_sources": policy_counts.get("project_owner_approved_public", 0),
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
