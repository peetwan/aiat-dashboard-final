"""Review: a local page for the pairs Resolve left waiting (match_pairs.status = 'queue').

`python -m tools.f2 review` serves the page on 127.0.0.1 only (it shows names, so it never leaves the
machine). Queued pairs are shown as clusters: the entities that queued pairs connect, side by side.
The reviewer sorts a cluster's entities into groups (one group = one entity); the LLM judge's
same/high answers are pre-filled, every judge answer is shown on its pair.

A saved cluster is written straight into data/runtime/f2/decisions/matching.json (origin user:<date>,
ref review:<cluster>:...): a "same" decision per group of two or more, and a "different" (or, when the
reviewer is not sure, "unsure") decision that keeps the groups apart. Saving a cluster again replaces
its decisions. Run `python -m tools.f2 resolve` afterwards to apply them; decided clusters then leave
the queue.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import webbrowser
from collections import defaultdict
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import duckdb

from .. import decisions as reviewed
from ..clean import DB_PATH
from ..resolve import MATCHERS, judge

PAGE = Path(__file__).resolve().parent / "page.html"
FILE = "matching.json"
PLACE = ("subdistrict", "district", "province")
FIELDS = ("kind", "role", "category", "cultural_type", "title_en", "institution", "faculty", "ip_number",
          "price_thb", "name_quality", "address_raw", "geo_note")
# details keys shown elsewhere on the card, or bookkeeping
HIDDEN = {"evidence", "images", "quotes", "quotes_missing", "source_records", "innovation_upstream_ids", "url"}
TEXT_CAP, VALUE_CAP, LIST_CAP = 3000, 300, 8


def _value(v) -> str:
    if isinstance(v, list):
        v = " · ".join(_value(x) for x in v[:LIST_CAP]) + (f" · +{len(v) - LIST_CAP}" if len(v) > LIST_CAP else "")
    elif isinstance(v, dict):  # {"label_raw": "ประเภท", "value_raw": "…"} -> "ประเภท: …"; otherwise its values
        v = f"{v['label_raw']}: {v['value_raw']}" if {"label_raw", "value_raw"} <= v.keys() else \
            " / ".join(_value(x) for x in v.values() if x not in (None, "", [], {}))
    v = str(v)
    return v if len(v) <= VALUE_CAP else v[:VALUE_CAP] + "…"


def _rows(con, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


class _Context:
    """Lookups for the things a card shows about a record besides its own row."""

    def __init__(self, con):
        self.titles = {}  # (source, upstream or record id) -> title, for "found in"
        for s, u, t in con.execute("SELECT source, upstream_id, title FROM innovations").fetchall():
            self.titles[s, u] = t
        for s, r, t in con.execute("SELECT source, record_id, title FROM cultural_records").fetchall():
            self.titles[s, r] = t
        self.innovation_titles = {(s, r): t for s, r, t in con.execute("SELECT source, record_id, title FROM innovations").fetchall()}
        self.places, self.trl, self.people = defaultdict(set), defaultdict(set), defaultdict(list)
        for s, r, role, *place in con.execute(
                "SELECT source, record_id, role, subdistrict, district, province FROM innovation_places").fetchall():
            if any(place):
                self.places[s, r].add(f"{role}: {', '.join(p for p in place if p)}")
        for s, r, lvl in con.execute("SELECT source, record_id, level FROM innovation_readiness WHERE level IS NOT NULL").fetchall():
            self.trl[s, r].add(str(lvl))
        for s, about, title, name, role in con.execute("""SELECT source, about_record_id, title, name, role FROM people
                WHERE about_kind = 'innovation' ORDER BY ALL""").fetchall():
            self.people[s, about].append(f"{title or ''}{name} ({role})")
        names = {(s, r): n for s, r, n in con.execute("SELECT source, record_id, name FROM operators").fetchall()}
        offers = {(s, r): n for s, r, n in con.execute("SELECT source, record_id, name FROM offerings").fetchall()}
        self.producers, self.sells = defaultdict(list), defaultdict(list)
        self.producer_entities = defaultdict(set)
        operator_entity = {(s, r): e for s, r, e in con.execute(
            "SELECT source, record_id, entity_id FROM entity_members WHERE entity = 'operator'").fetchall()}
        for s, o, p, rel in con.execute(
                "SELECT source, offering_record_id, operator_record_id, relationship FROM offering_operators ORDER BY ALL").fetchall():
            self.producers[s, o].append(f"{names.get((s, p), p)} ({rel})")
            self.sells[s, p].append(offers.get((s, o), o))
            if (s, p) in operator_entity:
                self.producer_entities[s, o].add(operator_entity[s, p])

    def extra(self, table: str, k: tuple, row: dict, details: dict) -> list[list[str]]:
        out = []
        if table == "innovations":
            out += [["Places", self.places[k]], ["TRL", self.trl[k]], ["People", self.people[k]]]
        elif table == "offerings":
            out += [["Producer / seller", self.producers[k]]]
        elif table == "operators":
            out += [["Offerings", self.sells[k]]]
        elif table == "people" and row.get("about_kind") == "innovation":
            out += [["About", [self.innovation_titles.get((k[0], row["about_record_id"]), row["about_record_id"])]]]
        found = [self.titles.get((k[0], x), x) for x in details.get("source_records") or []]
        out += [["Found in", found]]
        return [[label, _value(sorted(v) if isinstance(v, set) else v)] for label, v in out if v]


def _view(table: str, row: dict, ctx: _Context) -> dict:
    k = (row["source"], row["record_id"])
    details = json.loads(row["details"]) if row.get("details") else {}
    fields = [[f, _value(row[f])] for f in FIELDS if row.get(f) not in (None, "")]
    place = ", ".join(row[p] for p in PLACE if row.get(p))
    if place:
        fields.append(["Place", place])
    if row.get("latitude") is not None:
        fields.append(["Coordinates", f"{row['latitude']:.5f}, {row['longitude']:.5f}"])
    fields += ctx.extra(table, k, row, details)
    fields += [[key, _value(v)] for key, v in details.items() if key not in HIDDEN and v not in (None, "", [], {})]
    text = row.get("description") or "\n".join(details.get("evidence") or [])
    images = [x["url"] if isinstance(x, dict) else x for x in details.get("images") or []]
    return {"source": k[0], "record_id": k[1], "name": _name(table, row), "fields": fields,
            "text": text if len(text) <= TEXT_CAP else text[:TEXT_CAP] + "…",
            "url": row.get("url") or details.get("url"), "images": [u for u in images if not u.endswith("/default.png")][:3]}


def _cluster_id(entity: str, records) -> str:
    return hashlib.sha1(json.dumps([entity, sorted(records)]).encode()).hexdigest()[:12]


def clusters(db_path: Path = DB_PATH) -> list[dict]:
    """Every queued pair, as clusters of the entities queued pairs connect."""
    con = duckdb.connect(str(db_path), read_only=True)
    ctx = _Context(con)
    entity_of = {(e, s, r): eid for e, eid, s, r in con.execute(
        "SELECT entity, entity_id, source, record_id FROM entity_members").fetchall()}
    members = defaultdict(list)
    for (e, s, r), eid in entity_of.items():
        members[e, eid].append((s, r))
    queued = defaultdict(list)
    for e, a_s, a_r, b_s, b_r, rule, verdict in con.execute("""SELECT entity, a_source, a_record_id, b_source, b_record_id,
            rule, judge FROM match_pairs WHERE status = 'queue' ORDER BY ALL""").fetchall():
        queued[e].append(((a_s, a_r), (b_s, b_r), rule, verdict))
    apart = defaultdict(set)  # entity -> {(entity id, entity id)} a reviewed decision keeps apart
    for e, a_s, a_r, b_s, b_r in con.execute("""SELECT entity, a_source, a_record_id, b_source, b_record_id
            FROM match_pairs WHERE status = 'different' AND basis LIKE 'decision:%'""").fetchall():
        ea, eb = entity_of.get((e, a_s, a_r)), entity_of.get((e, b_s, b_r))
        if ea and eb:
            apart[e] |= {(ea, eb), (eb, ea)}
    saved = _saved()
    out = []
    for entity, matcher in MATCHERS.items():
        if not queued[entity]:
            continue
        rows = {(r["source"], r["record_id"]): r for r in _rows(con, f"SELECT * FROM {matcher.TABLE}")}
        answers = judge.applied(entity) if entity in judge.ENTITIES else {}
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a, b, *_ in queued[entity]:
            parent[find(entity_of[entity, *a])] = find(entity_of[entity, *b])
        by_root = defaultdict(list)
        for pair in queued[entity]:
            by_root[find(entity_of[entity, *pair[0]])].append(pair)
        for pairs in by_root.values():
            eids = sorted({entity_of[entity, *k] for a, b, *_ in pairs for k in (a, b)})
            index = {eid: i for i, eid in enumerate(eids)}
            shown = defaultdict(set)  # the records the queued pairs name, per entity
            for a, b, *_ in pairs:
                shown[entity_of[entity, *a]].add(a)
                shown[entity_of[entity, *b]].add(b)
            items = []
            for eid in eids:
                others = sorted(set(members[entity, eid]) - shown[eid])
                items.append({"entity_id": eid, "records": [_view(matcher.TABLE, rows[k], ctx) for k in sorted(shown[eid])],
                              "keys": sorted(shown[eid]),
                              "others": [f"{_name(matcher.TABLE, rows[k])} [{k[0]}]" for k in others[:LIST_CAP]],
                              "others_count": len(others)})
            pair_rows = []
            for a, b, rule, verdict in pairs:
                x = answers.get((a, b)) if verdict else None  # no verdict: no answer, or a stale one (Resolve)
                ia, ib = index[entity_of[entity, *a]], index[entity_of[entity, *b]]
                producers = ""
                if entity == "offering":
                    pa, pb = ctx.producer_entities[a], ctx.producer_entities[b]
                    producers = "unknown" if not pa or not pb else "yes" if pa & pb else "no"
                pair_rows.append({"a": ia, "b": ib, "rule": rule, "judge": verdict,
                                  "evidence": x["evidence"] if x else None, "same_producer": producers})
            cid = _cluster_id(entity, [k for eid in eids for k in shown[eid]])
            hard = sorted({tuple(sorted((index[x], index[y]))) for x, y in apart[entity] if x in index and y in index})
            out.append({"id": cid, "entity": entity, "items": items, "pairs": pair_rows, "apart": hard,
                        "prefill": _prefill(len(eids), pair_rows, hard), "saved": _restore(saved.get(cid), items)})
    con.close()
    return sorted(out, key=lambda c: (list(MATCHERS).index(c["entity"]), len(c["items"]), c["id"]))


def _name(table: str, row: dict) -> str:
    if table == "people":
        return f"{row.get('title') or ''}{row['name']}"
    return (row.get("title") if table in ("innovations", "cultural_records") else row.get("name")) or "(no name)"


def _prefill(n: int, pairs: list[dict], apart: list) -> list[int]:
    """A group number per item: the judge's same/high answers joined, unless a decision keeps them apart."""
    group = list(range(n))
    for p in pairs:
        if p["judge"] != "same/high":
            continue
        ga, gb = group[p["a"]], group[p["b"]]
        a_members = [i for i in range(n) if group[i] == ga]
        b_members = [i for i in range(n) if group[i] == gb]
        if ga != gb and not any(tuple(sorted((i, j))) in apart for i in a_members for j in b_members):
            group = [ga if g == gb else g for g in group]
    first = {}
    return [first.setdefault(g, len(first)) for g in group]


