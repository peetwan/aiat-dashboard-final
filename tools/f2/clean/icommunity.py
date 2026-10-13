"""iCommunity: apptech_innovations.json (apptechpmua.com export) and community_products.json (shop).

Innovations: the export lists an innovation once per plan group, so one innovation_id can appear several times:
record_id is the listing (source_key "group:innovation_id"), upstream_id the innovation_id.
Readiness comes from the export's "start/end" text (e.g. "6/8" = TRL 6 at project start, 8 at end).

Products: the seller is the name on the description's "พื้นที่:" line, before its address.
"""

from __future__ import annotations

import re

from ..text import clean_or_none, level, norm, person, strip_html

FILE, PRODUCTS, INNOVATORS = "apptech_innovations.json", "community_products.json", "apptech_innovators.json"
POSTS, BACKGROUND = "activity_posts.json", "programme_background.json"
# The three development scores an innovator's detail page states (start and current level).
DIMENSIONS = ("technology_knowledge", "learning_process_management", "collaboration_network")
# Seller names the "พื้นที่:" line writes incompletely or not at all (checked by hand in the old pipeline).
SELLER_IN_TEXT = {"กลุ่มห้อมบ้านนาคูหา": "เครือข่ายวิสาหกิจชุมชนกลุ่มห้อมบ้านนาคูหา",
                  "ทอผ้าย้อมครามบ้านอูนดง": "กลุ่มวิสาหกิจชุมชนทอผ้าย้อมครามบ้านอูนดง"}
NOT_A_SELLER = {"วิสาหกิจชุมชน", "บ้านอูนดง-หนองไชยวาลย์"}


def clean(raw, geo) -> dict[str, list[dict]]:
    innovations, readiness, people, places = [], [], [], []
    for index, record in enumerate(raw.json(FILE)["data"]):
        key = {"record_id": record["source_key"]}
        detail, project = record.get("detail") or {}, record.get("project") or {}
        institution = clean_or_none((record.get("institute") or {}).get("name"))
        innovations.append({
            **key,
            "upstream_id": record["innovation_id"],
            "title": norm(record["innovation_name"]),
            "description": strip_html(detail.get("short_description_html") or detail.get("short_description_text"))
            or None,
            "category": clean_or_none(record.get("technology_group_raw")),
            "institution": institution,
            "url": detail.get("source_url"),
            "raw_ref": f"{FILE}#data/{index}",
            "details": {"innovation_type": detail.get("innovation_type"), "project_code": project.get("code"),
                        "project_name": project.get("name"), "project_year_be": project.get("year_be"),
                        "group": (record.get("scope") or {}).get("group_label_th")},
        })
        for scale, field in (("TRL", "latest_readiness_level_raw"), ("SRL", "latest_social_readiness_level_raw")):
            m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(record.get(field) or ""))
            readiness.append({**key, "scale": scale, "level": level(m[2]) if m else None,
                              "start_level": level(m[1]) if m else None, "raw": record.get(field),
                              "stated_in": "export"})
        researcher = record.get("researcher") or {}
        who = person(researcher.get("full_name"))
        if who:
            people.append({"record_id": f"{record['source_key']}#researcher#0", "kind": "listed", "role": "researcher",
                           **who, "institution": institution, "person_ref": clean_or_none(researcher.get("user_id")),
                           "about_kind": "innovation", "about_record_id": record["source_key"],
                           "raw_ref": f"{FILE}#data/{index}"})
        location = record.get("location") or {}
        if any(location.get(k) for k in ("province", "amphor", "tambon", "geocode")):
            places.append({**key, "role": "use", "stated_in": "location", **_place(location, geo),
                           "raw": " / ".join(str(location.get(k)) for k in ("tambon", "amphor", "province", "geocode")
                                             if location.get(k))})
    operators, offerings, links = _products(raw, geo)
    innovators, assessments = _innovators(raw, geo)
    return {"innovations": innovations, "innovation_readiness": readiness,
            "people": people + innovators, "assessments": assessments, "innovation_places": places,
            "operators": operators, "offerings": offerings, "offering_operators": links,
            "publications": _publications(raw)}


