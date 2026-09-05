#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(
    os.environ.get("AIAT_EVIDENCE_ROOT", str(DASHBOARD_ROOT.parent))
).expanduser().resolve()
REGISTRY_PATH = PROJECT_ROOT / "config/source_registry.json"
AUDIT_ROOT = PROJECT_ROOT / "data/source_audit"
DEFAULT_MERGED = PROJECT_ROOT / "data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01"
LEARNING_DASHBOARD_OBSERVATION = (
    PROJECT_ROOT
    / "data/raw/network/f2_learning_dashboard/20260803T_network/observation.json"
)
PPPCONNEXT_2026_OBSERVATION = (
    PROJECT_ROOT
    / "data/raw/network/f1_pppconnext/20260817T_public_api_fetch_02/network_observation.json"
)
PPPCONNEXT_2026_RECORD_COUNT = 47
TARGET_HOUSEHOLD_OBSERVATION = (
    PROJECT_ROOT
    / "data/raw/network/f2_target_household/20260818T163000Z_pmua_apptech_catalogue_01/observation.json"
)
TARGET_HOUSEHOLD_SEARCH_URL = "https://pmua-apptech.com/search"
TARGET_PUBLIC_PRODUCT_LISTING_COUNT = 1160
WALLET_ALL_CURRENT_MONTH_RECORDS = 2
WALLET_CLUSTER_CURRENT_MONTH_RECORDS = 14
APPTECH_CURRENT_MANIFEST = (
    PROJECT_ROOT
    / "data/staged/f2_apptech_mtr/20260817T_public_api_silver_07/manifest.json"
)
APPTECH_CURRENT_RECORDS = (
    PROJECT_ROOT
    / "data/staged/f2_apptech_mtr/20260817T_public_api_silver_07/silver/apptech_public_innovation.jsonl"
)
APPTECH_CURRENT_OBSERVATION = (
    PROJECT_ROOT
    / "data/raw/network/f2_apptech_mtr/20260817T_public_api_completeness_07/api_probe_observation.json"
)
INGESTION_PLANS_PATH = DASHBOARD_ROOT / "config/ingestion_plans.json"

# Publication permission is deliberately separate from semantic acceptance. Every
# source in this map remains candidate/needs_review until its fact gates pass.
APPROVED_PUBLIC_MODES = {
    "f1_sradss_ppaos": "api_first",
    "f1_pppconnext": "api_first",
    "f2_culturalmap_university": "snapshot_only",
    "f2_rmutdb": "snapshot_only",
    "f2_apptech_mtr": "api_first",
    "f2_apptech_mru": "api_first",
    "f2_target_household": "api_first",
    "f2_learning_dashboard": "api_first",
    "f2_learning_area_based": "api_first",
    "f2_wallet_all_realtime": "api_first",
    "f2_wallet_cluster_realtime": "api_first",
    "f3_city_capital_open_data": "snapshot_only",
    "f3_ruamthiao_lamphun": "snapshot_only",
    "f3_housing_portal": "api_first",
    "spu_sukhothai_care": "api_first",
    "spu_sukhothai_water": "api_first",
    "spu_nsn_flood": "api_first",
    "spu_rawangphai_uru": "api_first",
    "clig_projects": "api_first",
    "f4_pmua_product_details": "api_first",
}

SPU_DISASTER_SOURCE_IDS = frozenset(
    {
        "spu_sukhothai_care",
        "spu_sukhothai_water",
        "spu_nsn_flood",
        "spu_rawangphai_uru",
    }
)

# These lanes remain local-only. Public AppTech product search and Super App
# open-data wallet aggregates are not in this set: the live pages publish those
# surfaces without login. Nonthaburi health/learning stay restricted.
RESTRICTED_SOURCE_IDS = frozenset(
    {
        "f3_nonthaburi_city_learning",
        "f3_healthcare_nonthaburi",
    }
)

# The PMUA payload contains a header/label row plus 66 province rows. This count
# must not be replaced with the sum of unrelated lookup arrays in the payload.
LEARNING_DASHBOARD_PROVINCE_ROWS = 66


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def endpoint_id(source_id: str, method: str, url: str, action: str) -> str:
    value = f"{source_id}|{method}|{url}|{action}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def provenance_path(
    path: Path,
    *,
    evidence_root: Path = PROJECT_ROOT,
    dashboard_root: Path = DASHBOARD_ROOT,
) -> str:
    """Return a stable path without assuming the repo lives under the evidence root."""
    resolved = path.expanduser().resolve()
    dashboard_root = dashboard_root.expanduser().resolve()
    evidence_root = evidence_root.expanduser().resolve()
    try:
        relative = resolved.relative_to(dashboard_root)
    except ValueError:
        try:
            return resolved.relative_to(evidence_root).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"provenance input is outside the dashboard and evidence roots: {resolved}"
            ) from exc
    return (Path("dashboard_final") / relative).as_posix()


def as_project_path(path_text: str, merged_root: Path) -> Path:
    path = Path(path_text.replace("\\", "/"))
    if path.is_absolute():
        return path
    project_candidate = PROJECT_ROOT / path
    if project_candidate.exists():
        return project_candidate
    return merged_root / path


def source_card_path(ordinal: int, source_id: str) -> Path:
    return AUDIT_ROOT / f"{ordinal:02d}_{source_id}" / "source_card.json"


