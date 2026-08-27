from __future__ import annotations

import gzip
import json
import re
import time
from dataclasses import dataclass
from typing import Any

from tools.evidence_store import config_from_env, make_client


CACHE_TTL_SECONDS = 300
PMUA_STATIC_INNOVATION_TOTAL = 1172
PMUA_STATIC_INNOVATOR_TOTAL = 12059

LEARNING_SUMMARY_KEY = "raw/f2/f2_learning_dashboard/20260820T134600Z/complete_refresh_summary.json"
LEARNING_DASHBOARD_KEY = "raw/f2/f2_learning_dashboard/20260820T134600Z/learning_dashboard.json"
PMUA_PRODUCTS_KEY = "raw/f2/f2_target_household/20260818T163603Z/products_redacted.jsonl.gz"
PMUA_PROPOSE_KEY = "raw/f2/f2_target_household/20260820T134640Z/public_pages/propose.html"
PMUA_AREA_DISTRICTS_KEY = "raw/f4/pmua_area_lookup/20260826T145433Z/districts.jsonl.gz"
PMUA_AREA_SUBDISTRICTS_KEY = "raw/f4/pmua_area_lookup/20260826T145433Z/subdistricts.jsonl.gz"
PMUA_PRODUCT_DETAILS_KEY = "raw/f4/pmua_product_details/20260827T051354Z/product_details.jsonl.gz"
CLIG_MANIFEST_KEY = "raw/f4/clig_projects/20260823T072251Z/manifest.json"
CLIG_PROJECTS_KEY = "raw/f4/clig_projects/20260823T072251Z/projects.jsonl.gz"

CLIG_PROVINCE_FIELDS = (
    "project_title",
    "detail_title",
    "abstract_th",
    "abstract_en",
    "lead_organization",
)

THAI_PROVINCE_NAMES = (
    "กระบี่",
    "กรุงเทพมหานคร",
    "กาญจนบุรี",
    "กาฬสินธุ์",
    "กำแพงเพชร",
    "ขอนแก่น",
    "จันทบุรี",
    "ฉะเชิงเทรา",
    "ชลบุรี",
    "ชัยนาท",
    "ชัยภูมิ",
    "ชุมพร",
    "เชียงราย",
    "เชียงใหม่",
    "ตรัง",
    "ตราด",
    "ตาก",
    "นครนายก",
    "นครปฐม",
    "นครพนม",
    "นครราชสีมา",
    "นครศรีธรรมราช",
    "นครสวรรค์",
    "นนทบุรี",
    "นราธิวาส",
    "น่าน",
    "บึงกาฬ",
    "บุรีรัมย์",
    "ปทุมธานี",
    "ประจวบคีรีขันธ์",
    "ปราจีนบุรี",
    "ปัตตานี",
    "พระนครศรีอยุธยา",
    "พะเยา",
    "พังงา",
    "พัทลุง",
    "พิจิตร",
    "พิษณุโลก",
    "เพชรบุรี",
    "เพชรบูรณ์",
    "แพร่",
    "ภูเก็ต",
    "มหาสารคาม",
    "มุกดาหาร",
    "แม่ฮ่องสอน",
    "ยโสธร",
    "ยะลา",
    "ร้อยเอ็ด",
    "ระนอง",
    "ระยอง",
    "ราชบุรี",
    "ลพบุรี",
    "ลำปาง",
    "ลำพูน",
    "เลย",
    "ศรีสะเกษ",
    "สกลนคร",
    "สงขลา",
    "สตูล",
    "สมุทรปราการ",
    "สมุทรสงคราม",
    "สมุทรสาคร",
    "สระแก้ว",
    "สระบุรี",
    "สิงห์บุรี",
    "สุโขทัย",
    "สุพรรณบุรี",
    "สุราษฎร์ธานี",
    "สุรินทร์",
    "หนองคาย",
    "หนองบัวลำภู",
    "อ่างทอง",
    "อำนาจเจริญ",
    "อุดรธานี",
    "อุตรดิตถ์",
    "อุทัยธานี",
    "อุบลราชธานี",
)


class F4DataError(RuntimeError):
    """Raised when the R2-backed F4 evidence snapshot cannot be loaded."""


@dataclass
class CachedF4Snapshot:
    loaded_at_monotonic: float
    payload: dict[str, Any]


_CACHE: CachedF4Snapshot | None = None


def clear_f4_cache() -> None:
    global _CACHE
    _CACHE = None


def _read_r2_object(client: Any, bucket: str, key: str) -> bytes:
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


def _read_json(client: Any, bucket: str, key: str) -> Any:
    return json.loads(_read_r2_object(client, bucket, key).decode("utf-8"))


