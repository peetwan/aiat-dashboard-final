from __future__ import annotations

import json
import re
from copy import deepcopy
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select, text

from app.catalog import load_catalog, load_ingestion_plans, sync_catalog, validate_catalog_contract
from app.database import SessionLocal, engine, init_db
from app.models import DashboardRecord, Endpoint, IngestionRun, PublicArtifact, Source, SpatialFeature
from app.api_schemas import (
    CulturalPointFeatureCollectionResponse,
    DatabaseCoverageResponse,
    DisasterProvinceIndexResponse,
    DisasterStationHistoryResponse,
    DisasterTimeseriesResponse,
    DisasterTrackingResponse,
    ExecutiveSummaryResponse,
    HealthResponse,
    HousingDemandSummaryResponse,
    HousingSpatialFeatureCollectionResponse,
    HousingSpatialSummaryResponse,
    LearningDashboardResponse,
    OperationsResponse,
    ProvinceFeatureCollectionResponse,
    ProvinceResponse,
    ProvincialBriefingResponse,
    PublicCatalogResponse,
    PublicOverviewResponse,
    PublicSourceResponse,
    SourceCoverageResponse,
    SourceInsightsResponse,
    UnmappedRecordsResponse,
)
from app.public_artifacts import (
    REQUIRED_ARTIFACT_COUNT,
    REQUIRED_GROUP_COUNTS,
    database_artifact_counts,
    sync_public_artifacts,
)
from app.publication import (
    PublicationError,
    downloadable_public_files,
    validate_workspace,
)
from app.public_data import (
    cultural_points,
    executive_summary,
    housing_spatial_summary,
    housing_demand_summary,
    learning_dashboard,
    province_boundaries,
    provincial_briefing,
    public_catalog,
    source_coverage,
    source_insights,
    unmapped_records,
)
from app.operations import operations_status
from app.settings import PROJECT_ROOT, get_settings
from app.spatial_artifacts import (
    REQUIRED_SPATIAL_COUNTS,
    REQUIRED_SPATIAL_TOTAL,
    spatial_contract_snapshot,
    sync_spatial_layers,
)
from app.demand_artifacts import (
    REQUIRED_DEMAND_COUNT,
    demand_contract_snapshot,
    sync_housing_demand,
)


settings = get_settings()
templates = Jinja2Templates(directory=PROJECT_ROOT / "app" / "templates")
PUBLICATION_CONTRACTS_ROOT = PROJECT_ROOT / "config" / "publication_contracts"

_REVIEWED_CATALOG = load_catalog()
validate_catalog_contract(_REVIEWED_CATALOG)
_REVIEWED_SOURCES = _REVIEWED_CATALOG["sources"]
EXPECTED_PUBLIC_ARTIFACTS = REQUIRED_ARTIFACT_COUNT
EXPECTED_SOURCE_COUNT = len(_REVIEWED_SOURCES)
EXPECTED_PUBLIC_SOURCE_COUNT = sum(
    source.get("cloud_policy") == "team_approved_public" for source in _REVIEWED_SOURCES
)


def _reviewed_dashboard_source_ids() -> frozenset[str]:
    """Return the reviewed public-dashboard inventory, not every ingestible source.

    Catalog `team_approved_public` can grow before a publication rebuild adds the
    source to `public_dashboard.json`. Health still requires the published
    inventory to match `dashboard_core.source_ids` and stay inside the approved set.
    """

    contract = json.loads(
        (PUBLICATION_CONTRACTS_ROOT / "dashboard_core.json").read_text(encoding="utf-8")
    )
    source_ids = contract.get("source_ids")
    if not isinstance(source_ids, list) or not source_ids:
        raise RuntimeError("dashboard_core.source_ids must be a non-empty list")
    if len(source_ids) != len(set(source_ids)):
        raise RuntimeError("dashboard_core.source_ids contains duplicates")
    if any(not isinstance(item, str) or not item.strip() for item in source_ids):
        raise RuntimeError("dashboard_core.source_ids must be non-empty strings")
    approved_ids = {
        source["source_id"]
        for source in _REVIEWED_SOURCES
        if source.get("cloud_policy") == "team_approved_public"
    }
    unknown = sorted(set(source_ids) - approved_ids)
    if unknown:
        raise RuntimeError(
            "dashboard_core.source_ids includes sources that are not "
            "team_approved_public: " + ", ".join(unknown)
        )
    return frozenset(source_ids)


REVIEWED_DASHBOARD_SOURCE_IDS = _reviewed_dashboard_source_ids()
EXPECTED_PUBLISHED_DASHBOARD_SOURCE_COUNT = len(REVIEWED_DASHBOARD_SOURCE_IDS)
EXPECTED_METADATA_SOURCE_COUNT = sum(
    source.get("cloud_policy") == "metadata_only" for source in _REVIEWED_SOURCES
)
EXPECTED_RESTRICTED_SOURCE_COUNT = sum(
    source.get("cloud_policy") == "restricted_local_only" for source in _REVIEWED_SOURCES
)
EXPECTED_ENDPOINT_COUNT = sum(len(source.get("endpoints", [])) for source in _REVIEWED_SOURCES)
EXPECTED_RUNTIME_ENDPOINT_COUNT = sum(
    endpoint.get("runtime_enabled") is True and endpoint.get("restricted") is not True
    for source in _REVIEWED_SOURCES
    for endpoint in source.get("endpoints", [])
)
STARTUP_SYNC_LOCK_ID = 0x4149415453594E43  # ASCII "AIATSYNC", signed bigint-safe.
SPATIAL_DATABASE_REQUIRED = (
    settings.app_env.lower() == "production" and engine.dialect.name == "postgresql"
)
EXPECTED_SPATIAL_FEATURES = REQUIRED_SPATIAL_TOTAL if SPATIAL_DATABASE_REQUIRED else 0
DEMAND_DATABASE_REQUIRED = (
    settings.app_env.lower() == "production" and engine.dialect.name == "postgresql"
)
EXPECTED_DEMAND_RECORDS = REQUIRED_DEMAND_COUNT if DEMAND_DATABASE_REQUIRED else 0
_PUBLICATION_PREFLIGHT_COMPLETE = False
THAIWATER_SOURCE_ID = "spu_sukhothai_water"
SPU_DISASTER_PROVINCES = {
    "64": {
        "province_name": "สุโขทัย",
        "sources": ("spu_sukhothai_care",),
    },
    "60": {
        "province_name": "นครสวรรค์",
        "sources": ("spu_nsn_flood",),
    },
    "53": {
        "province_name": "อุตรดิตถ์",
        "sources": ("spu_rawangphai_uru",),
    },
}
SPU_DISASTER_SOURCE_NAMES = {
    "spu_rawangphai_uru": "RawangPhai อุตรดิตถ์",
    "spu_sukhothai_water": "ThaiWater ระดับน้ำ/ฝน/เขื่อน",
    "spu_sukhothai_care": "Sukhothai Care",
    "spu_nsn_flood": "NSN Flood",
}
SPU_PROVINCE_SPECIFIC_DISASTER_SOURCE_PROVINCES = {
    source_id: province_code
    for province_code, config in SPU_DISASTER_PROVINCES.items()
    for source_id in config["sources"]
}


def _debug_api_enabled() -> bool:
    return (
        settings.app_env.lower() in {"local", "development", "dev", "test"}
        and engine.dialect.name == "sqlite"
    )


