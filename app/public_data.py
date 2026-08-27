from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.public_artifacts import artifact_payload
from app.settings import PROJECT_ROOT


PUBLIC_DATA_ROOT = PROJECT_ROOT / "data" / "public"


@lru_cache(maxsize=8)
def load_public_file(filename: str) -> dict[str, Any]:
    path = (PUBLIC_DATA_ROOT / filename).resolve()
    if path.parent != PUBLIC_DATA_ROOT.resolve() or not path.exists():
        raise FileNotFoundError(filename)
    return json.loads(path.read_text(encoding="utf-8"))


def load_public_artifact(artifact_key: str, fallback_filename: str) -> dict[str, Any]:
    """Read from the serving database, with a startup-safe file fallback."""

    try:
        with SessionLocal() as session:
            payload = artifact_payload(session, artifact_key)
        if payload is not None:
            return payload
    except SQLAlchemyError:
        # The fallback keeps CLI builders/import-time checks usable before init_db.
        pass
    return load_public_file(fallback_filename)


def public_catalog() -> dict[str, Any]:
    return load_public_artifact("catalog", "public_dashboard.json")


def province_boundaries() -> dict[str, Any]:
    return load_public_artifact("map/provinces", "thailand_provinces.geojson")


def cultural_points() -> dict[str, Any]:
    return load_public_artifact("map/cultural-points", "cultural_points.geojson")


def source_insights() -> dict[str, Any]:
    return load_public_artifact("source-insights", "source_insights.json")


def source_coverage() -> dict[str, Any]:
    return load_public_artifact("source-coverage", "source_coverage.json")


def unmapped_records() -> dict[str, Any]:
    return load_public_artifact("unmapped-records", "unmapped_records.json")


def housing_spatial_summary() -> dict[str, Any]:
    return load_public_artifact("housing-spatial-summary", "housing_spatial_summary.json")


def housing_demand_summary() -> dict[str, Any]:
    return load_public_artifact("housing-demand-summary", "housing_demand_summary.json")


def learning_dashboard() -> dict[str, Any]:
    return load_public_artifact("learning-dashboard", "learning_dashboard.json")


def disaster_tracking() -> dict[str, Any]:
    """Return the reviewed disaster projection, never operational candidate rows."""

    return load_public_artifact("disaster-tracking", "disaster_tracking.json")


def f1_details() -> dict[str, Any]:
    """Return the reviewed aggregate F1 province, district and tambon projection."""

    return load_public_artifact("f1/details", "f1_detail_projection.json")


def f1_province_details(province_code: str) -> dict[str, Any]:
    code = province_code.strip().zfill(2)
    payload = f1_details()
    province = (payload.get("provinces") or {}).get(code)
    if province is None:
        raise FileNotFoundError(code)
    return {
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "publication_status": payload.get("publication_status"),
        "source_id": payload.get("source_id"),
        "as_of": payload.get("as_of"),
        "source_url": payload.get("source_url"),
        "dashboard_url": payload.get("dashboard_url"),
        "privacy": payload.get("privacy"),
        "province": province,
    }


def _display_number(value: Any) -> int | float:
    number = float(value or 0)
    return int(number) if number.is_integer() else number


