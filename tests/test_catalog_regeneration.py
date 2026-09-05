"""Regeneration must keep the connectors and public request shapes already in use."""
import json

import pytest

from app.settings import PROJECT_ROOT
from tools.build_source_catalog import (
    load_clig_endpoints, load_target_household_search_endpoint, source_policy,
)
from tools import build_source_catalog as catalog_builder, build_source_coverage as coverage_builder


@pytest.fixture
def clig_evidence(tmp_path, monkeypatch):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"total_records": 1, "sources": [{
        "source_id": "clig_projects", "name_th": "CLIG", "normalized_url": "https://clig.oas.psu.ac.th/project/search_project",
    }]}), encoding="utf-8")
    (tmp_path / "00_INDEX.csv").write_text("source_id,data_location,name_th,url,data_row_count\n", encoding="utf-8")
    audit = tmp_path / "audit"
    for module in (catalog_builder, coverage_builder):
        monkeypatch.setattr(module, "REGISTRY_PATH", registry)
        monkeypatch.setattr(module, "AUDIT_ROOT", audit)
        monkeypatch.setattr(module, "provenance_path", lambda path: path.as_posix())
    monkeypatch.setattr(coverage_builder, "current_public_projection", lambda: (set(), {}))
    return tmp_path, audit / "01_clig_projects/source_card.json"


def test_catalog_requires_the_canonical_source_card(clig_evidence):
    root, _ = clig_evidence
    with pytest.raises(SystemExit, match="source card"):
        catalog_builder.build_catalog(root)


@pytest.mark.parametrize("card", [
    {"source_id": "clig_projects", "contract_version": "1.0.0"},
    {"source_id": "another_source", "status": "NEEDS_REVIEW"},
])
def test_connector_contract_or_wrong_source_cannot_replace_a_source_card(clig_evidence, card):
    root, path = clig_evidence
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(card), encoding="utf-8")
    with pytest.raises(ValueError, match="Source card"):
        catalog_builder.build_catalog(root)


def test_catalog_uses_real_source_card_and_coverage_cannot_fall_back_to_contract(clig_evidence):
    root, path = clig_evidence
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"source_id": "clig_projects", "status": "NEEDS_REVIEW"}), encoding="utf-8")
    catalog = catalog_builder.build_catalog(root)
    assert catalog["sources"][0]["source_card"] == path.as_posix()
    assert catalog["sources"][0]["audit_status"] == "NEEDS_REVIEW"
    catalog["sources"][0]["source_card"] = "config/connector_contracts/clig_projects.json"
    catalog_path = root / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    path.unlink()
    with pytest.raises(SystemExit, match="source card"):
        coverage_builder.build_coverage(catalog_path, root)


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
