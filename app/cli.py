from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import func, select

from app.catalog import load_catalog, load_ingestion_plans, sync_catalog
from app.connector_contracts import ConnectorContractError, validate_connector_contracts
from app.database import SessionLocal, init_db
from app.flood_snapshot_importer import DEFAULT_PIPELINE_ROOT, DRIVE_FOLDER_ID, import_flood_snapshots
from app.ingestion import IngestionPipeline, PolicyViolation
from app.models import DashboardRecord, HousingDemandRecord, IngestionRun, PublicArtifact, Source
from app.demand_artifacts import sync_housing_demand
from app.public_artifacts import database_artifact_counts, sync_public_artifacts
from app.publication import validate_git_revision, validate_workspace, write_receipt
from app.spatial_artifacts import database_spatial_counts, sync_spatial_layers
from app.settings import PROJECT_ROOT


PUBLICATION_CONTRACTS_ROOT = PROJECT_ROOT / "config" / "publication_contracts"
SOURCE_CATALOG_PATH = PROJECT_ROOT / "config" / "source_catalog.json"


def initialize() -> None:
    publication_report = validate_workspace(
        PROJECT_ROOT,
        PUBLICATION_CONTRACTS_ROOT,
        SOURCE_CATALOG_PATH,
    )
    if publication_report["status"] != "valid":
        raise RuntimeError(
            "publication preflight failed: "
            + "; ".join(publication_report["problems"][:10])
        )
    init_db()
    with SessionLocal() as session:
        sync_catalog(session)
        sync_public_artifacts(session)
        sync_spatial_layers(session)
        sync_housing_demand(session)


def command_ingest(args: argparse.Namespace) -> int:
    initialize()
    source_ids = args.source
    if args.all:
        executable = set(load_ingestion_plans().get("sources", {}))
        source_ids = [
            item["source_id"]
            for item in load_catalog()["sources"]
            if item.get("production_values_allowed")
            and item["cloud_policy"] != "restricted_local_only"
            and item["source_id"] in executable
        ]
    if not source_ids:
        raise SystemExit("ระบุ --source SOURCE_ID หรือ --all")
    failed = 0
    with SessionLocal() as session:
        pipeline = IngestionPipeline(session)
        for source_id in source_ids:
            try:
                print(json.dumps(pipeline.ingest_source(source_id, args.strategy), ensure_ascii=False))
            except PolicyViolation as exc:
                print(json.dumps({"source_id": source_id, "status": "blocked", "reason": str(exc)}, ensure_ascii=False))
            except Exception as exc:
                failed += 1
                print(
                    json.dumps(
                        {"source_id": source_id, "status": "failed", "error": f"{type(exc).__name__}: {exc}"},
                        ensure_ascii=False,
                    )
                )
    return 1 if failed else 0


def command_status() -> int:
    initialize()
    with SessionLocal() as session:
        rows = session.execute(
            select(
                Source.source_id,
                Source.acquisition_mode,
                Source.cloud_policy,
                Source.production_values_allowed,
                func.count(DashboardRecord.id),
            )
            .outerjoin(DashboardRecord, DashboardRecord.source_id == Source.source_id)
            .group_by(Source.source_id)
            .order_by(Source.ordinal)
        )
        for row in rows:
            print(
                json.dumps(
                    {
                        "source_id": row[0],
                        "acquisition_mode": row[1],
                        "cloud_policy": row[2],
                        "production_values_allowed": row[3],
                        "loaded_records": row[4],
                    },
                    ensure_ascii=False,
                )
            )
        failed = session.scalar(select(func.count()).select_from(IngestionRun).where(IngestionRun.status == "failed"))
        print(
            json.dumps(
                {
                    "serving_database": {
                        "public_artifacts": session.scalar(
                            select(func.count()).select_from(PublicArtifact)
                        )
                        or 0,
                        "groups": database_artifact_counts(session),
                        "spatial_layers": database_spatial_counts(session),
                        "housing_demand_records": session.scalar(
                            select(func.count()).select_from(HousingDemandRecord)
                        ) or 0,
                    }
                },
                ensure_ascii=False,
            )
        )
        return 1 if failed else 0


