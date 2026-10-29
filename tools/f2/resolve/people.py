"""People: one row per person per record. Names are never sent to an LLM, so people are matched by rules
and the user only.

Resolved: the roles a measure can count (community innovators, researchers, inventors, owners, the
cultural entrepreneurs reviewers found). Informants, recorders, RINMP collectors (the accounts that
registered technologies) and project / site team members are not counted anywhere and stay one row each.

Policy (agreed 2026-10-13, the previous pipeline's):
- the source's own person id (same id space) -> same;
- exact full name (title removed) + compatible institution or shared work -> same;
- exact full name, but the titles state different sexes (นาย vs นาง/นางสาว) -> different;
- exact full name without shared context, or a spelling variant of the name -> queue;
- a different first name -> not a candidate.
"""

from __future__ import annotations

import difflib
from collections import defaultdict
from itertools import combinations

from ..text import key
from .innovations import _institution

PREFIX, TABLE = "per", "people"
NOT_RESOLVED = ("informant", "recorder", "collector", "site_team", "project_team_member")
# Which of a source's id spaces a person_ref belongs to.
ID_SPACE = {"community_innovator": "innovator", "cultural_product_operator": "innovator", "researcher": "researcher",
            "owner": "account"}


def nodes(con) -> list[tuple[str, str]]:
    return con.execute(f"""SELECT source, record_id FROM people WHERE role NOT IN {NOT_RESOLVED}
                           AND (kind <> 'extracted' OR review_status = 'supported') ORDER BY ALL""").fetchall()


def profiles(con) -> dict[tuple, dict]:
    innovation_entity = {(s, r): e for e, s, r in con.execute(
        "SELECT entity_id, source, record_id FROM entity_members WHERE entity = 'innovation'").fetchall()}
    wanted = set(nodes(con))
    out = {}
    for source, rid, role, name, sex, institution, ref, about_kind, about in con.execute(
            "SELECT source, record_id, role, name, sex, institution, person_ref, about_kind, about_record_id FROM people").fetchall():
        if (source, rid) not in wanted:
            continue
        out[source, rid] = {
            "name": " ".join(key(w) for w in name.split()), "sex": sex,
            "record_name": (source, about, key(name)) if about_kind == "innovation" else None,
            "inst": {_institution(institution)} - {""},
            "id": (source, ID_SPACE.get(role, role), ref) if ref else None,
            "works": {innovation_entity[source, about]} if about_kind == "innovation" and (source, about) in innovation_entity else set(),
        }
    return out


def _institutions_agree(a: set, b: set) -> bool:
    return any(x == y or (min(len(x), len(y)) >= 6 and (x in y or y in x)) for x in a for y in b)


def decide(a: dict, b: dict) -> tuple[str, str]:
    """a, b: two persons (units of rows) whose names are the same or nearly the same."""
    if a["sexes"] and b["sexes"] and not a["sexes"] & b["sexes"]:
        return "different", "titles_state_different_sexes"
    if not a["names"] & b["names"]:
        return "queue", "spelling_variant"
    if _institutions_agree(a["inst"], b["inst"]):
        return "same", "same_name_and_institution"
    if a["works"] & b["works"] or a["coauthors"] & b["coauthors"]:
        return "same", "same_name_and_shared_work"
    return "queue", "same_name_no_shared_context"


def _units(profs: dict) -> tuple[dict, list]:
    """Rows that are one person by construction: the source's own person id, or the same name in one
    record (an MRU lead who is also the inventor). Returns unit -> merged profile, and the joining edges."""
    parent = {k: k for k in profs}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    edges, first = [], {}
    for k, p in sorted(profs.items()):
        for group, rule in ((p["id"], "same_source_person_id"), (p["record_name"], "same_name_in_one_record")):
            if group is None:
                continue
            if group in first:
                edges.append((first[group], k, rule))
                parent[find(k)] = find(first[group])
            else:
                first[group] = k
    units = defaultdict(lambda: {"names": set(), "sexes": set(), "inst": set(), "works": set(), "rows": []})
    for k, p in profs.items():
        u = units[find(k)]
        u["names"].add(p["name"])
        u["sexes"] |= {p["sex"]} - {None}
        u["inst"] |= p["inst"]
        u["works"] |= p["works"]
        u["rows"].append(k)
    by_work = defaultdict(set)
    for u in units.values():
        for w in u["works"]:
            by_work[w] |= u["names"]
    for u in units.values():
        u["coauthors"] = {n for w in u["works"] for n in by_work[w]} - u["names"]
    return units, edges


def pairs(con):
    profs = profiles(con)
    units, edges = _units(profs)
    for a, b, rule in edges:
        yield a, b, "same", rule
    by_name = defaultdict(set)
    for u, p in units.items():
        for n in p["names"]:
            by_name[n].add(u)
    candidates = set()
    for n, us in by_name.items():
        if " " in n:  # a single given name or nickname alone cannot tell two people apart
            candidates |= set(combinations(sorted(us), 2))
    # spelling variants ("สมใจ จันทร์ดี" / "สมใจจันทร์ ดี"): nearly the same full name, same start
    block = defaultdict(set)
    for n in by_name:
        if " " in n:
            block[n[:3]].add(n)
    for names in block.values():
        for x, y in combinations(sorted(names), 2):
            if min(len(x), len(y)) >= 8 and difflib.SequenceMatcher(None, x, y).ratio() >= 0.9:
                candidates |= {tuple(sorted((a, b))) for a in by_name[x] for b in by_name[y] if a != b}
    for a, b in sorted(candidates):
        yield (a, b, *decide(units[a], units[b]))