def _preflight_publication_release() -> None:
    """Validate the immutable release once, before any serving rows are changed."""

    global _PUBLICATION_PREFLIGHT_COMPLETE
    if _PUBLICATION_PREFLIGHT_COMPLETE:
        return
    report = validate_workspace(
        PROJECT_ROOT,
        PUBLICATION_CONTRACTS_ROOT,
        PROJECT_ROOT / "config" / "source_catalog.json",
    )
    if report["status"] != "valid":
        evidence = "; ".join(report["problems"][:10])
        raise RuntimeError(f"publication preflight failed: {evidence}")
    _PUBLICATION_PREFLIGHT_COMPLETE = True


def _sync_serving_database() -> None:
    """Serialize startup seed work on PostgreSQL and stay lightweight on SQLite."""

    if engine.dialect.name != "postgresql":
        with SessionLocal() as session:
            sync_catalog(session)
            sync_public_artifacts(session)
        return

    # A session-level lock is intentional: both sync functions commit their own
    # transactions. Binding the ORM session to this checked-out connection keeps
    # the lock held across those commits until both synchronized sets are ready.
    with engine.connect() as connection:
        connection.execute(
            text("SELECT pg_advisory_lock(:lock_id)"),
            {"lock_id": STARTUP_SYNC_LOCK_ID},
        )
        # End the transaction started by SELECT without releasing the
        # session-level lock. The ORM can then own and commit each sync
        # transaction normally on this same checked-out connection.
        connection.commit()
        try:
            with SessionLocal(bind=connection) as session:
                sync_catalog(session)
                sync_public_artifacts(session)
                sync_spatial_layers(session)
                sync_housing_demand(session)
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": STARTUP_SYNC_LOCK_ID},
            )
            connection.commit()


def _serving_contract_snapshot(session) -> dict:
    """Return the fail-closed serving contract from database state only."""

    artifact_counts = database_artifact_counts(session)
    artifact_total = sum(artifact_counts.values())
    all_source_ids = set(session.scalars(select(Source.source_id)).all())
    approved_ids = set(
        session.scalars(
            select(Source.source_id).where(Source.production_values_allowed.is_(True))
        ).all()
    )
    public_policy_ids = set(
        session.scalars(
            select(Source.source_id).where(
                Source.cloud_policy == "team_approved_public"
            )
        ).all()
    )
    metadata_ids = set(
        session.scalars(
            select(Source.source_id).where(Source.cloud_policy == "metadata_only")
        ).all()
    )
    restricted_ids = set(
        session.scalars(
            select(Source.source_id).where(Source.cloud_policy == "restricted_local_only")
        ).all()
    )
    catalog_payload = session.scalar(
        select(PublicArtifact.payload).where(PublicArtifact.artifact_key == "catalog")
    )
    catalog_rows = catalog_payload.get("sources", []) if isinstance(catalog_payload, dict) else []
    published_ids = [
        row.get("source_id")
        for row in catalog_rows
        if isinstance(row, dict) and isinstance(row.get("source_id"), str)
    ] if isinstance(catalog_rows, list) else []
    published_id_set = set(published_ids)
    published_ids_match_approved = (
        isinstance(catalog_rows, list)
        and len(catalog_rows) == EXPECTED_PUBLISHED_DASHBOARD_SOURCE_COUNT
        and len(published_ids) == len(catalog_rows)
        and len(published_id_set) == len(published_ids)
        and published_id_set == REVIEWED_DASHBOARD_SOURCE_IDS
        and published_id_set <= approved_ids
    )
    restricted_catalog_sources = published_id_set & restricted_ids
    disallowed_operational_records = (
        session.scalar(
            select(func.count())
            .select_from(DashboardRecord)
            .join(Source, DashboardRecord.source_id == Source.source_id)
            .where(Source.production_values_allowed.is_(False))
        )
        or 0
    )
    approved_operational_records = (
        session.scalar(
            select(func.count())
            .select_from(DashboardRecord)
            .join(Source, DashboardRecord.source_id == Source.source_id)
            .where(Source.production_values_allowed.is_(True))
        )
        or 0
    )
    endpoint_total = session.scalar(select(func.count()).select_from(Endpoint)) or 0
    runtime_endpoint_total = (
        session.scalar(
            select(func.count()).select_from(Endpoint).where(
                Endpoint.runtime_enabled.is_(True),
                Endpoint.restricted.is_(False),
            )
        )
        or 0
    )
    spatial = spatial_contract_snapshot(
        session,
        required=SPATIAL_DATABASE_REQUIRED,
    )
    demand = demand_contract_snapshot(
        session,
        required=DEMAND_DATABASE_REQUIRED,
    )
    policy_partitions_are_exact = (
        approved_ids == public_policy_ids
        and not (approved_ids & metadata_ids)
        and not (approved_ids & restricted_ids)
        and not (metadata_ids & restricted_ids)
        and approved_ids | metadata_ids | restricted_ids == all_source_ids
    )
    complete = (
        artifact_total == EXPECTED_PUBLIC_ARTIFACTS
        and artifact_counts == REQUIRED_GROUP_COUNTS
        and len(all_source_ids) == EXPECTED_SOURCE_COUNT
        and len(approved_ids) == EXPECTED_PUBLIC_SOURCE_COUNT
        and len(public_policy_ids) == EXPECTED_PUBLIC_SOURCE_COUNT
        and len(metadata_ids) == EXPECTED_METADATA_SOURCE_COUNT
        and len(restricted_ids) == EXPECTED_RESTRICTED_SOURCE_COUNT
        and policy_partitions_are_exact
        and published_ids_match_approved
        and not restricted_catalog_sources
        and disallowed_operational_records == 0
        and endpoint_total == EXPECTED_ENDPOINT_COUNT
        and runtime_endpoint_total == EXPECTED_RUNTIME_ENDPOINT_COUNT
        and spatial["complete"]
        and demand["complete"]
    )
    return {
        "complete": complete,
        "artifact_counts": artifact_counts,
        "artifact_total": artifact_total,
        "source_total": len(all_source_ids),
        "approved_total": len(approved_ids),
        "public_policy_total": len(public_policy_ids),
        "metadata_only_total": len(metadata_ids),
        "restricted_source_total": len(restricted_ids),
        "published_catalog_source_count": len(published_ids),
        "published_catalog_ids_match_approved": published_ids_match_approved,
        "restricted_catalog_sources_published": len(restricted_catalog_sources),
        "disallowed_operational_records": disallowed_operational_records,
        "approved_operational_records": approved_operational_records,
        "endpoint_total": endpoint_total,
        "runtime_endpoint_total": runtime_endpoint_total,
        "spatial": spatial,
        "housing_demand": demand,
    }


def _require_local_debug_api() -> None:
    """Hide operational inventory, run, error and record routes in production."""

    if not _debug_api_enabled():
        raise HTTPException(status_code=404, detail="Not Found")


def _province_catalog_index() -> tuple[dict[str, str], dict[str, str]]:
    by_code: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for province in public_catalog().get("provinces", []):
        code = str(province.get("province_code") or "").zfill(2)
        name = str(province.get("province_name_th") or "").strip()
        if not code or not name:
            continue
        by_code[code] = name
        by_name[_normalize_disaster_text(name)] = code
    return by_code, by_name


def _disaster_province_name(province_code: str) -> str | None:
    by_code, _ = _province_catalog_index()
    return by_code.get(province_code)


