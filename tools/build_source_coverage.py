#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(
    os.environ.get("AIAT_EVIDENCE_ROOT", str(DASHBOARD_ROOT.parent))
).expanduser().resolve()
REGISTRY_PATH = PROJECT_ROOT / "config/source_registry.json"
AUDIT_ROOT = PROJECT_ROOT / "data/source_audit"
DEFAULT_CATALOG = DASHBOARD_ROOT / "config/source_catalog.json"
DEFAULT_MERGED = PROJECT_ROOT / "data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01"
DEFAULT_OUTPUT = DASHBOARD_ROOT / "data/public/source_coverage.json"
PUBLIC_DASHBOARD_PATH = DASHBOARD_ROOT / "data/public/public_dashboard.json"

SRA_MISSING_SCORE_PROVINCES = [
    "นครราชสีมา",
    "ยโสธร",
    "ลำปาง",
    "พิษณุโลก",
    "พัทลุง",
]

SERVING_PROJECTIONS = {
    "clig_projects": {
        "count": 107,
        "grain": "public_project_attribution_records",
        "evidence": "dashboard_final/data/public/clig_work_attribution.json",
    },
    "f1_sradss_ppaos": {
        "count": 20,
        "numeric_value_count": 15,
        "grain": "province_target_registry_rows_20_with_15_numeric_scores",
        "evidence": (
            "data/qa/web_profile_team_drive_simple/20260814T_team_drive_simple_final/"
            "01_f1_sradss_ppaos/data/f1_sradss_ppaos_current_year_2569_indicator_rows.csv"
        ),
    },
    "f1_pppconnext": {
        "count": 660,
        "grain": "approved_aggregate_rows",
        "evidence": (
            "data/staged/f1_pppconnext/20260804T_pppconnext_bi_silver_01/"
            "silver/bi_aggregate_records.jsonl"
        ),
    },
    "f2_culturalmap_university": {
        "count": 5258,
        "grain": "geocoded_public_point_records",
        "evidence": (
            "data/qa/web_profile_team_drive_simple/20260816T_team_repo_merge_01/"
            "03_f2_culturalmap_university/data/map_inspiration.json"
        ),
    },
    "f2_rmutdb": {
        "count": 2001,
        "grain": "national_technology_catalog_records",
        "evidence": "data/staged/silver/f2_rmutdb/20260805T_ebook_silver_01/manifest.json",
    },
    "f2_apptech_mtr": {
        "count": 77,
        "grain": "province_aggregate_api_rows",
        "evidence": "data/raw/network/f2_apptech_mtr/20260816T_geo_link_audit_07/manifest.json",
    },
    "f2_learning_dashboard": {
        "count": 66,
        "grain": "province_rows_excluding_header",
        "evidence": "data/raw/network/f2_learning_dashboard/20260803T_network/response.txt",
    },
    "f3_city_capital_open_data": {
        "count": 18,
        "grain": "municipality_records",
        "evidence": "data/raw/ckan/f3_city_capital_open_data/20260816T_dla_city_crosswalk_14b/manifest.json",
    },
    "f3_housing_portal": {
        "count": 6953,
        "grain": "province_linked_public_package_rows",
        "evidence": "dashboard_final/data/public/province_evidence.csv",
    },
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        dashboard_relative = resolved.relative_to(dashboard_root)
    except ValueError:
        try:
            return resolved.relative_to(evidence_root).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"provenance input is outside the dashboard and evidence roots: {resolved}"
            ) from exc
    return (Path("dashboard_final") / dashboard_relative).as_posix()


def card_path(ordinal: int, source_id: str) -> Path:
    return AUDIT_ROOT / f"{ordinal:02d}_{source_id}" / "source_card.json"


def flatten_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from flatten_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from flatten_strings(nested)


def evidence_paths(card: dict, source_id: str, restricted: bool) -> list[str]:
    if restricted:
        return []
    selected = {
        "new_run": card.get("new_run", {}),
        "dashboard_validation": card.get("dashboard_validation_2026_08_11", {}),
        "geo": card.get("geo_linkage_reassessment_2026_08_16", {}),
    }
    paths: list[str] = []
    for text in flatten_strings(selected):
        normalized = text.replace("\\", "/")
        if normalized.startswith(("data/", "reports/", "dashboard_final/")):
            if normalized not in paths:
                paths.append(normalized)
    serving_evidence = SERVING_PROJECTIONS.get(source_id, {}).get("evidence")
    if serving_evidence and serving_evidence not in paths:
        paths.append(serving_evidence)
    return paths[:12]


