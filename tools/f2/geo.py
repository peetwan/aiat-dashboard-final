"""Thai administrative geography: turn written place names into official codes.

One resolver for every source. Reference lists: config/f2_pipeline/geography.
Order of trust: exact official name → a unique lower level fixes or fills the level above →
a close spelling match within the already-known parent (typo fix). Every fix is noted.
"""

from __future__ import annotations

import difflib
import json
import re
from collections import defaultdict
from pathlib import Path

from .text import norm

GEO_DIR = Path(__file__).resolve().parents[2] / "config" / "f2_pipeline" / "geography"

PREFIXES = {
    "province": ("จังหวัด", "จ."),
    "district": ("อำเภอ", "อ.", "เขต"),
    "subdistrict": ("ตำบล", "ต.", "แขวง"),
}
ALIASES = {"กรุงเทพฯ": "กรุงเทพมหานคร", "กรุงเทพ": "กรุงเทพมหานคร", "กทม": "กรุงเทพมหานคร",
           "กทม.": "กรุงเทพมหานคร", "สุไหง-โกลก": "สุไหงโก-ลก", "สุไหงโกลก": "สุไหงโก-ลก",
           # Reviewed spellings of Pattani subdistricts too far from the official name for a typo match.
           "ปูยุด": "ปุยุด", "จะบังตีฆอ": "จะบังติกอ", "ปาเซยาวอ": "ปะเสยะวอ"}
# Where a marker word ends the written name.
NAME_END = r"[\s,;:()/]|จังหวัด|อำเภอ|ตำบล|จ\.|อ\.|ต\.|เขต|แขวง"


def _name(value: object, level: str) -> str:
    text = norm(value)
    for prefix in PREFIXES[level]:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    text = re.split(r"\s(?:จังหวัด|อำเภอ|ตำบล)", text)[0]  # "โคกปรง อำเภอ" -> "โคกปรง"; not "สามตำบล"
    text = text.replace("ํา", "ำ").replace(" ", "").rstrip(".ๆฯ")
    text = re.sub(r"\d+$", "", text)
    return ALIASES.get(text, text)


def _close(name: str, choices: list[str]) -> str | None:
    """A unique close spelling (typo) match, or None."""
    found = difflib.get_close_matches(name, choices, n=2, cutoff=0.85)
    if len(found) == 1:
        return found[0]
    if len(found) == 2:
        a, b = (difflib.SequenceMatcher(None, name, f).ratio() for f in found)
        return found[0] if a > b else None
    return None


