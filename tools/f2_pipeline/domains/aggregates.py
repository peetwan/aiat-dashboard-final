"""Pure Phase 6 projections of source-owned aggregates and participation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from ..common import PipelineError, parse_json
from .raw_inputs import observation_uri, resolve_evidence


TABLE_COLUMNS = {
    "aggregate_breakdowns": [
        "measure_id",
        "breakdown_id",
        "member_id",
        "amount",
        "amount_unit",
        "result_divisor",
        "evidence_table",
        "evidence_key",
        "evidence_id",
        "province_code",
        "province_name",
        "source_level",
        "raw_locator",
        "member_label",
        "region",
        "component",
    ],
    "aggregate_results": ["measure_id", "value_exact"],
    "entity_contributions": ["entity_id", "label", "measure_id"],
    "province_memberships": [
        "entity_id",
        "evidence_id",
        "evidence_key",
        "evidence_table",
        "location_role",
        "measure_id",
        "province_code",
    ],
    "eligibility_evidence": [
        "entity_id",
        "evidence_id",
        "evidence_key",
        "evidence_role",
        "evidence_table",
        "measure_id",
    ],
    "evidence_links": [
        "entity_id",
        "evidence_role",
        "key",
        "measure_id",
        "record_id",
        "table",
    ],
}

_COUNT_DIMENSIONS = {
    "categories": "business_category",
    "entityTypes": "business_form",
    "geography": "region",
    "provinces": "province",
}
_IMPACT_FIELDS = {
    "localEmployeeAmount": (
        "reported_monthly_employment",
        "totalEmplyeeAmount",
        "people/month",
    ),
    "localEmployeeExpense": (
        "worker_payments",
        "totalEmployeeExpense",
        "THB/month",
    ),
    "localResourceExpense": (
        "resource_spending",
        "totalResourceExpense",
        "THB/month",
    ),
}
_MILLION = Decimal("1000000")
_MISSING = object()


def _fail(message: str) -> None:
    raise PipelineError(f"aggregates: {message}")


def _decimal(value: Any, what: str) -> Decimal:
    if isinstance(value, bool):
        _fail(f"{what} is not an exact decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        _fail(f"{what} is not an exact decimal")
    if not result.is_finite() or result < 0:
        _fail(f"{what} must be finite and nonnegative")
    return result


def _text(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f") if normalized else "0"


def _table(
    source_tables: dict[str, dict[str, list[dict]]], source_id: str, name: str
) -> list[dict]:
    source = source_tables.get(source_id)
    if not isinstance(source, dict):
        _fail(f"missing canonical source {source_id}")
    rows = source.get(name)
    if not isinstance(rows, list):
        _fail(f"missing source table {source_id}/{name}")
    if not all(isinstance(row, dict) for row in rows):
        _fail(f"{source_id}/{name} contains a non-row")
    return rows


def _index(rows: list[dict], key: str, what: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in rows:
        value = str(row.get(key, ""))
        if not value or value in result:
            _fail(f"duplicate or missing {what} {key}")
        result[value] = row
    return result


def _json_cell(value: Any, expected_type: type, what: str) -> Any:
    if not isinstance(value, str):
        _fail(f"{what} must be a serialized JSON cell")
    try:
        decoded = parse_json(value)
    except (PipelineError, TypeError, ValueError) as exc:
        raise PipelineError(f"aggregates: invalid JSON cell for {what}") from exc
    if not isinstance(decoded, expected_type):
        _fail(f"{what} has the wrong JSON shape")
    return decoded


def _truth(value: Any, what: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    _fail(f"{what} must be a canonical CSV boolean")


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _child_locator(locator: str, *parts: Any) -> str:
    base, separator, pointer = locator.partition("#")
    if not separator:
        _fail("evidence locator has no JSON pointer")
    tokens = [token for token in pointer.lstrip("/").split("/") if token]
    tokens.extend(_pointer_token(str(part)) for part in parts)
    return base + "#/" + "/".join(tokens)


def _observation_index(
    source_tables: dict[str, dict[str, list[dict]]], source_id: str
) -> dict[str, dict]:
    return _index(
        _table(source_tables, source_id, "source_observations"),
        "observation_id",
        f"{source_id} observation",
    )


def _observation_locator(
    raw_inputs: dict,
    source_id: str,
    observations: dict[str, dict],
    observation_id: str,
) -> str:
    observation = observations.get(observation_id)
    if observation is None:
        _fail(f"missing {source_id} observation {observation_id}")
    evidence_observation = observation
    if not observation.get("row_locator") and observation.get("raw_locator"):
        evidence_observation = {
            **observation,
            "row_locator": observation["raw_locator"],
        }
    try:
        return observation_uri(raw_inputs, source_id, evidence_observation)
    except (KeyError, PipelineError) as exc:
        raise PipelineError(
            f"aggregates: invalid {source_id} observation evidence {observation_id}"
        ) from exc


def _raw_value(
    raw_inputs: dict,
    source_id: str,
    observations: dict[str, dict],
    observation_id: str,
    locator: str,
    what: str,
) -> Any:
    observation_locator = _observation_locator(
        raw_inputs, source_id, observations, observation_id
    )
    observation_base, _, observation_pointer = observation_locator.partition("#")
    locator_base, separator, locator_pointer = locator.partition("#")
    parent = observation_pointer.rstrip("/")
    if (
        not separator
        or locator_base != observation_base
        or (
            parent
            and locator_pointer != parent
            and not locator_pointer.startswith(parent + "/")
        )
    ):
        _fail(f"{what} locator does not belong to its source observation")
    try:
        return resolve_evidence(raw_inputs, locator)
    except PipelineError as exc:
        raise PipelineError(f"aggregates: {what} locator does not resolve") from exc


def _require_row_locator(
    raw_inputs: dict,
    source_id: str,
    observations: dict[str, dict],
    row: dict,
    expected_locator: str,
    expected_value: Any,
    what: str,
) -> str:
    locator = str(row.get("raw_locator", ""))
    if locator != expected_locator:
        _fail(f"{what} has a stale or foreign raw locator")
    actual = _raw_value(
        raw_inputs,
        source_id,
        observations,
        str(row.get("observation_id", "")),
        locator,
        what,
    )
    if actual != expected_value:
        _fail(f"{what} raw citation does not match the source row")
    return locator


def _breakdown(
    *,
    measure_id: str,
    breakdown_id: str,
    member_id: str,
    amount: Decimal,
    amount_unit: str,
    result_divisor: str,
    evidence_table: str,
    evidence_key: str,
    evidence_id: str,
    raw_locator: str,
    province_code: str = "",
    province_name: str = "",
    source_level: str = "",
    member_label: str = "",
    region: str = "",
    component: str = "",
) -> dict:
    return {
        "measure_id": measure_id,
        "breakdown_id": breakdown_id,
        "member_id": member_id,
        "amount": _text(amount),
        "amount_unit": amount_unit,
        "result_divisor": result_divisor,
        "evidence_table": evidence_table,
        "evidence_key": evidence_key,
        "evidence_id": evidence_id,
        "province_code": province_code,
        "province_name": province_name,
        "source_level": source_level,
        "raw_locator": raw_locator,
        "member_label": member_label,
        "region": region,
        "component": component,
    }


def _build_k02(source_tables: dict, raw_inputs: dict, out: dict) -> None:
    source_id = "f2_target_household"
    observations = _observation_index(source_tables, source_id)
    summaries = _table(source_tables, source_id, "aggregate_summaries")
    components = _table(source_tables, source_id, "aggregate_components")
    choices = [
        row
        for row in summaries
        if row.get("dashboard") == "innovators"
        and row.get("entity_type") == "innovator_aggregate"
        and not row.get("year_filter")
        and row.get("unit") == "innovators"
        and row.get("status") == "source_reported_nonadditive"
        and str(row.get("source_file", "")).endswith("dashboards/innovators_all.json")
    ]
    if len(choices) != 1:
        _fail("innovators_all summary is absent or ambiguous")
    summary = choices[0]
    observation_id = str(summary.get("observation_id", ""))
    observation = observations.get(observation_id)
    if (
        observation is None
        or observation.get("dataset") != "innovators_all"
        or observation.get("record_type") != "dashboard"
        or not str(observation.get("raw_file", "")).endswith(
            "dashboards/innovators_all.json"
        )
    ):
        _fail("innovators_all summary references the wrong source observation")
    root_locator = _observation_locator(
        raw_inputs, source_id, observations, observation_id
    )
    raw = _raw_value(
        raw_inputs,
        source_id,
        observations,
        observation_id,
        root_locator,
        "K02 summary",
    )
    if not isinstance(raw, dict) or raw.get("dashboard") != "innovators":
        _fail("K02 observation is not the innovators dashboard capture")
    headline = _decimal(summary.get("reported_count"), "K02 reported count")
    if _decimal(raw.get("headline"), "K02 raw headline") != headline:
        _fail("K02 summary does not match the raw headline")
    raw_provinces = raw.get("prov_data")
    integrity = raw.get("integrity_checks")
    if not isinstance(raw_provinces, dict) or not raw_provinces:
        _fail("K02 raw capture has no province components")
    if (
        not isinstance(integrity, dict)
        or integrity.get("headline_matches_sum_total_inno") is not True
        or _decimal(integrity.get("provinces"), "K02 province count")
        != Decimal(len(raw_provinces))
        or _decimal(integrity.get("sum_total_inno"), "K02 integrity total") != headline
    ):
        _fail("K02 raw integrity metadata is incomplete")

    aggregate_id = str(summary.get("aggregate_id", ""))
    if not aggregate_id:
        _fail("innovators_all summary has no source aggregate identifier")
    selected = [
        row
        for row in components
        if row.get("aggregate_id") == aggregate_id
        and row.get("component_kind") == "innovator_province"
    ]
    component_by_id = _index(selected, "component_id", "K02 component")
    province_rows: dict[str, dict] = {}
    for row in component_by_id.values():
        province_raw = str(row.get("province_raw", ""))
        if not province_raw or province_raw in province_rows:
            _fail("K02 has a duplicate or missing source province")
        if str(row.get("observation_id", "")) != observation_id:
            _fail("K02 component belongs to another aggregate observation")
        province_rows[province_raw] = row
    if set(province_rows) != set(raw_provinces):
        _fail("K02 province components do not cover the raw capture")

    total = Decimal()
    flattened_total = Decimal()
    for province_raw, raw_component in raw_provinces.items():
        component = province_rows[province_raw]
        if not isinstance(raw_component, dict):
            _fail("K02 raw province component is not an object")
        province_total = _decimal(component.get("total_inno"), "K02 province total")
        if province_total != _decimal(
            raw_component.get("total_inno"), "K02 raw province total"
        ):
            _fail("K02 province total differs from its raw component")
        levels = _json_cell(component.get("levels_json"), dict, "K02 levels_json")
        raw_levels = raw_component.get("levels")
        if not isinstance(raw_levels, dict) or set(levels) != {"1", "2", "3", "4"}:
            _fail("K02 province must contain all four source levels")
        if set(raw_levels) != set(levels):
            _fail("K02 source levels do not cover the raw province")
        level_total = Decimal()
        component_id = str(component["component_id"])
        province_code = str(component.get("province_code", ""))
        province_name = str(
            component.get("province_normalized") or component.get("province_raw") or ""
        )
        for level in ("1", "2", "3", "4"):
            amount = _decimal(levels[level], "K02 source level")
            if amount != _decimal(raw_levels[level], "K02 raw source level"):
                _fail("K02 source level differs from its raw province")
            locator = _child_locator(
                root_locator, "prov_data", province_raw, "levels", level
            )
            actual = _raw_value(
                raw_inputs,
                source_id,
                observations,
                observation_id,
                locator,
                "K02 source level",
            )
            if _decimal(actual, "K02 cited source level") != amount:
                _fail("K02 source-level citation has the wrong value")
            stable_province = province_code or component_id
            out["aggregate_breakdowns"].append(
                _breakdown(
                    measure_id="K02",
                    breakdown_id="province_level",
                    member_id=f"{stable_province}:{level}",
                    amount=amount,
                    amount_unit="person",
                    result_divisor="1",
                    evidence_table="sources/f2_target_household/aggregate_components",
                    evidence_key="component_id",
                    evidence_id=component_id,
                    raw_locator=locator,
                    province_code=province_code,
                    province_name=province_name,
                    source_level=level,
                )
            )
            level_total += amount
        if level_total != province_total:
            _fail("K02 source levels do not reconcile within a province")
        total += province_total
        flattened_total += level_total
    if total != headline or flattened_total != headline:
        _fail("K02 components do not reconcile to the innovators_all headline")
    out["aggregate_results"].append(
        {"measure_id": "K02", "value_exact": _text(headline)}
    )


def _dashboard_observation(
    raw_inputs: dict,
    observations: dict[str, dict],
    source_key: str,
) -> tuple[dict, str, Any]:
    matches = [
        row for row in observations.values() if row.get("source_key") == source_key
    ]
    if len(matches) != 1:
        _fail(f"dashboard observation {source_key} is absent or ambiguous")
    observation = matches[0]
    observation_id = str(observation["observation_id"])
    locator = _observation_locator(
        raw_inputs, "f2_learning_dashboard", observations, observation_id
    )
    raw = _raw_value(
        raw_inputs,
        "f2_learning_dashboard",
        observations,
        observation_id,
        locator,
        f"dashboard {source_key}",
    )
    return observation, locator, raw


def _build_reported_businesses(
    source_tables: dict, raw_inputs: dict, observations: dict[str, dict], out: dict
) -> list[str]:
    source_id = "f2_learning_dashboard"
    headers = _table(source_tables, source_id, "count_dimension_headers")
    members = _table(source_tables, source_id, "count_members")
    header_by_dimension: dict[str, dict] = {}
    for header in headers:
        dimension = str(header.get("dimension", ""))
        if dimension in header_by_dimension:
            _fail("dashboard count dimension has duplicate headers")
        header_by_dimension[dimension] = header
    if set(header_by_dimension) != set(_COUNT_DIMENSIONS):
        _fail("dashboard count headers do not cover the four source dimensions")
    _index(headers, "header_id", "dashboard count header")
    _index(members, "count_member_id", "dashboard count member")
    if any(row.get("dimension") not in _COUNT_DIMENSIONS for row in members):
        _fail("dashboard count members contain an unknown source dimension")

    totals: dict[str, Decimal] = {}
    region_order: list[str] = []
    nonadditive_groups: set[str] = set()
    for dimension, dimension_label in _COUNT_DIMENSIONS.items():
        observation, root_locator, raw_dimension = _dashboard_observation(
            raw_inputs, observations, dimension
        )
        if not isinstance(raw_dimension, list) or not raw_dimension:
            _fail(f"{dimension} raw dimension is empty")
        header = header_by_dimension[dimension]
        raw_header = raw_dimension[0]
        if (
            not isinstance(raw_header, list)
            or len(raw_header) != 2
            or str(header.get("observation_id", ""))
            != str(observation["observation_id"])
            or header.get("label_header_raw") != raw_header[0]
            or header.get("count_header_raw") != raw_header[1]
            or header.get("treatment")
            != "retained_as_display_header_excluded_from_facts"
        ):
            _fail(f"{dimension} header does not match the raw capture")
        _require_row_locator(
            raw_inputs,
            source_id,
            observations,
            header,
            _child_locator(root_locator, 0),
            raw_header,
            f"{dimension} header",
        )
        rows = [row for row in members if row.get("dimension") == dimension]
        positions: dict[int, dict] = {}
        for row in rows:
            try:
                position = int(str(row.get("position", "")))
            except ValueError:
                _fail(f"{dimension} member has an invalid source position")
            if position in positions:
                _fail(f"{dimension} has duplicate source positions")
            positions[position] = row
        expected_positions = set(range(1, len(raw_dimension)))
        if set(positions) != expected_positions:
            _fail(f"{dimension} members do not cover the raw capture")

        total = Decimal()
        labels: list[str] = []
        for position in sorted(positions):
            row = positions[position]
            raw_member = raw_dimension[position]
            if not isinstance(raw_member, list) or len(raw_member) != 2:
                _fail(f"{dimension} raw member has the wrong shape")
            amount = _decimal(row.get("count"), f"{dimension} count")
            if (
                str(row.get("observation_id", "")) != str(observation["observation_id"])
                or row.get("header_id") != header.get("header_id")
                or row.get("dimension_label") != dimension_label
                or row.get("label_raw") != raw_member[0]
                or amount != _decimal(raw_member[1], f"{dimension} raw count")
                or row.get("unit") != "source-reported businesses"
                or row.get("filter_support") != "count_dimension_only"
                or not row.get("nonadditive_group")
            ):
                _fail(f"{dimension} member metadata differs from the source")
            nonadditive_groups.add(str(row["nonadditive_group"]))
            member_locator = _require_row_locator(
                raw_inputs,
                source_id,
                observations,
                row,
                _child_locator(root_locator, position),
                raw_member,
                f"{dimension} member",
            )
            amount_locator = _child_locator(member_locator, 1)
            cited_amount = _raw_value(
                raw_inputs,
                source_id,
                observations,
                str(row["observation_id"]),
                amount_locator,
                f"{dimension} count",
            )
            if _decimal(cited_amount, f"{dimension} cited count") != amount:
                _fail(f"{dimension} count citation has the wrong value")
            out["aggregate_breakdowns"].append(
                _breakdown(
                    measure_id="C08_REPORTED_BUSINESSES",
                    breakdown_id=dimension,
                    member_id=str(row["count_member_id"]),
                    amount=amount,
                    amount_unit="business",
                    result_divisor="1",
                    evidence_table="sources/f2_learning_dashboard/count_members",
                    evidence_key="count_member_id",
                    evidence_id=str(row["count_member_id"]),
                    raw_locator=amount_locator,
                    member_label=str(row.get("label_raw", "")),
                )
            )
            labels.append(str(row.get("label_raw", "")))
            total += amount
        totals[dimension] = total
        if dimension == "geography":
            region_order = labels
    if len(nonadditive_groups) != 1 or len(set(totals.values())) != 1:
        _fail("reported-business dimensions do not independently reconcile")
    headline = totals["categories"]
    out["aggregate_results"].append(
        {
            "measure_id": "C08_REPORTED_BUSINESSES",
            "value_exact": _text(headline),
        }
    )
    return region_order


def _validate_regions(
    source_tables: dict,
    raw_inputs: dict,
    observations: dict[str, dict],
    region_order: list[str],
) -> tuple[dict[str, dict], list[dict]]:
    source_id = "f2_learning_dashboard"
    regionals = _table(source_tables, source_id, "regional_impacts")
    regional_by_id = _index(regionals, "regional_impact_id", "regional impact")
    observation, root_locator, raw_impacts = _dashboard_observation(
        raw_inputs, observations, "geographyImpact"
    )
    if (
        len(region_order) != 6
        or not isinstance(raw_impacts, list)
        or len(raw_impacts) != 6
        or len(regional_by_id) != 6
    ):
        _fail("dashboard impacts require all six source regions")
    by_position: dict[int, dict] = {}
    for regional in regional_by_id.values():
        try:
            position = int(str(regional.get("position", "")))
        except ValueError:
            _fail("regional impact has an invalid source position")
        if position in by_position:
            _fail("regional impacts have duplicate source positions")
        by_position[position] = regional
    if set(by_position) != set(range(1, 7)):
        _fail("regional impacts do not cover all six source positions")
    for position, regional in by_position.items():
        if (
            str(regional.get("observation_id", ""))
            != str(observation["observation_id"])
            or regional.get("region_raw") != region_order[position - 1]
            or not regional.get("region_mapping_basis")
        ):
            _fail("regional impact mapping differs from source metadata")
        _require_row_locator(
            raw_inputs,
            source_id,
            observations,
            regional,
            _child_locator(root_locator, position - 1),
            raw_impacts[position - 1],
            "regional impact",
        )
    return regional_by_id, raw_impacts


def _validate_impact_field(
    *,
    field: str,
    source_tables: dict,
    raw_inputs: dict,
    observations: dict[str, dict],
    regional_by_id: dict[str, dict],
    raw_impacts: list[dict],
) -> tuple[list[dict], Decimal]:
    source_id = "f2_learning_dashboard"
    kind, summary_name, unit = _IMPACT_FIELDS[field]
    all_components = _table(source_tables, source_id, "impact_components")
    rows = [row for row in all_components if row.get("raw_field") == field]
    _index(rows, "component_id", field)
    by_regional: dict[str, dict] = {}
    total = Decimal()
    for row in rows:
        regional_id = str(row.get("regional_impact_id", ""))
        regional = regional_by_id.get(regional_id)
        if regional is None or regional_id in by_regional:
            _fail(f"{field} has a duplicate or unknown regional component")
        by_regional[regional_id] = row
        position = int(str(regional["position"]))
        amount = _decimal(row.get("amount"), field)
        raw_impact = raw_impacts[position - 1]
        if not isinstance(raw_impact, dict) or field not in raw_impact:
            _fail(f"{field} is absent from a raw regional impact")
        if (
            str(row.get("observation_id", ""))
            != str(regional.get("observation_id", ""))
            or str(row.get("position", "")) != str(regional.get("position", ""))
            or row.get("region_raw") != regional.get("region_raw")
            or row.get("metric_kind") != kind
            or row.get("unit") != unit
            or amount != _decimal(raw_impact[field], f"raw {field}")
        ):
            _fail(f"{field} component metadata differs from its source region")
        root_locator = _observation_locator(
            raw_inputs,
            source_id,
            observations,
            str(row["observation_id"]),
        )
        _require_row_locator(
            raw_inputs,
            source_id,
            observations,
            row,
            _child_locator(root_locator, position - 1, field),
            raw_impact[field],
            field,
        )
        total += amount
    if set(by_regional) != set(regional_by_id):
        _fail(f"{field} does not cover all six source regions")

    summaries = _table(source_tables, source_id, "impact_summary_metrics")
    matches = [row for row in summaries if row.get("raw_field") == summary_name]
    if len(matches) != 1:
        _fail(f"{field} reconciliation summary is absent or ambiguous")
    summary = matches[0]
    observation, root_locator, raw_summary = _dashboard_observation(
        raw_inputs, observations, "impactSummary"
    )
    if not isinstance(raw_summary, dict) or summary_name not in raw_summary:
        _fail(f"{field} raw reconciliation summary is absent")
    summary_amount = _decimal(summary.get("amount"), f"{field} summary")
    if (
        str(summary.get("observation_id", "")) != str(observation["observation_id"])
        or summary.get("stable_metric_name")
        != (
            "reported_monthly_employment_total"
            if field == "localEmployeeAmount"
            else summary_name
        )
        or summary.get("unit") != unit
        or summary.get("treatment") != "reconciliation_only_not_additional_contribution"
        or summary_amount != _decimal(raw_summary[summary_name], f"raw {field} summary")
        or summary_amount != total
    ):
        _fail(f"{field} components do not reconcile to their source summary")
    _require_row_locator(
        raw_inputs,
        source_id,
        observations,
        summary,
        _child_locator(root_locator, summary_name),
        raw_summary[summary_name],
        f"{field} summary",
    )
    return rows, total


def _add_impact_rows(
    out: dict,
    measure_id: str,
    rows: list[dict],
    divisor: Decimal,
) -> None:
    for row in rows:
        out["aggregate_breakdowns"].append(
            _breakdown(
                measure_id=measure_id,
                breakdown_id="components",
                member_id=str(row["component_id"]),
                amount=_decimal(row["amount"], measure_id),
                amount_unit=str(row["unit"]),
                result_divisor=_text(divisor),
                evidence_table="sources/f2_learning_dashboard/impact_components",
                evidence_key="component_id",
                evidence_id=str(row["component_id"]),
                raw_locator=str(row["raw_locator"]),
                region=str(row["region_raw"]),
                component=str(row["raw_field"]),
            )
        )


def _build_impacts(
    source_tables: dict,
    raw_inputs: dict,
    observations: dict[str, dict],
    region_order: list[str],
    out: dict,
) -> None:
    regional_by_id, raw_impacts = _validate_regions(
        source_tables, raw_inputs, observations, region_order
    )
    selected: dict[str, list[dict]] = {}
    totals: dict[str, Decimal] = {}
    for field in _IMPACT_FIELDS:
        rows, total = _validate_impact_field(
            field=field,
            source_tables=source_tables,
            raw_inputs=raw_inputs,
            observations=observations,
            regional_by_id=regional_by_id,
            raw_impacts=raw_impacts,
        )
        selected[field] = rows
        totals[field] = total

    _add_impact_rows(out, "K09", selected["localEmployeeAmount"], Decimal(1))
    out["aggregate_results"].append(
        {"measure_id": "K09", "value_exact": _text(totals["localEmployeeAmount"])}
    )
    k10_rows = selected["localEmployeeExpense"] + selected["localResourceExpense"]
    _add_impact_rows(out, "K10", k10_rows, _MILLION)
    k10_total = totals["localEmployeeExpense"] + totals["localResourceExpense"]
    out["aggregate_results"].append(
        {"measure_id": "K10", "value_exact": _text(k10_total / _MILLION)}
    )

    resource_rows = selected["localResourceExpense"]
    _add_impact_rows(out, "C10_ALTERNATIVE", resource_rows, _MILLION)
    excluded_rows = _table(source_tables, "f2_learning_dashboard", "excluded_amounts")
    excluded_by_id = _index(
        excluded_rows, "excluded_amount_id", "excluded resource amount"
    )
    if len(excluded_by_id) != 1:
        _fail("alternative requires one separately reported excluded amount")
    excluded = next(iter(excluded_by_id.values()))
    observation, root_locator, raw_excluded = _dashboard_observation(
        raw_inputs, observations, "excludedResourceExpense"
    )
    amount = _decimal(excluded.get("amount"), "excluded resource amount")
    if (
        not isinstance(raw_excluded, dict)
        or set(raw_excluded) != {"region", "amount"}
        or excluded.get("region_raw") != raw_excluded["region"]
        or amount != _decimal(raw_excluded["amount"], "raw excluded resource amount")
        or str(excluded.get("observation_id", "")) != str(observation["observation_id"])
        or excluded.get("unit") != "THB/month_assumed_for_K10B_only"
        or excluded.get("meaning_status") != "reviewed_unresolved"
        or excluded.get("treatment")
        != "separate_component_used_only_under_K10B_assumption"
    ):
        _fail("excluded resource amount differs from its source assumption")
    _require_row_locator(
        raw_inputs,
        "f2_learning_dashboard",
        observations,
        excluded,
        root_locator,
        raw_excluded,
        "excluded resource amount",
    )
    amount_locator = _child_locator(root_locator, "amount")
    if (
        _decimal(
            _raw_value(
                raw_inputs,
                "f2_learning_dashboard",
                observations,
                str(excluded["observation_id"]),
                amount_locator,
                "excluded resource amount",
            ),
            "cited excluded resource amount",
        )
        != amount
    ):
        _fail("excluded-resource citation has the wrong value")
    out["aggregate_breakdowns"].append(
        _breakdown(
            measure_id="C10_ALTERNATIVE",
            breakdown_id="components",
            member_id=str(excluded["excluded_amount_id"]),
            amount=amount,
            amount_unit="THB/month_assumed",
            result_divisor="1000000",
            evidence_table="sources/f2_learning_dashboard/excluded_amounts",
            evidence_key="excluded_amount_id",
            evidence_id=str(excluded["excluded_amount_id"]),
            raw_locator=amount_locator,
            region=str(excluded["region_raw"]),
            component="excludedResourceExpense",
        )
    )
    alternative = totals["localResourceExpense"] + amount
    out["aggregate_results"].append(
        {
            "measure_id": "C10_ALTERNATIVE",
            "value_exact": _text(alternative / _MILLION),
        }
    )


def _area_capture(raw_inputs: dict) -> list[dict]:
    bundle = raw_inputs.get("f2_learning_area_based")
    if not isinstance(bundle, dict):
        _fail("missing learning-area raw capture")
    metadata = bundle.get("metadata")
    datasets = bundle.get("datasets")
    if not isinstance(metadata, dict) or not isinstance(datasets, dict):
        _fail("learning-area raw capture bundle is malformed")
    keys = [
        key
        for key, row in metadata.items()
        if isinstance(row, dict) and row.get("file") == "area_based.json"
    ]
    if len(keys) != 1 or keys[0] not in datasets:
        _fail("learning-area authoritative capture is absent or ambiguous")
    capture = datasets[keys[0]]
    if not isinstance(capture, dict) or not isinstance(capture.get("data"), list):
        _fail("learning-area authoritative capture has no data array")
    rows = capture["data"]
    if not all(isinstance(row, dict) and row.get("id") for row in rows):
        _fail("learning-area capture contains an invalid source row")
    stats = capture.get("stats")
    if not isinstance(stats, dict) or _decimal(
        stats.get("totalRecords"), "learning-area source total"
    ) != Decimal(len(rows)):
        _fail("learning-area capture completeness metadata does not reconcile")
    return rows


def _build_participation(source_tables: dict, raw_inputs: dict, out: dict) -> None:
    source_id = "f2_learning_area_based"
    observations = _observation_index(source_tables, source_id)
    businesses = _table(source_tables, source_id, "businesses")
    links = _table(source_tables, source_id, "business_observation_links")
    participations = _table(source_tables, source_id, "participations")
    contributions = _table(source_tables, source_id, "measure_contributions")
    locations = _table(source_tables, source_id, "locations")
    raw_rows = _area_capture(raw_inputs)
    raw_by_source_id = _index(raw_rows, "id", "learning-area raw row")
    business_by_id = _index(businesses, "business_id", "participating business")
    link_by_observation = _index(links, "observation_id", "business observation link")
    _index(participations, "participation_id", "participation")
    location_by_id = _index(locations, "location_id", "business location")

    if len(observations) != len(raw_by_source_id) or len(links) != len(observations):
        _fail("learning-area observations do not cover the raw source capture")
    for observation_id, observation in observations.items():
        source_key = str(observation.get("source_id", ""))
        raw_row = raw_by_source_id.get(source_key)
        if raw_row is None:
            _fail("learning-area observation changed source identity")
        locator = _observation_locator(
            raw_inputs, source_id, observations, observation_id
        )
        cited = _raw_value(
            raw_inputs,
            source_id,
            observations,
            observation_id,
            locator,
            "learning-area observation",
        )
        if cited != raw_row:
            _fail("learning-area observation citation does not match its source row")
        link = link_by_observation.get(observation_id)
        if (
            link is None
            or link.get("source_id") != source_key
            or str(link.get("business_id", "")) not in business_by_id
        ):
            _fail("learning-area observation is not linked to its source business")

    link_pairs = {
        (str(row.get("business_id", "")), str(row.get("observation_id", "")))
        for row in links
    }
    participation_pairs = {
        (str(row.get("business_id", "")), str(row.get("observation_id", "")))
        for row in participations
    }
    if participation_pairs != link_pairs or len(participations) != len(link_pairs):
        _fail("participations do not preserve the source business links")
    location_pairs = {
        (str(row.get("business_id", "")), str(row.get("observation_id", "")))
        for row in locations
    }
    if location_pairs != link_pairs or len(locations) != len(link_pairs):
        _fail("locations do not preserve the source business links")

    observations_by_business: dict[str, set[str]] = {
        business_id: set() for business_id in business_by_id
    }
    source_ids_by_business: dict[str, set[str]] = {
        business_id: set() for business_id in business_by_id
    }
    for observation_id, link in link_by_observation.items():
        business_id = str(link["business_id"])
        observations_by_business[business_id].add(observation_id)
        source_ids_by_business[business_id].add(str(link["source_id"]))
    eligible_businesses: set[str] = set()
    for business_id, business in business_by_id.items():
        source_ids = set(
            str(value)
            for value in _json_cell(
                business.get("source_ids_json"), list, "business source_ids_json"
            )
        )
        if source_ids != source_ids_by_business[business_id] or not source_ids:
            _fail("business identity does not preserve its source observation links")
        if _truth(business.get("eligible_k08"), "business eligible_k08"):
            eligible_businesses.add(business_id)

    eligible = [
        row
        for row in contributions
        if row.get("measure") == "K08_participating_businesses_provisional"
    ]
    contribution_by_business = _index(
        eligible, "business_id", "participating contribution"
    )
    if set(contribution_by_business) != eligible_businesses:
        _fail("participating contributions do not cover eligible source businesses")

    locations_by_business: dict[str, list[dict]] = {
        business_id: [] for business_id in eligible_businesses
    }
    for location in location_by_id.values():
        business_id = str(location.get("business_id", ""))
        observation_id = str(location.get("observation_id", ""))
        if (business_id, observation_id) not in link_pairs:
            _fail("business location belongs to another source identity")
        raw_row = raw_by_source_id[str(observations[observation_id]["source_id"])]
        if str(location.get("province_raw") or "") != str(
            raw_row.get("province") or ""
        ):
            _fail("business location province differs from its source observation")
        if business_id in locations_by_business:
            locations_by_business[business_id].append(location)

    for business_id in sorted(eligible_businesses):
        contribution = contribution_by_business[business_id]
        business = business_by_id[business_id]
        evidence_ids = [
            str(value)
            for value in _json_cell(
                contribution.get("evidence_observation_ids_json"),
                list,
                "participation evidence_observation_ids_json",
            )
        ]
        owned_observations = observations_by_business[business_id]
        expected_status = (
            "provisional_unit"
            if len(owned_observations) == 1
            else "supported_merged_business"
        )
        if (
            not evidence_ids
            or len(evidence_ids) != len(set(evidence_ids))
            or set(evidence_ids) != owned_observations
            or contribution.get("province_code")
            or contribution.get("location_role") != "programme_business_location"
            or contribution.get("contribution_status") != expected_status
        ):
            _fail(
                "participation contribution has wrong-business or incomplete evidence"
            )
        out["entity_contributions"].append(
            {
                "entity_id": business_id,
                "label": str(business.get("display_name", "")),
                "measure_id": "C08_PARTICIPATING",
            }
        )
        out["evidence_links"].append(
            {
                "entity_id": business_id,
                "evidence_role": "participating_business_identity",
                "key": "business_id",
                "measure_id": "C08_PARTICIPATING",
                "record_id": business_id,
                "table": "sources/f2_learning_area_based/businesses",
            }
        )
        for observation_id in evidence_ids:
            _observation_locator(raw_inputs, source_id, observations, observation_id)
            evidence = {
                "entity_id": business_id,
                "evidence_id": observation_id,
                "evidence_key": "observation_id",
                "evidence_role": "participation",
                "evidence_table": "sources/f2_learning_area_based/source_observations",
                "measure_id": "C08_PARTICIPATING",
            }
            out["eligibility_evidence"].append(evidence)
        for location in locations_by_business[business_id]:
            province_code = str(location.get("province_code", ""))
            if (
                not province_code
                or location.get("resolution_status") == "unresolved_province"
            ):
                continue
            if location.get("location_role") != contribution.get("location_role"):
                _fail("participation location role differs from its contribution")
            out["province_memberships"].append(
                {
                    "entity_id": business_id,
                    "evidence_id": str(location["location_id"]),
                    "evidence_key": "location_id",
                    "evidence_table": "sources/f2_learning_area_based/locations",
                    "location_role": str(location["location_role"]),
                    "measure_id": "C08_PARTICIPATING",
                    "province_code": province_code,
                }
            )
    out["aggregate_results"].append(
        {
            "measure_id": "C08_PARTICIPATING",
            "value_exact": str(len(eligible_businesses)),
        }
    )


def build_tables(
    source_tables: dict,
    reviews: dict,
    raw_inputs: dict,
    geography: Any,
) -> dict[str, list[dict]]:
    """Build six independently reconciled results from canonical injected inputs."""
    if not isinstance(source_tables, dict) or not isinstance(raw_inputs, dict):
        _fail("source tables and raw inputs are required")
    if not isinstance(reviews, dict):
        _fail("reviews must be an injected mapping")
    del geography
    out = {name: [] for name in TABLE_COLUMNS}
    _build_k02(source_tables, raw_inputs, out)
    dashboard_observations = _observation_index(source_tables, "f2_learning_dashboard")
    region_order = _build_reported_businesses(
        source_tables, raw_inputs, dashboard_observations, out
    )
    _build_impacts(source_tables, raw_inputs, dashboard_observations, region_order, out)
    _build_participation(source_tables, raw_inputs, out)
    expected_results = {
        "K02",
        "C08_REPORTED_BUSINESSES",
        "K09",
        "K10",
        "C10_ALTERNATIVE",
        "C08_PARTICIPATING",
    }
    if {row["measure_id"] for row in out["aggregate_results"]} != expected_results:
        _fail("Phase 6 aggregate results are incomplete")
    return out
