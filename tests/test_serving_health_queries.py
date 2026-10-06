from __future__ import annotations

from sqlalchemy import event

from app import main
from app.catalog import load_catalog, sync_catalog
from app.database import SessionLocal, engine
from app.models import DashboardRecord


def test_health_batches_counts_and_still_detects_disallowed_candidate_records(monkeypatch):
    monkeypatch.setattr(main, "SPATIAL_DATABASE_REQUIRED", False)
    monkeypatch.setattr(main, "DEMAND_DATABASE_REQUIRED", False)
    catalog = load_catalog()["sources"]
    approved = next(row for row in catalog if row["production_values_allowed"])
    restricted = next(row for row in catalog if not row["production_values_allowed"])
    with SessionLocal() as session:
        sync_catalog(session)
        for number, source in enumerate([approved, approved, restricted]):
            session.add(DashboardRecord(
                source_id=source["source_id"], dataset_key="fixture",
                source_record_id=str(number), record_hash=str(number) * 64, payload={},
            ))
        session.commit()
        statements = []
        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(engine, "before_cursor_execute", capture)
        try:
            result = main._serving_contract_snapshot(session)
        finally:
            event.remove(engine, "before_cursor_execute", capture)

    assert result["source_total"] == len(catalog)
    assert result["approved_total"] == sum(row["production_values_allowed"] for row in catalog)
    assert result["restricted_source_total"] == sum(
        row["cloud_policy"] == "restricted_local_only" for row in catalog
    )
    endpoints = [endpoint for row in catalog for endpoint in row.get("endpoints", [])]
    assert result["endpoint_total"] == len(endpoints)
    assert result["runtime_endpoint_total"] == sum(
        row["runtime_enabled"] and not row["restricted"] for row in endpoints
    )
    assert result["approved_operational_records"] == 2
    assert result["disallowed_operational_records"] == 1
    assert result["complete"] is False
    # Previously 15 SELECTs; the same fail-closed contract now takes 9.
    assert len(statements) <= 9
    record_queries = [sql for sql in statements if "dashboard_records" in sql]
    assert len(record_queries) == 1
    assert "payload" not in record_queries[0]
