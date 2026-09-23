import pytest

from tools.f2_pipeline.measure_query import MeasureQuery
from tools.f2_pipeline.query import EntityQuery


PROVINCES = [
    {
        "province_code": "10",
        "province_name_th": "A",
        "region": "Dashboard North",
        "region_id": "north",
    },
    {
        "province_code": "20",
        "province_name_th": "B",
        "region": "Dashboard South",
        "region_id": "south",
    },
]


def definition(measure_id, filters, unit="person", status="source_aggregate"):
    return {
        "measure_id": measure_id,
        "unit": unit,
        "status": status,
        "supported_filters": filters,
        "permitted_filter_combinations": [[], *[[name] for name in filters], filters]
        if len(filters) > 1
        else [[], filters],
        "limitations": "Source did not supply the required data.",
    }


def row(measure_id, breakdown, member, amount, divisor="1", **extra):
    return {
        "measure_id": measure_id,
        "breakdown_id": breakdown,
        "member_id": member,
        "amount": str(amount),
        "amount_unit": "THB",
        "result_divisor": str(divisor),
        "evidence_table": "synthetic",
        "evidence_key": member,
        "evidence_id": member,
        "province_code": None,
        "province_name": None,
        "source_level": None,
        "raw_locator": member,
        "member_label": member,
        "region": None,
        "component": None,
        **extra,
    }


def aggregate_query(measure_id, filters, rows, **kwargs):
    return MeasureQuery(
        definition(measure_id, filters, **kwargs),
        {"aggregate_breakdowns": rows},
        PROVINCES,
    )


def test_k02_rejects_missing_pmua_province_level_cell_and_keeps_exact_details():
    rows = [
        row("K02", "province", "10-a", "100", province_code="10", source_level="A"),
        row("K02", "province", "20-a", "200", province_code="20", source_level="A"),
        row("K02", "province", "10-b", "10", province_code="10", source_level="B"),
    ]
    query = aggregate_query("K02", ["province", "source_level"], rows)
    absent_province = aggregate_query(
        "K02", ["province", "source_level"], rows[:1]
    ).select({"province": ["20"]})
    assert absent_province["result"]["availability"] == "unavailable"
    missing = query.select({"province": ["10", "20"], "source_level": ["B"]})
    assert missing["result"]["availability"] == "unavailable"
    assert missing["result"]["unavailable_reason"]["code"] == "missing_breakdown"
    selected = query.select({"province": ["10", "20"], "source_level": ["A"]})
    assert selected["result"]["value_exact"] == "300"
    assert [item["member_id"] for item in selected["aggregate_breakdowns"]] == [
        "10-a",
        "20-a",
    ]


def test_reported_business_dimensions_are_marginal_not_additive():
    query = aggregate_query(
        "C08_REPORTED_BUSINESSES",
        ["source_dimension"],
        [
            row("C08_REPORTED_BUSINESSES", "categories", "company", "375"),
            row("C08_REPORTED_BUSINESSES", "entityTypes", "d1", "375"),
        ],
        unit="business",
    )
    query.definition["baseline_value"] = 999
    default = query.select()
    assert default["result"]["value"] == 375
    assert default["result"]["requested_filters"] == {}
    assert default["result"]["applied_filters"] == {"source_dimension": ["categories"]}
    assert default["coverage"]["national_total"] is None
    assert (
        query.select({"source_dimension": ["categories", "entityTypes"]})["result"][
            "unavailable_reason"
        ]["code"]
        == "invalid_source_dimension_filter"
    )


def test_invalid_aggregate_identity_and_divisor_are_rejected():
    duplicate = [
        row("K09", "regional", "north", "1"),
        row("K09", "regional", "north", "2"),
    ]
    with pytest.raises(ValueError, match="duplicate aggregate member"):
        aggregate_query("K09", ["region"], duplicate)
    with pytest.raises(ValueError, match="result_divisor positive"):
        aggregate_query(
            "K09", ["region"], [row("K09", "regional", "north", "1", divisor="-1")]
        )