@lru_cache(maxsize=1)
def f1_overview() -> dict[str, Any]:
    """Aggregate the reviewed F1 province projections for the map experience.

    This endpoint derives only from already-reviewed public artifacts. It never
    fetches upstream data and never reads operational candidate records.
    """

    catalog = public_catalog()
    target_provinces = [
        province
        for province in catalog.get("provinces", [])
        if str(province.get("sra_scope_status") or "").startswith("in_scope")
    ]
    details = f1_details()
    metric_keys = (
        "people",
        "households",
        "poor_people",
        "poor_households",
        "om_count",
        "chain_count",
        "om_capital_baht",
        "assistance_households",
        "assistance_episodes",
        "assistance_budget_baht",
        "area_developers",
        "area_researchers",
        "support_organizations",
        "project_households",
        "project_poor_people",
        "local_people",
        "freelance_workers",
        "entrepreneurs",
        "vvn_organizations",
        "apptech_institute",
        "apptech_rmu",
        "innovations",
        "project_households_target",
        "project_poor_people_target",
    )

    def empty_totals() -> dict[str, Any]:
        return {
            "province_count": 0,
            **{key: 0 for key in metric_keys},
            "latest_assistance_year": None,
            "score_province_count": 0,
            "overall_score_average": None,
        }

    province_rows: list[dict[str, Any]] = []
    for province in target_provinces:
        code = str(province["province_code"]).zfill(2)
        detail_province = (details.get("provinces") or {}).get(code) or {}
        briefing = provincial_briefing(code)
        sections = briefing.get("sections", {})
        sra = sections.get("sra") or {}
        ppp = sections.get("pppconnext") or {}
        ppp_values = {
            item.get("metric_key"): item.get("value")
            for item in ppp.get("items", [])
            if item.get("metric_key")
        }
        detail_project = detail_province.get("project") or {}
        detail_project_items = detail_project.get("items") or []
        briefing_project_items = sra.get("project_metrics_latest", [])
        project_items = detail_project_items or briefing_project_items
        project_values = {
            item.get("key") or item.get("metric_key"): item.get("value")
            for item in project_items
            if item.get("key") or item.get("metric_key")
        }
        project_targets = {
            item.get("key") or item.get("metric_key"): item.get("target_value")
            for item in project_items
            if item.get("key") or item.get("metric_key")
        }
        project_year = detail_project.get("year")
        if not project_year and briefing_project_items:
            project_year = briefing_project_items[0].get("year")
        assistance_rows = sorted(
            sra.get("assistance_trend", []),
            key=lambda item: int(item.get("year") or 0),
        )
        assistance = assistance_rows[-1] if assistance_rows else {}
        assistance_dimensions = [
            {
                "year": item.get("year"),
                "dimension_key": item.get("dimension_key"),
                "dimension_title": item.get("dimension_title"),
                "households": _display_number(item.get("households")),
                "episodes": _display_number(item.get("episodes")),
                "budget_baht": _display_number(item.get("budget_baht")),
            }
            for item in sra.get("assistance_dimensions_latest", [])
            if item.get("dimension_key")
        ]
        om = sra.get("om_total") or {}
        score = province.get("sra_overall_score")

        province_rows.append(
            {
                "province_code": code,
                "province_name_th": province.get("province_name_th"),
                "region": province.get("region"),
                "scope_status": province.get("sra_scope_status"),
                "scope_as_of": province.get("sra_as_of"),
                "geography_coverage": detail_province.get("coverage") or {},
                "overall_score": score,
                "people": _display_number(ppp_values.get("members_total")),
                "households": _display_number(ppp_values.get("households_total")),
                "poor_people": _display_number(ppp_values.get("poor_members_total")),
                "poor_households": _display_number(ppp_values.get("poor_households_total")),
                "om_count": _display_number(om.get("om_count")),
                "chain_count": _display_number(om.get("chain_count")),
                "om_capital_baht": _display_number(om.get("capital_baht")),
                "assistance_households": _display_number(assistance.get("households")),
                "assistance_episodes": _display_number(assistance.get("episodes")),
                "assistance_budget_baht": _display_number(assistance.get("budget_baht")),
                "latest_assistance_year": assistance.get("year"),
                "assistance_dimensions_latest": assistance_dimensions,
                "area_developers": _display_number(project_values.get("area_developer")),
                "area_researchers": _display_number(project_values.get("area_researcher")),
                "support_organizations": _display_number(project_values.get("support_org")),
                "project_households": _display_number(project_values.get("project_households")),
                "project_poor_people": _display_number(project_values.get("poor_people")),
                "local_people": _display_number(project_values.get("local_people")),
                "freelance_workers": _display_number(project_values.get("freelance_worker")),
                "entrepreneurs": _display_number(project_values.get("entrepreneur")),
                "vvn_organizations": _display_number(project_values.get("vvn_org")),
                "apptech_institute": _display_number(project_values.get("apptech_institute")),
                "apptech_rmu": _display_number(project_values.get("apptech_rmu")),
                "innovations": _display_number(project_values.get("innovation")),
                "project_year": project_year,
                "project_households_target": _display_number(project_targets.get("project_households")),
                "project_poor_people_target": _display_number(project_targets.get("poor_people")),
                "project_metrics": [
                    {
                        "year": project_year or item.get("year"),
                        "metric_key": item.get("key") or item.get("metric_key"),
                        "metric_label": item.get("metric_label"),
                        "metric_group": item.get("group") or item.get("metric_group"),
                        "unit": item.get("unit"),
                        "value": item.get("value"),
                        "target_value": item.get("target_value"),
                        "target_pct": item.get("target_pct"),
                    }
                    for item in project_items
                    if item.get("key") or item.get("metric_key")
                ],
            }
        )

    def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        totals = empty_totals()
        totals["province_count"] = len(rows)
        score_values: list[float] = []
        assistance_years: list[int] = []
        project_years: list[int] = []
        assistance_dimensions: dict[str, dict[str, Any]] = {}
        for row in rows:
            for key in metric_keys:
                totals[key] += float(row.get(key) or 0)
            if row.get("overall_score") is not None:
                score_values.append(float(row["overall_score"]))
            if row.get("latest_assistance_year"):
                assistance_years.append(int(row["latest_assistance_year"]))
            if row.get("project_year"):
                project_years.append(int(row["project_year"]))
            for item in row.get("assistance_dimensions_latest", []):
                key = str(item.get("dimension_key") or "")
                if not key:
                    continue
                current = assistance_dimensions.setdefault(
                    key,
                    {
                        "year": item.get("year"),
                        "dimension_key": key,
                        "dimension_title": item.get("dimension_title"),
                        "households": 0,
                        "episodes": 0,
                        "budget_baht": 0,
                    },
                )
                for metric in ("households", "episodes", "budget_baht"):
                    current[metric] += float(item.get(metric) or 0)
        for key in metric_keys:
            totals[key] = _display_number(totals[key])
        totals["score_province_count"] = len(score_values)
        totals["overall_score_average"] = (
            round(sum(score_values) / len(score_values), 2) if score_values else None
        )
        totals["latest_assistance_year"] = str(max(assistance_years)) if assistance_years else None
        totals["project_years"] = [str(year) for year in sorted(set(project_years), reverse=True)]
        totals["latest_project_year"] = str(max(project_years)) if project_years else None
        totals["assistance_dimensions_latest"] = [
            {
                **item,
                "households": _display_number(item["households"]),
                "episodes": _display_number(item["episodes"]),
                "budget_baht": _display_number(item["budget_baht"]),
            }
            for item in assistance_dimensions.values()
        ]
        totals["project_households_target_pct"] = (
            round(totals["project_households"] / totals["project_households_target"] * 100, 1)
            if totals["project_households_target"]
            else None
        )
        totals["project_poor_people_target_pct"] = (
            round(totals["project_poor_people"] / totals["project_poor_people_target"] * 100, 1)
            if totals["project_poor_people_target"]
            else None
        )
        return totals

    region_rows = []
    for region_name in sorted({str(row["region"]) for row in province_rows}):
        rows = [row for row in province_rows if row["region"] == region_name]
        region_rows.append(
            {
                "region": region_name,
                "province_codes": [row["province_code"] for row in rows],
                "totals": aggregate(rows),
            }
        )

    insights = source_insights()
    ppp_source = (insights.get("sources") or {}).get("f1_pppconnext") or {}
    national_summary = ppp_source.get("national_summary") or {}
    member_registration = national_summary.get("member_registration") or {}
    assistance_all_years = ppp_source.get("assistance_summary") or {}

    return {
        "schema_version": "1.0",
        "generated_at": catalog.get("generated_at"),
        "publication_status": catalog.get("publication_status"),
        "scope": {
            "name_th": "ประเทศไทย",
            "province_codes": [row["province_code"] for row in province_rows],
        },
        "totals": aggregate(province_rows),
        "regions": region_rows,
        "provinces": province_rows,
        "national_profile": {
            "source_url": ppp_source.get("source_url"),
            "fetched_at": ppp_source.get("fetched_at"),
            "households_in_system_total": national_summary.get("households_in_system_total"),
            "members_in_system_total": national_summary.get("members_in_system_total"),
            "residing_total": member_registration.get("residing_total"),
            "named_present": member_registration.get("named_present"),
            "named_absent": member_registration.get("named_absent"),
            "unnamed_present": member_registration.get("unnamed_present"),
            "other": member_registration.get("other"),
            "unspecified": member_registration.get("unspecified"),
            "capital_dimensions": ppp_source.get("capital_dimensions") or [],
            "assistance_all_years": {
                "households": assistance_all_years.get("total_households"),
                "episodes": assistance_all_years.get("total_episodes"),
                "budget_baht": assistance_all_years.get("total_budget_baht"),
            },
        },
        "geography_coverage": details.get("coverage") or {},
        "province_groups": details.get("province_groups") or [],
        "quality": {
            "label_th": "ข้อมูลฝ่าย 1 รอบที่เผยแพร่ปัจจุบัน",
            "note_th": "ตัวเลขรวมจากข้อมูลรายจังหวัดที่ตรวจแล้ว",
            "om_note_th": "จำนวนโมเดลและห่วงโซ่เป็นยอดรวมตามจังหวัดและปี ไม่ใช่จำนวนชื่อที่ไม่ซ้ำ",
            "assistance_note_th": "ข้อมูลความช่วยเหลือใช้ปีล่าสุดที่มีในข้อมูลรายจังหวัด",
            "missing_th": ["ยังไม่มีข้อมูลแผนจังหวัด"],
        },
    }


@lru_cache(maxsize=77)
def provincial_briefing(province_code: str) -> dict[str, Any]:
    code = province_code.strip().zfill(2)
    try:
        with SessionLocal() as session:
            payload = artifact_payload(session, f"province/{code}/briefing")
        if payload is not None:
            return payload
    except SQLAlchemyError:
        pass
    path = (PUBLIC_DATA_ROOT / "provincial_briefings" / f"{code}.json").resolve()
    briefing_root = (PUBLIC_DATA_ROOT / "provincial_briefings").resolve()
    if path.parent != briefing_root or not path.exists():
        raise FileNotFoundError(code)
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=77)
def executive_summary(province_code: str) -> dict[str, Any]:
    code = province_code.strip().zfill(2)
    try:
        with SessionLocal() as session:
            payload = artifact_payload(session, f"province/{code}/summary")
        if payload is not None:
            return payload
    except SQLAlchemyError:
        pass
    path = (PUBLIC_DATA_ROOT / "executive_summaries" / f"{code}.json").resolve()
    summary_root = (PUBLIC_DATA_ROOT / "executive_summaries").resolve()
    if path.parent != summary_root or not path.exists():
        raise FileNotFoundError(code)
    return json.loads(path.read_text(encoding="utf-8"))
