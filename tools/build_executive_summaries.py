from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
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
    "development": "โครงการและนวัตกรรม",
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


def build_risk_dimension(
    briefing: dict[str, Any],
    benchmarks: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    signals = signal_map(briefing)
    flood = signals.get("flood_risk_area_level_4_5")
    metrics = [metric_context(flood, benchmarks[flood["key"]])] if flood and flood["key"] in benchmarks else []
    scores = sra_scores(briefing)
    if not metrics and not scores:
        return None
    if metrics and metrics[0]["attention"]:
        summary = "พื้นที่เสี่ยงน้ำท่วมระดับ 4–5 สูงกว่าค่ากลางของจังหวัดที่มีข้อมูล"
    elif scores:
        summary = f"คะแนนตามต้นทางสูงสุดอยู่ที่มิติ{scores['items'][0]['label_th']}"
    else:
        summary = "ความเสี่ยงน้ำท่วมอยู่ใกล้หรือต่ำกว่าค่ากลางของจังหวัดที่มีข้อมูล"
    source_ids = []
    if metrics:
        source_ids.append("f3_housing_portal")
    if scores:
        source_ids.append("f1_sradss_ppaos")
    return {
        "key": "risk",
        "label_th": DIMENSION_LABELS["risk"],
        "summary_th": summary,
        "metrics": metrics,
        "breakdowns": [scores] if scores else [],
        "highlights": [],
        "source_ids": source_ids,
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
    projects = sections.get("area_based", {}).get("items", [])
    learning = sections.get("learning_dashboard", {}).get("items", [])
    innovations = sections.get("innovation", {}).get("items", [])
    requirements = sections.get("requirements", {}).get("items", [])
    tourism = sections.get("tourism", {}).get("items", [])
    apptech = sections.get("apptech_mtr", {}).get("items", [])
    if not projects and not learning and not innovations and not requirements and not tourism and not apptech:
        return None

    project_districts = distribution(
        projects, lambda item: item.get("district"), "project_districts", "พื้นที่ดำเนินโครงการ"
    )
    project_years = distribution(
        projects, lambda item: item.get("fiscal_year"), "project_years", "ปีงบประมาณของโครงการ"
    )
    innovation_categories = distribution(
        innovations, lambda item: item.get("category"), "innovation_categories", "หมวดนวัตกรรม"
    )
    requirement_categories = distribution(
        requirements,
        lambda item: item.get("category"),
        "requirement_categories",
        "หมวดโจทย์หรือความต้องการ",
    )
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
    else:
        summary = "มีหลักฐานโครงการหรือนวัตกรรมที่เชื่อมกับจังหวัด"

    highlights = []
    sorted_projects = sorted(
        projects,
        key=lambda item: str(item.get("fiscal_year") or ""),
        reverse=True,
    )
    for item in sorted_projects[:2]:
        highlights.append({
            "kind": "project",
            "title_th": item.get("project_name") or "ไม่ระบุชื่อโครงการ",
            "detail_th": " · ".join(
                value
                for value in (clean_text(item.get("district")), clean_text(item.get("research_unit")))
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
        "source_coverage": briefing.get("source_coverage", []),
        "quality": briefing.get("quality", {}),
        "methodology": {
            "join_level": "province",
            "comparison_basis_th": "ค่ากลางของจังหวัดที่มีข้อมูลในตัวชี้วัดเดียวกัน",
            "near_median_rule": "absolute_relative_difference_lte_10_percent",
            "policy_score_created": False,
            "raw_rows_included": False,
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
