"""Full internal v3 comparison against the manifest-verified frozen v2 release."""

from __future__ import annotations

import csv
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from .common import PipelineError, digest, load_json, local_path, read_csv
from .comparison_core import _baseline_reader, _compare_measure_tables
from .commerce_comparison import COMMERCE_MEASURES, compare_commerce_content
from .aggregate_comparison import compare_aggregate_rows
from .aggregate_measures import AGGREGATE_AND_RELATED_MEASURES, NULL_MEASURES
from .validation import load_release_tables, verify_release

FULL_MEASURES = frozenset(COMMERCE_MEASURES) | AGGREGATE_AND_RELATED_MEASURES
ROOT_TABLES = frozenset(
    {
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
    }
)
LEGACY_PREFIXES = {
    "domains/activities/": "support/derived/cross-source/activities-coverage-v1/",
    "domains/areas/": "support/derived/cross-source/cultural-areas-v1/",
    "domains/innovations/": "support/derived/cross-source/innovations-v1/",
    "domains/people/": "support/derived/cross-source/people-v1/",
    "domains/commerce/": "support/derived/cross-source/offerings-v2/",
    "domains/programme_coverage/": "support/derived/cross-source/activities-coverage-v1/",
    "sources/f2_cultural_market_civil/": "support/derived/pilots/atlocal-v1/",
    "sources/f2_culturalmap_university/": "support/derived/pilots/cultural-map-v1/",
    "sources/f2_icommunity/": "support/derived/pilots/icommunity-v1/",
    "sources/f2_target_household/": "support/derived/pilots/pmua-apptech-v1/",
    "sources/f2_learning_area_based/": "support/derived/pilots/learning-area-based-v1/",
    "sources/f2_learning_dashboard/": "support/derived/pilots/learning-dashboard-v1/",
}


def _value(value):
    if value in (None, "", "null"):
        return None
    if isinstance(value, str) and value[:1] in "[{":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value


def _filters(value):
    value = _value(value)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [part for part in str(value).split(",") if part]


def _exact_number(value):
    value = _value(value)
    if value is None:
        return None
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except ArithmeticError:
        return value


def _display(value):
    return "" if value in (None, "") else str(value)


