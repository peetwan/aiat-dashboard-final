from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Endpoint, Source
from app.settings import PROJECT_ROOT


CATALOG_PATH = PROJECT_ROOT / "config" / "source_catalog.json"
PLANS_PATH = PROJECT_ROOT / "config" / "ingestion_plans.json"
CATALOG_CONTRACT = {
    "registry_source_count": 28,
    "approved_public_source_count": 11,
    "metadata_only_source_count": 12,
    "restricted_source_count": 5,
}


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_ingestion_plans(path: Path = PLANS_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def source_config(source_id: str) -> dict:
    for source in load_catalog()["sources"]:
        if source["source_id"] == source_id:
            return source
    raise KeyError(f"ไม่พบ source_id: {source_id}")


def validate_catalog_contract(catalog: dict) -> None:
    sources = catalog.get("sources")
    if not isinstance(sources, list):
        raise ValueError("source catalog must contain a sources array")
    source_ids = [item.get("source_id") for item in sources]
    public_ids = {
        item["source_id"]
        for item in sources
        if item.get("cloud_policy") == "project_owner_approved_public"
    }
    approved_ids = {
        item["source_id"] for item in sources if item.get("production_values_allowed") is True
    }
    actual = {
        "registry_source_count": len(sources),
        "approved_public_source_count": len(public_ids),
        "metadata_only_source_count": sum(
            item.get("cloud_policy") == "metadata_only" for item in sources
        ),
        "restricted_source_count": sum(
            item.get("cloud_policy") == "restricted_local_only" for item in sources
        ),
    }
    policy = catalog.get("policy", {})
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("source catalog contains duplicate source_id values")
    if actual != CATALOG_CONTRACT:
        raise ValueError(f"source catalog contract mismatch: {actual}")
    if {key: policy.get(key) for key in CATALOG_CONTRACT} != CATALOG_CONTRACT:
        raise ValueError("source catalog policy summary does not match its required contract")
    if public_ids != approved_ids:
        raise ValueError("public cloud policy and production approval source sets differ")


def sync_catalog(session: Session) -> None:
    catalog = load_catalog()
    validate_catalog_contract(catalog)
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
