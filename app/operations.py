from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.catalog import load_catalog, load_ingestion_plans
from app.settings import PROJECT_ROOT


OPERATIONS_POLICY_PATH = PROJECT_ROOT / "config" / "operations_policy.json"


def load_operations_policy(path: Path = OPERATIONS_POLICY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def operations_status() -> dict[str, Any]:
    policy = load_operations_policy()
    catalog = load_catalog()
    plans = load_ingestion_plans().get("sources", {})
    sources = catalog.get("sources", [])
    public_sources = [row for row in sources if row.get("production_values_allowed")]
    policy["summary"] = {
        "registered_sources": len(sources),
        "public_candidate_sources": len(public_sources),
        "api_first_sources": sum(row.get("acquisition_mode") == "api_first" for row in sources),
        "snapshot_sources": sum(row.get("acquisition_mode") == "snapshot_only" for row in sources),
        "metadata_only_sources": sum(row.get("acquisition_mode") == "metadata_only" for row in sources),
        "restricted_sources": sum(row.get("cloud_policy") == "restricted_local_only" for row in sources),
        "executable_connectors": len(plans),
        "automatic_refresh_enabled": bool(policy.get("scheduler", {}).get("enabled")),
        "automatic_public_promotion_enabled": False,
    }
    return policy
