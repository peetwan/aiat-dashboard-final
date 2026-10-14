"""Cultural records: Cultural Map subjects (CD-…) and AtLocal programme areas.

Cultural Map sometimes records one subject twice (a temple, a performer); AtLocal's areas can be a
Cultural Map subject. No rule merges or separates them: the previous pipeline merged only reviewed
pairs, and its reviews (149 + 3) are decisions. A pair is queued when, in the same district, the titles
are the same or nearly the same (no differing numbers) and the main category agrees (AtLocal areas have
none). "ข้าวหลาม" in two districts, or a temple and a ritual held at it, are different records.
"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from itertools import combinations

from ..text import key

PREFIX, TABLE = "cul", "cultural_records"


def nodes(con) -> list[tuple[str, str]]:
    return con.execute("SELECT source, record_id FROM cultural_records ORDER BY ALL").fetchall()


def pairs(con):
    by_district = defaultdict(list)
    for source, rid, title, category, dc in con.execute(
            "SELECT source, record_id, title, category, district_code FROM cultural_records WHERE district_code IS NOT NULL").fetchall():
        if key(title):
            by_district[dc].append(((source, rid), key(title), None if category == "area" else category,
                                    set(re.findall(r"\d+", title))))
    for records in by_district.values():
        for (a, ta, ca, na), (b, tb, cb, nb) in combinations(sorted(records), 2):
            if ca and cb and ca != cb:
                continue
            if ta == tb:
                yield a, b, "queue", "same_title_same_district"
            elif na == nb and min(len(ta), len(tb)) >= 6 and difflib.SequenceMatcher(None, ta, tb).ratio() >= 0.9:
                yield a, b, "queue", "similar_title_same_district"
