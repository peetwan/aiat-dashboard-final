from __future__ import annotations

import pytest

from app.catalog import load_catalog, load_ingestion_plans


def test_catalog_covers_all_registry_sources_and_public_candidates():
    catalog = load_catalog()
    source_ids = {source["source_id"] for source in catalog["sources"]}
    assert len(source_ids) == 28
    assert sum(source["production_values_allowed"] for source in catalog["sources"]) == 11
    assert {
        source["source_id"]
        for source in catalog["sources"]
        if source["cloud_policy"] == "restricted_local_only"
    } == {
        "f2_target_household",
        "f2_wallet_all_realtime",
        "f2_wallet_cluster_realtime",
        "f3_nonthaburi_city_learning",
        "f3_healthcare_nonthaburi",
    }
    apptech = next(source for source in catalog["sources"] if source["source_id"] == "f2_apptech_mtr")
    assert apptech["expected_record_count"] == 630
    assert apptech["snapshot_origin_files"] == [
        "data/staged/f2_apptech_mtr/20260817T_public_api_silver_07/silver/apptech_public_innovation.jsonl"
    ]


def test_executable_plans_never_include_restricted_sources():
    plans = load_ingestion_plans()["sources"]
    assert set(plans) == {
        "f1_sradss_ppaos",
        "f2_apptech_mtr",
        "f2_apptech_mru",
        "f2_learning_dashboard",
        "f2_learning_area_based",
        "f3_housing_portal",
    }
    executable_urls = []
    for plan in plans.values():
        executable_urls.extend(item["url"] for item in plan.get("requests", []))
        executable_urls.extend(item["url"] for item in plan.get("datasets", []) if "url" in item)
        if "url" in plan:
            executable_urls.append(plan["url"])
        if "package_show_url" in plan:
            executable_urls.append(plan["package_show_url"])
    serialized = " ".join(executable_urls).lower()
    assert "data_household_detail.php" not in serialized
    assert "/backend/ajax/auth/" not in serialized
    assert all(
        plan.get("connector", "").startswith("app.connectors.")
        for plan in plans.values()
    )


def test_postgres_startup_sync_holds_one_advisory_lock(monkeypatch):
    import app.main as main

    events: list[str] = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, statement, parameters):
            sql = str(statement)
            assert parameters == {"lock_id": main.STARTUP_SYNC_LOCK_ID}
            if "pg_advisory_unlock" in sql:
                events.append("unlock")
            elif "pg_advisory_lock" in sql:
                events.append("lock")
            else:  # pragma: no cover - guards the exact lock-only contract
                raise AssertionError(sql)

        def commit(self):
            events.append("commit")

    class FakeEngine:
        dialect = type("Dialect", (), {"name": "postgresql"})()

        def __init__(self):
            self.connection = FakeConnection()

        def connect(self):
            return self.connection

    class FakeSessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_):
            return False

    fake_engine = FakeEngine()
    monkeypatch.setattr(main, "engine", fake_engine)
    monkeypatch.setattr(
        main,
        "SessionLocal",
        lambda **kwargs: (
            FakeSessionContext()
            if kwargs.get("bind") is fake_engine.connection
            else pytest.fail("PostgreSQL startup session was not bound to the locked connection")
        ),
    )
    monkeypatch.setattr(main, "sync_catalog", lambda _: events.append("catalog"))
    monkeypatch.setattr(
        main,
        "sync_public_artifacts",
        lambda _: events.append("public_artifacts"),
    )
    monkeypatch.setattr(
        main,
        "sync_spatial_layers",
        lambda _: events.append("spatial_layers"),
    )
    monkeypatch.setattr(
        main,
        "sync_housing_demand",
        lambda _: events.append("housing_demand"),
    )

    main._sync_serving_database()

    assert events == [
        "lock",
        "commit",
        "catalog",
        "public_artifacts",
        "spatial_layers",
        "housing_demand",
        "unlock",
        "commit",
    ]


def test_postgres_startup_sync_releases_lock_when_seed_fails(monkeypatch):
    import app.main as main

    statements: list[str] = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, statement, _parameters):
            statements.append(str(statement))

        def commit(self):
            statements.append("COMMIT")

    connection = FakeConnection()
    fake_engine = type(
        "FakeEngine",
        (),
        {
            "dialect": type("Dialect", (), {"name": "postgresql"})(),
            "connect": lambda _: connection,
        },
    )()

    class FakeSessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(main, "engine", fake_engine)
    monkeypatch.setattr(main, "SessionLocal", lambda **_: FakeSessionContext())
    monkeypatch.setattr(main, "sync_catalog", lambda _: None)

    def fail_sync(_):
        raise RuntimeError("seed failed")

    monkeypatch.setattr(main, "sync_public_artifacts", fail_sync)

    with pytest.raises(RuntimeError, match="seed failed"):
        main._sync_serving_database()

    assert "pg_advisory_lock" in statements[0]
    assert statements[1] == "COMMIT"
    assert "pg_advisory_unlock" in statements[-2]
    assert statements[-1] == "COMMIT"
