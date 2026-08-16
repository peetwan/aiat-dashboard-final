from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select, text

from app.catalog import load_catalog, load_ingestion_plans, sync_catalog
from app.database import SessionLocal, engine, init_db
from app.models import DashboardRecord, Endpoint, IngestionRun, Source
from app.settings import PROJECT_ROOT, get_settings


settings = get_settings()
templates = Jinja2Templates(directory=PROJECT_ROOT / "app" / "templates")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as session:
        sync_catalog(session)
    yield


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "app" / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.app_name,
            "app_env": settings.app_env,
            "values_enabled": settings.public_data_values_enabled,
        },
    )


@app.get("/health")
def health():
    with SessionLocal() as session:
        session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected", "app_env": settings.app_env}


@app.get("/api/summary")
def summary():
    with SessionLocal() as session:
        source_count = session.scalar(select(func.count()).select_from(Source)) or 0
        endpoint_count = session.scalar(select(func.count()).select_from(Endpoint)) or 0
        safe_endpoints = (
            session.scalar(
                select(func.count()).select_from(Endpoint).where(
                    Endpoint.restricted.is_(False),
                    Endpoint.runtime_enabled.is_(True),
                )
            )
            or 0
        )
        records = session.scalar(select(func.count()).select_from(DashboardRecord)) or 0
        production_approved_sources = (
            session.scalar(
                select(func.count()).select_from(Source).where(
                    Source.production_values_allowed.is_(True)
                )
            )
            or 0
        )
        complete_runs = (
            session.scalar(
                select(func.count()).select_from(IngestionRun).where(IngestionRun.status == "complete")
            )
            or 0
        )
        failed_runs = (
            session.scalar(
                select(func.count()).select_from(IngestionRun).where(IngestionRun.status == "failed")
            )
            or 0
        )
        expected_records = (
            session.scalar(
                select(func.sum(Source.expected_record_count)).where(
                    Source.production_values_allowed.is_(True)
                )
            )
            or 0
        )
        api_first_sources = (
            session.scalar(
                select(func.count()).select_from(Source).where(Source.acquisition_mode == "api_first")
            )
            or 0
        )
        snapshot_sources = (
            session.scalar(
                select(func.count()).select_from(Source).where(
                    Source.acquisition_mode == "snapshot_only"
                )
            )
            or 0
        )
        blocked_sources = (
            session.scalar(
                select(func.count()).select_from(Source).where(
                    Source.acquisition_mode == "blocked"
                )
            )
            or 0
        )
        latest_run_at = session.scalar(select(func.max(IngestionRun.started_at)))
        return {
            "sources": source_count,
            "endpoints_catalogued": endpoint_count,
            "safe_runtime_endpoints": safe_endpoints,
            "candidate_records_loaded": records,
            "production_approved_sources": production_approved_sources,
            "complete_runs": complete_runs,
            "failed_runs": failed_runs,
            "expected_candidate_records": expected_records,
            "api_first_sources": api_first_sources,
            "snapshot_sources": snapshot_sources,
            "blocked_sources": blocked_sources,
            "configured_connectors": api_first_sources + snapshot_sources,
            "database_backend": engine.dialect.name,
            "latest_run_at": latest_run_at,
            "public_data_values_enabled": settings.public_data_values_enabled,
            "warning": "ทุกค่าปัจจุบันเป็น candidate/needs_review ไม่ใช่ KPI หรือ production fact",
        }


