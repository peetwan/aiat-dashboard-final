"""Regeneration must keep the connectors and public request shapes already in use."""
import gzip
import hashlib
import json

import pytest

from app.settings import PROJECT_ROOT
from tools.build_source_catalog import (
    load_plan_endpoints, load_target_household_search_endpoint, source_policy,
)
from tools import build_source_catalog as catalog_builder, build_source_coverage as coverage_builder


@pytest.fixture
def evidence_snapshot(tmp_path, monkeypatch):
    source_id = "f2_cultural_market_civil"
    run_id = catalog_builder.EVIDENCE_SNAPSHOT_RUNS[source_id]
    run_root = tmp_path / "data/raw" / source_id / run_id
    run_root.mkdir(parents=True)
    content = gzip.compress(json.dumps({"data": [{"id": "fixture-a"}, {"id": "fixture-b"}]}).encode())
    (run_root / "records.json.gz").write_bytes(content)
    manifest = {
        "source_id": source_id, "run_id": run_id,
        "datasets": [{"dataset_key": "fixture.records", "file": "records.json.gz",
                      "sha256": hashlib.sha256(content).hexdigest(), "row_count": 1}],
    }
    path = run_root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(catalog_builder, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(catalog_builder, "provenance_path", lambda path: path.as_posix())
    return source_id, run_id, path, manifest


def test_snapshot_promotion_keeps_unreviewed_counts_and_values_out_of_coverage(clig_evidence, evidence_snapshot):
    root, _ = clig_evidence
    source_id, run_id, _, _ = evidence_snapshot
    catalog_builder.REGISTRY_PATH.write_text(json.dumps({"total_records": 1, "sources": [{
        "source_id": source_id, "name_th": "Fixture", "normalized_url": "https://example.test/",
    }]}), encoding="utf-8")
    card = catalog_builder.AUDIT_ROOT / f"01_{source_id}/source_card.json"
    card.parent.mkdir(parents=True)
    card.write_text(json.dumps({"source_id": source_id, "status": "NEEDS_REVIEW"}), encoding="utf-8")
    catalog = catalog_builder.build_catalog(root)
    source = catalog["sources"][0]
    assert source["acquisition_mode"] == "snapshot_only"
    assert source["audit_status"] == "NEEDS_REVIEW"
    assert source["snapshot_evidence"]["run_id"] == run_id
    assert source["snapshot_evidence"]["dataset_count"] == 1
    assert len(source["snapshot_origin_files"]) == 1
    assert source["expected_record_count"] == 0  # Neither the envelope count nor its data[] length.
    assert source["endpoints"] == []
    catalog_path = root / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    coverage = coverage_builder.build_coverage(catalog_path, root)["sources"][0]
    assert coverage["records"]["observed_count"] is None
    assert coverage["records"]["observed_count_basis"] == "snapshot_evidence_only_no_reviewed_record_count"
    assert coverage["public_visibility"]["current_public_data_artifact"] is False
    assert coverage["evidence"]["primary_paths"][0] == source["snapshot_evidence"]["manifest"]


@pytest.mark.parametrize("fault", ["identity", "missing_file", "hash", "traversal", "duplicate_dataset", "extra_file"])
def test_snapshot_promotion_rejects_invalid_evidence(evidence_snapshot, fault):
    source_id, run_id, path, manifest = evidence_snapshot
    if fault == "identity":
        manifest["source_id"] = "another_source"
    elif fault == "missing_file":
        (path.parent / "records.json.gz").unlink()
    elif fault == "hash":
        (path.parent / "records.json.gz").write_bytes(b"corrupted")
    elif fault == "traversal":
        manifest["datasets"][0]["file"] = "../outside.json.gz"
    elif fault == "duplicate_dataset":
        manifest["datasets"].append(dict(manifest["datasets"][0]))
    elif fault == "extra_file":
        manifest["extra_files"] = [{"file": "missing.json", "sha256": "0" * 64}]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        catalog_builder.load_evidence_snapshot(source_id, run_id)


def test_snapshot_promotion_requires_a_pinned_manifest(evidence_snapshot):
    source_id, run_id, path, _ = evidence_snapshot
    path.unlink()
    with pytest.raises(SystemExit, match=f"evidence_pull.py {source_id} --run {run_id}"):
        catalog_builder.load_evidence_snapshot(source_id, run_id)


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
    endpoints = load_plan_endpoints("clig_projects", plan, "team_approved_public", "api_first")
    assert {(row["method"], row["url"]) for row in endpoints} == {
        ("POST", plan["list_url"]), ("GET", plan["detail_url_template"])}
    assert all(row["runtime_enabled"] and not row["restricted"] for row in endpoints)
    assert endpoints[0]["request_template"]["form_body"] == {
        "project_name": "<value>", "project_year": "<value>", "page": "<value>"}
    other = load_plan_endpoints("another_source", plan, "restricted_local_only", "api_first")
    assert all(row["restricted"] and not row["runtime_enabled"] for row in other)
    assert {row["endpoint_id"] for row in other}.isdisjoint({row["endpoint_id"] for row in endpoints})


def test_target_public_dashboard_requests_survive_catalog_regeneration():
    endpoints = load_target_household_search_endpoint("api_first")
    assert len(endpoints) == 7
    assert len({row["endpoint_id"] for row in endpoints}) == 7
    dashboards = [row for row in endpoints if "dashboard" in row["url"]]
    assert len(dashboards) == 6
    assert sum(row["request_template"] == {"query_or_body": "year_filter=<value>"} for row in dashboards) == 3
