from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(
    os.environ.get("AIAT_EVIDENCE_ROOT", str(PROJECT_ROOT.parent))
).expanduser().resolve()
DEFAULT_BUNDLE = (
    WORKSPACE_ROOT
    / "data/push_staging/f1_sradss_ppaos/20260821T130211Z/raw_json_bundle.zip"
)
OUTPUT_PATH = PROJECT_ROOT / "data/public/f1_detail_projection.json"
MANIFEST_PATH = PROJECT_ROOT / "data/public/f1_detail_projection_manifest.json"
SOURCE_URL = "https://sradss.ppaos.com/"
SOURCE_DASHBOARD_URL = "https://sradss.ppaos.com/dashboard/?p=ppaos-poverty-drive"


def read_json(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    return json.loads(archive.read(name))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def number(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return int(parsed) if parsed.is_integer() else round(parsed, 4)


def numeric_map(value: dict[str, Any] | None, keys: tuple[str, ...]) -> dict[str, Any]:
    source = value or {}
    return {key: number(source.get(key)) for key in keys}


def group_counts(value: dict[str, Any] | None) -> dict[str, Any]:
    source = value or {}
    return numeric_map(source, ("very_hard", "hard", "fair", "good", "total"))


def transition_summary(row: dict[str, Any]) -> dict[str, Any]:
    matrix = row.get("transition") or {}
    improved = 0
    unchanged = 0
    declined = 0
    for from_key, destinations in matrix.items():
        from_level = int(re.sub(r"\D", "", str(from_key)) or 0)
        for to_key, raw_count in (destinations or {}).items():
            to_level = int(re.sub(r"\D", "", str(to_key)) or 0)
            count = int(number(raw_count) or 0)
            if to_level > from_level:
                improved += count
            elif to_level < from_level:
                declined += count
            else:
                unchanged += count
    return {
        "dimension_key": row.get("dim"),
        "dimension_label": row.get("label"),
        "average_score": number(row.get("avg_score")),
        "households": number(row.get("total_count")),
        "improved": improved,
        "unchanged": unchanged,
        "declined": declined,
        "matrix": matrix,
    }


def project_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    fields = (
        "key",
        "group",
        "unit",
        "value",
        "prev_value",
        "target_value",
        "target_pct",
        "yoy_direction",
        "yoy_pct",
    )
    return [
        {key: (number(item.get(key)) if key in {"value", "prev_value", "target_value", "target_pct", "yoy_pct"} else item.get(key)) for key in fields}
        for item in payload.get("items", [])
        if item.get("key")
    ]


def assistance_dimensions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "key": item.get("key"),
            "title": item.get("title"),
            "households": number(item.get("households")),
            "episodes": number(item.get("episode_count")),
            "budget_baht": number(item.get("budget_baht")),
            "household_share_pct": number(item.get("share_pct")),
            "episode_share_pct": number(item.get("episode_share_pct")),
            "budget_share_pct": number(item.get("budget_share_pct")),
        }
        for item in payload.get("dimensions", [])
        if item.get("key")
    ]


def assistance_sides(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "households": number(item.get("family")),
            "people": number(item.get("person")),
            "episodes": number(item.get("episode")),
            "budget_baht": number(item.get("cost")),
        }
        for item in rows
    ]


DIMENSION_LABELS = {
    "human": "ทุนมนุษย์",
    "physical": "ทุนกายภาพ",
    "financial": "ทุนทางเศรษฐกิจ",
    "natural_res": "ทุนธรรมชาติ",
    "social": "ทุนทางสังคม",
}


def detailed_dimension(
    payload: dict[str, Any], expected_key: str
) -> dict[str, Any]:
    source_key = str(payload.get("dimension") or "")
    source_matches_file = source_key == expected_key
    sections = []
    for section in (payload.get("sections", []) if source_matches_file else []):
        items = []
        for item in section.get("items", []):
            items.append(
                {
                    "key": item.get("field_value"),
                    "label": item.get("label"),
                    "very_hard": number(item.get("very_hard")),
                    "hard": number(item.get("hard")),
                    "fair": number(item.get("fair")),
                    "good": number(item.get("good")),
                    "total": number(item.get("total")),
                }
            )
        sections.append(
            {
                "key": section.get("field"),
                "title": section.get("title"),
                "type": section.get("type"),
                "totals": group_counts(section.get("totals")),
                "items": items,
            }
        )
    return {
        "key": expected_key,
        "label": DIMENSION_LABELS[expected_key],
        "detail_available": source_matches_file,
        "source_dimension_key": source_key or None,
        "sections": sections,
    }


