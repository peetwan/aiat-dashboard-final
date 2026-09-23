import json
from pathlib import Path

import pytest

from tools.f2_pipeline.common import (
    PipelineError,
    digest,
    read_csv,
    write_csv,
    write_json,
)
from tools.f2_pipeline.comparison_review import verify_comparison_review
from tools.f2_pipeline.full_comparison import (
    _material_differences,
    _metadata_comparison,
)
from tools.f2_pipeline.comparison_core import _compare_identity
from tools.f2_pipeline.commerce_comparison import _commerce_identity
from tools.f2_pipeline.aggregate_measures import NULL_MEASURES
from tools.f2_pipeline.public_stage import verify_public_stage
from tools.f2_pipeline.validation import load_release_tables


@pytest.fixture
def accepted_comparison(tmp_path):
    definitions = json.loads(Path("config/f2_pipeline/measures.c02-v2.json").read_text())[
        "measures"
    ]
    measures = [row["measure_id"] for row in definitions]
    release = tmp_path / "release"
    results = {
        row["measure_id"]: {
            "value": None if row["measure_id"] in NULL_MEASURES else 0,
            "value_exact": None if row["measure_id"] in NULL_MEASURES else "0",
            "display_value": "" if row["measure_id"] in NULL_MEASURES else "0",
            "unit": row["unit"],
            "status": row["status"],
        }
        for row in definitions
    }
    rows = {
        "measure_dictionary": definitions,
        "province_coverage": [
            {
                "measure_id": measure,
                "national_total": 0,
                "with_province": 0,
                "without_province": 0,
                "province_sum_is_additive": False,
            }
            for measure in measures
        ],
        "entity_contributions": [],
        "province_memberships": [],
        "category_memberships": [],
        "aggregate_breakdowns": [],
        "domains/people/person_assertions": [],
        "domains/commerce/person_operator_links": [],
        "domains/innovations/innovation_crosswalk": [],
        "domains/people/person_crosswalk": [],
        "domains/commerce/operator_crosswalk": [],
        "domains/commerce/offering_crosswalk": [],
        "domains/commerce/operator_offering_edges": [],
        "domains/programme_coverage/coverage_assertions": [],
    }
    catalog = []
    for name, data in rows.items():
        fields = (
            list(data[0])
            if data
            else ["measure_id", "entity_id", "province_code", "category_code"]
        )
        write_csv(release / (name + ".csv"), data, fields)
        catalog.append(
            {
                "table": name,
                "path": name + ".csv",
                "row_count": len(data),
                "fields_json": fields,
            }
        )
    write_csv(release / "table_catalog.csv", catalog)
    write_json(release / "results.json", results)
    write_json(
        release / "manifest.json",
        {
            "schema_version": 1,
            "validation_status": "passed",
            "profile": "full",
            "release_id": "f2-dashboard-snapshot-v3",
            "complete": True,
            "publication_status": "internal_only",
            "enabled_measures": measures,
            "files": [
                {
                    "path": path.relative_to(release).as_posix(),
                    "sha256": digest(path),
                    "size": path.stat().st_size,
                }
                for path in sorted(release.rglob("*"))
                if path.is_file()
            ],
        },
    )
    tables = load_release_tables(release)
    baseline = lambda name: (
        tables["measure_dictionary"]
        if name == "measure_dictionary.csv"
        else [{"measure_id": measure, **result} for measure, result in results.items()]
    )
    delta = {
        "added": 0,
        "removed": 0,
        "added_keys": [],
        "removed_keys": [],
        "reference_distinct": 0,
        "current_distinct": 0,
    }
    mapped = {
        spec["table"]: {
            "status": "current_only",
            "current_path": spec["path"],
            "current_row_count": int(spec["row_count"]),
        }
        for spec in read_csv(release / "table_catalog.csv")
    }
    report = {
        "release_id": "f2-dashboard-snapshot-v3",
        "reference_release": "f2-dashboard-snapshot-v2",
        "current_manifest_sha256": digest(release / "manifest.json"),
        "reference_manifest_sha256": "a" * 64,
        "measures": {
            measure: {
                "current_value": result["value"],
                "value_difference": 0,
                "entities": delta,
                "province_pairs": delta,
                "category_pairs": delta,
            }
            for measure, result in results.items()
        },
        "measure_metadata": _metadata_comparison(baseline, tables, results),
        "geography_coverage": {
            measure: {
                "status": "compared",
                **{
                    key: {"reference": value, "current": value}
                    for key, value in (
                        ("overall_entities", "0"),
                        ("with_supported_province", "0"),
                        ("without_supported_province", "0"),
                        ("province_sum_is_additive", "False"),
                    )
                },
            }
            for measure in measures
        },
        "detail_tables": {
            "mapped": mapped,
            "reference_only": [],
            "unmatched_current": sorted(mapped),
        },
        "person_sources_effects": {
            "status": "pending_review",
            "scope": "synthetic comparison",
            "person_assertion_detail": mapped["domains/people/person_assertions"],
            "downstream_commerce_person_links": mapped[
                "domains/commerce/person_operator_links"
            ],
        },
        "aggregate_facts": {
            key: {"current_rows": 0, "reference_rows": 0, "added": 0, "removed": 0}
            for key in ("members_and_amounts", "source_citations")
        },
        "identities": {
            **{
                name: _compare_identity(lambda _: [], tables, name)
                for name in ("innovations", "people")
            },
            **{
                name + "s": _commerce_identity(lambda _: [], tables, name)
                for name in ("operator", "offering")
            },
        },
        "commerce": {
            **{
                key: delta
                for key in (
                    "reviewed_candidate_innovation_contexts",
                    "offering_identities",
                    "family_definitions",
                    "family_memberships",
                    "review_coverage",
                    "operator_offering_relationships",
                    "reviewed_relationships",
                    "listing_evidence",
                    "seller_evidence",
                    "location_subjects_and_relationship_context",
                )
            },
            "baseline_review_dispositions": {},
            "additional_review_dispositions": {},
            "current_extra_detail_tables_not_packaged_by_v2": {},
        },
        "programme_coverage": {
            "source_citation_assertions": {
                **delta,
                "current_rows": 0,
                "reference_rows": 0,
            },
            "identity_comparison_note": "Synthetic empty coverage",
            "assertion_memberships": delta,
            "source_province_memberships": delta,
            "reference_dispositions": {},
            "current_dispositions": {},
        },
    }
    report["semantic_deltas"] = {
        "innovation_identity": report["identities"]["innovations"]["grouping"],
        "people_identity": report["identities"]["people"]["grouping"],
        "operator_identity": report["identities"]["operators"]["source_to_global"],
        "offering_identity": report["identities"]["offerings"]["source_to_global"],
        "commerce_relationships": report["commerce"]["operator_offering_relationships"],
        "category_memberships": report["measures"]["K12"]["category_pairs"],
    }
    report["material_differences"] = _material_differences(report)
    report_path, review_path = tmp_path / "comparison.json", tmp_path / "review.json"
    write_json(report_path, report)
    review = {
        "schema_version": 1,
        "release_id": report["release_id"],
        "release_manifest_sha256": report["current_manifest_sha256"],
        "reference_manifest_sha256": report["reference_manifest_sha256"],
        "comparison_sha256": digest(report_path),
        "review_status": "accepted",
        "scope": "internal_release_only",
        "decisions": [
            {
                "difference_id": difference["id"],
                "status": "accepted",
                "reason": "Synthetic migration evidence checked in this fixture.",
                "acceptance_basis": "Explicit trusted test review input",
            }
            for difference in report["material_differences"]
        ],
    }
    write_json(review_path, review)
    return release, report_path, review_path, review


