#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DASHBOARD_ROOT.parent
REGISTRY_PATH = PROJECT_ROOT / "config/source_registry.json"
AUDIT_ROOT = PROJECT_ROOT / "data/source_audit"
DEFAULT_MERGED = PROJECT_ROOT / "data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01"
LEARNING_DASHBOARD_OBSERVATION = (
    PROJECT_ROOT
    / "data/raw/network/f2_learning_dashboard/20260803T_network/observation.json"
)

# Publication permission is deliberately separate from semantic acceptance. Every
# source in this map remains candidate/needs_review until its fact gates pass.
APPROVED_PUBLIC_MODES = {
    "f1_sradss_ppaos": "api_first",
    "f1_pppconnext": "snapshot_only",
    "f2_culturalmap_university": "snapshot_only",
    "f2_rmutdb": "snapshot_only",
    "f2_apptech_mtr": "api_first",
    "f2_apptech_mru": "api_first",
    "f2_learning_dashboard": "api_first",
    "f2_learning_area_based": "api_first",
    "f3_city_capital_open_data": "snapshot_only",
    "f3_ruamthiao_lamphun": "snapshot_only",
    "f3_housing_portal": "api_first",
}

RESTRICTED_SOURCE_IDS = frozenset(
    {
        "f2_target_household",
        "f2_wallet_all_realtime",
        "f2_wallet_cluster_realtime",
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


def is_restricted(cloud_policy: str, access: str, action: str) -> bool:
    if cloud_policy == "restricted_local_only":
        return True
    action_value = action.lower()
    access_value = access.lower()
    return (
        action_value.startswith("do_not_call")
        or any(token in access_value for token in ("auth_401", "http_401", "login", "error"))
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


def load_snapshot_files(data_location: Path) -> list[str]:
    if not data_location.exists():
        return []
    return sorted(
        path.relative_to(PROJECT_ROOT).as_posix()
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


def source_policy(source_id: str) -> tuple[str, str, str, bool]:
    if source_id in APPROVED_PUBLIC_MODES:
        return (
            APPROVED_PUBLIC_MODES[source_id],
            "project_owner_approved_public",
            "public_candidate",
            True,
        )
    if source_id in RESTRICTED_SOURCE_IDS:
        return "blocked", "restricted_local_only", "restricted_local_only", False
    return "metadata_only", "metadata_only", "metadata_only", False


def source_notes(registry_row: dict, index_row: dict | None, source_id: str) -> str:
    notes = [registry_row.get("notes", "")]
    if index_row and index_row.get("notes_th"):
        notes.append(index_row["notes_th"])
    if source_id == "f2_learning_dashboard":
        notes.append(
            "อนุญาต Cloud publication เฉพาะ candidate aggregate ระดับจังหวัด 66 แถว; "
            "permission นี้ไม่ใช่ fact acceptance, raw response ยังไม่มี manifest และต้องทบทวน "
            "selected-project scope ก่อนใช้เป็น KPI"
        )
    if source_id in RESTRICTED_SOURCE_IDS:
        notes.append("เก็บเฉพาะ metadata ใน catalog; ห้าม deploy endpoint payload หรือค่าข้อมูล")
    return " | ".join(note.strip() for note in notes if note and note.strip())


def build_catalog(merged_root: Path) -> dict:
    registry = read_json(REGISTRY_PATH)
    index_path = merged_root / "00_INDEX.csv"
    index_rows = list(csv.DictReader(index_path.open(encoding="utf-8-sig", newline="")))
    index_by_source_id = {row["source_id"]: row for row in index_rows}

    sources: list[dict] = []
    for ordinal, registry_row in enumerate(registry["sources"], start=1):
        source_id = registry_row["source_id"]
        index_row = index_by_source_id.get(source_id)
        acquisition_mode, cloud_policy, value_visibility, production_values_allowed = source_policy(source_id)
        card_path = source_card_path(ordinal, source_id)
        card = read_json(card_path) if card_path.exists() else {}

        data_location = as_project_path(index_row["data_location"], merged_root) if index_row else None
        endpoints = (
            load_endpoints(source_id, cloud_policy, acquisition_mode, data_location)
            if data_location and (production_values_allowed or cloud_policy == "restricted_local_only")
            else []
        )
        if source_id == "f2_learning_dashboard":
            endpoints = load_learning_dashboard_endpoint(acquisition_mode)
        snapshot_files = (
            load_snapshot_files(data_location)
            if data_location and production_values_allowed
            else []
        )

        if source_id == "f2_learning_dashboard":
            expected_record_count = LEARNING_DASHBOARD_PROVINCE_ROWS
        elif index_row and production_values_allowed:
            expected_record_count = int(index_row["data_row_count"])
        else:
            # Do not leak restricted/local-only counts through the deployed catalog.
            expected_record_count = 0

        sources.append(
            {
                "ordinal": ordinal,
                "source_id": source_id,
                "group": registry_row.get("group", ""),
                "name_th": index_row["name_th"] if index_row else registry_row["name_th"],
                "url": index_row["url"] if index_row else registry_row["normalized_url"],
                "source_type": registry_row.get("source_type_guess", ""),
                "sensitivity_lane": registry_row.get("sensitivity", "public_unknown"),
                "source_card": card_path.relative_to(PROJECT_ROOT).as_posix(),
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
        "catalog_version": "0.2.0",
        "generated_from": {
            "registry": REGISTRY_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "merged_index": index_path.relative_to(PROJECT_ROOT).as_posix(),
            "source_cards": "data/source_audit/<ordinal>_<source_id>/source_card.json",
            "verified_endpoint_observations": [
                LEARNING_DASHBOARD_OBSERVATION.relative_to(PROJECT_ROOT).as_posix()
            ],
        },
        "policy": {
            "approval_recorded_at": "2026-08-16",
            "approved_by": "peet",
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
        "เอกสารนี้เป็นจุดอ้างอิงเดียวสำหรับ source classification, publication permission, privacy boundary และสิ่งที่ห้ามนำขึ้น Cloud",
        "",
        "> Publication permission ไม่ใช่ fact acceptance ข้อมูล public ทุกชุดยังต้องแสดง `candidate` หรือ `needs_review` จนกว่า semantic, freshness, unit, denominator และ owner gate จะผ่าน",
        "",
        "## Approval record",
        "",
        f"- วันที่บันทึก: {policy['approval_recorded_at']}",
        f"- Project owner: `{policy['approved_by']}`",
        f"- Public candidate ที่อนุญาตให้ใช้ใน Dashboard: {policy['approved_public_source_count']} แหล่ง",
        f"- Metadata-only: {policy['metadata_only_source_count']} แหล่ง",
        f"- Restricted local-only: {policy['restricted_source_count']} แหล่ง",
        "",
        "Approval ครอบเฉพาะ cleaned projection ตาม field allowlist และ privacy rules ใน repository นี้ ไม่อนุญาตให้เผยแพร่ raw payload, person-level data หรือข้อมูลจาก restricted lane",
        "",
        "`f2_learning_dashboard` ได้รับ publication permission เฉพาะ candidate aggregate ระดับจังหวัด 66 แถว แต่ยังขาด source-wide unit/`as_of`, raw manifest และ selected-project scope review สถานะจึงยังเป็น `needs_review` และ approval นี้ไม่เปลี่ยน semantic owner decision ให้เป็น accepted",
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
            "- Restricted sources ไม่มี executable ingestion plan",
            "- Auth, login, household, person และ error endpoints มีได้เฉพาะใน inventory และต้องมี `runtime_enabled=false`",
            "- Unknown unit, denominator, `as_of` หรือ geography ต้องคงเป็น `null`/`needs_review`",
            "",
            "## Privacy projection",
            "",
            "ก่อนเข้า `data/public/` ต้องตัดข้อมูลต่อไปนี้:",
            "",
            "- email, phone, address และ credential-shaped values",
            "- person-level, household-level, health และ financial fields",
            "- small-cell records ที่อาจระบุตัวบุคคลหรือกลุ่มย่อยได้",
            "- payload จาก endpoint ที่ต้อง login, token หรือ permission เพิ่มเติม",
            "",
            "External-team artifacts ต้องคง source URL, source ID, evidence path และ provenance ของผู้เก็บเดิม",
            "",
            "## สิ่งที่ห้าม commit",
            "",
            "- `.env`, secret, token, private key, cookie และ Authorization header",
            "- signed URL หรือ credential ที่พบใน frontend code",
            "- SQLite/PostgreSQL dump และ runtime database",
            "- `data/runtime/`, `data/snapshots/` และ raw payload",
            "- contact, household, health หรือ financial values",
            "",
            "## Checklist ก่อน publication/deploy",
            "",
            f"1. Source อยู่ใน public candidate {policy['approved_public_source_count']} แหล่งและไม่ใช่ restricted lane",
            "2. มี publication scope เป็นลายลักษณ์อักษร",
            "3. ยืนยัน schema, grain, unit, denominator, `as_of` และ freshness เท่าที่หลักฐานรองรับ",
            "4. PII/secret scan ผ่านและ field allowlist ตรงกับ projection",
            "5. Row counts และ hashes ย้อนกลับไปยัง immutable evidence ได้",
            "6. Geography ใช้ exact match หรือ official crosswalk เท่านั้น",
            "7. API retry/rate-limit tests ไม่ bypass auth",
            "8. UI/API ยังคง quality label และข้อจำกัดของ source",
            "9. Restricted value count ใน `/api/public/v1/database-coverage` เท่ากับ 0",
            "10. Test suite ผ่านก่อน push/deploy",
            "",
            "ผล coverage และข้อจำกัดล่าสุดอยู่ใน [Data audit](data-audit.md)",
            "",
        ]
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")


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
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
