import copy
import json

import pytest

from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.domains.aggregates import TABLE_COLUMNS, build_tables


RUN = "synthetic-run"
HASH = "synthetic-hash"
REGIONS = ["North", "Central", "Northeast", "West", "East", "South"]


def uri(source_id, filename, pointer=""):
    suffix = "/" + pointer.strip("/") if pointer else ""
    return f"evidence://{source_id}/{RUN}/{filename}#{suffix}"


def bundle(source_id, dataset_key, filename, payload):
    return {
        "datasets": {dataset_key: payload},
        "metadata": {
            dataset_key: {
                "source_id": source_id,
                "run_id": RUN,
                "file": filename,
                "sha256": HASH,
            }
        },
        "files": [
            {
                "path": filename,
                "sha256": HASH,
                "dataset_key": dataset_key,
            }
        ],
    }


def dashboard_observation(source_key):
    return {
        "observation_id": f"dashboard-{source_key}",
        "source_key": source_key,
        "raw_file": "learning_dashboard.json",
        "raw_file_sha256": HASH,
        "raw_locator": uri(
            "f2_learning_dashboard", "learning_dashboard.json", source_key
        ),
    }


def aggregate_fixture():
    pmua_raw = {
        "dashboard": "innovators",
        "headline": 10,
        "integrity_checks": {
            "headline_matches_sum_total_inno": True,
            "provinces": 2,
            "sum_total_inno": 10,
        },
        "prov_data": {
            "Alpha": {"total_inno": 3, "levels": {"1": 1, "2": 2, "3": 0, "4": 0}},
            "Beta": {"total_inno": 7, "levels": {"1": 0, "2": 1, "3": 2, "4": 4}},
        },
    }
    pmua_observation = {
        "observation_id": "pmua-all",
        "dataset": "innovators_all",
        "record_type": "dashboard",
        "raw_file": "dashboards/innovators_all.json",
        "file_sha256": HASH,
        "row_locator": uri("f2_target_household", "dashboards/innovators_all.json"),
    }
    pmua = {
        "source_observations": [pmua_observation],
        "aggregate_summaries": [
            {
                "aggregate_id": "aggregate-all",
                "observation_id": "pmua-all",
                "source_file": "data/pmua_apptech/dashboards/innovators_all.json",
                "dashboard": "innovators",
                "entity_type": "innovator_aggregate",
                "year_filter": "",
                "reported_count": "10",
                "unit": "innovators",
                "status": "source_reported_nonadditive",
            }
        ],
        "aggregate_components": [
            {
                "component_id": "component-alpha",
                "aggregate_id": "aggregate-all",
                "observation_id": "pmua-all",
                "province_raw": "Alpha",
                "province_normalized": "Alpha",
                "province_code": "10",
                "component_kind": "innovator_province",
                "total_inno": "3",
                "levels_json": json.dumps(
                    {"1": 1, "2": 2, "3": 0, "4": 0}, separators=(",", ":")
                ),
            },
            {
                "component_id": "component-beta",
                "aggregate_id": "aggregate-all",
                "observation_id": "pmua-all",
                "province_raw": "Beta",
                "province_normalized": "Beta",
                "province_code": "20",
                "component_kind": "innovator_province",
                "total_inno": "7",
                "levels_json": json.dumps(
                    {"1": 0, "2": 1, "3": 2, "4": 4}, separators=(",", ":")
                ),
            },
        ],
    }

    dimensions = {
        "categories": [["Category", "Popularity"], ["Food", 5], ["Unused", 0]],
        "entityTypes": [["Entity Type", "Popularity"], ["Group", 5], ["Unused", 0]],
        "geography": [["Geography", "Popularity"]]
        + [[region, 0 if index == 5 else 1] for index, region in enumerate(REGIONS)],
        "provinces": [
            ["Province", "Community businesses"],
            ["Alpha", 5],
            ["Unused", 0],
        ],
    }
    impacts = []
    employment = [1, 2, 3, 4, 5, 0]
    workers = [1, 2, 3, 4, 5, 6]
    resources = [6, 5, 4, 3, 2, 1]
    for index in range(6):
        impacts.append(
            {
                "localEmployeeAmount": employment[index],
                "localEmployeeExpense": workers[index],
                "localResourceExpense": resources[index],
            }
        )
    dashboard_raw = {
        **dimensions,
        "geographyImpact": impacts,
        "impactSummary": {
            "totalEmplyeeAmount": 15,
            "totalEmployeeExpense": 21,
            "totalResourceExpense": 21,
        },
        "excludedResourceExpense": {"region": "Central", "amount": 7},
    }
    dashboard_observations = [
        dashboard_observation(key)
        for key in (
            "categories",
            "entityTypes",
            "geography",
            "provinces",
            "geographyImpact",
            "impactSummary",
            "excludedResourceExpense",
        )
    ]
    headers = []
    members = []
    labels = {
        "categories": "business_category",
        "entityTypes": "business_form",
        "geography": "region",
        "provinces": "province",
    }
    for dimension, raw_rows in dimensions.items():
        header_id = f"header-{dimension}"
        headers.append(
            {
                "header_id": header_id,
                "observation_id": f"dashboard-{dimension}",
                "dimension": dimension,
                "label_header_raw": raw_rows[0][0],
                "count_header_raw": raw_rows[0][1],
                "raw_locator": uri(
                    "f2_learning_dashboard",
                    "learning_dashboard.json",
                    f"{dimension}/0",
                ),
                "treatment": "retained_as_display_header_excluded_from_facts",
            }
        )
        for position, raw_row in enumerate(raw_rows[1:], 1):
            members.append(
                {
                    "count_member_id": f"member-{dimension}-{position}",
                    "observation_id": f"dashboard-{dimension}",
                    "header_id": header_id,
                    "dimension": dimension,
                    "dimension_label": labels[dimension],
                    "position": str(position),
                    "label_raw": raw_row[0],
                    "count": str(raw_row[1]),
                    "unit": "source-reported businesses",
                    "raw_locator": uri(
                        "f2_learning_dashboard",
                        "learning_dashboard.json",
                        f"{dimension}/{position}",
                    ),
                    "nonadditive_group": "synthetic-reported-businesses",
                    "filter_support": "count_dimension_only",
                }
            )
    regionals = []
    impact_components = []
    field_metadata = {
        "localEmployeeAmount": ("reported_monthly_employment", "people/month"),
        "localEmployeeExpense": ("worker_payments", "THB/month"),
        "localResourceExpense": ("resource_spending", "THB/month"),
    }
    for position, (region, raw_impact) in enumerate(zip(REGIONS, impacts), 1):
        regional_id = f"regional-{position}"
        regionals.append(
            {
                "regional_impact_id": regional_id,
                "observation_id": "dashboard-geographyImpact",
                "position": str(position),
                "region_raw": region,
                "region_mapping_basis": "reviewed source position",
                "raw_locator": uri(
                    "f2_learning_dashboard",
                    "learning_dashboard.json",
                    f"geographyImpact/{position - 1}",
                ),
            }
        )
        for raw_field, amount in raw_impact.items():
            kind, unit = field_metadata[raw_field]
            impact_components.append(
                {
                    "component_id": f"impact-{position}-{raw_field}",
                    "regional_impact_id": regional_id,
                    "observation_id": "dashboard-geographyImpact",
                    "position": str(position),
                    "region_raw": region,
                    "raw_field": raw_field,
                    "metric_kind": kind,
                    "amount": str(amount),
                    "unit": unit,
                    "raw_locator": uri(
                        "f2_learning_dashboard",
                        "learning_dashboard.json",
                        f"geographyImpact/{position - 1}/{raw_field}",
                    ),
                }
            )
    summary_metadata = {
        "totalEmplyeeAmount": ("reported_monthly_employment_total", "people/month"),
        "totalEmployeeExpense": ("totalEmployeeExpense", "THB/month"),
        "totalResourceExpense": ("totalResourceExpense", "THB/month"),
    }
    impact_summaries = []
    for raw_field, amount in dashboard_raw["impactSummary"].items():
        stable_name, unit = summary_metadata[raw_field]
        impact_summaries.append(
            {
                "summary_metric_id": f"summary-{raw_field}",
                "observation_id": "dashboard-impactSummary",
                "raw_field": raw_field,
                "stable_metric_name": stable_name,
                "amount": str(amount),
                "unit": unit,
                "raw_locator": uri(
                    "f2_learning_dashboard",
                    "learning_dashboard.json",
                    f"impactSummary/{raw_field}",
                ),
                "treatment": "reconciliation_only_not_additional_contribution",
            }
        )
    dashboard = {
        "source_observations": dashboard_observations,
        "count_dimension_headers": headers,
        "count_members": members,
        "regional_impacts": regionals,
        "impact_components": impact_components,
        "impact_summary_metrics": impact_summaries,
        "excluded_amounts": [
            {
                "excluded_amount_id": "excluded-resource",
                "observation_id": "dashboard-excludedResourceExpense",
                "region_raw": "Central",
                "amount": "7",
                "unit": "THB/month_assumed_for_K10B_only",
                "raw_locator": uri(
                    "f2_learning_dashboard",
                    "learning_dashboard.json",
                    "excludedResourceExpense",
                ),
                "meaning_status": "reviewed_unresolved",
                "treatment": "separate_component_used_only_under_K10B_assumption",
            }
        ],
    }

    area_raw_rows = [
        {"id": "source-one", "businessName": "Business One", "province": "Alpha"},
        {"id": "source-two", "businessName": "Business Two", "province": "Beta"},
    ]
    area_raw = {"data": area_raw_rows, "stats": {"totalRecords": 2}}
    area_observations = []
    businesses = []
    links = []
    participations = []
    contributions = []
    locations = []
    for index, (business_id, source_id, name, province, code) in enumerate(
        (
            ("business-one", "source-one", "Business One", "Alpha", "10"),
            ("business-two", "source-two", "Business Two", "Beta", "20"),
        )
    ):
        observation_id = f"area-observation-{index + 1}"
        area_observations.append(
            {
                "observation_id": observation_id,
                "source_id": source_id,
                "raw_file": "area_based.json",
                "raw_file_sha256": HASH,
                "row_locator": uri(
                    "f2_learning_area_based", "area_based.json", f"data/{index}"
                ),
            }
        )
        businesses.append(
            {
                "business_id": business_id,
                "display_name": name,
                "source_ids_json": json.dumps([source_id]),
                "eligible_k08": "True",
            }
        )
        links.append(
            {
                "business_id": business_id,
                "observation_id": observation_id,
                "source_id": source_id,
                "link_basis": "one_source_listing_one_provisional_unit",
            }
        )
        participations.append(
            {
                "participation_id": f"participation-{index + 1}",
                "business_id": business_id,
                "observation_id": observation_id,
            }
        )
        contributions.append(
            {
                "measure": "K08_participating_businesses_provisional",
                "business_id": business_id,
                "province_code": "",
                "contribution_status": "provisional_unit",
                "evidence_observation_ids_json": json.dumps([observation_id]),
                "location_role": "programme_business_location",
            }
        )
        locations.append(
            {
                "location_id": f"location-{index + 1}",
                "observation_id": observation_id,
                "business_id": business_id,
                "location_role": "programme_business_location",
                "province_raw": province,
                "province_code": code,
                "resolution_status": "hierarchy_match",
            }
        )
    area = {
        "source_observations": area_observations,
        "businesses": businesses,
        "business_observation_links": links,
        "participations": participations,
        "measure_contributions": contributions,
        "locations": locations,
    }

    source_tables = {
        "f2_target_household": pmua,
        "f2_learning_dashboard": dashboard,
        "f2_learning_area_based": area,
    }
    raw_inputs = {
        "f2_target_household": bundle(
            "f2_target_household",
            "innovators_all",
            "dashboards/innovators_all.json",
            pmua_raw,
        ),
        "f2_learning_dashboard": bundle(
            "f2_learning_dashboard",
            "learning_dashboard_response",
            "learning_dashboard.json",
            dashboard_raw,
        ),
        "f2_learning_area_based": bundle(
            "f2_learning_area_based",
            "area_based_response",
            "area_based.json",
            area_raw,
        ),
    }
    return source_tables, raw_inputs


