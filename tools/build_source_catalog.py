#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DASHBOARD_ROOT.parent
DEFAULT_MERGED = PROJECT_ROOT / "data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01"

POLICIES = {
    "f1_sradss_ppaos": ("api_first", "project_owner_approved_public", True),
    "f1_pppconnext": ("snapshot_only", "project_owner_approved_public", True),
    "f2_culturalmap_university": ("snapshot_only", "project_owner_approved_public", True),
    "f2_rmutdb": ("snapshot_only", "project_owner_approved_public", True),
    "f2_apptech_mtr": ("api_first", "project_owner_approved_public", True),
    "f2_apptech_mru": ("api_first", "project_owner_approved_public", True),
    "f2_learning_area_based": ("api_first", "project_owner_approved_public", True),
    "f2_wallet_all_realtime": ("blocked", "restricted_local_only", False),
    "f2_wallet_cluster_realtime": ("blocked", "restricted_local_only", False),
    "f3_city_capital_open_data": ("snapshot_only", "project_owner_approved_public", True),
    "f3_ruamthiao_lamphun": ("snapshot_only", "project_owner_approved_public", True),
    "f3_housing_portal": ("api_first", "project_owner_approved_public", True),
}


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


def is_restricted(source_id: str, access: str, action: str) -> bool:
    if POLICIES[source_id][1] == "restricted_local_only":
        return True
    action_value = action.lower()
    access_value = access.lower()
    return (
        action_value.startswith("do_not_call")
        or any(token in access_value for token in ("auth_401", "http_401", "login", "error"))
    )


def build_catalog(merged_root: Path) -> dict:
    rows = list(csv.DictReader((merged_root / "00_INDEX.csv").open(encoding="utf-8-sig", newline="")))
    sources: list[dict] = []
    for row in rows:
        source_id = row["source_id"]
        if source_id not in POLICIES:
            continue
        acquisition_mode, cloud_policy, production_values_allowed = POLICIES[source_id]
        data_location = as_project_path(row["data_location"], merged_root)
        endpoints_path = data_location / "endpoints.csv"
        endpoint_rows = list(csv.DictReader(endpoints_path.open(encoding="utf-8-sig", newline="")))
        endpoints = []
        for endpoint in endpoint_rows:
            method = endpoint.get("method", "GET").upper()
            url = endpoint.get("url", "")
            action = endpoint.get("team_action", "")
            access = endpoint.get("access", "")
            restricted = is_restricted(source_id, access, action)
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
                    "request_template": {
                        "query_or_body": endpoint.get("query_or_body", "")
                    },
                    "notes_th": endpoint.get("notes") or endpoint.get("notes_th", ""),
                }
            )
        data_files = [
            path.relative_to(PROJECT_ROOT).as_posix()
            for path in data_location.rglob("*")
            if path.is_file()
            and (path.name == "data.csv" or "data" in path.relative_to(data_location).parts[:-1])
            and (
                path.suffix.lower() in {".csv", ".json", ".jsonl"}
                or path.name.lower().endswith((".csv.gz", ".jsonl.gz"))
            )
            and "metadata" not in path.parts
        ]
        sources.append(
            {
                "ordinal": int(row["ordinal"]),
                "source_id": source_id,
                "name_th": row["name_th"],
                "url": row["url"],
                "acquisition_mode": acquisition_mode,
                "snapshot_fallback": acquisition_mode in {"api_first", "snapshot_only"},
                "readiness_status": "restricted" if cloud_policy == "restricted_local_only" else "needs_review",
                "cloud_policy": cloud_policy,
                "production_values_allowed": production_values_allowed,
                "expected_record_count": int(row["data_row_count"]),
                "notes_th": row["notes_th"],
                "snapshot_origin_files": data_files,
                "endpoints": endpoints,
            }
        )
    return {
        "catalog_version": "0.1.0",
        "generated_from": merged_root.relative_to(PROJECT_ROOT).as_posix(),
        "policy": {
            "approval_recorded_at": "2026-08-16",
            "approved_by": "peet",
            "approved_public_source_count": 10,
            "restricted_sources_are_never_deployed": True,
            "candidate_records_are_not_kpi_facts": True
        },
        "sources": sources,
    }


def write_matrix(catalog: dict, target: Path) -> None:
    lines = [
        "# Source matrix",
        "",
        "10 source ได้รับ project-owner publication approval แล้ว แต่ทุกข้อมูลยังเป็น candidate/needs_review จนกว่า semantic และ freshness gate จะผ่าน; wallet 2 source คง restricted local-only",
        "",
        "| # | source_id | วิธีหลัก | Cloud policy | records อ้างอิง | endpoints | safe runtime |",
        "|---:|---|---|---|---:|---:|---:|",
    ]
    for source in catalog["sources"]:
        safe = sum(endpoint["runtime_enabled"] for endpoint in source["endpoints"])
        lines.append(
            f"| {source['ordinal']} | {source['source_id']} | {source['acquisition_mode']} | "
            f"{source['cloud_policy']} | {source['expected_record_count']:,} | "
            f"{len(source['endpoints'])} | {safe} |"
        )
    lines.extend(
        [
            "",
            "หมายเหตุ:",
            "",
            "- safe runtime หมายถึง endpoint ที่ผ่าน technical allowlist เท่านั้น ไม่ได้แปลว่าอนุญาต publish",
            "- f2_wallet_all_realtime และ f2_wallet_cluster_realtime ถูกบล็อกทั้ง endpoint และ data บน Cloud",
            "- Source สาธารณะ 10 แหล่งได้รับ project-owner approval เมื่อ 2026-08-16 แต่ยังคงป้าย needs_review",
            "- Source จากทีมเพื่อน 3, 14 และ 16 ต้องคง provenance ของ external-team scraper",
            "- Housing demand แสดง schema เท่านั้น และ policy-assessment ถูกบล็อกค่ารายแถว",
            "",
        ]
    )
    target.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-root", type=Path, default=DEFAULT_MERGED)
    parser.add_argument("--output", type=Path, default=DASHBOARD_ROOT / "config/source_catalog.json")
    args = parser.parse_args()
    catalog = build_catalog(args.merged_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_matrix(catalog, DASHBOARD_ROOT / "SOURCE_MATRIX.md")
    print(json.dumps({"sources": len(catalog["sources"]), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