class Geo:
    def __init__(self, directory: Path = GEO_DIR):
        load = lambda name: json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
        self.provinces = {str(r["provinceCode"]).zfill(2): r["provinceNameTh"] for r in load("provinces")}
        self.province_code = {name: code for code, name in self.provinces.items()}
        self.english_province = {r["provinceNameEn"]: r["provinceNameTh"] for r in load("provinces")}
        self.districts = {str(r["districtCode"]): r for r in load("districts")}
        self.subdistricts = {str(r["subdistrictCode"]): r for r in load("subdistricts")}
        self.district_codes = defaultdict(list)
        for code, r in self.districts.items():
            self.district_codes[r["districtNameTh"]].append(code)
        self.subdistrict_codes = defaultdict(list)
        self.districts_in = defaultdict(dict)     # province code -> {district name: code}
        self.subdistricts_in = defaultdict(dict)  # district code -> {subdistrict name: code}
        for code, r in self.districts.items():
            self.districts_in[str(r["provinceCode"]).zfill(2)][r["districtNameTh"]] = code
        for code, r in self.subdistricts.items():
            self.subdistrict_codes[r["subdistrictNameTh"]].append(code)
            self.subdistricts_in[str(r["districtCode"])][r["subdistrictNameTh"]] = code

    def _prov(self, code: str) -> str:
        return str(self.districts[code]["provinceCode"]).zfill(2) if len(code) == 4 else \
            str(self.subdistricts[code]["provinceCode"]).zfill(2)

    def place_by_code(self, code: str) -> dict:
        """A place from an official province (2), district (4) or subdistrict (6 digit) code."""
        sc = code if len(code) == 6 else None
        dc = str(self.subdistricts[sc]["districtCode"]) if sc else code if len(code) == 4 else None
        pc = self._prov(dc) if dc else code
        return self._result(pc, dc, sc, None)

    def place(self, province: object = None, district: object = None, subdistrict: object = None) -> dict:
        """Codes for a written (province, district, subdistrict). Unknown levels stay None."""
        p, d, s = _name(province, "province"), _name(district, "district"), _name(subdistrict, "subdistrict")
        notes: list[str] = []
        pc = self.province_code.get(p)
        if p and not pc:
            fixed = _close(p, list(self.province_code))
            pc = self.province_code.get(fixed) if fixed else None
            if pc:
                notes.append("province_spelling_fixed")
        dc = sc = None
        if pc and d in ("เมือง", self.provinces[pc]):
            d = "เมือง" + self.provinces[pc]
        if pc and d and s and d not in self.districts_in[pc] and self.subdistricts_in.get(self.districts_in[pc].get(s, ""), {}).get(d):
            d, s = s, d  # district and subdistrict written in each other's fields
            notes.append("district_subdistrict_swapped")
        if d:
            named = self.district_codes.get(d, [])
            local = [c for c in named if self._prov(c) == pc]
            if len(local) == 1:
                dc = local[0]
            elif len(named) == 1 and not pc:
                dc = named[0]
                notes.append("province_from_unique_district")
                pc = self._prov(dc)
            elif len(named) == 1 and s in self.subdistricts_in[named[0]]:
                dc = named[0]  # district and subdistrict agree with each other: the province was miswritten
                notes.append("province_corrected_by_district_and_subdistrict")
                pc = self._prov(dc)
            elif len(named) == 1:
                notes.append("district_in_other_province")  # one field against another: keep the province
            elif pc:
                subs = [c for c in self.subdistrict_codes.get(d, []) if self._prov(c) == pc]
                if len(subs) == 1 and not s:
                    sc = subs[0]
                    dc = str(self.subdistricts[sc]["districtCode"])
                    notes.append("subdistrict_written_as_district")
                else:
                    pool = self.districts_in[pc]
                    fixed = _close(d, list(pool))
                    if fixed:
                        dc = pool[fixed]
                        notes.append("district_spelling_fixed")
            if not dc:
                notes.append("district_unmatched")
        if s and not sc:
            if dc:
                pool = self.subdistricts_in[dc]
                sc = pool.get(s)
                if not sc:
                    fixed = _close(s, list(pool))
                    sc = pool.get(fixed) if fixed else None
                    if sc:
                        notes.append("subdistrict_spelling_fixed")
            else:
                named = [c for c in self.subdistrict_codes.get(s, []) if not pc or self._prov(c) == pc]
                if len(named) == 1:
                    sc = named[0]
                    dc = str(self.subdistricts[sc]["districtCode"])
                    pc = self._prov(sc)
                    notes.append("district_from_unique_subdistrict")
            if not sc:
                notes.append("subdistrict_unmatched")
        return self._result(pc, dc, sc, ",".join(notes) or None)

    def _result(self, pc, dc, sc, note) -> dict:
        return {
            "province_code": pc,
            "district_code": dc,
            "subdistrict_code": sc,
            "province": self.provinces.get(pc) if pc else None,
            "district": self.districts[dc]["districtNameTh"] if dc else None,
            "subdistrict": self.subdistricts[sc]["subdistrictNameTh"] if sc else None,
            "geo_note": note,
        }

    def places_in_text(self, text: object) -> list[dict]:
        """Places written with markers (จังหวัด/อำเภอ/ตำบล…) in free text, line by line.
        Returns only places that resolved to at least a province."""
        found: dict[tuple, dict] = {}
        for line in str(text or "").splitlines():
            line = norm(line)
            provinces, districts, subdistricts = (_marked(line, PREFIXES[k]) for k in PREFIXES)
            sub = subdistricts[0] if len(subdistricts) == 1 else None
            claims: list[tuple] = []
            if len(provinces) == 1 and districts:
                claims += [(provinces[0], d, sub) for d in districts]
            else:
                claims += [(p, None, None) for p in provinces]
                claims += [(None, d, sub) for d in districts]
                if not districts and not provinces:
                    claims += [(None, None, s) for s in subdistricts]
            for claim in claims:
                place = self.place(*claim)
                if place["province_code"]:
                    found.setdefault((place["province_code"], place["district_code"], place["subdistrict_code"]), place)
        return list(found.values())


def _marked(text: str, prefixes: tuple[str, ...]) -> list[str]:
    hits = []
    for prefix in prefixes:
        for m in re.finditer(re.escape(prefix), text):
            name = re.split(NAME_END, text[m.end():].lstrip(), maxsplit=1)[0].rstrip(".ๆฯ")
            if name:
                hits.append((m.start(), name))
    return [name for _, name in sorted(hits)]
