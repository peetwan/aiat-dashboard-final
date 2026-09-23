from tools.f2_pipeline.query import EntityQuery
from tools.f2_pipeline.measure_query import MeasureQuery


def query(contributions=None, supported_filters=None):
    if contributions == []:
        return EntityQuery(
            {"measure_id": "K12", "unit": "subject", "status": "available_snapshot", "supported_filters": supported_filters or ["province", "region", "category"]},
            {"entity_contributions": [], "province_memberships": [], "category_memberships": []},
            [{"province_code": "10", "province_name_th": "A", "region": "North", "region_id": "r-north"}],
        )
    return EntityQuery(
        {"measure_id": "K12", "unit": "subject", "status": "available_snapshot", "supported_filters": supported_filters or ["province", "region", "category"]},
        {
            "entity_contributions": contributions if contributions is not None else [{"measure_id": "K12", "entity_id": value} for value in ("a", "b", "c")],
            "province_memberships": [
                {"measure_id": "K12", "entity_id": "a", "province_code": "10"},
                {"measure_id": "K12", "entity_id": "a", "province_code": "20"},
                {"measure_id": "K12", "entity_id": "b", "province_code": "20"},
            ],
            "category_memberships": [
                {"measure_id": "K12", "entity_id": "a", "category_code": "c1", "category_name_th": "หนึ่ง"},
                {"measure_id": "K12", "entity_id": "b", "category_code": "c2", "category_name_th": "สอง"},
                {"measure_id": "K12", "entity_id": "c", "category_code": "c1", "category_name_th": "หนึ่ง"},
            ],
        },
        [
            {"province_code": "10", "province_name_th": "A", "region": "North", "region_id": "r-north"},
            {"province_code": "20", "province_name_th": "B", "region": "North", "region_id": "r-north"},
        ],
    )


def test_province_and_category_use_union_then_intersection_without_additivity():
    result = query().select({"province": ["10", "20"], "category": ["c1", "c2"]})
    assert result["entity_ids"] == ["a", "b"]
    assert result["result"]["value"] == 2
    assert result["result"]["scope_key"] == "province/10,20"
    assert result["coverage"] == {"national_total": 3, "with_province": 2, "without_province": 1, "selected_count": 2, "province_sum_is_additive": False}


def test_c02_province_scope_is_distinct_nonadditive_and_keeps_unknown_nationally():
    instance = MeasureQuery(
        {
            "measure_id": "C02_COMMUNITY",
            "unit": "person",
            "status": "partial_coverage",
            "supported_filters": ["province"],
            "unsupported_filters": ["region"],
            "permitted_filter_combinations": [[], ["province"]],
        },
        {
            "entity_contributions": [
                {"measure_id": "C02_COMMUNITY", "entity_id": value}
                for value in ("a", "b", "unknown")
            ],
            "province_memberships": [
                {
                    "measure_id": "C02_COMMUNITY",
                    "entity_id": "a",
                    "province_code": code,
                }
                for code in ("10", "20")
            ]
            + [
                {
                    "measure_id": "C02_COMMUNITY",
                    "entity_id": "b",
                    "province_code": "20",
                }
            ],
            "category_memberships": [],
        },
        [
            {
                "province_code": "10",
                "province_name_th": "A",
                "region": "North",
                "region_id": "r-north",
            },
            {
                "province_code": "20",
                "province_name_th": "B",
                "region": "North",
                "region_id": "r-north",
            },
        ],
    )

    national = instance.select()
    province_10 = instance.select({"province": ["10"]})
    province_20 = instance.select({"province": ["20"]})
    unsupported_region = instance.select({"region": ["r-north"]})

    assert national["entity_ids"] == ["a", "b", "unknown"]
    assert national["result"]["value"] == 3
    assert national["coverage"] == {
        "national_total": 3,
        "with_province": 2,
        "without_province": 1,
        "selected_count": 3,
        "province_sum_is_additive": False,
    }
    assert province_10["entity_ids"] == ["a"]
    assert province_20["entity_ids"] == ["a", "b"]
    assert province_10["result"]["value"] + province_20["result"]["value"] > 2
    assert unsupported_region["result"]["unavailable_reason"]["code"] == (
        "unsupported_filter"
    )


def test_region_derives_province_union_and_intersects_category():
    result = query().select({"region": ["r-north"], "category": ["c1"]})
    assert result["entity_ids"] == ["a"]
    assert result["result"]["scope_key"] == "region/r-north"

def test_region_is_a_derived_scope_when_only_province_is_declared():
    result = query(supported_filters=["province", "category"]).select({"region": ["r-north"], "category": ["c1"]})
    assert result["entity_ids"] == ["a"]
    assert result["result"]["applied_filters"] == {"category": ["c1"], "region": ["r-north"]}


def test_unnamed_additional_category_uses_later_named_primary_label():
    instance = EntityQuery(
        {"measure_id": "K12", "unit": "subject", "status": "available_snapshot", "supported_filters": ["category"]},
        {
            "entity_contributions": [{"measure_id": "K12", "entity_id": "additional"}, {"measure_id": "K12", "entity_id": "primary"}],
            "province_memberships": [],
            "category_memberships": [
                {"measure_id": "K12", "entity_id": "additional", "category_code": "c1", "category_name_th": None},
                {"measure_id": "K12", "entity_id": "additional", "category_code": "c1", "category_name_th": ""},
                {"measure_id": "K12", "entity_id": "primary", "category_code": "c1", "category_name_th": "หนึ่ง"},
            ],
        },
        [],
    )
    assert instance.select({"category": ["c1"]})["entity_ids"] == ["additional", "primary"]
    assert instance.categories["c1"] == "หนึ่ง"

def test_zero_entity_measure_is_available_while_invalid_scope_is_missing():
    empty = query([]).select()
    assert empty["result"]["value"] == 0
    assert empty["result"]["availability"] == "available"
    unavailable = query().select({"province": ["99"]})
    assert unavailable["result"]["value"] is None
    assert unavailable["result"]["availability"] == "unavailable"
    assert unavailable["result"]["unavailable_reason"]["code"] == "unknown_province"


def test_invalid_filters_do_not_fall_back_or_leak_prior_selection():
    instance = query()
    assert instance.select({"province": ["10"]})["entity_ids"] == ["a"]
    invalid = instance.select({"province": ["10"], "region": ["r-north"]})
    assert invalid["entity_ids"] == []
    assert invalid["result"]["applied_filters"] == {}
    assert invalid["result"]["unavailable_reason"]["code"] == "unsupported_filter_combination"
    unsupported = instance.select({"year": ["2026"]})
    assert unsupported["result"]["availability"] == "unavailable"
    assert unsupported["result"]["applied_filters"] == {}


def test_empty_lists_and_unknown_categories_are_unavailable_not_zero():
    empty_list = query().select({"category": []})
    assert empty_list["result"]["availability"] == "unavailable"
    assert empty_list["result"]["unavailable_reason"]["code"] == "invalid_filter"
    unknown = query().select({"category": ["not-a-category"]})
    assert unknown["result"]["value"] is None
    assert unknown["result"]["unavailable_reason"]["code"] == "unknown_category"
