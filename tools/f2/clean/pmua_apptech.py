"""PMUA AppTech (pmua-apptech.com): products.json (one detail page per innovation) and the
innovation map dashboard (dashboards/innovation_map_all.json: the same innovations listed per province,
with use areas and TRL). Two map innovations have no detail page; they come from the map alone."""

from __future__ import annotations

import re

from ..text import clean_or_none, level, norm, person, ref_part, sections

PRODUCTS, MAP, RESEARCHERS = "products.json", "innovation_map_all.json", "researchers.json"
# Dashboards publishing totals per province (K02 uses innovators_all's total_inno).
DASHBOARDS = ("innovators_all", "innovators_2025", "innovators_2026", "family_all", "family_2025", "family_2026")
# Raw files this cleaner does not read, and why (the clean stage warns about any other unread file).
SKIPPED = {"stations.json": "research station profiles (organisations), not counted entities",
           "universities.json": "university profiles; each innovation states its university",
           **{f"{name}.json": f"a compressed copy of dashboards/{name}.json" for name in (MAP.removesuffix(".json"), *DASHBOARDS)}}
MAP_AREA = re.compile(r"^อ\.(?P<district>.*?)\s+ต\.(?P<subdistrict>.*)$")


def clean(raw, geo) -> dict[str, list[dict]]:
    innovations, readiness, people, places = {}, [], [], []
    for index, record in enumerate(raw.json(PRODUCTS)["data"]):
        rid = str(record["record_id"])
        key = {"record_id": rid}
        university = clean_or_none((record.get("university") or {}).get("name_raw"))
        ip_number = next((norm(i.get("value_raw")) for i in record.get("ip") or []
                          if "เลขที่" in norm(i.get("label_raw")) and re.search(r"\d", norm(i.get("value_raw")))), None)
        innovations[rid] = {
            **key,
            "upstream_id": rid,
            "title": norm(record["title"]),
            "description": sections(record.get("description_sections")),
            "category": clean_or_none(record.get("category")),
            "institution": university,
            "ip_number": ip_number,
            "url": record.get("detail_url"),
            "raw_ref": f"{PRODUCTS}#data/{index}",
            "details": {"technology_type": record.get("technology_type"), "tags": record.get("tags"),
                        "price_thb": record.get("price_thb"), "ip": record.get("ip"),
                        "funding": record.get("funding_history"), "target_groups": record.get("target_groups")},
        }
        trl = record.get("trl") or {}
        readiness.append({**key, "scale": "TRL", "level": level(trl.get("level")), "raw": trl.get("label_raw"),
                          "stated_in": "detail"})
        researcher = record.get("researcher") or {}
        who = person(researcher.get("name_raw"))
        if who:
            people.append({"record_id": f"{rid}#researcher#0", "kind": "listed", "role": "researcher", **who,
                           "institution": university, "person_ref": clean_or_none(researcher.get("agent_id")),
                           "about_kind": "innovation", "about_record_id": rid, "raw_ref": f"{PRODUCTS}#data/{index}"})
        for area in record.get("areas") or []:
            places += [{**key, "role": "use", "stated_in": "detail", **place} for place in _detail_area(area, geo)]

    map_trl = set()
    for province, items in raw.json(f"dashboards/{MAP}")["prov_data"].items():
        province = geo.english_province.get(province, province)
        for position, item in enumerate(items):
            rid = str(item["prod_id"])
            key = {"record_id": rid}
            if rid not in innovations:  # listed on the map only
                innovations[rid] = {**key, "upstream_id": rid, "title": norm(item.get("prod_name")),
                                    "institution": clean_or_none(item.get("univ")),
                                    "raw_ref": f"dashboards/{MAP}#prov_data/{province}/{position}",
                                    "details": {"map_only": True}}
            if (rid, item.get("trl")) not in map_trl:
                map_trl.add((rid, item.get("trl")))
                readiness.append({**key, "scale": "TRL", "level": level(item.get("trl")), "raw": item.get("trl"),
                                  "stated_in": "map"})
            for area in item.get("areas") or []:
                m = MAP_AREA.match(norm(area))
                place = geo.place(province, m["district"], m["subdistrict"]) if m else geo.place(province)
                places.append({**key, "role": "use", "stated_in": "map", **place, "raw": f"{province} {area}"})
    for index, item in enumerate(raw.json(RESEARCHERS)["data"]):
        who = person(item.get("title"))
        if who:
            people.append({"record_id": f"researcher:{item['record_id']}", "kind": "listed", "role": "researcher", **who,
                           "institution": clean_or_none(item.get("university_raw")), "person_ref": str(item["record_id"]),
                           "raw_ref": f"{RESEARCHERS}#data/{index}",
                           "details": {"expertise": clean_or_none(item.get("expertise_raw")),
                                       "innovation_count": item.get("innovation_count"), "url": item.get("profile_url")}})
    return {"innovations": list(innovations.values()), "innovation_readiness": readiness,
            "people": people, "innovation_places": _unique(places),
            "reported_figures": [row for name in DASHBOARDS for row in _dashboard(raw, name, geo)]}


def _dashboard(raw, name: str, geo) -> list[dict]:
    """Every number a PMUA dashboard shows: the headline, economic metrics, and per-province values
    (nested counts such as levels {"1": 2} become metric "levels.1")."""
    data, ref = raw.json(f"dashboards/{name}.json"), f"dashboards/{name}.json#"
    rows = [{"dataset": name, "metric": "headline", "value": data.get("headline"), "raw_ref": ref + "headline"}]
    for metric, value in (data.get("economic_metrics") or {}).items():
        if isinstance(value, dict) and "thb" in value:
            rows.append({"dataset": name, "metric": metric, "value": value["thb"],
                         "raw_ref": f"{ref}economic_metrics/{ref_part(metric)}/thb"})
    for province, values in (data.get("prov_data") or {}).items():
        place = geo.place(geo.english_province.get(province, province))
        for field, value in values.items():
            for metric, number in (value.items() if isinstance(value, dict) else [(None, value)]):
                rows.append({"dataset": name, "metric": f"{field}.{metric}" if metric else field,
                             "dimension": "province", "dimension_value": province,
                             "province_code": place["province_code"], "value": number,
                             "raw_ref": f"{ref}prov_data/{ref_part(province)}/{ref_part(field)}"
                             + (f"/{ref_part(metric)}" if metric else "")})
    return rows


def _detail_area(area: dict, geo) -> list[dict]:
    """PMUA states official codes: tambon_ids are subdistricts; a district with no listed tambon is
    district-level; an area with no codes falls back to its written names."""
    raw = f"{area.get('province')} {area.get('districts')} {area.get('tambons')}"
    tambons = [str(t) for t in area.get("tambon_ids") or [] if str(t) in geo.subdistricts]
    covered = {str(geo.subdistricts[t]["districtCode"]) for t in tambons}
    districts = [str(d) for d in area.get("district_ids") or [] if str(d) in geo.districts and str(d) not in covered]
    out = [geo.place_by_code(t) for t in tambons] + [geo.place_by_code(d) for d in districts]
    if not out:
        province = str(area.get("province_id") or "").zfill(2)
        out = [geo.place_by_code(province) if province in geo.provinces else geo.place(area.get("province"))]
    return [{**place, "raw": raw} for place in out]


def _unique(places: list[dict]) -> list[dict]:
    seen, out = set(), []
    for p in places:
        key = (p["record_id"], p["stated_in"], p["province_code"], p["district_code"], p["subdistrict_code"])
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out
