import pytest
from tools.f2_pipeline.sources.rinmp import DATASET_KEYS, TABLE_COLUMNS, RINMPPilot, build_tables


def test_rinmp_requires_complete_capture_bundle_before_reading_reviews():
    with pytest.raises(
        ValueError, match="datasets must be app_tech, owner_profiles, statistics"
    ):
        build_tables({}, {}, None, {})


def test_rinmp_preserves_legacy_table_contract_exports():
    assert DATASET_KEYS == ("app_tech", "owner_profiles", "statistics")
    assert {
        "innovations",
        "people",
        "location_assertions",
        "owner_groups",
        "review_coverage",
    } <= set(TABLE_COLUMNS)


def _pilot():
    datasets = {
        "app_tech": {"record_count": 1, "data": {"records": [{"id": 1}]}},
        "owner_profiles": {
            "record_count": 1,
            "data": {"records": [{"owner_key": "synthetic-owner"}]},
        },
        # Statistics is one aggregate object, not an envelope with a row total.
        "statistics": {"data": {}},
    }
    metadata = {
        name: {
            "source_id": "f2_apptech_mtr",
            "run_id": "synthetic-run",
            "file": name + ".json",
            "sha256": "a" * 64,
            "size": 1,
            "captured_at": "2026-01-01",
            "originating_system": "synthetic",
        }
        for name in datasets
    }
    return RINMPPilot(datasets, {"reviewed_cases.json": {}}, None, metadata)


def test_rinmp_ingest_accounts_for_each_capture_without_fixed_snapshot_totals():
    pilot = _pilot()
    pilot.ingest()
    assert len(pilot.tables["source_observations"]) == 3
    assert [row["row_count"] for row in pilot.tables["source_files"]] == [1, 1, 1]


@pytest.mark.parametrize("dataset", ["app_tech", "owner_profiles"])
@pytest.mark.parametrize("count", [None, True, "1", -1, 0, 2])
def test_rinmp_rejects_missing_invalid_or_inconsistent_declared_count(dataset, count):
    pilot = _pilot()
    pilot.datasets[dataset]["record_count"] = count
    with pytest.raises(ValueError, match="row accounting"):
        pilot.ingest()


@pytest.mark.parametrize("dataset, field", [("app_tech", "id"), ("owner_profiles", "owner_key")])
@pytest.mark.parametrize("identity", [None, "", " ", True, [], {}])
def test_rinmp_rejects_invalid_source_ids_before_string_conversion(dataset, field, identity):
    pilot = _pilot()
    pilot.datasets[dataset]["data"]["records"][0][field] = identity
    with pytest.raises(ValueError, match="source ID"):
        pilot.ingest()


@pytest.mark.parametrize("dataset", ["app_tech", "owner_profiles"])
def test_rinmp_duplicate_ids_fail_even_when_declared_count_matches(dataset):
    pilot = _pilot()
    envelope = pilot.datasets[dataset]
    envelope["data"]["records"] *= 2
    envelope["record_count"] = 2
    with pytest.raises(ValueError, match="reused"):
        pilot.ingest()