def _saved() -> dict[str, list[dict]]:
    by_cluster = defaultdict(list)
    for d in reviewed.load(FILE, {"decisions": []})["decisions"]:
        if d.get("ref", "").startswith("review:"):
            by_cluster[d["ref"].split(":")[1]].append(d)
    return by_cluster


def _restore(decisions: list[dict] | None, items: list[dict]) -> dict | None:
    """The groups a saved cluster was given, read back from its decisions."""
    if not decisions:
        return None
    sets = []
    for d in decisions:
        sets += [{tuple(k) for k in g} for g in d["groups"]] if d["decision"] != "same" else [
            {tuple(k) for g in d["groups"] for k in g}]
    group, first = [], {}
    for item in items:
        k = tuple(item["keys"][0])
        g = next((i for i, s in enumerate(sets) if k in s), -1 - len(group))
        group.append(first.setdefault(g, len(first)))
    apart = next((d for d in decisions if d["decision"] != "same"), None)
    return {"groups": group, "unsure": bool(apart and apart["decision"] == "unsure"),
            "note": decisions[0].get("reason", "") if decisions[0].get("reason") != DEFAULT_REASON else "",
            "date": decisions[0]["origin"].removeprefix("user:")}


DEFAULT_REASON = "Reviewed on the review page."


