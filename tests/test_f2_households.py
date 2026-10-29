"""H01 and the PMUA family dashboard table: the Measure checks that stop a release, and the allowlist publish reads."""

from __future__ import annotations

import json
import math

import duckdb
import pytest

from tools.f2.measure import FAMILY_METRICS, HERE as MEASURE_DIR, household_problems
from tools.f2.publish import CONFIG, _family_figures, _households

SCHEMA = MEASURE_DIR.parent / "schema.sql"
# a small dashboard whose money is off by 1 THB in places, as PMUA's page is
FIGURES = {
    "family_all": {"headline": 30, "income_increase": 100, "cost_reduction": 50, "net_income_increase": 151},
    "family_2025": {"headline": 12, "income_increase": 60, "cost_reduction": 20, "net_income_increase": 80},
    "family_2026": {"headline": 18, "income_increase": 41, "cost_reduction": 30, "net_income_increase": 71},
}
PROVINCES = [("Bangkok", "10", 10), ("เชียงใหม่", "50", 20)]


def _db(figures=FIGURES, provinces=PROVINCES):
    con = duckdb.connect()
    con.execute(SCHEMA.read_text(encoding="utf-8"))
    rows = [("pmua_apptech", d, m, None, None, None, v, "ref") for d, metrics in figures.items() for m, v in metrics.items()]
    rows += [("pmua_apptech", "family_all", "total_hh", "province", name, code, v, "ref") for name, code, v in provinces]
    # cells publish must never read
    rows += [("pmua_apptech", "family_all", "districts.อำเภอเมือง", "province", "Bangkok", "10", 4, "ref"),
             ("pmua_apptech", "family_all", "business_types.กลุ่มทอผ้า", "province", "Bangkok", "10", 1, "ref")]
    con.executemany("INSERT INTO reported_figures VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    con.execute((MEASURE_DIR / "values.sql").read_text(encoding="utf-8"))
    return con


def _with(dataset: str, metric: str, value):
    return {d: {**m, metric: value} if d == dataset else m for d, m in FIGURES.items()}


def test_a_dashboard_within_one_baht_passes():
    con = _db()
    assert household_problems(con) == []
    assert con.execute("SELECT sum(value) FROM measure_values WHERE measure_id = 'H01'").fetchone()[0] == 30


@pytest.mark.parametrize("figures, provinces, problem", [
    (_with("family_all", "net_income_increase", 152), PROVINCES, "family_all: net income increase is +2 THB off"),
    (_with("family_2026", "income_increase", 43), PROVINCES, "family income_increase: fiscal years are +3 THB off"),
    (_with("family_2026", "headline", 19), PROVINCES, "fiscal years add up to 31, all years state 30"),
    (_with("family_2025", "cost_reduction", None), PROVINCES, "missing or not a number: family_2025 cost_reduction"),
    (_with("family_2025", "cost_reduction", math.nan), PROVINCES, "missing or not a number: family_2025 cost_reduction"),
    ({d: {k: v for k, v in m.items() if k != "headline"} for d, m in FIGURES.items()}, PROVINCES, "family_all headline"),
    (FIGURES, [*PROVINCES, ("กรุงเทพมหานคร", "10", 0)], "H01: 2 province rows with code 10"),
    (FIGURES, [("Atlantis", None, 30)], "H01: 1 province rows with code None"),
    (FIGURES, [("Bangkok", "10", 10.5), ("เชียงใหม่", "50", 19.5)], "H01 Bangkok: 10.5 households is not a whole number"),
    (FIGURES, [("Bangkok", "10", -10), ("เชียงใหม่", "50", 40)], "H01 Bangkok: -10.0 households is not a whole number"),
    (FIGURES, [("Bangkok", "10", None), ("เชียงใหม่", "50", 30)], "H01 Bangkok: None households is not a whole number"),
    (_with("family_2025", "headline", 12.5), PROVINCES, "family_2025 headline: 12.5 households is not a whole number"),
])
def test_what_stops_the_measure_stage(figures, provinces, problem):
    assert any(problem in p for p in household_problems(_db(figures, provinces)))


def test_publish_reads_only_the_allowlisted_national_figures():
    figures = _family_figures(_db())
    assert {(d, m) for d, m, _ in figures} == {(d, m) for d in FIGURES for m in FAMILY_METRICS}
    table = _households(json.loads(CONFIG.read_text(encoding="utf-8")), figures)
    assert [c["id"] for c in table["columns"]] == ["all", "2568", "2569"]
    assert {r["metric"]: r["values"] for r in table["rows"]}["net_income_increase"] == {"all": 151, "2568": 80, "2569": 71}
    assert "อำเภอ" not in json.dumps(table, ensure_ascii=False)


def test_publish_stops_on_a_missing_or_fractional_figure():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    figures = _family_figures(_db())
    with pytest.raises(SystemExit, match="family_2026 headline"):
        _households(config, [f for f in figures if f[:2] != ("family_2026", "headline")])
    with pytest.raises(SystemExit, match="not a whole number"):
        _households(config, [(d, m, v + 0.5 if m == "cost_reduction" else v) for d, m, v in figures])
