"""The innovation tab's follow-up evidence: how publish ties reviewed links and source fields to an innovation, and how
the API filters and counts it. Small synthetic inputs; the API on the published release is in test_f2_api.py."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

import duckdb
import pytest

from app.f2_data import F2InvalidQuery, _follow_up_summary, _innovation_filter
from tools.f2.publish import CONFIG
from tools.f2.publish.details import follow_up, linked_innovations

FOLLOW_UP = json.loads(CONFIG.read_text(encoding="utf-8"))["innovations"]
SOURCE_ID = {"rinmp": "f2_apptech_mtr", "icommunity": "f2_icommunity", "apptech_mru": "f2_apptech_mru"}


class Ctx:
    """The parts of publish's Context that the follow-up builders use."""

    def __init__(self, con, entity_of):
        self.con, self.entity_of, self.skipped_links = con, entity_of, []
        self.source_id = SOURCE_ID
        self.fetched_at = {s: datetime(2026, 10, 12, 12, tzinfo=timezone.utc) for s in SOURCE_ID}
        self.follow_up = FOLLOW_UP

    def rows(self, sql, *params):
        cursor = self.con.execute(sql, list(params))
        return [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]


def _links_db():
    con = duckdb.connect()
    con.execute("CREATE TABLE innovations (source VARCHAR, record_id VARCHAR, upstream_id VARCHAR)")
    con.execute("CREATE TABLE operators (source VARCHAR, record_id VARCHAR, kind VARCHAR, details JSON)")
    con.execute("CREATE TABLE offerings (source VARCHAR, record_id VARCHAR, kind VARCHAR, details JSON)")
    con.executemany("INSERT INTO innovations VALUES (?, ?, ?)", [
        ("rinmp", "r1", "u1"), ("icommunity", "g1:u2", "u2"), ("icommunity", "g2:u2", "u2"), ("icommunity", "g1:u1", "u1")])
    links = lambda *ids: json.dumps({"innovation_upstream_ids": list(ids)})
    con.executemany("INSERT INTO operators VALUES (?, ?, ?, ?)", [
        ("rinmp", "op1", "extracted", links("u1")),       # kept by Resolve -> linked
        ("rinmp", "op2", "extracted", links("u1")),       # not kept by Resolve -> ignored
        ("rinmp", "op3", "listed", links("u1")),          # a source field, not a review -> ignored
        ("icommunity", "op4", "extracted", links("u2"))])  # u2 is two innovations -> skipped
    con.executemany("INSERT INTO offerings VALUES (?, ?, ?, ?)", [("icommunity", "of1", "extracted", links("u1"))])
    entity_of = {("innovation", "rinmp", "r1"): "inn_a", ("innovation", "icommunity", "g1:u1"): "inn_a",
                 ("innovation", "icommunity", "g1:u2"): "inn_b", ("innovation", "icommunity", "g2:u2"): "inn_c",
                 ("operator", "rinmp", "op1"): "op_a", ("operator", "rinmp", "op3"): "op_c",
                 ("operator", "icommunity", "op4"): "op_d", ("offering", "icommunity", "of1"): "of_a"}
    return Ctx(con, entity_of)


def test_reviewed_links_need_both_ends_and_one_innovation():
    ctx = _links_db()
    assert linked_innovations(ctx) == {("inn_a", "rinmp"), ("inn_a", "icommunity")}
    assert len(ctx.skipped_links) == 1 and "which is 2 innovations" in ctx.skipped_links[0]


def _evidence(members, k04=(), **overrides):
    records = {
        ("rinmp", "r1"): {"details": json.dumps({"source_updated_at": "2026-05-08T06:04:16"})},
        ("rinmp", "r2"): {"details": json.dumps({"source_updated_at": "2026-12-01T00:00:00"})},  # after the fetch
        ("icommunity", "c1"): {"details": json.dumps({"project_code": "A11F660043-01"})},
        ("apptech_mru", "m1"): {"details": "{}"},
    }
    readiness = defaultdict(list, {("rinmp", "r1"): [{"scale": "TRL", "level": 8}], ("icommunity", "c1"): [{"scale": "TRL", "level": 6}],
                 ("rinmp", "r2"): [{"scale": "TRL", "level": None}], ("apptech_mru", "m1"): [{"scale": "ATL", "level": 3}]})
    places = defaultdict(list, {("icommunity", "c1"): [{"province_code": "92"}], ("rinmp", "r1"): [{"province_code": None}]})
    ctx = Ctx(None, {})
    ctx.follow_up = overrides.get("config", FOLLOW_UP)
    return follow_up(ctx, "inn_a", members, records, readiness, places, overrides.get("linked", set()), set(k04))


