"""Innovations: one record per source listing (all 4 innovation sources).

- Same source innovation id (iCommunity lists one innovation under several groups) -> same.
- Candidates from two sources: titles sharing >= 30% of their 3-letter pieces, or a shared IP number.
  Within one source the listings are distinct entries of one catalogue, so only near-identical titles
  (>= 0.9 similar) are candidates; that is also how the previous pipeline picked within-source reviews.
- Rules only separate. They were mined from 737 reviewed pairs (grouped 5-fold cross-validation,
  99.6% of separations right); no rule was safe enough to merge, so every other candidate is queued.
"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from itertools import combinations

from ..text import key, norm

PREFIX, TABLE = "inn", "innovations"
# A role that names who uploaded the listing, not who made the innovation.
NOT_MAKERS = {("apptech_mru", "owner")}
INSTITUTION_ABBREVIATIONS = [("มทร.", "มหาวิทยาลัยเทคโนโลยีราชมงคล"), ("มรภ.", "มหาวิทยาลัยราชภัฏ"),
                             ("มรภ ", "มหาวิทยาลัยราชภัฏ"), ("ม.", "มหาวิทยาลัย")]


def nodes(con) -> list[tuple[str, str]]:
    return con.execute("SELECT source, record_id FROM innovations ORDER BY ALL").fetchall()


def _institution(value) -> str:
    text = norm(value).replace("ราชภัฎ", "ราชภัฏ")
    for short, full in INSTITUTION_ABBREVIATIONS:
        if text.startswith(short):
            text = full + text[len(short):]
            break
    return key(text.replace("ในพระบรมราชูปถัมภ์", "").split(" จังหวัด")[0])


def _grams(text: str, n: int = 3) -> set[str]:
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def profiles(con) -> dict[tuple, dict]:
    out = {}
    for source, rid, upstream, title, description, institution, ip in con.execute(
            "SELECT source, record_id, upstream_id, title, description, institution, ip_number FROM innovations").fetchall():
        text = " ".join(re.sub(r"^[^:\n]{1,40}:\s*", "", line) for line in (description or "").split("\n"))
        digits = re.sub(r"\D", "", ip or "")
        out[source, rid] = {
            "upstream": upstream, "title": key(title), "tgrams": _grams(key(title)), "dgrams": _grams(key(text)),
            "numbers": {n.lstrip("0") or "0" for n in re.findall(r"\d+(?:\.\d+)?", title or "")},
            "inst": {_institution(institution)} - {""}, "people": set(), "prov": set(), "trl": set(),
            "ip": {digits} if len(digits) >= 4 else set()}
    for source, rid, role, name, institution in con.execute(
            "SELECT source, about_record_id, role, name, institution FROM people WHERE about_kind = 'innovation'").fetchall():
        p = out.get((source, rid))
        if p is None or (source, role) in NOT_MAKERS:
            continue
        if len(name.split()) >= 2:  # a first name alone is not enough to compare people
            p["people"].add(key(name))
        p["inst"] |= {_institution(institution)} - {""}
    for source, rid, province in con.execute(
            "SELECT DISTINCT source, record_id, province_code FROM innovation_places WHERE province_code IS NOT NULL").fetchall():
        out[source, rid]["prov"].add(province)
    for source, rid, level in con.execute(
            "SELECT source, record_id, level FROM innovation_readiness WHERE scale = 'TRL' AND level IS NOT NULL").fetchall():
        out[source, rid]["trl"].add(level)
    return out


def _state(a: set, b: set) -> str:
    if not a or not b:
        return "unknown"
    return "shared" if a & b else "conflict"


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _title_similarity(a: dict, b: dict) -> float:
    return difflib.SequenceMatcher(None, a["title"], b["title"], autojunk=False).ratio()


# Separation rules, in the order they are reported.
def _separate(a: dict, b: dict) -> str | None:
    if a["numbers"] and b["numbers"] and a["numbers"] != b["numbers"]:
        return "different_numbers_in_title"
    title_sim = _title_similarity(a, b)
    people = _state(a["people"], b["people"])
    if title_sim < 0.6 and people == "conflict":
        return "different_title_and_people"
    desc = _jaccard(a["dgrams"], b["dgrams"])
    if desc < 0.2 and _state(a["inst"], b["inst"]) == "conflict" and people == "conflict":
        return "different_description_institution_and_people"
    if desc < 0.2 and _state(a["ip"], b["ip"]) == "conflict":
        return "different_description_and_ip_number"
    return None


def pairs(con):
    profs = profiles(con)
    candidates: dict[tuple, str] = {}
    by_upstream = defaultdict(list)
    for k, p in profs.items():
        by_upstream[k[0], p["upstream"]].append(k)
    for ks in by_upstream.values():
        for a, b in combinations(sorted(ks), 2):
            candidates[a, b] = "same_source_innovation_id"

    index = defaultdict(set)
    for k, p in profs.items():
        for g in p["tgrams"]:
            index[g].add(k)
    for k, p in profs.items():
        near = set().union(*(index[g] for g in p["tgrams"] if len(index[g]) <= 300)) if p["tgrams"] else set()
        for o in near:
            if k < o and (k, o) not in candidates and _jaccard(p["tgrams"], profs[o]["tgrams"]) >= 0.3:
                candidates[k, o] = "similar_title"
    by_ip = defaultdict(set)
    for k, p in profs.items():
        for ip in p["ip"]:
            by_ip[ip].add(k)
    for ks in by_ip.values():
        for a, b in combinations(sorted(ks), 2):
            candidates.setdefault((a, b), "shared_ip_number")

    for (a, b), found_by in candidates.items():
        if found_by == "same_source_innovation_id":
            yield a, b, "same", found_by
            continue
        if a[0] == b[0] and _title_similarity(profs[a], profs[b]) < 0.9:
            continue
        rule = _separate(profs[a], profs[b])
        yield (a, b, "different", rule) if rule else (a, b, "queue", found_by)
