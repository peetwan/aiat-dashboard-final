"""The university tab's counts (measure/universities.sql + publish._universities) on a small made-up database."""

from __future__ import annotations

import json
from types import SimpleNamespace

import duckdb

from tools.f2 import institutions
from tools.f2.measure import HERE as MEASURE_SQL
from tools.f2.publish import CONFIG, _universities

SOURCE_IDS = {"rinmp": "f2_apptech_mtr", "pmua_apptech": "f2_target_household", "icommunity": "f2_icommunity",
              "apptech_mru": "f2_apptech_mru", "learning_area_based": "f2_learning_area_based", "atlocal": "f2_cultural_market_civil"}


def _database() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE innovations (source VARCHAR, record_id VARCHAR, upstream_id VARCHAR, institution VARCHAR);
        CREATE TABLE people (source VARCHAR, record_id VARCHAR, role VARCHAR, institution VARCHAR);
        CREATE TABLE operators (source VARCHAR, record_id VARCHAR, details JSON);
        CREATE TABLE entity_members (entity VARCHAR, entity_id VARCHAR, source VARCHAR, record_id VARCHAR);
        CREATE TABLE measure_members (measure_id VARCHAR, entity VARCHAR, entity_id VARCHAR, province_code VARCHAR);
        CREATE TABLE institution_names (raw VARCHAR, university VARCHAR, university_group VARCHAR);
        INSERT INTO innovations VALUES
            ('rinmp', 'r1', 'U1', 'มทร.ศรีวิชัย'),                                         -- inn_a: one university, two spellings
            ('pmua_apptech', 'p1', 'U1', 'มหาวิทยาลัยเทคโนโลยีราชมงคลศรีวิชัย วิทยาเขตตรัง'),
            ('pmua_apptech', 'p2', 'U2', 'มรภ.สงขลา'),                                     -- inn_b: two universities, two groups
            ('icommunity', 'i1', 'U2', 'มหาวิทยาลัยทักษิณ'),
            ('rinmp', 'r2', 'U3', 'มทร.ล้านนา'),                                           -- inn_c: two universities, one group
            ('pmua_apptech', 'p3', 'U3', 'มทร.ศรีวิชัย'),
            ('pmua_apptech', 'p4', 'U4', NULL);                                             -- inn_d: no university
        INSERT INTO people VALUES
            ('icommunity', 'pc1', 'community_innovator', 'มรภ.สงขลา'),                     -- per_a counts
            ('icommunity', 'pc2', 'researcher', 'มรภ.สงขลา'),                              -- per_b: not by a researcher row
            ('apptech_mru', 'pc3', 'inventor', NULL);
        INSERT INTO operators VALUES
            ('learning_area_based', 'o1', '{"research_unit": "มหาวิทยาลัยทักษิณ"}'),       -- op_a: research unit
            ('pmua_apptech', 'o2', '{"innovation_upstream_ids": ["U2"]}'),                -- op_b: PMUA U2 = สงขลา
            ('icommunity', 'o3', '{"innovation_upstream_ids": ["U2"]}'),                  -- op_c: iCommunity U2 = ทักษิณ
            ('atlocal', 'o4', '{"research_unit": "มหาวิทยาลัยทักษิณ"}');                   -- op_d: not a Learning unit
        INSERT INTO entity_members VALUES
            ('innovation', 'inn_a', 'rinmp', 'r1'), ('innovation', 'inn_a', 'pmua_apptech', 'p1'),
            ('innovation', 'inn_b', 'pmua_apptech', 'p2'), ('innovation', 'inn_b', 'icommunity', 'i1'),
            ('innovation', 'inn_c', 'rinmp', 'r2'), ('innovation', 'inn_c', 'pmua_apptech', 'p3'),
            ('innovation', 'inn_d', 'pmua_apptech', 'p4'),
            ('person', 'per_a', 'icommunity', 'pc1'), ('person', 'per_b', 'icommunity', 'pc2'),
            ('person', 'per_b', 'apptech_mru', 'pc3'),
            ('operator', 'op_a', 'learning_area_based', 'o1'), ('operator', 'op_b', 'pmua_apptech', 'o2'),
            ('operator', 'op_c', 'icommunity', 'o3'), ('operator', 'op_d', 'atlocal', 'o4');
        INSERT INTO measure_members VALUES
            ('C04_LISTED', 'innovation', 'inn_a', '90'), ('C04_LISTED', 'innovation', 'inn_a', '80'),
            ('C04_LISTED', 'innovation', 'inn_b', '90'), ('C04_LISTED', 'innovation', 'inn_c', '50'),
            ('C04_LISTED', 'innovation', 'inn_d', NULL), ('K04', 'innovation', 'inn_a', '90'),
            ('C02_COMMUNITY', 'person', 'per_a', NULL), ('C02_COMMUNITY', 'person', 'per_b', NULL),
            ('K05', 'operator', 'op_a', NULL), ('K05', 'operator', 'op_b', NULL),
            ('K05', 'operator', 'op_c', NULL), ('K05', 'operator', 'op_d', NULL);
    """)
    names = institutions.rows(n for (n,) in con.execute(
        "SELECT institution FROM innovations UNION SELECT institution FROM people").fetchall())
    con.executemany("INSERT INTO institution_names VALUES (?, ?, ?)",
                    [[r["raw"], r["university"], r["university_group"]] for r in names])
    con.execute((MEASURE_SQL / "universities.sql").read_text(encoding="utf-8"))
    return con


def test_university_counts_count_entities_once_per_university_and_group():
    con = _database()
    rows = con.execute("SELECT measure_id, entity_id, university, university_group, source "
                       "FROM university_members ORDER BY ALL").fetchall()
    places = con.execute("SELECT entity_id, province_code FROM measure_members "
                         "WHERE measure_id = 'C04_LISTED' AND province_code IS NOT NULL").fetchall()
    everyone = {m: {e for (e,) in con.execute("SELECT DISTINCT entity_id FROM measure_members WHERE measure_id = ?",
                                               [m]).fetchall()} for m in ("C04_LISTED", "K04", "C02_COMMUNITY", "K05")}
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    doc, key, sources = _universities(config, SimpleNamespace(everyone=everyone), rows, places, SOURCE_IDS, {})
    by_name = {u["name_th"]: u for u in doc["universities"].values()}

    assert {name: u["counts"] for name, u in by_name.items()} == {
        "มหาวิทยาลัยเทคโนโลยีราชมงคลศรีวิชัย": {"C04_LISTED": 2, "K04": 1, "C02_COMMUNITY": 0, "K05": 0},
        "มหาวิทยาลัยเทคโนโลยีราชมงคลล้านนา": {"C04_LISTED": 1, "K04": 0, "C02_COMMUNITY": 0, "K05": 0},
        "มหาวิทยาลัยราชภัฏสงขลา": {"C04_LISTED": 1, "K04": 0, "C02_COMMUNITY": 1, "K05": 1},
        "มหาวิทยาลัยทักษิณ": {"C04_LISTED": 1, "K04": 0, "C02_COMMUNITY": 0, "K05": 2},
    }
    assert {g: v["counts"] for g, v in doc["groups"].items()} == {
        "rajamangala": {"C04_LISTED": 2, "K04": 1, "C02_COMMUNITY": 0, "K05": 0},  # inn_c once, not once per university
        "rajabhat": {"C04_LISTED": 1, "K04": 0, "C02_COMMUNITY": 1, "K05": 1},
        "university": {"C04_LISTED": 1, "K04": 0, "C02_COMMUNITY": 0, "K05": 2},
        "other": {"C04_LISTED": 0, "K04": 0, "C02_COMMUNITY": 0, "K05": 0},
    }
    assert doc["coverage"] == {"C04_LISTED": {"with_university": 3, "counted": 4}, "K04": {"with_university": 1, "counted": 1},
                               "C02_COMMUNITY": {"with_university": 1, "counted": 2},
                               "K05": {"with_university": 3, "counted": 4}}
    srivijaya = by_name["มหาวิทยาลัยเทคโนโลยีราชมงคลศรีวิชัย"]
    assert srivijaya["item_ids"] == {"C04_LISTED": ["inn_a", "inn_c"]}
    assert srivijaya["innovation_provinces"] == [{"province_code": "50", "count": 1}, {"province_code": "80", "count": 1},
                                                 {"province_code": "90", "count": 1}]
    assert srivijaya["innovation_sources"] == [{"source_id": "f2_apptech_mtr", "count": 1},
                                               {"source_id": "f2_target_household", "count": 2}]
    assert key == "f2/universities"
    assert sources == ["f2_apptech_mtr", "f2_icommunity", "f2_learning_area_based", "f2_target_household"]
