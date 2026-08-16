from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
