"""Build the review-only, full F2 public artifact set from a complete release."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.publication import (
    PublicationError,
    _embedded_source_provenance,
    _privacy_problems,
)

from .common import (
    PipelineError,
    canonical_json,
    digest,
    ensure_new_output,
    load_json,
    output_directory,
    read_csv,
    stable_id,
)
from .field_approval import (
    approval_review_status,
    validate_detail_owner_approval,
)
from .measure_query import MeasureQuery
from .validation import load_release_tables, verify_release

_SCHEMA = "f2-dashboard-v1"
_RELEASE_ID = "f2-dashboard-snapshot-v3"
_REQUIRED_POLICY = {
    "preview_count",
    "max_overview_bytes",
    "max_geography_bytes",
    "max_topic_bytes",
    "max_detail_child_bytes",
    "max_file_bytes",
    "limitations",
    "detail_policies",
    "sources",
    "publication_field_contexts",
    "staged_for_review",
    "owner_checkpoint_required",
    "additional_field_review_status",
    "publication_approval_claimed",
    "excluded_fields",
    "detail_field_contexts",
}
_DETAIL_MEASURES = {
    "K01B",
    "K03",
    "K04",
    "C04_LISTED",
    "K05",
    "K07",
    "C08_PARTICIPATING",
    "K12",
}
_C02_DETAIL_MEASURES = {"C02_COMMUNITY"}
_AGGREGATE_ONLY_PERSON_MEASURES = {
    "C08_ASSESSED_PEOPLE",
    "C08_INCREASED_PEOPLE",
}
_PERSON_MEASURES = set(_AGGREGATE_ONLY_PERSON_MEASURES) | {"C02_COMMUNITY"}
_SOURCE_REGION_MEASURES = {"K09", "K10", "C10_ALTERNATIVE"}
_SOURCE_REGION_SCHEME = "f2_learning_dashboard_source_regions_v1"
_SECTION_TITLES = {
    "K01A": "หลักฐานความครอบคลุมโครงการรายจังหวัด",
    "K01B": "พื้นที่วัฒนธรรม",
    "K02": "ยอดรวมนวัตกรที่แหล่งข้อมูลรายงาน",
    "K03": "กิจกรรมโครงการ",
    "K04": "นวัตกรรมที่มีหลักฐานความพร้อม",
    "K05": "ธุรกิจ ร้านค้า และกลุ่มผู้ดำเนินการ",
    "K06": "วิธีการและข้อจำกัด",
    "K07": "ตระกูลสินค้า บริการ และผลงาน",
    "K08": "วิธีการและข้อจำกัด",
    "K09": "การจ้างงานที่แหล่งข้อมูลรายงาน",
    "K10": "รายจ่ายในพื้นที่ที่แหล่งข้อมูลรายงาน",
    "K11A": "วิธีการและข้อจำกัด",
    "K11B": "วิธีการและข้อจำกัด",
    "K12": "รายการข้อมูลวัฒนธรรม",
    "C02_COMMUNITY": "ประชากรนวัตกรชุมชนที่เกี่ยวข้อง",
    "C04_LISTED": "นวัตกรรมที่มีรายการในแหล่งข้อมูล",
    "C08_PARTICIPATING": "ธุรกิจที่เข้าร่วม",
    "C08_REPORTED_BUSINESSES": "ยอดรวมธุรกิจที่แหล่งข้อมูลรายงาน",
    "C08_ASSESSED_PEOPLE": "ผู้ได้รับการประเมิน",
    "C08_INCREASED_PEOPLE": "ผู้ที่คะแนนเพิ่มขึ้น",
    "C10_ALTERNATIVE": "รายจ่ายทรัพยากรทางเลือก",
}
_CHOICE_LABELS = {
    "categories": "หมวดหมู่ธุรกิจ",
    "entityTypes": "ประเภทหน่วยข้อมูล",
    "geography": "ภูมิภาคตามแหล่งข้อมูล",
    "provinces": "จังหวัดตามแหล่งข้อมูล",
    "localEmployeeExpense": "ค่าจ้างแรงงานในพื้นที่",
    "localResourceExpense": "ค่าทรัพยากรในพื้นที่",
    "excludedResourceExpense": "ค่าทรัพยากรทางเลือกที่ไม่นับในผลหลัก",
}


@dataclass(frozen=True)
class FullProjectionReport:
    release_id: str
    output_dir: str
    publication_status: str
    file_count: int
    topic_count: int
    counts_by_measure: dict[str, dict[str, int | None]]
    detail_record_count: int
    withheld_disposition_count: int
    topic_sizes: dict[str, int]
    output_bytes: int


def _encoded_bytes(value: Any) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _encoded_size(value: Any) -> int:
    return len(_encoded_bytes(value))


def _write_compact(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_encoded_bytes(value))


def _policy(release_dir: Path) -> tuple[dict, str]:
    value = load_json(release_dir / "projection_policy.json")
    if not isinstance(value, dict) or _REQUIRED_POLICY - set(value):
        raise PipelineError("Full projection policy lacks required reviewed fields")
    if value.get("publication_status") != "staged_for_review":
        raise PipelineError("Full projection policy must be staged_for_review")
    approval = validate_detail_owner_approval(value)
    expected_status = approval_review_status(approval)
    if value.get("additional_field_review_status") != expected_status:
        raise PipelineError(
            "Full projection policy lacks the required owner field-review boundary"
        )
    limits = (
        "max_overview_bytes",
        "max_geography_bytes",
        "max_topic_bytes",
        "max_detail_child_bytes",
        "max_file_bytes",
    )
    if (
        not isinstance(value["preview_count"], int)
        or value["preview_count"] < 0
        or any(not isinstance(value[key], int) or value[key] <= 0 for key in limits)
        or not isinstance(value["limitations"], list)
        or not isinstance(value["detail_policies"], dict)
        or not isinstance(value["sources"], dict)
        or not isinstance(value["publication_field_contexts"], dict)
    ):
        raise PipelineError("Full projection policy has unsafe limits or contracts")
    if any(value[key] > value["max_file_bytes"] for key in limits[:-1]):
        raise PipelineError("A reviewed artifact budget exceeds the per-file ceiling")
    return value, digest(release_dir / "projection_policy.json")


def _common_result(selected: dict) -> dict:
    """Expose the specified public result cell; never serialize query internals."""
    row = selected["result"]
    return {
        key: row.get(key)
        for key in (
            "value",
            "value_exact",
            "display_value",
            "unit",
            "status",
            "availability",
            "scope_key",
            "requested_filters",
            "applied_filters",
            "unavailable_reason",
        )
    }


def _reconcile(query: MeasureQuery, stored: dict, measure_id: str) -> dict:
    selected = query.select()
    actual = _common_result(selected)
    expected = {key: stored.get(key) for key in actual}
    if actual != expected:
        raise PipelineError(f"Stored result does not reconcile: {measure_id}")
    return selected


def _source_registry(policy: dict) -> tuple[dict[str, dict], dict[str, str]]:
    by_id: dict[str, dict] = {}
    aliases: dict[str, str] = {}
    for logical_id, row in policy.get("sources", {}).items():
        if not isinstance(logical_id, str) or not isinstance(row, dict):
            raise PipelineError("Projection policy has invalid source metadata")
        source_id = row.get("source_id")
        system = row.get("originating_system")
        if (
            not isinstance(source_id, str)
            or not source_id
            or not isinstance(system, str)
            or not system
        ):
            raise PipelineError(
                "Projection source metadata lacks a source ID or system"
            )
        if source_id in by_id:
            raise PipelineError(f"Projection policy repeats source ID: {source_id}")
        by_id[source_id] = row
        variants = {
            logical_id,
            logical_id.replace("_", "-"),
            source_id,
            source_id.removeprefix("f2_"),
            source_id.removeprefix("f2_").replace("_", "-"),
        }
        for variant in variants:
            aliases[variant] = source_id
            aliases[variant + "-v1"] = source_id
    return by_id, aliases


def _source_id_for_reference(
    reference: Any,
    policy: dict,
    registry: tuple[dict[str, dict], dict[str, str]] | None = None,
) -> str | None:
    if not isinstance(reference, str) or not reference:
        return None
    by_id, aliases = registry or _source_registry(policy)
    if reference.startswith("sources/"):
        source_id = reference.split("/", 2)[1]
        return source_id if source_id in by_id else None
    if reference.startswith("evidence://"):
        source_id = reference.removeprefix("evidence://").split("/", 1)[0]
        return source_id if source_id in by_id else None
    clean = reference.removesuffix("-v1")
    return aliases.get(reference) or aliases.get(clean)


def _row_source_ids(
    row: dict,
    policy: dict,
    registry: tuple[dict[str, dict], dict[str, str]] | None = None,
) -> set[str]:
    registry = registry or _source_registry(policy)
    result: set[str] = set()
    for key in ("source", "source_id", "raw_source_id"):
        source_id = _source_id_for_reference(row.get(key), policy, registry)
        if source_id:
            result.add(source_id)
    for key in ("sources_json", "source_ids_json"):
        values = row.get(key, [])
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except json.JSONDecodeError:
                values = []
        if isinstance(values, list):
            for value in values:
                source_id = _source_id_for_reference(value, policy, registry)
                if source_id:
                    result.add(source_id)
    for key in ("table", "evidence_table", "raw_locator"):
        source_id = _source_id_for_reference(row.get(key), policy, registry)
        if source_id:
            result.add(source_id)
    return result


def _domain_source_ids(
    tables: dict,
    measure_ids: set[str],
    policy: dict,
    registry: tuple[dict[str, dict], dict[str, str]],
) -> set[str]:
    entity_ids = {
        measure_id: {
            str(row["entity_id"])
            for row in tables.get("entity_contributions", [])
            if row.get("measure_id") == measure_id and row.get("entity_id")
        }
        for measure_id in measure_ids
    }
    selected_rows: list[dict] = []
    if "K01B" in measure_ids:
        selected_rows.extend(
            row
            for row in tables.get("domains/areas/area_crosswalk", [])
            if str(row.get("global_area_id")) in entity_ids["K01B"]
        )
    if "K03" in measure_ids:
        selected_rows.extend(
            row
            for row in tables.get("domains/activities/global_activities", [])
            if str(row.get("global_activity_id")) in entity_ids["K03"]
        )
    innovation_ids = set().union(
        *(entity_ids.get(measure_id, set()) for measure_id in ("K04", "C04_LISTED"))
    )
    if innovation_ids:
        selected_rows.extend(
            row
            for row in tables.get("domains/innovations/innovation_crosswalk", [])
            if str(row.get("global_innovation_id")) in innovation_ids
        )
    if "K05" in measure_ids:
        selected_rows.extend(
            row
            for row in tables.get("domains/commerce/operator_crosswalk", [])
            if str(row.get("global_operator_id")) in entity_ids["K05"]
        )
    if "K07" in measure_ids:
        offering_ids = {
            str(row.get("global_offering_id"))
            for row in tables.get("domains/commerce/offering_family_members", [])
            if str(row.get("family_id")) in entity_ids["K07"]
        }
        selected_rows.extend(
            row
            for row in tables.get("domains/commerce/offering_crosswalk", [])
            if str(row.get("global_offering_id")) in offering_ids
        )
    person_ids = set().union(
        *(entity_ids.get(measure_id, set()) for measure_id in _PERSON_MEASURES)
    )
    if person_ids:
        for row in tables.get("domains/people/person_assertions", []):
            attached = row.get("attached_global_person_ids_json", [])
            if not isinstance(attached, list):
                attached = []
            if str(row.get("global_person_id")) in person_ids or person_ids & {
                str(value) for value in attached
            }:
                selected_rows.append(row)
    return (
        set().union(*(_row_source_ids(row, policy, registry) for row in selected_rows))
        if selected_rows
        else set()
    )


def _source_ids(
    tables: dict,
    measure_ids: Iterable[str],
    policy: dict | None = None,
    details_by_measure: dict | None = None,
) -> list[str]:
    """Resolve public source IDs from source paths, domain evidence, and details."""
    wanted = set(measure_ids)
    if policy is None:
        ids = set()
        for name in (
            "evidence_links",
            "eligibility_evidence",
            "province_memberships",
            "category_memberships",
            "aggregate_breakdowns",
        ):
            for row in tables.get(name, []):
                if row.get("measure_id") not in wanted:
                    continue
                for field in ("table", "evidence_table"):
                    reference = row.get(field)
                    if isinstance(reference, str) and reference.startswith("sources/"):
                        ids.add(reference.split("/", 2)[1])
        return sorted(ids)

    ids: set[str] = set()
    registry = _source_registry(policy)
    ids.update(_domain_source_ids(tables, wanted, policy, registry))
    for name in (
        "evidence_links",
        "eligibility_evidence",
        "province_memberships",
        "category_memberships",
        "aggregate_breakdowns",
    ):
        rows = tables.get(name, [])
        if not isinstance(rows, list):
            raise PipelineError(f"Malformed provenance table: {name}")
        for row in rows:
            if row.get("measure_id") not in wanted:
                continue
            ids.update(_row_source_ids(row, policy, registry))
            # Domain references are resolved through the measure's counted public IDs
            # above; source-table paths resolve directly here.
    if "K01A" in wanted:
        for row in tables.get("domains/programme_coverage/coverage_assertions", []):
            if row.get("disposition") == "qualifying_resolved":
                ids.update(_row_source_ids(row, policy, registry))
    if details_by_measure:
        for measure_id in wanted:
            for detail in (
                details_by_measure.get(measure_id, {}).get("details", {}).values()
            ):
                if isinstance(detail, dict):
                    values = detail.get("source_ids", [])
                    if isinstance(values, list):
                        ids.update(value for value in values if isinstance(value, str))
    approved = set(registry[0])
    if not ids <= approved:
        raise PipelineError(f"Unapproved source provenance: {sorted(ids - approved)}")
    return sorted(ids)


def _sources(policy: dict, source_ids: list[str]) -> list[dict]:
    """Select approved metadata for actual topic provenance."""
    registry = _source_registry(policy)[0]
    selected = []
    for source_id in source_ids:
        row = registry.get(source_id)
        if row is None:
            raise PipelineError(
                f"Topic provenance is not approved by policy: {source_id}"
            )
        metadata = {
            "source_id": source_id,
            "originating_system": row["originating_system"],
            "source_context_review": row.get("source_context_review"),
        }
        if isinstance(row.get("public_url"), str) and row["public_url"]:
            metadata["public_url"] = row["public_url"]
        selected.append(metadata)
    return selected


def _source_region_catalog(tables: dict, policy: dict) -> dict[str, dict]:
    rows = [
        row
        for row in tables.get("aggregate_breakdowns", [])
        if row.get("measure_id") in _SOURCE_REGION_MEASURES and row.get("region")
    ]
    labels = sorted({str(row["region"]) for row in rows})
    registry = _source_registry(policy)
    result = {}
    for label in labels:
        region_id = stable_id("source_region", _SOURCE_REGION_SCHEME, label)
        source_ids = sorted(
            set().union(
                *(
                    _row_source_ids(row, policy, registry)
                    for row in rows
                    if str(row.get("region")) == label
                )
            )
        )
        result[region_id] = {
            "source_region_id": region_id,
            "label_th": label,
            "scheme_id": _SOURCE_REGION_SCHEME,
            "source_ids": source_ids,
            "dashboard_region_link": None,
            "dashboard_region_link_status": "not_defined",
        }
    return result


def _select_public(
    query: MeasureQuery,
    filters: dict | None,
    source_regions: dict[str, dict] | None = None,
) -> dict:
    filters = dict(filters or {})
    if "source_region" not in filters:
        return query.select(filters)
    values = filters.pop("source_region")
    if not isinstance(values, list):
        return query.select({"source_region": values, **filters})
    source_regions = source_regions or {}
    if any(value not in source_regions for value in values):
        return query.select({"source_region": values, **filters})
    raw_values = [source_regions[value]["label_th"] for value in values]
    selected = query.select({"region": raw_values, **filters})
    result = dict(selected["result"])
    result["scope_key"] = "source_region/" + ",".join(values)
    for field in ("requested_filters", "applied_filters"):
        public_filters = dict(result.get(field, {}))
        if "region" in public_filters:
            public_filters["source_region"] = values
            del public_filters["region"]
        result[field] = public_filters
    return {**selected, "result": result}


def _safe_breakdowns(
    rows: list[dict],
    policy: dict | None = None,
    source_regions: dict[str, dict] | None = None,
) -> list[dict]:
    """Project stable aggregate members without internal locators or member keys."""
    region_by_label = {
        row["label_th"]: region_id for region_id, row in (source_regions or {}).items()
    }
    registry = _source_registry(policy) if policy is not None else None
    projected = []
    for row in sorted(rows, key=canonical_json):
        source_id = row.get("source_id")
        if policy is not None:
            source_id = _source_id_for_reference(
                row.get("evidence_table"), policy, registry
            )
            if source_id is None:
                raise PipelineError(
                    "Aggregate member lacks canonical source provenance"
                )
        item = {
            "item_id": stable_id(
                "aggregate_member",
                row.get("measure_id"),
                row.get("breakdown_id"),
                row.get("member_id"),
                source_id,
            ),
            "label": row.get("member_label")
            or row.get("province_name")
            or row.get("region")
            or row.get("component")
            or row.get("source_level"),
            "amount": row.get("amount"),
            "amount_unit": row.get("amount_unit"),
            "result_divisor": row.get("result_divisor"),
            "breakdown_id": row.get("breakdown_id"),
            "province_code": row.get("province_code") or None,
            "province_name_th": row.get("province_name") or None,
            "source_level": row.get("source_level") or None,
            "component": row.get("component") or None,
            "source_region_id": region_by_label.get(str(row.get("region")))
            if row.get("region")
            else None,
            "source_region_label_th": row.get("region") or None,
            "source_id": source_id,
        }
        projected.append(
            {key: value for key, value in item.items() if value is not None}
        )
    return projected


def _supporting_assertions(tables: dict, policy: dict) -> list[dict]:
    """Aggregate K01A support at a safe province/source/location-rule grain."""
    grouped: Counter[tuple[str, ...]] = Counter()
    registry = _source_registry(policy)
    for row in tables.get("domains/programme_coverage/coverage_assertions", []):
        source_id = _source_id_for_reference(row.get("source"), policy, registry)
        if not source_id:
            raise PipelineError(
                "K01A coverage assertion lacks canonical source provenance"
            )
        key = (
            str(row.get("province_code") or ""),
            str(row.get("province_name") or ""),
            source_id,
            str(row.get("location_role") or "unspecified"),
            str(row.get("disposition") or "unspecified"),
            str(row.get("evidence_kind") or "unspecified"),
            str(row.get("lineage_status") or "unspecified"),
            str(row.get("reason") or ""),
        )
        grouped[key] += 1
    return [
        {
            "province_code": key[0] or None,
            "province_name_th": key[1] or None,
            "source_id": key[2],
            "location_role": key[3],
            "disposition": key[4],
            "evidence_rule": key[5],
            "lineage_status": key[6],
            "reason": key[7] or None,
            "assertion_count": count,
        }
        for key, count in sorted(grouped.items())
    ]


def _withheld_summary(
    selected_ids: Iterable[str], details: dict, withheld: dict
) -> dict:
    counts = Counter(
        withheld.get(entity_id, "not_approved_for_public_detail")
        for entity_id in selected_ids
        if entity_id not in details
    )
    return dict(sorted(counts.items()))


def _scope(
    query: MeasureQuery,
    filters: dict,
    details: dict,
    preview_count: int,
    measure_id: str,
    *,
    withheld: dict | None = None,
    policy: dict | None = None,
    source_regions: dict[str, dict] | None = None,
    supporting_assertions: list[dict] | None = None,
    national: bool | None = None,
) -> dict:
    selected = _select_public(query, filters, source_regions)
    result = _common_result(selected)
    counted_ids = list(selected.get("entity_ids", []))
    ids = [entity_id for entity_id in counted_ids if entity_id in details]
    withheld = withheld or {}
    title = _SECTION_TITLES.get(measure_id, measure_id)
    section: dict[str, Any]
    if measure_id in _PERSON_MEASURES and not (
        measure_id in _C02_DETAIL_MEASURES and (policy or {}).get("c02_projection")
    ):
        section = {
            "section_id": measure_id.lower(),
            "title_th": title,
            "kind": "related_population",
            "measure_ids": [measure_id],
            "scope_key": result["scope_key"],
            "counted_total": result["value"],
            "reconciles_with_headline": False,
            "detail_availability": "not_applicable",
            "unavailable_reason": result["unavailable_reason"],
        }
    elif measure_id == "K01A":
        assertions = supporting_assertions or []
        province_values = filters.get("province")
        if province_values:
            assertions = [
                row for row in assertions if row.get("province_code") in province_values
            ]
        section = {
            "section_id": "k01a_coverage",
            "title_th": title,
            "kind": "coverage_by_province",
            "measure_ids": [measure_id],
            "scope_key": result["scope_key"],
            "counted_total": result["value"],
            "supporting_assertions": assertions,
            "detail_availability": "summary_only",
            "unavailable_reason": result["unavailable_reason"],
        }
    elif query.kind == "entity":
        section = {
            "section_id": measure_id.lower(),
            "title_th": title,
            "kind": "entity_index",
            "measure_ids": [measure_id],
            "scope_key": result["scope_key"],
            "preview_ids": ids[:preview_count],
            "has_more": len(ids) > preview_count,
            "counted_total": result["value"],
            "public_detail_total": len(ids),
            "withheld_count": len(counted_ids) - len(ids),
            "withheld_reasons": _withheld_summary(counted_ids, details, withheld),
            "index_location": "topic.item_ids_by_measure_and_scope",
            "detail_availability": "available"
            if result["availability"] == "available"
            else "not_applicable",
            "unavailable_reason": result["unavailable_reason"],
            "item_ids": ids,
        }
    elif query.kind == "aggregate":
        section = {
            "section_id": measure_id.lower(),
            "title_th": title,
            "kind": "aggregate_breakdown",
            "measure_ids": [measure_id],
            "scope_key": result["scope_key"],
            "counted_total": result["value"],
            "breakdowns": _safe_breakdowns(
                selected.get("aggregate_breakdowns", []), policy, source_regions
            ),
            "detail_availability": "not_applicable",
            "unavailable_reason": result["unavailable_reason"],
        }
    else:
        section = {
            "section_id": measure_id.lower(),
            "title_th": title,
            "kind": "methodology",
            "measure_ids": [measure_id],
            "scope_key": result["scope_key"],
            "detail_availability": "not_applicable",
            "unavailable_reason": result["unavailable_reason"],
        }
    return {
        "scope_key": result["scope_key"],
        "results": {measure_id: result},
        "context_results": [],
        "coverage": {measure_id: selected.get("coverage", {})},
        "sections": [section],
    }


def _unsupported_scope(
    query: MeasureQuery, scope_key: str, requested: dict, measure_id: str
) -> dict:
    selected = query.select()
    row = {
        "value": None,
        "value_exact": None,
        "display_value": "",
        "unit": query.unit,
        "status": query.status,
        "availability": "unavailable",
        "scope_key": scope_key,
        "requested_filters": requested,
        "applied_filters": {},
        "unavailable_reason": {
            "code": "unsupported_filter",
            "message_th": "มาตรวัดนี้ไม่รองรับตัวกรองพื้นที่แดชบอร์ดที่ขอ",
        },
    }
    section = {
        "section_id": measure_id.lower(),
        "title_th": _SECTION_TITLES.get(measure_id, measure_id),
        "kind": "aggregate_breakdown" if query.kind == "aggregate" else "methodology",
        "measure_ids": [measure_id],
        "scope_key": scope_key,
        "detail_availability": "not_applicable",
        "unavailable_reason": row["unavailable_reason"],
    }
    if query.kind == "aggregate":
        section.update({"counted_total": None, "breakdowns": []})
    return {
        "scope_key": scope_key,
        "results": {measure_id: row},
        "context_results": [],
        "coverage": {measure_id: selected.get("coverage", {})},
        "sections": [section],
    }


def _context_results(
    measure_id: str,
    query: MeasureQuery,
    scoped_result: dict,
    national: dict,
    source_regions: dict[str, dict],
    policy: dict,
) -> list[dict]:
    if scoped_result.get("availability") != "unavailable":
        return []
    results = []
    national_result = _common_result(national)
    if national_result["availability"] == "available":
        results.append(
            {
                "context_id": f"{measure_id.lower()}-national",
                "measure_id": measure_id,
                "label_th": "บริบทระดับประเทศ (ไม่ใช่ค่าทดแทนของพื้นที่ที่เลือก)",
                "relationship": "national_context_not_fallback",
                "result": national_result,
            }
        )
    if measure_id in _SOURCE_REGION_MEASURES:
        for region_id, region in source_regions.items():
            selected = _select_public(
                query, {"source_region": [region_id]}, source_regions
            )
            results.append(
                {
                    "context_id": f"{measure_id.lower()}-{region_id}",
                    "measure_id": measure_id,
                    "label_th": f"บริบทภูมิภาคตามแหล่งข้อมูล: {region['label_th']}",
                    "relationship": "independent_source_region_not_mapped_to_selected_dashboard_geography",
                    "result": _common_result(selected),
                }
            )
    return results


def _selection_payload(
    selected: dict,
    query: MeasureQuery,
    details: dict,
    withheld: dict,
    preview_count: int,
    policy: dict,
    source_regions: dict[str, dict],
    *,
    full_ids: bool,
) -> dict:
    result = _common_result(selected)
    payload: dict[str, Any] = {"result": result}
    if query.kind == "entity":
        counted_ids = list(selected.get("entity_ids", []))
        ids = [entity_id for entity_id in counted_ids if entity_id in details]
        payload.update(
            {
                "counted_total": result["value"],
                "public_detail_total": len(ids),
                "withheld_count": len(counted_ids) - len(ids),
                "withheld_reasons": _withheld_summary(counted_ids, details, withheld),
            }
        )
        if full_ids:
            payload["item_ids"] = ids
        else:
            payload["preview_ids"] = ids[:preview_count]
            payload["has_more"] = len(ids) > preview_count
            payload["index_location"] = "topic.items_by_id"
    elif query.kind == "aggregate":
        source_policy = policy if policy.get("sources") else None
        payload["breakdowns"] = _safe_breakdowns(
            selected.get("aggregate_breakdowns", []), source_policy, source_regions
        )
    return payload


def _choice(
    choice_id: str, label_th: str, selection: dict, *, count_meaningful: bool
) -> dict:
    result = selection["result"]
    row = {
        "id": choice_id,
        "label_th": label_th,
        "availability": result["availability"],
        "unavailable_reason": result["unavailable_reason"],
    }
    if count_meaningful and result["availability"] == "available":
        row["count"] = result["value"]
    return row


def _prepared_filters(
    query: MeasureQuery,
    measure_id: str,
    filters: dict,
    tables: dict,
    details: dict | None = None,
    withheld: dict | None = None,
    preview_count: int = 0,
    policy: dict | None = None,
    source_regions: dict[str, dict] | None = None,
) -> dict:
    """Materialize every finite filter combination promised to the first page."""
    details, withheld = details or {}, withheld or {}
    policy = policy or {"sources": {}}
    source_regions = source_regions or {}
    selected = _select_public(query, filters, source_regions)
    is_national = not filters
    prepared = {
        "default": _selection_payload(
            selected,
            query,
            details,
            withheld,
            preview_count,
            policy,
            source_regions,
            full_ids=not is_national and "province" in filters,
        ),
        "choices": {},
        "selections": {},
    }

    def add(
        key: str,
        candidate_filters: dict,
        dimension: str,
        choice_id: str,
        label: str,
        *,
        count_meaningful: bool = False,
        full_ids: bool = False,
    ) -> None:
        candidate = _select_public(query, candidate_filters, source_regions)
        payload = _selection_payload(
            candidate,
            query,
            details,
            withheld,
            preview_count,
            policy,
            source_regions,
            full_ids=full_ids,
        )
        prepared["selections"][key] = payload
        prepared["choices"].setdefault(dimension, []).append(
            _choice(choice_id, label, payload, count_meaningful=count_meaningful)
        )

    if measure_id == "K12" and set(filters) <= {"province", "region"}:
        labels = {}
        for row in tables.get("category_memberships", []):
            if row.get("measure_id") == measure_id and row.get("category_code"):
                labels[str(row["category_code"])] = str(
                    row.get("category_name_th") or row["category_code"]
                )
        for category, label in sorted(labels.items()):
            key = f"category/{category}"
            add(
                key,
                {**filters, "category": [category]},
                "category",
                category,
                label,
                count_meaningful=True,
                full_ids=True,
            )
    elif measure_id == "K02" and set(filters) <= {"province"}:
        levels = sorted(
            {
                str(row["source_level"])
                for row in tables.get("aggregate_breakdowns", [])
                if row.get("measure_id") == measure_id and row.get("source_level")
            }
        )
        for level in levels:
            add(
                f"source_level/{level}",
                {**filters, "source_level": [level]},
                "source_level",
                level,
                f"ระดับที่แหล่งข้อมูลระบุ {level}",
            )
    elif measure_id == "C08_REPORTED_BUSINESSES" and not filters:
        dimensions = sorted(
            {
                str(row["breakdown_id"])
                for row in tables.get("aggregate_breakdowns", [])
                if row.get("measure_id") == measure_id and row.get("breakdown_id")
            }
        )
        for dimension in dimensions:
            add(
                f"source_dimension/{dimension}",
                {"source_dimension": [dimension]},
                "source_dimension",
                dimension,
                _CHOICE_LABELS.get(dimension, dimension),
            )
    elif measure_id in _SOURCE_REGION_MEASURES and set(filters) <= {"source_region"}:
        for region_id, region in source_regions.items():
            add(
                f"source_region/{region_id}",
                {"source_region": [region_id]},
                "source_region",
                region_id,
                region["label_th"],
            )
        if measure_id in {"K10", "C10_ALTERNATIVE"}:
            components = sorted(
                {
                    str(row["component"])
                    for row in tables.get("aggregate_breakdowns", [])
                    if row.get("measure_id") == measure_id and row.get("component")
                }
            )
            for component in components:
                add(
                    f"component/{component}",
                    {"component": [component]},
                    "component",
                    component,
                    _CHOICE_LABELS.get(component, component),
                )
            for region_id in source_regions:
                for component in components:
                    add(
                        f"source_region/{region_id}/component/{component}",
                        {"source_region": [region_id], "component": [component]},
                        "source_region_component",
                        f"{region_id}/{component}",
                        f"{source_regions[region_id]['label_th']} — {_CHOICE_LABELS.get(component, component)}",
                    )
    prepared["choices"] = {
        name: sorted(values, key=lambda row: row["id"])
        for name, values in sorted(prepared["choices"].items())
    }
    prepared["selections"] = dict(sorted(prepared["selections"].items()))
    return prepared


def _prepared_default_from_bundle(bundle: dict, measure_id: str) -> dict:
    """Reuse the exact scoped result and list/breakdown prepared for the section."""
    payload = {"result": bundle["results"][measure_id]}
    section = next(
        row for row in bundle["sections"] if row.get("measure_ids") == [measure_id]
    )
    for key in (
        "breakdowns",
        "counted_total",
        "public_detail_total",
        "withheld_count",
        "withheld_reasons",
        "preview_ids",
        "has_more",
        "index_location",
        "supporting_assertions",
    ):
        if key in section:
            payload[key] = section[key]
    return payload


def _merge_scope(bundles: list[dict], scope_key: str) -> dict:
    result = {
        "scope_key": scope_key,
        "results": {},
        "context_results": [],
        "coverage": {},
        "sections": [],
        "prepared_filters": {},
    }
    for bundle in bundles:
        for key in ("results", "coverage", "prepared_filters"):
            overlap = set(result[key]) & set(bundle.get(key, {}))
            if overlap:
                raise PipelineError(
                    f"Duplicate measure namespace in scope: {sorted(overlap)}"
                )
            result[key].update(bundle.get(key, {}))
        result["context_results"].extend(bundle.get("context_results", []))
        result["sections"].extend(bundle.get("sections", []))
    return result


def _bind_item_lists(
    scopes: dict[str, dict],
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Centralize complete entity membership without inferring it from detail fields."""
    bindings: dict[str, dict[str, list[str]]] = defaultdict(dict)
    bound_scopes = {}
    for scope_key, bundle in scopes.items():
        sections = []
        for section in bundle["sections"]:
            public_section = dict(section)
            if public_section.get("kind") == "entity_index":
                measure_id = public_section["measure_ids"][0]
                bindings[measure_id][scope_key] = public_section.pop("item_ids")
                public_section["item_list_scope"] = scope_key
            sections.append(public_section)
        bound_scopes[scope_key] = {**bundle, "sections": sections}
    return bound_scopes, {
        measure_id: dict(sorted(values.items()))
        for measure_id, values in sorted(bindings.items())
    }


