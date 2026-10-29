"""Measure stage: the measures as SQL over the Clean and Resolve tables.

members.sql: which entities each count measure counts, and in which provinces (measure_members).
values.sql: totals a source publishes, with the parts they add up from (measure_values).
universities.sql: the universities the sources tie each counted innovation, innovator and business to (university_members).
Reviewed counting exclusions (data/runtime/f2/decisions/counting.json) are loaded as counting_exclusions;
one whose records are gone is reported in counting_issues.

A refresh can rename what the SQL looks for (a metric, a category code, a role). Rather than publish a
smaller number, the stage then stops with the list of problems and writes nothing (check()).
"""

from __future__ import annotations

import math
from pathlib import Path

import duckdb

from .. import decisions as reviewed
from ..clean import DB_PATH, insert

HERE = Path(__file__).resolve().parent

COUNTED = ("C02_COMMUNITY", "C04_LISTED", "C08_ASSESSED_PEOPLE", "C08_INCREASED_PEOPLE", "C08_PARTICIPATING",
           "K01A", "K01B", "K03", "K04", "K05", "K07", "K12")
# Codes the SQL counts by: (table, column, value). None left means the source renamed it.
CODES = [("innovation_places", "role", "use"), ("innovation_readiness", "scale", "TRL"),
         ("people", "role", "community_innovator"), ("people", "role", "inventor"),
         ("cultural_records", "source", "cultural_map"), ("cultural_records", "category", "CS"),
         ("cultural_records", "category", "area"), ("operators", "source", "learning_area_based"),
         ("operators", "kind", "listed"), ("offerings", "kind", "listed"),
         ("reported_figures", "metric", "businesses_by_province"), ("reported_figures", "metric", "total_hh")]
LEARNING = "SELECT any_value(value) FROM reported_figures WHERE dataset = 'learning_dashboard' AND metric = "
PARTS = "SELECT sum(value) FROM measure_values WHERE measure_id = "
# A source total must add up to the total the source states itself: (what, sum of parts, source's total).
TOTALS = [
    ("K02 = PMUA headline", PARTS + "'K02'", "SELECT any_value(value) FROM reported_figures "
     "WHERE source = 'pmua_apptech' AND dataset = 'innovators_all' AND metric = 'headline'"),
    ("H01 = PMUA family headline", PARTS + "'H01'", "SELECT any_value(value) FROM reported_figures "
     "WHERE source = 'pmua_apptech' AND dataset = 'family_all' AND metric = 'headline'"),
    ("K09 = Learning totalEmplyeeAmount", PARTS + "'K09'", LEARNING + "'totalEmplyeeAmount'"),  # the source's spelling
    ("K10 workers = Learning totalEmployeeExpense", PARTS + "'K10' AND component = 'localEmployeeExpense'",
     LEARNING + "'totalEmployeeExpense'"),
    ("K10 suppliers = Learning totalResourceExpense", PARTS + "'K10' AND component = 'localResourceExpense'",
     LEARNING + "'totalResourceExpense'"),
    ("C10 suppliers = Learning totalResourceExpense", PARTS + "'C10_ALTERNATIVE' AND component = 'localResourceExpense'",
     LEARNING + "'totalResourceExpense'"),
    ("C10 excluded amount, one part", "SELECT count(*) FROM measure_values "
     "WHERE measure_id = 'C10_ALTERNATIVE' AND component = 'excludedResourceExpense'", "SELECT 1"),
]
C08_BREAKDOWNS = {"categories", "entityTypes", "geography", "provinces"}
UNIVERSITY_MEASURES = ("C02_COMMUNITY", "C04_LISTED", "K05")  # the university tab counts these
TRL_SOURCES = ("apptech_mru", "icommunity", "pmua_apptech", "rinmp")  # each states numeric readiness levels (K04)
# PMUA's family dashboard: H01 households by province, and national money and fiscal-year figures that publish shows
# as stated. These metrics are the only family figures published; its district and business-type cells never are.
FAMILY_ALL, FAMILY_YEARS = "family_all", {"family_2025": "2568", "family_2026": "2569"}  # year_filter = Thai fiscal year
FAMILY_MONEY = ("income_increase", "cost_reduction", "net_income_increase")
FAMILY_METRICS = ("headline", *FAMILY_MONEY)
# The page's money does not always add up to the baht (net vs its parts, fiscal years vs all years); a wider gap stops.
FAMILY_MONEY_SLACK_THB = 1