def load_plan_endpoints(source_id: str, plan: dict, cloud_policy: str, acquisition_mode: str) -> list[dict]:
    """Load source-owned endpoint metadata without source-specific generator branches."""
    endpoints = []
    for declared in plan.get("catalog_endpoints", []):
        method = declared.get("method", "GET").upper()
        url = declared.get("url") or plan[declared["url_key"]]
        action = declared["team_action"]
        access = declared["access"]
        restricted = is_restricted(cloud_policy, access, action)
        endpoints.append({
            "endpoint_id": endpoint_id(source_id, method, url, action),
            "method": method, "url": url, "kind": declared["kind"],
            "access": access, "team_action": action,
            "restricted": restricted,
            "runtime_enabled": acquisition_mode == "api_first" and action == "call_without_login" and not restricted,
            "request_template": declared.get("request_template", {}),
            **({"path_template": declared["path_template"], "path_parameters": declared["path_parameters"]}
               if "path_template" in declared else {}),
            "notes_th": declared.get("notes_th", ""),
        })
    return endpoints


def is_restricted(cloud_policy: str, access: str, action: str) -> bool:
    action_value = action.lower()
    access_value = access.lower()
    return (
        cloud_policy == "restricted_local_only"
        or action_value.startswith("do_not_call")
        or "auth_401" in access_value
        or "http_401" in access_value
        or "http_403" in access_value
        or "needs_auth" in access_value
        or "requires_auth" in access_value
        or "login" in access_value
        or "error" in access_value
    )


def load_endpoints(
    source_id: str,
    cloud_policy: str,
    acquisition_mode: str,
    data_location: Path,
) -> list[dict]:
    endpoints_path = data_location / "endpoints.csv"
    if not endpoints_path.exists():
        return []
    endpoint_rows = list(csv.DictReader(endpoints_path.open(encoding="utf-8-sig", newline="")))
    endpoints: list[dict] = []
    for endpoint in endpoint_rows:
        method = endpoint.get("method", "GET").upper()
        url = endpoint.get("url", "")
        action = endpoint.get("team_action", "")
        access = endpoint.get("access", "")
        restricted = is_restricted(cloud_policy, access, action)
        endpoints.append(
            {
                "endpoint_id": endpoint_id(source_id, method, url, action),
                "method": method,
                "url": url,
                "kind": endpoint.get("kind") or endpoint.get("dataset", ""),
                "access": access,
                "team_action": action,
                "restricted": restricted,
                "runtime_enabled": (
                    acquisition_mode == "api_first"
                    and action == "call_without_login"
                    and not restricted
                ),
                "request_template": {"query_or_body": endpoint.get("query_or_body", "")},
                "notes_th": endpoint.get("notes") or endpoint.get("notes_th", ""),
            }
        )
    return endpoints


def apply_runtime_request_templates(
    source_id: str,
    endpoints: list[dict],
    plan: dict | None,
) -> list[dict]:
    """Bind executable query/body shapes to the reviewed runtime endpoint catalog."""

    def render_dynamic_values(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): render_dynamic_values(item) for key, item in value.items()}
        if isinstance(value, list):
            return [render_dynamic_values(item) for item in value]
        if isinstance(value, str) and value.startswith("$"):
            return "<value>"
        return value

    request_templates: dict[tuple[str, str], dict[str, Any]] = {}
    requests = list((plan or {}).get("requests", []))
    if (plan or {}).get("url"):
        top_level_request: dict[str, Any] = {
            "method": (plan or {}).get("method", "GET"),
            "url": (plan or {})["url"],
        }
        if (plan or {}).get("query_params"):
            top_level_request["params"] = (plan or {})["query_params"]
        if (
            str(top_level_request["method"]).upper() != "GET"
            and (plan or {}).get("body_mode") == "json_empty"
        ):
            top_level_request["json_body"] = {}
        requests.append(top_level_request)
    if (plan or {}).get("package_show_url"):
        for dataset in (plan or {}).get("datasets", []):
            if isinstance(dataset, dict) and dataset.get("id"):
                requests.append(
                    {
                        "method": "GET",
                        "url": f"{(plan or {})['package_show_url']}?{urlencode({'id': dataset['id']})}",
                    }
                )
    for dataset in (plan or {}).get("datasets", []):
        if not isinstance(dataset, dict) or not dataset.get("url"):
            continue
        if "json_body" in dataset:
            requests.append(
                {
                    "method": dataset.get("method", "POST"),
                    "url": dataset["url"],
                    "json_body": dataset["json_body"],
                }
            )
        elif "form_body" in dataset:
            requests.append(
                {
                    "method": dataset.get("method", "POST"),
                    "url": dataset["url"],
                    "form_body": dataset["form_body"],
                }
            )
    for request in requests:
        params = request.get("params") or {}
        has_json_body = "json_body" in request
        has_form_body = "form_body" in request
        method = str(request.get("method", "GET")).upper()
        template: dict[str, Any] = {}
        if params:
            pairs = [
                (
                    str(key),
                    "<value>" if str(value).startswith("$") else str(value),
                )
                for key, value in params.items()
            ]
            query_template = urlencode(pairs).replace("%3Cvalue%3E", "<value>")
            template["query_or_body" if method == "GET" else "query"] = query_template
        if has_json_body:
            template["json_body"] = render_dynamic_values(request["json_body"])
        if has_form_body:
            template["form_body"] = render_dynamic_values(request["form_body"])
        request_templates[(method, str(request["url"]))] = template

    unmatched = set(request_templates)
    for endpoint in endpoints:
        key = (str(endpoint.get("method", "GET")).upper(), str(endpoint.get("url", "")))
        template = request_templates.get(key)
        if template is None:
            continue
        if endpoint.get("runtime_enabled") is not True:
            raise RuntimeError(
                f"{source_id}: executable request is not runtime-enabled: {key[0]} {key[1]}"
            )
        endpoint["request_template"] = {
            **(endpoint.get("request_template") or {}),
            **template,
        }
        unmatched.discard(key)
    if unmatched:
        missing = ", ".join(f"{method} {url}" for method, url in sorted(unmatched))
        raise RuntimeError(
            f"{source_id}: ingestion plan requests are missing from the endpoint catalog: {missing}"
        )

    excluded_urls = set((plan or {}).get("runtime_excluded_urls", []))
    seen_excluded: set[str] = set()
    for endpoint in endpoints:
        url = str(endpoint.get("url", ""))
        if url not in excluded_urls:
            continue
        endpoint["runtime_enabled"] = False
        endpoint["team_action"] = "do_not_call_publication_policy"
        endpoint["endpoint_id"] = endpoint_id(
            source_id,
            str(endpoint.get("method", "GET")),
            url,
            endpoint["team_action"],
        )
        endpoint["notes_th"] = (
            f"{endpoint.get('notes_th', '').strip()} — runtime blocked by ingestion publication policy"
        ).strip(" —")
        seen_excluded.add(url)
    missing_exclusions = excluded_urls - seen_excluded
    if missing_exclusions:
        raise RuntimeError(
            f"{source_id}: runtime_excluded_urls missing from endpoint catalog: "
            + ", ".join(sorted(missing_exclusions))
        )

    if (plan or {}).get("expected_resource_count"):
        resource_endpoints = [
            endpoint
            for endpoint in endpoints
            if endpoint.get("kind") == "ckan_resource_download"
        ]
        expected_resources = int((plan or {})["expected_resource_count"])
        if len(resource_endpoints) != expected_resources:
            raise RuntimeError(
                f"{source_id}: catalog has {len(resource_endpoints)} CKAN resource endpoints; "
                f"plan expects {expected_resources}"
            )
        expected_value_resources = int((plan or {}).get("expected_value_resource_count") or 0)
        enabled_resources = [
            endpoint for endpoint in resource_endpoints if endpoint.get("runtime_enabled") is True
        ]
        if expected_value_resources and len(enabled_resources) != expected_value_resources:
            raise RuntimeError(
                f"{source_id}: catalog has {len(enabled_resources)} runtime-enabled CKAN resources; "
                f"plan expects {expected_value_resources}"
            )
    return endpoints