def _item_index(
    measure_ids: list[str], details_by_measure: dict, _topic_key: str
) -> tuple[dict[str, dict], dict[str, dict]]:
    details: dict[str, dict] = {}
    for measure_id in measure_ids:
        for entity_id, detail in (
            details_by_measure.get(measure_id, {}).get("details", {}).items()
        ):
            if entity_id in details and details[entity_id] != detail:
                raise PipelineError(f"Topic detail collision: {entity_id}")
            details[entity_id] = detail
    c02_topic = {"C02_COMMUNITY"} & set(measure_ids)
    items = {}
    for entity_id, detail in sorted(details.items()):
        if c02_topic:
            roles = detail.get("children", {}).get("qualifying_roles", [])
            role_codes = sorted({row.get("role_code") for row in roles})
            relationship_ids = {
                row.get("entity_id") for row in detail.get("relationships", [])
            }
            if (
                not roles
                or any(
                    code not in {"community_innovator", "inventor"}
                    for code in role_codes
                )
                or detail.get("related_work_count") != len(relationship_ids)
            ):
                raise PipelineError("C02 compact index cannot be derived safely")
            item = {
                "label": detail.get("label"),
                "label_availability": detail.get("label_availability"),
                "identity_status": detail.get("identity_status"),
                "identity_review": detail.get("flags", {}).get("identity_review", {}),
                "source_ids": detail.get("source_ids", []),
                "role_codes": role_codes,
                "role_labels_th": [
                    next(
                        row["role_label_th"]
                        for row in roles
                        if row.get("role_code") == code
                    )
                    for code in role_codes
                ],
                "related_work_count": detail["related_work_count"],
            }
            if detail.get("flags", {}).get("related_work_count_unavailable"):
                item["related_work_count_unavailable"] = True
            organization_labels = sorted(
                {
                    row.get("organization")
                    for row in detail.get("children", {}).get("organizations", [])
                    if isinstance(row.get("organization"), str) and row["organization"]
                }
            )
            if organization_labels:
                item["organization_labels"] = organization_labels
            items[entity_id] = item
        else:
            items[entity_id] = {
                "label": detail.get("label"),
                "identity_status": detail.get("identity_status"),
                "identity_review": detail.get("flags", {}).get("identity_review", {}),
                "province_codes": detail.get("province_codes", []),
                "category_codes": detail.get("category_codes", []),
                "source_ids": detail.get("source_ids", []),
            }
    return items, details


