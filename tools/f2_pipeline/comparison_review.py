"""Bind an explicit internal-review disposition to the compared release bytes."""

from pathlib import Path
import re

from .common import PipelineError, digest, load_json, read_csv
from .full_comparison import (
    _display,
    _exact_number,
    _filters,
    _material_differences,
    _value,
)
from .comparison_core import _compare_identity
from .commerce_comparison import _commerce_identity
from .validation import load_release_tables, verify_release


def _validate_semantic_evidence(report, tables):
    """Recompute current identity populations without reading the frozen reference."""
    identities = {
        **{
            name: _compare_identity(lambda _: [], tables, name)
            for name in ("innovations", "people")
        },
        **{
            name + "s": _commerce_identity(lambda _: [], tables, name)
            for name in ("operator", "offering")
        },
    }
    if set(report["identities"]) != set(identities):
        raise PipelineError("Comparison lacks complete identity evidence")
    for name, expected in identities.items():
        actual = report["identities"][name]
        if set(actual) != set(expected):
            raise PipelineError("Comparison lacks complete identity detail")
        for key, value in expected.items():
            if isinstance(value, dict) and "current_distinct" in value:
                if actual[key]["current_distinct"] != value["current_distinct"]:
                    raise PipelineError("Comparison identity population is stale")
            elif key != "reference_group_count" and actual[key] != value:
                raise PipelineError("Comparison current identity detail is stale")
    relationship_fields = (
        "source_operator_offering_edge_id",
        "source_operator_id",
        "global_operator_id",
        "source_offering_id",
        "global_offering_id",
        "relationship",
    )
    relationships = len(
        {
            tuple(row.get(field, "") for field in relationship_fields)
            for row in tables["domains/commerce/operator_offering_edges"]
        }
    )
    if (
        report["commerce"]["operator_offering_relationships"]["current_distinct"]
        != relationships
    ):
        raise PipelineError("Comparison commerce relationship population is stale")
    expected_semantics = {
        "innovation_identity": report["identities"]["innovations"]["grouping"],
        "people_identity": report["identities"]["people"]["grouping"],
        "operator_identity": report["identities"]["operators"]["source_to_global"],
        "offering_identity": report["identities"]["offerings"]["source_to_global"],
        "commerce_relationships": report["commerce"]["operator_offering_relationships"],
        "category_memberships": report["measures"]["K12"]["category_pairs"],
    }
    if report["semantic_deltas"] != expected_semantics:
        raise PipelineError("Comparison lacks the exact six semantic assessments")
    for delta in report["semantic_deltas"].values():
        if (
            any(
                type(delta[key]) is not int or delta[key] < 0
                for key in (
                    "added",
                    "removed",
                    "current_distinct",
                    "reference_distinct",
                )
            )
            or len(delta["added_keys"]) != delta["added"]
            or len(delta["removed_keys"]) != delta["removed"]
            or delta["current_distinct"] - delta["reference_distinct"]
            != delta["added"] - delta["removed"]
        ):
            raise PipelineError(
                "Comparison semantic delta is incomplete or inconsistent"
            )
    required_commerce = {
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
        "baseline_review_dispositions",
        "additional_review_dispositions",
        "current_extra_detail_tables_not_packaged_by_v2",
    }
    required_coverage = {
        "source_citation_assertions",
        "identity_comparison_note",
        "assertion_memberships",
        "reference_dispositions",
        "current_dispositions",
        "source_province_memberships",
    }
    if (
        not required_commerce <= report["commerce"].keys()
        or not required_coverage <= report["programme_coverage"].keys()
    ):
        raise PipelineError("Comparison lacks complete commerce or programme evidence")
    coverage = report["programme_coverage"]["source_citation_assertions"]
    if coverage["current_rows"] != len(
        tables["domains/programme_coverage/coverage_assertions"]
    ):
        raise PipelineError("Comparison current programme evidence is stale")


