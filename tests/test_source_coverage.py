from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path

import pytest


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(
    os.environ.get("AIAT_EVIDENCE_ROOT", str(DASHBOARD_ROOT.parent))
).expanduser().resolve()
CATALOG_PATH = DASHBOARD_ROOT / "config/source_catalog.json"
COVERAGE_PATH = DASHBOARD_ROOT / "data/public/source_coverage.json"
REGISTRY_PATH = PROJECT_ROOT / "config/source_registry.json"
MERGED_ROOT = PROJECT_ROOT / "data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01"
HAS_EVIDENCE_WORKSPACE = (
    REGISTRY_PATH.is_file()
    and (MERGED_ROOT / "00_INDEX.csv").is_file()
    and (
        PROJECT_ROOT
        / "data/raw/network/f2_learning_dashboard/20260803T_network/observation.json"
    ).is_file()
    and (
        PROJECT_ROOT
        / "data/raw/network/f1_pppconnext/20260817T_public_api_fetch_02/network_observation.json"
    ).is_file()
)

PUBLIC_CANDIDATES = {
    "f1_sradss_ppaos",
    "f1_pppconnext",
    "f2_culturalmap_university",
    "f2_rmutdb",
    "f2_apptech_mtr",
    "f2_apptech_mru",
    "f2_learning_dashboard",
    "f2_learning_area_based",
    "f3_city_capital_open_data",
    "f3_ruamthiao_lamphun",
    "f3_housing_portal",
}

