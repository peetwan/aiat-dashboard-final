"""MRU AppTech (38rat.nstru.ac.th): innovations.json, one record per innovation page.

Inventors: the inventor text is free text ("ผศ.ดร.ก ข และคุณค ง", "… และคณะ"). The rule takes the record's
researchers whose names appear in it; records where that does not work were read by a reviewer
(decisions/parsing.json, apptech_mru.inventors).
"""

from __future__ import annotations

import re

from .. import decisions
from ..text import TITLES, clean_or_none, level, member_id, norm, person, sections, split_title, title_sex

FILE = "innovations.json"
# Raw files this cleaner does not read, and why (the clean stage warns about any other unread file).
SKIPPED = {"requirements.json": "technology requests posted by users (demand side), not innovations or people"}
# A researcher "university" that is really a faculty ("วิทยาศาสตร์และเทคโนโลยี") does not match this;
# for those the record's account affiliation (data.listing.affiliation) is the university.
ORGANISATION = re.compile(r"มหาวิทยาลัย|^ม\.|มรภ|มทร|สถาบัน|วิทยาลัย|วิสาหกิจ|กลุ่ม|บริษัท|ห้างหุ้นส่วน|สหกรณ์|ชุมชน|"
                          r"โรงเรียน|องค์การ|สำนักงาน|university|college|institute|company", re.I)
INSTITUTION = re.compile(r"มหาวิทยาลัย|^ม\.|^มรภ|^มทร|สถาบัน|วิทยาลัย|university|college|institute", re.I)


def clean(raw, geo) -> dict[str, list[dict]]:
    reviewed = decisions.load("parsing.json", {}).get("apptech_mru", {})
    reviewed_inventors, not_a_person = reviewed.get("inventors", {}), set(reviewed.get("not_a_person", {}))
    innovations, readiness, people = [], [], []
    for index, record in enumerate(raw.json(FILE)["data"]):
        rid, data = str(record["record_id"]), record["data"]
        key = {"record_id": rid}
        affiliation = clean_or_none(data["listing"].get("affiliation"))
        ip = data.get("ip") or {}
        ip_number = next((norm(v) for v in (ip.get("patent_no_raw"), ip.get("request_no_raw"))
                          if v and re.search(r"\d", str(v))), None)
        innovations.append({
            **key,
            "upstream_id": rid,
            "title": norm(record["title"]),
            "description": sections(data.get("description_sections")),
            "category": clean_or_none(data.get("category")),
            "institution": affiliation,
            "ip_number": ip_number,
            "url": record.get("detail_url"),
            "raw_ref": f"{FILE}#data/{index}",
            "details": {"innovation_type": data.get("innovation_type"), "ip_type": ip.get("type"),
                        "target_groups": data.get("target_groups"), "highlights": data.get("highlights")},
        })
        trl = data.get("trl") or {}
        image = re.search(r"TRL-(\d)\.png", str(trl.get("image_url") or ""))
        readiness.append({**key, "scale": "TRL", "level": level(trl.get("level")), "stated_in": "detail",
                          "raw": f"level={trl.get('level')} image={image.group(1) if image else None}"})
        srl = data.get("srl") or {}
        readiness.append({**key, "scale": "SRL", "level": level(srl.get("level")),
                          "raw": srl.get("label_raw"), "stated_in": "detail"})

        about = {"kind": "listed", "about_kind": "innovation", "about_record_id": rid, "raw_ref": f"{FILE}#data/{index}"}
        # a researcher field can hold two people: "ดร.ก ข, ผศ. ค ง"
        researchers = [(r, name) for r in data.get("researchers") or [] for name in str(r.get("name") or "").split(",")]
        seen = {}
        for researcher, name in researchers:
            who = person(name)
            if not who:
                continue
            university = clean_or_none(researcher.get("university"))
            faculty = clean_or_none(researcher.get("faculty"))
            if not university or not INSTITUTION.search(university):
                university, faculty = affiliation, faculty or university
            role = researcher.get("role") or "researcher"
            people.append({"record_id": member_id(rid, role, who["name"], seen), "role": role, **who, **about,
                           "institution": university, "faculty": faculty})
        # Inventors are usually also listed as researchers; Resolve joins them, the inventor role must stay.
        inventors, stale = _inventors(data, reviewed_inventors.get(rid))
        if stale:  # on the innovation: the new text may name no inventor at all
            innovations[-1]["details"]["reviewed_reading_stale"] = True
        for who in inventors:
            people.append({"record_id": member_id(rid, "inventor", who["name"], seen), "role": "inventor", **who, **about,
                           "institution": affiliation})
        owner = person(data["listing"].get("owner_name"))
        if owner:
            people.append({"record_id": member_id(rid, "owner", owner["name"], seen), "role": "owner", **owner, **about, "institution": affiliation,
                           "person_ref": clean_or_none(data["listing"].get("owner_user_id"))})
        for who in _rights_holders(data.get("rights_holder")):
            people.append({"record_id": member_id(rid, "rights_holder", who["name"], seen), "role": "rights_holder",
                           **who, **about, "institution": affiliation})
    # names a reviewer found are not a person (decisions/parsing.json, apptech_mru.not_a_person)
    people = [p for p in people if p["name"] not in not_a_person and f"{p.get('title') or ''}{p['name']}" not in not_a_person]
    return {"innovations": innovations, "innovation_readiness": readiness, "people": people}



def _rights_holders(value) -> list[dict]:
    """The rights holder is free text: usually the university (an organisation, not a person), or one or
    more people ("ก ข และผศ.ดร.ค ง", "ก ข และคณะ")."""
    text = norm(value)
    if not text or ORGANISATION.search(text):
        return []
    parts = re.split(r"\s*(?:,|และ)\s*", text)
    return [who for who in (person(part) for part in parts if part not in ("", "คณะ")) if who]


def _inventors(data: dict, reviewed: dict | None) -> tuple[list[dict], bool]:
    """The inventors, and whether a reviewed reading exists but the inventor text has changed since (then the
    rule reads the new text and the record needs a new look)."""
    written = norm(data.get("inventors_raw"))
    if reviewed is not None and norm(reviewed["written"]) == written:
        return [_titled(written, name) for name in reviewed["people"]], False
    found = [who for who in (person(r.get("name")) for r in data.get("researchers") or [])
             if who and len(who["name"].split()) >= 2 and who["name"].casefold() in written.casefold()]
    # keep the longest name when one is part of another (a full name and a given-name-only entry)
    found = [who for who in found if not any(o["name"] != who["name"] and who["name"] in o["name"] for o in found)]
    # the title written in the inventor text ("นาง…") wins over the researcher list's ("ผศ.…")
    return [_titled(written, who["name"]) if _title_before(written, who["name"]) else who for who in found], reviewed is not None


def _titled(written: str, name: str) -> dict:
    title = _title_before(written, name)
    return {"title": title, "name": name, "sex": title_sex(title or "")}


def _title_before(text: str, name: str) -> str | None:
    """The title(s) written right before name in text ("…และนายสมชาย ใจดี" -> "นาย")."""
    before, titles = text[:max(text.find(name), 0)].rstrip(), ""
    while True:
        t = next((t for t in TITLES if before.endswith(t)), None)
        if not t:
            return titles or None
        titles, before = t + titles, before[: -len(t)].rstrip()