def load_snapshot_files(data_location: Path) -> list[str]:
    if not data_location.exists():
        return []
    return sorted(
        provenance_path(path)
        for path in data_location.rglob("*")
        if path.is_file()
        and (path.name == "data.csv" or "data" in path.relative_to(data_location).parts[:-1])
        and (
            path.suffix.lower() in {".csv", ".json", ".jsonl"}
            or path.name.lower().endswith((".csv.gz", ".jsonl.gz"))
        )
        and "metadata" not in path.parts
    )


def load_learning_dashboard_endpoint(acquisition_mode: str) -> list[dict]:
    observation = read_json(LEARNING_DASHBOARD_OBSERVATION)
    network = observation["network"]
    method = network["method_observed"].upper()
    url = network["endpoint"]
    if method != "POST" or network.get("status") != 200 or network.get("get_probe_status") != 405:
        raise RuntimeError("Learning dashboard endpoint evidence no longer matches POST 200 / GET 405")
    action = "call_without_login"
    return [
        {
            "endpoint_id": endpoint_id("f2_learning_dashboard", method, url, action),
            "method": method,
            "url": url,
            "kind": "public_aggregate_dashboard",
            "access": "unauthenticated_post_http_200",
            "team_action": action,
            "restricted": False,
            "runtime_enabled": acquisition_mode == "api_first",
            "request_template": {"json": network.get("request_body_probe", {})},
            "notes_th": (
                "POST empty JSON body verified HTTP 200; GET returned 405. "
                "Payload is text/plain JSON and selected-project scope remains needs_review."
            ),
        }
    ]


def load_pppconnext_2026_endpoints(acquisition_mode: str) -> list[dict]:
    observation = read_json(PPPCONNEXT_2026_OBSERVATION)
    endpoints: list[dict] = []
    for row in observation["observations"]:
        if row.get("http_status") != 200 or row.get("auth_boundary_observed"):
            raise RuntimeError("PPPConnext public API evidence is no longer unauthenticated HTTP 200")
        action = "call_without_login"
        endpoints.append({
            "endpoint_id": endpoint_id("f1_pppconnext", "GET", row["url"], action),
            "method": "GET",
            "url": row["url"],
            "kind": "public_aggregate_dashboard",
            "access": "unauthenticated_get_http_200",
            "team_action": action,
            "restricted": False,
            "runtime_enabled": acquisition_mode == "api_first",
            "request_template": {"query_or_body": row["url"].partition("?")[2]},
            "notes_th": "Observed from the public 2026 dashboard; aggregate only and no cookies used.",
        })
    return endpoints


