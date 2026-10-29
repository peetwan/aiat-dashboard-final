"""Offerings (K07): listed products and offerings found in text. Identity = same product form and
variant from the same producer.

- AtLocal lists many products twice, on its map and on its marketplace. A marketplace listing and a map
  listing are the same product when the title, the seller and the district agree and the pairing is
  one-to-one (one marketplace listing, one map listing) — the rule of the previous pipeline.
- Every other candidate pair (same or near-identical name) is queued: no rule was safe enough to
  separate or merge offerings, so the judge proposes and the user confirms (decided 2026-10-13).
  A pair is a candidate only when the producer could be the same: a shared seller/maker, the same
  source record, or the same district with no conflicting producers. "ไก่ทอด" from two shops in two
  places is two products, and the previous pipeline never compared those either.
"""

from __future__ import annotations

import difflib
import json
from collections import defaultdict
from itertools import combinations

from ..text import key

PREFIX, TABLE = "off", "offerings"


def nodes(con) -> list[tuple[str, str]]:
    return con.execute("""SELECT source, record_id FROM offerings
                          WHERE kind <> 'extracted' OR review_status = 'supported' ORDER BY ALL""").fetchall()


def _producers(con) -> dict[tuple, set]:
    """offering -> the resolved operator entities that sell or make it (operators are resolved first)."""
    out = defaultdict(set)
    for source, offering, entity in con.execute("""
            SELECT l.source, l.offering_record_id, m.entity_id FROM offering_operators l
            JOIN entity_members m ON m.entity = 'operator' AND m.source = l.source AND m.record_id = l.operator_record_id""").fetchall():
        out[source, offering].add(entity)
    return out


def _atlocal(con, producers):
    """Pair one marketplace listing with one map listing: same title, seller and district, one-to-one.
    First by the seller as the listing names it, then (for listings still unpaired) by the resolved
    seller, so that a reviewed seller alias still lets its two listings pair."""
    listings = [(rid, key(name), pc, dc) for rid, name, pc, dc in con.execute(
        """SELECT record_id, name, province_code, district_code FROM offerings WHERE source = 'atlocal' AND kind = 'listed'""").fetchall()
        if key(name) and pc and dc]
    written = dict(con.execute("""SELECT offering_record_id, operator_record_id FROM offering_operators
                                  WHERE source = 'atlocal' AND relationship = 'seller'""").fetchall())
    resolved = {rid: next(iter(e)) for (s, rid), e in producers.items() if s == "atlocal" and len(e) == 1}
    paired = set()
    for seller in (written, resolved):
        by_title = defaultdict(lambda: ([], []))
        for rid, name, pc, dc in listings:
            if rid in seller and rid not in paired:
                by_title[name, seller[rid], pc, dc][rid.startswith("product_map:")].append(rid)
        for markets, maps in by_title.values():
            if len(markets) == 1 and len(maps) == 1:
                paired |= {markets[0], maps[0]}
                yield ("atlocal", markets[0]), ("atlocal", maps[0]), "same", "atlocal_map_and_marketplace_listing"


def profiles(con, producers) -> dict[tuple, dict]:
    """name key, producers, the records it comes from and the districts of those records."""
    record_districts = defaultdict(set)
    for source, rid, dc in con.execute("""
            SELECT source, record_id, district_code FROM cultural_records WHERE district_code IS NOT NULL
            UNION ALL SELECT source, record_id, district_code FROM innovation_places WHERE role = 'use' AND district_code IS NOT NULL
            UNION ALL SELECT i.source, i.upstream_id, p.district_code FROM innovation_places p
                JOIN innovations i USING (source, record_id) WHERE p.role = 'use' AND p.district_code IS NOT NULL""").fetchall():
        record_districts[source, rid].add(dc)
    out = {}
    for source, rid, kind, name, dc, details in con.execute("""
            SELECT source, record_id, kind, name, district_code, details FROM offerings
            WHERE kind <> 'extracted' OR review_status = 'supported'""").fetchall():
        records = set(json.loads(details).get("source_records") or []) if kind == "extracted" and details else {rid}
        districts = {dc} if dc else set().union(*(record_districts.get((source, r), set()) for r in records))
        out[source, rid] = {"name": key(name), "producers": producers.get((source, rid), set()),
                            "records": {(source, r) for r in records}, "districts": districts}
    return out


def _could_be_same_producer(a: dict, b: dict) -> bool:
    if a["producers"] & b["producers"] or a["records"] & b["records"]:
        return True
    conflict = a["producers"] and b["producers"]
    return not conflict and bool(a["districts"] & b["districts"])


def pairs(con):
    producers = _producers(con)
    done = set()
    for a, b, outcome, rule in _atlocal(con, producers):
        done.add(tuple(sorted((a, b))))
        yield a, b, outcome, rule
    profs = profiles(con, producers)
    index = defaultdict(set)
    for k, p in profs.items():
        for i in range(len(p["name"]) - 2):
            index[p["name"][i:i + 3]].add(k)
    seen = set()
    for ks in index.values():
        if len(ks) > 200:
            continue
        for a, b in combinations(sorted(ks), 2):
            if (a, b) in seen or (a, b) in done:
                continue
            seen.add((a, b))
            pa, pb = profs[a], profs[b]
            na, nb = pa["name"], pb["name"]
            similar = na == nb or (min(len(na), len(nb)) >= 6 and difflib.SequenceMatcher(None, na, nb).ratio() >= 0.85)
            if similar and _could_be_same_producer(pa, pb):
                yield a, b, "queue", "same_name" if na == nb else "near_identical_name"