def _detail_envelope_size(
    metadata: dict,
    topic_id: str,
    detail_count: int,
    detail_object_size: int,
    source_ids: set[str],
) -> int:
    """Return the exact compact UTF-8 size without rebuilding the detail object."""
    fields = {
        **metadata,
        "topic_id": topic_id,
        "detail_count": detail_count,
        "source_ids": sorted(source_ids),
    }
    field_sizes = [
        len(canonical_json(key).encode("utf-8"))
        + 1
        + len(canonical_json(value).encode("utf-8"))
        for key, value in fields.items()
    ]
    detail_field_size = (
        len(canonical_json("details_by_id").encode("utf-8")) + 1 + detail_object_size
    )
    # Braces, one comma between each top-level field, and the trailing newline.
    return 2 + sum(field_sizes) + detail_field_size + len(fields) + 1


def _detail_chunks(
    topic: dict,
    details: dict,
    metadata: dict,
    topic_maximum: int,
    child_maximum: int,
) -> dict[str, dict]:
    """Move whole detail records into bounded deterministic child artifacts."""
    if _encoded_size(topic) <= topic_maximum:
        return {}
    topic["details_by_id"], topic["detail_artifacts"] = {}, {}
    chunks: list[tuple[dict[str, dict], set[str]]] = []
    current: dict[str, dict] = {}
    current_sources: set[str] = set()
    detail_object_size = 2
    for entity_id in sorted(details):
        detail = details[entity_id]
        entry_size = (
            len(canonical_json(entity_id).encode("utf-8"))
            + 1
            + len(canonical_json(detail).encode("utf-8"))
        )
        candidate_object_size = detail_object_size + entry_size + (1 if current else 0)
        candidate_sources = current_sources | set(detail.get("source_ids", []))
        candidate_size = _detail_envelope_size(
            metadata,
            topic["topic_id"],
            len(current) + 1,
            candidate_object_size,
            candidate_sources,
        )
        if current and candidate_size > child_maximum:
            chunks.append((current, current_sources))
            current = {entity_id: detail}
            current_sources = set(detail.get("source_ids", []))
            detail_object_size = 2 + entry_size
        else:
            current[entity_id] = detail
            current_sources = candidate_sources
            detail_object_size = candidate_object_size
    if current:
        chunks.append((current, current_sources))
    outputs = {}
    for number, (rows, source_ids) in enumerate(chunks):
        key = f"f2/topic/{topic['topic_id']}/detail/{number:03d}"
        path = f"details/{topic['topic_id']}-{number:03d}.json"
        payload = {
            **metadata,
            "topic_id": topic["topic_id"],
            "details_by_id": rows,
            "detail_count": len(rows),
            "source_ids": sorted(source_ids),
        }
        if _encoded_size(payload) > child_maximum:
            raise PipelineError(
                "One approved public detail exceeds the child artifact budget"
            )
        outputs[path] = payload
        for entity_id in rows:
            topic["detail_artifacts"][entity_id] = key
            # The topic-level lookup contract resolves this public ID through
            # detail_artifacts without repeating a pointer in every compact item.
    if set(topic["detail_artifacts"]) != set(details):
        raise PipelineError("Detail chunk index is incomplete")
    return outputs


