from tools.f2_pipeline.sources.pmua_apptech import (
    TABLE_COLUMNS,
    TABLE_GRAINS,
    _export_tables,
    build_tables,
)


def test_pmua_exposes_the_complete_legacy_table_contract():
    assert callable(build_tables)
    assert {
        "innovations",
        "innovation_details",
        "researcher_assertions",
        "map_area_items",
        "readiness_assessments",
        "aggregate_components",
    } <= set(TABLE_COLUMNS)
    assert set(TABLE_COLUMNS) == set(TABLE_GRAINS)


def test_pmua_export_quotes_raw_area_json_scalars_without_mutating_facts():
    source = {
        "innovation_area_assertions": [
            {"raw_area_json": "007"},
            {"raw_area_json": {"province": "เชียงใหม่"}},
        ]
    }
    exported = _export_tables(source)
    assert exported["innovation_area_assertions"][0]["raw_area_json"] == '"007"'
    assert (
        exported["innovation_area_assertions"][1]["raw_area_json"]
        == '{"province":"เชียงใหม่"}'
    )
    assert source["innovation_area_assertions"][0]["raw_area_json"] == "007"
