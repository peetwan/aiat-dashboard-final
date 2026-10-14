"""Activities (events reported in posts and pages). Each reviewed occurrence is one row.

Two activities are a candidate (queued) when their dates overlap and they share a venue province;
otherwise they are different occurrences. The previous pipeline kept all 50 apart, 4 of them by review.
"""

from __future__ import annotations

import json
from itertools import combinations

PREFIX, TABLE = "act", "activities"


def nodes(con) -> list[tuple[str, str]]:
    return con.execute("""SELECT source, record_id FROM activities
                          WHERE kind <> 'extracted' OR review_status = 'supported' ORDER BY ALL""").fetchall()


def pairs(con):
    rows = []
    for source, rid, start, end, venues in con.execute("""SELECT source, record_id, start_date, coalesce(end_date, start_date),
            venues FROM activities WHERE (kind <> 'extracted' OR review_status = 'supported') AND start_date IS NOT NULL""").fetchall():
        provinces = {v.get("province_code") for v in json.loads(venues or "[]")} - {None}
        rows.append(((source, rid), start, end, provinces))
    for (a, sa, ea, pa), (b, sb, eb, pb) in combinations(sorted(rows), 2):
        if sa <= eb and sb <= ea and pa & pb:
            yield a, b, "queue", "overlapping_dates_same_province"