def decisions_for(cluster: dict, groups: list[int], unsure: bool, note: str) -> list[dict]:
    """The matching.json decisions for one reviewed cluster."""
    n = len(cluster["items"])
    if len(groups) != n or any(not isinstance(g, int) or g < 0 for g in groups):
        raise ValueError("one group number per item")
    for i, j in cluster["apart"]:
        if groups[i] == groups[j]:
            raise ValueError(f"items {i + 1} and {j + 1} were decided different before")
    by_group = defaultdict(list)
    for i, g in enumerate(groups):
        by_group[g].append([list(k) for k in cluster["items"][i]["keys"]])
    head = {"entity": cluster["entity"], "reason": note.strip() or DEFAULT_REASON, "origin": f"user:{date.today().isoformat()}"}
    out = []
    for g, entities in sorted(by_group.items()):
        # also one item showing several records: the reviewer saw them as one, rules may stop joining them
        if sum(len(keys) for keys in entities) > 1:
            out.append({**head, "decision": "same", "groups": entities, "ref": f"review:{cluster['id']}:same-{len(out) + 1}"})
    if len(by_group) > 1:
        out.append({**head, "decision": "unsure" if unsure else "different",
                    "groups": [[k for keys in entities for k in keys] for _, entities in sorted(by_group.items())],
                    "ref": f"review:{cluster['id']}:apart"})
    elif unsure:
        raise ValueError("'not sure' needs at least two groups")
    return out