def _count_disaster_rows(
    counts: dict[str, dict],
    province_code: str,
    source_id: str,
    record_count: int,
) -> None:
    if record_count <= 0:
        return
    item = counts.setdefault(
        province_code,
        {
            "disaster_source_count": 0,
            "disaster_record_count": 0,
            "disaster_sources": [],
        },
    )
    if source_id not in item["disaster_sources"]:
        item["disaster_source_count"] += 1
        item["disaster_sources"].append(source_id)
    item["disaster_record_count"] += record_count


def _disaster_counts_by_province() -> dict[str, dict]:
    with SessionLocal() as session:
        counts: dict[str, dict] = {}
        for source_id, province_code in SPU_PROVINCE_SPECIFIC_DISASTER_SOURCE_PROVINCES.items():
            province_name = SPU_DISASTER_PROVINCES[province_code]["province_name"]
            record_count = len(
                _disaster_rows_for_source(session, source_id, province_code, province_name)
            )
            _count_disaster_rows(counts, province_code, source_id, record_count)

        _, province_code_by_name = _province_catalog_index()
        thaiwater_counts: dict[str, int] = {}
        for record in _disaster_rows_for_source(session, THAIWATER_SOURCE_ID):
            payload = record.payload if isinstance(record.payload, dict) else {}
            province_value = _safe_disaster_value(
                payload,
                ("province_th", "province_name_th", "province", "province_name"),
            )
            province_code = province_code_by_name.get(_normalize_disaster_text(province_value))
            if province_code:
                thaiwater_counts[province_code] = thaiwater_counts.get(province_code, 0) + 1
        for province_code, record_count in thaiwater_counts.items():
            _count_disaster_rows(counts, province_code, THAIWATER_SOURCE_ID, record_count)
    return counts


def _disaster_sources_for_province(
    session,
    province_code: str,
    province_name: str,
) -> list[tuple[str, list[DashboardRecord]]]:
    sources: list[tuple[str, list[DashboardRecord]]] = []
    for source_id in SPU_DISASTER_PROVINCES.get(province_code, {}).get("sources", ()):
        records = _disaster_rows_for_source(session, source_id, province_code, province_name)
        if records:
            sources.append((source_id, records))

    thaiwater_records = _disaster_rows_for_source(
        session,
        THAIWATER_SOURCE_ID,
        province_code,
        province_name,
        allow_missing_province=False,
    )
    if thaiwater_records:
        sources.append((THAIWATER_SOURCE_ID, thaiwater_records))
    return sources


def _catalog_with_disaster_counts() -> dict:
    catalog = deepcopy(public_catalog())
    counts = _disaster_counts_by_province()
    for province in catalog.get("provinces", []):
        province_counts = counts.get(province.get("province_code"), {})
        province["disaster_source_count"] = int(
            province_counts.get("disaster_source_count", province.get("disaster_source_count", 0))
            or 0
        )
        province["disaster_record_count"] = int(
            province_counts.get("disaster_record_count", province.get("disaster_record_count", 0))
            or 0
        )
        province["disaster_sources"] = list(
            province_counts.get("disaster_sources", province.get("disaster_sources", []))
            or []
        )
    return catalog


def _province_boundaries_with_disaster_counts() -> dict:
    boundaries = deepcopy(province_boundaries())
    counts = _disaster_counts_by_province()
    for feature in boundaries.get("features", []):
        props = feature.setdefault("properties", {})
        code = props.get("province_code") or str(props.get("PROV_CODE", "")).zfill(2)
        province_counts = counts.get(code, {})
        props["disaster_source_count"] = int(
            province_counts.get("disaster_source_count", props.get("disaster_source_count", 0))
            or 0
        )
        props["disaster_record_count"] = int(
            province_counts.get("disaster_record_count", props.get("disaster_record_count", 0))
            or 0
        )
        props["disaster_sources"] = list(
            province_counts.get("disaster_sources", props.get("disaster_sources", []))
            or []
        )
    return boundaries


@asynccontextmanager
async def lifespan(_: FastAPI):
    _preflight_publication_release()
    init_db()
    _sync_serving_database()
    yield


app = FastAPI(
    title="AIAT Provincial Evidence Map API",
    description="Public candidate-data projection for province-level evidence exploration.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "app" / "static"), name="static")


@app.api_route(
    "/downloads/{asset_path:path}",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def reviewed_public_download(asset_path: str):
    """Serve only files explicitly marked downloadable by a reviewed contract."""

    try:
        allowed = downloadable_public_files(PROJECT_ROOT, PUBLICATION_CONTRACTS_ROOT)
    except PublicationError as exc:
        raise HTTPException(status_code=503, detail="publication contract unavailable") from exc
    path = allowed.get(asset_path.replace("\\", "/"))
    if path is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(path)


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


@app.get("/insights", response_class=HTMLResponse)
def insights_dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="insights.html",
        context={"app_name": settings.app_name, "app_env": settings.app_env},
    )


@app.get("/province/{province_code}", response_class=HTMLResponse)
def province_detail_dashboard(request: Request, province_code: str):
    code = province_code.strip().zfill(2)
    province = next(
        (row for row in public_catalog()["provinces"] if row["province_code"] == code),
        None,
    )
    if province is None:
        raise HTTPException(status_code=404, detail="ไม่พบรหัสจังหวัด")
    return templates.TemplateResponse(
        request=request,
        name="province.html",
        context={
            "app_name": settings.app_name,
            "province": province,
        },
    )


@app.get("/health", response_model=HealthResponse)
def health():
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
            contract = _serving_contract_snapshot(session)
    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "database_backend": engine.dialect.name,
                "public_artifacts": 0,
                "public_artifacts_expected": EXPECTED_PUBLIC_ARTIFACTS,
                "source_catalog_rows": 0,
                "public_value_sources": 0,
                "metadata_only_sources": 0,
                "restricted_local_only_sources": 0,
                "spatial_features": 0,
                "spatial_features_expected": EXPECTED_SPATIAL_FEATURES,
                "spatial_complete": False,
                "housing_demand_records": 0,
                "housing_demand_records_expected": EXPECTED_DEMAND_RECORDS,
                "housing_demand_complete": False,
                "published_catalog_ids_match_approved": False,
                "restricted_values_published": 0,
                "app_env": settings.app_env,
            },
        )
    payload = {
        "status": "ok" if contract["complete"] else "unhealthy",
        "database": "connected",
        "database_backend": engine.dialect.name,
        "public_artifacts": contract["artifact_total"],
        "public_artifacts_expected": EXPECTED_PUBLIC_ARTIFACTS,
        "source_catalog_rows": contract["source_total"],
        "public_value_sources": contract["approved_total"],
        "metadata_only_sources": contract["metadata_only_total"],
        "restricted_local_only_sources": contract["restricted_source_total"],
        "spatial_features": contract["spatial"]["feature_total"],
        "spatial_features_expected": contract["spatial"]["expected_total"],
        "spatial_complete": contract["spatial"]["complete"],
        "housing_demand_records": contract["housing_demand"]["count"],
        "housing_demand_records_expected": contract["housing_demand"]["expected"],
        "housing_demand_complete": contract["housing_demand"]["complete"],
        "published_catalog_ids_match_approved": contract[
            "published_catalog_ids_match_approved"
        ],
        "restricted_values_published": contract["disallowed_operational_records"],
        "app_env": settings.app_env,
    }
    return JSONResponse(
        status_code=200 if contract["complete"] else 503,
        content=payload,
    )


@app.get(
    "/api/public/v1/catalog",
    tags=["Public data"],
    response_model=PublicCatalogResponse,
)
def public_data_catalog():
    """Return the complete approved public projection and its semantic labels."""
    return _catalog_with_disaster_counts()