def _geography_scope(bundles: list[dict], scope_key: str) -> dict:
    merged = _merge_scope(bundles, scope_key)
    members = {}
    for section in merged["sections"]:
        if (
            section.get("measure_ids") == ["K02"]
            and section.get("kind") == "aggregate_breakdown"
        ):
            members["K02"] = section.get("breakdowns", [])
    measure_metadata = {
        measure_id: {
            "unit": cell["unit"],
            "availability": cell["availability"],
            "map_eligibility": (
                "source_region"
                if measure_id in _SOURCE_REGION_MEASURES
                and scope_key.startswith("source_region/")
                else (
                    "source_region_only"
                    if measure_id in _SOURCE_REGION_MEASURES and scope_key == "national"
                    else (
                        "available"
                        if cell["availability"] == "available"
                        else "unavailable"
                    )
                )
            ),
            "unavailable_reason": cell["unavailable_reason"],
            "province_sum_is_additive": merged["coverage"]
            .get(measure_id, {})
            .get("province_sum_is_additive", False),
        }
        for measure_id, cell in merged["results"].items()
    }
    return {
        "scope_key": scope_key,
        "results": merged["results"],
        "coverage": merged["coverage"],
        "context_results": merged["context_results"],
        "measure_metadata": measure_metadata,
        "aggregate_members": members,
    }