def test_review_is_hash_bound_and_never_grants_public_approval(accepted_comparison):
    release, comparison, path, review = accepted_comparison
    proof = verify_comparison_review(release, comparison, path)
    assert proof["accepted_differences"] == len(review["decisions"])
    assert proof["public_promotion_approved"] is False
    comparison.write_text(comparison.read_text() + "\n")
    with pytest.raises(PipelineError, match="stale"):
        verify_comparison_review(release, comparison, path)


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "rejected", "blank_reason", "public_scope"]
)
def test_incomplete_or_wrong_scope_review_fails(accepted_comparison, change):
    release, comparison, path, review = accepted_comparison
    if change == "missing":
        review["decisions"] = []
    elif change == "duplicate":
        review["decisions"] *= 2
    elif change == "rejected":
        review["decisions"][0]["status"] = "rejected"
    elif change == "blank_reason":
        review["decisions"][0]["reason"] = " "
    else:
        review["scope"] = "public_publication"
    write_json(path, review)
    with pytest.raises(PipelineError):
        verify_comparison_review(release, comparison, path)


def test_trusted_review_cannot_accept_sparse_or_stale_current_evidence(
    accepted_comparison,
):
    release, comparison, path, review = accepted_comparison
    report = json.loads(comparison.read_text())
    report["measure_metadata"]["K02"] = {}
    write_json(comparison, report)
    review["comparison_sha256"] = digest(comparison)
    write_json(path, review)
    with pytest.raises(PipelineError, match="sparse"):
        verify_comparison_review(release, comparison, path)


@pytest.mark.parametrize(
    "section", ["semantic_deltas", "identities", "commerce", "programme_coverage"]
)
def test_empty_semantic_sections_fail_even_with_a_rehashed_trusted_review(
    accepted_comparison, section
):
    release, comparison, path, review = accepted_comparison
    report = json.loads(comparison.read_text())
    report[section] = {}
    write_json(comparison, report)
    review["comparison_sha256"] = digest(comparison)
    write_json(path, review)
    with pytest.raises(PipelineError, match="sparse|complete|exact"):
        verify_comparison_review(release, comparison, path)


def test_public_stage_requires_complete_exact_file_set(tmp_path):
    write_json(
        tmp_path / "manifest.json",
        {
            "release_id": "f2-dashboard-snapshot-v3",
            "complete": True,
            "publication_status": "staged_for_review",
            "owner_checkpoint_required": True,
            "validation_status": "passed",
            "staged_for_review": True,
            "additional_field_review_status": "pending_owner_acceptance",
            "publication_approval_claimed": False,
            "files": [],
        },
    )
    with pytest.raises(PipelineError, match="missing staged artifact"):
        verify_public_stage(tmp_path)
