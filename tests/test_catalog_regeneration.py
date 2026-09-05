"""Regeneration must keep the connectors and public request shapes already in use."""
import json

from app.settings import PROJECT_ROOT
from tools.build_source_catalog import (
    load_clig_endpoints, load_target_household_search_endpoint, source_policy,
)


def test_clig_remains_an_executable_public_candidate_after_regeneration():
    plan = json.loads((PROJECT_ROOT / "config/ingestion_plans.json").read_text(encoding="utf-8"))["sources"]["clig_projects"]
    assert source_policy("clig_projects") == ("api_first", "team_approved_public", "public_candidate", True)
    endpoints = load_clig_endpoints(plan)
    assert {(row["method"], row["url"]) for row in endpoints} == {
        ("POST", plan["list_url"]), ("GET", plan["detail_url_template"])}
    assert all(row["runtime_enabled"] and not row["restricted"] for row in endpoints)


def test_target_public_dashboard_requests_survive_catalog_regeneration():
    endpoints = load_target_household_search_endpoint("api_first")
    assert len(endpoints) == 7
    assert len({row["endpoint_id"] for row in endpoints}) == 7
    dashboards = [row for row in endpoints if "dashboard" in row["url"]]
    assert len(dashboards) == 6
    assert sum(row["request_template"] == {"query_or_body": "year_filter=<value>"} for row in dashboards) == 3
