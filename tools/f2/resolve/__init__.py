"""Resolve stage: decide which cleaned records are the same thing, one entity kind at a time.

A matcher module per kind gives
- nodes(con): the records to resolve, as (source, record_id) keys;
- pairs(con): candidate pairs with a rule outcome (same | different | queue) and the rule's name.

Reviewed decisions (data/runtime/f2/decisions/matching.json) come first and override rules. A decision
lists groups of records: "same" joins all of them; "different" and "unsure" keep every record of one
group apart from every record of the others ("unsure" = reviewed, not enough evidence, not asked again).

The LLM judge's answers (judge.py) follow the decisions: the kinds of answer listed in judge.APPLIED
separate a queued pair; every answer is also kept on its pair (match_pairs.judge) as a proposal.

Records are joined one edge at a time (decisions, then rules). An edge that would put two records that
must stay apart into one entity is not applied and is reported. A queued pair stays separate until it
is decided, which is also what the previous pipeline did with unreviewed pairs.
"""

from __future__ import annotations

import hashlib
from itertools import combinations
from pathlib import Path

import duckdb

from .. import decisions as reviewed
from ..clean import DB_PATH, insert  # Resolve reads and extends the Clean stage's database
from . import activities, cultural_records, innovations, judge, offering_families, offerings, operators, people

SCHEMA = Path(__file__).resolve().parent / "schema.sql"
MATCHERS = {"innovation": innovations, "operator": operators, "offering": offerings,
            "offering_family": offering_families, "person": people, "cultural_record": cultural_records,
            "activity": activities}


def load() -> list[dict]:
    return reviewed.load("matching.json", {"decisions": []})["decisions"]


def run(db_path: Path = DB_PATH) -> dict[str, dict[str, int]]:
    """A judge answer is used only while its request, built from the resolved tables, is the one it answered.
    The request depends on other kinds' entities (innovations <-> people), so resolving is repeated until no
    further answer turns out stale; stale pairs stay queued, to be asked again."""
    con = duckdb.connect(str(db_path))
    con.begin()  # all entity kinds or none
    stale: set[tuple] = set()
    while True:
        counts = _resolve_all(con, stale)
        found = judge.stale(con)
        if found <= stale:
            break
        stale |= found
    con.commit()
    con.close()
    return counts


def _resolve_all(con, stale: set[tuple]) -> dict[str, dict[str, int]]:
    con.execute(SCHEMA.read_text(encoding="utf-8"))
    all_decisions, counts = load(), {}
    for entity, matcher in MATCHERS.items():
        nodes = matcher.nodes(con)
        known = set(con.execute(f"SELECT source, record_id FROM {matcher.TABLE}").fetchall())
        answers = {k: x for k, x in judge.applied(entity).items() if (entity, *k) not in stale}
        apart = {k for k, x in answers.items() if (entity, x["decision"], x["confidence"]) in judge.APPLIED}
        result = resolve(nodes, matcher.pairs(con), [d for d in all_decisions if d["entity"] == entity], known, apart)
        for row in result["pairs"]:
            x = answers.get(((row["a_source"], row["a_record_id"]), (row["b_source"], row["b_record_id"])))
            row["judge"] = f"{x['decision']}/{x['confidence']}" if x else None
        prefix = matcher.PREFIX
        insert(con, "entity_members", [
            {"entity": entity, "entity_id": entity_id(prefix, members), "source": s, "record_id": r}
            for members in result["entities"] for s, r in members])
        insert(con, "match_pairs", [{"entity": entity, **row} for row in result["pairs"]])
        insert(con, "decision_issues", [{"entity": entity, **row} for row in result["issues"]])
        counts[entity] = {"records": len(nodes), "entities": len(result["entities"]),
                          **{k: sum(1 for p in result["pairs"] if p["status"] == k) for k in ("same", "different", "queue")},
                          "issues": len(result["issues"])}
    return counts


def entity_id(prefix: str, members: list[tuple[str, str]]) -> str:
    """Stable while the entity's smallest member record stays."""
    source, record_id = min(members)
    return f"{prefix}_{hashlib.sha1(f'{source}|{record_id}'.encode()).hexdigest()[:12]}"


