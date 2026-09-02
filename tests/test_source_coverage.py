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
PUBLIC_ROOT = DASHBOARD_ROOT / "data/public"
CONTRACT_ROOT = DASHBOARD_ROOT / "config/publication_contracts"
REGISTRY_PATH = PROJECT_ROOT / "config/source_registry.json"
MERGED_ROOT = PROJECT_ROOT / "data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01"
MERGED_INDEX_PATH = MERGED_ROOT / "00_INDEX.csv"
if MERGED_INDEX_PATH.is_file():
    with MERGED_INDEX_PATH.open(encoding="utf-8-sig", newline="") as handle:
        MERGED_SOURCE_IDS = {row["source_id"] for row in csv.DictReader(handle)}
else:
    MERGED_SOURCE_IDS = set()
if CATALOG_PATH.is_file():
    _catalog_for_evidence_check = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    CATALOG_ENDPOINT_SOURCE_IDS = {
        source["source_id"]
        for source in _catalog_for_evidence_check["sources"]
        if source.get("endpoints")
    }
else:
    CATALOG_ENDPOINT_SOURCE_IDS = set()
SEPARATE_ENDPOINT_EVIDENCE_SOURCE_IDS = {
    "f1_pppconnext",
    "f2_learning_dashboard",
    "f2_target_household",
}
HAS_EVIDENCE_WORKSPACE = (
    REGISTRY_PATH.is_file()
    and MERGED_INDEX_PATH.is_file()
    and (
        PROJECT_ROOT
        / "data/raw/network/f2_learning_dashboard/20260803T_network/observation.json"
    ).is_file()
    and (
        PROJECT_ROOT
        / "data/raw/network/f1_pppconnext/20260817T_public_api_fetch_02/network_observation.json"
    ).is_file()
    and CATALOG_ENDPOINT_SOURCE_IDS
    <= MERGED_SOURCE_IDS | SEPARATE_ENDPOINT_EVIDENCE_SOURCE_IDS
)

PUBLIC_CANDIDATES = {
    "clig_projects",
    "f1_sradss_ppaos",
    "f1_pppconnext",
    "f2_culturalmap_university",
    "f2_rmutdb",
    "f2_apptech_mtr",
    "f2_apptech_mru",
    "f2_target_household",
    "f2_learning_dashboard",
    "f2_learning_area_based",
    "f2_wallet_all_realtime",
    "f2_wallet_cluster_realtime",
    "f3_city_capital_open_data",
    "f3_ruamthiao_lamphun",
    "f3_housing_portal",
    "spu_sukhothai_care",
    "spu_sukhothai_water",
    "spu_nsn_flood",
    "spu_rawangphai_uru",
}

