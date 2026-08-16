from __future__ import annotations

import argparse
import json

from sqlalchemy import func, select

from app.catalog import load_catalog, sync_catalog
from app.database import SessionLocal, init_db
from app.ingestion import IngestionPipeline, PolicyViolation
from app.models import DashboardRecord, IngestionRun, Source


def initialize() -> None:
    init_db()
    with SessionLocal() as session:
        sync_catalog(session)


def command_ingest(args: argparse.Namespace) -> int:
    initialize()
    source_ids = args.source
    if args.all:
        source_ids = [
            item["source_id"]
            for item in load_catalog()["sources"]
            if item["cloud_policy"] != "restricted_local_only"
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
        return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AIAT dashboard database workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="สร้างตารางและ sync source catalog")
    ingest = subparsers.add_parser("ingest", help="ดึง API หรือ replay snapshot เข้า database")
    ingest.add_argument("--source", action="append", default=[])
    ingest.add_argument("--all", action="store_true")
    ingest.add_argument("--strategy", choices=["auto", "api", "snapshot"], default="auto")
    subparsers.add_parser("status", help="ดูสถานะ source และจำนวน record")
    args = parser.parse_args()
    if args.command == "init-db":
        initialize()
        print("database initialized")
        return 0
    if args.command == "ingest":
        return command_ingest(args)
    return command_status()


if __name__ == "__main__":
    raise SystemExit(main())
