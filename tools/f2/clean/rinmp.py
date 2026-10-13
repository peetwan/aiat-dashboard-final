"""RINMP AppTech (app.rinmp.com): app_tech.json innovations + owner_profiles.json.

The profile "owner" is the account that registered the technology (often a collector entering many
technologies for a group), not its inventor; it is kept as role "collector" (previous pipeline review:
"collector group retained, not person").

Use places come from two parts of a record:
- the structured addresses, when a use/target-user passage of the description backs them up;
- places written in those passages ("ต.… อ.… จ.…").
A passage saying the innovation is not yet used cancels both.
"""

from __future__ import annotations

import re

from ..text import clean_or_none, level, norm, person, sections

FILE, OWNERS = "app_tech.json", "owner_profiles.json"
TARGET_SECTION = "targetUserAddressDetail"
USE_PHRASES = ("พื้นที่ที่นำไปใช้ประโยชน์", "ที่นำนวัตกรรมไปใช้ประโยชน์", "ติดตั้งอุปกรณ์ดังกล่าวในพื้นที่",
               "ถูกนำไปใช้", "ชุมชนนำผลงานออกแบบไปใช้ประโยชน์", "นำไปใช้การใน")
NOT_USED_PHRASES = ("ยังไม่มีกลุ่มนำไปใช้ประโยชน์", "ยังไม่มีการนำนวัตกรรมไปใช้งาน", "ยังไม่มีการนำนวัตกรรมไปใช้")
STRIP = {"province": ("จังหวัด", "จ."), "district": ("อำเภอ", "อ.", "เขต"), "subdistrict": ("ตำบล", "ต.", "แขวง")}


def clean(raw, geo) -> dict[str, list[dict]]:
    owners: dict[int, list[dict]] = {}
    for owner in raw.json(OWNERS)["data"]["records"]:
        for app_id in owner["app_tech_ids"]:
            owners.setdefault(int(app_id), []).append(owner)

    innovations, readiness, people, places = [], [], [], []
    for index, record in enumerate(raw.json(FILE)["data"]["records"]):
        rid = str(record["id"])
        key = {"record_id": rid}
        ip_number = norm((record.get("ip") or {}).get("number_raw"))
        innovations.append({
            **key,
            "upstream_id": rid,
            "title": norm(record["title"]),
            "description": sections(record.get("description_sections")),
            "category": clean_or_none(record.get("category")),
            "institution": clean_or_none((record.get("institute") or {}).get("name")),
            "ip_number": ip_number if re.search(r"\d", ip_number) else None,
            "url": record.get("detail_url"),
            "raw_ref": f"{FILE}#data/records/{index}",
            "details": {"sub_category": record.get("sub_category"), "status": record.get("status"),
                        "ip_category": (record.get("ip") or {}).get("category"), "tags": record.get("tags"),
                        "target_segments": record.get("target_segments")},
        })
        trl = record.get("trl") or {}
        readiness.append({**key, "scale": "TRL", "level": level(trl.get("level")), "raw": trl.get("raw"),
                          "stated_in": "profile"})
        readiness.append({**key, "scale": "ATL", "level": None, "raw": record.get("atl_level"), "stated_in": "profile"})

        for n, owner in enumerate(owners.get(int(record["id"])) or [{"fullname": record.get("owner_display_name")}]):
            who = person(owner["fullname"])
            if who:
                people.append({"record_id": f"{rid}#collector#{n}", "kind": "listed", "role": "collector", **who,
                               "institution": clean_or_none(owner.get("institute"))
                               or clean_or_none((record.get("institute") or {}).get("name")),
                               "about_kind": "innovation", "about_record_id": rid,
                               "raw_ref": f"{FILE}#data/records/{index}", "details": {"owner_key": owner.get("owner_key")}})

        places += [{**key, **place} for place in _places(record, geo)]
    return {"innovations": innovations, "innovation_readiness": readiness,
            "people": people, "innovation_places": places}


def _places(record: dict, geo) -> list[dict]:
    passages = []
    for section in record.get("description_sections") or []:
        text = norm(section.get("text"))
        if section.get("label") == TARGET_SECTION or any(p in text for p in USE_PHRASES):
            passages.append(text)
    not_used = any(p in text for text in passages for p in NOT_USED_PHRASES)
    usable = [] if not_used else [t for t in passages if t and t != "-"]
    out = []
    for address in record.get("addresses") or []:
        place = geo.place(address.get("province"), address.get("district"), address.get("sub_district"))
        backed = any(_backs(address, text) for text in usable)
        raw_text = " / ".join(norm(address.get(k)) for k in ("name", "sub_district", "district", "province")
                              if address.get(k))
        out.append({"role": "use" if backed else "profile", "stated_in": "address", **place, "raw": raw_text})
    for section in record.get("description_sections") or []:
        text = norm(section.get("text"))
        if text in usable:
            out += [{"role": "use", "stated_in": "text", **place, "raw": None}
                    for place in geo.places_in_text(section.get("text"))]
    if record.get("province_resolved"):
        out.append({"role": "profile", "stated_in": "collector_province", **geo.place(record["province_resolved"]),
                    "raw": record["province_resolved"]})
    return out


def _backs(address: dict, text: str) -> bool:
    """The passage names the address's party, or its province + district/subdistrict, or district + subdistrict."""
    party = norm(address.get("name"))
    p, d, s = (_strip(address.get(k), STRIP[level_]) for k, level_ in
               (("province", "province"), ("district", "district"), ("sub_district", "subdistrict")))
    has_p, has_d, has_s = p and p in text, len(d) >= 3 and d in text, len(s) >= 3 and s in text
    return bool((len(party) >= 6 and party in text) or (has_p and (has_d or has_s)) or (has_d and has_s))


def _strip(value, prefixes) -> str:
    text = norm(value)
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text
