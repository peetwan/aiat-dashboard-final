"""AtLocal Thailand (f2_cultural_market_civil): two product lists.

- product_map.json: map listings; shop_name is the seller (often only a vendor code like "04_97").
- marketplace_products.json: marketplace listings; shop_id is the platform's own shop (3 values for
  every product), NOT a seller. A marketplace listing gets a seller only when its description starts
  with the name of a map seller in the same province and district.

A seller is one shop_name in one district. Listings are kept one row each; deciding which listings
are the same product is the Resolve stage's job.

Also: areas_16.json (the programme's cultural areas) and the festival / culture / article /
entrepreneur pages (publications; reviewers found activities, businesses and people in them).
"""

from __future__ import annotations

import re

from ..text import clean_or_none, norm, strip_html

MAP, MARKET, AREAS = "product_map.json", "marketplace_products.json", "areas_16.json"
# page file -> (publication kind, id field, title field, text fields)
PAGES = {"festivals.json": ("festival", "festival_id", "title", ("description_text",)),
         "cultures.json": ("culture", "culture_id", "title", ("summary_html",)),
         "articles.json": ("article", "article_id", "title", ("summary_html",)),
         "entrepreneurs.json": ("entrepreneur", "entrepreneur_id", "title", ())}
VENDOR_CODE = re.compile(r"\s*\b\d{2}_\d+$")
CODE_ONLY = re.compile(r"^[\d_\-\s]*$")
# Category words AtLocal uses; "อาหาร 04_34" is a code with a category in front, not a name.
CATEGORY_WORDS = {"อาหาร", "ของใช้", "ความสวยงาม", "ความเชื่อ"}
# Map listings and areas give image file names; the site serves them from these folders.
ITEM_IMAGE, SHOP_IMAGE = "https://atlocalthailand.com/api/s9001/get_image_item/", "https://atlocalthailand.com/api/s9001/get_image_shop/"


def clean(raw, geo) -> dict[str, list[dict]]:
    operators: dict[str, dict] = {}
    offerings, links = [], []
    for index, item in enumerate(raw.json(MAP)["data"]):
        place = geo.place(item.get("province"), item.get("district"))
        seller = _seller(operators, norm(item.get("shop_name")), place, item, f"{MAP}#data/{index}")
        if seller:
            links.append(_link(f"product_map:{item['map_product_id']}", seller, "map_shop_name"))
        offerings.append({
            "record_id": f"product_map:{item['map_product_id']}",
            "kind": "listed",
            "name": norm(item.get("name")),
            "category": clean_or_none((item.get("product_type") or {}).get("name")),
            "price_thb": item.get("price_thb"),
            **place,
            "url": item.get("map_url"),
            "raw_ref": f"{MAP}#data/{index}",
            "details": {"tags": item.get("tags"), "images": [ITEM_IMAGE + f for f in item.get("image_filenames") or []],
                        "sale_channel": (item.get("sale_channel") or {}).get("name"),
                        "fulfilment": (item.get("fulfilment_status") or {}).get("name"),
                        "exclusive": item.get("exclusive")},
        })

    for index, item in enumerate(raw.json(MARKET)["data"]):
        place = geo.place(item.get("province"), item.get("district"))
        description = norm(item.get("description_raw"))
        seller = _seller_in_description(operators, description, place)
        if seller:
            links.append(_link(f"marketplace_products:{item['marketplace_product_id']}", seller,
                               "description_starts_with_map_seller_name"))
        offerings.append({
            "record_id": f"marketplace_products:{item['marketplace_product_id']}",
            "kind": "listed",
            "name": norm(item.get("name")),
            "description": description or None,
            "category": clean_or_none(item.get("category")),
            "price_thb": item.get("price_thb"),
            **place,
            "url": item.get("product_url"),
            "raw_ref": f"{MARKET}#data/{index}",
            "details": {"platform_shop_id": item.get("shop_id"), "active": item.get("active"),
                        "stock": item.get("stock_quantity"), "images": item.get("image_urls")},
        })
    areas = [{"record_id": f"areas_16:{item['area_id']}", "title": norm(item.get("name")), "category": "area",
              "description": clean_or_none(item.get("description_raw")),
              **geo.place(item.get("province"), item.get("district")), "raw_ref": f"{AREAS}#data/{index}",
              "details": {"images": [SHOP_IMAGE + f for f in item.get("image_filenames") or []]}}
             for index, item in enumerate(raw.json(AREAS)["data"])]
    publications = []
    for name, (kind, id_field, title_field, text_fields) in PAGES.items():
        for index, item in enumerate(raw.json(name)["data"]):
            publications.append({
                "record_id": f"{name.removesuffix('.json')}:{item[id_field]}", "kind": kind,
                "title": norm(item.get(title_field)),
                "text": "\n".join(filter(None, (strip_html(item.get(f)) for f in text_fields))) or None,
                "published_at": item.get("published_date"), "url": item.get("source_url") or item.get("detail_api_url"),
                "raw_ref": f"{name}#data/{index}",
                "details": {k: item.get(k) for k in ("type_raw", "area", "province", "active", "highlight_id") if k in item}})
    return {"operators": list(operators.values()), "offerings": offerings, "offering_operators": links,
            "cultural_records": areas, "publications": publications}


def _link(offering: str, operator: str, basis: str) -> dict:
    return {"offering_record_id": offering, "operator_record_id": operator, "relationship": "seller", "basis": basis}


def _seller(operators: dict, name: str, place: dict, item: dict, raw_ref: str) -> str | None:
    if not name:
        return None
    record_id = f"{name}|{place['province_code'] or norm(item.get('province'))}|" \
                f"{place['district_code'] or norm(item.get('district'))}"
    if record_id not in operators:
        bare = VENDOR_CODE.sub("", name).strip()
        operators[record_id] = {
            "record_id": record_id,
            "kind": "listed",
            "name": name,
            "name_quality": "code" if CODE_ONLY.match(name) or bare in CATEGORY_WORDS else "named",
            **place,
            "address_raw": " / ".join(filter(None, [norm(item.get("district")), norm(item.get("province"))])),
            "raw_ref": raw_ref,
            "details": {"vendor_code": (VENDOR_CODE.search(name) or [None])[0]},
        }
    return record_id


def _seller_in_description(operators: dict, description: str, place: dict) -> str | None:
    """The one map seller whose name the description starts with (or equals), in the same place."""
    text = description.casefold()
    if not place["province_code"]:
        return None
    found = []
    for op in operators.values():
        same_place = op["province_code"] == place["province_code"] and (
            not place["district_code"] or op["district_code"] == place["district_code"])
        if same_place and op["name_quality"] == "named" and any(
                text == name or (text.startswith(name) and len(text) > len(name) and text[len(name)] in " ,:;(/-–")
                for name in _names(op)):
            found.append(op)
    exact = [op for op in found if text in _names(op)]
    found = exact or found
    # Prefer a full written name over its shorter prefix ("ใบคราม สกล" over "ใบคราม").
    found = [op for op in found if not any(o is not op and o["name"].casefold().startswith(op["name"].casefold() + " ")
                                           for o in found)]
    return found[0]["record_id"] if len(found) == 1 else None


def _names(op: dict) -> set[str]:
    """The seller name, also without a trailing vendor code ("I-Destiny & Gallery Resort 09_59")."""
    return {op["name"].casefold(), VENDOR_CODE.sub("", op["name"]).strip().casefold()}
