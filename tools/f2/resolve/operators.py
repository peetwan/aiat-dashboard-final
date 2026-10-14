"""Businesses (K05 operators): listed sellers, learning-area directory rows and businesses found in text.

Rules were written from the user's review principles and scored on 788 reviewed pairs and a blind
check page (2026-10-13). A business is identified by its name core (the name without generic words
such as กลุ่ม / วิสาหกิจชุมชน / ร้าน, places and group numbers) and where it is.

Places of a business:
- loc: where the record puts the business (a listed seller's district, a directory row's address, or
  an address written right after the name in the text it was found in);
- context: where the record it was found in is (a Cultural Map item's place);
- name places: places written in the name itself ("… ตำบลกกแดง").
"""

from __future__ import annotations

import difflib
import json
import math
import re
from collections import Counter, defaultdict
from itertools import combinations

from .. import decisions as reviewed
from ..geo import Geo
from ..text import key, norm

PREFIX, TABLE = "op", "operators"
GENERIC_WORDS = ["ห้างหุ้นส่วนจำกัด", "หจก.", "บริษัท", "จำกัด", "(มหาชน)", "กลุ่มวิสาหกิจชุมชน", "วิสาหกิจชุมชน",
                 "เครือข่าย", "สหกรณ์", "กลุ่ม", "ร้าน", "ศูนย์", "ชมรม", "สมาคม", "ฟาร์ม"]
NAME_PLACE = re.compile(r"(?:ตำบล|ต\.|อำเภอ|อ\.|จังหวัด|จ\.)\s*[ก-๙]+")
GROUP_NO = re.compile(r"กลุ่มที่\s*(\d+)")
PERSON = re.compile(r"(?:นาย|นางสาว|นาง|น\.ส\.)\s*([ก-๙]+)")
LEGAL = ("บริษัท", "จำกัด", "หจก", "ห้างหุ้นส่วน")
NEXT_ITEM = re.compile(r"\d{1,2}\.\s*(?=[ก-๙A-Za-z])|\n")
LEVELS = ("province_code", "district_code", "subdistrict")
WRITTEN_SUBDISTRICT = re.compile(r"(?:ตำบล|ต\.)\s*([ก-๙]+)")
# Rules added 2026-10-14 from the reviewed pairs the rules above still queued:
# words that describe a business without naming it ("กลุ่มเกษตรกรวิสาหกิจชุมชนX" is "วิสาหกิจชุมชนX")
DESCRIPTIVE_WORDS = ["วิสาหกิจ", "เกษตรกร", "แม่บ้าน", "ผู้ผลิต", "ผลิตภัณฑ์", "หมู่บ้าน", "บ้าน", "ภัตตาคาร", "otop",
                     "ชุมชน"]
HONORIFICS = ["พ่อครู", "แม่ครู", "คุณยาย", "คุณตา", "คุณ", "ครู", "ป้า", "ลุง", "ยาย", "ตา", "เจ๊", "แม่", "พ่อ", "น้า",
              "อา", "พี่"]
# a person named after an honorific ("ร้านขนมจีนป้าเขียว", "กลุ่มผลิตโคมล้านนา คุณบุญมี")
HONORIFIC_PERSON = re.compile(r"(?:พ่อครู|แม่ครู|คุณยาย|คุณ|ป้า|ลุง|ยาย|เจ๊|ครู|น้า)\s*([ก-๙]{2,})")
# a directory row "<group label> <first name> <surname>"
ROSTER_PERSON = re.compile(r"\s([ก-๙]{2,})\s+[ก-๙]{2,}$")
VILLAGE = re.compile(r"(?<!แม่)(?<!พื้น)(?<!หมู่)(?<!อำเภอ)(?<!ตำบล)(?<!อ\.)(?<!ต\.)บ้าน\s*([ก-๙]{3,})")
GROUP_WORDS = ("กลุ่ม", "วิสาหกิจ", "สหกรณ์", "เครือข่าย")
MEMBERS_OF = re.compile(r"(?:ของ|สมาชิก)\s*(.+)$")  # "เครือข่ายเกษตรกรผู้ปลูกหมากเม่าของกลุ่มX"
THAI_MARKS = re.compile(r"[\u0E31\u0E34-\u0E3A\u0E47-\u0E4E]")  # vowel and tone marks above/below a letter


def nodes(con) -> list[tuple[str, str]]:
    return con.execute("""SELECT source, record_id FROM operators
                          WHERE kind <> 'extracted' OR review_status = 'supported' ORDER BY ALL""").fetchall()