_lock = threading.Lock()


def write(cluster_id: str, new: list[dict]) -> None:
    """Replace a cluster's decisions in matching.json (written to a temporary file, then moved)."""
    with _lock:
        path = reviewed.DIR / FILE
        store = reviewed.load(FILE, {"decisions": []})
        store["decisions"] = [d for d in store["decisions"]
                              if not d.get("ref", "").startswith(f"review:{cluster_id}:")] + new
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)


def serve(port: int = 8765, open_browser: bool = True) -> None:
    data = clusters()
    by_id = {c["id"]: c for c in data}

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, kind: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self._send(200, PAGE.read_bytes(), "text/html")
            elif self.path == "/clusters":
                self._send(200, json.dumps(data, ensure_ascii=False).encode())
            else:
                self._send(404, b"{}")

        def do_POST(self):
            if self.path != "/save" or self.headers.get("Origin") not in (None, f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                self._send(403, b"{}")
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                cluster = by_id[body["id"]]
                new = [] if body.get("clear") else decisions_for(cluster, body["groups"], bool(body.get("unsure")),
                                                                 str(body.get("note") or ""))
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False).encode())
                return
            write(cluster["id"], new)
            cluster["saved"] = _restore(new, cluster["items"])
            self._send(200, json.dumps({"saved": cluster["saved"]}, ensure_ascii=False).encode())

        def log_message(self, format, *args):  # quiet
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    waiting = sum(1 for c in data if not c["saved"])
    print(f"{len(data)} clusters ({sum(len(c['pairs']) for c in data)} queued pairs), {waiting} not reviewed yet")
    print(f"review page: {url}  (Ctrl-C to stop; then run `python -m tools.f2 resolve` to apply)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