def load_target_household_search_endpoint(acquisition_mode: str) -> list[dict]:
    url = TARGET_HOUSEHOLD_SEARCH_URL
    if TARGET_HOUSEHOLD_OBSERVATION.exists():
        observation = read_json(TARGET_HOUSEHOLD_OBSERVATION)
        observed_url = observation.get("public_surface", {}).get("search_url")
        if observed_url != url:
            raise RuntimeError("PMUA AppTech public search URL evidence no longer matches /search")
    action = "call_without_login"
    endpoints = [
        {
            "endpoint_id": endpoint_id("f2_target_household", "GET", url, action),
            "method": "GET",
            "url": url,
            "kind": "public_product_search",
            "access": "unauthenticated_get_http_200",
            "team_action": action,
            "restricted": False,
            "runtime_enabled": acquisition_mode == "api_first",
            "request_template": {"query_or_body": "page=<value>"},
            "notes_th": (
                "หน้ารวมนวัตกรรมสาธารณะ; page=1 ตรงกับ /search ที่ไม่มี query. "
                "ไม่ดึง login/EPMS และไม่แตก familydashboard เป็นแถวครัวเรือน."
            ),
        }
    ]
    # These public aggregate dashboards already belong to the live connector.
    # Regeneration must preserve both the base and year-filter request shapes.
    for suffix, kind in (("", "innovation"), ("/innovatordashboard", "innovator"), ("/familydashboard", "family")):
        dashboard_url = "https://pmua-apptech.com/dashboard" + suffix
        for filtered in (False, True):
            action = "call_without_login_year_filter" if filtered else "call_without_login"
            endpoints.append({
                "endpoint_id": endpoint_id("f2_target_household", "GET", dashboard_url, action),
                "method": "GET", "url": dashboard_url,
                "kind": f"public_{kind}_dashboard" + ("_year_filter" if filtered else ""),
                "access": "unauthenticated_get_http_200", "team_action": action,
                "restricted": False, "runtime_enabled": acquisition_mode == "api_first",
                "request_template": {"query_or_body": "year_filter=<value>"} if filtered else {},
                "notes_th": "Dashboard สาธารณะ ใช้เฉพาะ aggregate ไม่แตกเป็นแถวครัวเรือน ไม่เรียก login/EPMS",
            })
    return endpoints


def load_spu_disaster_endpoints(
    source_id: str,
    acquisition_mode: str,
    plan: dict[str, Any] | None,
) -> list[dict]:
    """Build the reviewed SPU runtime allowlist from the explicit PR plan."""

    datasets = list((plan or {}).get("datasets", []))
    if not datasets:
        raise RuntimeError(f"{source_id}: reviewed SPU plan must declare datasets")
    endpoints: list[dict] = []
    for dataset in datasets:
        url = str(dataset.get("url") or "").strip()
        name = str(dataset.get("name") or "").strip()
        if not url.startswith("https://") or not name:
            raise RuntimeError(f"{source_id}: SPU dataset requires an HTTPS URL and name")
        action = "call_without_login"
        if dataset.get("paginate") is True:
            request_shape = "page=<value>&limit=<value>"
        elif name == "incident_map":
            request_shape = "swLat=<value>&swLng=<value>&neLat=<value>&neLng=<value>"
        else:
            request_shape = ""
        endpoints.append(
            {
                "endpoint_id": endpoint_id(source_id, "GET", url, action),
                "method": "GET",
                "url": url,
                "kind": "public_disaster_monitoring_candidate",
                "access": "maintainer_reviewed_public_candidate",
                "team_action": action,
                "restricted": False,
                "runtime_enabled": acquisition_mode == "api_first",
                "request_template": {"query_or_body": request_shape},
                "notes_th": (
                    "Operational Candidate approved in PR #21; raw responses must use "
                    "ResponseRecorder and public serving must use a reviewed artifact."
                ),
            }
        )
    return endpoints


def source_policy(source_id: str) -> tuple[str, str, str, bool]:
    if source_id in RESTRICTED_SOURCE_IDS:
        return "blocked", "restricted_local_only", "restricted_local_only", False
    if source_id in APPROVED_PUBLIC_MODES:
        return (
            APPROVED_PUBLIC_MODES[source_id],
            "team_approved_public",
            "public_candidate",
            True,
        )
    return "metadata_only", "metadata_only", "metadata_only", False


