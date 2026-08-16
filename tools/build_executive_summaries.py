from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRIEFING_ROOT = PROJECT_ROOT / "data/public/provincial_briefings"
OUTPUT_ROOT = PROJECT_ROOT / "data/public/executive_summaries"

METRIC_DEFINITIONS = {
    "house_price_income_ratio": {
        "label_th": "ราคาบ้านต่อรายได้",
        "dimension": "housing",
        "concern_direction": "high",
        "format": "decimal",
    },
    "housing_loan_pass_share": {
        "label_th": "การผ่านเกณฑ์สินเชื่อที่อยู่อาศัย",
        "dimension": "housing",
        "concern_direction": "low",
        "format": "percent",
    },
    "overcrowding_pct": {
        "label_th": "ที่อยู่อาศัยแออัด",
        "dimension": "housing",
        "concern_direction": "high",
        "format": "percent",
    },
    "flood_risk_area_level_4_5": {
        "label_th": "พื้นที่เสี่ยงน้ำท่วมระดับ 4–5",
        "dimension": "risk",
        "concern_direction": "high",
        "format": "percent",
    },
    "population_latest": {
        "label_th": "ประชากรในชุดข้อมูลล่าสุด",
        "dimension": "context",
        "concern_direction": None,
        "format": "integer",
    },
}

SRA_LABELS = {
    "human": "ทุนมนุษย์",
    "physical": "ทุนกายภาพ",
    "financial": "ทุนการเงิน",
    "natural_res": "ทรัพยากรธรรมชาติ",
    "social": "ทุนสังคม",
    "overall": "ภาพรวมตามต้นทาง",
}

DIMENSION_LABELS = {
    "housing": "ที่อยู่อาศัยและกำลังซื้อ",
    "risk": "ความเสี่ยงและความเปราะบาง",
    "livelihood": "ครัวเรือนและทุนดำรงชีพ",
    "development": "การดำเนินงานและผลผลิต",
    "urban": "บริการเมืองและคุณภาพชีวิต",
    "culture": "ทุนวัฒนธรรม",
}