@app.get(
    "/api/public/v1/artifacts",
    tags=["Public data"],
    response_model=list[dict],
)
def public_artifact_index():
    """List every reviewed artifact declared by the current serving manifest."""
    with SessionLocal() as session:
        artifacts = session.execute(
            select(
                PublicArtifact.artifact_key,
                PublicArtifact.artifact_group,
                PublicArtifact.province_code,
                PublicArtifact.item_count,
                PublicArtifact.content_hash,
                PublicArtifact.source_path,
                PublicArtifact.updated_at,
            ).order_by(
                PublicArtifact.artifact_group,
                PublicArtifact.artifact_key,
            )
        ).all()
        return [
            {
                "artifact_key": artifact.artifact_key,
                "artifact_group": artifact.artifact_group,
                "province_code": artifact.province_code,
                "item_count": artifact.item_count,
                "content_hash": artifact.content_hash,
                "source_path": artifact.source_path,
                "updated_at": artifact.updated_at.isoformat(),
            }
            for artifact in artifacts
        ]


@app.get(
    "/api/public/v1/artifacts/{artifact_key:path}",
    tags=["Public data"],
    response_model=dict,
)
def public_artifact_by_key(artifact_key: str):
    """Return one reviewed JSON object without adding source-specific API code."""
    with SessionLocal() as session:
        artifact = session.get(PublicArtifact, artifact_key)
        if artifact is None:
            raise HTTPException(status_code=404, detail="ไม่พบ public artifact")
        return artifact.payload


@app.get(
    "/api/public/v1/overview",
    tags=["Public data"],
    response_model=PublicOverviewResponse,
)
def public_data_overview():
    catalog = public_catalog()
    return {
        "schema_version": catalog["schema_version"],
        "generated_at": catalog["generated_at"],
        "publication_status": catalog["publication_status"],
        "warning_th": catalog["warning_th"],
        "summary": catalog["summary"],
        "themes": catalog["themes"],
        "metrics": catalog["metrics"],
        "methodology": catalog["methodology"],
    }


@app.get(
    "/api/public/v1/source-insights",
    tags=["Public data"],
    response_model=SourceInsightsResponse,
)
def public_source_insights():
    """Return cleaned source dashboards and audited geography links."""
    return source_insights()


@app.get(
    "/api/public/v1/source-coverage",
    tags=["Public data"],
    response_model=SourceCoverageResponse,
)
def public_source_coverage():
    """Return audit/dashboard coverage for every registered source."""
    return source_coverage()


@app.get(
    "/api/public/v1/unmapped-records",
    tags=["Public data"],
    response_model=UnmappedRecordsResponse,
)
def public_unmapped_records():
    """Return public records intentionally kept outside the province map."""
    return unmapped_records()


@app.get(
    "/api/public/v1/learning-dashboard",
    tags=["Public data"],
    response_model=LearningDashboardResponse,
)
def public_learning_dashboard():
    """Return the cleaned Source 10 aggregate and its explicit scope caveat."""
    return learning_dashboard()


@app.get(
    "/api/public/v1/housing-spatial/summary",
    tags=["Public data"],
    response_model=HousingSpatialSummaryResponse,
)
def public_housing_spatial_summary():
    """Return executive-safe counts and distributions for public spatial layers."""
    return housing_spatial_summary()


@app.get(
    "/api/public/v1/housing-demand/summary",
    tags=["Public data"],
    response_model=HousingDemandSummaryResponse,
)
def public_housing_demand_summary():
    """Return the privacy-projected national and provincial demand aggregates."""
    return housing_demand_summary()


@app.get(
    "/api/public/v1/housing-spatial/features",
    tags=["Public data"],
    response_model=HousingSpatialFeatureCollectionResponse,
)
def public_housing_spatial_features(
    layer_id: str = Query(...),
    adm3_pcode: str | None = Query(default=None, max_length=20),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    limit: int = Query(default=200, ge=1, le=500),
):
    """Query privacy-projected features by layer, subdistrict or bounding box."""
    if layer_id not in REQUIRED_SPATIAL_COUNTS:
        raise HTTPException(status_code=422, detail="unsupported spatial layer")
    bbox_values = (min_lon, min_lat, max_lon, max_lat)
    if any(value is not None for value in bbox_values) and not all(
        value is not None for value in bbox_values
    ):
        raise HTTPException(status_code=422, detail="bbox requires all four coordinates")
    if all(value is not None for value in bbox_values):
        assert min_lon is not None and min_lat is not None
        assert max_lon is not None and max_lat is not None
        if min_lon > max_lon or min_lat > max_lat:
            raise HTTPException(status_code=422, detail="invalid bbox ordering")

    with SessionLocal() as session:
        conditions = [SpatialFeature.layer_id == layer_id]
        if adm3_pcode:
            conditions.append(SpatialFeature.adm3_pcode == adm3_pcode)
        if all(value is not None for value in bbox_values):
            conditions.extend([
                SpatialFeature.max_lon >= min_lon,
                SpatialFeature.min_lon <= max_lon,
                SpatialFeature.max_lat >= min_lat,
                SpatialFeature.min_lat <= max_lat,
            ])
        rows = list(session.scalars(
            select(SpatialFeature)
            .where(*conditions)
            .order_by(SpatialFeature.feature_id)
            .limit(limit)
        ))
        total = session.scalar(
            select(func.count())
            .select_from(SpatialFeature)
            .where(*conditions)
        ) or 0
    features = [
        {
            "type": "Feature",
            "geometry": json.loads(row.geometry_json),
            "properties": {
                "feature_id": row.feature_id,
                **row.properties,
                "quality_status": row.quality_status,
            },
        }
        for row in rows
    ]
    return {
        "type": "FeatureCollection",
        "layer_id": layer_id,
        "total_in_layer": total,
        "returned": len(features),
        "quality_status": "needs_review",
        "features": features,
    }


@app.get(
    "/api/public/v1/database-coverage",
    tags=["Public data"],
    response_model=DatabaseCoverageResponse,
)
def public_database_coverage():
    """Prove which cleaned public artifacts are synchronized to the serving DB."""
    with SessionLocal() as session:
        contract = _serving_contract_snapshot(session)
    artifact_counts = contract["artifact_counts"]
    province_briefings = artifact_counts.get("provincial_briefing", 0)
    executive_summaries = artifact_counts.get("executive_summary", 0)
    return {
        "status": "complete" if contract["complete"] else "incomplete",
        "database_backend": engine.dialect.name,
        "serving_mode": "database_seeded_from_validated_public_artifacts",
        "source_catalog_rows": contract["source_total"],
        "endpoint_catalog_rows": contract["endpoint_total"],
        "runtime_enabled_endpoints": contract["runtime_endpoint_total"],
        "public_value_sources": contract["approved_total"],
        "public_policy_sources": contract["public_policy_total"],
        "metadata_only_sources": contract["metadata_only_total"],
        "restricted_local_only_sources": contract["restricted_source_total"],
        "published_catalog_source_count": contract["published_catalog_source_count"],
        "published_catalog_ids_match_approved": contract[
            "published_catalog_ids_match_approved"
        ],
        "restricted_catalog_sources_published": contract[
            "restricted_catalog_sources_published"
        ],
        "public_artifacts_in_database": contract["artifact_total"],
        "public_artifacts_expected": EXPECTED_PUBLIC_ARTIFACTS,
        "artifact_groups": artifact_counts,
        "province_briefings": province_briefings,
        "executive_summaries": executive_summaries,
        "spatial_features_in_database": contract["spatial"]["feature_total"],
        "spatial_features_expected": contract["spatial"]["expected_total"],
        "spatial_layer_counts": contract["spatial"]["counts"],
        "spatial_complete": contract["spatial"]["complete"],
        "housing_demand_records_in_database": contract["housing_demand"]["count"],
        "housing_demand_records_expected": contract["housing_demand"]["expected"],
        "housing_demand_complete": contract["housing_demand"]["complete"],
        "restricted_values_published": contract["disallowed_operational_records"],
        "operational_candidate_records": contract["approved_operational_records"],
        "raw_data_storage": "immutable_evidence_outside_serving_database",
    }