def _read_jsonl_gz(client: Any, bucket: str, key: str) -> list[dict[str, Any]]:
    raw = gzip.decompress(_read_r2_object(client, bucket, key)).decode("utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _extract_pmua_propose_total(html: str) -> int | None:
    match = re.search(r"พบข้อมูลทั้งหมด\s*<b>\s*([0-9,]+)\s*</b>\s*รายการ", html)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _clig_manifest_project_count(manifest: dict[str, Any]) -> int:
    for dataset in manifest.get("datasets", []):
        if dataset.get("dataset_key") == "clig.projects":
            return int(dataset.get("row_count") or 0)
    return 0


def _target_province_names(learning_dashboard: dict[str, Any]) -> list[str]:
    rows = learning_dashboard.get("provinces") or []
    names: list[str] = []
    for row in rows:
        if not isinstance(row, list) or not row:
            continue
        name = str(row[0] or "").strip()
        if not name or name == "Province":
            continue
        names.append(name)
    return sorted(set(names))


def _project_text(project: dict[str, Any]) -> str:
    return " ".join(str(project.get(field) or "") for field in CLIG_PROVINCE_FIELDS)


def _project_province_names(project: dict[str, Any]) -> list[str]:
    haystack = _project_text(project)
    names = {name for name in THAI_PROVINCE_NAMES if name in haystack}
    if "กรุงเทพ" in haystack or "Bangkok" in haystack:
        names.add("กรุงเทพมหานคร")
    return sorted(names)


def _project_matches_province(project: dict[str, Any], province_name_th: str) -> bool:
    return province_name_th in _project_province_names(project)


def _project_row(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_title": project.get("project_title") or project.get("detail_title") or "",
        "project_id": project.get("project_id") or "",
        "contract_no": project.get("contract_no") or "",
        "fiscal_year": project.get("fiscal_year") or "",
        "status": project.get("status") or "",
        "lead_organization": project.get("lead_organization") or "",
        "budget_baht": project.get("budget_baht"),
        "detail_url": project.get("detail_url") or "",
        "matched_provinces": _project_province_names(project),
    }


def _policy_status_label(status: Any) -> str:
    label = str(status or "").strip()
    if not label:
        return "ไม่ระบุสถานะ"
    parts = label.split()
    if parts and parts[-1].isdigit():
        return " ".join(parts[:-1]) or label
    return label


def _policy_project_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_order = [
        "อยู่ระหว่างดำเนินการ",
        "PMU กำลังตรวจสอบ",
        "ปิดโครงการ",
        "ยุติโครงการ",
        "ไม่ระบุสถานะ",
    ]
    counts: dict[str, int] = {}
    budget_total = 0.0
    budget_known = 0
    for row in rows:
        status = _policy_status_label(row.get("status"))
        counts[status] = counts.get(status, 0) + 1
        budget = row.get("budget_baht")
        if budget in (None, ""):
            continue
        try:
            budget_total += float(budget)
            budget_known += 1
        except (TypeError, ValueError):
            pass
    ordered = [
        {"label": label, "count": counts.pop(label)}
        for label in status_order
        if counts.get(label)
    ]
    ordered.extend({"label": label, "count": count} for label, count in sorted(counts.items()))
    return {
        "status_summary": ordered,
        "budget_baht_total": budget_total,
        "budget_known_rows": budget_known,
        "total": len(rows),
    }


def _innovation_row(
    row: dict[str, Any],
    province_names_by_code: dict[str, str],
    district_names_by_code: dict[str, str],
    subdistrict_names_by_code: dict[str, str],
    product_details_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    province_codes = [str(code).zfill(2) for code in row.get("provinces") or []]
    district_codes = [str(code) for code in row.get("districts") or []]
    subdistrict_codes = [str(code) for code in row.get("subdistricts") or []]
    product_id = row.get("product_id")
    detail = product_details_by_id.get(str(product_id), {})
    return {
        "title": row.get("title") or "",
        "product_id": product_id,
        "provinces": province_codes,
        "province_names": [province_names_by_code.get(code, code) for code in province_codes],
        "districts": district_codes,
        "district_names": [district_names_by_code.get(code, code) for code in district_codes],
        "subdistricts": subdistrict_codes,
        "subdistrict_names": [subdistrict_names_by_code.get(code, code) for code in subdistrict_codes],
        "source_url": row.get("source_url") or "",
        "fetched_at": row.get("fetched_at") or "",
        "detail_fetched_at": detail.get("fetched_at") or "",
        "section_labels": row.get("section_labels") or [],
        "trl_level": detail.get("trl_level") if detail.get("trl_level") not in (None, "") else row.get("trl_level"),
        "trl_status": detail.get("trl_status") or row.get("trl_status") or row.get("trl_label"),
        "latitude": detail.get("latitude"),
        "longitude": detail.get("longitude"),
    }


def _product_matches_any_code(row: dict[str, Any], province_codes: set[str]) -> bool:
    row_codes = {str(item).zfill(2) for item in row.get("provinces") or []}
    return bool(row_codes & province_codes)


def _project_matches_any_province(project: dict[str, Any], province_names_th: set[str]) -> bool:
    return bool(set(_project_province_names(project)) & province_names_th)


def _target_codes(province_names_by_code: dict[str, str]) -> set[str]:
    codes_by_name = {name: code for code, name in province_names_by_code.items()}
    return {
        str(codes_by_name[name]).zfill(2)
        for name in _snapshot()["target_province_names"]
        if name in codes_by_name
    }


def _area_name_map(rows: list[dict[str, Any]], code_field: str, name_field: str) -> dict[str, str]:
    return {
        str(row[code_field]): str(row[name_field])
        for row in rows
        if row.get(code_field) not in (None, "") and str(row.get(name_field) or "").strip()
    }


def _load_snapshot_from_r2() -> dict[str, Any]:
    try:
        config = config_from_env()
        client = make_client(config)
        bucket = config.bucket
        learning_summary = _read_json(client, bucket, LEARNING_SUMMARY_KEY)
        learning_dashboard = _read_json(client, bucket, LEARNING_DASHBOARD_KEY)
        products = _read_jsonl_gz(client, bucket, PMUA_PRODUCTS_KEY)
        propose_html = _read_r2_object(client, bucket, PMUA_PROPOSE_KEY).decode("utf-8", errors="replace")
        area_districts = _read_jsonl_gz(client, bucket, PMUA_AREA_DISTRICTS_KEY)
        area_subdistricts = _read_jsonl_gz(client, bucket, PMUA_AREA_SUBDISTRICTS_KEY)
        product_details = _read_jsonl_gz(client, bucket, PMUA_PRODUCT_DETAILS_KEY)
        clig_manifest = _read_json(client, bucket, CLIG_MANIFEST_KEY)
        clig_projects = _read_jsonl_gz(client, bucket, CLIG_PROJECTS_KEY)
    except Exception as exc:  # pragma: no cover - exact boto errors vary by environment
        raise F4DataError("F4 R2 evidence snapshot unavailable") from exc

    mapped_project_count = sum(1 for project in clig_projects if _project_province_names(project))
    product_details_by_id = {
        str(row["product_id"]): row
        for row in product_details
        if row.get("product_id") not in (None, "")
    }
    pmua_trl_count = sum(1 for row in product_details if row.get("trl_level") not in (None, ""))
    return {
        "learning_summary": learning_summary,
        "learning_dashboard": learning_dashboard,
        "products": products,
        "product_details": product_details,
        "product_details_by_id": product_details_by_id,
        "pmua_product_detail_count": len(product_details),
        "pmua_trl_count": pmua_trl_count,
        "district_names_by_code": _area_name_map(area_districts, "district_code", "district_name_th"),
        "subdistrict_names_by_code": _area_name_map(area_subdistricts, "subdistrict_code", "subdistrict_name_th"),
        "pmua_propose_total": _extract_pmua_propose_total(propose_html),
        "clig_manifest": clig_manifest,
        "clig_projects": clig_projects,
        "clig_project_count": _clig_manifest_project_count(clig_manifest),
        "clig_mapped_project_count": mapped_project_count,
        "target_province_names": _target_province_names(learning_dashboard),
        "source_keys": {
            "learning_summary": LEARNING_SUMMARY_KEY,
            "learning_dashboard": LEARNING_DASHBOARD_KEY,
            "pmua_products": PMUA_PRODUCTS_KEY,
            "pmua_propose": PMUA_PROPOSE_KEY,
            "pmua_area_districts": PMUA_AREA_DISTRICTS_KEY,
            "pmua_area_subdistricts": PMUA_AREA_SUBDISTRICTS_KEY,
            "pmua_product_details": PMUA_PRODUCT_DETAILS_KEY,
            "clig_manifest": CLIG_MANIFEST_KEY,
            "clig_projects": CLIG_PROJECTS_KEY,
        },
    }


def _snapshot() -> dict[str, Any]:
    global _CACHE
    now = time.monotonic()
    if _CACHE is None or now - _CACHE.loaded_at_monotonic > CACHE_TTL_SECONDS:
        _CACHE = CachedF4Snapshot(loaded_at_monotonic=now, payload=_load_snapshot_from_r2())
    return _CACHE.payload


def f4_overview(province_codes_by_name: dict[str, str] | None = None) -> dict[str, Any]:
    snapshot = _snapshot()
    province_codes_by_name = province_codes_by_name or {}
    product_count = len(snapshot["products"])
    clig_count = snapshot["clig_project_count"]
    target_names = snapshot["target_province_names"]
    target_codes = sorted(
        {
            str(province_codes_by_name[name]).zfill(2)
            for name in target_names
            if name in province_codes_by_name
        }
    )
    target_headline_count = int(snapshot["learning_summary"].get("province_rows") or 0)
    target_membership_note = (
        f"Target province membership table maps {len(target_codes):,} provinces; "
        f"headline count is {target_headline_count:,}."
    )
    return {
        "schema_version": "f4-dashboard-v1",
        "quality_label_th": "ข้อมูล evidence drilldown · ยังไม่ใช่ KPI รับรอง",
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "target_province_codes": target_codes,
        "target_province_names": target_names,
        "target_province_membership_count": len(target_codes),
        "target_province_headline_count": target_headline_count,
        "target_province_membership_note": target_membership_note,
        "cards": [
            {
                "key": "target_provinces",
                "label": "พื้นที่เป้าหมาย",
                "value": target_headline_count,
                "unit": "จังหวัด",
                "source_behavior": "dynamic_r2",
                "membership_count": len(target_codes),
            },
            {
                "key": "innovations",
                "label": "เทคโนโลยี/นวัตกรรม",
                "value": PMUA_STATIC_INNOVATION_TOTAL,
                "unit": "นวัตกรรม",
                "source_behavior": "static_headline",
                "drilldown_row_count": product_count,
            },
            {
                "key": "policy_projects",
                "label": "นวัตกรรมเชิงนโยบาย",
                "value": clig_count,
                "unit": "โครงการวิจัย",
                "source_behavior": "dynamic_r2",
                "drilldown_row_count": len(snapshot["clig_projects"]),
            },
            {
                "key": "local_innovators",
                "label": "นวัตกรท้องถิ่น/นวัตกร",
                "value": PMUA_STATIC_INNOVATOR_TOTAL,
                "unit": "คน",
                "source_behavior": "static_headline",
            },
        ],
        "evidence_notes": [
            target_membership_note,
            f"PMUA product parsed list has {product_count:,} rows.",
            f"Older R2 /propose snapshot headline was {snapshot['pmua_propose_total']:,}."
            if snapshot["pmua_propose_total"]
            else "Older R2 /propose snapshot headline was not parsed.",
            f"CLIG province text mapping currently maps {snapshot['clig_mapped_project_count']:,} / {len(snapshot['clig_projects']):,} projects.",
        ],
        "source_keys": snapshot["source_keys"],
    }


def f4_province_summary(
    province_code: str,
    province_name_th: str,
    province_names_by_code: dict[str, str],
) -> dict[str, Any]:
    snapshot = _snapshot()
    code = str(province_code).zfill(2)
    target_codes = _target_codes(province_names_by_code)
    product_rows = [
        row for row in snapshot["products"] if code in {str(item).zfill(2) for item in row.get("provinces") or []}
    ]
    project_rows = [
        project for project in snapshot["clig_projects"] if _project_matches_province(project, province_name_th)
    ]
    return {
        "province_code": code,
        "province_name_th": province_name_th,
        "quality_label_th": "ข้อมูล evidence-matched · ยังไม่ใช่ KPI รับรอง",
        "is_target_province": code in target_codes,
        "target_membership_source": LEARNING_DASHBOARD_KEY,
        "cards": [
            {
                "key": "target_membership",
                "label": "พื้นที่เป้าหมาย 67 จังหวัด",
                "value": 1 if code in target_codes else 0,
                "unit": "อยู่ในพื้นที่เป้าหมาย" if code in target_codes else "ไม่อยู่ในชุดเป้าหมาย",
                "source_behavior": "target_membership_r2",
            },
            {
                "key": "innovations",
                "label": "เทคโนโลยี/นวัตกรรม",
                "value": len(product_rows),
                "unit": "นวัตกรรม",
                "match_type": "province_code",
            },
            {
                "key": "policy_projects",
                "label": "นวัตกรรมเชิงนโยบาย",
                "value": len(project_rows),
                "unit": "โครงการวิจัย",
                "match_type": "thai_province_name_text",
            },
        ],
        "notes": [
            "พื้นที่เป้าหมายอ่านจาก R2 target membership ไม่ได้อนุมานจากจำนวน PMUA/CLIG.",
            "PMUA rows filter by explicit province code in the R2 product list.",
            "CLIG rows filter by Thai province-name text match and may miss projects without province text.",
        ],
        "source_keys": snapshot["source_keys"],
        "province_names_by_code": {
            code: province_names_by_code.get(code, province_name_th),
        },
    }


def f4_region_summary(
    region_name_th: str,
    province_codes: list[str],
    province_names_by_code: dict[str, str],
) -> dict[str, Any]:
    snapshot = _snapshot()
    codes = {str(code).zfill(2) for code in province_codes}
    names = {province_names_by_code[code] for code in codes if code in province_names_by_code}
    product_rows = [row for row in snapshot["products"] if _product_matches_any_code(row, codes)]
    project_rows = [project for project in snapshot["clig_projects"] if _project_matches_any_province(project, names)]
    target_count = len(_target_codes(province_names_by_code) & codes)
    return {
        "region_name_th": region_name_th,
        "province_codes": sorted(codes),
        "quality_label_th": "ข้อมูล evidence-matched ระดับภาค · ยังไม่ใช่ KPI รับรอง",
        "cards": [
            {
                "key": "target_provinces",
                "label": "พื้นที่เป้าหมาย",
                "value": target_count,
                "unit": "จังหวัด",
                "source_behavior": "target_membership_r2",
            },
            {
                "key": "innovations",
                "label": "เทคโนโลยี/นวัตกรรม",
                "value": len(product_rows),
                "unit": "นวัตกรรม",
                "match_type": "region_province_code",
            },
            {
                "key": "policy_projects",
                "label": "นวัตกรรมเชิงนโยบาย",
                "value": len(project_rows),
                "unit": "โครงการวิจัย",
                "match_type": "region_thai_province_name_text",
            },
            {
                "key": "local_innovators",
                "label": "นวัตกรท้องถิ่น/นวัตกร",
                "value": None,
                "unit": "ยังไม่มี regional source",
                "source_behavior": "not_available_region",
            },
        ],
        "notes": [
            "PMUA region rows filter by explicit province codes in the R2 product list.",
            "CLIG region rows filter by Thai province-name text match across provinces in the selected region.",
            "นวัตกรท้องถิ่น/นวัตกรยังไม่มี regional source ใน R2 evidence ชุดนี้.",
        ],
        "source_keys": snapshot["source_keys"],
    }


def f4_innovations(
    province_code: str | None = None,
    province_names_by_code: dict[str, str] | None = None,
    province_codes: list[str] | None = None,
) -> dict[str, Any]:
    snapshot = _snapshot()
    province_names_by_code = province_names_by_code or {}
    products = snapshot["products"]
    if province_code:
        code = str(province_code).zfill(2)
        products = [
            row for row in products if code in {str(item).zfill(2) for item in row.get("provinces") or []}
        ]
    elif province_codes:
        codes = {str(code).zfill(2) for code in province_codes}
        products = [row for row in products if _product_matches_any_code(row, codes)]
    rows = [
        _innovation_row(
            row,
            province_names_by_code,
            snapshot["district_names_by_code"],
            snapshot["subdistrict_names_by_code"],
            snapshot["product_details_by_id"],
        )
        for row in products
    ]
    return {
        "total": len(rows),
        "rows": rows,
        "quality_label_th": "parsed PMUA AppTech R2 evidence list",
        "source_key": PMUA_PRODUCTS_KEY,
        "detail_source_key": PMUA_PRODUCT_DETAILS_KEY,
        "detail_row_count": snapshot["pmua_product_detail_count"],
        "trl_known_rows": snapshot["pmua_trl_count"],
    }


def f4_policy_projects(
    province_name_th: str | None = None,
    province_names_th: list[str] | None = None,
) -> dict[str, Any]:
    snapshot = _snapshot()
    projects = snapshot["clig_projects"]
    if province_name_th:
        projects = [
            project for project in projects if _project_matches_province(project, province_name_th)
        ]
    elif province_names_th:
        names = {str(name).strip() for name in province_names_th if str(name).strip()}
        projects = [project for project in projects if _project_matches_any_province(project, names)]
    rows = [_project_row(project) for project in projects]
    summary = _policy_project_summary(rows)
    return {
        "total": len(rows),
        "rows": rows,
        "status_summary": summary["status_summary"],
        "budget_baht_total": summary["budget_baht_total"],
        "budget_known_rows": summary["budget_known_rows"],
        "quality_label_th": "CLIG R2 evidence list; province counts are evidence-matched",
        "source_key": CLIG_PROJECTS_KEY,
    }