def test_each_source_keeps_its_own_evidence():
    got = _evidence([("rinmp", "r1"), ("icommunity", "c1")], k04={"inn_a"}, linked={("inn_a", "icommunity")})
    assert got == {"f2_apptech_mtr": {"trl": [8], "k04": True, "updated": "2026-05-08"},
                   "f2_icommunity": {"trl": [6], "use_area": True, "province_codes": ["92"], "linked": True,
                                     "project_codes": ["A11F660043-01"]}}
    # a date after the fetch is not a date the record was changed; a source with nothing found keeps an empty entry
    assert _evidence([("rinmp", "r2"), ("apptech_mru", "m1")]) == {"f2_apptech_mru": {}, "f2_apptech_mtr": {}}


def test_follow_up_stops_on_a_k04_mismatch_or_a_field_the_config_says_a_source_lacks():
    with pytest.raises(SystemExit, match="K04 membership"):
        _evidence([("rinmp", "r1")])
    narrowed = {**FOLLOW_UP, "evidence": [{**e, "source_ids": ["f2_apptech_mru"]} if e["id"] == "project" else e
                                          for e in FOLLOW_UP["evidence"]]}
    with pytest.raises(SystemExit, match="does not carry"):
        _evidence([("icommunity", "c1")], config=narrowed)


ITEMS = [
    {"source_ids": ["f2_apptech_mtr", "f2_icommunity"], "university_ids": ["uni_a"],
     "follow_up": {"f2_apptech_mtr": {"trl": [8], "k04": True, "updated": "2026-05-08"},
                   "f2_icommunity": {"trl": [5], "use_area": True, "project_codes": ["X1"]}}},
    {"source_ids": ["f2_apptech_mru"], "university_ids": [], "follow_up": {"f2_apptech_mru": {}}},
]


def _keep(universities=("uni_a",), **filters):
    keep = _innovation_filter(FOLLOW_UP, dict.fromkeys(universities, {}),
                              **{k: filters.get(k) for k in ("university", "trl", "source", "evidence")})
    return [i for i, item in enumerate(ITEMS) if keep(item)]


def test_filters_read_only_the_selected_source():
    assert _keep(evidence="use_area") == [0]
    assert _keep(source="f2_apptech_mtr", evidence="use_area") == []  # the area is iCommunity's, not RINMP's
    assert _keep(trl="4-6") == [0] and _keep(trl="7-9") == [0]        # stated levels differ: in both bands
    assert _keep(source="f2_apptech_mtr", trl="4-6") == []
    assert _keep(trl="none") == [1]
    assert _keep(university="uni_a") == [0]
    assert _keep(source="f2_apptech_mru") == [1]


@pytest.mark.parametrize("filters", [{"university": "uni_x"}, {"trl": "10"}, {"source": "f2_learning_dashboard"},
                                     {"evidence": "still_used"}])
def test_unknown_filter_values_are_refused(filters):
    with pytest.raises(F2InvalidQuery):
        _keep(**filters)


def test_summary_counts_only_innovations_from_sources_that_carry_the_field():
    rows = {row["id"]: (row["found"], row["eligible"]) for row in _follow_up_summary(ITEMS, FOLLOW_UP, None)["evidence"]}
    assert rows == {"use_area": (1, 1), "k04": (1, 2), "linked": (0, 2), "project": (1, 1), "updated": (1, 1)}
    scoped = {row["id"]: row["eligible"] for row in _follow_up_summary(ITEMS[:1], FOLLOW_UP, "f2_apptech_mtr")["evidence"]}
    assert scoped["project"] == 0 and scoped["updated"] == 1
