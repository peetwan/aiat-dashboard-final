"""Cultural Map Thailand (culturalmapthailand.info, f2_culturalmap_university).

- map_inspiration.json: cultural subjects (CD-…) with official place codes, categories, recorder and
  informants. The informant field is free text that can hold several names; it is kept as written.
- products.json: product listings (PD-…). The page ends its address with the site's own
  "ต. … อ. … จ. … <postcode>" fields, which are used for the place. Sellers are not structured:
  they were found in the product text by review (see extractions).
- activities.json (G-…), recreation.json (Re-creation projects, with team members): publications.
- team.json: the site's own team (provenance only).
"""

from __future__ import annotations

import re

from ..text import clean_or_none, member_id, norm, person

PRODUCTS, MAP, ACTIVITIES, RECREATION, TEAM = (
    "products.json", "map_inspiration.json", "activities.json", "recreation.json", "team.json")
DESCRIPTION_FIELDS = ("history", "identity", "potential", "limitations", "stakeholders")
SITE_ADDRESS = re.compile(r"ต\.\s*(\S*)\s+อ\.\s*(\S*)\s+จ\.\s*(\S*)")


def clean(raw, geo) -> dict[str, list[dict]]:
    offerings = []
    for index, record in enumerate(raw.json(PRODUCTS)["data"]["records"]):
        data = record["data"]
        address = norm(data.get("address_text"))
        site = SITE_ADDRESS.findall(address)
        subdistrict, district, province = site[-1] if site else ("", "", "")
        # "500-1500.00 บาท", "99, 149, 199 บาท": a range or choices is several amounts, not one price
        amounts = [float(a.replace(",", "")) for a in re.findall(r"\d[\d,]*(?:\.\d+)?", str(data.get("price_text") or ""))]
        offerings.append({
            "record_id": record["external_id"],
            "kind": "listed",
            "name": norm(record.get("title")),
            "description": clean_or_none(data.get("description")),
            "category": clean_or_none(data.get("product_category")),
            "price_thb": amounts[0] if len(amounts) == 1 else None,
            **geo.place(province, district, subdistrict),
            "url": record.get("source_url"),
            "raw_ref": f"{PRODUCTS}#data/records/{index}",
            "details": {"address": address, "price_text": clean_or_none(data.get("price_text")),
                        "price_amounts": amounts if len(amounts) > 1 else None, "sales_channels": data.get("sales_channels"),
                        "related_cultural_record": data.get("related_cultural_record"),
                        "external_links": data.get("external_links")},
        })
    records, people = _subjects(raw, geo)
    publications, team = _publications(raw)
    return {"offerings": offerings, "cultural_records": records, "people": people + team,
            "publications": publications}


def _subjects(raw, geo) -> tuple[list[dict], list[dict]]:
    records, people = [], []
    for index, record in enumerate(raw.json(MAP)["data"]["records"]):
        data, rid, ref = record["data"], record["external_id"], f"{MAP}#data/records/{index}"
        classification, location = data.get("classification") or {}, data.get("location") or {}
        coordinates = location.get("coordinates") or {}
        description = data.get("description") or {}
        records.append({
            "record_id": rid,
            "title": norm(record.get("title")),
            "title_en": clean_or_none((data.get("names") or {}).get("en")),
            "category": (classification.get("primary_category") or {}).get("code"),
            "cultural_type": (classification.get("cultural_type") or {}).get("code"),
            "categories": [c.get("code") for c in classification.get("additional_categories") or []],
            "description": "\n".join(f"{k}: {norm(description[k])}" for k in DESCRIPTION_FIELDS
                                     if clean_or_none(description.get(k))) or None,
            **_coded_place(location, geo),
            "latitude": coordinates.get("latitude"), "longitude": coordinates.get("longitude"),
            "url": record.get("source_url"), "raw_ref": ref,
            "details": {"record_code": (data.get("identifiers") or {}).get("record_code"),
                        "address": clean_or_none(location.get("address_raw")), "dates": data.get("dates"),
                        "funding": data.get("funding"), "page_roles": data.get("page_roles"),
                        "keywords": data.get("keywords"), "images": _images((data.get("media") or {}).get("images"))},
        })
        about = {"kind": "listed", "about_kind": "cultural_record", "about_record_id": rid, "raw_ref": ref}
        recorder = (data.get("people") or {}).get("recorder") or {}
        who = person(recorder.get("name"))
        if who:
            people.append({"record_id": f"{rid}#recorder#0", "role": "recorder", **who, **about,
                           "institution": clean_or_none((recorder.get("institution") or {}).get("name_th")),
                           "person_ref": clean_or_none(recorder.get("account_identifier"))})
        informants = clean_or_none((data.get("people") or {}).get("informants_raw"))
        if informants:
            people.append({"record_id": f"{rid}#informant#0", "role": "informant", **(person(informants) or
                           {"name": informants}), **about, "details": {"written_as": informants}})
    return records, people


def _images(images) -> list[dict]:
    return [{"url": i["url"], "caption": clean_or_none(i.get("caption"))} for i in images or [] if i.get("url")]


def _coded_place(location: dict, geo) -> dict:
    """The page states official codes (DOPA); use the most specific one that exists and agrees upward."""
    admin = location.get("administrative") or {}
    codes = [str((admin.get(k) or {}).get("code") or "") for k in ("tambon", "amphure", "province")]
    for code in codes:
        if code in geo.subdistricts or code in geo.districts or code in geo.provinces:
            place = geo.place_by_code(code)
            if all(not c or c in (place["subdistrict_code"], place["district_code"], place["province_code"])
                   for c in codes[codes.index(code) + 1:]):
                return place
    names = [(admin.get(k) or {}).get("name_th") for k in ("province", "amphure", "tambon")]
    return geo.place(*names) if any(names) else {}


def _publications(raw) -> tuple[list[dict], list[dict]]:
    publications, team = [], []
    for index, record in enumerate(raw.json(ACTIVITIES)["data"]["records"]):
        data = record["data"]
        publications.append({"record_id": record["external_id"], "kind": "activity_page", "title": norm(record.get("title")),
                             "text": clean_or_none(data.get("description")), "url": record.get("source_url"),
                             "raw_ref": f"{ACTIVITIES}#data/records/{index}",
                             "details": {"date_text": data.get("date_text"), "links": data.get("external_links"),
                                         "images": _images(data.get("gallery_images"))}})
    for index, record in enumerate(raw.json(RECREATION)["data"]["records"]):
        data, rid, ref = record["data"], record["external_id"], f"{RECREATION}#data/records/{index}"
        publications.append({"record_id": rid, "kind": "recreation_project", "title": norm(record.get("title")),
                             "text": "\n".join(filter(None, (clean_or_none(data.get(k)) for k in ("description", "extension_text")))) or None,
                             "url": record.get("source_url"), "raw_ref": ref,
                             "details": {"team_name": data.get("team_name"), "category": data.get("recreation_category"),
                                         "recorded_by": data.get("recorded_by")}})
        seen = {}
        for member in data.get("team_members") or []:
            who = person(member)
            if who:
                team.append({"record_id": member_id(rid, "team_member", who["name"], seen), "kind": "listed", "role": "project_team_member", **who,
                             "about_kind": "publication", "about_record_id": rid, "raw_ref": ref})
    for index, record in enumerate(raw.json(TEAM)["data"]["records"]):
        who = person(record.get("title"))
        if who:
            team.append({"record_id": record["external_id"], "kind": "listed", "role": "site_team", **who,
                         "raw_ref": f"{TEAM}#data/records/{index}", "details": {"group": record["data"].get("group")}})
    return publications, team