def _innovators(raw, geo) -> tuple[list[dict], list[dict]]:
    """Community innovators (one row per listing; the export repeats an innovator per plan group),
    the researcher working with each, and the innovator's development scores."""
    people, assessments = [], []
    for index, record in enumerate(raw.json(INNOVATORS)["data"]):
        key, ref = record["source_key"], f"{INNOVATORS}#data/{index}"
        who = person(record.get("innovator_name"))
        if not who:
            continue
        location, project = record.get("location") or {}, record.get("project") or {}
        place = _place(location, geo) if any(location.get(k) for k in ("province", "amphor", "tambon", "geocode")) else {}
        people.append({"record_id": key, "kind": "listed", "role": "community_innovator", **who,
                       "institution": clean_or_none((record.get("institute") or {}).get("name")),
                       "person_ref": record.get("innovator_id"), **place, "raw_ref": ref,
                       "details": {"community_role": clean_or_none(record.get("community_role_raw")),
                                   "linked_innovation": clean_or_none(record.get("linked_innovation_name")),
                                   "project_code": project.get("code"), "project_year_be": project.get("year_be"),
                                   "group": (record.get("scope") or {}).get("group_label_th")}})
        researcher = person((record.get("researcher") or {}).get("full_name"))
        if researcher:
            people.append({"record_id": f"{key}#researcher#0", "kind": "listed", "role": "researcher", **researcher,
                           "person_ref": clean_or_none((record.get("researcher") or {}).get("user_id")),
                           "about_kind": "person", "about_record_id": key, "raw_ref": ref})
        detail = record.get("detail") or {}
        for dimension in DIMENSIONS:
            if dimension in detail:
                scores = detail[dimension] or {}
                assessments.append({"person_record_id": key, "dimension": dimension,
                                    "start_level": level(scores.get("start_level"), 0, 10),
                                    "current_level": level(scores.get("current_level"), 0, 10),
                                    "raw_ref": f"{ref}/detail/{dimension}"})
    return people, assessments


def _publications(raw) -> list[dict]:
    rows = []
    for name, kind, id_field in ((POSTS, "activity_post", "post_id"), (BACKGROUND, "programme_page", "page_id")):
        for index, item in enumerate(raw.json(name)["data"]):
            rows.append({"record_id": str(item[id_field]), "kind": kind, "title": norm(item.get("title_html")),
                         "text": strip_html(item.get("content_html")) or clean_or_none(item.get("content_text")),
                         "published_at": item.get("published_at"), "url": item.get("source_url"),
                         "raw_ref": f"{name}#data/{index}", "details": {"modified_at": item.get("modified_at")}})
    return rows


def _products(raw, geo) -> tuple[list[dict], list[dict], list[dict]]:
    operators: dict[str, dict] = {}
    offerings, links = [], []
    for index, item in enumerate(raw.json(PRODUCTS)["data"]):
        text = strip_html(f"{item.get('description_html') or ''}\n{item.get('short_description_html') or ''}")
        area = (re.search(r"พื้นที่\s*:?\s*([^\n]+)", text) or [None, ""])[1]
        seller = re.split(r"ตำบล|ต\.|ที่อยู่|บ้านแม่อิงหลวง", area)[0].strip()
        seller = next((name for key, name in SELLER_IN_TEXT.items() if key in text.replace(" ", "")), seller)
        written = {k: (re.search(rx, area) or [None, ""])[1].strip() for k, rx in (
            ("province", r"(?:จังหวัด|จ\.)\s*([^\s.]+)"), ("district", r"(?:อำเภอ|อ\.)\s*(.*?)(?=จังหวัด|จ\.|$)"),
            ("subdistrict", r"(?:ตำบล|ต\.)\s*(.*?)(?=อำเภอ|อ\.|$)"))}
        place = geo.place(written["province"], written["district"], written["subdistrict"]) if area else {}
        seller_id = None
        if seller and seller not in NOT_A_SELLER:
            seller_id = f"{seller}|{place.get('province_code') or written['province']}"
            operators.setdefault(seller_id, {
                "record_id": seller_id, "kind": "listed", "name": seller, "name_quality": "named", **place,
                "address_raw": area or None, "raw_ref": f"{PRODUCTS}#data/{index}"})
            links.append({"offering_record_id": str(item["product_id"]), "operator_record_id": seller_id,
                          "relationship": "seller", "basis": "description_area_line"})
        prices = item.get("prices") or {}
        price = prices.get("price")
        offerings.append({
            "record_id": str(item["product_id"]),
            "kind": "listed",
            "name": norm(item.get("name")),
            "description": text or None,
            "category": ", ".join(norm(c.get("name")) for c in item.get("categories") or []) or None,
            "price_thb": int(price) / 10 ** int(prices.get("currency_minor_unit") or 0) if price else None,
            **place,
            "url": item.get("permalink"),
            "raw_ref": f"{PRODUCTS}#data/{index}",
            "details": {"in_stock": item.get("is_in_stock"), "purchasable": item.get("is_purchasable")},
        })
    return list(operators.values()), offerings, links


def _place(location: dict, geo) -> dict:
    """The written names decide; the geocode (official subdistrict code) only fills levels the names
    leave open, and only when it agrees with every level the names did resolve."""
    written = geo.place(location.get("province"), location.get("amphor"), location.get("tambon"))
    code = str(location.get("geocode") or "")
    if code not in geo.subdistricts:
        return written
    coded = geo.place_by_code(code)
    levels = ("province_code", "district_code", "subdistrict_code")
    if all(written[k] in (None, coded[k]) for k in levels):
        return {**coded, "geo_note": written["geo_note"]}
    return {**written, "geo_note": ",".join(filter(None, [written["geo_note"], "geocode_disagrees"]))}