def current_public_projection() -> tuple[set[str], dict[str, int]]:
    if not PUBLIC_DASHBOARD_PATH.exists():
        return set(), {}
    payload = read_json(PUBLIC_DASHBOARD_PATH)
    public_sources = {source["source_id"] for source in payload.get("sources", [])}
    manifest_path = PUBLIC_DASHBOARD_PATH.parent / "serving_manifest.json"
    if manifest_path.exists():
        for artifact in read_json(manifest_path).get("artifacts", []):
            if artifact.get("path") and (manifest_path.parent / artifact["path"]).is_file():
                public_sources.update(artifact.get("source_ids", []))
    province_counts: dict[str, int] = {}
    for province in payload.get("provinces", []):
        for source_id in province.get("evidence_sources", []):
            province_counts[source_id] = province_counts.get(source_id, 0) + 1
    return public_sources, province_counts


def geo_profile(
    source_id: str,
    registry_row: dict,
    card: dict,
    province_projection_count: int,
) -> dict:
    expected = "geography" in registry_row.get("expected_entities", [])
    review = card.get("geo_linkage_reassessment_2026_08_16") or {}
    decision = review.get("decision")
    grain = "unverified"
    linkability = "unverified" if expected else "not_expected"
    linked_area_count: int | None = None
    related_area_count: int | None = None

    if decision == "province_aggregate_join_allowed_for_candidate_serving":
        grain = "province_aggregate"
        linkability = "province_candidate"
        linked_area_count = review.get("linked_province_count")
    elif decision == "province_api_aggregates_allowed_for_candidate_serving":
        grain = "province_aggregate"
        linkability = "province_candidate"
        linked_area_count = review.get("province_rows")
    elif decision == "municipality_to_province_crosswalk_allowed_for_candidate_serving":
        grain = "municipality"
        linkability = "municipality_to_province_candidate"
        linked_area_count = review.get("linked_provinces")
        related_area_count = review.get("matched_cities")
    elif decision == "do_not_join_records_to_province":
        grain = "national_catalog"
        linkability = "not_province_scoped"
        linked_area_count = 0
    elif source_id == "f2_learning_dashboard":
        decision = "candidate_needs_selected_project_scope_review"
        grain = "province_aggregate_candidate"
        linkability = "province_candidate"
        linked_area_count = 66
    elif source_id == "f3_housing_portal":
        decision = "public_package_geo_audit_2026_08_16"
        grain = "province_linked_public_package_rows"
        linkability = "province_candidate"
        linked_area_count = 12
    elif province_projection_count:
        grain = "province_projection_candidate"
        linkability = "province_candidate_unreviewed"
        linked_area_count = province_projection_count

    known_omissions: list[dict] = []
    if source_id == "f1_sradss_ppaos":
        grain = "province_aggregate"
        linkability = "province_candidate"
        linked_area_count = 20
        known_omissions.append(
            {
                "kind": "registered_province_without_numeric_overall_score",
                "count": 5,
                "labels_th": SRA_MISSING_SCORE_PROVINCES,
                "reason_th": "ค่า overall ปี 2569 เป็น null จึงไม่บังคับแปลงเป็นศูนย์",
            }
        )
    if source_id == "f2_culturalmap_university":
        known_omissions.append(
            {
                "kind": "additional_public_non_point_records_outside_map_layer",
                "count": 361,
                "reason_th": "เป็น public records เพิ่มเติม แต่ไม่ใช่ point records 5,258 แถวที่ใช้บนแผนที่จังหวัด",
            }
        )
    if source_id == "f3_housing_portal":
        known_omissions.append(
            {
                "kind": "public_rows_with_unassigned_province_outside_map_projection",
                "count": 306,
                "reason_th": (
                    "แถวเหล่านี้ไม่มีจังหวัดที่ต้นทางกำหนด จึงคงสถานะ unassigned "
                    "และไม่เดาหรือบังคับผูกเข้าจังหวัด"
                ),
            }
        )

    return {
        "expected_by_registry": expected,
        "grain": grain,
        "linkability": linkability,
        "linked_area_count": linked_area_count,
        "related_area_count": related_area_count,
        "decision": decision,
        "current_map_area_count": province_projection_count,
        "numeric_value_area_count": 15 if source_id == "f1_sradss_ppaos" else None,
        "known_omissions": known_omissions,
    }