@app.get(
    "/api/public/v1/operations",
    tags=["Public data"],
    response_model=OperationsResponse,
)
def public_operations():
    """Explain connector coverage, refresh cadence, and publication gates."""
    return operations_status()


@app.get(
    "/api/public/v1/sources",
    tags=["Public data"],
    response_model=list[PublicSourceResponse],
)
def public_data_sources():
    return public_catalog()["sources"]


@app.get(
    "/api/public/v1/provinces",
    tags=["Public data"],
    response_model=list[ProvinceResponse],
)
def public_data_provinces(
    has_evidence: bool = Query(False, description="Return only provinces covered by at least one public metric"),
):
    provinces = _catalog_with_disaster_counts()["provinces"]
    if has_evidence:
        provinces = [row for row in provinces if row["evidence_source_count"] > 0]
    return provinces


@app.get(
    "/api/public/v1/provinces/{province_code}",
    tags=["Public data"],
    response_model=ProvinceResponse,
)
def public_data_province(province_code: str):
    code = province_code.strip().zfill(2)
    province = next(
        (row for row in _catalog_with_disaster_counts()["provinces"] if row["province_code"] == code),
        None,
    )
    if province is None:
        raise HTTPException(status_code=404, detail="ไม่พบรหัสจังหวัด")
    return province


@app.get(
    "/api/public/v1/provinces/{province_code}/briefing",
    tags=["Public data"],
    response_model=ProvincialBriefingResponse,
)
def public_data_provincial_briefing(province_code: str):
    """Return actual source values and complete province-scoped public projections."""
    try:
        return provincial_briefing(province_code)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลสรุปรายจังหวัด") from error


@app.get(
    "/api/public/v1/provinces/{province_code}/summary",
    tags=["Public data"],
    response_model=ExecutiveSummaryResponse,
)
def public_data_executive_summary(province_code: str):
    """Return a compact, cleaned and benchmarked province-level executive view."""
    try:
        return executive_summary(province_code)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลสรุปรายมิติของจังหวัด") from error


@app.get(
    "/api/public/v1/map/provinces",
    tags=["Public data"],
    response_model=ProvinceFeatureCollectionResponse,
)
def public_map_provinces():
    return _province_boundaries_with_disaster_counts()


@app.get(
    "/api/public/v1/map/cultural-points",
    tags=["Public data"],
    response_model=CulturalPointFeatureCollectionResponse,
)
def public_map_cultural_points():
    return cultural_points()


@app.get(
    "/api/summary",
    dependencies=[Depends(_require_local_debug_api)],
    include_in_schema=_debug_api_enabled(),
)
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
        public_artifacts = session.scalar(select(func.count()).select_from(PublicArtifact)) or 0
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
            "public_serving_artifacts": public_artifacts,
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


@app.get(
    "/api/sources",
    dependencies=[Depends(_require_local_debug_api)],
    include_in_schema=_debug_api_enabled(),
)
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


@app.get(
    "/api/connectivity",
    dependencies=[Depends(_require_local_debug_api)],
    include_in_schema=_debug_api_enabled(),
)
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
                "deployable": bool(source.get("production_values_allowed")),
                "candidate_only": source["readiness_status"] == "needs_review",
            }
        )
    return result


@app.get(
    "/api/sources/{source_id}/endpoints",
    dependencies=[Depends(_require_local_debug_api)],
    include_in_schema=_debug_api_enabled(),
)
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


@app.get(
    "/api/runs",
    dependencies=[Depends(_require_local_debug_api)],
    include_in_schema=_debug_api_enabled(),
)
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


@app.get(
    "/api/records",
    dependencies=[Depends(_require_local_debug_api)],
    include_in_schema=_debug_api_enabled(),
)
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
        query = (
            select(DashboardRecord)
            .join(Source, DashboardRecord.source_id == Source.source_id)
            .where(Source.production_values_allowed.is_(True))
            .order_by(desc(DashboardRecord.id))
            .limit(limit)
        )
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

# --- SPU disaster tracking ---


def _safe_disaster_value(payload: dict, keys: tuple[str, ...]):
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_disaster_text(value) -> str:
    return "".join(str(value or "").lower().replace("จังหวัด", "").split())


def _disaster_record_matches_province(
    record: DashboardRecord,
    province_code: str,
    province_name: str,
    *,
    allow_missing_province: bool = True,
) -> bool:
    payload = record.payload if isinstance(record.payload, dict) else {}
    province_value = _safe_disaster_value(
        payload,
        ("province_th", "province_name_th", "province", "province_name"),
    )
    if province_value is None:
        return allow_missing_province
    normalized_value = _normalize_disaster_text(province_value)
    normalized_name = _normalize_disaster_text(province_name)
    if normalized_value == normalized_name or normalized_name in normalized_value:
        return True
    romanized = {"53": "uttaradit", "60": "nakhonsawan", "64": "sukhothai"}
    return bool(romanized.get(province_code) and romanized[province_code] in normalized_value)


def _disaster_observed_at(record: DashboardRecord) -> str | None:
    payload = record.payload if isinstance(record.payload, dict) else {}
    value = _safe_disaster_value(
        payload,
        (
            "waterlevel_datetime",
            "rainfall_datetime",
            "dam_date",
            "measured_at",
            "updated_at",
            "timestamp",
            "fetched_at",
            "_fetched_at",
        ),
    )
    if value is not None:
        return str(value)
    if record.as_of:
        return str(record.as_of)
    if record.fetched_at:
        return record.fetched_at.isoformat()
    return None


def _disaster_preview(record: DashboardRecord) -> dict:
    payload = record.payload if isinstance(record.payload, dict) else {}
    observed_at = _disaster_observed_at(record)
    preview = {
        "dataset_key": record.dataset_key,
        "label": _safe_disaster_value(
            payload,
            (
                "station_name_th",
                "station_name_en",
                "name_th",
                "name_en",
                "name",
                "dam_name_th",
                "dam_name_en",
                "station_name",
                "station_code",
                "old_code",
                "id",
            ),
        ),
        "district": _safe_disaster_value(
            payload, ("amphoe_th", "district", "district_th", "tumbon_th", "subdistrict")
        ),
        "observed_at": observed_at,
        "water_level": _safe_disaster_value(
            payload,
            ("waterlevel_msl", "water_level_msl", "waterlevel_m", "water_level", "dam_storage_percent"),
        ),
        "rainfall": _safe_disaster_value(payload, ("rain_24h", "avg_rain_mm", "max_rain_mm")),
        "status": _safe_disaster_value(
            payload,
            (
                "situation_text",
                "situation_level",
                "diff_wl_bank_text",
                "diff_from_bank_text",
                "type",
                "category",
                "title",
            ),
        ),
        "source_url": _safe_disaster_value(payload, ("source_url", "_source_url", "station_url")),
        "quality_status": record.quality_status,
    }
    return {key: value for key, value in preview.items() if value not in (None, "")}


