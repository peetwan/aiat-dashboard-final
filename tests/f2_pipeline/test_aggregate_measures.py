import copy
import json
from pathlib import Path

import pytest

from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.aggregate_comparison import compare_aggregate_rows
from tools.f2_pipeline.aggregate_measures import (
    ROOT_ADDITIONS,
    assemble_aggregate_measures,
)

CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config/f2_pipeline"




def test_assembly_preserves_inputs_and_separates_population_relationships():
    definitions = json.loads((CONFIG_ROOT / "measures.json").read_text())["measures"]
    old = {name: [] for name in ROOT_ADDITIONS}
    old["entity_contributions"] = [
        {"measure_id": "C02_COMMUNITY", "entity_id": "person", "label": "Synthetic"}
    ]
    additional = {name: [] for name in ROOT_ADDITIONS}
    additional["entity_contributions"] = [
        {
            "measure_id": "C08_PARTICIPATING",
            "entity_id": "business",
            "label": "Synthetic",
        }
    ]
    before = copy.deepcopy((old, additional, definitions))
    root = assemble_aggregate_measures(old, additional, definitions)
    assert (old, additional, definitions) == before
    assert (
        root["entity_contributions"]
        == old["entity_contributions"] + additional["entity_contributions"]
    )
    assert {row["measure_id"] for row in root["measure_methodology"]} == {
        "K06",
        "K08",
        "K11A",
        "K11B",
    }
    assert all(row["reason"] for row in root["measure_methodology"])
    assert len(root["measure_relationships"]) == 7
    assert all(
        row["additive_to_headline"] is False
        and row["reconciles_with_headline"] is False
        for row in root["measure_relationships"]
    )
    with pytest.raises(PipelineError, match="already been assembled"):
        assemble_aggregate_measures(root, additional, definitions)


def test_aggregate_comparison_preserves_decimal_and_duplicate_occurrences():
    old = {
        "measure_id": "K10",
        "breakdown_id": "components",
        "member_id": "m",
        "amount": "0.10",
        "amount_unit": "THB/month",
        "result_divisor": "1000000",
        "evidence_table": "support/derived/pilots/learning-dashboard-v1/impact_components.csv",
        "evidence_key": "component_id",
        "evidence_id": "m",
        "raw_locator": "data/f2_learning_dashboard/run/learning_dashboard.json#geographyImpact/0/localEmployeeExpense",
        "region": "North",
        "component": "localEmployeeExpense",
    }
    current = {
        **old,
        "amount": "0.1",
        "evidence_table": "sources/f2_learning_dashboard/impact_components",
        "raw_locator": "evidence://f2_learning_dashboard/run/learning_dashboard.json.gz#geographyImpact/0/localEmployeeExpense",
    }
    assert compare_aggregate_rows([old], [current], citation=True)["added"] == 0
    duplicate = compare_aggregate_rows([old], [current, current], citation=True)
    assert duplicate["added"] == 1 and duplicate["removed"] == 0
    changed = compare_aggregate_rows([old], [{**current, "amount": "0.100001"}])
    assert changed["added"] == changed["removed"] == 1
    renamed = {**current, "member_id": "source-qualified-member"}
    assert compare_aggregate_rows([old], [renamed])["added"] == 1
    assert compare_aggregate_rows([old], [renamed], citation=True)["added"] == 0


def test_aggregate_validation_rejects_duplicate_entity_detail_links():
    from tools.f2_pipeline.aggregate_measures import validate_aggregate_tables

    definitions = json.loads((CONFIG_ROOT / "measures.json").read_text())["measures"]
    root = {name: [] for name in ROOT_ADDITIONS}
    root["entity_contributions"] = [
        {
            "measure_id": "C08_PARTICIPATING",
            "entity_id": "business",
            "label": "Synthetic",
        }
    ]
    root["evidence_links"] = [
        {
            "measure_id": "C08_PARTICIPATING",
            "entity_id": "business",
            "record_id": "one",
        },
        {
            "measure_id": "C08_PARTICIPATING",
            "entity_id": "business",
            "record_id": "two",
        },
    ]
    with pytest.raises(PipelineError, match="evidence_links unique complete keys"):
        validate_aggregate_tables(root, {}, {}, definitions, [])