def core_name(name: str) -> str:
    def strip(text, keep_place=False):
        text = GROUP_NO.sub(" ", text)
        if not keep_place:
            text = NAME_PLACE.sub(" ", text)
        text = re.sub(r"\(.*?\)", " ", text)
        for word in GENERIC_WORDS:
            text = text.replace(word, " ")
        return key(text)
    core = strip(norm(name))
    # "วิสาหกิจชุมชนตำบลรำแดง": the place is the distinctive part
    return core if len(core) >= 4 else strip(norm(name), keep_place=True)


def _letters(text: str) -> int:
    """Length without Thai vowel and tone marks ("น้ำปั่น" has 4 letters, not 7)."""
    return len(THAI_MARKS.sub("", text))


def loose(core: str) -> str:
    """A name core without descriptive words and honorifics."""
    for word in DESCRIPTIVE_WORDS + HONORIFICS:
        core = core.replace(word, "")
    return core


def _honorifics(names: set[str]) -> set[str]:
    return {h for n in names for h in HONORIFICS if re.search(rf"(?:^|\s|ร้าน){h}", n)}


def _roster(names: set[str]) -> dict[str, set[str]]:
    """Directory rows "<group label> <first name> <surname>": group label -> first names."""
    out = {}
    for n in names:
        m = ROSTER_PERSON.search(n)
        if m and n.startswith(("กลุ่ม", "วิสาหกิจ", "เกษตรกร")) and not any(w in n for w in LEGAL):
            out.setdefault(n[:m.start()].strip(), set()).add(m.group(1))
    return out


def _grams(text: str) -> set[str]:
    return {text[i:i + 3] for i in range(max(1, len(text) - 2))} if text else set()


def _window(quote: str, name: str, width: int = 150) -> str:
    """The text right after the business name (a roster lists several groups, each with its address)."""
    q, n = norm(quote), norm(name)
    i = q.find(n)
    if i < 0 and len(n) >= 12:
        n = n[:12]
        i = q.find(n)
    if i < 0:
        return ""
    tail = q[i + len(n): i + len(n) + width]
    m = NEXT_ITEM.search(tail)
    return n + " " + (tail[:m.start()] if m else tail)


def _places(places: list[dict], text: str = "") -> dict[str, set]:
    """Codes for province and district. Subdistricts are compared by name, also when the written name is
    not an official subdistrict of that district ("ตำบลบ้านไร่" vs "ตำบลท่าไม้" still disagree)."""
    out = {level: {p[level] for p in places if p.get(level)} for level in LEVELS}
    out["subdistrict"] |= {m.replace("ํา", "ำ") for m in WRITTEN_SUBDISTRICT.findall(text)}
    return out


def profiles(con) -> dict[tuple, dict]:
    geo = Geo()
    found_in = defaultdict(list)  # extracted record -> quotes
    for e in reviewed.load("extractions.json", {"extractions": []})["extractions"]:
        if e["kind"] == "operator":
            found_in[e["source"], e["record_id"]] = [q["text"] for r in e["records"] for q in r["quotes"] if q.get("text")]
    context = defaultdict(list)  # (source, record) -> places of the record a business was found in
    for source, rid, pc, dc, sc in con.execute(
            "SELECT source, record_id, province_code, district_code, subdistrict_code FROM cultural_records "
            "UNION ALL SELECT source, record_id, province_code, district_code, subdistrict_code FROM offerings "
            "WHERE source = 'cultural_map' AND kind = 'listed'").fetchall():
        context[source, rid].append({"province_code": pc, "district_code": dc,
                                     "subdistrict": sc and geo.subdistricts[sc]["subdistrictNameTh"]})

    out = {}
    for source, rid, kind, name, quality, pc, dc, sc, details in con.execute(
            "SELECT source, record_id, kind, name, name_quality, province_code, district_code, subdistrict_code, "
            "details FROM operators").fetchall():
        details = json.loads(details) if details else {}
        names = {norm(name)} | {norm(a) for a in details.get("aliases") or []}
        if kind == "extracted":
            windows = [_window(q, n) for q in found_in[source, rid] for n in names]
            loc = _places([p for w in windows for p in geo.places_in_text(w)], "\n".join(windows))
            ctx = [p for r in details.get("source_records") or [] for p in context.get((source, r), [])]
        else:
            loc = _places([{"province_code": pc, "district_code": dc, "subdistrict": sc and geo.subdistricts[sc]["subdistrictNameTh"]}])
            ctx = []
        cores = {core_name(n) for n in names} - {""}
        out[source, rid] = {
            "source": source, "names": names, "code_only": quality == "code", "core": cores,
            "grams": set().union(*(_grams(c) for c in cores)) if cores else set(),
            "loc": loc, "ctx": {k: loc[k] | v for k, v in _places(ctx).items()},
            "name_loc": _places([p for n in names for m in NAME_PLACE.findall(n) for p in geo.places_in_text(m)],
                                " ".join(NAME_PLACE.findall(" ".join(names)))),
            "group_no": {g for n in names for g in GROUP_NO.findall(n)},
            "numbers": {x.lstrip("0") for n in names for x in re.findall(r"\d+", re.sub(r"\(.*?\)", "", n))},
            "persons": {m for n in names for m in PERSON.findall(n)},
            "honorific_persons": {m for n in names for m in HONORIFIC_PERSON.findall(n)},
            "honorifics": _honorifics(names),
            "roster": _roster(names),
            "villages": {v for n in names for v in VILLAGE.findall(n)},
            "group": any(w in n for n in names for w in GROUP_WORDS),
            "owners": {core_name(m.group(1)) for n in names for m in [MEMBERS_OF.search(n)] if m} - {""},
            "qualifiers": {key(x) for n in names for x in re.findall(r"\((.*?)\)", n)},
            "legal": {any(w in n for w in LEGAL) for n in names},
            "latin": all(re.fullmatch(r"[\x00-\x7f]+", n) for n in names),
            "records": set(details.get("source_records") or []),
        }
    return out