def _disaster_float(value) -> float | None:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number


def _disaster_counter(items, limit: int = 6) -> list[dict]:
    counts = {}
    for item in items:
        if item in (None, ""):
            continue
        label = str(item)
        counts[label] = counts.get(label, 0) + 1
    return [
        {"label": label, "value": value}
        for label, value in sorted(counts.items(), key=lambda row: (-row[1], row[0]))[:limit]
    ]


def _disaster_dataset_label(dataset_key: str) -> str:
    labels = {
        "announcements.row": "ประกาศ",
        "incident_map.row": "เหตุการณ์บนแผนที่",
        "incidents.row": "รายงานเหตุการณ์",
        "water_levels.row": "ระดับน้ำ",
        "rain_24h.row": "ฝน 24 ชม.",
        "stations.row": "สถานีตรวจวัด",
        "shelters.row": "ศูนย์พักพิง",
        "rain_analysis.row": "เรดาร์ฝน",
    }
    return labels.get(dataset_key, dataset_key.replace("_", " "))


def _disaster_station_identity(payload: dict) -> str | None:
    station_code = _safe_disaster_value(payload, ("station_code", "old_code"))
    if station_code not in (None, ""):
        text_value = str(station_code)
        for prefix in ("ridhydro_", "telewater_", "hydro_"):
            if text_value.startswith(prefix):
                text_value = text_value[len(prefix):]
        return text_value
    value = _safe_disaster_value(
        payload,
        ("station_id", "id", "station_name_th", "station_name_en"),
    )
    return str(value) if value not in (None, "") else None


def _disaster_grouped_trends(
    records: list[DashboardRecord],
    *,
    dataset_key: str,
    value_keys: tuple[str, ...],
    time_keys: tuple[str, ...],
    station_keys: tuple[str, ...],
    station_id_keys: tuple[str, ...],
    metric: str,
) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    station_ids: dict[str, str] = {}
    station_labels: dict[str, str] = {}
    for record in records:
        if record.dataset_key != dataset_key:
            continue
        payload = record.payload if isinstance(record.payload, dict) else {}
        value = _disaster_float(_safe_disaster_value(payload, value_keys))
        timestamp = _safe_disaster_value(payload, time_keys) or _disaster_observed_at(record)
        label = _safe_disaster_value(payload, station_keys)
        if value is None or timestamp is None or label is None:
            continue
        group_key = _disaster_station_identity(payload) or str(_safe_disaster_value(payload, station_id_keys) or label)
        grouped.setdefault(group_key, []).append({"t": str(timestamp), "v": value})
        station_ids[group_key] = group_key
        station_labels[group_key] = str(label)
    series = []
    latest_points = []
    for group_key, points in grouped.items():
        points.sort(key=lambda point: point["t"])
        latest = points[-1]["v"]
        item = {
            "station_id": station_ids[group_key],
            "label": station_labels.get(group_key, group_key),
            "metric": metric,
            "latest": latest,
            "points": points[-12:],
        }
        if len(points) >= 2:
            series.append(item)
        else:
            latest_points.append(item)
    return {
        "series": sorted(series, key=lambda row: row["latest"], reverse=True),
        "latest_points": sorted(latest_points, key=lambda row: row["latest"], reverse=True),
    }


def _nsn_station_summary(record: DashboardRecord) -> dict:
    payload = record.payload if isinstance(record.payload, dict) else {}
    link_text = str(payload.get("link_text") or "")
    water_level = None
    water_percent = None
    bank_level = None
    status = None
    level_match = re.search(r"([0-9][0-9,.]*)ม\.รทก\.ปริมาณน้ำ([0-9][0-9,.]*)%", link_text)
    if level_match:
        water_level = _disaster_float(level_match.group(1))
        water_percent = _disaster_float(level_match.group(2))
    bank_match = re.search(r"ตลิ่ง([0-9][0-9,.]*)ม\.รทก\.", link_text)
    if bank_match:
        bank_level = _disaster_float(bank_match.group(1))
    for marker in ("วิกฤต", "เตือนภัย", "เฝ้าระวัง", "ปกติ", "ต่ำกว่าตลิ่ง"):
        if marker in link_text:
            status = marker
            break
    return {
        "station": payload.get("station_name") or payload.get("station_code"),
        "water_level": water_level,
        "water_percent": water_percent,
        "bank_level": bank_level,
        "status": status,
        "source_url": payload.get("station_url"),
    }


def _disaster_source_insights(source_id: str, records: list[DashboardRecord]) -> dict:
    dataset_counts = _disaster_counter([record.dataset_key for record in records], 10)
    pairs = [
        (record, record.payload)
        for record in records
        if isinstance(record.payload, dict)
    ]
    if source_id == "spu_sukhothai_care":
        incidents = [
            payload
            for record, payload in pairs
            if record.dataset_key in {"incidents.row", "incident_map.row"}
        ]
        announcements = [
            payload
            for record, payload in pairs
            if record.dataset_key == "announcements.row"
        ]
        return {
            "kind": "incident_feed",
            "dataset_counts": dataset_counts,
            "status_counts": _disaster_counter([item.get("type") or item.get("status") for item in incidents]),
            "priority_counts": _disaster_counter([item.get("priority") for item in announcements]),
            "highlights": [
                {
                    "title": item.get("title"),
                    "status": item.get("priority"),
                    "observed_at": item.get("createdAt") or item.get("updatedAt"),
                }
                for item in announcements[:4]
                if item.get("title")
            ],
        }
    if source_id == "spu_sukhothai_water":
        water_trends = _disaster_grouped_trends(
            records,
            dataset_key="water_levels.row",
            value_keys=("waterlevel_msl", "waterlevel_m"),
            time_keys=("waterlevel_datetime", "fetched_at"),
            station_keys=("station_name_th", "station_name_en", "station_code"),
            station_id_keys=("station_id", "station_code", "id"),
            metric="water",
        )
        rain_trends = _disaster_grouped_trends(
            records,
            dataset_key="rain_24h.row",
            value_keys=("rain_24h", "rain_1h"),
            time_keys=("rainfall_datetime", "fetched_at"),
            station_keys=("station_name_th", "station_name_en", "station_code"),
            station_id_keys=("station_id", "station_code", "id"),
            metric="rain",
        )
        water_values = [
            _disaster_float(payload.get("waterlevel_msl"))
            for record, payload in pairs
            if record.dataset_key == "water_levels.row"
        ]
        rain_values = [
            _disaster_float(payload.get("rain_24h"))
            for record, payload in pairs
            if record.dataset_key == "rain_24h.row"
        ]
        dam_values = [
            _disaster_float(payload.get("dam_storage_percent"))
            for record, payload in pairs
            if record.dataset_key.startswith("dams.")
        ]
        water_values = [value for value in water_values if value is not None]
        rain_values = [value for value in rain_values if value is not None]
        dam_values = [value for value in dam_values if value is not None]
        return {
            "kind": "water_metrics",
            "dataset_counts": dataset_counts,
            "metrics": [
                {"label": "สถานีระดับน้ำ", "value": sum(1 for record in records if record.dataset_key == "water_levels.row"), "unit": "สถานี"},
                {"label": "ฝนสูงสุด 24 ชม.", "value": max(rain_values) if rain_values else None, "unit": "มม."},
                {"label": "ระดับน้ำสูงสุด", "value": max(water_values) if water_values else None, "unit": "ม.รทก."},
                {"label": "ความจุเขื่อนสูงสุด", "value": max(dam_values) if dam_values else None, "unit": "%"},
            ],
            "trends": [
                {
                    "title": "ระดับน้ำรายสถานี",
                    "unit": "ม.รทก.",
                    "series": water_trends["series"],
                    "latest_points": water_trends["latest_points"],
                },
                {
                    "title": "ฝน 24 ชม. รายสถานี",
                    "unit": "มม.",
                    "series": rain_trends["series"],
                    "latest_points": rain_trends["latest_points"],
                },
            ],
        }
    if source_id == "spu_nsn_flood":
        stations = [_nsn_station_summary(record) for record in records]
        return {
            "kind": "station_status",
            "dataset_counts": dataset_counts,
            "status_counts": _disaster_counter([item.get("status") for item in stations]),
            "stations": stations,
        }
    if source_id == "spu_rawangphai_uru":
        rawang_rain_trends = _disaster_grouped_trends(
            records,
            dataset_key="rain_analysis.row",
            value_keys=("max_rain_mm", "avg_rain_mm"),
            time_keys=("timestamp", "fetched_at"),
            station_keys=("point_no", "id_utm", "province"),
            station_id_keys=("point_no", "id_utm", "id"),
            metric="rain",
        )
        rain = [
            _disaster_float(payload.get("max_rain_mm"))
            for record, payload in pairs
            if record.dataset_key == "rain_analysis.row"
        ]
        shelter_capacity = [
            _disaster_float(payload.get("capacity"))
            for record, payload in pairs
            if record.dataset_key == "shelters.row"
        ]
        rain = [value for value in rain if value is not None]
        shelter_capacity = [value for value in shelter_capacity if value is not None]
        return {
            "kind": "rain_shelter",
            "dataset_counts": dataset_counts,
            "metrics": [
                {"label": "กริดเรดาร์ฝน", "value": sum(1 for record in records if record.dataset_key == "rain_analysis.row"), "unit": "กริด"},
                {"label": "ฝนสูงสุด", "value": max(rain) if rain else None, "unit": "มม."},
                {"label": "ศูนย์พักพิง", "value": sum(1 for record in records if record.dataset_key == "shelters.row"), "unit": "แห่ง"},
                {"label": "รองรับรวม", "value": sum(shelter_capacity) if shelter_capacity else None, "unit": "คน"},
            ],
            "district_counts": _disaster_counter(
                [
                    payload.get("district")
                    for record, payload in pairs
                    if record.dataset_key == "shelters.row"
                ]
            ),
            "trends": [
                {
                    "title": "ฝนสูงสุดตามกริด",
                    "unit": "มม.",
                    "series": rawang_rain_trends["series"],
                    "latest_points": rawang_rain_trends["latest_points"],
                }
            ],
        }
    return {"kind": "records", "dataset_counts": dataset_counts}