def notes_for(source_id: str, visibility: str, registry_row: dict) -> list[str]:
    if visibility == "public_candidate":
        notes = ["อนุญาตเผยแพร่ candidate projection แต่ยังไม่ใช่ fact/KPI ที่ผ่านการรับรอง"]
    elif visibility == "restricted_local_only":
        notes = ["เผยแพร่เฉพาะ metadata; ไม่ส่ง payload หรือจำนวน record ภายในขึ้น Cloud"]
    else:
        notes = ["discovery metadata only; ยังไม่มี structured values ที่อนุมัติให้ serving"]

    source_notes = {
        "f1_sradss_ppaos": (
            "ทะเบียนต้นทางมี 20 จังหวัด แต่ map score มี overall ที่เป็นตัวเลข 15 จังหวัด; "
            "นครราชสีมา ยโสธร ลำปาง พิษณุโลก และพัทลุงไม่มีคะแนนตัวเลข"
        ),
        "f1_pppconnext": (
            "serving ใช้ aggregate 660 แถวที่ยืนยัน grain; generic chart points 997,293 แถวเป็น "
            "structure evidence และไม่ควรเทลง UI"
        ),
        "f2_culturalmap_university": (
            "แผนที่ใช้ point records 5,258 แถว; public non-point records อีก 361 แถวต้องแสดงในมุมอื่น ไม่ใช่ marker"
        ),
        "f2_rmutdb": "2,001 records เป็น national technology catalog; affiliation ไม่ใช่พื้นที่ใช้งานหรือผู้รับประโยชน์",
        "f2_target_household": "เส้นทางที่ใช้งานเป็นตลาดผลงานสาธารณะ ใช้ชื่อเจ้าของงานและข้อมูลติดต่องานตาม field_contexts ได้ ส่วนข้อมูลครัวเรือนระดับบุคคลเป็นคนละ dataset",
        "f2_apptech_mtr": "public list และ statistics รอบ 2026-08-17 ตรงกันที่ 630 records; province aggregates, interactions และ innovation records เป็นคนละ population ห้ามบวกเข้าด้วยกัน",
        "f2_learning_dashboard": (
            "นับเฉพาะ province data rows 66 แถว (ไม่รวม header); raw response ยังไม่มี manifest และ "
            "selected-project scope ต้อง review"
        ),
        "f3_city_capital_open_data": "18 municipality records เชื่อมได้ 16 จังหวัด แต่ metric ยังเป็น grain ระดับเทศบาล",
        "f3_housing_portal": (
            "approved public package มี 7,259 แถว: 6,953 แถวเชื่อมได้ 12 จังหวัด และ 306 แถว "
            "คงสถานะ unassigned นอกแผนที่โดยไม่เดาพื้นที่; CKAN lane นี้ครบแล้ว แต่หน้า Housing Stock "
            "มี public spatial surfaces 28,694 points + 6,543 accessibility grids + 159,126 flood grids "
            "ใน serving database. Demand 25,919 respondent rows เผยแพร่แบบ privacy projection โดยตัด "
            "source id และผ่าน contact scan; ทั้งสามชุดแยก grain และยังเป็น needs_review."
        ),
    }
    if source_id in source_notes:
        notes.append(source_notes[source_id])
    elif registry_row.get("notes"):
        notes.append(registry_row["notes"])
    return notes