SOURCE_JOIN_AUDIT = [
    {
        "source_id": "f1_sradss_ppaos",
        "join_status": "province_code_confirmed",
        "dimension": "risk",
        "serving_use": "province_aggregate_only",
    },
    {
        "source_id": "f1_pppconnext",
        "join_status": "province_name_confirmed_in_curated_bi",
        "dimension": "livelihood",
        "serving_use": "province_aggregate_only",
    },
    {
        "source_id": "f2_culturalmap_university",
        "join_status": "province_code_confirmed",
        "dimension": "culture",
        "serving_use": "province_summary_and_records",
    },
    {
        "source_id": "f2_rmutdb",
        "join_status": "no_confirmed_province_key",
        "dimension": None,
        "serving_use": "source_inventory_only",
    },
    {
        "source_id": "f2_apptech_mtr",
        "join_status": "source_api_province_code",
        "dimension": "development",
        "serving_use": "province_aggregate_only",
    },
    {
        "source_id": "f2_apptech_mru",
        "join_status": "province_name_crosswalk",
        "dimension": "development",
        "serving_use": "province_summary_and_records",
    },
    {
        "source_id": "f2_learning_area_based",
        "join_status": "province_name_crosswalk",
        "dimension": "development",
        "serving_use": "province_summary_and_records",
    },
    {
        "source_id": "f2_learning_dashboard",
        "join_status": "exact_province_name_against_official_boundary",
        "dimension": "development",
        "serving_use": "selected_project_scope_province_aggregate",
    },
    {
        "source_id": "f3_city_capital_open_data",
        "join_status": "official_dla_municipality_crosswalk",
        "dimension": "urban",
        "serving_use": "municipality_records_linked_to_province",
    },
    {
        "source_id": "f3_ruamthiao_lamphun",
        "join_status": "source_scope_lamphun",
        "dimension": "development",
        "serving_use": "lamphun_records_only",
    },
    {
        "source_id": "f3_housing_portal",
        "join_status": "province_code_and_name_crosswalk",
        "dimension": "housing_and_risk",
        "serving_use": "province_summary_and_records",
    },
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clean_text(value: Any) -> str | None:
    text = " ".join(str(value or "").strip().split())
    return text or None


def compact_text(value: Any, limit: int = 180) -> str | None:
    text = clean_text(value)
    if text is None or len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def format_value(value: float, style: str) -> str:
    if style == "percent":
        return f"{value:,.1f}%"
    if style == "integer":
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def load_briefings() -> dict[str, dict[str, Any]]:
    return {
        path.stem: read_json(path)
        for path in sorted(BRIEFING_ROOT.glob("*.json"))
        if path.name != "index.json"
    }


def signal_map(briefing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        signal["key"]: signal
        for signal in briefing.get("executive_signals", [])
        if signal.get("key")
    }


def build_benchmarks(
    briefings: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    values: dict[str, list[float]] = {key: [] for key in METRIC_DEFINITIONS}
    for briefing in briefings.values():
        for key, signal in signal_map(briefing).items():
            value = safe_float(signal.get("value"))
            if key in values and value is not None:
                values[key].append(value)

    benchmarks: dict[str, dict[str, Any]] = {}
    for key, metric_values in values.items():
        if not metric_values:
            continue
        metric_values.sort()
        benchmarks[key] = {
            "province_count": len(metric_values),
            "minimum": metric_values[0],
            "median": median(metric_values),
            "maximum": metric_values[-1],
        }
    return benchmarks


def metric_context(
    signal: dict[str, Any],
    benchmark: dict[str, Any],
) -> dict[str, Any]:
    key = signal["key"]
    definition = METRIC_DEFINITIONS[key]
    value = float(signal["value"])
    middle = float(benchmark["median"])
    spread = float(benchmark["maximum"]) - float(benchmark["minimum"])
    relative_gap = abs(value - middle) / abs(middle) if middle else abs(value - middle)
    if relative_gap <= 0.10:
        relation = "near"
        comparison_th = "ใกล้ค่ากลางของจังหวัดที่มีข้อมูล"
    elif value > middle:
        relation = "above"
        comparison_th = "สูงกว่าค่ากลางของจังหวัดที่มีข้อมูล"
    else:
        relation = "below"
        comparison_th = "ต่ำกว่าค่ากลางของจังหวัดที่มีข้อมูล"

    direction = definition["concern_direction"]
    needs_attention = (
        (direction == "high" and relation == "above")
        or (direction == "low" and relation == "below")
    )
    position = 50.0 if not spread else (value - benchmark["minimum"]) / spread * 100
    benchmark_position = (
        50.0
        if not spread
        else (middle - benchmark["minimum"]) / spread * 100
    )
    return {
        "key": key,
        "label_th": definition["label_th"],
        "value": value,
        "display_value": signal["display_value"],
        "unit": signal.get("unit"),
        "comparison": relation,
        "comparison_th": comparison_th,
        "benchmark_label_th": f"ค่ากลางจาก {benchmark['province_count']} จังหวัด",
        "benchmark_value": middle,
        "benchmark_display_value": format_value(middle, definition["format"]),
        "position_pct": round(max(0, min(100, position)), 1),
        "benchmark_position_pct": round(max(0, min(100, benchmark_position)), 1),
        "attention": needs_attention,
        "attention_strength": round(relative_gap, 4) if needs_attention else 0,
        "source_id": signal.get("source_id"),
        "source_url": signal.get("source_url"),
    }


def distribution(
    items: Iterable[dict[str, Any]],
    getter: Callable[[dict[str, Any]], Any],
    key: str,
    label_th: str,
    limit: int = 4,
) -> dict[str, Any] | None:
    counts = Counter(
        value
        for item in items
        if (value := clean_text(getter(item))) is not None
    )
    if not counts:
        return None
    total = sum(counts.values())
    return {
        "key": key,
        "kind": "distribution",
        "label_th": label_th,
        "items": [
            {
                "label_th": label,
                "value": count,
                "share_pct": round(count / total * 100, 1),
            }
            for label, count in counts.most_common(limit)
        ],
    }


def housing_group(briefing: dict[str, Any], resource_id: str) -> dict[str, Any] | None:
    groups = briefing.get("sections", {}).get("housing", {}).get("resource_groups", [])
    return next((group for group in groups if group.get("resource_id") == resource_id), None)


def population_trend(briefing: dict[str, Any]) -> dict[str, Any] | None:
    group = housing_group(briefing, "827aca76-9e90-43ed-86a2-cb9cb8651280")
    if not group:
        return None
    points = []
    for row in group.get("rows", []):
        values = row.get("values", {})
        year = safe_float(values.get("year"))
        value = safe_float(values.get("population"))
        if year is not None and value is not None:
            points.append({
                "label_th": str(int(year)),
                "value": value,
                "display_value": format_value(value, "integer"),
            })
    if len(points) < 2:
        return None
    points.sort(key=lambda item: item["label_th"])
    return {
        "key": "population_trend",
        "kind": "trend",
        "label_th": "แนวโน้มประชากรในชุดข้อมูล",
        "items": points[-6:],
        "source_url": group.get("source_url"),
    }


def build_housing_dimension(
    briefing: dict[str, Any],
    benchmarks: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    signals = signal_map(briefing)
    metrics = []
    for key in (
        "house_price_income_ratio",
        "housing_loan_pass_share",
        "overcrowding_pct",
    ):
        signal = signals.get(key)
        benchmark = benchmarks.get(key)
        if signal and benchmark:
            metrics.append(metric_context(signal, benchmark))
    trend = population_trend(briefing)
    if not metrics and not trend:
        return None
    attention = [metric["label_th"] for metric in metrics if metric["attention"]]
    if attention:
        summary = f"เมื่อเทียบกับค่ากลาง ประเด็นที่เด่นคือ {' และ '.join(attention[:2])}"
    else:
        summary = "ตัวชี้วัดที่มีอยู่ไม่ต่างจากค่ากลางอย่างเด่นชัด"
    return {
        "key": "housing",
        "label_th": DIMENSION_LABELS["housing"],
        "summary_th": summary,
        "metrics": metrics,
        "breakdowns": [trend] if trend else [],
        "highlights": [],
        "source_ids": ["f3_housing_portal"],
    }


def sra_scores(briefing: dict[str, Any]) -> dict[str, Any] | None:
    section = briefing.get("sections", {}).get("sra", {})
    items = []
    for item in section.get("items", []):
        key = item.get("metric_key")
        value = safe_float(item.get("value"))
        if key in SRA_LABELS and key != "overall" and value is not None:
            items.append({
                "key": key,
                "label_th": SRA_LABELS[key],
                "value": value,
                "display_value": format_value(value, "decimal"),
            })
    if not items:
        return None
    items.sort(key=lambda item: item["value"], reverse=True)
    return {
        "key": "sra_scores",
        "kind": "scores",
        "label_th": "ห้ามิติจาก SRA-DSS",
        "items": items,
        "note_th": "คะแนน provisional ตามนิยามต้นทาง",
        "source_url": next(
            (item.get("source_url") for item in section.get("items", []) if item.get("source_url")),
            None,
        ),
    }


def sra_program_breakdowns(briefing: dict[str, Any]) -> list[dict[str, Any]]:
    section = briefing.get("sections", {}).get("sra", {})
    breakdowns: list[dict[str, Any]] = []
    assistance = section.get("assistance_trend") or []
    if assistance:
        breakdowns.append({
            "key": "sra_assistance_households_trend",
            "kind": "trend",
            "evidence_stage": "activity",
            "label_th": "ครัวเรือนที่ได้รับความช่วยเหลือตาม SRA-DSS",
            "items": [
                {
                    "label_th": item.get("year") or "ไม่ระบุปี",
                    "value": item.get("households") or 0,
                    "display_value": f"{(item.get('households') or 0):,.0f} ครัวเรือน",
                }
                for item in assistance
            ],
            "note_th": "aggregate candidate ตามต้นทาง; ไม่ใช่จำนวนผู้รับประโยชน์ของโครงการ บพท. ทั้งหมด",
        })
    assistance_dimensions = section.get("assistance_dimensions_latest") or []
    if assistance_dimensions:
        total_budget = sum(
            safe_float(item.get("budget_baht")) or 0
            for item in assistance_dimensions
        )
        breakdowns.append({
            "key": "sra_assistance_budget_dimensions",
            "kind": "distribution",
            "evidence_stage": "input",
            "label_th": "งบช่วยเหลือรายมิติที่ SRA-DSS รายงาน ปี 2569",
            "items": [
                {
                    "label_th": item.get("dimension_title") or item.get("dimension_key") or "ไม่ระบุมิติ",
                    "value": safe_float(item.get("budget_baht")) or 0,
                    "share_pct": (
                        round((safe_float(item.get("budget_baht")) or 0) / total_budget * 100, 1)
                        if total_budget
                        else 0
                    ),
                    "display_value": f"{(safe_float(item.get('budget_baht')) or 0):,.0f} บาท",
                }
                for item in assistance_dimensions
            ],
            "note_th": "งบช่วยเหลือจาก SRA-DSS ไม่ใช่งบจัดสรรวิจัยรายจังหวัด",
        })
    project_metrics = section.get("project_metrics_latest") or []
    if project_metrics:
        breakdowns.append({
            "key": "sra_project_metrics_latest",
            "kind": "scores",
            "evidence_stage": "activity",
            "label_th": "ตัวชี้วัดโครงการตามต้นทาง SRA-DSS ปี 2569",
            "items": [
                {
                    "label_th": item.get("metric_label") or item.get("metric_key") or "ไม่ระบุตัวชี้วัด",
                    "value": safe_float(item.get("value")) or 0,
                    "display_value": " ".join(
                        value
                        for value in (
                            f"{(safe_float(item.get('value')) or 0):,.0f}",
                            clean_text(item.get("unit")),
                        )
                        if value
                    ),
                }
                for item in project_metrics
            ],
            "note_th": "คงชื่อ หน่วย และค่าแบบ provisional จากต้นทาง; ไม่รวมต่างหน่วยเป็นคะแนนเดียว",
        })
    return breakdowns


def build_risk_dimension(
    briefing: dict[str, Any],
    benchmarks: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    signals = signal_map(briefing)
    flood = signals.get("flood_risk_area_level_4_5")
    metrics = [metric_context(flood, benchmarks[flood["key"]])] if flood and flood["key"] in benchmarks else []
    scores = sra_scores(briefing)
    sra_program = sra_program_breakdowns(briefing)
    if not metrics and not scores and not sra_program:
        return None
    if metrics and metrics[0]["attention"]:
        summary = "พื้นที่เสี่ยงน้ำท่วมระดับ 4–5 สูงกว่าค่ากลางของจังหวัดที่มีข้อมูล"
    elif scores:
        summary = f"คะแนนตามต้นทางสูงสุดอยู่ที่มิติ{scores['items'][0]['label_th']}"
    elif sra_program:
        summary = "อยู่ในขอบเขตจังหวัดเป้าหมาย SRA-DSS แต่คะแนนปี 2569 ยังไม่มีค่า; แสดง aggregate การดำเนินงานแบบ candidate"
    else:
        summary = "ความเสี่ยงน้ำท่วมอยู่ใกล้หรือต่ำกว่าค่ากลางของจังหวัดที่มีข้อมูล"
    source_ids = []
    if metrics:
        source_ids.append("f3_housing_portal")
    if scores or sra_program:
        source_ids.append("f1_sradss_ppaos")
    return {
        "key": "risk",
        "label_th": DIMENSION_LABELS["risk"],
        "summary_th": summary,
        "metrics": metrics,
        "breakdowns": ([scores] if scores else []) + sra_program,
        "highlights": [],
        "source_ids": source_ids,
        "evidence_stage": "context_and_program_activity",
    }


def build_livelihood_dimension(briefing: dict[str, Any]) -> dict[str, Any] | None:
    records = briefing.get("sections", {}).get("pppconnext", {}).get("items", [])
    if not records:
        return None
    preferred = (
        "จำนวนครัวเรือน",
        "กลุ่มที่ 1 อยู่ลำบาก",
        "กลุ่มที่ 2 อยู่ยาก",
        "กลุ่มที่ 3 อยู่พอได้",
        "กลุ่มที่ 4 อยู่พอดี",
        "TPMAP (2565)",
        "PPPConnext (2564-2565)",
    )
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for label in preferred:
        record = next(
            (
                item
                for item in records
                if item.get("metric_name") == label and item.get("metric_name") not in used
            ),
            None,
        )
        value = safe_float((record or {}).get("value"))
        if record and value is not None:
            used.add(label)
            selected.append({
                "kind": "source_fact",
                "title_th": label,
                "detail_th": f"{value:,.0f} · หน่วยตามต้นทางยังต้องทบทวน",
                "source_url": record.get("source_url"),
            })
    return {
        "key": "livelihood",
        "label_th": DIMENSION_LABELS["livelihood"],
        "summary_th": "มีค่ารวมระดับจังหวัดจากกราฟ PPPConnext โดยคงแต่ละตัวชี้วัดแยกกัน",
        "metrics": [],
        "breakdowns": [],
        "highlights": selected[:4],
        "source_ids": ["f1_pppconnext"],
        "context_th": "ไม่รวมค่าต่างหน่วยเป็นคะแนนเดียว",
    }


def build_development_dimension(briefing: dict[str, Any]) -> dict[str, Any] | None:
    sections = briefing.get("sections", {})
    projects = sections.get("project_master", {}).get("items", [])
    learning = sections.get("learning_dashboard", {}).get("items", [])
    innovations = sections.get("innovation", {}).get("items", [])
    requirements = sections.get("requirements", {}).get("items", [])
    tourism = sections.get("tourism", {}).get("items", [])
    apptech = sections.get("apptech_mtr", {}).get("items", [])
    if not projects and not learning and not innovations and not requirements and not tourism and not apptech:
        return None

    project_district_rows = [
        {"district": area.get("district")}
        for project in projects
        for area in project.get("geography") or []
    ]
    project_districts = distribution(
        project_district_rows,
        lambda item: item.get("district"),
        "project_districts",
        "พื้นที่ดำเนินโครงการ (หนึ่งโครงการอาจอยู่หลายอำเภอ)",
    )
    if project_districts:
        project_districts["evidence_stage"] = "activity"
    project_years = distribution(
        projects, lambda item: item.get("fiscal_year"), "project_years", "ปีงบประมาณของโครงการ"
    )
    if project_years:
        project_years["evidence_stage"] = "activity"
    innovation_categories = distribution(
        innovations, lambda item: item.get("category"), "innovation_categories", "หมวดนวัตกรรม"
    )
    if innovation_categories:
        innovation_categories["evidence_stage"] = "output"
    requirement_categories = distribution(
        requirements,
        lambda item: item.get("category"),
        "requirement_categories",
        "หมวดโจทย์หรือความต้องการ",
    )
    if requirement_categories:
        requirement_categories["evidence_stage"] = "need"
    breakdowns = [
        item
        for item in (
            project_districts,
            project_years,
            innovation_categories,
            requirement_categories,
        )
        if item
    ]
    if learning:
        aggregate = learning[0]
        breakdowns.append({
            "key": "learning_dashboard_business_records",
            "kind": "scores",
            "label_th": aggregate.get("metric_label_th") or "Dashboard LE",
            "items": [{
                "label_th": "ค่าจังหวัดตามต้นทาง",
                "value": aggregate.get("value", 0),
                "display_value": f"{aggregate.get('value', 0):,.0f}",
            }],
            "note_th": aggregate.get("scope_warning_th"),
            "evidence_stage": "activity",
        })
    if apptech:
        activity = apptech[0]
        breakdowns.append({
            "key": "apptech_activity",
            "kind": "scores",
            "label_th": "กิจกรรม AppTech ที่ API ผูกกับจังหวัด",
            "items": [
                {
                    "label_th": "ผู้ใช้ที่ลงทะเบียน",
                    "value": activity.get("registered_users", 0),
                    "display_value": f"{activity.get('registered_users', 0):,.0f}",
                },
                {
                    "label_th": "การปฏิสัมพันธ์",
                    "value": activity.get("interactions", 0),
                    "display_value": f"{activity.get('interactions', 0):,.0f}",
                },
            ],
            "note_th": "เป็นคนละ grain กับจำนวนผลงานนวัตกรรม",
            "evidence_stage": "activity",
        })

    districts = [item["label_th"] for item in (project_districts or {}).get("items", [])[:2]]
    categories = [item["label_th"] for item in (innovation_categories or {}).get("items", [])[:2]]
    if districts and categories:
        summary = f"โครงการกระจุกใน{' และ '.join(districts)} ส่วนนวัตกรรมเด่นในหมวด{' และ '.join(categories)}"
    elif districts:
        summary = f"โครงการที่เชื่อมได้กระจุกใน{' และ '.join(districts)}"
    elif categories:
        summary = f"นวัตกรรมที่เชื่อมได้เด่นในหมวด{' และ '.join(categories)}"
    elif requirements:
        summary = "มีโจทย์หรือความต้องการสาธารณะที่ต้นทางผูกกับจังหวัด"
    elif learning:
        summary = "มี aggregate ผู้เข้าร่วมโครงการจาก Learning Dashboard; หน่วยและ as-of ยังไม่ยืนยัน"
    elif apptech:
        summary = "มีข้อมูลกิจกรรมแพลตฟอร์ม AppTech ระดับจังหวัด; ไม่ใช่หลักฐานจำนวนโครงการหรือนวัตกรรม"
    elif tourism:
        summary = "มีข้อมูลบริการและเนื้อหาท่องเที่ยวสาธารณะที่ผูกกับจังหวัด"
    else:
        summary = "ยังไม่มีหลักฐานโครงการหรือนวัตกรรมที่ผูกกับจังหวัดในทะเบียนที่ใช้"

    highlights = []
    sorted_projects = sorted(
        projects,
        key=lambda item: str(item.get("fiscal_year") or ""),
        reverse=True,
    )
    for item in sorted_projects[:2]:
        area_names = [
            area.get("district")
            for area in item.get("geography") or []
            if area.get("district")
        ]
        highlights.append({
            "kind": "project",
            "title_th": item.get("project_name") or "ไม่ระบุชื่อโครงการ",
            "detail_th": " · ".join(
                value
                for value in (
                    " / ".join(area_names[:2]) or None,
                    clean_text(item.get("research_unit")),
                )
                if value
            ),
            "source_url": item.get("source_url"),
        })
    for item in innovations[:2]:
        highlights.append({
            "kind": "innovation",
            "title_th": item.get("title") or "ไม่ระบุชื่อนวัตกรรม",
            "detail_th": " · ".join(
                value
                for value in (clean_text(item.get("category")), f"TRL {item['trl_level']}" if item.get("trl_level") is not None else None)
                if value
            ),
            "source_url": item.get("source_url"),
        })
    for item in requirements[:2]:
        highlights.append({
            "kind": "requirement",
            "title_th": item.get("title") or "ไม่ระบุชื่อโจทย์หรือความต้องการ",
            "detail_th": compact_text(item.get("description")) or clean_text(item.get("category")),
            "source_url": item.get("source_url"),
        })
    source_ids = []
    if projects:
        source_ids.append("f2_learning_area_based")
    if learning:
        source_ids.append("f2_learning_dashboard")
    if innovations or requirements:
        source_ids.append("f2_apptech_mru")
    if tourism:
        source_ids.append("f3_ruamthiao_lamphun")
    if apptech:
        source_ids.append("f2_apptech_mtr")
    return {
        "key": "development",
        "label_th": DIMENSION_LABELS["development"],
        "summary_th": summary,
        "metrics": [],
        "breakdowns": breakdowns,
        "highlights": highlights,
        "source_ids": source_ids,
        "evidence_stage": "activity_and_output",
    }


def build_urban_dimension(briefing: dict[str, Any]) -> dict[str, Any] | None:
    cities = briefing.get("sections", {}).get("city_capital", {}).get("items", [])
    if not cities:
        return None
    signals = sorted(
        (
            {**signal, "city_name_th": city.get("city_name_th")}
            for city in cities
            for signal in city.get("signals", [])
        ),
        key=lambda item: item.get("attention_strength", 0),
        reverse=True,
    )
    city_names = " และ ".join(city.get("city_name_th") or "ไม่ระบุเมือง" for city in cities)
    if signals:
        lead = signals[0]
        summary = f"{lead['city_name_th']}: {lead['label_th']} {lead['comparison_th']}"
    else:
        summary = f"มีข้อมูลทุนเมืองระดับเทศบาลของ {city_names}"
    highlights = [
        {
            "kind": "city",
            "title_th": city.get("city_name_th") or "ไม่ระบุเมือง",
            "detail_th": f"อำเภอ{city.get('district_name_th') or 'ไม่ระบุ'} · ตัวชี้วัด 39 รายการ",
            "source_url": "https://evaluatethecity.netlify.app/",
        }
        for city in cities
    ]
    return {
        "key": "urban",
        "label_th": DIMENSION_LABELS["urban"],
        "summary_th": summary,
        "metrics": signals[:3],
        "breakdowns": [],
        "highlights": highlights,
        "source_ids": ["f3_city_capital_open_data"],
        "context_th": "เปรียบเทียบกับค่ากลางของ 18 เมืองใน snapshot เดียวกัน",
    }


def build_culture_dimension(briefing: dict[str, Any]) -> dict[str, Any] | None:
    records = briefing.get("sections", {}).get("culture", {}).get("items", [])
    if not records:
        return None
    categories = distribution(records, lambda item: item.get("category"), "culture_categories", "หมวดทุนวัฒนธรรม")
    districts = distribution(records, lambda item: item.get("amphoe"), "culture_districts", "พื้นที่ที่มีการบันทึก")
    cultural_types = distribution(records, lambda item: item.get("cultural_type"), "culture_types", "ลักษณะทุนวัฒนธรรม", 3)
    risk_records = [item for item in records if clean_text(item.get("risk_reason"))]
    top_categories = [item["label_th"] for item in (categories or {}).get("items", [])[:2]]
    top_districts = [item["label_th"] for item in (districts or {}).get("items", [])[:2]]
    if risk_records:
        summary = f"ต้นทางระบุเหตุผลความเสี่ยงในบางรายการ เช่น {risk_records[0].get('title_th') or 'รายการทุนวัฒนธรรม'}"
    elif top_categories:
        summary = f"ข้อมูลที่บันทึกมากอยู่ในหมวด{' และ '.join(top_categories)}"
    else:
        summary = "มีทะเบียนทุนวัฒนธรรมที่เชื่อมกับจังหวัด"
    highlights = [
        {
            "kind": "culture_risk",
            "title_th": item.get("title_th") or "ไม่ระบุชื่อ",
            "detail_th": clean_text(item.get("risk_reason")),
            "meta_th": clean_text(item.get("amphoe")),
            "source_url": item.get("source_url"),
        }
        for item in risk_records[:3]
    ]
    if not highlights:
        highlights = [
            {
                "kind": "culture",
                "title_th": item.get("title_th") or "ไม่ระบุชื่อ",
                "detail_th": clean_text(item.get("category")),
                "meta_th": clean_text(item.get("amphoe")),
                "source_url": item.get("source_url"),
            }
            for item in records[:2]
        ]
    return {
        "key": "culture",
        "label_th": DIMENSION_LABELS["culture"],
        "summary_th": summary,
        "metrics": [],
        "breakdowns": [item for item in (categories, districts, cultural_types) if item],
        "highlights": highlights,
        "source_ids": ["f2_culturalmap_university"],
        "context_th": " · ".join(top_districts) if top_districts else None,
    }


PMUA_FUNDER_KEYWORD = "บพท."


def count_breakdown(
    items: Iterable[dict[str, Any]],
    getter: Callable[[dict[str, Any]], Any],
    limit: int,
) -> list[dict[str, Any]]:
    counts = Counter(
        value
        for item in items
        if (value := clean_text(getter(item))) is not None
    )
    total = sum(counts.values())
    return [
        {
            "label_th": label,
            "value": count,
            "share_pct": round(count / total * 100, 1) if total else 0,
        }
        for label, count in counts.most_common(limit)
    ]


def build_research_portfolio(briefing: dict[str, Any]) -> dict[str, Any]:
    """Build a decision-safe portfolio without treating participant rows as projects."""

    sections = briefing.get("sections", {})
    project_section = sections.get("project_master", {})
    participant_section = sections.get("area_based", {})
    innovation_section = sections.get("innovation", {})
    projects = project_section.get("items", [])
    participant_records = participant_section.get("items", [])
    innovations = innovation_section.get("items", [])

    year_counts = Counter(
        clean_text(item.get("fiscal_year")) or "ไม่ระบุปี" for item in projects
    )
    fiscal_years = [
        {"label_th": year, "value": count}
        for year, count in sorted(year_counts.items())
    ]
    universities = count_breakdown(
        projects, lambda item: item.get("research_unit"), limit=8
    )
    university_count = len({
        value
        for item in projects
        if (value := clean_text(item.get("research_unit"))) is not None
    })

    district_project_ids: dict[str, set[str]] = defaultdict(set)
    subdistrict_project_ids: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for project in projects:
        project_id = str(project.get("project_group_id") or "")
        for area in project.get("geography") or []:
            district = clean_text(area.get("district"))
            if district is None:
                continue
            district_project_ids[district].add(project_id)
            subdistricts = area.get("subdistricts") or ["ไม่ระบุตำบล"]
            for subdistrict in subdistricts:
                subdistrict_project_ids[district][subdistrict].add(project_id)
    districts = [
        {
            "label_th": district,
            "value": len(project_ids),
            "subdistricts": [
                {"label_th": name, "value": len(ids)}
                for name, ids in sorted(
                    subdistrict_project_ids[district].items(),
                    key=lambda entry: len(entry[1]),
                    reverse=True,
                )[:6]
            ],
        }
        for district, project_ids in district_project_ids.items()
    ]
    districts.sort(key=lambda item: item["value"], reverse=True)
    districts = districts[:12]

    seen_businesses: set[str] = set()
    businesses: list[dict[str, Any]] = []
    for item in sorted(
        participant_records,
        key=lambda entry: str(entry.get("fiscal_year") or ""),
        reverse=True,
    ):
        name = clean_text(item.get("business_name"))
        if name is None or name in seen_businesses:
            continue
        seen_businesses.add(name)
        if len(businesses) < 12:
            businesses.append({
                "name_th": name,
                "project_th": compact_text(item.get("project_name"), 120),
                "district_th": clean_text(item.get("district")),
                "fiscal_year": clean_text(item.get("fiscal_year")),
            })

    pmua_funded_innovation_ids: set[str] = set()
    pmua_funding_entry_count = 0
    pmua_amount_baht = 0.0
    pmua_amount_known = 0
    for item in innovations:
        record_id = str(item.get("record_id") or "")
        for entry in item.get("funding") or []:
            funder = clean_text(entry.get("funder")) or ""
            if PMUA_FUNDER_KEYWORD not in funder:
                continue
            pmua_funded_innovation_ids.add(record_id)
            pmua_funding_entry_count += 1
            amount = safe_float(entry.get("amount_baht"))
            if amount is not None:
                pmua_amount_baht += amount
                pmua_amount_known += 1

    innovation_values = [
        value
        for item in innovations
        if (value := safe_float(item.get("innovation_value_baht"))) is not None
    ]
    trl_distribution = count_breakdown(
        innovations,
        lambda item: (
            f"TRL {int(level)}"
            if (level := safe_float(item.get("trl_level"))) is not None
            else None
        ),
        limit=9,
    )
    target_groups = count_breakdown(
        innovations,
        lambda item: (item.get("target_groups") or [None])[0],
        limit=5,
    )
    latest_update = max(
        (
            clean_text(item.get("latest_source_update"))
            for item in projects
            if clean_text(item.get("latest_source_update"))
        ),
        default=None,
    )
    research_leads = {
        name
        for item in innovations
        for researcher in item.get("research_leads") or []
        if (name := clean_text(researcher.get("name"))) is not None
    }
    roi_known = sum(
        1
        for item in innovations
        if clean_text(item.get("roi_indicator")) or clean_text(item.get("roi_unit"))
    )
    sroi_known = sum(
        1
        for item in innovations
        if clean_text(item.get("sroi_indicator")) or clean_text(item.get("sroi_unit"))
    )
    ip_known = sum(
        1
        for item in innovations
        if any(clean_text(value) for value in (item.get("ip") or {}).values())
    )
    multi_province_innovations = sum(
        1 for item in innovations if (safe_float(item.get("linked_province_count")) or 0) > 1
    )

    return {
        "title_th": "โครงการ งบที่เชื่อมโยง และผลลัพธ์ที่มีหลักฐาน",
        "scope_note_th": (
            "จำนวนโครงการเป็นการจัดกลุ่มเบื้องต้นจากชื่อโครงการ+ปีงบประมาณ+หน่วยวิจัย "
            "ส่วนจำนวนผู้เข้าร่วมคง grain แยกกัน; ทุกค่าเป็น candidate"
        ),
        "project_count": len(projects),
        "project_count_status": (
            "provisional_grouping" if projects else "not_found_in_area_based_registry"
        ),
        "project_grouping_method": "project_name_fiscal_year_research_unit",
        "participant_record_count": len(participant_records),
        "participant_record_status": (
            "available" if participant_records else "not_found_in_area_based_registry"
        ),
        "university_count": university_count,
        "district_count": len(district_project_ids),
        "business_count": len(seen_businesses),
        "innovation_count": len(innovations),
        "innovation_count_status": (
            "available" if innovations else "not_found_in_apptech_registry"
        ),
        "fiscal_years": fiscal_years,
        "universities": universities,
        "districts": districts,
        "funding": {
            "label_th": "ทุนของนวัตกรรมที่เชื่อมกับจังหวัด (ไม่ใช่งบจัดสรรจังหวัด)",
            "pmua_funded_count": len(pmua_funded_innovation_ids),
            "pmua_funded_innovation_count": len(pmua_funded_innovation_ids),
            "pmua_funding_entry_count": pmua_funding_entry_count,
            "pmua_amount_baht": round(pmua_amount_baht, 2),
            "pmua_amount_known_entries": pmua_amount_known,
            "innovation_value_baht_total": round(sum(innovation_values), 2),
            "innovation_value_known_entries": len(innovation_values),
            "allocation_status": "linked_innovation_funding_not_provincial_allocation",
            "multi_province_innovation_count": multi_province_innovations,
            "cross_province_sum_warning": multi_province_innovations > 0,
            "note_th": (
                "แสดงยอดเต็มที่ต้นทางกรอกกับนวัตกรรมซึ่งอาจเชื่อมหลายจังหวัด "
                "ห้ามรวมข้ามจังหวัดหรือใช้แทนงบจัดสรร/เบิกจ่ายของจังหวัด"
            ),
        },
        "trl_distribution": trl_distribution,
        "outcome_coverage": {
            "research_lead_names": len(research_leads),
            "ip_records": ip_known,
            "roi_records": roi_known,
            "sroi_records": sroi_known,
            "note_th": "ROI/SROI เป็น field ที่ต้นทางกรอกและมีความครบต่ำ; ไม่ใช้เป็น KPI รวม",
        },
        "latest_update": latest_update,
        "data_gaps_th": [
            "ยังไม่มี Project ID ทางการสำหรับเชื่อม Area-Based กับระบบโครงการหลัก",
            "ชื่อหัวหน้าโครงการของ Area-Based ยังไม่มี; ชื่อนักวิจัยที่มีอยู่เป็นของทะเบียนนวัตกรรม",
            "สถานะดำเนินงานรายโครงการ (อยู่ระหว่าง/เสร็จสิ้น) ต้นทางไม่ระบุ",
            "งบประมาณจัดสรรและสถานะเบิกจ่ายรายกรอบ/รายฝ่าย ต้องใช้ระบบภายในของ บพท.",
        ],
        "source_ids": [
            source_id
            for source_id, present in (
                ("f2_learning_area_based", bool(participant_records)),
                ("f2_apptech_mru", bool(innovations)),
            )
            if present
        ],
    }


def compact_source_coverage(briefing: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep the summary fast; the briefing endpoint carries field-level details."""

    keys = (
        "source_id",
        "name_th",
        "url",
        "acquisition_mode",
        "readiness_status",
        "status",
        "records",
        "note_th",
        "quality_label_th",
        "data_grain_th",
        "observed_as_of",
        "observed_fetched_at",
    )
    return [
        {key: source.get(key) for key in keys}
        for source in briefing.get("source_coverage", [])
    ]


def build_decision_chain(
    briefing: dict[str, Any], portfolio: dict[str, Any]
) -> list[dict[str, Any]]:
    sections = briefing.get("sections", {})
    ppp_records = sections.get("pppconnext", {}).get("items", [])
    poverty_households = next(
        (
            safe_float(item.get("value"))
            for item in ppp_records
            if item.get("metric_name") == "จำนวนครัวเรือน"
            and safe_float(item.get("value")) is not None
        ),
        None,
    )
    sra = sections.get("sra", {})
    latest_assistance = max(
        sra.get("assistance_trend") or [],
        key=lambda item: str(item.get("year") or ""),
        default=None,
    )
    funding = portfolio.get("funding") or {}
    outcomes = portfolio.get("outcome_coverage") or {}
    apptech_items = sections.get("apptech_mtr", {}).get("items", [])
    apptech = apptech_items[0] if apptech_items else {}

    need_metrics = []
    if poverty_households is not None:
        need_metrics.append({
            "label_th": "ครัวเรือนที่สำรวจใน PPPConnext",
            "value": poverty_households,
            "display_value": f"{poverty_households:,.0f} ครัวเรือน",
        })
    if sra.get("scope_status") == "in_scope":
        need_metrics.append({
            "label_th": "ขอบเขตจังหวัดเป้าหมาย SRA-DSS",
            "value": None,
            "display_value": (
                "มีคะแนนปี 2569"
                if sra.get("score_status") == "in_scope_value_available"
                else "อยู่ในขอบเขต แต่คะแนนปี 2569 ไม่มีค่า"
            ),
        })

    input_metrics = []
    if funding.get("pmua_amount_known_entries"):
        input_metrics.append({
            "label_th": "ทุนที่ระบุในนวัตกรรมที่เชื่อมจังหวัด",
            "value": funding.get("pmua_amount_baht"),
            "display_value": f"{funding.get('pmua_amount_baht', 0):,.0f} บาท",
        })
    if latest_assistance and safe_float(latest_assistance.get("budget_baht")) is not None:
        input_metrics.append({
            "label_th": f"งบช่วยเหลือ SRA-DSS ปี {latest_assistance.get('year')}",
            "value": latest_assistance.get("budget_baht"),
            "display_value": f"{latest_assistance.get('budget_baht', 0):,.0f} บาท",
        })

    activity_metrics = []
    if portfolio.get("project_count_status") == "provisional_grouping":
        activity_metrics.extend([
            {
                "label_th": "กลุ่มโครงการที่เชื่อมได้",
                "value": portfolio.get("project_count"),
                "display_value": f"{portfolio.get('project_count', 0):,.0f} กลุ่มโครงการ",
            },
            {
                "label_th": "หน่วย/ผู้ประกอบการเข้าร่วม",
                "value": portfolio.get("participant_record_count"),
                "display_value": f"{portfolio.get('participant_record_count', 0):,.0f} records",
            },
        ])
    elif apptech:
        activity_metrics.append({
            "label_th": "กิจกรรมแพลตฟอร์ม AppTech",
            "value": apptech.get("interactions"),
            "display_value": f"{(apptech.get('interactions') or 0):,.0f} interactions",
        })

    output_metrics = []
    if portfolio.get("innovation_count_status") == "available":
        output_metrics.extend([
            {
                "label_th": "นวัตกรรมที่เชื่อมจังหวัด",
                "value": portfolio.get("innovation_count"),
                "display_value": f"{portfolio.get('innovation_count', 0):,.0f} รายการ",
            },
            {
                "label_th": "ระเบียนที่มีข้อมูลทรัพย์สินทางปัญญา",
                "value": outcomes.get("ip_records"),
                "display_value": f"{outcomes.get('ip_records', 0):,.0f} รายการ",
            },
        ])

    outcome_records = (outcomes.get("roi_records") or 0) + (outcomes.get("sroi_records") or 0)
    outcome_metrics = (
        [
            {
                "label_th": "ระเบียนที่กรอก ROI/SROI",
                "value": outcome_records,
                "display_value": f"{outcome_records:,.0f} ช่องข้อมูล",
            }
        ]
        if outcome_records
        else []
    )

    return [
        {
            "key": "need",
            "label_th": "สถานการณ์/ความต้องการ",
            "evidence_stage": "context",
            "status": "available" if need_metrics else "not_available",
            "metrics": need_metrics,
            "note_th": "บริบทพื้นที่ ไม่ใช่ผลลัพธ์ของโครงการ",
        },
        {
            "key": "input",
            "label_th": "ทรัพยากร/งบที่เชื่อมได้",
            "evidence_stage": "input",
            "status": "limited" if input_metrics else "not_available",
            "metrics": input_metrics,
            "note_th": "ยังไม่มีงบจัดสรรและสถานะเบิกจ่ายทางการรายจังหวัด",
        },
        {
            "key": "activity",
            "label_th": "การดำเนินงาน",
            "evidence_stage": "activity",
            "status": "available" if activity_metrics else "not_available",
            "metrics": activity_metrics,
            "note_th": "กลุ่มโครงการเป็น provisional grouping; participant records แสดงแยก",
        },
        {
            "key": "output",
            "label_th": "ผลผลิต",
            "evidence_stage": "output",
            "status": "available" if output_metrics else "not_available",
            "metrics": output_metrics,
            "note_th": "ทะเบียนนวัตกรรมไม่เท่ากับผลผลิตที่รับรองของทุกโครงการ",
        },
        {
            "key": "outcome",
            "label_th": "ผลลัพธ์/ผลกระทบ",
            "evidence_stage": "outcome_impact",
            "status": "limited" if outcome_metrics else "not_available",
            "metrics": outcome_metrics,
            "note_th": "ROI/SROI มีความครบต่ำและยังไม่ใช้เป็น KPI รวม",
        },
    ]


def build_data_quality_overview(briefing: dict[str, Any]) -> dict[str, Any]:
    sources = briefing.get("source_coverage", [])
    accepted = sum(
        1
        for source in sources
        if str(source.get("readiness_status") or "").lower() == "accepted"
    )
    with_as_of = sum(1 for source in sources if source.get("observed_as_of"))
    fetched_values = [
        str(source["observed_fetched_at"])
        for source in sources
        if source.get("observed_fetched_at")
    ]
    return {
        "status": "candidate_needs_review" if accepted < len(sources) else "accepted",
        "public_source_count": len(sources),
        "accepted_source_count": accepted,
        "candidate_or_review_source_count": len(sources) - accepted,
        "sources_with_explicit_as_of": with_as_of,
        "sources_without_explicit_as_of": len(sources) - with_as_of,
        "latest_observed_fetch": max(fetched_values, default=None),
        "rules_th": [
            "ค่าว่างและไม่พบในทะเบียนไม่แสดงเป็นศูนย์",
            "จำนวนโครงการแยกจาก participant records",
            "งบที่ผูกกับนวัตกรรมไม่ตีความเป็นงบจัดสรรจังหวัด",
            "ไม่มี source ที่ accepted จะไม่เรียกค่าบนหน้านี้ว่า KPI รับรอง",
        ],
    }


def coverage_label(available_count: int) -> str:
    if available_count >= 4:
        return "ข้อมูลค่อนข้างครบ"
    if available_count == 3:
        return "ข้อมูลปานกลาง"
    if available_count == 2:
        return "ข้อมูลบางส่วน"
    return "ข้อมูลยังบาง"


def build_observations(dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attention_metrics = sorted(
        (
            metric
            for dimension in dimensions
            for metric in dimension.get("metrics", [])
            if metric.get("attention")
        ),
        key=lambda metric: metric.get("attention_strength", 0),
        reverse=True,
    )
    observations = [
        {
            "kind": "comparison",
            "label_th": metric["label_th"],
            "text_th": metric["comparison_th"],
            "source_url": metric.get("source_url"),
        }
        for metric in attention_metrics[:3]
    ]
    if not observations:
        observations = [
            {
                "kind": "coverage",
                "label_th": dimension["label_th"],
                "text_th": dimension["summary_th"],
                "source_url": None,
            }
            for dimension in dimensions[:2]
        ]
    return observations[:3]


def build_summary(
    briefing: dict[str, Any],
    benchmarks: dict[str, dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    dimensions = [
        dimension
        for dimension in (
            build_housing_dimension(briefing, benchmarks),
            build_risk_dimension(briefing, benchmarks),
            build_livelihood_dimension(briefing),
            build_development_dimension(briefing),
            build_urban_dimension(briefing),
            build_culture_dimension(briefing),
        )
        if dimension
    ]
    available_source_ids = briefing.get("available_source_ids", [])
    signals = signal_map(briefing)
    context_metrics = []
    population = signals.get("population_latest")
    if population:
        context_metrics.append({
            "key": "population_latest",
            "label_th": METRIC_DEFINITIONS["population_latest"]["label_th"],
            "display_value": population.get("display_value"),
            "unit": population.get("unit"),
            "source_url": population.get("source_url"),
        })
    attention_metrics = [
        metric
        for dimension in dimensions
        for metric in dimension.get("metrics", [])
        if metric.get("attention")
    ]
    context_metrics.extend(
        {
            "key": metric["key"],
            "label_th": metric["label_th"],
            "display_value": metric["display_value"],
            "unit": metric.get("unit"),
            "source_url": metric.get("source_url"),
        }
        for metric in attention_metrics[:2]
    )
    present_keys = {dimension["key"] for dimension in dimensions}
    research_portfolio = build_research_portfolio(briefing)
    return {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "publication_status": briefing.get("publication_status"),
        "province": briefing["province"],
        "readout": {
            "title_th": "ภาพที่เห็นจากข้อมูล",
            "observations": build_observations(dimensions),
            "context_metrics": context_metrics[:3],
        },
        "research_portfolio": research_portfolio,
        "decision_chain": build_decision_chain(briefing, research_portfolio),
        "data_quality_overview": build_data_quality_overview(briefing),
        "dimensions": dimensions,
        "missing_dimensions": [
            {"key": key, "label_th": label}
            for key, label in DIMENSION_LABELS.items()
            if key not in present_keys
        ],
        "coverage": {
            "label_th": coverage_label(len(available_source_ids)),
            "available_source_count": len(available_source_ids),
            "public_source_count": len(briefing.get("source_coverage", [])),
            "available_source_ids": available_source_ids,
        },
        "source_coverage": compact_source_coverage(briefing),
        "quality": briefing.get("quality", {}),
        "methodology": {
            "join_level": "province",
            "comparison_basis_th": "ค่ากลางของจังหวัดที่มีข้อมูลในตัวชี้วัดเดียวกัน",
            "near_median_rule": "absolute_relative_difference_lte_10_percent",
            "policy_score_created": False,
            "raw_rows_included": False,
            "unknown_value_policy": "null_and_not_found_are_never_rendered_as_zero",
            "project_count_method": "provisional_project_name_fiscal_year_research_unit_grouping",
            "funding_attribution": "linked_innovation_funding_not_provincial_allocation",
        },
    }


def build() -> None:
    briefings = load_briefings()
    if len(briefings) != 77:
        raise RuntimeError(f"expected 77 provincial briefings, found {len(briefings)}")
    benchmarks = build_benchmarks(briefings)
    generated_at = datetime.now(timezone.utc).isoformat()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    written = []
    for code, briefing in briefings.items():
        path = OUTPUT_ROOT / f"{code}.json"
        write_json(path, build_summary(briefing, benchmarks, generated_at))
        written.append(path)

    index = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "province_count": len(written),
        "comparison_method": "median_of_provinces_with_same_metric",
        "benchmarks": benchmarks,
        "source_join_audit": SOURCE_JOIN_AUDIT,
        "inputs": [
            {
                "path": path.relative_to(PROJECT_ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sorted(BRIEFING_ROOT.glob("*.json"))
        ],
        "files": [
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sorted(written)
        ],
    }
    write_json(OUTPUT_ROOT / "index.json", index)
    print(json.dumps({
        "status": "ok",
        "provinces": len(written),
        "benchmarked_metrics": len(benchmarks),
        "output": OUTPUT_ROOT.relative_to(PROJECT_ROOT).as_posix(),
    }, ensure_ascii=False))


if __name__ == "__main__":
    build()