def _state(a: set, b: set) -> str:
    if not a or not b:
        return "unknown"
    return "shared" if a & b else "conflict"


def _changed(x: str, y: str) -> int:
    return sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, x, y).get_opcodes()
               if op != "equal")


class Rules:
    def __init__(self, profs: dict):
        self.profs = profs
        df = Counter(g for p in profs.values() for g in p["grams"])
        self.idf = {g: math.log(len(profs) / n) for g, n in df.items()}
        self.core_provinces = defaultdict(set)  # name core -> provinces it is seen in
        self.core_districts = defaultdict(set)
        for p in profs.values():
            for c in p["core"]:
                self.core_provinces[c] |= p["ctx"]["province_code"]
                self.core_districts[c] |= p["ctx"]["district_code"]

    def dsim(self, a, b) -> float:
        """Cosine of IDF-weighted name pieces: generic words (กลุ่ม, เกษตรกร) count for little."""
        wa = {g: self.idf[g] for g in a["grams"]}
        wb = {g: self.idf[g] for g in b["grams"]}
        num = sum(wa[g] * wb[g] for g in wa.keys() & wb.keys())
        den = math.sqrt(sum(v * v for v in wa.values()) * sum(v * v for v in wb.values()))
        return num / den if den else 0.0

    def generic(self, a, b) -> bool:
        """An activity label, not a name: the shared core is seen in 3+ provinces or is very short."""
        return any(len(self.core_provinces[c]) >= 3 or len(c) <= 6 for c in a["core"] & b["core"])

    def reused(self, core: str) -> bool:
        """A label groups in different places carry ("ผู้เลี้ยงโคเนื้อ", "การเกษตร"): an activity, not a name."""
        return len(self.core_provinces[core]) >= 2 or len(self.core_districts[core]) >= 2

    @staticmethod
    def different_persons(a, b) -> bool:
        def apart(x, y):
            return bool(x and y) and not any(p == q or _changed(p, q) <= 1 for p in x for q in y)
        return (apart(a["persons"], b["persons"]) or apart(a["honorific_persons"], b["honorific_persons"])
                or any(apart(a["roster"][label], b["roster"][label]) for label in a["roster"].keys() & b["roster"].keys()))

    def decide(self, a, b) -> tuple[str, str]:
        f = {f"{part}_{lvl.removesuffix('_code')}": _state(a[part][lvl], b[part][lvl])
             for part in ("loc", "ctx", "name_loc") for lvl in LEVELS}
        explicit_conflict = "conflict" in (f["loc_province"], f["loc_district"], f["loc_subdistrict"],
                                           f["name_loc_district"], f["name_loc_subdistrict"])
        place_agrees = f["loc_subdistrict"] == "shared" or (f["loc_subdistrict"] == "unknown" and f["loc_district"] == "shared")
        core_exact = bool(a["core"] & b["core"])
        sim = max((difflib.SequenceMatcher(None, x, y).ratio() for x in a["core"] for y in b["core"]), default=0.0)
        contain = any(x in y or y in x for x in a["core"] for y in b["core"] if min(len(x), len(y)) >= 4)
        typo = min((_changed(x, y) for x in a["core"] for y in b["core"] if min(len(x), len(y)) >= 8), default=99)
        same_name = core_exact or any(min(len(x), len(y)) >= 10 and _changed(x, y) <= 2 for x in a["core"] for y in b["core"])
        script_mix = a["latin"] != b["latin"]
        ds = self.dsim(a, b)

        # separate
        if _state(a["group_no"], b["group_no"]) == "conflict":
            return "different", "S1 different group number"
        if a["numbers"] and b["numbers"] and a["numbers"] != b["numbers"]:
            return "different", "S1b different number in the name"
        if f["name_loc_district"] == "conflict" or f["name_loc_subdistrict"] == "conflict":
            return "different", "S4 names state different districts/subdistricts"
        if same_name and explicit_conflict and (self.generic(a, b) or any(_letters(c) <= 6 for c in a["core"] & b["core"])):
            return "different", "S2 generic activity label in a different place"
        if sim < 0.5 and not contain and explicit_conflict:
            return "different", "S3 different names in different places"
        if ds < 0.3 and not contain and not script_mix:
            return "different", "S5 no shared distinctive name part"

        # merge
        qualifier_conflict = bool(a["qualifiers"] and b["qualifiers"] and not a["qualifiers"] & b["qualifiers"])
        qualifier_one_side = bool(a["qualifiers"]) != bool(b["qualifiers"])
        legal_mismatch = len(a["legal"]) == 1 and len(b["legal"]) == 1 and a["legal"] != b["legal"]
        scope_mismatch = {k for k, v in a["name_loc"].items() if v} != {k for k, v in b["name_loc"].items() if v}
        # a number on one side only ("เถียงนาน้อย 2", "หมิงเทียน 2") is often a branch or a second group
        number_mismatch = a["numbers"] != b["numbers"]
        clean = not (qualifier_conflict or qualifier_one_side or legal_mismatch or scope_mismatch or explicit_conflict
                     or number_mismatch) and f["ctx_province"] != "conflict"
        if core_exact and clean:
            if place_agrees:
                return "same", "M1 same name + same subdistrict/district"
            if not self.generic(a, b) and f["loc_province"] != "conflict":
                return "same", "M2 same distinctive name, no place conflict"
        # the user's rule (2026-10-13): a one-character typo in a long name, in the same district
        if not core_exact and typo <= 1 and clean and place_agrees:
            return "same", "M3 one-character typo, same district"
        honorific_conflict = bool(a["honorifics"] and b["honorifics"] and a["honorifics"] != b["honorifics"])
        if clean and place_agrees and not (a["qualifiers"] or b["qualifiers"] or honorific_conflict) and \
                any(loose(x) == loose(y) and _letters(loose(x)) >= 5 for x in a["core"] for y in b["core"]):
            return "same", "M4 same name apart from descriptive words or one honorific, same place"

        if self.different_persons(a, b):
            return "different", "S7 names state different persons"
        for x, y in ((a, b), (b, a)):
            if x["owners"] and not y["owners"] and any(o in c or c in o for o in x["owners"] for c in y["core"]):
                return "different", "S9 one is the network or members of the other"
        if a["group"] and b["group"] and a["villages"] and b["villages"] and not any(
                v.startswith(w) or w.startswith(v) or _changed(v, w) <= 1 for v in a["villages"] for w in b["villages"]):
            return "different", "S10 groups of different villages"
        if not core_exact and f["ctx_province"] == "conflict":
            return "different", "S11 similar names, records in different provinces"
        if same_name:
            return "queue", "Q1 same name, place conflict or scope/qualifier difference"

        # similar, not identical names
        if explicit_conflict:
            return "different", "S6 similar (not identical) names in different places"
        if "shared" not in (f["loc_subdistrict"], f["loc_district"]):
            for x, y in ((a, b), (b, a)):
                if any(self.reused(c) and all(c in d and _letters(loose(d)) - _letters(loose(c)) >= 3 for d in y["core"])
                       for c in x["core"]):
                    return "different", "S12 only a common activity label in common"
        if place_agrees and (ds >= 0.5 or contain or script_mix):
            return "queue", "Q2 similar names, same place"
        short = min((len(c) for c in a["core"] | b["core"]), default=0)
        if ds >= 0.7 or (contain and short >= 6 and ds >= 0.5):
            return "queue", "Q3 near-identical names, place unknown"
        return "different", "S8 weak name similarity, no shared place"


def pairs(con):
    profs = {k: p for k, p in profiles(con).items() if k in set(nodes(con)) and p["core"] and not p["code_only"]}
    rules = Rules(profs)
    index = defaultdict(set)
    for k, p in profs.items():
        for g in p["grams"]:
            index[g].add(k)
    seen = set()
    for ks in index.values():
        if len(ks) > 200:  # a piece most names share is no evidence
            continue
        for a, b in combinations(sorted(ks), 2):
            if (a, b) in seen:
                continue
            seen.add((a, b))
            pa, pb = profs[a], profs[b]
            contain = any(x in y or y in x for x in pa["core"] for y in pb["core"] if min(len(x), len(y)) >= 4)
            if contain or rules.dsim(pa, pb) >= 0.3:
                outcome, rule = rules.decide(pa, pb)
                yield a, b, outcome, rule
