"""Judge: a cheap LLM reads queued innovation and offering pairs and answers same / different / unsure.

Run `python -m tools.f2 judge` after `resolve`, then `resolve` again to use the answers. Answers are kept
in data/runtime/f2/decisions/judge.json, keyed by the pair, with a hash of the exact request: a pair is
asked again only when a record's text changed. Only queued pairs are asked (and pairs whose stored
answer is in use), so a refresh costs only its new pairs.

How an answer counts (tested on the user's reviews, 2026-10-13):
- innovations, different + high confidence: applied, the pair is separated (197 right / 3 wrong of 200);
- everything else is a proposal shown to the user, who confirms it. Innovation merges were right 120 of
  124 times and offerings were tested on only 179 labels, so they wait for confirmations first.

Privacy: personal names never leave the machine. Every full name the people table knows, titled names
("นายสมชาย", "ป้าแดง") and phone numbers / e-mail addresses are masked as [person] / [contact]; a
person is sent only as a computed same / different / unknown flag. A request in which a known full name
is still found is not sent. The request goes to OpenRouter with zero data retention and no training
use. The key is read from OPENROUTER_API_KEY and never printed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import duckdb

from .. import decisions as reviewed
from ..clean import DB_PATH
from ..geo import Geo
from ..text import key, norm
from .offerings import _producers

MODEL, EFFORT = "deepseek/deepseek-v4.1-flash", "low"
URL = "https://openrouter.ai/api/v1/chat/completions"
FILE = "judge.json"
ENTITIES = ("innovation", "offering")
APPLIED = {("innovation", "different", "high")}
PROMPTS = Path(__file__).resolve().parent / "prompts"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["decision", "confidence", "evidence"],
          "properties": {"decision": {"type": "string", "enum": ["same", "different", "unsure"]},
                         "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                         "evidence": {"type": "string"}}}
DESCRIPTION_CAP = {"innovation": 3000, "offering": 1500}
SOURCE_LABEL = {"icommunity": "iCommunity", "rinmp": "RINMP AppTech", "pmua_apptech": "PMUA AppTech",
                "apptech_mru": "AppTech MRU", "atlocal": "AtLocal marketplace", "cultural_map": "Cultural Map Thailand"}

# A formal title (or several) and a name: "นายสมชาย ใจดี", "ผศ.ดร. สมศรี". The title starts a word, or
# follows a word that often comes before a name ("โดยนาย…", "ที่นาง…"); a name starts with a consonant
# or a leading vowel. Words that only start like a title are kept ("หอยนางรม", "นายอำเภอ", "นายก อบต.").
# Thai often has no space after a name, so at most 15 letters are taken.
_BEFORE_NAME = "".join(f"|(?<={w})" for w in (
    "โดย", "ของ", "คือ", "กับ", "และ", "จาก", "ให้", "ได้แก่", "ชื่อ", "ร้าน", "บ้าน", "ที่", "หรือ", "ว่า", "มี", "คน",
    "สมัย", "เล่า", "ถึง", "แก่", "ต่อ", "เป็น"))
_NAME_START = r"[ก-ฮเ-ไ]"
_FORMAL = re.compile(
    r"(?:(?<![ก-๙])" + _BEFORE_NAME + r")"
    r"(?:(?:นางสาว|น\.ส\.|ด\.ช\.|ด\.ญ\.|นาง(?!ฟ้า|รำ|รม|พญา|เอก|งาม|แบบ|ไม้|ใน|เงือก)"
    r"|นาย(?!ก(?![ิ-ฺ็-๎])|อำเภอ|หน้า|ทุน|ช่าง|จ้าง|ฮ้อย|ร้อย|ทหาร|พราน|ด่าน|ตรวจ|สิบ|พล|แพทย์|ประกัน|งาน|ห้าง|โรง|สถานี)"
    r"|ดร\.|ผศ\.|รศ\.|อาจารย์)\s*)+" + _NAME_START + r"[ก-๙]{1,14}(?:\s+[ก-๙]{2,20}(?![ก-๙]))?")
# A kinship title used as a name, placed like a formal title or in a shop's name: "ป้าแดง", "คุณแม่สมศรี",
# "ร้านลุงแดง". Not common words ("แม่บ้าน", "คุณภาพ", "พ่อค้า") or places ("แม่ฮ่องสอน", checked in Masker).
_NICKNAME = re.compile(
    r"(?:(?<![ก-๙])" + _BEFORE_NAME + r"|(?<=ครัว)|(?<=กลุ่ม))(?!ป้าย)(?:คุณ|พี่)?(?:ลุง|ป้า|ยาย|แม่|พ่อ|เจ๊|เฮีย|คุณ)"
    r"(?!บ้าน|ครัว|ค้า|น้ำ|พิมพ์|พันธุ์|ลาย|แบบ|ไม้|เหล็ก|สี|ทัพ|ยาม|ตลาด|ผล|เป็น|ย่า|ใหญ่|ภาพ|ค่า|สมบัติ|ธรรม"
    r"|ประโยชน์|ลักษณะ|วุฒิ|งาม|ความ|ูปการ|ข่า|ไก่|มด|หมู|ปู|เลี้ยง|ชี|หม้าย|ทาก|เฒ่า|นยำ|ๆ|แม่|โค|แรง|ปุ๋ย|พันธ|ทัพ)" + _NAME_START + r"[ก-๙]{1,11}")
# an e-mail address, or a Thai phone number (0 + 8 or 9 digits, dashes or spaces allowed)
_CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|(?<!\d)(?:\+66[\s-]?|0)(?:\d[\s-]?){7,8}\d(?!\d)")


class Masker:
    """Masks personal names: every full name the people table knows (also written without the space),
    names after a formal title, kinship-title nicknames, and phone numbers / e-mail addresses."""

    def __init__(self, con):
        geo = Geo()
        places = set(geo.provinces.values()) | {r["districtNameTh"] for r in geo.districts.values()} \
            | {r["subdistrictNameTh"] for r in geo.subdistricts.values()}
        self.places = tuple(p for p in places if _NICKNAME.match(p))
        names = set()
        for (name,) in con.execute("SELECT DISTINCT name FROM people").fetchall():
            parts = norm(name).strip(" .").split()
            if len(parts) >= 2 and len("".join(parts)) >= 6:
                names.add(tuple(parts))
        self.full = {key("".join(n)) for n in names}
        # one alternation, longest first; the parts may be written with or without spaces between them
        self._names = re.compile("|".join(r"\s*".join(map(re.escape, n))
                                          for n in sorted(names, key=lambda n: len("".join(n)), reverse=True)))

    def _nickname(self, m: re.Match) -> str:
        return m.group(0) if m.string.startswith(self.places, m.start()) else "[person]"

    def __call__(self, text: object) -> str:
        text = self._names.sub("[person]", norm(text))
        text = _NICKNAME.sub(self._nickname, _FORMAL.sub("[person]", text))
        return _CONTACT.sub("[contact]", text)

    def leaked(self, text: str) -> bool:
        """A known full name still in the text, spaces and marks ignored."""
        k = key(text)
        return any(n in k for n in self.full)


def _block(tag: str, source: str, fields: list[tuple[str, Iterable]], description: str, cap: int) -> str:
    lines = [f'<record id="{tag}">', f"catalogue: {SOURCE_LABEL.get(source, source)}"]
    for label, values in fields:
        values = sorted({norm(v) for v in values if v not in (None, "")} - {""})
        if values:
            lines.append(f"{label}: {' | '.join(values)}")
    if len(description) > cap:
        description = description[:cap] + " [...truncated]"
    lines += [f"description: {description or '(no description)'}", "</record>"]
    return "\n".join(lines)


def _flag(a: set, b: set) -> str:
    return "unknown" if not a or not b else "yes" if a & b else "no"


def _innovation_requests(con, pairs, mask) -> dict:
    readiness, places, people = defaultdict(set), defaultdict(set), defaultdict(set)
    for s, r, lvl in con.execute("SELECT source, record_id, level FROM innovation_readiness WHERE scale = 'TRL' AND level IS NOT NULL").fetchall():
        readiness[s, r].add(str(lvl))
    for s, r, p in con.execute("SELECT source, record_id, province FROM innovation_places WHERE province IS NOT NULL").fetchall():
        places[s, r].add(p)
    for s, about, e in con.execute("""SELECT p.source, p.about_record_id, m.entity_id FROM people p
            JOIN entity_members m ON m.entity = 'person' AND m.source = p.source AND m.record_id = p.record_id
            WHERE p.about_kind = 'innovation'""").fetchall():
        people[s, about].add(e)
    records = {(s, r): (t, d, c, i, ip) for s, r, t, d, c, i, ip in con.execute(
        "SELECT source, record_id, title, description, category, institution, ip_number FROM innovations").fetchall()}

    def block(tag, k):
        title, desc, category, institution, ip = records[k]
        return _block(tag, k[0], [("title", [mask(title)]), ("institution", [institution]), ("province", places[k]),
                                  ("TRL", readiness[k]), ("IP number", [ip]), ("category", [category])],
                      mask(desc), DESCRIPTION_CAP["innovation"])

    return {(a, b): f"{block('A', a)}\n\n{block('B', b)}\n\nSame named researcher on both records (computed; names "
                    f"withheld): {_flag(people[a], people[b])}\n\nAre A and B the same innovation?" for a, b in pairs}


def _offering_requests(con, pairs, mask) -> dict:
    quotes = defaultdict(list)
    for e in reviewed.load("extractions.json", {"extractions": []})["extractions"]:
        if e["kind"] == "offering":
            quotes[e["source"], e["record_id"]] = [q["text"] for r in e["records"] for q in r["quotes"] if q.get("text")]
    record_places = defaultdict(set)
    for s, r, p, d in con.execute("""
            SELECT source, record_id, province, district FROM cultural_records
            UNION ALL SELECT i.source, i.upstream_id, p.province, p.district FROM innovation_places p
                JOIN innovations i USING (source, record_id) WHERE p.role = 'use'""").fetchall():
        record_places[s, r] |= {x for x in (p, d) if x}
    records = {}
    for s, r, kind, name, desc, category, p, d, details in con.execute(
            "SELECT source, record_id, kind, name, description, category, province, district, details FROM offerings").fetchall():
        details = json.loads(details) if details else {}
        place = {x for x in (p, d) if x} or set().union(*(record_places[s, x] for x in details.get("source_records") or []))
        text = " ".join(dict.fromkeys(quotes[s, r])) if kind == "extracted" else norm(desc)
        records[s, r] = ([name, *details.get("aliases", [])], category, details.get("output_type"), place, text)
    producers = _producers(con)

    def block(tag, k):
        titles, category, output_type, place, text = records[k]
        return _block(tag, k[0], [("title", [mask(t) for t in titles]), ("category", [category]),
                                  ("output type", [output_type]), ("place", place)],
                      mask(text), DESCRIPTION_CAP["offering"])

    return {(a, b): f"{block('A', a)}\n\n{block('B', b)}\n\nSame producer (computed; names withheld): "
                    f"{_flag(producers.get(a, set()), producers.get(b, set()))}\n\nAre A and B the same offering?"
            for a, b in pairs}


BUILDERS = {"innovation": _innovation_requests, "offering": _offering_requests}


def load() -> dict:
    return reviewed.load(FILE, {"about": "LLM answers for queued pairs; written by python -m tools.f2 judge (see tools/f2/resolve/judge.py).",
                                "answers": []})


def applied(entity: str) -> dict[tuple, dict]:
    """sorted (a, b) -> stored answer, for Resolve."""
    return {(tuple(x["a"]), tuple(x["b"])): x for x in load()["answers"] if x["entity"] == entity}


def requests(con, entities=ENTITIES) -> list[dict]:
    """One request per queued pair (or per pair whose stored answer is in use)."""
    mask = Masker(con)
    out = []
    for entity in entities:
        pairs = [((a_s, a_r), (b_s, b_r)) for a_s, a_r, b_s, b_r in con.execute(
            """SELECT a_source, a_record_id, b_source, b_record_id FROM match_pairs
               WHERE entity = ? AND (status = 'queue' OR basis = 'judge') ORDER BY ALL""", [entity]).fetchall()]
        system = (PROMPTS / f"{entity}.txt").read_text(encoding="utf-8")
        for (a, b), user in BUILDERS[entity](con, pairs, mask).items():
            out.append({"entity": entity, "a": list(a), "b": list(b), "system": system, "user": user,
                        "hash": hashlib.sha256(f"{MODEL}@{EFFORT}\n{system}\n{user}".encode()).hexdigest()[:16],
                        "leak": mask.leaked(user)})
    return out


def _body(r: dict) -> dict:
    return {"model": MODEL,
            "messages": [{"role": "system", "content": r["system"]}, {"role": "user", "content": r["user"]}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "pair_verdict", "strict": True, "schema": SCHEMA}},
            "provider": {"data_collection": "deny", "zdr": True, "require_parameters": True},
            "reasoning": {"effort": EFFORT, "exclude": True},
            "max_tokens": 8000, "temperature": 0}


def _ask(r: dict, api_key: str) -> dict:
    req = urllib.request.Request(URL, data=json.dumps(_body(r)).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    data: dict = {}
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(5 * 2 ** attempt)
                continue
            return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"}
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 3:
                time.sleep(5 * 2 ** attempt)
                continue
            return {"error": str(e)}
    cost = float((data.get("usage") or {}).get("cost") or 0)
    text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    try:
        verdict = json.loads(text)
        if verdict.get("decision") not in ("same", "different", "unsure") or verdict.get("confidence") not in ("high", "medium", "low"):
            raise ValueError
    except (ValueError, AttributeError):
        return {"error": f"unreadable answer: {text[:200]}", "cost": cost}
    return {"verdict": verdict, "cost": cost}


def run(budget_usd: float, entities=ENTITIES, send: bool = False, db_path: Path = DB_PATH) -> dict:
    """send=False: build the requests and report what would be sent (nothing leaves the machine)."""
    con = duckdb.connect(str(db_path), read_only=True)
    todo = requests(con, entities)
    con.close()
    store = load()
    done = {(tuple(x["a"]), tuple(x["b"])): x["hash"] for x in store["answers"]}
    leaks = [r for r in todo if r["leak"]]
    todo = [r for r in todo if not r["leak"] and done.get((tuple(r["a"]), tuple(r["b"]))) != r["hash"]]
    report = {"to_ask": dict(sorted(_count(todo).items())), "withheld_name_found": len(leaks),
              "chars": sum(len(r["system"]) + len(r["user"]) for r in todo)}
    if not send or not todo:
        return report
    api_key = os.environ["OPENROUTER_API_KEY"]
    lock, spent, errors, answered = threading.Lock(), [0.0], [], [0]
    path = reviewed.DIR / FILE

    def one(r):
        with lock:
            if spent[0] >= budget_usd:
                return
        result = _ask(r, api_key)
        with lock:
            spent[0] += result.get("cost", 0)
            if "error" in result:
                errors.append(result["error"])
                return
            answered[0] += 1
            pair = (tuple(r["a"]), tuple(r["b"]))
            store["answers"] = [x for x in store["answers"] if (tuple(x["a"]), tuple(x["b"])) != pair] + [{
                "entity": r["entity"], "a": r["a"], "b": r["b"], **result["verdict"], "model": f"{MODEL}@{EFFORT}",
                "hash": r["hash"], "asked": date.today().isoformat()}]
            # saved after every answer, so a stopped run keeps what was paid for
            path.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(one, todo))
    return {**report, "answered": answered[0], "errors": errors[:5], "error_count": len(errors),
            "cost_usd": round(spent[0], 4), "stopped_at_budget": spent[0] >= budget_usd}


def _count(rows) -> dict:
    out = defaultdict(int)
    for r in rows:
        out[r["entity"]] += 1
    return out