def _latest_text(values: list[str | None]) -> str | None:
    clean = [str(value) for value in values if value]
    return max(clean) if clean else None


def _disaster_rows_for_source(
    session,
    source_id: str,
    province_code: str | None = None,
    province_name: str | None = None,
    *,
    allow_missing_province: bool = True,
) -> list[DashboardRecord]:
    rows = list(
        session.scalars(
            select(DashboardRecord)
            .where(DashboardRecord.source_id == source_id)
            .order_by(desc(DashboardRecord.fetched_at), desc(DashboardRecord.id))
        ).all()
    )
    if province_code and province_name:
        rows = [
            record
            for record in rows
            if _disaster_record_matches_province(
                record,
                province_code,
                province_name,
                allow_missing_province=allow_missing_province,
            )
        ]
    return rows


def _disaster_preview_rows(records: list[DashboardRecord], limit: int = 12) -> list[DashboardRecord]:
    return records[:limit]


def _disaster_source_summary(
    source_id: str,
    records: list[DashboardRecord],
    total_count: int,
) -> dict | None:
    if not total_count:
        return None
    dataset_keys = sorted({record.dataset_key for record in records})
    latest_observed_at = _latest_text([_disaster_observed_at(record) for record in records])
    latest_fetched_at = _latest_text(
        [record.fetched_at.isoformat() if record.fetched_at else None for record in records]
    )
    return {
        "source_id": source_id,
        "name_th": SPU_DISASTER_SOURCE_NAMES.get(source_id, source_id),
        "count": total_count,
        "dataset_keys": dataset_keys,
        "latest_observed_at": latest_observed_at,
        "latest_fetched_at": latest_fetched_at,
        "quality_label_th": "ข้อมูล candidate · ยังไม่ใช่สถานการณ์ภัยที่รับรอง",
        "insights": _disaster_source_insights(source_id, records),
        "records": [_disaster_preview(record) for record in _disaster_preview_rows(records)],
    }