def _public_filter_contract(definition: dict) -> dict:
    supported = list(definition.get("supported_filters", []))
    combinations = [
        list(values) for values in definition.get("permitted_filter_combinations", [[]])
    ]
    if definition["measure_id"] in _SOURCE_REGION_MEASURES:
        supported = [
            "source_region" if value == "region" else value for value in supported
        ]
        combinations = [
            ["source_region" if value == "region" else value for value in values]
            for values in combinations
        ]
    return {"supported_filters": supported, "permitted_combinations": combinations}


def _map_availability(definition: dict) -> str:
    measure_id = definition["measure_id"]
    explicit = definition.get("map_availability")
    if explicit is not None:
        allowed = {"unavailable", "province", "source_region_only"}
        if explicit not in allowed:
            raise PipelineError(f"Invalid map availability for {measure_id}")
        if explicit == "province" and "province" not in definition.get(
            "supported_filters", []
        ):
            raise PipelineError(
                f"Province map requires a province filter for {measure_id}"
            )
        if explicit == "source_region_only" and measure_id not in _SOURCE_REGION_MEASURES:
            raise PipelineError(
                f"Source-region map is not available for {measure_id}"
            )
        return explicit
    if measure_id in _SOURCE_REGION_MEASURES:
        return "source_region_only"
    return (
        "province"
        if "province" in definition.get("supported_filters", [])
        else "unavailable"
    )


