from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tools.f2_pipeline.common import PipelineError, digest
from tools.f2_pipeline.full_comparison import (
    FULL_MEASURES,
    _catalog_comparison,
    _material_differences,
    _metadata_comparison,
    verify_reference_inventory,
)
from tools.f2_pipeline.full_release import validate_full_release_contract
from tools.f2_pipeline.inputs import load_build_config

CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config/f2_pipeline"


def _definitions():
    return [
        {
            "measure_id": measure,
            "kind": "headline" if index < 14 else "companion",
            "display_order": index,
            "label_th": measure,
            "requested_label_th": measure,
            "unit": "unit",
            "formula": "formula",
            "scope": "scope",
            "status": "available_snapshot",
            "supported_filters": [],
            "permitted_filter_combinations": [[]],
            "drilldown": "detail",
            "limitations": "limitation",
            "parent_measure_id": None,
        }
        for index, measure in enumerate(sorted(FULL_MEASURES))
    ]


def test_successor_full_configs_are_complete_and_checkpoint_config_is_not_runnable():
    pending, _, _ = load_build_config(CONFIG_ROOT / "v3-c02-review-v2.json")
    accepted, _, _ = load_build_config(CONFIG_ROOT / "v3-c02-accepted-v1.json")
    for full in (pending, accepted):
        assert full["profile"] == "full"
        assert full["complete"] is True
        assert full["publication_status"] == "internal_only"
        assert full["release_id"] == "f2-dashboard-snapshot-v3"
        assert set(full["enabled_measures"]) == FULL_MEASURES
        assert "C02_BROADER" not in full["enabled_measures"]
    assert accepted["private_revision_id"] == (
        "f2-dashboard-snapshot-v3-c02-accepted-v1"
    )
    with pytest.raises(PipelineError, match="Only complete full"):
        load_build_config(CONFIG_ROOT / "phase6-checkpoint.json")


def test_full_root_contract_requires_every_result_coverage_and_dictionary_field():
    definitions = _definitions()
    root = {
        name: []
        for name in (
            "aggregate_breakdowns",
            "category_memberships",
            "entity_contributions",
            "evidence_links",
            "eligibility_evidence",
            "measure_dictionary",
            "province_coverage",
            "province_memberships",
            "provinces",
            "validation_checks",
        )
    }
    root["measure_dictionary"] = definitions
    root["province_coverage"] = [
        {"measure_id": row["measure_id"]} for row in definitions
    ]
    results = {row["measure_id"]: {"value": None} for row in definitions}
    assert (
        validate_full_release_contract(root, results, definitions)["status"] == "passed"
    )
    incomplete = copy.deepcopy(root)
    incomplete["province_coverage"].pop()
    with pytest.raises(PipelineError, match="coverage"):
        validate_full_release_contract(incomplete, results, definitions)


def test_metadata_comparison_preserves_nulls_display_and_formula_and_fails_missing_detail():
    definitions = _definitions()
    old_dictionary = [
        {
            **row,
            "supported_filters": "[]",
            "formula": "old formula" if row["measure_id"] == "K06" else row["formula"],
        }
        for row in definitions
    ]
    current = copy.deepcopy(definitions)
    current_by_id = {row["measure_id"]: row for row in current}
    current_by_id["K06"]["formula"] = "new formula"
    results = {
        row["measure_id"]: {
            "value": None if row["measure_id"] == "K06" else 1,
            "display_value": "Unavailable" if row["measure_id"] == "K06" else "1",
            "unit": row["unit"],
            "status": row["status"],
        }
        for row in current
    }
    old_results = [
        {
            "measure_id": row["measure_id"],
            "value": "" if row["measure_id"] == "K06" else "1",
            "display_value": "Unavailable" if row["measure_id"] == "K06" else "1",
            "unit": row["unit"],
            "status": row["status"],
        }
        for row in current
    ]
    baseline = lambda name: {
        "measure_dictionary.csv": old_dictionary,
        "kpi_results.csv": old_results[:14],
        "companion_results.csv": old_results[14:],
    }[name]
    report = _metadata_comparison(baseline, {"measure_dictionary": current}, results)
    assert report["K06"]["result"]["value"] == {"reference": None, "current": None}
    assert report["K06"]["metadata"]["formula"] == {
        "reference": "old formula",
        "current": "new formula",
    }
    with pytest.raises(PipelineError, match="required measure detail"):
        _metadata_comparison(baseline, {"measure_dictionary": current[:-1]}, results)


def test_material_differences_ignore_zero_and_report_content_aggregate_and_semantic_changes():
    unchanged = {
        "measures": {
            "K01A": {
                "value_difference": 0,
                "entities": {"added": 0, "removed": 0},
                "province_pairs": {"added": 0, "removed": 0},
                "category_pairs": {"added": 0, "removed": 0},
            }
        },
        "measure_metadata": {
            "K01A": {
                "result": {"value": {"reference": 1, "current": 1}},
                "metadata": {"formula": {"reference": "same", "current": "same"}},
            }
        },
        "geography_coverage": {
            "K01A": {
                "status": "compared",
                "overall_entities": {"reference": 1, "current": 1},
            }
        },
        "detail_tables": {
            "mapped": {
                "domains/people/person_assertions": {
                    "status": "compared",
                    "reference_fields": ["id"],
                    "current_fields": ["id"],
                    "content": {"content_matches": True},
                }
            },
            "unmatched_current": [],
            "reference_only": [],
        },
        "aggregate_facts": {"members_and_amounts": {"added": 0, "removed": 0}},
        "semantic_deltas": {"people_identity": {"added": 0, "removed": 0}},
    }
    assert _material_differences(unchanged) == []
    changed = copy.deepcopy(unchanged)
    changed["measure_metadata"]["K01A"]["result"]["value"] = {
        "reference": None,
        "current": 1,
    }
    changed["detail_tables"]["mapped"]["domains/people/person_assertions"][
        "content"
    ] = {
        "reference_rows": 1,
        "current_rows": 1,
        "added": 1,
        "removed": 1,
        "content_matches": False,
    }
    changed["aggregate_facts"]["members_and_amounts"] = {"added": 1, "removed": 0}
    changed["semantic_deltas"]["people_identity"] = {"added": 1, "removed": 0}
    ids = [item["id"] for item in _material_differences(changed)]
    assert ids == [
        "aggregate:members_and_amounts",
        "detail:domains/people/person_assertions",
        "metadata:K01A",
        "semantic:people_identity",
    ]


def test_catalog_comparison_reads_header_only_frozen_table_schema(tmp_path):
    (tmp_path / "header_only.csv").write_text("id,label\n", encoding="utf-8")
    report = _catalog_comparison(
        tmp_path,
        {"files": {"header_only.csv": {}}},
        lambda name: [],
        {"header_only": []},
        [
            {
                "table": "header_only",
                "path": "header_only.csv",
                "row_count": "0",
                "fields_json": '["id", "label"]',
            }
        ],
    )
    assert report["mapped"]["header_only"]["reference_fields"] == ["id", "label"]
    assert report["mapped"]["header_only"]["content"]["content_matches"] is True


def test_reference_only_file_tampering_invalidates_the_comparison_basis(tmp_path):
    path = tmp_path / "reference-only.json"
    path.write_text("{}")
    manifest = {"files": {path.name: {"bytes": 2, "sha256": digest(path)}}}
    verify_reference_inventory(tmp_path, manifest)
    path.write_text("[]")
    with pytest.raises(PipelineError, match="inventory hash"):
        verify_reference_inventory(tmp_path, manifest)
