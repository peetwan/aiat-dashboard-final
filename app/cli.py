from __future__ import annotations

import argparse
import json

from sqlalchemy import func, select

from app.catalog import load_catalog, load_ingestion_plans, sync_catalog
from app.connector_contracts import ConnectorContractError, validate_connector_contracts
from app.database import SessionLocal, init_db
from app.ingestion import IngestionPipeline, PolicyViolation
from app.models import DashboardRecord, HousingDemandRecord, IngestionRun, PublicArtifact, Source
from app.demand_artifacts import sync_housing_demand
from app.public_artifacts import database_artifact_counts, sync_public_artifacts
from app.spatial_artifacts import database_spatial_counts, sync_spatial_layers


def initialize() -> None:
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


def command_validate_pipeline() -> int:
    """Validate the public connector surface without network or database access."""

    try:
        report = validate_connector_contracts()
    except ConnectorContractError as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


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
    subparsers.add_parser("status", help="ดูสถานะ source และจำนวน record")
    subparsers.add_parser(
        "validate-pipeline",
        help="ตรวจ registry, connector entrypoint, grain, completeness และ privacy contract โดยไม่เรียก network",
    )
    args = parser.parse_args()
    if args.command == "init-db":
        initialize()
        print("database initialized")
        return 0
    if args.command == "ingest":
        return command_ingest(args)
    if args.command == "validate-pipeline":
        return command_validate_pipeline()
    return command_status()


if __name__ == "__main__":
    raise SystemExit(main())