@app.get("/api/sources")
def sources():
    with SessionLocal() as session:
        record_counts = dict(
            session.execute(
                select(DashboardRecord.source_id, func.count(DashboardRecord.id)).group_by(
                    DashboardRecord.source_id
                )
            ).all()
        )
        endpoint_counts: dict[str, dict[str, int]] = {}
        for endpoint in session.scalars(select(Endpoint)).all():
            counts = endpoint_counts.setdefault(
                endpoint.source_id,
                {"total": 0, "runtime": 0, "restricted": 0},
            )
            counts["total"] += 1
            counts["runtime"] += int(endpoint.runtime_enabled and not endpoint.restricted)
            counts["restricted"] += int(endpoint.restricted)

        latest_runs: dict[str, IngestionRun] = {}
        for run in session.scalars(select(IngestionRun).order_by(desc(IngestionRun.started_at))).all():
            latest_runs.setdefault(run.source_id, run)

        items = session.scalars(select(Source).order_by(Source.ordinal)).all()
        result = []
        for item in items:
            counts = endpoint_counts.get(item.source_id, {"total": 0, "runtime": 0, "restricted": 0})
            latest = latest_runs.get(item.source_id)
            result.append({
                "ordinal": item.ordinal,
                "source_id": item.source_id,
                "name_th": item.name_th,
                "url": item.source_url,
                "acquisition_mode": item.acquisition_mode,
                "readiness_status": item.readiness_status,
                "cloud_policy": item.cloud_policy,
                "production_values_allowed": item.production_values_allowed,
                "expected_record_count": item.expected_record_count,
                "loaded_records": record_counts.get(item.source_id, 0),
                "endpoint_count": counts["total"],
                "runtime_endpoint_count": counts["runtime"],
                "restricted_endpoint_count": counts["restricted"],
                "latest_run": (
                    {
                        "run_id": latest.run_id,
                        "status": latest.status,
                        "strategy": latest.strategy,
                        "started_at": latest.started_at,
                        "records_loaded": latest.records_loaded,
                    }
                    if latest
                    else None
                ),
                "notes_th": item.notes_th,
            })
        return result


@app.get("/api/connectivity")
def connectivity():
    catalog = load_catalog()
    api_plans = load_ingestion_plans().get("sources", {})
    backend = engine.dialect.name
    result = []
    for source in catalog["sources"]:
        source_id = source["source_id"]
        snapshot_path = settings.resolved_snapshot_root / source_id
        snapshot_configured = bool(source.get("snapshot_fallback")) or source["acquisition_mode"] == "snapshot_only"
        result.append(
            {
                "source_id": source_id,
                "name_th": source["name_th"],
                "acquisition_mode": source["acquisition_mode"],
                "api_plan_configured": source_id in api_plans,
                "snapshot_configured": snapshot_configured,
                "snapshot_available": snapshot_path.exists(),
                "database_backend": backend,
                "cloud_policy": source["cloud_policy"],
                "deployable": source["cloud_policy"] != "restricted_local_only",
                "candidate_only": source["readiness_status"] == "needs_review",
            }
        )
    return result


@app.get("/api/sources/{source_id}/endpoints")
def endpoints(source_id: str):
    with SessionLocal() as session:
        if not session.get(Source, source_id):
            raise HTTPException(status_code=404, detail="ไม่พบ source")
        items = session.scalars(
            select(Endpoint).where(Endpoint.source_id == source_id).order_by(Endpoint.url)
        ).all()
        return [
            {
                "method": item.method,
                "url": item.url,
                "kind": item.kind,
                "access": item.access_status,
                "team_action": item.team_action,
                "restricted": item.restricted,
                "runtime_enabled": item.runtime_enabled,
                "notes_th": item.notes_th,
            }
            for item in items
        ]


@app.get("/api/runs")
def runs(limit: int = Query(20, ge=1, le=200)):
    with SessionLocal() as session:
        items = session.scalars(
            select(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(limit)
        ).all()
        return [
            {
                "run_id": item.run_id,
                "source_id": item.source_id,
                "strategy": item.strategy,
                "status": item.status,
                "started_at": item.started_at,
                "finished_at": item.finished_at,
                "records_seen": item.records_seen,
                "records_loaded": item.records_loaded,
                "records_skipped": item.records_skipped,
                "manifest_path": item.manifest_path,
                "note": item.error_message,
            }
            for item in items
        ]


@app.get("/api/records")
def records(
    source_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    include_payload: bool = False,
):
    if include_payload and not settings.public_data_values_enabled:
        raise HTTPException(
            status_code=403,
            detail="ปิดการแสดงค่าจริงอยู่; ต้องผ่าน owner/privacy gate ก่อน",
        )
    with SessionLocal() as session:
        query = select(DashboardRecord).order_by(desc(DashboardRecord.id)).limit(limit)
        if source_id:
            query = query.where(DashboardRecord.source_id == source_id)
        items = session.scalars(query).all()
        result = []
        for item in items:
            row = {
                "id": item.id,
                "source_id": item.source_id,
                "dataset_key": item.dataset_key,
                "source_record_id": item.source_record_id,
                "record_hash": item.record_hash,
                "quality_status": item.quality_status,
                "fetched_at": item.fetched_at,
                "as_of": item.as_of,
            }
            if include_payload:
                row["payload"] = item.payload
            result.append(row)
        return result
