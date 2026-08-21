from __future__ import annotations

import pytest

from app.catalog import load_catalog, load_ingestion_plans


# The originally reviewed acceptance set.  The catalog may grow past it, but
# none of these identities may disappear or be swapped for a different source
# while keeping the count — removal requires a conscious edit here.
BASELINE_SOURCE_IDS = frozenset(
    {
        "f1_sradss_ppaos",
        "f1_pppconnext",
        "f2_culturalmap_university",
        "f2_cultural_market_civil",
        "f2_icommunity",
        "f2_rmutdb",
        "f2_apptech_mtr",
        "f2_apptech_mru",
        "f2_target_household",
        "f2_learning_dashboard",
        "f2_learning_area_based",
        "f2_wallet_all_realtime",
        "f2_wallet_cluster_realtime",
        "f3_city_capital_open_data",
        "f3_nonthaburi_city_learning",
        "f3_ruamthiao_lamphun",
        "f3_ruamrian",
        "f3_ruamkhai",
        "f3_ruamjai_thungsong",
        "f3_healthcare_nonthaburi",
        "f3_ciap_smartcity",
        "f3_learning_city_platform",
        "f3_housing_portal",
        "f4_research_dashboard_psu",
        "spu_sukhothai_care",
        "spu_sukhothai_water",
        "spu_nsn_flood",
        "spu_rawangphai_uru",
    }
)


def test_catalog_covers_all_registry_sources_and_public_candidates():
    catalog = load_catalog()
    sources = catalog["sources"]
    source_ids = [source["source_id"] for source in sources]
    # The catalog may grow as the team registers new sources through the
    # canonical evidence workspace; growth is not pinned to a literal count —
    # that would fail CI for every legitimate new source.  But the original
    # reviewed identities must all remain present, not merely "at least 28
    # rows": count alone would let a baseline source vanish unnoticed.
    assert len(source_ids) == len(set(source_ids))
    assert len(BASELINE_SOURCE_IDS) == 28
    missing_baseline = BASELINE_SOURCE_IDS - set(source_ids)
    assert not missing_baseline, f"baseline sources missing from catalog: {sorted(missing_baseline)}"
    # Whether values may reach production is a policy lane decision, not a
    # frozen tally: the flag must agree with cloud_policy for every source.
    for source in sources:
        assert bool(source["production_values_allowed"]) == (
            source["cloud_policy"] == "team_approved_public"
        ), f"{source['source_id']}: production_values_allowed disagrees with cloud_policy"
    # The restricted lane stays an explicit, reviewed list: adding a source
    # here must be a conscious edit, never a side effect.
    assert {
        source["source_id"]
        for source in sources
        if source["cloud_policy"] == "restricted_local_only"
    } == {
        "f3_nonthaburi_city_learning",
        "f3_healthcare_nonthaburi",
    }
    apptech = next(source for source in catalog["sources"] if source["source_id"] == "f2_apptech_mtr")
    assert apptech["expected_record_count"] >= 1
    assert apptech["snapshot_origin_files"]
    assert all(
        path.startswith("data/staged/f2_apptech_mtr/")
        for path in apptech["snapshot_origin_files"]
    )


def test_executable_plans_never_include_restricted_sources():
    plans = load_ingestion_plans()["sources"]
    assert set(plans) == {
        "f1_sradss_ppaos",
        "f1_pppconnext",
        "f2_apptech_mtr",
        "f2_apptech_mru",
        "f2_target_household",
        "f2_learning_dashboard",
        "f2_learning_area_based",
        "f2_wallet_all_realtime",
        "f2_wallet_cluster_realtime",
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
