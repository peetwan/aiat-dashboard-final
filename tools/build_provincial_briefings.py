from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
BASE_RUN = WORKSPACE_ROOT / "data/qa/web_profile_team_drive_simple/20260814T_team_drive_simple_final"
MERGE_RUN = WORKSPACE_ROOT / "data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01"
STAGED_ROOT = WORKSPACE_ROOT / "data/staged"
SRA_REGISTRY_PATH = (
    BASE_RUN
    / "01_f1_sradss_ppaos/data/f1_sradss_ppaos_drilldown_province_registry_rows.csv"
)
SRA_EXTENDED_ROOT = (
    STAGED_ROOT
    / "f1_sradss_ppaos/20260804T_sradss_extended_silver_01/silver"
)
OUTPUT_ROOT = PROJECT_ROOT / "data/public/provincial_briefings"
SOURCE_INSIGHTS_PATH = PROJECT_ROOT / "data/public/source_insights.json"
LEARNING_PATH = PROJECT_ROOT / "data/public/learning_dashboard.json"
LEARNING_MANIFEST_PATH = PROJECT_ROOT / "data/public/learning_dashboard_manifest.json"
UNMAPPED_PATH = PROJECT_ROOT / "data/public/unmapped_records.json"
REQUIREMENT_PATH = (
    STAGED_ROOT
    / "f2_apptech_mru/20260805T_apptech_mru_silver_02/silver/apptech_mru_public_requirement.jsonl"
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_entry(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(WORKSPACE_ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def csv_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def jsonl_rows(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def clean(value: Any) -> Any:
    if value in (None, "", "\\N"):
        return None
    return value


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).replace("จังหวัด", "")


def exact_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def canonical_code(value: Any) -> str | None:
    if value in (None, "", "\\N", "_unknown", "_multi_province"):
        return None
    text = str(value).strip()
    return text.zfill(2)[:2] if text.isdigit() else None


def source_fields(row: dict[str, Any], prefix: str = "source_fields__") -> dict[str, Any]:
    return {
        key.removeprefix(prefix): clean(value)
        for key, value in row.items()
        if key.startswith(prefix) and clean(value) is not None
    }


def compact_provenance(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "endpoint_url": clean(row.get("source_endpoint")),
        "fetched_at": clean(row.get("fetched_at")),
        "as_of": clean(row.get("as_of")),
        "quality_status": clean(row.get("quality_status")),
        "record_hash": clean(row.get("source_record_sha256")),
    }


CONTACT_CLAUSE_RE = re.compile(
    r"(?i)(?:ติดต่อ|โทร(?:ศัพท์)?|เบอร์(?:โทร)?|อีเมล|อีเมล์|"
    r"\bcontact\b|\bphone\b|\btel(?:ephone)?\b|\be-?mail\b|"
    r"\bline(?:\s*id)?\b|ไลน์|\bfacebook\b|เฟซบุ๊ก|"
    r"\binstagram\b|\btiktok\b)\s*[:：]?\s*[^\n;|]*"
)
ADDRESS_CLAUSE_RE = re.compile(
    r"(?i)(?:ที่อยู่|address|เลขที่\s*\d+|หมู่(?:ที่)?\s*\d+|ซอย|ถนน)"
    r"\s*[:：]?\s*[^\n;|]*"
)
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(
    r"(?<![\dA-Za-z])(?:\+?66|0)\s*\d(?:[\s().-]*\d){7,9}(?!\d)"
)
PUBLIC_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
SOCIAL_HANDLE_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9._-]{2,}")


def sanitize_public_text(value: Any) -> str | None:
    """Return descriptive text with contact/address fragments removed.

    This is a defensive backstop. Public projections still use strict field
    whitelists, so structured contact fields never reach this function.
    """

    text = exact_text(value)
    if not text:
        return None
    for pattern in (
        CONTACT_CLAUSE_RE,
        ADDRESS_CLAUSE_RE,
        EMAIL_RE,
        PHONE_RE,
        PUBLIC_URL_RE,
        SOCIAL_HANDLE_RE,
    ):
        text = pattern.sub(" ", text)
    text = re.sub(r"[;|]+", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" \t\r\n,.;:|-–—")
    return text or None


def project_localized_text(value: Any, *, sanitize: bool = False) -> dict[str, str] | str | None:
    """Keep only display languages understood by the public UI."""

    if isinstance(value, dict):
        projected: dict[str, str] = {}
        for language in ("TH", "EN", "CN", "th", "en", "cn"):
            text = sanitize_public_text(value.get(language)) if sanitize else clean(value.get(language))
            if text is not None:
                projected[language] = str(text)
        return projected or None
    return sanitize_public_text(value) if sanitize else clean(value)


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def project_cultural_record(
    row: dict[str, Any], source_artifact: Path
) -> tuple[str | None, dict[str, Any]]:
    """Create the executive-safe Cultural Map briefing record.

    The map source contains people, free-form histories, stakeholders,
    addresses, media and assessment narratives. None of those fields are
    copied to province briefings. The public map retains its independently
    reviewed coordinate projection; briefing cards do not need coordinates.
    """

    data = row.get("data") or {}
    location = data.get("location") or {}
    administrative = location.get("administrative") or {}
    province = administrative.get("province") or {}
    amphure = administrative.get("amphure") or {}
    tambon = administrative.get("tambon") or {}
    classification = data.get("classification") or {}
    names = data.get("names") or {}
    warnings = row.get("validation_warnings") or []
    code = canonical_code(province.get("code"))
    item = {
        "record_id": clean(row.get("external_id")),
        "record_code": clean((data.get("identifiers") or {}).get("record_code")),
        "title_th": sanitize_public_text(names.get("th")) or sanitize_public_text(row.get("title")),
        "title_en": sanitize_public_text(names.get("en")),
        "category": clean((classification.get("primary_category") or {}).get("name_th")),
        "cultural_type": clean((classification.get("cultural_type") or {}).get("name_th")),
        "province_code": code,
        "province_name_th": clean(province.get("name_th")),
        "amphoe": clean(amphure.get("name_th")),
        "tambon": clean(tambon.get("name_th")),
        "source_url": clean(row.get("source_url")),
        "provenance": {
            "source_artifact": source_artifact.relative_to(WORKSPACE_ROOT).as_posix(),
            "recorded_at": clean((data.get("dates") or {}).get("recorded")),
            "record_hash": canonical_json_sha256(row),
        },
        "quality": {
            "status": "has_validation_warnings" if warnings else "projected_from_source",
            "warning_count": len(warnings),
        },
    }
    return code, item


def _safe_fare(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    amount = safe_float(value.get("amount"))
    currency = clean(value.get("currency"))
    if amount is None and currency is None:
        return None
    return {"amount": amount, "currency": currency}


def project_tourism_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project a Ruam Thiao page without copying its payload wholesale."""

    page_id = clean(payload.get("page_id"))
    data = payload.get("data") or {}
    projected: dict[str, Any]
    record_count = 0

    if page_id == "recommend":
        categories = []
        for category in data.get("categories") or []:
            items = []
            for item in category.get("items") or []:
                items.append({
                    "record_id": clean(item.get("item_id")),
                    "title": project_localized_text(item.get("title"), sanitize=True),
                    "description": project_localized_text(item.get("description"), sanitize=True),
                })
            record_count += len(items)
            categories.append({
                "label": project_localized_text(category.get("label"), sanitize=True),
                "items": items,
            })
        projected = {"categories": categories}
    elif page_id == "homepage":
        stations = []
        for station in (data.get("map") or {}).get("stations") or []:
            stations.append({
                "name": project_localized_text(station.get("name"), sanitize=True),
                "nearby_count": len(station.get("venues") or []),
            })
        record_count = len(stations)
        projected = {"map": {"stations": stations}}
    elif page_id == "komepage":
        record_count = len(data.get("lantern_production_groups") or [])
        projected = {"lantern_group_count": record_count}
    elif page_id == "travel":
        train = data.get("train") or {}
        tram = data.get("tourism_tram") or {}
        train_services = []
        for service in train.get("services") or []:
            train_services.append({
                "service_days": [clean(day) for day in service.get("service_days") or [] if clean(day)],
                "origin": {
                    "name": project_localized_text((service.get("origin") or {}).get("name"), sanitize=True),
                },
                "destination": {
                    "name": project_localized_text((service.get("destination") or {}).get("name"), sanitize=True),
                },
                "departure_time": clean(service.get("departure_time")),
                "arrival_time": clean(service.get("arrival_time")),
                "fare": _safe_fare(service.get("fare")),
                "description": project_localized_text(service.get("description"), sanitize=True),
            })
        tram_services = []
        for service in tram.get("services") or []:
            tram_services.append({
                "route_name": project_localized_text(service.get("route_name"), sanitize=True),
                "departure_time": clean(service.get("departure_time")),
                "fare": _safe_fare(service.get("fare")),
            })
        other_transport = []
        for service in data.get("other_transport") or []:
            other_transport.append({
                "type": clean(service.get("type")),
                "name": project_localized_text(service.get("name"), sanitize=True),
            })
        record_count = len(train_services) + len(tram_services) + len(other_transport)
        projected = {
            "train": {
                "service_days": [
                    {
                        "label": project_localized_text(item.get("label"), sanitize=True),
                        "days": [clean(day) for day in item.get("days") or [] if clean(day)],
                    }
                    for item in train.get("service_days") or []
                ],
                "services": train_services,
            },
            "tourism_tram": {
                "operating_days": [clean(day) for day in tram.get("operating_days") or [] if clean(day)],
                "closed_days": [clean(day) for day in tram.get("closed_days") or [] if clean(day)],
                "services": tram_services,
            },
            "other_transport": other_transport,
        }
    elif page_id == "contact":
        emergency_rows = data.get("emergency_numbers") or []
        service_labels = [
            project_localized_text(item.get("service"), sanitize=True)
            for item in emergency_rows
        ] + [
            project_localized_text(item.get("name"), sanitize=True)
            for item in data.get("service_contacts") or []
        ]
        service_labels = [item for item in service_labels if item]
        # The source manifest counts the six emergency rows as the page records.
        # Service-contact names are nested labels, not additional stable records.
        record_count = len(emergency_rows)
        projected = {
            "service_availability": [
                {"label": label}
                for label in service_labels
            ],
            "service_availability_label_count": len(service_labels),
        }
    else:
        raise ValueError(f"unsupported tourism page_id: {page_id!r}")

    warnings = payload.get("warnings") or []
    return {
        "page_id": page_id,
        "source_url": clean(payload.get("source_url")),
        "scraped_at": clean(payload.get("scraped_at")),
        "record_count": record_count,
        "data": projected,
        "provenance": {
            "source_url": clean(payload.get("source_url")),
            "scraped_at": clean(payload.get("scraped_at")),
            "bundle_sha256": clean(payload.get("bundle_sha256")),
        },
        "quality": {
            "status": "has_warnings" if warnings else "projected_from_source",
            "warning_count": len(warnings),
        },
    }


def project_requirement_record(
    row: dict[str, Any], code_by_exact_name: dict[str, str]
) -> tuple[list[str], dict[str, Any], list[str]]:
    if row.get("record_type") != "apptech_mru_public_requirement":
        raise ValueError("requirement projection received a non-requirement record")
    fields = row.get("normalized_fields")
    if not isinstance(fields, dict):
        raise ValueError("requirement record has no normalized_fields object")

    safe_areas: list[dict[str, Any]] = []
    linked_codes: set[str] = set()
    unmatched_names: set[str] = set()
    for area in fields.get("areas") or []:
        if not isinstance(area, dict):
            continue
        province_name = exact_text(area.get("province"))
        code = code_by_exact_name.get(province_name)
        if code:
            linked_codes.add(code)
        elif province_name:
            unmatched_names.add(province_name)
        safe_areas.append({
            "tambon": clean(area.get("tambon")),
            "amphoe": clean(area.get("amphoe")),
            "province": province_name or None,
            "province_code": code,
        })

    provenance = row.get("provenance") or {}
    quality = row.get("quality") or {}
    item = {
        "record_id": clean(fields.get("record_id")) or clean(row.get("source_record_id")),
        "record_grain": "one_public_requirement",
        "title": clean(fields.get("title")),
        "description": clean(fields.get("description")),
        "category": clean(fields.get("category_label")),
        "areas": safe_areas,
        "source_url": clean(provenance.get("detail_url")) or clean(provenance.get("source_url")),
        "provenance": {
            "endpoint_url": clean(provenance.get("list_endpoint")),
            "fetched_at": clean(provenance.get("fetched_at")),
            "as_of": clean(provenance.get("as_of")),
            "run_id": clean(provenance.get("run_id")),
            "record_hash": clean(provenance.get("detail_artifact_sha256")),
            "quality_status": clean(quality.get("confidence")),
        },
        "scope_note_th": "เป็นโจทย์หรือความต้องการหนึ่งรายการ ไม่ใช่ผลงานนวัตกรรมและไม่รวมกับยอด innovation",
    }
    return sorted(linked_codes), item, sorted(unmatched_names)


def housing_unmapped_reason(
    row: dict[str, Any], resolved_code: str | None, valid_codes: set[str]
) -> str:
    if resolved_code is not None and resolved_code not in valid_codes:
        return "source_province_code_not_in_official_crosswalk"
    if row.get("partition_type") == "area_name_noncanonical":
        return "source_geography_not_at_province_grain"
    if clean(row.get("partition_key")) in {None, "_unmapped", "_unknown"}:
        return "source_geography_missing"
    return "source_geography_not_in_exact_crosswalk"


def project_unmapped_housing_record(
    row: dict[str, Any],
    metadata: dict[str, Any],
    resolved_code: str | None,
    valid_codes: set[str],
) -> dict[str, Any]:
    resource_id = row.get("resource_id") or row.get("dataset_id", "").rsplit(":", 1)[-1]
    geography_keys = (
        "cwt_id",
        "cwt_dc",
        "province_id",
        "province_name",
        "province_name_th",
        "area_name",
    )
    values = source_fields(row)
    return {
        "reason": housing_unmapped_reason(row, resolved_code, valid_codes),
        "dataset_id": clean(row.get("dataset_id")),
        "dataset_key": clean(row.get("dataset_key")) or clean(metadata.get("dataset_key")),
        "dataset_title": clean(row.get("dataset_title")) or clean(metadata.get("dataset_title")),
        "resource_id": resource_id,
        "resource_name": clean(row.get("resource_name")) or clean(metadata.get("resource_name")),
        "source_url": clean(metadata.get("resource_url")) or clean(row.get("source_endpoint")),
        "source_geography": {
            "partition_type": clean(row.get("partition_type")),
            "partition_key": clean(row.get("partition_key")),
            "resolved_candidate_code": resolved_code,
            "fields": {
                key: values[key]
                for key in geography_keys
                if clean(values.get(key)) is not None
            },
        },
        "record": {
            "row_number": clean(row.get("row_number")) or clean(row.get("source_record_id")),
            "record_grain": "one_approved_public_projection_row",
            "values": values,
            "provenance": compact_provenance(row),
        },
    }


def source_meta(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": source["source_id"],
        "name_th": source["name_th"],
        "url": source["url"],
        "acquisition_mode": source["acquisition_mode"],
        "readiness_status": source["readiness_status"],
        "quality_label_th": source.get("quality_label_th"),
        "source_note_th": source.get("notes_th"),
    }


def initial_section(source_id: str, title_th: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "title_th": title_th,
        "status": "source_has_no_record_for_province",
        "total_records": 0,
        "items": [],
    }


SOURCE_GRAIN_TH = {
    "f1_sradss_ppaos": "จังหวัด × ปี; คะแนนและ aggregate โครงการ/การช่วยเหลือตามต้นทาง",
    "f1_pppconnext": "แถว aggregate จาก widget ระดับจังหวัด/อำเภอ",
    "f2_culturalmap_university": "หนึ่งระเบียนทุนวัฒนธรรม",
    "f2_rmutdb": "หนึ่งระเบียนองค์ความรู้; ยังไม่มีจังหวัดที่ยืนยันได้",
    "f2_apptech_mtr": "aggregate กิจกรรมแพลตฟอร์มรายจังหวัด",
    "f2_apptech_mru": "หนึ่งนวัตกรรมหรือหนึ่งโจทย์ความต้องการ",
    "f2_learning_dashboard": "aggregate ผู้เข้าร่วมโครงการที่ต้นทางเลือก",
    "f2_learning_area_based": "หนึ่งหน่วย/ผู้ประกอบการเข้าร่วม; ไม่ใช่หนึ่งโครงการ",
    "f3_city_capital_open_data": "หนึ่งเทศบาล; ไม่ใช่ค่ารวมทั้งจังหวัด",
    "f3_ruamthiao_lamphun": "หนึ่งระเบียนเนื้อหาหน้าสาธารณะของลำพูน",
    "f3_housing_portal": "หนึ่ง observation จาก resource ที่เชื่อมจังหวัดได้",
}


def provisional_project_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group participant-grain Area-Based rows without inventing a project ID."""

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        key = tuple(
            exact_text(item.get(field)) or "ไม่ระบุ"
            for field in ("project_name", "fiscal_year", "research_unit")
        )
        grouped[key].append(item)

    projects: list[dict[str, Any]] = []
    for key, participants in grouped.items():
        project_name, fiscal_year, research_unit = key
        businesses = sorted({
            name
            for item in participants
            if (name := clean(item.get("business_name"))) is not None
        })
        geography: dict[str, set[str]] = defaultdict(set)
        for item in participants:
            district = clean(item.get("district")) or "ไม่ระบุอำเภอ"
            subdistrict = clean(item.get("subdistrict"))
            if subdistrict:
                geography[district].add(subdistrict)
            else:
                geography.setdefault(district, set())
        updated_values = [
            value
            for item in participants
            if (value := clean(item.get("updated_at"))) is not None
        ]
        group_seed = "\u001f".join(key)
        projects.append({
            "project_group_id": hashlib.sha256(group_seed.encode("utf-8")).hexdigest()[:16],
            "official_project_id": None,
            "project_name": project_name,
            "fiscal_year": fiscal_year,
            "research_unit": research_unit,
            "grouping_method": "project_name_fiscal_year_research_unit",
            "definition_status": "provisional_grouping_no_official_project_id",
            "project_status": "not_reported_by_source",
            "budget_status": "official_allocation_and_disbursement_not_available",
            "participant_record_count": len(participants),
            "business_count": len(businesses),
            "businesses": businesses,
            "geography": [
                {
                    "district": district,
                    "subdistricts": sorted(subdistricts),
                }
                for district, subdistricts in sorted(geography.items())
            ],
            "participants": [
                {
                    "record_id": item.get("record_id"),
                    "business_name": item.get("business_name"),
                    "district": item.get("district"),
                    "subdistrict": item.get("subdistrict"),
                    "source_url": item.get("source_url"),
                    "provenance": item.get("provenance"),
                }
                for item in participants
            ],
            "latest_source_update": max(updated_values, default=None),
            "source_url": next(
                (item.get("source_url") for item in participants if item.get("source_url")),
                None,
            ),
        })
    return sorted(
        projects,
        key=lambda item: (
            str(item.get("fiscal_year") or ""),
            str(item.get("project_name") or ""),
        ),
        reverse=True,
    )


def section_observation(sections: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """Return latest explicit as-of and fetch timestamps without inferring either."""

    as_of_values: list[str] = []
    fetched_values: list[str] = []
    for section in sections:
        candidates = list(section.get("items") or [])
        for key in (
            "assistance_trend",
            "assistance_dimensions_latest",
            "om_trend",
            "project_metrics_latest",
        ):
            candidates.extend(section.get(key) or [])
        if section.get("om_total"):
            candidates.append(section["om_total"])
        for item in candidates:
            provenance = item.get("provenance") or {}
            as_of = clean(item.get("as_of")) or clean(provenance.get("as_of"))
            fetched = clean(item.get("fetched_at")) or clean(provenance.get("fetched_at"))
            if as_of:
                as_of_values.append(str(as_of))
            if fetched:
                fetched_values.append(str(fetched))
    return max(as_of_values, default=None), max(fetched_values, default=None)


def compact_nested_provenance(row: dict[str, Any]) -> dict[str, Any]:
    provenance = row.get("provenance") or {}
    return {
        "endpoint_url": clean(provenance.get("endpoint_url")),
        "fetched_at": clean(provenance.get("fetched_at")),
        "as_of": clean(provenance.get("as_of")),
        "quality_status": clean(row.get("quality_status"))
        or clean(provenance.get("quality_status")),
        "definition_status": clean(row.get("definition_status"))
        or clean(provenance.get("definition_status")),
        "freshness_status": clean(provenance.get("freshness_status")),
        "record_hash": clean(provenance.get("content_hash")),
    }


def resolve_row_code(
    row: dict[str, Any], code_by_name: dict[str, str]
) -> str | None:
    candidates = (
        row.get("source_fields__cwt_id"),
        row.get("source_fields__province_id"),
        row.get("partition_key"),
    )
    for value in candidates:
        code = canonical_code(value)
        if code:
            return code
    names = (
        row.get("source_fields__cwt_dc"),
        row.get("source_fields__cwt_name"),
        row.get("source_fields__province_name"),
        row.get("source_fields__province_name_th"),
        row.get("source_fields__area_name"),
        row.get("partition_key"),
    )
    for value in names:
        code = code_by_name.get(normalize_text(value))
        if code:
            return code
    return None


def indicator(
    key: str,
    label_th: str,
    value: float,
    display_value: str,
    unit: str,
    source_url: str,
    source_id: str = "f3_housing_portal",
    note_th: str | None = None,
    calculation_th: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label_th": label_th,
        "value": value,
        "display_value": display_value,
        "unit": unit,
        "source_id": source_id,
        "source_url": source_url,
        "note_th": note_th,
        "calculation_th": calculation_th,
    }


def add_housing_signals(briefing: dict[str, Any]) -> None:
    groups = briefing["sections"]["housing"]["resource_groups"]
    by_id = {group["resource_id"]: group for group in groups}
    signals: list[dict[str, Any]] = []

    population = by_id.get("827aca76-9e90-43ed-86a2-cb9cb8651280")
    if population and population["rows"]:
        latest = max(population["rows"], key=lambda row: safe_float(row["values"].get("year")) or -1)
        value = safe_float(latest["values"].get("population"))
        year = latest["values"].get("year")
        if value is not None:
            signals.append(indicator(
                "population_latest", f"ประชากรในชุดข้อมูล ปี {year}", value,
                f"{value:,.0f}", "หน่วยตามต้นทาง", population["source_url"],
                note_th="ต้นทางยังไม่ระบุหน่วยใน resource metadata",
            ))

    simple_metrics = (
        (
            "197a5259-80a8-4c19-b90f-0bb9430d0037",
            "house_price_income_ratio",
            "อัตราส่วนราคาบ้านต่อรายได้",
            "house_price_income_ratio",
            "เท่า",
            lambda value: f"{value:.2f}",
        ),
        (
            "51b9cc37-cc96-4b33-900c-fa74408dcde0",
            "overcrowding_pct",
            "ที่อยู่อาศัยแออัด",
            "pct_overcrowded",
            "%",
            lambda value: f"{value:.2f}%",
        ),
        (
            "d9dd729e-3d23-445e-a126-4c7b69d7a578",
            "affordability_index",
            "ดัชนีความสามารถในการจ่ายที่อยู่อาศัย",
            "Mean",
            "ค่าดัชนีต้นทาง",
            lambda value: f"{value:.2f}",
        ),
    )
    for resource_id, key, label, field, unit, formatter in simple_metrics:
        group = by_id.get(resource_id)
        if not group or not group["rows"]:
            continue
        value = safe_float(group["rows"][0]["values"].get(field))
        if value is not None:
            signals.append(indicator(
                key, label, value, formatter(value), unit, group["source_url"],
                note_th="คงนิยามจากชื่อ field และ resource ของต้นทาง",
            ))

    loan = by_id.get("75436ffc-f88b-4092-a8c5-d1e4eec9c45f")
    if loan and loan["rows"]:
        share = safe_float(loan["rows"][0]["values"].get("share_loan_pass"))
        if share is not None:
            value = share * 100
            signals.append(indicator(
                "housing_loan_pass_share", "ผ่านเกณฑ์สินเชื่อที่อยู่อาศัย", value,
                f"{value:.2f}%", "%", loan["source_url"],
                calculation_th="share_loan_pass × 100",
            ))

    flood = by_id.get("7d51f36e-7072-4a2a-8067-4f10d97d5485")
    if flood and flood["rows"]:
        values = flood["rows"][0]["values"]
        level_4 = safe_float(values.get("risk_level_4_pct_area"))
        level_5 = safe_float(values.get("risk_level_5_pct_area"))
        if level_4 is not None and level_5 is not None:
            value = level_4 + level_5
            signals.append(indicator(
                "flood_risk_area_level_4_5", "พื้นที่เสี่ยงน้ำท่วมระดับ 4–5", value,
                f"{value:.2f}%", "% ของพื้นที่ตามต้นทาง", flood["source_url"],
                calculation_th="risk_level_4_pct_area + risk_level_5_pct_area",
            ))

    briefing["executive_signals"] = signals


def build() -> None:
    dashboard = read_json(PROJECT_ROOT / "data/public/public_dashboard.json")
    catalog = read_json(PROJECT_ROOT / "config/source_catalog.json")
    restricted_source_ids = sorted(
        source["source_id"]
        for source in catalog["sources"]
        if source.get("cloud_policy") == "restricted_local_only"
    )
    public_sources = {
        source["source_id"]: source
        for source in dashboard["sources"]
    }
    generated_at = datetime.now(timezone.utc).isoformat()
    code_by_name = {
        normalize_text(province["province_name_th"]): province["province_code"]
        for province in dashboard["provinces"]
    }
    briefings: dict[str, dict[str, Any]] = {}
    for province in dashboard["provinces"]:
        code = province["province_code"]
        briefings[code] = {
            "schema_version": "2.0.0",
            "generated_at": generated_at,
            "publication_status": "public_candidate_projection",
            "province": {
                "province_code": code,
                "province_name_th": province["province_name_th"],
                "province_name_en": province["province_name_en"],
                "region": province["region"],
                "centroid": province["centroid"],
            },
            "executive_signals": [],
            "sections": {
                "sra": {
                    **initial_section("f1_sradss_ppaos", "สถานการณ์และการดำเนินงาน SRA-DSS"),
                    "scope_status": "out_of_scope",
                    "scope_as_of": "2569",
                    "score_status": "out_of_scope",
                    "assistance_trend": [],
                    "assistance_dimensions_latest": [],
                    "om_total": None,
                    "om_trend": [],
                    "project_metrics_latest": [],
                    "quality_note_th": (
                        "aggregate สาธารณะสถานะ needs_review/definition provisional; "
                        "ไม่ใช่งบจัดสรรโครงการของจังหวัด"
                    ),
                },
                "learning_dashboard": initial_section(
                    "f2_learning_dashboard", "ภาพรวมธุรกิจชุมชนในกลุ่มผู้เข้าร่วมโครงการ"
                ),
                "area_based": initial_section(
                    "f2_learning_area_based",
                    "หน่วย/ผู้ประกอบการเข้าร่วม Area-Based",
                ),
                "project_master": {
                    **initial_section(
                        "f2_learning_area_based",
                        "กลุ่มโครงการจากทะเบียน Area-Based",
                    ),
                    "grouping_method": "project_name_fiscal_year_research_unit",
                    "definition_status": "provisional_grouping_no_official_project_id",
                },
                "innovation": initial_section("f2_apptech_mru", "นวัตกรรมพร้อมใช้ในพื้นที่"),
                "requirements": initial_section("f2_apptech_mru", "โจทย์หรือความต้องการจากพื้นที่"),
                "housing": {
                    **initial_section("f3_housing_portal", "ที่อยู่อาศัยและความเสี่ยงเมือง"),
                    "resource_groups": [],
                },
                "culture": initial_section("f2_culturalmap_university", "ทุนวัฒนธรรมในพื้นที่"),
                "tourism": initial_section("f3_ruamthiao_lamphun", "การเดินทางและท่องเที่ยวลำพูน"),
                "pppconnext": initial_section("f1_pppconnext", "ครัวเรือนและทุนดำรงชีพ"),
                "apptech_mtr": initial_section("f2_apptech_mtr", "การใช้งานแพลตฟอร์มนวัตกรรม"),
                "city_capital": initial_section("f3_city_capital_open_data", "ทุนเมืองระดับเทศบาล"),
            },
            "source_coverage": [],
            "quality": {
                "status": "candidate_needs_review",
                "note_th": "แสดงค่าตามต้นทางและ derivation ที่ระบุเท่านั้น ไม่สร้างคะแนนจัดสรรงบอัตโนมัติ",
                "restricted_source_ids_excluded": restricted_source_ids,
            },
        }

    # SRA-DSS: target scope and current score availability are distinct states.
    for row in csv_rows(SRA_REGISTRY_PATH):
        if str(row.get("as_of") or "").strip() != "2569":
            continue
        code = canonical_code(row.get("province_code"))
        if code not in briefings:
            continue
        section = briefings[code]["sections"]["sra"]
        section["scope_status"] = "in_scope"
        section["score_status"] = "in_scope_no_current_value"

    sra_path = BASE_RUN / "01_f1_sradss_ppaos/data/f1_sradss_ppaos_current_year_2569_indicator_rows.csv"
    for row in csv_rows(sra_path):
        code = canonical_code(row.get("province_code"))
        value = safe_float(row.get("value"))
        metric_key = clean(row.get("metric_key"))
        if code not in briefings or not metric_key:
            continue
        section = briefings[code]["sections"]["sra"]
        if value is None:
            continue
        section["items"].append({
            "metric_key": metric_key,
            "value": value,
            "unit": clean(row.get("unit")),
            "as_of": clean(row.get("as_of")),
            "snapshot_date": clean(row.get("snapshot_date")),
            "source_url": clean(row.get("source_endpoint")),
            "definition_status": clean(row.get("definition_status")),
        })
        if metric_key == "overall":
            section["score_status"] = "in_scope_value_available"

    sra_extended_paths = {
        "assistance_total": SRA_EXTENDED_ROOT / "assistance_total_rows.jsonl",
        "assistance_dimension": SRA_EXTENDED_ROOT / "assistance_dimension_rows.jsonl",
        "om_total": SRA_EXTENDED_ROOT / "om_total_rows.jsonl",
        "om_year": SRA_EXTENDED_ROOT / "om_year_rows.jsonl",
        "project_metric": SRA_EXTENDED_ROOT / "project_metric_rows.jsonl",
    }
    for row in jsonl_rows(sra_extended_paths["assistance_total"]):
        code = canonical_code(row.get("scope_key"))
        if row.get("scope_type") != "province" or code not in briefings:
            continue
        briefings[code]["sections"]["sra"]["assistance_trend"].append({
            "year": clean(row.get("year")),
            "households": safe_float(row.get("total_households")),
            "episodes": safe_float(row.get("total_episodes")),
            "budget_baht": safe_float(row.get("total_budget_baht")),
            "as_of": clean(row.get("year")),
            "provenance": compact_nested_provenance(row),
        })
    for row in jsonl_rows(sra_extended_paths["assistance_dimension"]):
        code = canonical_code(row.get("scope_key"))
        if (
            row.get("scope_type") != "province"
            or str(row.get("year") or "") != "2569"
            or code not in briefings
        ):
            continue
        briefings[code]["sections"]["sra"]["assistance_dimensions_latest"].append({
            "year": "2569",
            "dimension_key": clean(row.get("dimension_key")),
            "dimension_title": clean(row.get("dimension_title")),
            "households": safe_float(row.get("households")),
            "episodes": safe_float(row.get("episode_count")),
            "budget_baht": safe_float(row.get("budget_baht")),
            "household_share_pct": safe_float(row.get("share_pct")),
            "budget_share_pct": safe_float(row.get("budget_share_pct")),
            "as_of": "2569",
            "provenance": compact_nested_provenance(row),
        })
    for row in jsonl_rows(sra_extended_paths["om_total"]):
        code = canonical_code(row.get("scope_key"))
        if row.get("scope_type") != "province" or code not in briefings:
            continue
        briefings[code]["sections"]["sra"]["om_total"] = {
            "om_count": safe_float(row.get("total_om")),
            "chain_count": safe_float(row.get("total_chain")),
            "capital_baht": safe_float(row.get("total_capital_baht")),
            "as_of": None,
            "provenance": compact_nested_provenance(row),
        }
    for row in jsonl_rows(sra_extended_paths["om_year"]):
        code = canonical_code(row.get("scope_key"))
        if row.get("scope_type") != "province" or code not in briefings:
            continue
        briefings[code]["sections"]["sra"]["om_trend"].append({
            "year": clean(row.get("year")),
            "om_count": safe_float(row.get("om_count")),
            "chain_count": safe_float(row.get("chain_count")),
            "capital_baht": safe_float(row.get("capital_baht")),
            "as_of": None,
            "provenance": compact_nested_provenance(row),
        })
    for row in jsonl_rows(sra_extended_paths["project_metric"]):
        code = canonical_code(row.get("scope_key"))
        if (
            row.get("scope_type") != "province"
            or str(row.get("year") or "") != "2569"
            or code not in briefings
        ):
            continue
        briefings[code]["sections"]["sra"]["project_metrics_latest"].append({
            "year": "2569",
            "metric_key": clean(row.get("metric_key")),
            "metric_label": clean(row.get("metric_label")),
            "metric_group": clean(row.get("metric_group")),
            "unit": clean(row.get("unit")),
            "value": safe_float(row.get("value")),
            "target_value": safe_float(row.get("target_value")),
            "target_pct": safe_float(row.get("target_pct")),
            "data_model": clean(row.get("data_model")),
            "as_of": "2569",
            "provenance": compact_nested_provenance(row),
        })

    # Area-Based: keep every participant record attached to a province.
    area_path = BASE_RUN / "11_f2_learning_area_based/data.csv"
    area_unmapped: list[dict[str, Any]] = []
    for row in csv_rows(area_path):
        code = code_by_name.get(normalize_text(row.get("source_fields__province")))
        item = {
            "record_id": clean(row.get("source_fields__id")),
            "project_name": clean(row.get("source_fields__projectName")),
            "fiscal_year": clean(row.get("source_fields__fiscalYear")),
            "research_unit": clean(row.get("source_fields__researchUnit")),
            "business_name": clean(row.get("source_fields__businessName")),
            "district": clean(row.get("source_fields__district")),
            "subdistrict": clean(row.get("source_fields__subDistrict")),
            "updated_at": clean(row.get("source_fields__updatedAt")),
            "source_url": clean(row.get("source_endpoint")),
            "provenance": compact_provenance(row),
        }
        if code not in briefings:
            source_province = clean(row.get("source_fields__province"))
            area_unmapped.append(
                {
                    "reason": (
                        "source_province_missing"
                        if source_province is None
                        else "province_name_not_in_exact_crosswalk"
                    ),
                    "source_province": source_province,
                    "record": item,
                }
            )
            continue
        briefings[code]["sections"]["area_based"]["items"].append(item)

    for briefing in briefings.values():
        participant_items = briefing["sections"]["area_based"]["items"]
        briefing["sections"]["project_master"]["items"] = (
            provisional_project_groups(participant_items)
        )

    # AppTech MRU: use the richer validated Silver projection, while the list is refreshed by API.
    innovation_path = (
        STAGED_ROOT
        / "f2_apptech_mru/20260805T_apptech_mru_silver_02/silver/apptech_mru_public_innovation.jsonl"
    )
    for row in jsonl_rows(innovation_path):
        fields = row.get("normalized_fields") or {}
        codes = {
            code_by_name.get(normalize_text(area.get("province")))
            for area in fields.get("areas") or []
        }
        for code in codes - {None}:
            if code not in briefings:
                continue
            provenance = row.get("provenance") or {}
            briefings[code]["sections"]["innovation"]["items"].append({
                "record_id": fields.get("record_id") or row.get("record_id"),
                "title": fields.get("title"),
                "owner_affiliation_name": fields.get("owner_affiliation_name"),
                "description": fields.get("description"),
                "knowledge_technology": fields.get("knowledge_technology"),
                "innovation_type": fields.get("innovation_type_label"),
                "category": fields.get("category_label"),
                "trl_level": fields.get("trl_level"),
                "srl_level": fields.get("srl_level"),
                "innovation_value_baht": fields.get("innovation_value_baht"),
                "funding": fields.get("funding") or [],
                "roi_indicator": fields.get("roi_indicator"),
                "roi_unit": fields.get("roi_unit"),
                "sroi_indicator": fields.get("sroi_indicator"),
                "sroi_unit": fields.get("sroi_unit"),
                "target_groups": fields.get("target_groups") or [],
                "highlights": fields.get("highlights") or [],
                "research_leads": [
                    {
                        "name": clean(researcher.get("name")),
                        "faculty": clean(researcher.get("faculty")),
                        "institute": clean(researcher.get("institute")),
                    }
                    for researcher in (fields.get("principal_researchers") or [])
                ],
                "co_researcher_count": len(fields.get("co_researchers") or []),
                "ip": {
                    "type": clean(fields.get("ip_type")),
                    "rights_owner": clean(fields.get("ip_rights_owner")),
                    "asset_name": clean(fields.get("ip_asset_name")),
                    "application_number": clean(fields.get("ip_application_number")),
                    "patent_number": clean(fields.get("ip_patent_number")),
                },
                "views_count": safe_float(fields.get("views_count")),
                "areas": fields.get("areas") or [],
                "linked_province_count": len({
                    normalize_text(area.get("province"))
                    for area in fields.get("areas") or []
                    if normalize_text(area.get("province"))
                }),
                "source_url": provenance.get("detail_url") or provenance.get("endpoint_url"),
                "fetched_at": provenance.get("fetched_at"),
            })

    requirement_unmapped: list[dict[str, Any]] = []
    for row in jsonl_rows(REQUIREMENT_PATH):
        codes, item, unmatched_names = project_requirement_record(row, code_by_name)
        for code in codes:
            if code in briefings:
                briefings[code]["sections"]["requirements"]["items"].append(item)
        if not codes or unmatched_names:
            requirement_unmapped.append({
                "reason": (
                    "province_name_not_in_exact_crosswalk"
                    if unmatched_names
                    else "source_province_missing"
                ),
                "source_provinces": unmatched_names,
                "record": item,
            })

    # Cultural Map: all province records, including records without coordinates.
    cultural_path = MERGE_RUN / "03_f2_culturalmap_university/data/map_inspiration.json"
    cultural_root = read_json(cultural_path)
    for row in cultural_root["data"]["records"]:
        code, item = project_cultural_record(row, cultural_path)
        if code not in briefings:
            continue
        briefings[code]["sections"]["culture"]["items"].append(item)

    # Housing: every approved flattened record, grouped by CKAN resource.
    housing_metadata_path = (
        STAGED_ROOT
        / "f3_housing_portal/20260803T_housing_silver_02/resource_inventory.json"
    )
    housing_metadata = {
        item["resource_id"]: item
        for item in read_json(housing_metadata_path)["resources"]
    }
    grouped_rows: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    housing_unmapped: list[dict[str, Any]] = []
    housing_total_records = 0
    valid_province_codes = set(briefings)
    housing_dir = BASE_RUN / "23_f3_housing_portal/data"
    housing_paths = sorted(housing_dir.glob("*.csv"))
    for path in housing_paths:
        for row in csv_rows(path):
            housing_total_records += 1
            code = resolve_row_code(row, code_by_name)
            if code not in briefings:
                resource_id = row.get("resource_id") or row.get("dataset_id", "").rsplit(":", 1)[-1]
                housing_unmapped.append(
                    project_unmapped_housing_record(
                        row,
                        housing_metadata.get(resource_id, {}),
                        code,
                        valid_province_codes,
                    )
                )
                continue
            resource_id = row.get("resource_id") or row.get("dataset_id", "").rsplit(":", 1)[-1]
            grouped_rows[code][resource_id].append({
                "row_number": clean(row.get("row_number")) or clean(row.get("source_record_id")),
                "values": source_fields(row),
                "provenance": compact_provenance(row),
            })
    for code, resources in grouped_rows.items():
        groups = []
        for resource_id, rows in resources.items():
            metadata = housing_metadata.get(resource_id, {})
            sample = rows[0] if rows else {"provenance": {}}
            groups.append({
                "dataset_key": metadata.get("dataset_key"),
                "dataset_title": metadata.get("dataset_title"),
                "resource_id": resource_id,
                "resource_name": metadata.get("resource_name") or resource_id,
                "source_url": metadata.get("resource_url") or sample["provenance"].get("endpoint_url"),
                "resource_metadata_modified": metadata.get("resource_metadata_modified"),
                "definition_status": metadata.get("status") or "needs_review",
                "field_names": sorted({key for item in rows for key in item["values"]}),
                "row_count": len(rows),
                "rows": rows,
            })
        groups.sort(key=lambda item: (item["dataset_key"] or "", item["resource_name"] or ""))
        briefings[code]["sections"]["housing"]["resource_groups"] = groups
        briefings[code]["sections"]["housing"]["items"] = []
    housing_mapped_records = sum(
        len(rows)
        for resources in grouped_rows.values()
        for rows in resources.values()
    )
    if housing_mapped_records + len(housing_unmapped) != housing_total_records:
        raise RuntimeError("housing projection reconciliation failed")

    # Ruam Thiao is explicitly Lamphun-scoped in its source definition.
    tourism_files = sorted((MERGE_RUN / "16_f3_ruamthiao_lamphun/data").glob("*.json"))
    if "51" in briefings:
        briefings["51"]["sections"]["tourism"]["items"] = [
            project_tourism_payload(payload)
            for payload in (read_json(path) for path in tourism_files)
        ]

    # Audited cross-source geography links. Each source retains its original grain.
    source_insights = read_json(SOURCE_INSIGHTS_PATH)
    city_source = source_insights["sources"]["f3_city_capital_open_data"]
    city_metrics = {
        metric["metric_id"]: metric
        for group in city_source["groups"]
        for metric in group["metrics"]
    }
    for code, briefing in briefings.items():
        links = source_insights["province_links"].get(code, {})
        briefing["sections"]["pppconnext"]["items"] = links.get("f1_pppconnext") or []

        learning = links.get("f2_learning_dashboard")
        if learning:
            briefing["sections"]["learning_dashboard"]["items"] = [learning]

        apptech = links.get("f2_apptech_mtr")
        if apptech:
            briefing["sections"]["apptech_mtr"]["items"] = [apptech]

        city_items = []
        for city in links.get("f3_city_capital_open_data") or []:
            signals = []
            for metric_id, value in city.get("values", {}).items():
                metric = city_metrics.get(metric_id)
                middle = safe_float((metric or {}).get("median"))
                number = safe_float(value)
                direction = (metric or {}).get("concern_direction")
                if number is None or middle in (None, 0) or direction not in {"high", "low"}:
                    continue
                gap = (number - middle) / abs(middle)
                attention = gap > 0.10 if direction == "high" else gap < -0.10
                if not attention:
                    continue
                low = safe_float(metric.get("minimum"))
                high = safe_float(metric.get("maximum"))
                span = (high - low) if low is not None and high is not None else 0
                signals.append({
                    "key": metric_id,
                    "label_th": metric.get("label_th"),
                    "value": number,
                    "display_value": f"{number:,.1f}",
                    "unit": metric.get("display_unit"),
                    "comparison": "above" if gap > 0 else "below",
                    "comparison_th": "สูงกว่าค่ากลางของ 18 เมือง" if gap > 0 else "ต่ำกว่าค่ากลางของ 18 เมือง",
                    "benchmark_label_th": "ค่ากลาง 18 เมือง",
                    "benchmark_value": middle,
                    "benchmark_display_value": f"{middle:,.1f}",
                    "position_pct": round((number - low) / span * 100, 1) if span else 50,
                    "benchmark_position_pct": round((middle - low) / span * 100, 1) if span else 50,
                    "attention": True,
                    "attention_strength": round(abs(gap), 4),
                    "source_id": "f3_city_capital_open_data",
                    "source_url": city_source["source_url"],
                })
            signals.sort(key=lambda item: item["attention_strength"], reverse=True)
            city_items.append({**city, "signals": signals})
        briefing["sections"]["city_capital"]["items"] = city_items

    not_province_scoped = {
        "f2_rmutdb": "ทะเบียนไม่มี field จังหวัดที่ยืนยันแล้ว",
    }
    source_sections = {
        "f1_sradss_ppaos": ("sra",),
        "f2_learning_dashboard": ("learning_dashboard",),
        "f2_culturalmap_university": ("culture",),
        "f2_apptech_mru": ("innovation", "requirements"),
        "f2_learning_area_based": ("area_based",),
        "f3_housing_portal": ("housing",),
        "f3_ruamthiao_lamphun": ("tourism",),
        "f1_pppconnext": ("pppconnext",),
        "f2_apptech_mtr": ("apptech_mtr",),
        "f3_city_capital_open_data": ("city_capital",),
    }

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    written_files: list[Path] = []
    for code, briefing in briefings.items():
        for section_id, section in briefing["sections"].items():
            if section["source_id"] == "f3_housing_portal":
                total = sum(group["row_count"] for group in section["resource_groups"])
            elif section_id == "sra":
                total = (
                    len(section["items"])
                    + len(section["assistance_trend"])
                    + len(section["assistance_dimensions_latest"])
                    + len(section["om_trend"])
                    + len(section["project_metrics_latest"])
                    + (1 if section.get("om_total") else 0)
                )
            else:
                total = len(section["items"])
            section["total_records"] = total
            section["status"] = "available" if total else "source_has_no_record_for_province"
            if section_id == "sra" and section["scope_status"] == "in_scope" and not section["items"]:
                section["score_status"] = "in_scope_no_current_value"

        add_housing_signals(briefing)
        coverage = []
        for source_id, source in public_sources.items():
            item = source_meta(source)
            section_objects = [
                briefing["sections"][section_id]
                for section_id in source_sections.get(source_id, ())
            ]
            observed_as_of, observed_fetched_at = section_observation(section_objects)
            item.update({
                "data_grain_th": SOURCE_GRAIN_TH.get(source_id, "ไม่ระบุ grain"),
                "observed_as_of": observed_as_of,
                "observed_fetched_at": observed_fetched_at,
            })
            if source_id in not_province_scoped:
                item.update({
                    "status": "not_province_scoped",
                    "records": None,
                    "note_th": not_province_scoped[source_id],
                })
            else:
                record_breakdown = {
                    section_id: briefing["sections"][section_id]["total_records"]
                    for section_id in source_sections.get(source_id, ())
                }
                records = sum(record_breakdown.values())
                item.update({
                    "status": "available" if records else "source_has_no_record_for_province",
                    "records": records,
                    "note_th": (
                        "innovation และ requirements เป็นคนละ grain; แสดงแยกใน record_breakdown"
                        if source_id == "f2_apptech_mru"
                        else (
                            "นับ participant records; จำนวนโครงการเป็นการจัดกลุ่มเบื้องต้นจากชื่อ+ปี+หน่วยวิจัย"
                            if source_id == "f2_learning_area_based"
                            else (
                                "อยู่ในขอบเขตจังหวัดเป้าหมาย แต่คะแนนปี 2569 เป็นค่าว่าง; aggregate ชุดอื่นยังแสดงแบบ candidate"
                                if source_id == "f1_sradss_ppaos"
                                and briefing["sections"]["sra"]["score_status"]
                                == "in_scope_no_current_value"
                                else None
                            )
                        )
                    ),
                })
                if source_id == "f2_apptech_mru":
                    item["record_breakdown"] = record_breakdown
                elif source_id == "f2_learning_area_based":
                    item["record_breakdown"] = {
                        "participant_records": briefing["sections"]["area_based"]["total_records"],
                        "provisional_project_groups": briefing["sections"]["project_master"]["total_records"],
                    }
            coverage.append(item)
        briefing["source_coverage"] = sorted(coverage, key=lambda item: public_sources[item["source_id"]]["ordinal"])
        briefing["available_source_ids"] = [
            item["source_id"] for item in briefing["source_coverage"] if item["status"] == "available"
        ]
        output_path = OUTPUT_ROOT / f"{code}.json"
        write_json(output_path, briefing)
        written_files.append(output_path)

    input_paths = [
        PROJECT_ROOT / "config/source_catalog.json",
        PROJECT_ROOT / "data/public/public_dashboard.json",
        SRA_REGISTRY_PATH,
        sra_path,
        *sra_extended_paths.values(),
        area_path,
        innovation_path,
        REQUIREMENT_PATH,
        cultural_path,
        housing_metadata_path,
        *housing_paths,
        *tourism_files,
        SOURCE_INSIGHTS_PATH,
        PROJECT_ROOT / "data/public/source_insights_manifest.json",
        LEARNING_PATH,
        LEARNING_MANIFEST_PATH,
    ]
    learning_unmatched = source_insights["sources"]["f2_learning_dashboard"].get(
        "unmatched_province_rows", []
    )
    unmapped_payload = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "publication_status": "public_candidate_projection",
        "total_records": (
            len(area_unmapped)
            + len(learning_unmatched)
            + len(requirement_unmapped)
            + len(housing_unmapped)
        ),
        "sources": {
            "f2_learning_area_based": {
                "record_count": len(area_unmapped),
                "items": area_unmapped,
            },
            "f2_learning_dashboard": {
                "record_count": len(learning_unmatched),
                "items": learning_unmatched,
            },
            "f2_apptech_mru": {
                "dataset": "public_requirement",
                "record_count": len(requirement_unmapped),
                "items": requirement_unmapped,
            },
            "f3_housing_portal": {
                "record_count": len(housing_unmapped),
                "approved_projection_records": housing_total_records,
                "province_linked_records": housing_mapped_records,
                "reason_counts": dict(sorted(Counter(
                    item["reason"] for item in housing_unmapped
                ).items())),
                "items": housing_unmapped,
            },
        },
        "methodology_th": "เก็บรายการที่จับคู่จังหวัดไม่ได้โดยไม่เดาหรือเติมค่าพื้นที่",
    }
    write_json(UNMAPPED_PATH, unmapped_payload)
    index = {
        "schema_version": "2.0.0",
        "generated_at": generated_at,
        "province_count": len(briefings),
        "source_count": len(public_sources),
        "inputs": [manifest_entry(path) for path in input_paths],
        "unmapped": manifest_entry(UNMAPPED_PATH),
        "files": [
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sorted(written_files)
        ],
    }
    write_json(OUTPUT_ROOT / "index.json", index)
    print(json.dumps({"status": "ok", **index}, ensure_ascii=False))


if __name__ == "__main__":
    build()