def _definition_payload(
    definition: dict,
    national: dict,
    source_ids: list[str],
    detail_measures: set[str],
) -> dict:
    measure_id = definition["measure_id"]
    return {
        key: definition.get(key)
        for key in (
            "measure_id",
            "label_th",
            "unit",
            "status",
            "formula",
            "scope",
            "limitations",
            "map_legend_th",
            "display_order",
            "topic_id",
            "parent_measure_id",
        )
    } | {
        "result": _common_result(national),
        "filter_contract": _public_filter_contract(definition),
        "map_availability": _map_availability(definition),
        "detail_availability": "available"
        if measure_id in detail_measures
        else (
            "not_applicable" if measure_id not in _PERSON_MEASURES else "internal_only"
        ),
        "coverage": national.get("coverage", {}),
        "source_ids": source_ids,
    }


def _validate_payload(path: str, payload: dict, policy: dict) -> None:
    excluded = set(policy.get("excluded_fields", []))

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            forbidden = excluded & set(value)
            if forbidden:
                raise PipelineError(
                    f"Public payload contains excluded fields: {path}: {sorted(forbidden)}"
                )
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    contexts = (
        policy["publication_field_contexts"]
        if path.startswith(("topics/", "details/"))
        else {}
    )
    problems = _privacy_problems(
        payload,
        artifact_path=f"data/public/f2/{path}",
        restricted_source_ids=set(),
        profile="aggregate_public",
        field_contexts=contexts,
    )
    if problems:
        raise PipelineError(
            f"Public projection privacy validation failed: {path}; {len(problems)} findings"
        )
    declared = {source["source_id"] for source in policy["sources"].values()}
    try:
        found, _ = _embedded_source_provenance(
            payload,
            artifact_path=f"data/public/f2/{path}",
            declared_source_ids=declared,
            restricted_source_ids=set(),
        )
    except PublicationError as exc:
        raise PipelineError(
            f"Public projection provenance shape is invalid: {path}"
        ) from exc
    if not found <= declared:
        raise PipelineError(f"Public projection contains undeclared sources: {path}")


def _review_proof(release_dir: Path, manifest: dict, proof: dict) -> dict:
    if not isinstance(proof, dict):
        raise PipelineError("Full projection requires a verified comparison proof")
    if (
        proof.get("release_id") != manifest.get("release_id")
        or proof.get("release_manifest_sha256") != digest(release_dir / "manifest.json")
        or proof.get("scope") != "internal_release_only"
        or proof.get("public_promotion_approved") is not False
    ):
        raise PipelineError("Comparison proof does not bind this internal release")
    return proof


def _protected_paths(release_dir: Path) -> tuple[Path, ...]:
    repository = Path(__file__).resolve().parents[2]
    return (
        release_dir,
        repository / "data/current",
        repository / "data/public",
        repository / "data/runtime/f2/raw",
        repository / "data/runtime/f2/reviews",
        repository / "config/f2_pipeline",
    )