def run(db_path: Path = DB_PATH) -> dict[str, int]:
    con = duckdb.connect(str(db_path))
    con.begin()
    con.execute("""CREATE OR REPLACE TABLE counting_exclusions (
                       measure_id VARCHAR NOT NULL, source VARCHAR NOT NULL, record_id VARCHAR NOT NULL, reason VARCHAR)""")
    con.execute("""CREATE OR REPLACE TABLE counting_place_from (  -- an excluded record whose place another record takes
                       measure_id VARCHAR NOT NULL, source VARCHAR NOT NULL, record_id VARCHAR NOT NULL,
                       place_source VARCHAR NOT NULL, place_record_id VARCHAR NOT NULL)""")
    con.execute("""CREATE OR REPLACE TABLE counting_issues (  -- counting decisions whose records are gone
                       measure_id VARCHAR NOT NULL, decision_ref VARCHAR NOT NULL, issue VARCHAR NOT NULL, detail JSON)""")
    exclusions = reviewed.load("counting.json", {"exclusions": []})["exclusions"]
    insert(con, "counting_exclusions", [
        {"measure_id": x["measure"], "source": x["source"], "record_id": x["record_id"], "reason": x["reason"]}
        for x in exclusions])
    insert(con, "counting_place_from", [
        {"measure_id": x["measure"], "source": s, "record_id": r, "place_source": x["source"], "place_record_id": x["record_id"]}
        for x in exclusions for s, r in x.get("evidence_for", [])])
    insert(con, "counting_issues", _gone(con, exclusions))
    for name in ("members.sql", "values.sql", "universities.sql"):
        con.execute((HERE / name).read_text(encoding="utf-8"))
    problems = check(con)
    if problems:
        con.rollback()
        con.close()
        raise ValueError("Measure stopped, nothing written:\n- " + "\n- ".join(problems))
    counts = dict(con.execute(
        "SELECT measure_id, count(DISTINCT entity_id) FROM measure_members GROUP BY 1 ORDER BY 1").fetchall())
    counts |= dict(con.execute("""SELECT measure_id, max(total) FROM (
        SELECT measure_id, breakdown, sum(value) / any_value(divisor) AS total FROM measure_values GROUP BY ALL) GROUP BY 1""").fetchall())
    con.commit()
    con.close()
    return counts


def _gone(con, exclusions: list[dict]) -> list[dict]:
    """An excluded K07 listing that is no longer in the data (the exclusion then has no effect), or a family
    record taking its place that is gone (the exclusion still applies; that family no longer takes its place)."""
    offerings = set(con.execute("SELECT source, record_id FROM offerings").fetchall())
    families = set(con.execute("SELECT source, record_id FROM entity_members WHERE entity = 'offering_family'").fetchall())
    out = []
    for x in exclusions:
        head = {"measure_id": x["measure"], "decision_ref": x.get("ref") or x["record_id"]}
        if (x["source"], x["record_id"]) not in offerings:
            out.append({**head, "issue": "excluded_record_not_found_exclusion_has_no_effect",
                        "detail": {"excluded": [x["source"], x["record_id"]]}})
        missing = [[s, r] for s, r in x.get("evidence_for", []) if (s, r) not in families]
        if missing:
            out.append({**head, "issue": "evidence_records_not_found_exclusion_still_applies",
                        "detail": {"excluded": [x["source"], x["record_id"]], "missing": missing}})
    return out


