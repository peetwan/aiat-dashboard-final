"""Measure stage: the measures as SQL over the Clean and Resolve tables.

members.sql: which entities each count measure counts, and in which provinces (measure_members).
values.sql: totals a source publishes, with the parts they add up from (measure_values).
Reviewed counting exclusions (data/runtime/f2/decisions/counting.json) are loaded as counting_exclusions.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from .. import decisions as reviewed
from ..clean import DB_PATH, insert

HERE = Path(__file__).resolve().parent


def run(db_path: Path = DB_PATH) -> dict[str, int]:
    con = duckdb.connect(str(db_path))
    con.begin()
    con.execute("""CREATE OR REPLACE TABLE counting_exclusions (
                       measure_id VARCHAR NOT NULL, source VARCHAR NOT NULL, record_id VARCHAR NOT NULL, reason VARCHAR)""")
    con.execute("""CREATE OR REPLACE TABLE counting_place_from (  -- an excluded record whose place another record takes
                       measure_id VARCHAR NOT NULL, source VARCHAR NOT NULL, record_id VARCHAR NOT NULL,
                       place_source VARCHAR NOT NULL, place_record_id VARCHAR NOT NULL)""")
    exclusions = reviewed.load("counting.json", {"exclusions": []})["exclusions"]
    insert(con, "counting_exclusions", [
        {"measure_id": x["measure"], "source": x["source"], "record_id": x["record_id"], "reason": x["reason"]}
        for x in exclusions])
    insert(con, "counting_place_from", [
        {"measure_id": x["measure"], "source": s, "record_id": r, "place_source": x["source"], "place_record_id": x["record_id"]}
        for x in exclusions for s, r in x.get("evidence_for", [])])
    for name in ("members.sql", "values.sql"):
        con.execute((HERE / name).read_text(encoding="utf-8"))
    counts = dict(con.execute(
        "SELECT measure_id, count(DISTINCT entity_id) FROM measure_members GROUP BY 1 ORDER BY 1").fetchall())
    counts |= dict(con.execute("""SELECT measure_id, max(total) FROM (
        SELECT measure_id, breakdown, sum(value) / any_value(divisor) AS total FROM measure_values GROUP BY ALL) GROUP BY 1""").fetchall())
    con.commit()
    con.close()
    return counts
