"""Shared semantic comparison helpers for complete F2 releases."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .common import PipelineError, digest, load_json, local_path, read_csv

ENTITY_MEASURES = (
    "K01B",
    "K03",
    "K04",
    "C04_LISTED",
    "C02_COMMUNITY",
    "C08_ASSESSED_PEOPLE",
    "C08_INCREASED_PEOPLE",
    "K12",
)


def _baseline_reader(root: Path):
    manifest = load_json(root / "manifest.json")
    if manifest.get("release_id") != "f2-dashboard-snapshot-v2":
        raise PipelineError("Comparison requires the explicitly frozen v2 reference")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise PipelineError("Frozen v2 manifest lacks file map")

    def read(name: str) -> list[dict[str, str]]:
        metadata = files.get(name)
        if not isinstance(metadata, dict):
            raise PipelineError("Frozen comparison table is not in its manifest")
        path = local_path(root, name)
        if (
            not path.is_file()
            or path.stat().st_size != metadata.get("bytes")
            or digest(path) != metadata.get("sha256")
        ):
            raise PipelineError("Frozen comparison table hash mismatch")
        return read_csv(path)

    return manifest, read


def _as_number(value: Any) -> Any:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number.is_integer() else number


def _set_delta(old: set[tuple], new: set[tuple]) -> dict[str, Any]:
    return {
        "reference_distinct": len(old),
        "current_distinct": len(new),
        "added": len(new - old),
        "removed": len(old - new),
        "added_keys": sorted(new - old),
        "removed_keys": sorted(old - new),
    }


def _groups(
    rows: list[dict], group_key: str, member_key
) -> dict[tuple[str, ...], set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    owners = {}
    for row in rows:
        group, member = row.get(group_key, ""), member_key(row)
        if not group or not member:
            raise PipelineError(
                "Identity crosswalk lacks a required group or member key"
            )
        if member in owners:
            raise PipelineError("Identity source member has repeated ownership")
        owners[member] = group
        grouped[str(group)].add(member)
    return {tuple(sorted(members)): members for members in grouped.values()}


def _source_local_member(row: dict) -> str:
    source, local = str(row.get("source", "")), str(row.get("source_local_id", ""))
    if not source or not local:
        raise PipelineError("People identity crosswalk lacks source/source_local_id")
    return source + ":" + local


def _innovation_local_groups(rows: list[dict]) -> set[tuple[str, ...]]:
    def member(row):
        source, local = (
            str(row.get("source", "")),
            str(row.get("local_innovation_id", "")),
        )
        if not source or not local:
            raise PipelineError("Innovation crosswalk lacks source/local_innovation_id")
        return source + ":" + local

    return set(_groups(rows, "global_innovation_id", member))


def _effective_dispositions(rows: list[dict]) -> dict[str, int]:
    result: dict[str, int] = defaultdict(int)
    for row in rows:
        disposition = (
            row.get("effective_decision")
            or row.get("decision")
            or row.get("review_decision")
        )
        if disposition:
            result[str(disposition)] += 1
    return dict(sorted(result.items()))


def _compare_identity(
    read, current: dict[str, list[dict]], kind: str
) -> dict[str, Any]:
    if kind == "innovations":
        reference_rows = read(
            "support/derived/cross-source/innovations-v1/innovation_crosswalk.csv"
        )
        current_rows = current.get("domains/innovations/innovation_crosswalk")
        if current_rows is None:
            raise PipelineError("Current innovation crosswalk is missing")
        reference_groups = {
            group: set(group) for group in _innovation_local_groups(reference_rows)
        }
        current_groups = {
            group: set(group) for group in _innovation_local_groups(current_rows)
        }
        decisions = current.get("domains/innovations/identity_decisions", [])
    else:
        reference_rows = read(
            "support/derived/cross-source/people-v1/person_crosswalk.csv"
        )
        current_rows = current.get("domains/people/person_crosswalk")
        if current_rows is None:
            raise PipelineError("Current people crosswalk is missing")
        reference_groups = _groups(
            reference_rows, "global_person_id", _source_local_member
        )
        current_groups = _groups(current_rows, "global_person_id", _source_local_member)
        decisions = current.get("domains/people/identity_decisions", [])
    reference_keys, current_keys = set(reference_groups), set(current_groups)
    return {
        "reference_group_count": len(reference_keys),
        "current_group_count": len(current_keys),
        "grouping": _set_delta(reference_keys, current_keys),
        "member_keys": _set_delta(
            set().union(*reference_groups.values()) if reference_groups else set(),
            set().union(*current_groups.values()) if current_groups else set(),
        ),
        "effective_reviewed_dispositions": _effective_dispositions(decisions),
    }


def _compare_measure_tables(baseline, tables, current_results, measure_ids):
    """Compare semantic populations through manifest-verified reference reads."""
    if not isinstance(current_results, dict):
        raise PipelineError("Current identity results must be an object")
    old_kpi = {row["measure_id"]: row for row in baseline("kpi_results.csv")}
    old_companion = {
        row["measure_id"]: row for row in baseline("companion_results.csv")
    }
    current_contributions = tables.get("entity_contributions", [])
    current_provinces = tables.get("province_memberships", [])
    current_categories = tables.get("category_memberships", [])
    old_contributions = baseline("entity_contributions.csv")
    old_provinces = baseline("province_memberships.csv")
    old_categories = baseline("category_memberships.csv")
    measures = {}
    for measure in measure_ids:
        old_result = old_kpi.get(measure, old_companion.get(measure))
        new_result = current_results.get(measure)
        if old_result is None or not isinstance(new_result, dict):
            raise PipelineError(
                f"Identity comparison requires measure in both releases: {measure}"
            )
        old_entities = {
            (row.get("entity_id", ""),)
            for row in old_contributions
            if row.get("measure_id") == measure
        }
        new_entities = {
            (row.get("entity_id", ""),)
            for row in current_contributions
            if row.get("measure_id") == measure
        }
        old_pairs = {
            (row.get("entity_id", ""), row.get("province_code", ""))
            for row in old_provinces
            if row.get("measure_id") == measure
        }
        new_pairs = {
            (row.get("entity_id", ""), row.get("province_code", ""))
            for row in current_provinces
            if row.get("measure_id") == measure
        }
        old_categories_set = {
            (row.get("entity_id", ""), row.get("category_code", ""))
            for row in old_categories
            if row.get("measure_id") == measure
        }
        new_categories_set = {
            (row.get("entity_id", ""), row.get("category_code", ""))
            for row in current_categories
            if row.get("measure_id") == measure
        }
        current_value, reference_value = (
            _as_number(new_result.get("value")),
            _as_number(old_result.get("value")),
        )
        measures[measure] = {
            "comparison_status": "compared",
            "reference_value": reference_value,
            "current_value": current_value,
            "value_difference": current_value - reference_value
            if isinstance(current_value, (int, float))
            and isinstance(reference_value, (int, float))
            else None,
            "entities": _set_delta(old_entities, new_entities),
            "province_pairs": _set_delta(old_pairs, new_pairs),
            "category_pairs": _set_delta(old_categories_set, new_categories_set),
        }
    return measures