RESTRICTED = {
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
    coverage_contract = read_json(CONTRACT_ROOT / "source_coverage.json")
    expected_source_count = next(
        output["expected_count"]
        for output in coverage_contract["outputs"]
        if output.get("records_pointer") == "/sources"
    )
    assert catalog["catalog_version"] == "0.3.0"
    assert catalog["policy"]["approval_basis"] == "current_catalog_policy_and_source_cards"
    assert catalog["policy"]["current_stewardship"] == "repository_co_maintainers"
    assert "approval_recorded_by" not in catalog["policy"]
    assert "approved_by" not in catalog["policy"]
    catalog_ids = [source["source_id"] for source in catalog["sources"]]
    assert len(catalog_ids) == catalog["policy"]["registry_source_count"] == expected_source_count
    if REGISTRY_PATH.is_file():
        registry = read_json(REGISTRY_PATH)
        registry_ids = [source["source_id"] for source in registry["sources"]]
        assert registry["total_records"] == expected_source_count
        assert catalog_ids == registry_ids
    assert [source["ordinal"] for source in catalog["sources"]] == list(
        range(1, expected_source_count + 1)
    )

    by_id = {source["source_id"]: source for source in catalog["sources"]}
    assert {source_id for source_id, source in by_id.items() if source["production_values_allowed"]} == PUBLIC_CANDIDATES
    assert {source_id for source_id, source in by_id.items() if source["value_visibility"] == "restricted_local_only"} == RESTRICTED
    assert sum(
        source["value_visibility"] == "metadata_only" for source in by_id.values()
    ) == expected_source_count - len(PUBLIC_CANDIDATES) - len(RESTRICTED)
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


def test_learning_dashboard_uses_verified_public_post_contract():
    catalog = read_json(CATALOG_PATH)
    source = next(
        source for source in catalog["sources"] if source["source_id"] == "f2_learning_dashboard"
    )
    assert source["acquisition_mode"] == "api_first"
    assert source["production_values_allowed"] is True
    assert source["readiness_status"] == "needs_review"
    assert source["expected_record_count"] >= 1
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


def test_wallet_and_target_household_use_reviewed_public_contracts():
    catalog = read_json(CATALOG_PATH)
    by_id = {source["source_id"]: source for source in catalog["sources"]}

    target = by_id["f2_target_household"]
    assert target["acquisition_mode"] == "api_first"
    assert target["production_values_allowed"] is True
    assert target["expected_record_count"] == 1160
    assert target["snapshot_origin_files"] == []
    assert len(target["endpoints"]) == 7
    search = next(endpoint for endpoint in target["endpoints"] if endpoint["url"] == "https://pmua-apptech.com/search")
    assert search["method"] == "GET"
    assert search["request_template"]["query_or_body"] == "page=<value>"
    assert search["runtime_enabled"] is True
    assert search["restricted"] is False
    dashboard_urls = {
        endpoint["url"]
        for endpoint in target["endpoints"]
        if endpoint["url"] != "https://pmua-apptech.com/search"
    }
    assert dashboard_urls == {
        "https://pmua-apptech.com/dashboard",
        "https://pmua-apptech.com/dashboard/innovatordashboard",
        "https://pmua-apptech.com/dashboard/familydashboard",
    }
    assert all(endpoint["runtime_enabled"] is True for endpoint in target["endpoints"])
    assert all(endpoint["restricted"] is False for endpoint in target["endpoints"])

    wallet_all = by_id["f2_wallet_all_realtime"]
    assert wallet_all["expected_record_count"] == 2
    assert wallet_all["snapshot_origin_files"] == []
    assert {(item["method"], item["url"]) for item in wallet_all["endpoints"]} == {
        ("POST", "https://lesuper.app/api/opendata/superapp/gen4/hh"),
        ("POST", "https://lesuper.app/api/opendata/superapp/gen4/bu"),
    }
    assert all(item["request_template"].get("json_body") == {"date": ""} for item in wallet_all["endpoints"])
    assert all(item["runtime_enabled"] is True and item["restricted"] is False for item in wallet_all["endpoints"])

    wallet_cluster = by_id["f2_wallet_cluster_realtime"]
    assert wallet_cluster["expected_record_count"] == 14
    assert wallet_cluster["snapshot_origin_files"] == []
    assert {(item["method"], item["url"]) for item in wallet_cluster["endpoints"]} == {
        ("POST", "https://lesuper.app/api/opendata/superapp/gen4/cluster/hh"),
        ("POST", "https://lesuper.app/api/opendata/superapp/gen4/cluster/bu"),
    }
    assert all(item["request_template"].get("json_body") == {} for item in wallet_cluster["endpoints"])
    assert all(item["runtime_enabled"] is True and item["restricted"] is False for item in wallet_cluster["endpoints"])


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
    allowed.add(("f2_target_household", "GET", "https://pmua-apptech.com/search"))
    allowed.add(("f2_target_household", "GET", "https://pmua-apptech.com/dashboard"))
    allowed.add(("f2_target_household", "GET", "https://pmua-apptech.com/dashboard/innovatordashboard"))
    allowed.add(("f2_target_household", "GET", "https://pmua-apptech.com/dashboard/familydashboard"))

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
    contract = read_json(CONTRACT_ROOT / "source_coverage.json")
    expected_source_count = next(
        output["expected_count"]
        for output in contract["outputs"]
        if output.get("records_pointer") == "/sources"
    )
    dashboard_contract = read_json(CONTRACT_ROOT / "dashboard_core.json")
    expected_province_count = next(
        output["expected_count"]
        for output in dashboard_contract["outputs"]
        if output.get("path") == "data/public/public_dashboard.json"
    )
    catalog = read_json(CATALOG_PATH)
    catalog_by_id = {source["source_id"]: source for source in catalog["sources"]}

    assert summary["registry_source_count"] == expected_source_count
    assert summary["catalog_metadata_source_count"] == expected_source_count
    assert summary["public_candidate_source_count"] == len(PUBLIC_CANDIDATES)
    assert summary["metadata_only_source_count"] == sum(
        source["value_visibility"] == "metadata_only"
        for source in catalog_by_id.values()
    )
    assert summary["restricted_local_only_source_count"] == len(RESTRICTED)
    assert summary["restricted_value_leak_count"] == 0

    sources = {source["source_id"]: source for source in payload["sources"]}
    assert len(sources) == expected_source_count
    assert set(sources) == set(catalog_by_id)
    assert summary["sources_with_merged_index_entry"] == sum(
        source["records"]["source_index_present"] for source in sources.values()
    )
    assert summary["public_candidates_with_observed_count"] == sum(
        source_id in PUBLIC_CANDIDATES and source["records"]["observed_count"] is not None
        for source_id, source in sources.items()
    )
    assert summary["current_public_data_artifact_source_count"] == sum(
        source["public_visibility"]["current_public_data_artifact"]
        for source in sources.values()
    )
    assert summary["current_province_projection_source_count"] == sum(
        source["public_visibility"]["current_province_projection"]
        for source in sources.values()
    )

    sra = sources["f1_sradss_ppaos"]
    assert sra["geo"]["linked_area_count"] == sra["geo"]["current_map_area_count"]
    assert sra["geo"]["linked_area_count"] == sra["records"]["serving_projection_count"]
    assert sra["geo"]["numeric_value_area_count"] == sra["records"]["serving_numeric_value_count"]
    assert 0 <= sra["geo"]["numeric_value_area_count"] <= sra["geo"]["linked_area_count"]
    missing_numeric_count = (
        sra["geo"]["linked_area_count"] - sra["geo"]["numeric_value_area_count"]
    )
    missing_numeric = [
        omission
        for omission in sra["geo"]["known_omissions"]
        if omission["kind"] == "registered_province_without_numeric_overall_score"
    ]
    assert sum(item["count"] for item in missing_numeric) == missing_numeric_count
    assert sum(len(item["labels_th"]) for item in missing_numeric) == missing_numeric_count

    culture = sources["f2_culturalmap_university"]
    cultural_points = read_json(PUBLIC_ROOT / "cultural_points.geojson")
    assert culture["records"]["serving_projection_count"] == len(
        cultural_points["features"]
    )
    assert culture["records"]["observed_count"] == (
        culture["records"]["serving_projection_count"]
        + culture["records"]["additional_public_non_map_count"]
    )
    assert sum(
        omission["count"] for omission in culture["geo"]["known_omissions"]
    ) == culture["records"]["additional_public_non_map_count"]

    learning = sources["f2_learning_dashboard"]
    learning_dashboard = read_json(PUBLIC_ROOT / "learning_dashboard.json")
    assert learning["records"]["observed_count"] == len(
        learning_dashboard["province_rows"]
    )
    assert learning["records"]["serving_projection_count"] == len(
        learning_dashboard["province_rows"]
    )
    assert learning["records"]["observed_count_basis"] == "verified_province_rows_excluding_header"
    assert learning["public_visibility"]["production_values_allowed"] is True
    assert learning["status"]["fact_acceptance"] == "candidate_needs_review"
    assert learning["evidence"]["approval_basis"] == "source_card_candidate_scope_needs_review"

    assert sources["f2_cultural_market_civil"]["public_visibility"]["classification"] == "metadata_only"
    assert sources["f2_icommunity"]["public_visibility"]["classification"] == "metadata_only"
    household = sources["f2_target_household"]
    assert household["public_visibility"]["classification"] == "public_candidate"
    assert household["records"]["observed_count"] == 1160
    assert household["records"]["observed_count_basis"] == "public_product_search_listing"
    assert household["public_visibility"]["production_values_allowed"] is True

    wallet_all = sources["f2_wallet_all_realtime"]
    assert wallet_all["public_visibility"]["classification"] == "public_candidate"
    assert wallet_all["records"]["observed_count"] == 2
    assert wallet_all["records"]["observed_count_basis"] == "public_current_month_hh_and_bu_snapshots"

    wallet_cluster = sources["f2_wallet_cluster_realtime"]
    assert wallet_cluster["public_visibility"]["classification"] == "public_candidate"
    assert wallet_cluster["records"]["observed_count"] == 14
    assert wallet_cluster["records"]["observed_count_basis"] == "public_current_month_cluster_snapshots"

    rmutdb = sources["f2_rmutdb"]
    assert rmutdb["geo"]["linkability"] == "not_province_scoped"
    assert rmutdb["geo"]["linked_area_count"] == 0

    housing = sources["f3_housing_portal"]
    unmapped_housing = read_json(PUBLIC_ROOT / "unmapped_records.json")["sources"][
        "f3_housing_portal"
    ]
    assert housing["records"]["observed_count"] == unmapped_housing[
        "approved_projection_records"
    ]
    assert housing["records"]["serving_projection_count"] == unmapped_housing[
        "province_linked_records"
    ]
    assert housing["records"]["additional_public_non_map_count"] == unmapped_housing[
        "record_count"
    ]
    assert housing["records"]["serving_projection_count"] + housing["records"][
        "additional_public_non_map_count"
    ] == housing["records"]["observed_count"]
    assert 0 <= housing["geo"]["linked_area_count"] <= expected_province_count
    housing_omissions = [
        omission
        for omission in housing["geo"]["known_omissions"]
        if omission["kind"]
        == "public_rows_with_unassigned_province_outside_map_projection"
    ]
    assert sum(item["count"] for item in housing_omissions) == housing["records"][
        "additional_public_non_map_count"
    ]
