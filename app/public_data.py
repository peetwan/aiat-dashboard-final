from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.public_artifacts import artifact_payload
from app.settings import PROJECT_ROOT


PUBLIC_DATA_ROOT = PROJECT_ROOT / "data" / "public"


@lru_cache(maxsize=8)
def load_public_file(filename: str) -> dict[str, Any]:
    path = (PUBLIC_DATA_ROOT / filename).resolve()
    if path.parent != PUBLIC_DATA_ROOT.resolve() or not path.exists():
        raise FileNotFoundError(filename)
    return json.loads(path.read_text(encoding="utf-8"))


def load_public_artifact(artifact_key: str, fallback_filename: str) -> dict[str, Any]:
    """Read from the serving database, with a startup-safe file fallback."""

    try:
        with SessionLocal() as session:
            payload = artifact_payload(session, artifact_key)
        if payload is not None:
            return payload
    except SQLAlchemyError:
        # The fallback keeps CLI builders/import-time checks usable before init_db.
        pass
    return load_public_file(fallback_filename)


def public_catalog() -> dict[str, Any]:
    return load_public_artifact("catalog", "public_dashboard.json")


def province_boundaries() -> dict[str, Any]:
    return load_public_artifact("map/provinces", "thailand_provinces.geojson")


def cultural_points() -> dict[str, Any]:
    return load_public_artifact("map/cultural-points", "cultural_points.geojson")


def source_insights() -> dict[str, Any]:
    return load_public_artifact("source-insights", "source_insights.json")


def source_coverage() -> dict[str, Any]:
    return load_public_artifact("source-coverage", "source_coverage.json")


def unmapped_records() -> dict[str, Any]:
    return load_public_artifact("unmapped-records", "unmapped_records.json")


def learning_dashboard() -> dict[str, Any]:
    return load_public_artifact("learning-dashboard", "learning_dashboard.json")


@lru_cache(maxsize=77)
def provincial_briefing(province_code: str) -> dict[str, Any]:
    code = province_code.strip().zfill(2)
    try:
        with SessionLocal() as session:
            payload = artifact_payload(session, f"province/{code}/briefing")
        if payload is not None:
            return payload
    except SQLAlchemyError:
        pass
    path = (PUBLIC_DATA_ROOT / "provincial_briefings" / f"{code}.json").resolve()
    briefing_root = (PUBLIC_DATA_ROOT / "provincial_briefings").resolve()
    if path.parent != briefing_root or not path.exists():
        raise FileNotFoundError(code)
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=77)
def executive_summary(province_code: str) -> dict[str, Any]:
    code = province_code.strip().zfill(2)
    try:
        with SessionLocal() as session:
            payload = artifact_payload(session, f"province/{code}/summary")
        if payload is not None:
            return payload
    except SQLAlchemyError:
        pass
    path = (PUBLIC_DATA_ROOT / "executive_summaries" / f"{code}.json").resolve()
    summary_root = (PUBLIC_DATA_ROOT / "executive_summaries").resolve()
    if path.parent != summary_root or not path.exists():
        raise FileNotFoundError(code)
    return json.loads(path.read_text(encoding="utf-8"))
