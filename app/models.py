from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Source(Base):
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, index=True)
    name_th: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str] = mapped_column(Text)
    acquisition_mode: Mapped[str] = mapped_column(String(60))
    readiness_status: Mapped[str] = mapped_column(String(60), default="needs_review")
    cloud_policy: Mapped[str] = mapped_column(String(80))
    production_values_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_record_count: Mapped[int] = mapped_column(Integer, default=0)
    notes_th: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    endpoints: Mapped[list["Endpoint"]] = relationship(back_populates="source")
    runs: Mapped[list["IngestionRun"]] = relationship(back_populates="source")


class Endpoint(Base):
    __tablename__ = "endpoints"

    endpoint_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"), index=True)
    method: Mapped[str] = mapped_column(String(12))
    url: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(80), default="")
    access_status: Mapped[str] = mapped_column(String(80), default="")
    team_action: Mapped[str] = mapped_column(String(100), default="")
    restricted: Mapped[bool] = mapped_column(Boolean, default=True)
    runtime_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    request_template: Mapped[dict] = mapped_column(JSON, default=dict)
    notes_th: Mapped[str] = mapped_column(Text, default="")

    source: Mapped[Source] = relationship(back_populates="endpoints")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    run_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"), index=True)
    strategy: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    as_of: Mapped[str | None] = mapped_column(String(100), nullable=True)
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    records_loaded: Mapped[int] = mapped_column(Integer, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0)
    manifest_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[Source] = relationship(back_populates="runs")


class DashboardRecord(Base):
    __tablename__ = "dashboard_records"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "dataset_key",
            "source_record_id",
            "record_hash",
            name="uq_record_version",
        ),
        Index("ix_records_source_dataset", "source_id", "dataset_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"), index=True)
    dataset_key: Mapped[str] = mapped_column(String(200), index=True)
    source_record_id: Mapped[str] = mapped_column(String(200))
    record_hash: Mapped[str] = mapped_column(String(64))
    quality_status: Mapped[str] = mapped_column(String(60), default="needs_review")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    as_of: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)


class PublicArtifact(Base):
    """Versioned serving artifact used by the public dashboard and API.

    The immutable/raw evidence remains outside this table.  Only the cleaned,
    public projection committed under ``data/public`` is synchronized here.
    """

    __tablename__ = "public_artifacts"
    __table_args__ = (
        Index("ix_public_artifacts_group", "artifact_group"),
        Index("ix_public_artifacts_province", "province_code"),
    )

    artifact_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    artifact_group: Mapped[str] = mapped_column(String(60))
    province_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    source_path: Mapped[str] = mapped_column(Text)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SpatialLayerSnapshot(Base):
    """One validated, transaction-swapped snapshot per public spatial layer."""

    __tablename__ = "spatial_layer_snapshots"

    layer_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    feature_count: Mapped[int] = mapped_column(Integer)
    source_path: Mapped[str] = mapped_column(Text)
    quality_status: Mapped[str] = mapped_column(String(60), default="needs_review")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SpatialFeature(Base):
    """Privacy-projected GeoJSON feature stored without requiring PostGIS."""

    __tablename__ = "spatial_features"
    __table_args__ = (
        UniqueConstraint("layer_id", "feature_id", name="uq_spatial_layer_feature"),
        Index("ix_spatial_features_layer", "layer_id"),
        Index("ix_spatial_features_adm3", "adm3_pcode"),
        Index(
            "ix_spatial_features_layer_bbox",
            "layer_id",
            "min_lon",
            "max_lon",
            "min_lat",
            "max_lat",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"), index=True)
    layer_id: Mapped[str] = mapped_column(String(80))
    feature_id: Mapped[str] = mapped_column(String(200))
    geometry_type: Mapped[str] = mapped_column(String(40))
    adm3_pcode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    min_lon: Mapped[float] = mapped_column(Float)
    min_lat: Mapped[float] = mapped_column(Float)
    max_lon: Mapped[float] = mapped_column(Float)
    max_lat: Mapped[float] = mapped_column(Float)
    properties: Mapped[dict] = mapped_column(JSON)
    geometry_json: Mapped[str] = mapped_column(Text)
    evidence_path: Mapped[str] = mapped_column(Text)
    evidence_sha256: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    as_of: Mapped[str] = mapped_column(String(100), default="ไม่ระบุ")
    quality_status: Mapped[str] = mapped_column(String(60), default="needs_review")