def build_full_projection(
    release_dir, output_dir, *, comparison_proof
) -> FullProjectionReport:
    release_dir, output_dir = Path(release_dir), Path(output_dir)
    protected = _protected_paths(release_dir)
    ensure_new_output(output_dir, protected)
    manifest = verify_release(release_dir, require_complete=True)
    if (
        manifest.get("profile") != "full"
        or manifest.get("complete") is not True
        or manifest.get("publication_status") != "internal_only"
        or manifest.get("release_id") != _RELEASE_ID
    ):
        raise PipelineError(
            "Full projection requires the complete v3 internal-only full release"
        )
    comparison_proof = _review_proof(release_dir, manifest, comparison_proof)
    policy, policy_hash = _policy(release_dir)
    tables = load_release_tables(release_dir)
    definitions = load_json(release_dir / "definitions.json").get("measures")
    stored = load_json(release_dir / "results.json")
    if (
        not isinstance(definitions, list)
        or len(definitions) != 21
        or not isinstance(stored, dict)
    ):
        raise PipelineError(
            "Full release does not contain the exact 21-measure contract"
        )
    definitions = sorted(definitions, key=lambda row: row["display_order"])
    definition_ids = {row["measure_id"] for row in definitions}
    if definition_ids != set(stored) or len(definition_ids) != 21:
        raise PipelineError("Definitions and stored results differ")
    provinces = sorted(
        tables.get("provinces", []), key=lambda row: row["province_code"]
    )
    if (
        len(provinces) != 77
        or len({row.get("province_code") for row in provinces}) != 77
    ):
        raise PipelineError("Full projection requires all 77 dashboard provinces")
    queries = {
        row["measure_id"]: MeasureQuery(row, tables, provinces) for row in definitions
    }
    national = {
        measure_id: _reconcile(query, stored[measure_id], measure_id)
        for measure_id, query in queries.items()
    }

    from .public_details import (  # Detail approval stays at this seam.
        build_details,
        price_source_snapshots,
    )

    input_manifest_path = release_dir / "input_manifest.csv"
    if input_manifest_path.is_file():
        input_manifest = read_csv(input_manifest_path)
    elif "files" not in manifest:  # Legacy synthetic projection fixture.
        input_manifest = None
    else:
        raise PipelineError("Full projection requires the verified input manifest")
    details_by_measure = build_details(
        tables, definitions, policy, input_manifest=input_manifest
    )
    if not isinstance(details_by_measure, dict):
        raise PipelineError("Public detail builder returned an invalid contract")
    detail_measures = set(_DETAIL_MEASURES)
    if "c02_projection" in policy or "c02_field_review" in policy:
        from .c02_projection import build_c02_details

        public_targets = {}
        for target_measure in ("K04", "C04_LISTED"):
            for entity_id, detail in details_by_measure[target_measure][
                "details"
            ].items():
                public_targets.setdefault(entity_id, (detail["label"], target_measure))
        details_by_measure.update(build_c02_details(tables, policy, public_targets))
        detail_measures |= _C02_DETAIL_MEASURES
    for measure_id in detail_measures:
        contract = details_by_measure.get(measure_id, {})
        details, withheld = contract.get("details", {}), contract.get("withheld", {})
        if (
            not isinstance(details, dict)
            or not isinstance(withheld, dict)
            or set(details) & set(withheld)
        ):
            raise PipelineError(f"Invalid public detail disposition: {measure_id}")
        if set(details) | set(withheld) != set(
            national[measure_id].get("entity_ids", [])
        ):
            raise PipelineError(
                f"Public detail disposition does not reconcile: {measure_id}"
            )
        if any(
            not isinstance(row, dict) or row.get("entity_id") != entity_id
            for entity_id, row in details.items()
        ):
            raise PipelineError(
                f"Public detail identity differs from its key: {measure_id}"
            )
    for shared_id in set(details_by_measure["K04"]["details"]) & set(
        details_by_measure["C04_LISTED"]["details"]
    ):
        if (
            details_by_measure["K04"]["details"][shared_id]
            != details_by_measure["C04_LISTED"]["details"][shared_id]
        ):
            raise PipelineError("Shared K04/C04 public detail differs")

    enabled_sources = manifest.get("enabled_sources")
    approved_sources = set(_source_registry(policy)[0])
    if (
        not isinstance(enabled_sources, list)
        or len(enabled_sources) != 8
        or set(enabled_sources) != approved_sources
    ):
        raise PipelineError(
            "Full projection source registry must match all eight release sources"
        )

    field_approval = validate_detail_owner_approval(policy)
    c02_field_review = None
    c02_geography_review = None
    if "c02_projection" in policy or "c02_field_review" in policy:
        from .field_approval import (
            C02_PRIVATE_REVISIONS,
            c02_geography_private_revision,
            validate_c02_field_review,
            validate_c02_geography_review,
        )

        c02_field_review = validate_c02_field_review(policy)
        c02_geography_review = validate_c02_geography_review(policy)
    price_snapshots = price_source_snapshots(tables, policy, input_manifest)
    metadata = {
        "schema_version": _SCHEMA,
        "release_id": manifest["release_id"],
        "release_date": manifest["release_date"],
        "input_lock_sha256": manifest["input_lock_sha256"],
        "publication_status": "staged_for_review",
        "staged_for_review": True,
        "owner_checkpoint_required": True,
        "additional_field_review_status": approval_review_status(field_approval),
        "projection_policy_sha256": policy_hash,
        "publication_approval_claimed": False,
        "internal_review": comparison_proof,
    }
    if field_approval is not None:
        metadata["detail_owner_approval"] = field_approval
    if c02_geography_review is not None:
        metadata["additional_field_review_status"] = c02_geography_review["status"]
    if c02_field_review is not None:
        expected_revision = (
            c02_geography_private_revision(c02_geography_review)
            if c02_geography_review is not None
            else C02_PRIVATE_REVISIONS[c02_field_review["status"]]
        )
        if policy.get("private_revision_id") != expected_revision:
            raise PipelineError("C02 projection has an unexpected private revision")
    source_regions = _source_region_catalog(tables, policy)
    k01a_assertions = _supporting_assertions(tables, policy)
    measure_sources = {
        measure_id: _source_ids(tables, [measure_id], policy, details_by_measure)
        for measure_id in definition_ids
    }

    definition_payloads = {
        row["measure_id"]: _definition_payload(
            row,
            national[row["measure_id"]],
            measure_sources[row["measure_id"]],
            detail_measures,
        )
        for row in definitions
    }
    headlines = []
    for definition in definitions:
        if definition.get("kind") != "headline":
            continue
        measure_id = definition["measure_id"]
        companions = [
            definition_payloads[child["measure_id"]]
            for child in definitions
            if child.get("parent_measure_id") == measure_id
        ]
        headlines.append(
            {
                **definition_payloads[measure_id],
                "companions": companions,
                "artifact_key": f"f2/topic/{definition['topic_id']}",
            }
        )
    if len(headlines) != 14:
        raise PipelineError("Full release does not contain exactly 14 headlines")
    overview = {
        **metadata,
        "source_ids": sorted(enabled_sources),
        "headlines": headlines,
        "limitations": policy["limitations"],
    }
    if _encoded_size(overview) > policy["max_overview_bytes"]:
        raise PipelineError("Overview exceeds reviewed payload budget")

    dashboard_scope_keys = ["national"] + [
        f"province/{row['province_code']}" for row in provinces
    ]
    dashboard_regions = {row["region_id"]: row["region"] for row in provinces}
    dashboard_scope_keys.extend(
        f"region/{region_id}" for region_id in sorted(dashboard_regions)
    )
    all_scope_bundles: dict[str, dict[str, dict]] = {
        key: {} for key in dashboard_scope_keys
    }
    for measure_id, query in queries.items():
        contract = details_by_measure.get(measure_id, {})
        details, withheld = contract.get("details", {}), contract.get("withheld", {})
        for scope_key in dashboard_scope_keys:
            if scope_key == "national":
                scope_filters = {}
                bundle = _scope(
                    query,
                    scope_filters,
                    details,
                    policy["preview_count"],
                    measure_id,
                    withheld=withheld,
                    policy=policy,
                    source_regions=source_regions,
                    supporting_assertions=k01a_assertions,
                    national=True,
                )
            elif scope_key.startswith("province/"):
                scope_filters = {"province": [scope_key.split("/", 1)[1]]}
                bundle = _scope(
                    query,
                    scope_filters,
                    details,
                    policy["preview_count"],
                    measure_id,
                    withheld=withheld,
                    policy=policy,
                    source_regions=source_regions,
                    supporting_assertions=k01a_assertions,
                    national=False,
                )
            else:
                region_id = scope_key.split("/", 1)[1]
                scope_filters = {"dashboard_region": [region_id]}
                if query.kind == "entity" and "province" in query.supported_filters:
                    scope_filters = {"region": [region_id]}
                    bundle = _scope(
                        query,
                        scope_filters,
                        details,
                        policy["preview_count"],
                        measure_id,
                        withheld=withheld,
                        policy=policy,
                        source_regions=source_regions,
                        supporting_assertions=[
                            row
                            for row in k01a_assertions
                            if row.get("province_code")
                            in {
                                province["province_code"]
                                for province in provinces
                                if province["region_id"] == region_id
                            }
                        ],
                        national=False,
                    )
                else:
                    bundle = _unsupported_scope(
                        query, scope_key, scope_filters, measure_id
                    )
            result = bundle["results"][measure_id]
            bundle["context_results"] = _context_results(
                measure_id, query, result, national[measure_id], source_regions, policy
            )
            prepared = _prepared_filters(
                query,
                measure_id,
                scope_filters,
                tables,
                details,
                withheld,
                policy["preview_count"],
                policy,
                source_regions,
            )
            prepared["default"] = _prepared_default_from_bundle(bundle, measure_id)
            bundle["prepared_filters"] = {measure_id: prepared}
            all_scope_bundles[scope_key][measure_id] = bundle

    source_scope_bundles: dict[str, dict[str, dict]] = {}
    for region_id in source_regions:
        scope_key = f"source_region/{region_id}"
        source_scope_bundles[scope_key] = {}
        for measure_id in _SOURCE_REGION_MEASURES:
            query = queries[measure_id]
            bundle = _scope(
                query,
                {"source_region": [region_id]},
                {},
                policy["preview_count"],
                measure_id,
                policy=policy,
                source_regions=source_regions,
                national=False,
            )
            prepared = _prepared_filters(
                query,
                measure_id,
                {"source_region": [region_id]},
                tables,
                {},
                {},
                policy["preview_count"],
                policy,
                source_regions,
            )
            prepared["default"] = _prepared_default_from_bundle(bundle, measure_id)
            bundle["prepared_filters"] = {measure_id: prepared}
            source_scope_bundles[scope_key][measure_id] = bundle

    geography = {
        **metadata,
        "source_ids": sorted(enabled_sources),
        "dashboard_region_scheme": {
            "scheme_id": "f2_dashboard_regions_v1",
            "label_th": "ภูมิภาคสำหรับการจัดกลุ่มจังหวัดบนแดชบอร์ด",
        },
        "source_region_scheme": {
            "scheme_id": _SOURCE_REGION_SCHEME,
            "label_th": "ภูมิภาคตามที่แหล่งข้อมูลรายงาน",
            "dashboard_region_mapping": None,
            "mapping_status": "not_defined",
        },
        "national": _geography_scope(
            list(all_scope_bundles["national"].values()), "national"
        ),
        "provinces": {
            row["province_code"]: {
                "province_code": row["province_code"],
                "province_name_th": row["province_name_th"],
                "province_name_en": row["province_name_en"],
                "dashboard_region_id": row["region_id"],
                **_geography_scope(
                    list(
                        all_scope_bundles[f"province/{row['province_code']}"].values()
                    ),
                    f"province/{row['province_code']}",
                ),
            }
            for row in provinces
        },
        "regions": {
            region_id: {
                "dashboard_region_id": region_id,
                "label_th": dashboard_regions[region_id],
                "province_codes": [
                    row["province_code"]
                    for row in provinces
                    if row["region_id"] == region_id
                ],
                **_geography_scope(
                    list(all_scope_bundles[f"region/{region_id}"].values()),
                    f"region/{region_id}",
                ),
            }
            for region_id in sorted(dashboard_regions)
        },
        "source_regions": {
            region_id: {
                **region,
                **_geography_scope(
                    list(source_scope_bundles[f"source_region/{region_id}"].values()),
                    f"source_region/{region_id}",
                ),
            }
            for region_id, region in source_regions.items()
        },
        "coverage_note": "Source regions are independent source categories and are not mapped to dashboard regions or provinces.",
    }
    if _encoded_size(geography) > policy["max_geography_bytes"]:
        raise PipelineError("Geography exceeds reviewed payload budget")

    outputs: dict[str, dict] = {"overview.json": overview, "geography.json": geography}
    topic_sizes: dict[str, int] = {}
    counts_by_measure = {}
    for measure_id, query in queries.items():
        counted = (
            len(national[measure_id].get("entity_ids", []))
            if query.kind == "entity"
            else None
        )
        contract = details_by_measure.get(measure_id, {})
        public_count = len(contract.get("details", {}))
        withheld_count = len(contract.get("withheld", {}))
        if measure_id in _PERSON_MEASURES and measure_id not in detail_measures:
            withheld_count = counted or 0
        counts_by_measure[measure_id] = {
            "counted_entity_total": counted,
            "public_detail_total": public_count,
            "withheld_detail_total": withheld_count,
        }
    detail_record_count = 0
    withheld_disposition_count = sum(
        len(details_by_measure[measure_id]["withheld"])
        for measure_id in detail_measures
    )
    topics: dict[str, list[dict]] = defaultdict(list)
    for definition in definitions:
        topics[definition["topic_id"]].append(definition)
    if len(topics) != 14:
        raise PipelineError("Full release does not contain exactly 14 topics")
    for topic_id, members in sorted(topics.items()):
        measure_ids = [row["measure_id"] for row in members]
        topic_key = f"f2/topic/{topic_id}"
        items, detail_rows = _item_index(measure_ids, details_by_measure, topic_key)
        detail_record_count += len(detail_rows)
        scope_keys = list(dashboard_scope_keys)
        if set(measure_ids) <= _SOURCE_REGION_MEASURES:
            scope_keys.extend(sorted(source_scope_bundles))
        scopes = {}
        for key in scope_keys:
            source = (
                source_scope_bundles
                if key.startswith("source_region/")
                else all_scope_bundles
            )
            bundles = [source[key][measure_id] for measure_id in measure_ids]
            scopes[key] = _merge_scope(bundles, key)
        scopes, item_lists = _bind_item_lists(scopes)
        source_ids = sorted(
            set().union(*(set(measure_sources[mid]) for mid in measure_ids))
        )
        topic_metadata = (
            {**metadata, "source_snapshots": price_snapshots}
            if "K07" in measure_ids and price_snapshots
            else metadata
        )
        topic = {
            **topic_metadata,
            "topic_id": topic_id,
            "source_ids": source_ids,
            "measure_ids": measure_ids,
            "filter_contracts": {
                row["measure_id"]: {
                    **_public_filter_contract(row),
                    "detail_availability": definition_payloads[row["measure_id"]][
                        "detail_availability"
                    ],
                    "map_availability": definition_payloads[row["measure_id"]][
                        "map_availability"
                    ],
                }
                for row in members
            },
            "scopes": scopes,
            "item_list_contract": {
                "collection": "item_ids_by_measure_and_scope",
                "section_measure_field": "measure_ids[0]",
                "section_scope_field": "item_list_scope",
                "items_pointer": "/items_by_id",
            },
            "item_ids_by_measure_and_scope": item_lists,
            "items_by_id": items,
            "detail_lookup": {
                "records_pointer": "/details_by_id",
                "identity": "items_by_id key",
                "default_artifact_key": topic_key,
                "artifact_keys_by_id": "detail_artifacts",
            },
            "detail_artifacts": {},
            "details_by_id": dict(sorted(detail_rows.items())),
            "sources": _sources(policy, source_ids),
            "limitations": policy["limitations"],
        }
        children = _detail_chunks(
            topic,
            detail_rows,
            topic_metadata,
            policy["max_topic_bytes"],
            policy["max_detail_child_bytes"],
        )
        if _encoded_size(topic) > policy["max_topic_bytes"]:
            raise PipelineError(
                f"Topic {topic_id} envelope is {_encoded_size(topic)} bytes; "
                f"reviewed budget is {policy['max_topic_bytes']}"
            )
        outputs[f"topics/{topic_id}.json"] = topic
        outputs.update(children)
        topic_sizes[topic_id] = _encoded_size(topic) + sum(
            _encoded_size(payload) for payload in children.values()
        )

    with output_directory(output_dir, protected) as stage:
        entries = []
        for path, payload in sorted(outputs.items()):
            limit = policy["max_file_bytes"]
            if path == "overview.json":
                limit = policy["max_overview_bytes"]
            elif path == "geography.json":
                limit = policy["max_geography_bytes"]
            elif path.startswith("topics/"):
                limit = policy["max_topic_bytes"]
            elif path.startswith("details/"):
                limit = policy["max_detail_child_bytes"]
            if _encoded_size(payload) > limit:
                raise PipelineError(
                    f"Public projection exceeds declared size budget: {path}"
                )
            _validate_payload(path, payload, policy)
            _write_compact(stage / path, payload)
            if path.startswith("topics/"):
                topic_id = path.split("/")[-1].removesuffix(".json")
                artifact_key = f"f2/topic/{topic_id}"
            elif path.startswith("details/"):
                topic_id, chunk = (
                    path.removeprefix("details/").removesuffix(".json").rsplit("-", 1)
                )
                artifact_key = f"f2/topic/{topic_id}/detail/{chunk}"
            else:
                artifact_key = f"f2/{path.removesuffix('.json')}"
            entries.append(
                {
                    "path": path,
                    "artifact_key": artifact_key,
                    "sha256": digest(stage / path),
                    "size": (stage / path).stat().st_size,
                    "source_ids": payload["source_ids"],
                }
            )
        public_manifest = {
            **metadata,
            "complete": True,
            "validation_status": "passed",
            "source_ids": sorted(enabled_sources),
            "internal_manifest_sha256": digest(release_dir / "manifest.json"),
            "projection_policy_sha256": policy_hash,
            "source_snapshots": price_snapshots,
            "files": entries,
            "topic_count": len(topics),
            "counts_by_measure": dict(sorted(counts_by_measure.items())),
            "detail_inventory": {
                "detail_record_count": detail_record_count,
                "detail_child_artifact_count": sum(
                    path.startswith("details/") for path in outputs
                ),
                "withheld_disposition_count": withheld_disposition_count,
            },
        }
        if c02_field_review is not None:
            public_manifest["private_revision_id"] = policy["private_revision_id"]
            public_manifest["c02_field_review"] = c02_field_review
            if c02_geography_review is not None:
                public_manifest["c02_geography_review"] = c02_geography_review
        if _encoded_size(public_manifest) > 1024 * 1024:
            raise PipelineError("Public manifest exceeds its provenance budget")
        _validate_payload("manifest.json", public_manifest, policy)
        _write_compact(stage / "manifest.json", public_manifest)
        output_bytes = sum(entry["size"] for entry in entries) + _encoded_size(
            public_manifest
        )
    return FullProjectionReport(
        manifest["release_id"],
        str(output_dir),
        "staged_for_review",
        len(outputs) + 1,
        len(topics),
        counts_by_measure,
        detail_record_count,
        withheld_disposition_count,
        topic_sizes,
        output_bytes,
    )