def test_money_and_alternative_stay_separate_with_source_region_and_component_ids():
    rows = [
        row(
            "K10",
            "regional",
            "north-workers",
            "11701018",
            divisor="1000000",
            region="Source North",
            component="localEmployeeExpense",
        ),
        row(
            "K10",
            "regional",
            "north-resources",
            "12368490",
            divisor="1000000",
            region="Source North",
            component="localResourceExpense",
        ),
        row(
            "K10",
            "regional",
            "excluded-workers",
            "0",
            divisor="1000000",
            region="Excluded source",
            component="localEmployeeExpense",
        ),
        row(
            "C10_ALTERNATIVE",
            "regional",
            "north-resources",
            "12368490",
            divisor="1000000",
            region="Source North",
            component="localResourceExpense",
        ),
        row(
            "C10_ALTERNATIVE",
            "excluded",
            "wallet",
            "200093000",
            divisor="1000000",
            region="Excluded source",
            component="excludedResourceExpense",
        ),
    ]
    k10 = aggregate_query(
        "K10", ["region", "component"], rows, unit="million_THB_per_month"
    )
    alternative = aggregate_query(
        "C10_ALTERNATIVE", ["region", "component"], rows, unit="million_THB_per_month"
    )
    assert k10.select()["result"] == {
        "value": 24.069508,
        "value_exact": "24.069508",
        "display_value": "24.1",
        "unit": "million_THB_per_month",
        "status": "source_aggregate",
        "availability": "available",
        "scope_key": "national",
        "requested_filters": {},
        "applied_filters": {},
        "unavailable_reason": None,
    }
    excluded = alternative.select(
        {"region": ["Excluded source"], "component": ["excludedResourceExpense"]}
    )
    missing_cell = k10.select(
        {
            "region": ["Source North", "Excluded source"],
            "component": ["localEmployeeExpense", "localResourceExpense"],
        }
    )
    assert missing_cell["result"]["unavailable_reason"]["code"] == "missing_breakdown"
    assert excluded["aggregate_breakdowns"][0]["region"] == "Excluded source"
    assert (
        k10.select({"region": ["Dashboard North"]})["result"]["availability"]
        == "unavailable"
    )


def test_participating_uses_entity_query_for_province_but_not_implicit_region():
    definition_row = definition("C08_PARTICIPATING", ["province"], unit="business")
    tables = {
        "entity_contributions": [
            {"measure_id": "C08_PARTICIPATING", "entity_id": "one"}
        ],
        "province_memberships": [
            {
                "measure_id": "C08_PARTICIPATING",
                "entity_id": "one",
                "province_code": "10",
            }
        ],
        "category_memberships": [],
    }
    query = MeasureQuery(definition_row, tables, PROVINCES)
    malformed = query.select({"region": [1]})
    assert malformed["result"]["requested_filters"] == {"region": [1]}
    assert malformed["result"]["unavailable_reason"]["code"] == "unsupported_filter"
    assert query.kind == "entity"
    assert query.select({"province": ["10"]})["entity_ids"] == ["one"]
    assert (
        query.select({"region": ["north"]})["result"]["unavailable_reason"]["code"]
        == "unsupported_filter"
    )


def test_null_measure_has_explanation_and_old_entity_route_is_unchanged():
    for measure_id, status, code in (
        ("K06", "deferred", "deferred"),
        ("K08", "insufficient_data", "insufficient_data"),
        ("K11A", "insufficient_data", "insufficient_data"),
        ("K11B", "insufficient_data", "insufficient_data"),
    ):
        unavailable = MeasureQuery(
            definition(measure_id, [], status=status), {}, PROVINCES
        ).select()
        assert unavailable["query_kind"] == "methodology"
        assert unavailable["result"]["value"] is None
        assert unavailable["result"]["unavailable_reason"]["code"] == code
    definition_row = definition(
        "K12", ["province"], unit="subject", status="available_snapshot"
    )
    tables = {
        "entity_contributions": [{"measure_id": "K12", "entity_id": "one"}],
        "province_memberships": [
            {"measure_id": "K12", "entity_id": "one", "province_code": "10"}
        ],
        "category_memberships": [],
    }
    selected = MeasureQuery(definition_row, tables, PROVINCES).select(
        {"province": ["10"]}
    )
    assert selected["query_kind"] == "entity"
    assert selected["aggregate_breakdowns"] == []
    assert {
        key: selected[key] for key in ("result", "entity_ids", "coverage")
    } == EntityQuery(definition_row, tables, PROVINCES).select({"province": ["10"]})