class _Entities:
    """Union-find where every group remembers which records it must stay apart from."""

    def __init__(self, nodes):
        self.parent = {n: n for n in nodes}
        self.members = {n: {n} for n in nodes}
        self.apart = {n: set() for n in nodes}

    def find(self, n):
        while self.parent[n] != n:
            self.parent[n] = self.parent[self.parent[n]]
            n = self.parent[n]
        return n

    def keep_apart(self, a, b):
        self.apart[self.find(a)].add(b)
        self.apart[self.find(b)].add(a)

    def can_join(self, a, b) -> bool:
        ra, rb = self.find(a), self.find(b)
        return ra == rb or not (self.apart[ra] & self.members[rb] or self.apart[rb] & self.members[ra])

    def join(self, a, b) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True
        if not self.can_join(a, b):
            return False
        if len(self.members[ra]) < len(self.members[rb]):
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.members[ra] |= self.members.pop(rb)
        self.apart[ra] |= self.apart.pop(rb)
        return True


def _key(pair) -> tuple:
    return tuple(sorted(pair))


def resolve(nodes: list[tuple[str, str]], rule_pairs, decisions: list[dict], known: set | None = None,
            judged_apart: set | None = None) -> dict:
    """known: every record of the table; a decision on a known record that is not resolved here (e.g. a
    finding that does not count) is simply not applied, a decision on an unknown record is reported.
    judged_apart: sorted pairs the judge separated; applied to pairs a rule queued."""
    judged_apart = judged_apart or set()
    present = set(nodes)
    known = present if known is None else known
    ents = _Entities(nodes)
    pairs: dict[tuple, dict] = {}  # sorted (a, b) -> row
    issues = []

    def row(a, b, rule, outcome, status, basis):
        (a_s, a_r), (b_s, b_r) = _key((a, b))
        return {"a_source": a_s, "a_record_id": a_r, "b_source": b_s, "b_record_id": b_r,
                "rule": rule, "rule_outcome": outcome, "status": status, "basis": basis}

    # 1. decisions
    same_edges = []
    for d in decisions:
        groups = [[tuple(k) for k in g] for g in d["groups"]]
        gone = [k for g in groups for k in g if k not in known]
        if gone:
            issues.append({"decision_ref": d["ref"], "issue": "records_not_found", "detail": gone})
        groups = [[k for k in g if k in present] for g in groups]
        groups = [g for g in groups if g]
        if d["decision"] == "same":
            flat = [k for g in groups for k in g]
            same_edges += [(flat[0], k, d) for k in flat[1:]]
        else:
            for g1, g2 in combinations(groups, 2):
                for a in g1:
                    for b in g2:
                        ents.keep_apart(a, b)
                        pairs[_key((a, b))] = row(a, b, None, None, "different", f"decision:{d['ref']}")
    for a, b, d in same_edges:
        if ents.join(a, b):
            pairs[_key((a, b))] = row(a, b, None, None, "same", f"decision:{d['ref']}")
        else:
            issues.append({"decision_ref": d["ref"], "issue": "conflicts_with_a_different_decision",
                           "detail": [list(a), list(b)]})

    # 2. rules (decided pairs keep the decision; the rule outcome is still recorded)
    rule_rows, looked_at = [], set()
    for a, b, outcome, rule in rule_pairs:
        k = _key((a, b))
        if k in looked_at:  # a matcher's first rule for a pair wins
            continue
        looked_at.add(k)
        if k in pairs:
            pairs[k].update(rule=rule, rule_outcome=outcome)
            continue
        by_judge = outcome == "queue" and k in judged_apart
        if outcome == "different" or by_judge:
            ents.keep_apart(a, b)
        rule_rows.append((a, b, outcome, rule, by_judge))
    for a, b, outcome, rule, by_judge in sorted(rule_rows, key=lambda x: x[2] != "same"):
        if outcome == "same":
            joined = ents.join(a, b)
            pairs[_key((a, b))] = row(a, b, rule, outcome, "same" if joined else "blocked", f"rule:{rule}")
        elif outcome == "different" or by_judge:
            pairs[_key((a, b))] = row(a, b, rule, outcome, "different", "judge" if by_judge else f"rule:{rule}")
        else:
            pairs[_key((a, b))] = row(a, b, rule, outcome, "queue", f"rule:{rule}")

    # 3. a queued pair that ended up in one entity, or whose entities must stay apart, needs no review
    for k, r in pairs.items():
        if r["status"] == "queue":
            a, b = k
            if ents.find(a) == ents.find(b):
                r.update(status="same", basis=r["basis"] + "+transitive")
            elif not ents.can_join(a, b):
                r.update(status="different", basis=r["basis"] + "+transitive")
    entities = [sorted(m) for m in ents.members.values()]
    return {"entities": entities, "pairs": list(pairs.values()), "issues": issues}
