from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Endpoint, Source
from app.settings import PROJECT_ROOT


CATALOG_PATH = PROJECT_ROOT / "config" / "source_catalog.json"
PLANS_PATH = PROJECT_ROOT / "config" / "ingestion_plans.json"


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_ingestion_plans(path: Path = PLANS_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def source_config(source_id: str) -> dict:
    for source in load_catalog()["sources"]:
        if source["source_id"] == source_id:
            return source
    raise KeyError(f"ไม่พบ source_id: {source_id}")


def sync_catalog(session: Session) -> None:
    catalog = load_catalog()
    known_source_ids: list[str] = []
    for item in catalog["sources"]:
        known_source_ids.append(item["source_id"])
        source = session.get(Source, item["source_id"]) or Source(source_id=item["source_id"])
        source.ordinal = item["ordinal"]
        source.name_th = item["name_th"]
        source.source_url = item["url"]
        source.acquisition_mode = item["acquisition_mode"]
        source.readiness_status = item["readiness_status"]
        source.cloud_policy = item["cloud_policy"]
        source.production_values_allowed = item["production_values_allowed"]
        source.expected_record_count = item["expected_record_count"]
        source.notes_th = item.get("notes_th", "")
        session.add(source)

    session.flush()
    if known_source_ids:
        session.execute(delete(Endpoint).where(Endpoint.source_id.in_(known_source_ids)))
    for item in catalog["sources"]:
        for endpoint in item.get("endpoints", []):
            session.add(
                Endpoint(
                    endpoint_id=endpoint["endpoint_id"],
                    source_id=item["source_id"],
                    method=endpoint["method"],
                    url=endpoint["url"],
                    kind=endpoint.get("kind", ""),
                    access_status=endpoint.get("access", ""),
                    team_action=endpoint.get("team_action", ""),
                    restricted=endpoint["restricted"],
                    runtime_enabled=endpoint["runtime_enabled"],
                    request_template=endpoint.get("request_template", {}),
                    notes_th=endpoint.get("notes_th", ""),
                )
            )
    session.commit()