def _parse_disaster_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    text_value = str(value).strip().replace("Z", "+00:00")
    for candidate in (text_value, text_value.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _station_history_bucket(timestamp: datetime, grain: str) -> str:
    local_time = timestamp.astimezone(timezone.utc)
    if grain == "weekly":
        year, week, _ = local_time.isocalendar()
        return f"{year}-W{week:02d}"
    if grain == "monthly":
        return local_time.strftime("%Y-%m")
    return local_time.date().isoformat()


def _station_history_points(records: list[DashboardRecord], metric: str, grain: str) -> list[dict]:
    value_keys = {
        "water": ("waterlevel_msl", "waterlevel_m"),
        "rain": ("rain_24h", "rain_1h"),
    }[metric]
    time_keys = {
        "water": ("waterlevel_datetime", "fetched_at"),
        "rain": ("rainfall_datetime", "fetched_at"),
    }[metric]
    grouped: dict[str, list[float]] = {}
    bucket_times: dict[str, datetime] = {}
    for record in records:
        payload = record.payload if isinstance(record.payload, dict) else {}
        value = _disaster_float(_safe_disaster_value(payload, value_keys))
        timestamp = _parse_disaster_datetime(
            _safe_disaster_value(payload, time_keys) or _disaster_observed_at(record)
        )
        if value is None or timestamp is None:
            continue
        bucket = _station_history_bucket(timestamp, grain)
        grouped.setdefault(bucket, []).append(value)
        bucket_times[bucket] = min(bucket_times.get(bucket, timestamp), timestamp)

    points = []
    for bucket, values in grouped.items():
        if metric == "rain" and grain in {"weekly", "monthly"}:
            value = sum(values)
        elif metric == "rain" and grain == "daily":
            value = max(values)
        else:
            value = sum(values) / len(values)
        points.append({"t": bucket, "v": round(value, 3), "samples": len(values)})
    return sorted(points, key=lambda point: bucket_times[point["t"]])


def _station_history_record_matches(record: DashboardRecord, station_id: str, metric: str) -> bool:
    payload = record.payload if isinstance(record.payload, dict) else {}
    return (_disaster_station_identity(payload) or "") == station_id


@app.get(
    "/api/public/v1/provinces/{province_code}/disaster-tracking",
    tags=["SPU disaster tracking"],
    response_model=DisasterTrackingResponse,
)
def public_data_disaster_tracking(province_code: str):
    """Return normalized SPU flood/disaster monitoring summaries for a province."""
    code = province_code.strip().zfill(2)
    province_name = _disaster_province_name(code)
    if not province_name:
        return {
            "province_code": code,
            "province_name": "",
            "source_count": 0,
            "record_count": 0,
            "latest_observed_at": None,
            "quality_label_th": "ข้อมูล candidate · ยังไม่ใช่สถานการณ์ภัยที่รับรอง",
            "sources": {},
        }

    with SessionLocal() as session:
        result: dict = {
            "province_code": code,
            "province_name": province_name,
            "source_count": 0,
            "record_count": 0,
            "latest_observed_at": None,
            "quality_label_th": "ข้อมูล candidate · ยังไม่ใช่สถานการณ์ภัยที่รับรอง",
            "sources": {},
        }

        latest_values = []
        for source_id, records in _disaster_sources_for_province(session, code, province_name):
            summary = _disaster_source_summary(
                source_id,
                records,
                len(records),
            )
            if summary:
                result["sources"][source_id] = summary
                result["record_count"] += summary["count"]
                latest_values.append(summary["latest_observed_at"])

        result["source_count"] = len(result["sources"])
        result["latest_observed_at"] = _latest_text(latest_values)
        return result


@app.get(
    "/api/public/v1/provinces/{province_code}/disaster-stations/{station_id}/history",
    tags=["SPU disaster tracking"],
    response_model=DisasterStationHistoryResponse,
)
def public_disaster_station_history(
    province_code: str,
    station_id: str,
    metric: str = Query("water", pattern="^(water|rain)$"),
    grain: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    days: int = Query(90, ge=30, le=365),
):
    """Return normalized station history for expanded disaster charts."""
    code = province_code.strip().zfill(2)
    province_name = _disaster_province_name(code)
    metric_name = "rain" if metric == "rain" else "water"
    grain_name = grain if grain in {"daily", "weekly", "monthly"} else "daily"
    bounded_days = min(max(int(days), 30), 365)
    unit = "มม." if metric_name == "rain" else "ม.รทก."

    if not province_name:
        return {
            "province_code": code,
            "province_name": None,
            "station_id": station_id,
            "station_name": None,
            "metric": metric_name,
            "grain": grain_name,
            "days": bounded_days,
            "window_start": None,
            "window_end": None,
            "unit": unit,
            "history_status": "unavailable",
            "quality_label_th": "ข้อมูล candidate · ยังไม่ใช่สถานการณ์ภัยที่รับรอง",
            "points": [],
        }

    dataset_key = "rain_24h.row" if metric_name == "rain" else "water_levels.row"
    time_keys = (
        ("rainfall_datetime", "fetched_at")
        if metric_name == "rain"
        else ("waterlevel_datetime", "fetched_at")
    )
    station_name = None
    with SessionLocal() as session:
        candidate_records = [
            record
            for record in _disaster_rows_for_source(
                session,
                THAIWATER_SOURCE_ID,
                code,
                province_name,
                allow_missing_province=False,
            )
            if record.dataset_key == dataset_key
            and _station_history_record_matches(record, station_id, metric_name)
        ]
        dated_records: list[tuple[DashboardRecord, datetime]] = []
        for record in candidate_records:
            payload = record.payload if isinstance(record.payload, dict) else {}
            if station_name is None:
                station_name = _safe_disaster_value(
                    payload,
                    ("station_name_th", "station_name_en", "station_code", "id"),
                )
            timestamp = _parse_disaster_datetime(
                _safe_disaster_value(payload, time_keys) or _disaster_observed_at(record)
            )
            if timestamp is not None:
                dated_records.append((record, timestamp))

        if dated_records:
            latest = max(timestamp for _, timestamp in dated_records)
            window_start_dt = latest - timedelta(days=bounded_days)
            window_records = [
                record
                for record, timestamp in dated_records
                if timestamp >= window_start_dt
            ]
            points = _station_history_points(window_records, metric_name, grain_name)
            has_history_dataset = any(
                "history" in record.dataset_key or "runoff" in record.dataset_key.lower()
                for record in window_records
            )
            history_status = "available" if has_history_dataset else "snapshot_only"
            return {
                "province_code": code,
                "province_name": province_name,
                "station_id": station_id,
                "station_name": str(station_name or station_id),
                "metric": metric_name,
                "grain": grain_name,
                "days": bounded_days,
                "window_start": window_start_dt.date().isoformat(),
                "window_end": latest.date().isoformat(),
                "unit": unit,
                "history_status": history_status,
                "quality_label_th": "ข้อมูล candidate · ยังไม่ใช่สถานการณ์ภัยที่รับรอง",
                "points": points,
            }

    return {
        "province_code": code,
        "province_name": province_name,
        "station_id": station_id,
        "station_name": None,
        "metric": metric_name,
        "grain": grain_name,
        "days": bounded_days,
        "window_start": None,
        "window_end": None,
        "unit": unit,
        "history_status": "unavailable",
        "quality_label_th": "ข้อมูล candidate · ยังไม่ใช่สถานการณ์ภัยที่รับรอง",
        "points": [],
    }

@app.get(
    "/api/public/v1/disaster/provinces",
    tags=["SPU disaster tracking"],
    response_model=DisasterProvinceIndexResponse,
)
def public_disaster_provinces():
    """Return province codes that have SPU disaster monitoring data."""

    province_names, _ = _province_catalog_index()
    counts = _disaster_counts_by_province()
    result = {
        province_code: {
            "province_name": province_names.get(province_code, ""),
            "sources": values["disaster_sources"],
            "total_records": values["disaster_record_count"],
        }
        for province_code, values in sorted(counts.items())
        if province_code in province_names and values["disaster_record_count"] > 0
    }

    return {
        "provinces": result,
        "total_provinces": len(result),
    }

@app.get(
    "/api/public/v1/provinces/{province_code}/disaster-timeseries",
    tags=["SPU disaster tracking"],
    response_model=DisasterTimeseriesResponse,
)
def public_disaster_timeseries(province_code: str):
    """Return time-series data suitable for charting from SPU sources."""
    code = province_code.strip().zfill(2)
    province_name = _disaster_province_name(code)
    if not province_name:
        return {"province_code": code, "series": []}

    with SessionLocal() as session:
        series = []

        # Sukhothai Water - water levels time series
        thaiwater_records = _disaster_rows_for_source(
            session,
            THAIWATER_SOURCE_ID,
            code,
            province_name,
            allow_missing_province=False,
        )
        for trend in _disaster_source_insights(THAIWATER_SOURCE_ID, thaiwater_records).get("trends", []):
            for station_data in trend.get("series", []):
                station_data["unit"] = trend.get("unit")
                station_data["metric"] = trend.get("title")
                series.append(station_data)
        
        # RawangPhai - rain analysis
        if code == "53":
            records = [
                record
                for record in _disaster_rows_for_source(
                    session,
                    "spu_rawangphai_uru",
                    code,
                    province_name,
                )
                if "rain" in record.dataset_key
            ]
            
            stations = {}
            for r in records:
                p = r.payload
                station = p.get("province") or "unknown"
                ts = p.get("timestamp")
                val = p.get("avg_rain_mm")
                if ts and val is not None:
                    if station not in stations:
                        stations[station] = {"label": station, "points": []}
                    stations[station]["points"].append({
                        "t": ts,
                        "v": float(val),
                    })
            
            for station_data in stations.values():
                station_data["points"].sort(key=lambda pt: pt["t"])
                station_data["points"] = station_data["points"][-100:]
                station_data["unit"] = "มม."
                station_data["metric"] = "ปริมาณน้ำฝนเฉลี่ย"
                series.append(station_data)
        
        return {"province_code": code, "province_name": province_name, "series": series}
