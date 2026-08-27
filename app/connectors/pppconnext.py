"""Public 2026 PPPConnext aggregate APIs → Candidate grains.

The serving connector calls only the four unauthenticated dashboard endpoints
already in the generated catalog. It does not follow login, Open API Bearer,
``/areas/*`` guest 401 routes, or extra ``prov_code`` loops that are not in the
runtime allowlist. Per-province analytics beyond the national ``prov_code=0``
call remain evidence-workspace/R2 inventory.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.connectors.base import ConnectorContext, DatasetRecord

SOURCE_ID = "f1_pppconnext"
EXPECTED_RECORD_COUNT = 47
EXPECTED_PROVINCE_COUNT = 20
EXPECTED_SURVEY_YEAR_COUNT = 7
EXPECTED_CAPITAL_DIMENSIONS = 5
EXPECTED_ASSISTANCE_DIMENSIONS = 5
REQUIRED_REQUESTS = (
    "national_bootstrap",
    "province_analytics",
    "poor_capital_potential",
    "assistance_summary",
)


def _stable_id(record_type: str, *parts: Any) -> str:
    key = "|".join([SOURCE_ID, record_type, *(str(part) for part in parts)])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _require_success_data(payload: Any, name: str) -> dict:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RuntimeError(f"PPPConnext {name} success is not true")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"PPPConnext {name} data is not an object")
    return data


def _zfill_code(value: Any) -> str:
    if value in (None, ""):
        raise RuntimeError("PPPConnext province code is missing")
    return str(value).zfill(2)


def _object_list(value: Any, label: str) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise RuntimeError(f"PPPConnext {label} is not an object array")
    return value


def build_candidate_records(
    *,
    national_bootstrap: dict,
    province_analytics: dict,
    poor_capital_potential: dict,
    assistance_summary: dict,
    expected_record_count: int = EXPECTED_RECORD_COUNT,
) -> list[DatasetRecord]:
    """Project the four public envelopes into the reviewed 47-row grain set."""

    national = _require_success_data(national_bootstrap, "national_bootstrap")
    analytics = _require_success_data(province_analytics, "province_analytics")
    capital = _require_success_data(poor_capital_potential, "poor_capital_potential")
    assistance = _require_success_data(assistance_summary, "assistance_summary")

    map_summary = national.get("map_summary")
    survey_years = national.get("available_survey_years")
    if not isinstance(map_summary, dict) or not isinstance(survey_years, dict):
        raise RuntimeError("PPPConnext national bootstrap is missing map_summary or survey years")
    items = _object_list(map_summary.get("items"), "map_summary.items")
    summary = map_summary.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("PPPConnext map_summary.summary is not an object")

    meta = national_bootstrap.get("meta") if isinstance(national_bootstrap, dict) else None
    allowed_codes = {
        _zfill_code(code)
        for code in (meta.get("allowed_province_codes") if isinstance(meta, dict) else []) or []
    }
    item_codes = {_zfill_code(item.get("prov_code")) for item in items}
    if (
        len(items) != EXPECTED_PROVINCE_COUNT
        or allowed_codes != item_codes
        or len(item_codes) != EXPECTED_PROVINCE_COUNT
    ):
        raise RuntimeError(
            "PPPConnext province inventory incomplete: "
            f"items={len(items)}, unique={len(item_codes)}, "
            f"allowed={len(allowed_codes)}"
        )

    households_by_year = _object_list(
        survey_years.get("households_by_year"),
        "available_survey_years.households_by_year",
    )
    cumulative = _object_list(
        analytics.get("by_year_cumulative"),
        "province_analytics.by_year_cumulative",
    )
    capital_dimensions = _object_list(capital.get("dimensions"), "capital dimensions")
    assistance_dimensions = _object_list(assistance.get("dimensions"), "assistance dimensions")
    if len(households_by_year) != EXPECTED_SURVEY_YEAR_COUNT:
        raise RuntimeError(
            f"PPPConnext survey-year rows={len(households_by_year)}; "
            f"expected {EXPECTED_SURVEY_YEAR_COUNT}"
        )
    if len(cumulative) != EXPECTED_SURVEY_YEAR_COUNT:
        raise RuntimeError(
            f"PPPConnext cumulative rows={len(cumulative)}; expected {EXPECTED_SURVEY_YEAR_COUNT}"
        )
    if len(capital_dimensions) != EXPECTED_CAPITAL_DIMENSIONS:
        raise RuntimeError(
            f"PPPConnext capital dimensions={len(capital_dimensions)}; "
            f"expected {EXPECTED_CAPITAL_DIMENSIONS}"
        )
    if len(assistance_dimensions) != EXPECTED_ASSISTANCE_DIMENSIONS:
        raise RuntimeError(
            f"PPPConnext assistance dimensions={len(assistance_dimensions)}; "
            f"expected {EXPECTED_ASSISTANCE_DIMENSIONS}"
        )
    for field in ("households_in_system_total", "members_in_system_total", "member_registration"):
        if field not in analytics:
            raise RuntimeError(f"PPPConnext province analytics missing {field}")

    records: list[DatasetRecord] = []
    records.append(
        (
            "national_summary",
            {
                "record_id": _stable_id("national_summary", "all"),
                "record_type": "national_summary",
                "grain": "all_20_provinces_unique_households_all_survey_years",
                "geography_level": "national_dashboard_scope",
                "geography_code": "0",
                "geography_name_th": "ภาพรวม 20 จังหวัด",
                "survey_year": None,
                "as_of": None,
                "values": {
                    **summary,
                    "households_in_system_total": analytics["households_in_system_total"],
                    "members_in_system_total": analytics["members_in_system_total"],
                    "member_registration": analytics["member_registration"],
                },
            },
        )
    )
    for item in items:
        code = _zfill_code(item.get("prov_code"))
        name = item.get("prov_name")
        if not name:
            raise RuntimeError(f"PPPConnext province {code} is missing prov_name")
        records.append(
            (
                "province_summary",
                {
                    "record_id": _stable_id("province_summary", code, "all"),
                    "record_type": "province_summary",
                    "grain": "province_unique_households_all_survey_years",
                    "geography_level": "province",
                    "geography_code": code,
                    "geography_name_th": name,
                    "survey_year": None,
                    "as_of": None,
                    "values": {
                        key: value
                        for key, value in item.items()
                        if key not in {"prov_code", "prov_name"}
                    },
                },
            )
        )
    for item in households_by_year:
        year = item.get("survey_year")
        if year in (None, ""):
            raise RuntimeError("PPPConnext survey-year household row is missing survey_year")
        records.append(
            (
                "survey_year_households",
                {
                    "record_id": _stable_id("survey_year_households", year),
                    "record_type": "survey_year_households",
                    "grain": "survey_year_non_deduplicated_across_years",
                    "geography_level": "national_dashboard_scope",
                    "geography_code": "0",
                    "geography_name_th": "ภาพรวม 20 จังหวัด",
                    "survey_year": year,
                    "as_of": None,
                    "values": {"households_total": item.get("households_total")},
                },
            )
        )
    for item in cumulative:
        year = item.get("survey_year")
        if year in (None, ""):
            raise RuntimeError("PPPConnext cumulative row is missing survey_year")
        records.append(
            (
                "survey_year_cumulative",
                {
                    "record_id": _stable_id("survey_year_cumulative", year),
                    "record_type": "survey_year_cumulative",
                    "grain": "cumulative_unique_households_through_survey_year",
                    "geography_level": "national_dashboard_scope",
                    "geography_code": "0",
                    "geography_name_th": "ภาพรวม 20 จังหวัด",
                    "survey_year": year,
                    "as_of": None,
                    "values": {
                        key: value for key, value in item.items() if key != "survey_year"
                    },
                },
            )
        )
    for item in capital_dimensions:
        key = item.get("key")
        if not key:
            raise RuntimeError("PPPConnext capital dimension is missing key")
        records.append(
            (
                "capital_dimension",
                {
                    "record_id": _stable_id("capital_dimension", key, "all"),
                    "record_type": "capital_dimension",
                    "grain": "capital_dimension_all_households_all_survey_years",
                    "geography_level": "national_dashboard_scope",
                    "geography_code": "0",
                    "geography_name_th": "ภาพรวม 20 จังหวัด",
                    "survey_year": None,
                    "dimension_key": key,
                    "dimension_label_th": item.get("label"),
                    "as_of": None,
                    "values": {
                        "average": item.get("avg"),
                        "standard_deviation": item.get("sd"),
                    },
                },
            )
        )
    records.append(
        (
            "capital_overall",
            {
                "record_id": _stable_id("capital_overall", "all"),
                "record_type": "capital_overall",
                "grain": "five_capital_overall_all_households_all_survey_years",
                "geography_level": "national_dashboard_scope",
                "geography_code": "0",
                "geography_name_th": "ภาพรวม 20 จังหวัด",
                "survey_year": None,
                "as_of": None,
                "values": {
                    "household_count": capital.get("household_count"),
                    "average": capital.get("overall_avg"),
                    "standard_deviation": capital.get("overall_sd"),
                },
            },
        )
    )
    assistance_year = assistance.get("year")
    assistance_year_scope = assistance.get("year_label")
    if assistance_year in (None, "") or not assistance_year_scope:
        raise RuntimeError("PPPConnext assistance summary is missing year or year_label")
    for item in assistance_dimensions:
        key = item.get("key")
        if not key:
            raise RuntimeError("PPPConnext assistance dimension is missing key")
        records.append(
            (
                "assistance_dimension",
                {
                    "record_id": _stable_id("assistance_dimension", key, assistance_year),
                    "record_type": "assistance_dimension",
                    "grain": "assistance_dimension_selected_assistance_years",
                    "geography_level": "national_dashboard_scope",
                    "geography_code": "0",
                    "geography_name_th": "ภาพรวม 20 จังหวัด",
                    "survey_year": None,
                    "assistance_year_scope": assistance_year_scope,
                    "dimension_key": key,
                    "dimension_label_th": item.get("title"),
                    "as_of": None,
                    "values": {
                        "households": item.get("households"),
                        "episode_count": item.get("episode_count"),
                        "budget_baht": item.get("budget_baht"),
                        "household_share_pct": item.get("share_pct"),
                        "episode_share_pct": item.get("episode_share_pct"),
                        "budget_share_pct": item.get("budget_share_pct"),
                    },
                },
            )
        )
    records.append(
        (
            "assistance_summary",
            {
                "record_id": _stable_id("assistance_summary", assistance_year),
                "record_type": "assistance_summary",
                "grain": "unique_assisted_households_selected_assistance_years",
                "geography_level": "national_dashboard_scope",
                "geography_code": "0",
                "geography_name_th": "ภาพรวม 20 จังหวัด",
                "survey_year": None,
                "assistance_year_scope": assistance_year_scope,
                "as_of": None,
                "values": {
                    "total_households": assistance.get("total_households"),
                    "total_episodes": assistance.get("total_episodes"),
                    "total_budget_baht": assistance.get("total_budget_baht"),
                },
            },
        )
    )

    identities = [row["record_id"] for _, row in records]
    if len(identities) != len(set(identities)):
        raise RuntimeError("PPPConnext candidate identities are duplicated")
    if len(records) != expected_record_count:
        raise RuntimeError(
            f"PPPConnext incomplete: records={len(records)}; expected {expected_record_count}"
        )
    return records


class PppconnextConnector:
    driver_name = "pppconnext"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        requests = list(context.plan.get("requests") or [])
        names = [str(request.get("name") or "") for request in requests]
        if names != list(REQUIRED_REQUESTS):
            raise RuntimeError(
                "PPPConnext plan must declare the four catalog APIs in reviewed order: "
                + ", ".join(REQUIRED_REQUESTS)
            )
        payloads: dict[str, dict] = {}
        for request in requests:
            response, _ = context.recorder.request(
                "GET",
                request["url"],
                name=request["name"],
            )
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError(f"PPPConnext {request['name']} response is not an object")
            payloads[request["name"]] = payload
        records = build_candidate_records(
            national_bootstrap=payloads["national_bootstrap"],
            province_analytics=payloads["province_analytics"],
            poor_capital_potential=payloads["poor_capital_potential"],
            assistance_summary=payloads["assistance_summary"],
            expected_record_count=int(
                context.plan.get("expected_record_count") or EXPECTED_RECORD_COUNT
            ),
        )
        return context.apply_limit(records)