def source_notes(registry_row: dict, index_row: dict | None, source_id: str) -> str:
    notes = [registry_row.get("notes", "")]
    if source_id == "f2_target_household":
        notes = ["ดึงข้อมูลตลาดผลงานสาธารณะ เครดิตเจ้าของงานใช้ได้ตาม field_contexts เมื่อมีฟิลด์และหลักฐาน"]
    if source_id == "clig_projects":
        notes.append("ชื่อผู้วิจัยและสังกัดเป็นเครดิตของโครงการตาม field_contexts; คงเลน Candidate และไม่ใช้แทน KPI รับรอง")
    if index_row and index_row.get("notes_th"):
        notes.append(index_row["notes_th"])
    if source_id == "f3_housing_portal":
        notes = [note for note in notes if "demand 25,919" not in note.lower()]
    if source_id == "f2_learning_dashboard":
        notes.append(
            "กำหนด Cloud publication scope เฉพาะ candidate aggregate ระดับจังหวัด 66 แถว; "
            "scope นี้ไม่ใช่ fact acceptance, raw response ยังไม่มี manifest และต้องทบทวน "
            "selected-project scope ก่อนใช้เป็น KPI"
        )
    if source_id == "f1_pppconnext":
        notes.append(
            "พบ canonical Dashboard รุ่น 2026 และ API aggregate สาธารณะ 4 endpoints; "
            "Silver ปัจจุบันมี 47 aggregate records ครบ 20 จังหวัด/ปีสำรวจ/ทุน/ความช่วยเหลือ. "
            "Snapshot BI เดิม 997,293 chart records เก็บเป็นหลักฐานประวัติและห้ามเทียบเป็นจำนวนครัวเรือน."
        )
    if source_id == "f2_culturalmap_university":
        notes.append(
            "ตรวจ public JSON feed และ listing pages ล่าสุด 2026-08-17 แล้ว ID coverage ตรง snapshot "
            "5,619/5,619; Dashboard เก็บ Map details 5,258 และทะเบียนผลงาน/ผู้จัดทำอีก 361 รายการ "
            "พร้อมข้อมูลติดต่องานตาม field_contexts. Source as_of ยังไม่ระบุ."
        )
    if source_id == "f2_apptech_mtr":
        notes.append(
            "public list และ API สถิติรอบ 2026-08-17 ตรงกันที่ 630 records; "
            "Silver เดิม 621 ขาด 9 records และ common record 1 รายการเปลี่ยน version. "
            "Serving เก็บชื่อเจ้าของผลงานและข้อมูลติดต่องานจาก public listing ตาม field_contexts."
        )
    if source_id == "f2_rmutdb":
        notes.append(
            "ตรวจ public e-book ครบ 11/11 ไฟล์เมื่อ 2026-08-17 และ metadata ไม่เปลี่ยน; "
            "public snapshot 2,001 rows ยังใช้ได้โดยแยก detail 1,006 กับ annual summary 995 เป็นคนละ grain. "
            "Live Dashboard ที่เคยพบ 1,015 ยังต่างจาก detail 9 records; "
            "JSON API ของหน้า dashboard สาธารณะใช้ได้ตามที่เว็บเรียก"
        )
    if source_id == "f2_apptech_mru":
        notes.append(
            "snapshot 503 records ผ่าน structural/privacy validation และครอบ public surface ณ 2026-08-05; "
            "รอบ 2026-08-17 API ยังรายงาน innovation totaldata=501 และ 192 แถวแรกตรง baseline ทั้งหมด "
            "แต่หยุดคืน JSON ที่ parse ได้ก่อนจบ จึงคง snapshot เดิมและห้าม publish partial run. "
            "Railway commit รอบใหม่ได้เฉพาะ unique IDs เท่ากับ totaldata ครบทุก dataset."
        )
    if source_id == "f2_target_household":
        notes.append(
            "หน้าสาธารณะคือตลาดนวัตกรรม AppTech ไม่ใช่ทะเบียนครัวเรือน; serving ดึง /search pagination "
            "เป็นรายการสินค้าสาธารณะ โดยข้อมูลเจ้าของงานใช้ได้เมื่อมีหลักฐาน. จำนวนรายการอ้างอิงล่าสุดที่ตรวจครบคือ 1,160 รายการ "
            "และอาจขยับได้ — completeness คือ pagination ไม่ใช่จำนวนคงที่. "
            "ไม่แตก /dashboard/familydashboard เป็นแถวครัวเรือน และไม่ GET หน้ารายละเอียดตอน ingest."
        )
    if source_id == "f2_learning_area_based":
        notes.append(
            "ตรวจหน้าและ API ล่าสุด 2026-08-17 แล้ว response byte-identical กับ snapshot: "
            "1,002 rows/1,002 unique IDs; หน้าแสดง 6 ภูมิภาค, 55 จังหวัด, 256 อำเภอ, "
            "533 ตำบล และ 1,002 ธุรกิจตรงกับ stats envelope. business type มีเฉพาะ aggregate; "
            "Railway เก็บ aggregate แยก grain และตรวจทุกผลรวมก่อน commit."
        )
    if source_id == "f2_wallet_all_realtime":
        notes.append(
            "หน้า lesuper เป็นแดชบอร์ดข้อมูลเปิด; serving ดึงเดือนปัจจุบันด้วย POST {\"date\": \"\"} "
            "ได้ 2 aggregate (ครัวเรือน+ธุรกิจ) ไม่ใช่รายการรายบุคคล. ประวัติรายเดือนเต็มอยู่เลนหลักฐาน/R2. "
            "as_of ใช้ thisMonth ของต้นทาง และยังเป็น needs_review."
        )
    if source_id == "f2_wallet_cluster_realtime":
        notes.append(
            "หน้าเปรียบเทียบคลัสเตอร์เป็นข้อมูลเปิด; serving ดึงเดือนปัจจุบัน 7 กลุ่ม × 2 กระเป๋า = 14 records. "
            "กลุ่มขนาดเล็กเป็นค่าที่หน้าเว็บเผยแพร่แล้ว จึงเก็บเป็น Candidate และไม่เทียบยอดรวมที่ frontend ฮาร์ดโค้ด. "
            "as_of ใช้ thisMonth ของต้นทาง และยังเป็น needs_review."
        )
    if source_id == "f3_city_capital_open_data":
        notes.append(
            "homepage HTML รอบ 2026-08-17 byte-identical กับ raw HTML ที่ parser ใช้เมื่อ 2026-08-16; "
            "snapshot ยังครบ 18 เมือง × 39 metric definitions = 702 unique city×metric observations "
            "(698 numeric, 4 null). Railway ใช้ snapshot-only และตรวจ cartesian coverage/unique keys ก่อน commit."
        )
    if source_id == "f3_ruamthiao_lamphun":
        notes.append(
            "ตรวจ public Vite bundle รอบ 2026-08-17 แล้ว hash และ data ทั้ง 5 หน้าตรง snapshot: "
            "54 primary records และ 157 content items ครบ. Railway แยกเป็น 8 queryable grains "
            "และบล็อก commit เมื่อ page/count/bundle/warning/unique-ID gate ไม่ผ่าน; as_of/owner/terms "
            "ยังไม่ระบุ จึงคง needs_review."
        )
    if source_id == "f3_housing_portal":
        notes.append(
            "ตรวจ 2026-08-17 แล้ว CKAN 7 datasets/41 resources ไม่เปลี่ยน และ Railway value-approved "
            "projection ครบ 7,259 rows. Housing Stock 28,694 points, 6,543 accessibility grids และ "
            "159,126 flood grids เข้า serving database แล้ว. Demand 25,919 respondent rows เผยแพร่แบบ "
            "privacy projection โดยตัด source id และผ่านการตรวจชื่อ เบอร์โทร และอีเมล; ยังเป็น needs_review."
        )
    if source_id in SPU_DISASTER_SOURCE_IDS:
        notes.append(
            "Operational disaster records remain Candidate; public serving reads only the "
            "reviewed disaster_tracking artifact and never reads dashboard_records directly."
        )
    return " | ".join(note.strip() for note in notes if note and note.strip())