def build_coverage(catalog_path: Path, merged_root: Path) -> dict:
    if not REGISTRY_PATH.exists():
        raise SystemExit(
            "ไม่พบ canonical registry: "
            f"{REGISTRY_PATH}\n"
            "เครื่องนี้ยังไม่มี evidence workspace (AIAT_Project) หรือยังไม่ได้ชี้ AIAT_EVIDENCE_ROOT\n"
            "- ถ้ามี workspace อยู่โฟลเดอร์อื่น: ตั้ง environment variable AIAT_EVIDENCE_ROOT "
            "ให้ชี้โฟลเดอร์นั้นก่อนรันใหม่\n"
            "- ถ้าไม่มี workspace: ไม่ต้องรันไฟล์นี้ — data/public/source_coverage.json ที่ commit ไว้"
            "คือผลลัพธ์ generated ล่าสุดแล้ว ใช้ต่อได้เลย (ดู docs/add-new-source.md ขั้น 1)"
        )
    registry = read_json(REGISTRY_PATH)
    catalog = read_json(catalog_path)
    if len(catalog.get("sources", [])) != registry["total_records"]:
        raise RuntimeError("Source catalog is stale; rebuild it before source coverage")

    index_path = merged_root / "00_INDEX.csv"
    index_rows = list(csv.DictReader(index_path.open(encoding="utf-8-sig", newline="")))
    index_by_source_id = {row["source_id"]: row for row in index_rows}
    catalog_by_source_id = {row["source_id"]: row for row in catalog["sources"]}
    public_source_ids, province_projection_counts = current_public_projection()

    sources: list[dict] = []
    card_hashes: list[str] = []
    for ordinal, registry_row in enumerate(registry["sources"], start=1):
        source_id = registry_row["source_id"]
        catalog_row = catalog_by_source_id[source_id]
        index_row = index_by_source_id.get(source_id)
        source_card = card_path(ordinal, source_id)
        if not source_card.is_file():
            raise SystemExit(f"ไม่พบ source card: {source_card}; เพิ่มหลักฐานตาม docs/add-new-source.md ขั้น 1 ก่อน regenerate")
        card = read_json(source_card)
        if card.get("source_id") != source_id or not card.get("status"):
            raise ValueError(f"Source card must identify {source_id} and its audit status: {source_card}")
        card_hashes.append(sha256_file(source_card))

        visibility = catalog_row["value_visibility"]
        restricted = visibility == "restricted_local_only"
        values_allowed = bool(catalog_row["production_values_allowed"])
        observed_count = (
            catalog_row["expected_record_count"]
            if values_allowed
            else None
        )
        if source_id == "f2_learning_dashboard":
            count_basis = "verified_province_rows_excluding_header"
        elif source_id == "f2_apptech_mtr":
            count_basis = "validated_current_public_api_silver_2026_08_17"
        elif source_id == "f2_wallet_all_realtime":
            count_basis = "public_current_month_hh_and_bu_snapshots"
        elif source_id == "f2_wallet_cluster_realtime":
            count_basis = "public_current_month_cluster_snapshots"
        elif source_id == "f2_target_household":
            count_basis = "public_product_search_listing"
        elif source_id == "clig_projects":
            count_basis = "verified_public_project_snapshot"
        elif observed_count is not None:
            count_basis = "merged_index_data_row_count"
        elif restricted:
            count_basis = "restricted_local_only_count_withheld"
        else:
            count_basis = "no_approved_structured_projection"

        projection = SERVING_PROJECTIONS.get(source_id, {})
        serving_count = projection.get("count") if values_allowed else None
        additional_non_map_count = {
            "f2_culturalmap_university": 361,
            "f3_housing_portal": 306,
        }.get(source_id)
        not_all_raw_rows_are_served = bool(
            values_allowed
            and (
                serving_count is not None
                and observed_count is not None
                and serving_count != observed_count
                or source_id in {"f2_learning_dashboard", "f2_apptech_mtr"}
            )
        )

        approval = card.get("dashboard_publication_approval_2026_08_16") or {}
        if source_id == "f2_learning_dashboard":
            approval_basis = "source_card_candidate_scope_needs_review"
        elif source_id in {
            "f2_target_household",
            "f2_wallet_all_realtime",
            "f2_wallet_cluster_realtime",
        }:
            approval_basis = "source_card_candidate_scope_needs_review"
        elif approval.get("production_allowed"):
            approval_basis = "source_card_dashboard_publication_scope"
        else:
            approval_basis = "none"

        workflow = card.get("workflow") or {}
        current_map_count = province_projection_counts.get(source_id, 0)
        geo = geo_profile(source_id, registry_row, card, current_map_count)
        primary_paths = evidence_paths(card, source_id, restricted)

        sources.append(
            {
                "ordinal": ordinal,
                "source_id": source_id,
                "group": registry_row.get("group", ""),
                "name_th": catalog_row["name_th"],
                "url": catalog_row["url"],
                "source_type": registry_row.get("source_type_guess", ""),
                "sensitivity_lane": registry_row.get("sensitivity", "public_unknown"),
                "status": {
                    "audit": card.get("status", catalog_row.get("audit_status", "NOT_AUDITED")),
                    "readiness": catalog_row["readiness_status"],
                    "network_api_export": workflow.get("network_api_export", "NOT_RECORDED"),
                    "data_inventory": workflow.get("data_inventory", "NOT_RECORDED"),
                    "fact_acceptance": (
                        "candidate_needs_review"
                        if values_allowed
                        else "not_allowed_restricted"
                        if restricted
                        else "not_applicable_metadata_only"
                    ),
                },
                "records": {
                    "source_index_present": index_row is not None,
                    "observed_count": observed_count,
                    "observed_count_basis": count_basis,
                    "serving_projection_count": serving_count,
                    "serving_numeric_value_count": projection.get("numeric_value_count"),
                    "serving_projection_grain": projection.get("grain"),
                    "additional_public_non_map_count": additional_non_map_count,
                    "not_all_raw_rows_are_served": not_all_raw_rows_are_served,
                    "local_record_count_withheld": restricted,
                },
                "geo": geo,
                "public_visibility": {
                    "classification": visibility,
                    "metadata_in_catalog": True,
                    "production_values_allowed": values_allowed,
                    "candidate_not_fact": values_allowed,
                    "current_public_data_artifact": source_id in public_source_ids,
                    "current_province_projection": current_map_count > 0,
                    "restricted_values_excluded": restricted,
                },
                "evidence": {
                    "registry": provenance_path(REGISTRY_PATH),
                    "source_card": provenance_path(source_card),
                    "merged_index": provenance_path(index_path) if index_row else None,
                    "approval_basis": approval_basis,
                    "catalogued_endpoint_count": len(catalog_row.get("endpoints", [])),
                    "primary_paths": primary_paths,
                    "local_evidence_paths_withheld": restricted,
                },
                "notes_th": notes_for(source_id, visibility, registry_row),
            }
        )

    visibility_counts = {
        key: sum(source["public_visibility"]["classification"] == key for source in sources)
        for key in ("public_candidate", "metadata_only", "restricted_local_only")
    }
    restricted_value_leaks = sum(
        source["public_visibility"]["classification"] == "restricted_local_only"
        and source["records"]["observed_count"] is not None
        for source in sources
    )

    cards_digest = hashlib.sha256("".join(card_hashes).encode("ascii")).hexdigest()
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_scope": "all_registry_sources_metadata_with_gated_value_visibility",
        "inputs": {
            "registry": {"path": provenance_path(REGISTRY_PATH), "sha256": sha256_file(REGISTRY_PATH)},
            "source_catalog": {"path": provenance_path(catalog_path), "sha256": sha256_file(catalog_path)},
            "merged_index": {"path": provenance_path(index_path), "sha256": sha256_file(index_path)},
            "source_cards": {
                "path_pattern": "data/source_audit/<ordinal>_<source_id>/source_card.json",
                "count": len(card_hashes),
                "aggregate_sha256": cards_digest,
            },
        },
        "summary": {
            "registry_source_count": len(sources),
            "catalog_metadata_source_count": len(sources),
            "public_candidate_source_count": visibility_counts["public_candidate"],
            "metadata_only_source_count": visibility_counts["metadata_only"],
            "restricted_local_only_source_count": visibility_counts["restricted_local_only"],
            "sources_with_merged_index_entry": sum(
                source["records"]["source_index_present"] for source in sources
            ),
            "public_candidates_with_observed_count": sum(
                source["records"]["observed_count"] is not None for source in sources
            ),
            "current_public_data_artifact_source_count": sum(
                source["public_visibility"]["current_public_data_artifact"] for source in sources
            ),
            "current_province_projection_source_count": sum(
                source["public_visibility"]["current_province_projection"] for source in sources
            ),
            "restricted_value_leak_count": restricted_value_leaks,
        },
        "sources": sources,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build public-safe source coverage for all registry sources")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--merged-root", type=Path, default=DEFAULT_MERGED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_coverage(args.catalog.resolve(), args.merged_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