def public_catalog_by_code() -> dict[str, dict[str, Any]]:
    payload = json.loads(
        (PROJECT_ROOT / "data/public/public_dashboard.json").read_text(encoding="utf-8")
    )
    return {
        str(item["province_code"]).zfill(2): item
        for item in payload.get("provinces", [])
    }


def build(bundle_path: Path) -> dict[str, Any]:
    catalog = public_catalog_by_code()
    with zipfile.ZipFile(bundle_path) as archive:
        names = set(archive.namelist())
        groups = read_json(archive, "core/groups_2569.json")
        star_map = read_json(archive, "core/poverty_districts.json").get("starAmpByProv", {})
        group_by_code: dict[str, str] = {}
        for group in groups.get("groups", []):
            for province in group.get("provinces", []):
                group_by_code[str(province.get("code")).zfill(2)] = str(group.get("name") or "")
        province_codes = sorted(group_by_code)
        provinces: dict[str, Any] = {}
        national_counts = Counter()

        for code in province_codes:
            core = read_json(archive, f"geo/core_2569_p{code}.json")
            family_report = read_json(archive, f"report/report_family_2569_{code}.json")
            person_report = read_json(archive, f"report/report_person_2569_{code}.json")
            project = read_json(archive, f"drive/drive_project_overview_2569_{code}.json")
            assistance = read_json(archive, f"drive/drive_assistance_summary_2569_{code}.json")
            assist_bundle = read_json(archive, f"core/assist_bundle_{code}.json")
            om = read_json(archive, f"core/om_{code}.json")
            models = read_json(archive, f"report/model_groups_summary_2569_{code}.json")
            transition = read_json(archive, f"drive/five_dim_transition_2569_{code}.json")
            score_year = read_json(archive, f"drive/five_dim_chart_year_2569_{code}.json")

            dimension_details = []
            for dimension in ("human", "physical", "financial", "natural_res", "social"):
                dimension_details.append(
                    detailed_dimension(
                        read_json(archive, f"report/report_five_dim_2569_{code}_{dimension}.json"),
                        dimension,
                    )
                )

            family_by_district = {
                str(item.get("district_id")): item
                for item in family_report.get("districts", [])
                if item.get("district_id")
            }
            person_by_district = {
                str(item.get("district_id")): item
                for item in person_report.get("districts", [])
                if item.get("district_id")
            }
            current_by_district = {
                str(item.get("district_id")): item
                for item in core.get("districts", [])
                if item.get("district_id")
            }
            dimension_by_district = {
                str(item.get("district_id")): item
                for item in core.get("dimensions_by_district", [])
                if item.get("district_id")
            }
            gender_by_district = {
                str(item.get("district")): item
                for item in core.get("gender_by_district", [])
                if item.get("district")
            }
            star_districts = {str(value) for value in star_map.get(code, [])}
            districts = []
            tambon_total = 0
            tambon_data_total = 0

            for district_id, family_row in sorted(family_by_district.items()):
                current = current_by_district.get(district_id) or {}
                dimensions = dimension_by_district.get(district_id) or {}
                district_name = (
                    current.get("district_name_thai")
                    or family_row.get("district_name")
                    or person_by_district.get(district_id, {}).get("district_name")
                )
                gender = gender_by_district.get(str(district_name)) or {}
                tambon_path = f"geo/tambons_2569_p{code}_a{district_id}.json"
                tambons = []
                if tambon_path in names:
                    for item in read_json(archive, tambon_path).get("tambons", []):
                        has_data = int(number(item.get("household")) or 0) > 0
                        tambons.append(
                            {
                                "tambon_code": str(item.get("code") or ""),
                                "tambon_name": item.get("name"),
                                "has_current_data": has_data,
                                "households": number(item.get("household")),
                                "people": number(item.get("member")),
                                "average_score": number(item.get("avg_score")),
                                "gender": numeric_map(item, ("male", "female", "other")),
                                "poverty_levels": numeric_map(item, ("lv1", "lv2", "lv3", "lv4")),
                            }
                        )
                        tambon_total += 1
                        tambon_data_total += int(has_data)
                districts.append(
                    {
                        "district_id": district_id,
                        "district_name": district_name,
                        "marked_as_poverty_area": district_id in star_districts,
                        "has_current_data": bool(current),
                        "households": number(current.get("household_count")),
                        "people": number(current.get("member_count")),
                        "poor_households": number(current.get("poor_count")),
                        "average_score": number(current.get("avg_score")),
                        "poverty_levels": numeric_map(current, ("lv1", "lv2", "lv3", "lv4")),
                        "gender": numeric_map(gender, ("male", "female", "other")),
                        "dimensions": numeric_map(
                            dimensions,
                            ("human", "physical", "financial", "natural_res", "social", "overall"),
                        ),
                        "household_groups": group_counts(family_row),
                        "people_groups": group_counts(person_by_district.get(district_id)),
                        "tambons": tambons,
                    }
                )

            transition_rows = [
                transition_summary(item)
                for item in transition.get("summary_year_group", [])
            ]
            meta = catalog.get(code, {})
            current_district_total = sum(item["has_current_data"] for item in districts)
            national_counts.update(
                {
                    "province_count": 1,
                    "district_list_count": len(districts),
                    "district_data_count": current_district_total,
                    "tambon_list_count": tambon_total,
                    "tambon_data_count": tambon_data_total,
                }
            )
            provinces[code] = {
                "province_code": code,
                "province_name_th": meta.get("province_name_th") or core.get("province_name"),
                "region": meta.get("region"),
                "year": "2569",
                "province_group": group_by_code.get(code),
                "coverage": {
                    "district_list_count": len(districts),
                    "district_data_count": current_district_total,
                    "tambon_list_count": tambon_total,
                    "tambon_data_count": tambon_data_total,
                },
                "people_and_households": {
                    "stats": numeric_map(
                        core.get("stats"),
                        ("total_districts", "total_tambons", "total_households", "total_members"),
                    ),
                    "gender": numeric_map(core.get("gender"), ("male", "female", "other", "total")),
                    "age_groups": [
                        {
                            "age_group": item.get("age_group"),
                            **numeric_map(item, ("male", "female", "other")),
                        }
                        for item in core.get("gender_by_age", [])
                    ],
                    "poverty_levels": [
                        {
                            "level": item.get("id"),
                            "label": item.get("detail"),
                            "households": number(item.get("cnt")),
                        }
                        for item in core.get("poverty_levels", [])
                    ],
                    "survey_years": [
                        {"year": item.get("survey_year"), "households": number(item.get("cnt"))}
                        for item in core.get("years", [])
                    ],
                    "household_groups": group_counts(family_report.get("totals")),
                    "people_groups": group_counts(person_report.get("totals")),
                },
                "livelihood_capitals": {
                    "scores": numeric_map(
                        core.get("dimensions"),
                        ("human", "physical", "financial", "natural_res", "social", "overall"),
                    ),
                    "score_spread": numeric_map(
                        core.get("dimensions"),
                        ("human_sd", "physical_sd", "financial_sd", "natural_res_sd", "social_sd", "overall_sd"),
                    ),
                    "survey_summary": {
                        "year": score_year.get("summary", {}).get("selected_year"),
                        "households": number(score_year.get("summary", {}).get("family_count")),
                        "human": number(score_year.get("summary", {}).get("avg_ch1")),
                        "physical": number(score_year.get("summary", {}).get("avg_ch2")),
                        "financial": number(score_year.get("summary", {}).get("avg_ch3")),
                        "natural_res": number(score_year.get("summary", {}).get("avg_ch4")),
                        "social": number(score_year.get("summary", {}).get("avg_ch5")),
                    },
                    "transition_year": transition.get("active_year"),
                    "transitions": transition_rows,
                    "details": dimension_details,
                },
                "poverty_models": [
                    {
                        "key": item.get("model_key"),
                        "name": item.get("model_name"),
                        "households": number(item.get("households")),
                        "people": number(item.get("people")),
                        "poor_people": number(item.get("poor")),
                        "poor_income_baht": number(item.get("poor_income")),
                        "poor_income_sum_baht": number(item.get("poor_income_sum")),
                    }
                    for item in models.get("rows", [])
                ],
                "om": {
                    "total": {
                        "methods": number(om.get("total_om")),
                        "career_chains": number(om.get("total_chain")),
                        "capital_baht": number(om.get("total_capital")),
                    },
                    "yearly": [
                        {
                            "year": item.get("year"),
                            "methods": number(item.get("om_count")),
                            "career_chains": number(item.get("chain_count")),
                            "capital_baht": number(item.get("capital")),
                        }
                        for item in om.get("by_year", [])
                    ],
                },
                "project": {
                    "year": project.get("year"),
                    "years_with_data": project.get("years_with_data", []),
                    "items": project_items(project),
                },
                "assistance": {
                    "year": assistance.get("year"),
                    "current": {
                        "households": number(assistance.get("total_households")),
                        "unique_households": number(assistance.get("total_households_unique")),
                        "episodes": number(assistance.get("total_episodes")),
                        "budget_baht": number(assistance.get("total_budget_baht")),
                    },
                    "dimensions": assistance_dimensions(assistance),
                    "all_years": {
                        "episodes": number(assist_bundle.get("summary", {}).get("total_help")),
                        "budget_baht": number(assist_bundle.get("summary", {}).get("total_cost")),
                        "sides": assistance_sides(assist_bundle.get("summary", {}).get("sides", [])),
                    },
                    "yearly": {
                        "years": assist_bundle.get("yearly", {}).get("years", []),
                        "sides": assistance_sides(assist_bundle.get("yearly", {}).get("summary", [])),
                    },
                },
                "districts": districts,
            }

        national_project = read_json(archive, "drive/drive_project_overview_2569_ALL.json")
        national_assistance = read_json(archive, "drive/drive_assistance_summary_2569_ALL.json")
        national_models = read_json(archive, "report/model_groups_summary_2569_ALL.json")
        group_counts_national = Counter(group_by_code.values())
        return {
            "schema_version": "1.0.0",
            "generated_at": "2026-08-21T13:02:11+00:00",
            "publication_status": "public_candidate_projection",
            "source_id": "f1_sradss_ppaos",
            "as_of": "2569",
            "source_url": SOURCE_URL,
            "dashboard_url": SOURCE_DASHBOARD_URL,
            "privacy": {
                "grain": "ข้อมูลรวมระดับจังหวัด อำเภอ และตำบล",
                "aggregate_only": True,
                "individual_records_included": False,
                "direct_identifiers_included": False,
            },
            "coverage": dict(national_counts),
            "province_groups": [
                {"name": name, "province_count": count}
                for name, count in sorted(group_counts_national.items())
            ],
            "national": {
                "project": {
                    "year": national_project.get("year"),
                    "items": project_items(national_project),
                },
                "assistance": {
                    "year": national_assistance.get("year"),
                    "current": {
                        "households": number(national_assistance.get("total_households")),
                        "unique_households": number(national_assistance.get("total_households_unique")),
                        "episodes": number(national_assistance.get("total_episodes")),
                        "budget_baht": number(national_assistance.get("total_budget_baht")),
                    },
                    "dimensions": assistance_dimensions(national_assistance),
                },
                "poverty_models": [
                    {
                        "key": item.get("model_key"),
                        "name": item.get("model_name"),
                        "households": number(item.get("households")),
                        "people": number(item.get("people")),
                        "poor_people": number(item.get("poor")),
                    }
                    for item in national_models.get("rows", [])
                ],
            },
            "provinces": provinces,
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the reviewed aggregate F1 province, district and tambon projection"
    )
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    bundle_path = args.bundle.expanduser().resolve()
    if not bundle_path.is_file():
        raise SystemExit(f"ไม่พบไฟล์ R2 bundle: {bundle_path}")
    payload = build(bundle_path)
    write_json(args.output, payload)
    manifest = {
        "schema_version": "1.0.0",
        "generated_at": payload["generated_at"],
        "source_id": "f1_sradss_ppaos",
        "as_of": payload["as_of"],
        "input": {
            "snapshot": bundle_path.parent.name,
            "bytes": bundle_path.stat().st_size,
            "sha256": sha256(bundle_path),
        },
        "output": {
            "path": args.output.resolve().relative_to(PROJECT_ROOT).as_posix(),
            "bytes": args.output.stat().st_size,
            "sha256": sha256(args.output),
        },
        "coverage": payload["coverage"],
        "privacy": payload["privacy"],
    }
    write_json(MANIFEST_PATH, manifest)
    print(
        "สร้างข้อมูลฝ่าย 1 แล้ว "
        f"{payload['coverage']['province_count']} จังหวัด "
        f"{payload['coverage']['district_list_count']} อำเภอ "
        f"{payload['coverage']['tambon_list_count']} ตำบล"
    )


if __name__ == "__main__":
    main()
