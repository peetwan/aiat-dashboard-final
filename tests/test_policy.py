from __future__ import annotations

from app.catalog import load_catalog, load_ingestion_plans


def test_catalog_has_all_merged_sources_and_ten_public_approvals():
    catalog = load_catalog()
    source_ids = {source["source_id"] for source in catalog["sources"]}
    assert len(source_ids) == 12
    assert sum(source["production_values_allowed"] for source in catalog["sources"]) == 10
    assert {
        "f2_wallet_all_realtime",
        "f2_wallet_cluster_realtime",
    } == {
        source["source_id"]
        for source in catalog["sources"]
        if source["cloud_policy"] == "restricted_local_only"
    }


def test_executable_plans_never_include_restricted_sources():
    plans = load_ingestion_plans()["sources"]
    assert set(plans) == {
        "f1_sradss_ppaos",
        "f2_apptech_mtr",
        "f2_apptech_mru",
        "f2_learning_area_based",
        "f3_housing_portal",
    }
    executable_urls = []
    for plan in plans.values():
        executable_urls.extend(item["url"] for item in plan.get("requests", []))
        executable_urls.extend(item["url"] for item in plan.get("datasets", []) if "url" in item)
        if "url" in plan:
            executable_urls.append(plan["url"])
        if "package_show_url" in plan:
            executable_urls.append(plan["package_show_url"])
    serialized = " ".join(executable_urls).lower()
    assert "data_household_detail.php" not in serialized
    assert "/backend/ajax/auth/" not in serialized