def test_builds_exact_results_with_source_ids_leaf_citations_and_no_input_mutation():
    source_tables, raw_inputs = aggregate_fixture()
    original_sources = copy.deepcopy(source_tables)
    original_raw = copy.deepcopy(raw_inputs)

    tables = build_tables(source_tables, {}, raw_inputs, geography=None)

    assert source_tables == original_sources
    assert raw_inputs == original_raw
    assert {
        row["measure_id"]: row["value_exact"] for row in tables["aggregate_results"]
    } == {
        "K02": "10",
        "C08_REPORTED_BUSINESSES": "5",
        "K09": "15",
        "K10": "0.000042",
        "C10_ALTERNATIVE": "0.000028",
        "C08_PARTICIPATING": "2",
    }
    assert all(
        list(row) == TABLE_COLUMNS[table]
        for table, rows in tables.items()
        for row in rows
    )

    k02 = next(
        row
        for row in tables["aggregate_breakdowns"]
        if row["measure_id"] == "K02" and row["member_id"] == "10:1"
    )
    assert {
        key: k02[key]
        for key in (
            "breakdown_id",
            "amount_unit",
            "evidence_table",
            "evidence_key",
            "evidence_id",
            "source_level",
        )
    } == {
        "breakdown_id": "province_level",
        "amount_unit": "person",
        "evidence_table": "sources/f2_target_household/aggregate_components",
        "evidence_key": "component_id",
        "evidence_id": "component-alpha",
        "source_level": "1",
    }
    assert k02["raw_locator"].endswith("#/prov_data/Alpha/levels/1")

    zero_members = [
        row
        for row in tables["aggregate_breakdowns"]
        if row["measure_id"] == "C08_REPORTED_BUSINESSES" and row["amount"] == "0"
    ]
    assert {row["breakdown_id"] for row in zero_members} == {
        "categories",
        "entityTypes",
        "geography",
        "provinces",
    }
    employee = next(
        row for row in tables["aggregate_breakdowns"] if row["measure_id"] == "K09"
    )
    assert employee["breakdown_id"] == "components"
    assert employee["component"] == "localEmployeeAmount"
    assert employee["evidence_key"] == "component_id"
    assert employee["evidence_id"] == employee["member_id"]
    assert employee["raw_locator"].endswith("/localEmployeeAmount")

    k10_members = {
        row["member_id"]
        for row in tables["aggregate_breakdowns"]
        if row["measure_id"] == "K10"
    }
    alternative = [
        row
        for row in tables["aggregate_breakdowns"]
        if row["measure_id"] == "C10_ALTERNATIVE"
    ]
    excluded = next(
        row for row in alternative if row["member_id"] == "excluded-resource"
    )
    assert "excluded-resource" not in k10_members
    assert excluded["component"] == "excludedResourceExpense"
    assert excluded["amount_unit"] == "THB/month_assumed"
    assert excluded["raw_locator"].endswith("#/excludedResourceExpense/amount")

    assert tables["entity_contributions"] == [
        {
            "entity_id": "business-one",
            "label": "Business One",
            "measure_id": "C08_PARTICIPATING",
        },
        {
            "entity_id": "business-two",
            "label": "Business Two",
            "measure_id": "C08_PARTICIPATING",
        },
    ]
    assert tables["province_memberships"][0]["evidence_key"] == "location_id"
    assert tables["province_memberships"][0]["evidence_id"] == "location-1"

    for row in tables["aggregate_breakdowns"]:
        source, table = row["evidence_table"].split("/")[1:]
        assert any(
            candidate[row["evidence_key"]] == row["evidence_id"]
            for candidate in source_tables[source][table]
        )