def require_evidence_workspace() -> None:
    """Fail with a next-step message instead of a raw traceback on fresh clones."""

    if REGISTRY_PATH.exists():
        return
    raise SystemExit(
        "ไม่พบ canonical registry: "
        f"{REGISTRY_PATH}\n"
        "เครื่องนี้ยังไม่มี evidence workspace (AIAT_Project) หรือยังไม่ได้ชี้ AIAT_EVIDENCE_ROOT\n"
        "- ถ้ามี workspace อยู่โฟลเดอร์อื่น: ตั้ง environment variable AIAT_EVIDENCE_ROOT "
        "ให้ชี้โฟลเดอร์นั้นก่อนรันใหม่\n"
        "- ถ้าไม่มี workspace: ไม่ต้องรันไฟล์นี้ — config/source_catalog.json ที่ commit ไว้"
        "คือผลลัพธ์ generated ล่าสุดแล้ว ใช้ต่อได้เลย (ดู docs/add-new-source.md ขั้น 1)"
    )


def build_catalog(merged_root: Path) -> dict:
    require_evidence_workspace()
    registry = read_json(REGISTRY_PATH)
    ingestion_plans = read_json(INGESTION_PLANS_PATH).get("sources", {})
    index_path = merged_root / "00_INDEX.csv"
    index_rows = list(csv.DictReader(index_path.open(encoding="utf-8-sig", newline="")))
    index_by_source_id = {row["source_id"]: row for row in index_rows}

    sources: list[dict] = []
    for ordinal, registry_row in enumerate(registry["sources"], start=1):
        source_id = registry_row["source_id"]
        index_row = index_by_source_id.get(source_id)
        acquisition_mode, cloud_policy, value_visibility, production_values_allowed = source_policy(source_id)
        card_path = source_card_path(ordinal, source_id)
        if not card_path.is_file():
            raise SystemExit(f"ไม่พบ source card: {card_path}; เพิ่มหลักฐานตาม docs/add-new-source.md ขั้น 1 ก่อน regenerate")
        card = read_json(card_path)
        if card.get("source_id") != source_id or not card.get("status"):
            raise ValueError(f"Source card must identify {source_id} and its audit status: {card_path}")

        data_location = as_project_path(index_row["data_location"], merged_root) if index_row else None
        endpoints = (
            load_endpoints(source_id, cloud_policy, acquisition_mode, data_location)
            if data_location and (production_values_allowed or cloud_policy == "restricted_local_only")
            else []
        )
        if source_id == "f2_learning_dashboard":
            endpoints = load_learning_dashboard_endpoint(acquisition_mode)
        if source_id == "f1_pppconnext":
            endpoints = load_pppconnext_2026_endpoints(acquisition_mode)
        if ingestion_plans.get(source_id, {}).get("catalog_endpoints"):
            endpoints = load_plan_endpoints(source_id, ingestion_plans[source_id], cloud_policy, acquisition_mode)
        if source_id == "f2_target_household":
            endpoints = load_target_household_search_endpoint(acquisition_mode)
        if source_id in SPU_DISASTER_SOURCE_IDS:
            endpoints = load_spu_disaster_endpoints(
                source_id,
                acquisition_mode,
                ingestion_plans.get(source_id),
            )
        endpoints = apply_runtime_request_templates(
            source_id,
            endpoints,
            ingestion_plans.get(source_id),
        )
        snapshot_files = (
            load_snapshot_files(data_location)
            if data_location and production_values_allowed
            else []
        )
        if source_id in {"f2_wallet_all_realtime", "f2_wallet_cluster_realtime"}:
            # INDEX row counts are historical monthly dumps, not the current-month
            # serving grain.
            snapshot_files = []
        if source_id == "f2_apptech_mtr":
            current_manifest = read_json(APPTECH_CURRENT_MANIFEST)
            if current_manifest.get("source_id") != source_id or current_manifest.get("row_count") != 630:
                raise RuntimeError("AppTech current Silver manifest no longer matches 630-row audit")
            snapshot_files = [provenance_path(APPTECH_CURRENT_RECORDS)]

        if "catalog_expected_record_count" in ingestion_plans.get(source_id, {}):
            expected_record_count = int(ingestion_plans[source_id]["catalog_expected_record_count"])
        elif source_id == "f2_learning_dashboard":
            expected_record_count = LEARNING_DASHBOARD_PROVINCE_ROWS
        elif source_id == "f1_pppconnext":
            expected_record_count = PPPCONNEXT_2026_RECORD_COUNT
        elif source_id == "f2_apptech_mtr":
            expected_record_count = int(current_manifest["row_count"])
        elif source_id == "f2_wallet_all_realtime":
            expected_record_count = WALLET_ALL_CURRENT_MONTH_RECORDS
        elif source_id == "f2_wallet_cluster_realtime":
            expected_record_count = WALLET_CLUSTER_CURRENT_MONTH_RECORDS
        elif source_id == "f2_target_household":
            expected_record_count = TARGET_PUBLIC_PRODUCT_LISTING_COUNT
        elif index_row and production_values_allowed:
            expected_record_count = int(index_row["data_row_count"])
        else:
            # Metadata-only sources do not publish production counts in this catalog.
            expected_record_count = 0

        sources.append(
            {
                "ordinal": ordinal,
                "source_id": source_id,
                "group": registry_row.get("group", ""),
                "name_th": index_row["name_th"] if index_row else registry_row["name_th"],
                "url": (
                    registry_row["normalized_url"]
                    if source_id == "f1_pppconnext"
                    else index_row["url"] if index_row else registry_row["normalized_url"]
                ),
                "source_type": registry_row.get("source_type_guess", ""),
                "sensitivity_lane": registry_row.get("sensitivity", "public_unknown"),
                "source_card": provenance_path(card_path),
                "audit_status": card.get("status", "NOT_AUDITED"),
                "acquisition_mode": acquisition_mode,
                "snapshot_fallback": bool(snapshot_files),
                "readiness_status": (
                    "restricted"
                    if cloud_policy == "restricted_local_only"
                    else "needs_review"
                    if production_values_allowed
                    else "metadata_only"
                ),
                "cloud_policy": cloud_policy,
                "value_visibility": value_visibility,
                "production_values_allowed": production_values_allowed,
                "expected_record_count": expected_record_count,
                "notes_th": source_notes(registry_row, index_row, source_id),
                "snapshot_origin_files": snapshot_files,
                "endpoints": endpoints,
            }
        )

    if len(sources) != registry["total_records"]:
        raise RuntimeError(
            f"Registry declares {registry['total_records']} sources, built {len(sources)}"
        )

    return {
        "catalog_version": "0.3.0",
        "generated_from": {
            "registry": provenance_path(REGISTRY_PATH),
            "merged_index": provenance_path(index_path),
            "source_cards": "data/source_audit/<ordinal>_<source_id>/source_card.json",
            "verified_endpoint_observations": [
                provenance_path(LEARNING_DASHBOARD_OBSERVATION),
                provenance_path(PPPCONNEXT_2026_OBSERVATION),
                provenance_path(APPTECH_CURRENT_OBSERVATION),
                provenance_path(TARGET_HOUSEHOLD_OBSERVATION),
            ],
        },
        "policy": {
            "approval_basis": "current_catalog_policy_and_source_cards",
            "current_stewardship": "repository_co_maintainers",
            "registry_source_count": len(sources),
            "approved_public_source_count": sum(
                source["production_values_allowed"] for source in sources
            ),
            "metadata_only_source_count": sum(
                source["value_visibility"] == "metadata_only" for source in sources
            ),
            "restricted_source_count": sum(
                source["cloud_policy"] == "restricted_local_only" for source in sources
            ),
            "restricted_sources_are_never_deployed": True,
            "candidate_records_are_not_kpi_facts": True,
        },
        "sources": sources,
    }