def check(con) -> list[str]:
    """What would make a published number silently wrong after a refresh."""
    problems = []
    for measure in COUNTED:
        if not con.execute("SELECT count(*) FROM measure_members WHERE measure_id = ?", [measure]).fetchone()[0]:
            problems.append(f"{measure} counts nothing")
    for measure in UNIVERSITY_MEASURES:
        if not con.execute("SELECT count(*) FROM university_members WHERE measure_id = ?", [measure]).fetchone()[0]:
            problems.append(f"{measure}: no counted entity has a university any more (institution_names, universities.sql)")
    for source in TRL_SOURCES:
        if not con.execute("SELECT count(level) FROM innovation_readiness WHERE scale = 'TRL' AND source = ?",
                           [source]).fetchone()[0]:
            problems.append(f"{source} states no numeric TRL level any more (K04)")
    for table, column, value in CODES:
        if not con.execute(f"SELECT count(*) FROM {table} WHERE {column} = ?", [value]).fetchone()[0]:
            problems.append(f"no {table} row has {column} = {value!r} any more (renamed by the source?)")
    for what, parts, total in TOTALS:
        a, b = con.execute(parts).fetchone()[0], con.execute(total).fetchone()[0]
        if a is None or b is None or abs(a - b) > 0.005:  # money has two decimals
            problems.append(f"{what}: parts add up to {a}, the source states {b}")
    for (province,) in con.execute("""
            SELECT coalesce(m.member, t.dimension_value) FROM
                (SELECT member, sum(value) AS v FROM measure_values WHERE measure_id = 'K02' GROUP BY 1) m
            FULL JOIN (SELECT dimension_value, value FROM reported_figures WHERE source = 'pmua_apptech'
                       AND dataset = 'innovators_all' AND metric = 'total_inno') t ON t.dimension_value = m.member
            WHERE m.v IS DISTINCT FROM t.value ORDER BY 1""").fetchall():
        problems.append(f"K02 {province}: levels do not add up to the source's total_inno")
    sums = dict(con.execute("""SELECT breakdown, sum(value) FROM measure_values
                               WHERE measure_id = 'C08_REPORTED_BUSINESSES' GROUP BY 1""").fetchall())
    if set(sums) != C08_BREAKDOWNS or len(set(sums.values())) != 1:
        problems.append(f"C08_REPORTED_BUSINESSES: the four breakdowns should add up to one total, got {sums}")
    for (metric,) in con.execute("""SELECT DISTINCT metric FROM reported_figures WHERE dataset = 'learning_dashboard'
            AND metric LIKE 'businesses_by_%' AND metric NOT IN ('businesses_by_category', 'businesses_by_entity_type',
            'businesses_by_region', 'businesses_by_province') ORDER BY 1""").fetchall():
        problems.append(f"new Learning breakdown {metric}: decide how C08 shows it (values.sql)")
    return problems + household_problems(con)


def household_problems(con) -> list[str]:
    """H01 and the family figures publish shows: every province once, fiscal years adding up to all years, and
    money within FAMILY_MONEY_SLACK_THB of adding up."""
    problems = []
    for code, n in con.execute("""SELECT province_code, count(*) FROM measure_values WHERE measure_id = 'H01'
                                  GROUP BY 1 HAVING province_code IS NULL OR count(*) > 1 ORDER BY 1""").fetchall():
        problems.append(f"H01: {n} province rows with code {code} (an unmapped or repeated province)")
    for member, value in con.execute("SELECT member, value FROM measure_values WHERE measure_id = 'H01' ORDER BY ord").fetchall():
        if not _count(value):
            problems.append(f"H01 {member}: {value!r} households is not a whole number of zero or more")
    datasets = [FAMILY_ALL, *FAMILY_YEARS]
    figures = {(d, m): v for d, m, v in con.execute(
        f"""SELECT dataset, metric, any_value(value) FROM reported_figures WHERE source = 'pmua_apptech'
            AND dimension IS NULL AND dataset IN ({", ".join("?" * len(datasets))}) GROUP BY ALL""", datasets).fetchall()}
    missing = [f"{d} {m}" for d in datasets for m in FAMILY_METRICS
               if not isinstance(figures.get((d, m)), (int, float)) or not math.isfinite(figures[(d, m)])]
    if missing:
        return problems + [f"family dashboard figure missing or not a number: {', '.join(missing)}"]
    problems += [f"{d} headline: {figures[(d, 'headline')]!r} households is not a whole number of zero or more"
                 for d in datasets if not _count(figures[(d, "headline")])]
    years = sum(figures[(d, "headline")] for d in FAMILY_YEARS)
    if years != figures[(FAMILY_ALL, "headline")]:
        problems.append(f"family households: fiscal years add up to {years:,.0f}, all years state {figures[(FAMILY_ALL, 'headline')]:,.0f}")
    for d in datasets:
        gap = figures[(d, "net_income_increase")] - figures[(d, "income_increase")] - figures[(d, "cost_reduction")]
        if abs(gap) > FAMILY_MONEY_SLACK_THB:
            problems.append(f"{d}: net income increase is {gap:+,.0f} THB off income increase + cost reduction")
    for m in FAMILY_MONEY:
        gap = sum(figures[(d, m)] for d in FAMILY_YEARS) - figures[(FAMILY_ALL, m)]
        if abs(gap) > FAMILY_MONEY_SLACK_THB:
            problems.append(f"family {m}: fiscal years are {gap:+,.0f} THB off all years")
    return problems


def _count(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 and value == int(value)