def _validate_current_evidence(report, release_dir, manifest):
    """Check report completeness and current facts; trusted review pins the reference."""
    tables = load_release_tables(release_dir)
    results = load_json(release_dir / "results.json")
    definitions = {row["measure_id"]: row for row in tables["measure_dictionary"]}
    coverage = {row["measure_id"]: row for row in tables["province_coverage"]}
    catalog = {row["table"]: row for row in read_csv(release_dir / "table_catalog.csv")}
    try:
        for measure in manifest["enabled_measures"]:
            detail = report["measures"][measure]
            current = results[measure]
            if detail["current_value"] != current["value"]:
                raise PipelineError(
                    "Comparison result differs from the current release"
                )
            for group, table, fields in (
                ("entities", "entity_contributions", ("entity_id",)),
                (
                    "province_pairs",
                    "province_memberships",
                    ("entity_id", "province_code"),
                ),
                (
                    "category_pairs",
                    "category_memberships",
                    ("entity_id", "category_code"),
                ),
            ):
                count = len(
                    {
                        tuple(row[field] for field in fields)
                        for row in tables[table]
                        if row["measure_id"] == measure
                    }
                )
                delta = detail[group]
                if delta["current_distinct"] != count or any(
                    type(delta[key]) is not int or delta[key] < 0
                    for key in (
                        "added",
                        "removed",
                        "reference_distinct",
                        "current_distinct",
                    )
                ):
                    raise PipelineError(
                        "Comparison membership evidence is incomplete or stale"
                    )
                if (
                    len(delta["added_keys"]) != delta["added"]
                    or len(delta["removed_keys"]) != delta["removed"]
                ):
                    raise PipelineError(
                        "Comparison membership deltas lack their complete keys"
                    )
            row = definitions[measure]
            expected_result = {
                "value": _exact_number(current.get("value_exact", current["value"])),
                "display": _display(current.get("display_value")),
                "unit": current["unit"],
                "status": current["status"],
            }
            expected_metadata = {
                field: _value(row.get(field))
                for field in (
                    "display_order",
                    "kind",
                    "label_th",
                    "requested_label_th",
                    "unit",
                    "status",
                    "formula",
                    "scope",
                    "drilldown",
                    "limitations",
                )
            }
            expected_metadata.update(
                filters=_filters(
                    row.get("supported_filters_json", row.get("supported_filters"))
                ),
                parent_relationship=_value(row.get("parent_measure_id")),
            )
            for group, expected in (
                ("result", expected_result),
                ("metadata", expected_metadata),
            ):
                actual = report["measure_metadata"][measure][group]
                if set(actual) != set(expected) or any(
                    not isinstance(actual[key], dict)
                    or not {"reference", "current"} <= actual[key].keys()
                    or actual[key]["current"] != value
                    for key, value in expected.items()
                ):
                    raise PipelineError(
                        "Comparison metadata evidence is incomplete or stale"
                    )
            current_coverage = coverage[measure]
            for public_key, field in (
                ("overall_entities", "national_total"),
                ("with_supported_province", "with_province"),
                ("without_supported_province", "without_province"),
                ("province_sum_is_additive", "province_sum_is_additive"),
            ):
                pair = report["geography_coverage"][measure][public_key]
                if "reference" not in pair or pair["current"] != _value(
                    current_coverage.get(field)
                ):
                    raise PipelineError(
                        "Comparison geography evidence is incomplete or stale"
                    )
        mapped = report["detail_tables"]["mapped"]
        if set(mapped) != set(catalog):
            raise PipelineError(
                "Comparison does not cover the complete current table catalog"
            )
        for name, spec in catalog.items():
            detail = mapped[name]
            if detail["current_path"] != spec["path"]:
                raise PipelineError(
                    "Comparison table path differs from current catalog"
                )
            if detail["status"] == "current_only":
                count = detail["current_row_count"]
            elif detail["status"] == "compared":
                count = detail["content"]["current_rows"]
                if detail["current_fields"] != sorted(_value(spec["fields_json"])):
                    raise PipelineError(
                        "Comparison table fields differ from current catalog"
                    )
            else:
                raise PipelineError("Comparison has an unresolved table mapping")
            if count != int(spec["row_count"]):
                raise PipelineError(
                    "Comparison table count differs from current catalog"
                )
        for delta in report["aggregate_facts"].values():
            if delta["current_rows"] != len(tables["aggregate_breakdowns"]):
                raise PipelineError("Comparison aggregate evidence is incomplete")
        if set(report["aggregate_facts"]) != {
            "members_and_amounts",
            "source_citations",
        }:
            raise PipelineError(
                "Comparison must distinguish aggregate keys and source facts"
            )
        if (
            not {
                "person_assertion_detail",
                "downstream_commerce_person_links",
                "scope",
                "status",
            }
            <= report["person_sources_effects"].keys()
        ):
            raise PipelineError("Comparison lacks the post-v2 person-code assessment")
        _validate_semantic_evidence(report, tables)
        if report["material_differences"] != _material_differences(report):
            raise PipelineError(
                "Comparison omits or changes material-difference dispositions"
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise PipelineError("Malformed or sparse full-comparison evidence") from exc


def verify_comparison_review(release_dir, comparison_path, review_path) -> dict:
    """Accept internal review evidence only; this never grants public-field approval."""
    if comparison_path is None or review_path is None:
        raise PipelineError(
            "Full public staging requires comparison and internal-review files"
        )
    release_dir = Path(release_dir)
    manifest = verify_release(release_dir, require_complete=True)
    if (
        manifest.get("profile") != "full"
        or manifest.get("publication_status") != "internal_only"
    ):
        raise PipelineError("Comparison review requires the full internal release")
    comparison_path, review_path = Path(comparison_path), Path(review_path)
    report, review = load_json(comparison_path), load_json(review_path)
    release_hash = digest(release_dir / "manifest.json")
    report_hash = digest(comparison_path)
    required_sections = {
        "measures",
        "measure_metadata",
        "geography_coverage",
        "detail_tables",
        "person_sources_effects",
        "material_differences",
        "aggregate_facts",
        "semantic_deltas",
        "identities",
        "commerce",
        "programme_coverage",
    }
    if not isinstance(report, dict) or not required_sections <= report.keys():
        raise PipelineError("Comparison lacks required full-release evidence")
    if (
        report.get("release_id") != manifest["release_id"]
        or report.get("reference_release") != "f2-dashboard-snapshot-v2"
        or report.get("current_manifest_sha256") != release_hash
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(report.get("reference_manifest_sha256", ""))
        )
        or any(
            not isinstance(report[key], dict)
            for key in ("measures", "measure_metadata", "geography_coverage")
        )
        or set(report["measures"]) != set(manifest["enabled_measures"])
        or set(report["measure_metadata"]) != set(manifest["enabled_measures"])
        or set(report["geography_coverage"]) != set(manifest["enabled_measures"])
    ):
        raise PipelineError(
            "Comparison does not cover these exact release bytes/measures"
        )
    if (
        not isinstance(review, dict)
        or review.get("schema_version") != 1
        or review.get("release_id") != manifest["release_id"]
        or review.get("release_manifest_sha256") != release_hash
        or review.get("comparison_sha256") != report_hash
        or review.get("reference_manifest_sha256")
        != report["reference_manifest_sha256"]
        or review.get("review_status") != "accepted"
        or review.get("scope") != "internal_release_only"
    ):
        raise PipelineError("Missing, stale or non-internal comparison acceptance")
    differences = report["material_differences"]
    decisions = review.get("decisions")
    if not isinstance(differences, list) or not isinstance(decisions, list):
        raise PipelineError(
            "Comparison differences and decisions must be explicit lists"
        )
    identifiers = [row.get("id") for row in differences if isinstance(row, dict)]
    decision_ids = [
        row.get("difference_id") for row in decisions if isinstance(row, dict)
    ]
    if (
        len(identifiers) != len(differences)
        or len(decision_ids) != len(decisions)
        or any(
            not isinstance(value, str) or not value
            for value in identifiers + decision_ids
        )
        or len(identifiers) != len(set(identifiers))
        or len(decision_ids) != len(set(decision_ids))
        or set(identifiers) != set(decision_ids)
    ):
        raise PipelineError(
            "Every material difference needs exactly one review disposition"
        )
    for decision in decisions:
        if decision.get("status") != "accepted" or any(
            not isinstance(decision.get(field), str) or not decision[field].strip()
            for field in ("reason", "acceptance_basis")
        ):
            raise PipelineError("Unresolved difference or missing acceptance rationale")
    _validate_current_evidence(report, release_dir, manifest)
    return {
        "release_id": manifest["release_id"],
        "release_manifest_sha256": release_hash,
        "reference_manifest_sha256": report["reference_manifest_sha256"],
        "comparison_sha256": report_hash,
        "review_sha256": digest(review_path),
        "accepted_differences": len(decisions),
        "scope": "internal_release_only",
        "public_promotion_approved": False,
    }