RESTRICTED = {
    "f2_target_household",
    "f2_wallet_all_realtime",
    "f2_wallet_cluster_realtime",
    "f3_nonthaburi_city_learning",
    "f3_healthcare_nonthaburi",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_endpoint_ids_match_the_current_policy_fields():
    catalog = read_json(CATALOG_PATH)
    for source in catalog["sources"]:
        for endpoint in source.get("endpoints", []):
            identity = "|".join(
                (
                    source["source_id"],
                    endpoint["method"],
                    endpoint["url"],
                    endpoint["team_action"],
                )
            )
            assert endpoint["endpoint_id"] == hashlib.sha256(
                identity.encode("utf-8")
            ).hexdigest()


def test_catalog_covers_registry_and_keeps_value_lanes_separate():
    catalog = read_json(CATALOG_PATH)
    assert catalog["catalog_version"] == "0.3.0"
    assert catalog["policy"]["approval_basis"] == "current_catalog_policy_and_source_cards"
    assert catalog["policy"]["current_stewardship"] == "repository_co_maintainers"
    assert "approval_recorded_by" not in catalog["policy"]
    assert "approved_by" not in catalog["policy"]
    catalog_ids = [source["source_id"] for source in catalog["sources"]]
    assert len(catalog_ids) == catalog["policy"]["registry_source_count"] == 28
    if REGISTRY_PATH.is_file():
        registry = read_json(REGISTRY_PATH)
        registry_ids = [source["source_id"] for source in registry["sources"]]
        assert registry["total_records"] == 28
        assert catalog_ids == registry_ids
    assert [source["ordinal"] for source in catalog["sources"]] == list(range(1, 29))

    by_id = {source["source_id"]: source for source in catalog["sources"]}
    assert {source_id for source_id, source in by_id.items() if source["production_values_allowed"]} == PUBLIC_CANDIDATES
    assert {source_id for source_id, source in by_id.items() if source["value_visibility"] == "restricted_local_only"} == RESTRICTED
    assert sum(source["value_visibility"] == "metadata_only" for source in by_id.values()) == 12
    assert {
        source["cloud_policy"]
        for source in by_id.values()
        if source["production_values_allowed"]
    } == {"team_approved_public"}

    for source_id in RESTRICTED:
        source = by_id[source_id]
        assert source["acquisition_mode"] == "blocked"
        assert source["expected_record_count"] == 0
        assert source["snapshot_origin_files"] == []
        assert all(endpoint["restricted"] for endpoint in source["endpoints"])
        assert not any(endpoint["runtime_enabled"] for endpoint in source["endpoints"])

    for source in by_id.values():
        if source["value_visibility"] == "metadata_only":
            assert source["acquisition_mode"] == "metadata_only"
            assert source["expected_record_count"] == 0
            assert source["snapshot_origin_files"] == []
            assert source["endpoints"] == []


def test_learning_dashboard_uses_verified_post_and_66_province_rows():
    catalog = read_json(CATALOG_PATH)
    source = next(
        source for source in catalog["sources"] if source["source_id"] == "f2_learning_dashboard"
    )
    assert source["acquisition_mode"] == "api_first"
    assert source["production_values_allowed"] is True
    assert source["readiness_status"] == "needs_review"
    assert source["expected_record_count"] == 66
    assert source["snapshot_origin_files"] == []
    assert len(source["endpoints"]) == 1
    endpoint = source["endpoints"][0]
    assert endpoint["method"] == "POST"
    assert endpoint["url"] == "https://lesuper.app/api/opendata/pmua"
    assert endpoint["request_template"] == {"json": {}, "json_body": {}}
    assert endpoint["runtime_enabled"] is True
    assert endpoint["restricted"] is False
    assert "raw response" in source["notes_th"]
    assert "selected-project scope" in source["notes_th"]


@pytest.mark.skipif(
    not HAS_EVIDENCE_WORKSPACE,
    reason="full endpoint evidence is not included in the public clone",
)
def test_every_catalog_endpoint_has_evidence_and_is_not_invented():
    index_rows = list(
        csv.DictReader((MERGED_ROOT / "00_INDEX.csv").open(encoding="utf-8-sig", newline=""))
    )
    allowed: set[tuple[str, str, str]] = set()
    for row in index_rows:
        relative = Path(row["data_location"].replace("\\", "/"))
        data_location = PROJECT_ROOT / relative
        if not data_location.exists():
            data_location = MERGED_ROOT / relative
        endpoint_path = data_location / "endpoints.csv"
        for endpoint in csv.DictReader(endpoint_path.open(encoding="utf-8-sig", newline="")):
            allowed.add((row["source_id"], endpoint.get("method", "GET").upper(), endpoint["url"]))

    observation = read_json(
        PROJECT_ROOT
        / "data/raw/network/f2_learning_dashboard/20260803T_network/observation.json"
    )["network"]
    allowed.add(
        (
            "f2_learning_dashboard",
            observation["method_observed"].upper(),
            observation["endpoint"],
        )
    )
    ppp_observation = read_json(
        PROJECT_ROOT
        / "data/raw/network/f1_pppconnext/20260817T_public_api_fetch_02/network_observation.json"
    )
    for endpoint in ppp_observation["observations"]:
        allowed.add(("f1_pppconnext", "GET", endpoint["url"]))

    catalog = read_json(CATALOG_PATH)
    actual = {
        (source["source_id"], endpoint["method"], endpoint["url"])
        for source in catalog["sources"]
        for endpoint in source["endpoints"]
    }
    assert actual <= allowed


def test_public_coverage_reports_counts_geo_gaps_and_zero_restricted_leaks():
    payload = read_json(COVERAGE_PATH)
    summary = payload["summary"]
    assert summary["registry_source_count"] == 28
    assert summary["catalog_metadata_source_count"] == 28
    assert summary["public_candidate_source_count"] == 11
    assert summary["metadata_only_source_count"] == 12
    assert summary["restricted_local_only_source_count"] == 5
    assert summary["sources_with_merged_index_entry"] == 12
    assert summary["public_candidates_with_observed_count"] == 11
    assert summary["restricted_value_leak_count"] == 0

    sources = {source["source_id"]: source for source in payload["sources"]}
    assert len(sources) == 28
    sra = sources["f1_sradss_ppaos"]
    omission = sra["geo"]["known_omissions"][0]
    assert sra["geo"]["linked_area_count"] == 20
    assert sra["geo"]["current_map_area_count"] == 20
    assert sra["geo"]["numeric_value_area_count"] == 15
    assert sra["records"]["serving_projection_count"] == 20
    assert sra["records"]["serving_numeric_value_count"] == 15
    assert omission["count"] == 5
    assert omission["labels_th"] == ["นครราชสีมา", "ยโสธร", "ลำปาง", "พิษณุโลก", "พัทลุง"]

    culture = sources["f2_culturalmap_university"]
    assert culture["records"]["observed_count"] == 5619
    assert culture["records"]["serving_projection_count"] == 5258
    assert culture["records"]["additional_public_non_map_count"] == 361
    assert culture["geo"]["known_omissions"][0]["count"] == 361

    learning = sources["f2_learning_dashboard"]
    assert learning["records"]["observed_count"] == 66
    assert learning["records"]["observed_count_basis"] == "verified_province_rows_excluding_header"
    assert learning["public_visibility"]["production_values_allowed"] is True
    assert learning["status"]["fact_acceptance"] == "candidate_needs_review"
    assert learning["evidence"]["approval_basis"] == "source_card_candidate_scope_needs_review"

    assert sources["f2_cultural_market_civil"]["public_visibility"]["classification"] == "metadata_only"
    assert sources["f2_icommunity"]["public_visibility"]["classification"] == "metadata_only"
    household = sources["f2_target_household"]
    assert household["public_visibility"]["classification"] == "restricted_local_only"
    assert household["records"]["observed_count"] is None

    rmutdb = sources["f2_rmutdb"]
    assert rmutdb["geo"]["linkability"] == "not_province_scoped"
    assert rmutdb["geo"]["linked_area_count"] == 0

    housing = sources["f3_housing_portal"]
    assert housing["records"]["observed_count"] == 7259
    assert housing["records"]["serving_projection_count"] == 6953
    assert housing["records"]["additional_public_non_map_count"] == 306
    assert housing["records"]["serving_projection_count"] + 306 == housing["records"]["observed_count"]
    assert housing["geo"]["linked_area_count"] == 12
    housing_omission = housing["geo"]["known_omissions"][0]
    assert housing_omission["kind"] == "public_rows_with_unassigned_province_outside_map_projection"
    assert housing_omission["count"] == 306