def _row_key(row):
    def normalized(key, value):
        if key.endswith("_json"):
            return _value(value)
        return str(value) if isinstance(value, bool) else value

    return tuple(
        (
            key,
            json.dumps(
                normalized(key, value),
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        )
        for key, value in sorted(row.items())
    )


def _counter_delta(old, new):
    before, after = (
        Counter(_row_key(row) for row in old),
        Counter(_row_key(row) for row in new),
    )
    removed, added = before - after, after - before
    return {
        "reference_rows": sum(before.values()),
        "current_rows": sum(after.values()),
        "added": sum(added.values()),
        "removed": sum(removed.values()),
        "content_matches": not added and not removed,
    }


def _metadata_comparison(baseline, tables, results):
    old_rows = {row["measure_id"]: row for row in baseline("measure_dictionary.csv")}
    new_rows = {row["measure_id"]: row for row in tables["measure_dictionary"]}
    old_results = {
        row["measure_id"]: row
        for name in ("kpi_results.csv", "companion_results.csv")
        for row in baseline(name)
    }
    report = {}
    for measure in sorted(FULL_MEASURES):
        if (
            measure not in old_rows
            or measure not in new_rows
            or measure not in old_results
        ):
            raise PipelineError(
                f"Full comparison lacks required measure detail: {measure}"
            )
        current = results.get(measure)
        if not isinstance(current, dict):
            raise PipelineError(f"Full comparison lacks current result: {measure}")
        old, new = old_rows[measure], new_rows[measure]
        result = {
            "value": {
                "reference": _exact_number(
                    old_results[measure].get(
                        "value_exact", old_results[measure].get("value")
                    )
                ),
                "current": _exact_number(
                    current.get("value_exact", current.get("value"))
                ),
            },
            "display": {
                "reference": _display(old_results[measure].get("display_value")),
                "current": _display(current.get("display_value")),
            },
            "unit": {
                "reference": _value(old_results[measure].get("unit", old.get("unit"))),
                "current": current.get("unit"),
            },
            "status": {
                "reference": _value(
                    old_results[measure].get("status", old.get("status"))
                ),
                "current": current.get("status"),
            },
        }
        metadata = {
            "display_order": {
                "change": "added_metadata",
                "reference": None,
                "current": _value(new.get("display_order")),
            },
            "kind": {
                "reference": _value(old.get("kind")),
                "current": _value(new.get("kind")),
            },
            "label_th": {
                "reference": _value(old.get("label_th")),
                "current": _value(new.get("label_th")),
            },
            "requested_label_th": {
                "reference": _value(old.get("requested_label_th")),
                "current": _value(new.get("requested_label_th")),
            },
            "unit": {
                "reference": _value(old.get("unit")),
                "current": _value(new.get("unit")),
            },
            "status": {
                "reference": _value(old.get("status")),
                "current": _value(new.get("status")),
            },
            "formula": {
                "reference": _value(old.get("formula")),
                "current": _value(new.get("formula")),
            },
            "scope": {
                "reference": _value(old.get("scope")),
                "current": _value(new.get("scope")),
            },
            "drilldown": {
                "reference": _value(old.get("drilldown")),
                "current": _value(new.get("drilldown")),
            },
            "filters": {
                "reference": _filters(old.get("filters")),
                "current": _filters(
                    new.get("supported_filters_json", new.get("supported_filters"))
                ),
            },
            "limitations": {
                "reference": _value(old.get("limitations")),
                "current": _value(new.get("limitations")),
            },
            "parent_relationship": {
                "reference": _value(old.get("parent_kpi")),
                "current": _value(new.get("parent_measure_id")),
            },
        }
        report[measure] = {"result": result, "metadata": metadata}
    return report


def _reference_path(name, path, reference_files):
    if path in reference_files:
        return path
    for current_prefix, old_prefix in LEGACY_PREFIXES.items():
        if name.startswith(current_prefix):
            candidate = old_prefix + name.removeprefix(current_prefix) + ".csv"
            if candidate in reference_files:
                return candidate
    basename = Path(path).name
    candidates = sorted(
        item
        for item in reference_files
        if item.endswith(".csv") and Path(item).name == basename
    )
    return candidates[0] if len(candidates) == 1 else None


def _reference_fields(reference_dir, reference_path):
    with local_path(reference_dir, reference_path).open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        return next(csv.reader(handle), [])


def _catalog_comparison(reference_dir, reference_manifest, baseline, tables, catalog):
    current_catalog = {row["table"]: row for row in catalog}
    if not current_catalog:
        raise PipelineError("Full comparison lacks current table catalog")
    reference_files = set(reference_manifest["files"])
    compared, used = {}, set()
    for name, row in sorted(current_catalog.items()):
        reference_path = _reference_path(name, row["path"], reference_files)
        if reference_path is None:
            compared[name] = {
                "status": "current_only",
                "current_path": row["path"],
                "current_row_count": int(row["row_count"]),
            }
            continue
        used.add(reference_path)
        old_rows, new_rows = baseline(reference_path), tables[name]
        old_fields = _reference_fields(reference_dir, reference_path)
        new_fields = sorted(_value(row.get("fields_json")) or [])
        delta = _counter_delta(old_rows, new_rows)
        compared[name] = {
            "status": "compared",
            "reference_path": reference_path,
            "current_path": row["path"],
            "reference_fields": old_fields,
            "current_fields": new_fields,
            "path_only_change": reference_path != row["path"]
            and delta["content_matches"],
            "content": delta,
        }
    return {
        "mapped": compared,
        "reference_only": sorted(
            path
            for path in reference_files
            if path.endswith(".csv") and path not in used
        ),
        "unmatched_current": sorted(
            name for name, detail in compared.items() if detail["status"] != "compared"
        ),
    }


def _coverage_comparison(baseline, tables):
    old_rows = {row["measure_id"]: row for row in baseline("province_coverage.csv")}
    new_rows = {row["measure_id"]: row for row in tables["province_coverage"]}
    if set(new_rows) != FULL_MEASURES:
        raise PipelineError("Full comparison lacks current measure coverage detail")
    return {
        measure: {
            "status": "compared" if measure in old_rows else "missing_reference",
            "overall_entities": {
                "reference": _value(old_rows.get(measure, {}).get("overall_entities")),
                "current": _value(new_rows[measure].get("national_total")),
            },
            "with_supported_province": {
                "reference": _value(
                    old_rows.get(measure, {}).get("entities_with_supported_province")
                ),
                "current": _value(new_rows[measure].get("with_province")),
            },
            "without_supported_province": {
                "reference": _value(
                    old_rows.get(measure, {}).get("entities_without_supported_province")
                ),
                "current": _value(new_rows[measure].get("without_province")),
            },
            "province_sum_is_additive": {
                "reference": _value(
                    old_rows.get(measure, {}).get("province_sum_is_additive")
                ),
                "current": _value(new_rows[measure].get("province_sum_is_additive")),
            },
        }
        for measure in sorted(FULL_MEASURES)
    }


def _changed(delta):
    return bool(delta.get("added") or delta.get("removed"))


def _material_differences(report):
    ids = set()

    def add(identifier):
        ids.add(identifier)

    for measure, detail in report["measures"].items():
        if detail["value_difference"] not in (None, 0) or any(
            _changed(detail[key])
            for key in ("entities", "province_pairs", "category_pairs")
        ):
            add(f"measure:{measure}")
    for measure, detail in report["measure_metadata"].items():
        if any(
            pair["reference"] != pair["current"]
            for group in (detail["result"], detail["metadata"])
            for pair in group.values()
        ):
            add(f"metadata:{measure}")
    for measure, detail in report["geography_coverage"].items():
        if detail["status"] != "compared" or any(
            pair["reference"] != pair["current"]
            for key, pair in detail.items()
            if key != "status"
        ):
            add(f"geography:{measure}")
    for table, detail in report["detail_tables"]["mapped"].items():
        if (
            detail["status"] != "compared"
            or detail["reference_fields"] != detail["current_fields"]
            or not detail["content"]["content_matches"]
        ):
            add(f"detail:{table}")
    for table in report["detail_tables"]["unmatched_current"]:
        add(f"detail:{table}")
    for path in report["detail_tables"]["reference_only"]:
        add(f"reference_only:{path}")
    for name, delta in report["aggregate_facts"].items():
        if _changed(delta):
            add(f"aggregate:{name}")
    for group, delta in report["semantic_deltas"].items():
        if _changed(delta):
            add(f"semantic:{group}")
    return [
        {"id": identifier, "review_disposition": "pending_review"}
        for identifier in sorted(ids)
    ]


def verify_reference_inventory(reference_dir: Path, manifest: dict) -> None:
    """Verify even reference-only files before accepting a frozen comparison basis."""
    for name, metadata in manifest["files"].items():
        path = local_path(reference_dir, name)
        if (
            not isinstance(metadata, dict)
            or not path.is_file()
            or path.stat().st_size != metadata.get("bytes")
            or digest(path) != metadata.get("sha256")
        ):
            raise PipelineError("Frozen reference inventory hash/size mismatch")


def compare_full_release(release_dir: Path, reference_dir: Path) -> dict:
    manifest = verify_release(Path(release_dir))
    if (
        manifest.get("profile") != "full"
        or manifest.get("release_id") != "f2-dashboard-snapshot-v3"
        or manifest.get("complete") is not True
        or manifest.get("publication_status") != "internal_only"
        or set(manifest.get("enabled_measures", [])) != FULL_MEASURES
        or len(manifest.get("enabled_measures", [])) != 21
    ):
        raise PipelineError("Comparison requires the complete internal v3 full release")
    reference_manifest, baseline = _baseline_reader(Path(reference_dir))
    verify_reference_inventory(Path(reference_dir), reference_manifest)
    tables, results = (
        load_release_tables(release_dir),
        load_json(Path(release_dir) / "results.json"),
    )
    missing = sorted(ROOT_TABLES - tables.keys())
    if missing:
        raise PipelineError(
            "Full comparison lacks required root detail: " + ", ".join(missing)
        )
    report = compare_commerce_content(
        manifest, reference_manifest, baseline, tables, results
    )
    report["current_manifest_sha256"] = digest(Path(release_dir) / "manifest.json")
    report["reference_manifest_sha256"] = digest(Path(reference_dir) / "manifest.json")
    report["profile_measures"] = sorted(FULL_MEASURES)
    report["measures"].update(
        _compare_measure_tables(
            baseline, tables, results, sorted(AGGREGATE_AND_RELATED_MEASURES)
        )
    )
    old_results = {
        row["measure_id"]: row
        for name in ("kpi_results.csv", "companion_results.csv")
        for row in baseline(name)
    }
    for measure in sorted(AGGREGATE_AND_RELATED_MEASURES):
        old, current = old_results[measure], results[measure]
        report["measures"][measure]["unit_matches"] = old.get("unit") == current.get(
            "unit"
        )
        report["measures"][measure]["status_matches"] = old.get(
            "status"
        ) == current.get("status")
        if measure in NULL_MEASURES:
            report["measures"][measure]["explicit_null_matches"] = (
                old.get("value") in (None, "", "null") and current.get("value") is None
            )
        else:
            report["measures"][measure]["value_difference_exact"] = format(
                Decimal(str(current.get("value_exact", current["value"])))
                - Decimal(str(old["value"])),
                "f",
            )
    report["aggregate_facts"] = {
        "members_and_amounts": compare_aggregate_rows(
            baseline("aggregate_breakdowns.csv"), tables["aggregate_breakdowns"]
        ),
        "source_citations": compare_aggregate_rows(
            baseline("aggregate_breakdowns.csv"),
            tables["aggregate_breakdowns"],
            citation=True,
        ),
    }
    report["measure_metadata"] = _metadata_comparison(baseline, tables, results)
    report["geography_coverage"] = _coverage_comparison(baseline, tables)
    report["detail_tables"] = _catalog_comparison(
        Path(reference_dir),
        reference_manifest,
        baseline,
        tables,
        read_csv(Path(release_dir) / "table_catalog.csv"),
    )
    report["semantic_deltas"] = {
        "innovation_identity": report["identities"]["innovations"]["grouping"],
        "people_identity": report["identities"]["people"]["grouping"],
        "operator_identity": report["identities"]["operators"]["source_to_global"],
        "offering_identity": report["identities"]["offerings"]["source_to_global"],
        "commerce_relationships": report["commerce"]["operator_offering_relationships"],
        "category_memberships": report["measures"]["K12"]["category_pairs"],
    }
    people_detail = report["detail_tables"]["mapped"].get(
        "domains/people/person_assertions", {"status": "missing_current_detail"}
    )
    commerce_people = report["detail_tables"]["mapped"].get(
        "domains/commerce/person_operator_links", {"status": "missing_current_detail"}
    )
    report["person_sources_effects"] = {
        "status": "pending_review",
        "person_assertion_detail": people_detail,
        "downstream_commerce_person_links": commerce_people,
        "scope": "Observed snapshot deltas in person assertions and downstream commerce links; this report does not assign causal attribution to a code path.",
    }
    report["namespace_path_changes"] = {
        name: detail
        for name, detail in report["detail_tables"]["mapped"].items()
        if detail.get("path_only_change")
    }
    report["material_differences"] = _material_differences(report)
    report["review_status"] = "pending_review"
    report["interpretation"] = (
        "Full internal comparison evidence only. Namespace/path changes are separate from semantic and content deltas; unmatched and missing reference details remain pending review."
    )
    return report