def write_governance(catalog: dict, target: Path) -> None:
    policy = catalog["policy"]
    lines = [
        "<!-- Generated by tools/build_source_catalog.py; edit policy inputs or the generator, not this file. -->",
        "",
        "# Data governance and publication policy",
        "",
        "เอกสารนี้เป็นจุดอ้างอิงสำหรับ source classification และ publication permission",
        "",
        "> Publication permission ไม่ใช่ fact acceptance ข้อมูล public ทุกชุดยังเป็น `candidate`/`needs_review` จนกว่า semantic, freshness, unit และ denominator จะชัด",
        "",
        "## Current publication basis",
        "",
        f"- ฐานการจัดหมวดปัจจุบัน: `{policy['approval_basis']}`",
        f"- ผู้ดูแล policy ปัจจุบัน: `{policy['current_stewardship']}`",
        f"- Public candidate ที่อนุญาตให้ใช้ใน Dashboard: {policy['approved_public_source_count']} แหล่ง",
        f"- Metadata-only: {policy['metadata_only_source_count']} แหล่ง",
        f"- Restricted local-only: {policy['restricted_source_count']} แหล่ง",
        "",
        "พิจารณาตามบริบทของฟิลด์: เครดิตเจ้าของงาน ผู้วิจัย หน่วยงาน ช่องทางติดต่องานและที่ตั้งสาธารณะเผยแพร่ได้ตาม field_contexts ใน contract ดู [คู่มือบริบทข้อมูล](field-contexts.md)",
        "",
        "`f2_learning_dashboard` ถูกจัด publication scope เฉพาะ candidate aggregate ระดับจังหวัด 66 แถวตามสถานะใน source card แต่ยังขาด source-wide unit/`as_of`, raw manifest และ selected-project scope review สถานะจึงยังเป็น `needs_review` และการจัด scope นี้ไม่เปลี่ยน semantic review ให้เป็น accepted",
        "",
        "## Source classification",
        "",
        "| # | `source_id` | วิธีหลัก | Visibility | Records อ้างอิง | Endpoints | Runtime-safe |",
        "|---:|---|---|---|---:|---:|---:|",
    ]
    mode_labels = {
        "api_first": "API-first",
        "snapshot_only": "Snapshot",
        "metadata_only": "Metadata",
        "blocked": "Blocked",
    }
    visibility_labels = {
        "public_candidate": "public candidate",
        "metadata_only": "metadata-only",
        "restricted_local_only": "restricted local-only",
    }
    for source in catalog["sources"]:
        safe = sum(endpoint["runtime_enabled"] for endpoint in source["endpoints"])
        lines.append(
            f"| {source['ordinal']} | `{source['source_id']}` | "
            f"{mode_labels.get(source['acquisition_mode'], source['acquisition_mode'])} | "
            f"{visibility_labels.get(source['value_visibility'], source['value_visibility'])} | "
            f"{source['expected_record_count']:,} | "
            f"{len(source['endpoints'])} | {safe} |"
        )
    lines.extend(
        [
            "",
            "ตัวเลข records เป็น reference count ของ source ไม่ใช่จำนวนที่ต้องแสดงทั้งหมดใน UI และ runtime-safe เป็น technical allowlist ไม่ใช่การรับรองความหมายหรือ freshness",
            "",
            "## Fail-closed defaults",
            "",
            "- `PUBLIC_DATA_VALUES_ENABLED=false` ปิด operational row payload endpoint; cleaned public projection ใช้ publication gate แยกต่างหาก",
            "- `ALLOW_PENDING_OWNER_SOURCES=false`",
            "- ไม่มี executable ingestion plan สำหรับ login-only endpoint",
            "- login และ error endpoints ไม่ต้องยิงถ้าไม่จำเป็น",
            "- Unknown unit, denominator, `as_of` หรือ geography ต้องคงเป็น `null`/`needs_review`",
            "",
            "## Publication workflow แบบ 2 เลน",
            "",
            "- URL/dataset ใหม่ หรือการเปลี่ยน grain, identity, unit, denominator, geography, `as_of`, contract, builder หรือ `serving_manifest.json` ต้องผ่าน Codex review และ merge ด้วยมือ",
            "- Routine refresh อัตโนมัติได้เฉพาะ output/provenance ใต้ `data/public/` ที่ contract เดิมประกาศไว้ พร้อม `publication_receipt.json` ที่คำนวณใหม่",
            "- `publication-gate` ตรวจ schema, identity, count, privacy, source policy, SHA-256 และ semantic diff ก่อน label `codex-publication-reviewed` จะใช้กับ revision นั้นได้",
            "- ถ้า `peetwan` เป็น PR author ให้ตรวจว่า Codex review ครอบคลุม head SHA ล่าสุด ไม่มี P0/P1/conversation ค้าง และ required checks ผ่าน แล้วกด squash merge เองได้โดยไม่ต้องรอ teammate Approve",
            "- Codex review เป็น findings ไม่ใช่ GitHub approving review; PR ของ contributor ยังใช้ผู้ตรวจที่ไม่ใช่ author ใส่ auto-merge label ตาม lane",
            "- `data/spatial/` และ `data/demand/` ยังเป็น manual lane; scheduled automation ตรวจ PR/deployment แต่ไม่เขียน Production database เอง",
            "- ความหมายที่หลักฐานยังไม่บอกต้องคง `needs_review` ห้ามให้ automation เดาเติม",
            "",
            "ขั้นตอนทีมแบบย่ออยู่ที่ [Publication workflow](publication-workflow.md)",
            "",
            "## Privacy projection",
            "",
            "ก่อนเข้า `data/public/` ให้จัด projection ตามชนิดข้อมูล:",
            "",
            "- ข้อมูลติดต่อส่วนตัว เลขประจำตัว และข้อมูลสุขภาพ/การเงินระดับบุคคล; ชื่อเจ้าของผลงานหรือช่องทางติดต่องานใช้บริบทที่ประกาศใน contract",
            "- payload จาก endpoint ที่ต้อง login, token หรือ permission เพิ่มเติม",
            "",
            "Artifacts ที่เพื่อนร่วมทีมนำเข้าต้องคง source URL, source ID, evidence path และ provenance ของผู้เก็บเดิม",
            "",
            "## สิ่งที่ห้าม commit",
            "",
            "- `.env`, secret, token, private key, cookie และ Authorization header",
            "- signed URL, cookie ของบัญชีส่วนตัว และ secret ที่ไม่ใช่ public client header ของเว็บ",
            "- SQLite/PostgreSQL dump และ runtime database",
            "- `data/runtime/`, `data/snapshots/` และ raw payload",
            "- ข้อมูลส่วนบุคคลที่ไม่ได้อยู่ในขอบเขตเผยแพร่ของงาน; ไม่ห้ามเครดิตเจ้าของงานแบบเหมารวม",
            "",
            "## Checklist ก่อน publication/deploy",
            "",
            f"1. Source อยู่ใน public candidate {policy['approved_public_source_count']} แหล่งและไม่ใช่ restricted lane",
            "2. มี publication scope เป็นลายลักษณ์อักษร",
            "3. ยืนยัน schema, grain, unit, denominator, `as_of` และ freshness เท่าที่หลักฐานรองรับ",
            "4. PII/secret scan ผ่านและ field allowlist ตรงกับ projection",
            "5. Row counts และ hashes ย้อนกลับไปยัง immutable evidence ได้",
            "6. Geography ใช้ exact match หรือ official crosswalk เท่านั้น",
            "7. API retry/rate-limit tests ไม่เดารหัสผ่านและไม่ยิง login ส่วนตัว",
            "8. UI/API ยังคง quality label และข้อจำกัดของ source",
            "9. Restricted value count ใน `/api/public/v1/database-coverage` เท่ากับ 0",
            "10. Test suite ผ่านก่อน push/deploy",
            "",
            "สถานะ serving ล่าสุดดูได้จาก `/api/public/v1/source-coverage` และ `/api/public/v1/database-coverage`",
            "",
        ]
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-root", type=Path, default=DEFAULT_MERGED)
    parser.add_argument("--output", type=Path, default=DASHBOARD_ROOT / "config/source_catalog.json")
    parser.add_argument(
        "--governance-output",
        type=Path,
        default=DASHBOARD_ROOT / "docs/data-governance.md",
    )
    args = parser.parse_args()
    catalog = build_catalog(args.merged_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_governance(catalog, args.governance_output)
    print(
        json.dumps(
            {
                "sources": len(catalog["sources"]),
                "public_candidate": catalog["policy"]["approved_public_source_count"],
                "metadata_only": catalog["policy"]["metadata_only_source_count"],
                "restricted_local_only": catalog["policy"]["restricted_source_count"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