@pytest.mark.parametrize(
    "mutation, message",
    [
        ("province_imbalance", "within a province"),
        ("missing_zero_member", "members do not cover"),
        ("missing_zero_region", "does not cover all six source regions"),
    ],
)
def test_rejects_incomplete_components_even_when_national_total_is_unchanged(
    mutation, message
):
    source_tables, raw_inputs = aggregate_fixture()
    if mutation == "province_imbalance":
        source_tables["f2_target_household"]["aggregate_components"][0][
            "levels_json"
        ] = '{"1":2,"2":2,"3":0,"4":0}'
        source_tables["f2_target_household"]["aggregate_components"][1][
            "levels_json"
        ] = '{"1":0,"2":0,"3":2,"4":4}'
        raw = raw_inputs["f2_target_household"]["datasets"]["innovators_all"]
        raw["prov_data"]["Alpha"]["levels"] = {"1": 2, "2": 2, "3": 0, "4": 0}
        raw["prov_data"]["Beta"]["levels"] = {"1": 0, "2": 0, "3": 2, "4": 4}
    elif mutation == "missing_zero_member":
        rows = source_tables["f2_learning_dashboard"]["count_members"]
        rows[:] = [
            row for row in rows if row["count_member_id"] != "member-categories-2"
        ]
    else:
        rows = source_tables["f2_learning_dashboard"]["impact_components"]
        rows[:] = [
            row for row in rows if row["component_id"] != "impact-6-localEmployeeAmount"
        ]

    with pytest.raises(PipelineError, match=message):
        build_tables(source_tables, {}, raw_inputs, geography=None)


def test_rejects_wrong_source_leaf_even_when_observation_file_is_valid():
    source_tables, raw_inputs = aggregate_fixture()
    component = source_tables["f2_learning_dashboard"]["impact_components"][0]
    component["raw_locator"] = uri(
        "f2_target_household",
        "dashboards/innovators_all.json",
        "prov_data/Alpha/levels/1",
    )

    with pytest.raises(PipelineError, match="stale or foreign raw locator"):
        build_tables(source_tables, {}, raw_inputs, geography=None)


def test_rejects_participation_evidence_owned_by_another_business():
    source_tables, raw_inputs = aggregate_fixture()
    contribution = source_tables["f2_learning_area_based"]["measure_contributions"][0]
    contribution["evidence_observation_ids_json"] = '["area-observation-2"]'

    with pytest.raises(PipelineError, match="wrong-business or incomplete evidence"):
        build_tables(source_tables, {}, raw_inputs, geography=None)