def command_import_flood_snapshots(args: argparse.Namespace) -> int:
    initialize()
    with SessionLocal() as session:
        result = import_flood_snapshots(
            session,
            pipeline_root=Path(args.pipeline_root),
            folders=args.folder or None,
            drive_folder_id=args.drive_folder_id,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_validate_pipeline() -> int:
    """Validate the public connector surface without network or database access."""

    try:
        report = validate_connector_contracts()
    except ConnectorContractError as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def command_publication(args: argparse.Namespace) -> int:
    if args.publication_command == "receipt":
        receipt = write_receipt(
            PROJECT_ROOT,
            PUBLICATION_CONTRACTS_ROOT,
            SOURCE_CATALOG_PATH,
        )
        print(
            json.dumps(
                {
                    "status": "written",
                    "path": "data/public/publication_receipt.json",
                    "artifact_count": receipt["artifact_count"],
                    "release_digest": receipt["release_digest"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.publication_command == "diff":
        report, valid = validate_git_revision(
            PROJECT_ROOT,
            PUBLICATION_CONTRACTS_ROOT,
            SOURCE_CATALOG_PATH,
            args.base_sha,
            args.head_sha,
        )
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.report:
            Path(args.report).write_text(encoded, encoding="utf-8")
        print(encoded, end="")
        return 0 if valid else 1
    report = validate_workspace(
        PROJECT_ROOT,
        PUBLICATION_CONTRACTS_ROOT,
        SOURCE_CATALOG_PATH,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "valid" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="AIAT dashboard database workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="สร้างตารางและ sync catalog + public serving artifacts")
    ingest = subparsers.add_parser("ingest", help="ดึง API หรือ replay snapshot เข้า database")
    ingest.add_argument("--source", action="append", default=[])
    ingest.add_argument(
        "--all",
        action="store_true",
        help="เรียกเฉพาะ source สาธารณะที่มี executable API plan",
    )
    ingest.add_argument("--strategy", choices=["auto", "api", "snapshot"], default="auto")
    flood = subparsers.add_parser(
        "import-flood-snapshots",
        help="import existing flood/water JSONL snapshots into dashboard_records candidate rows",
    )
    flood.add_argument(
        "--pipeline-root",
        default=DEFAULT_PIPELINE_ROOT.as_posix(),
        help="root folder containing sukhothaicare, sukhothai-water, NSN, and rawangphai",
    )
    flood.add_argument(
        "--folder",
        action="append",
        default=[],
        help="optional source folder to import; repeat for multiple folders",
    )
    flood.add_argument(
        "--drive-folder-id",
        default=None,
        help="Google Drive folder ID to download pipeline snapshots from (e.g. %s)" % DRIVE_FOLDER_ID,
    )
    subparsers.add_parser("status", help="ดูสถานะ source และจำนวน record")
    subparsers.add_parser(
        "validate-pipeline",
        help="ตรวจ registry, connector entrypoint, grain, completeness และ privacy contract โดยไม่เรียก network",
    )
    publication = subparsers.add_parser(
        "publication",
        help="ตรวจหรือสร้าง receipt สำหรับ reviewed public artifacts",
    )
    publication_commands = publication.add_subparsers(
        dest="publication_command",
        required=True,
    )
    publication_commands.add_parser(
        "validate",
        help="ตรวจ contracts, ทุกไฟล์ public, privacy, identity, count และ receipt",
    )
    publication_commands.add_parser(
        "receipt",
        help="สร้าง deterministic receipt หลัง builder เขียน data/public เสร็จ",
    )
    publication_diff = publication_commands.add_parser(
        "diff",
        help="สร้าง semantic diff แบบไม่พิมพ์ค่าของ record",
    )
    publication_diff.add_argument("--base-sha", required=True)
    publication_diff.add_argument("--head-sha", required=True)
    publication_diff.add_argument("--report")
    args = parser.parse_args()
    if args.command == "init-db":
        initialize()
        print("database initialized")
        return 0
    if args.command == "ingest":
        return command_ingest(args)
    if args.command == "import-flood-snapshots":
        return command_import_flood_snapshots(args)
    if args.command == "validate-pipeline":
        return command_validate_pipeline()
    if args.command == "publication":
        return command_publication(args)
    return command_status()


if __name__ == "__main__":
    raise SystemExit(main())
