from tools.f2_pipeline.sources.atlocal import TABLE_COLUMNS, build_tables


class Geography:
    reference_version = "geo-v1"

    def resolve(self, province, district):
        return {
            "province_raw": province,
            "district_raw": district,
            "province_normalized": province,
            "province_code": "10",
            "district_normalized": district,
            "district_code": "1001",
            "subdistrict_normalized": "",
            "subdistrict_code": "",
            "status": "hierarchy_match",
            "correction_reason": "",
        }


def envelope(rows):
    return {
        "data": rows,
        "record_count": len(rows),
        "scraped_at": "2026-01-01T00:00:00Z",
    }


def narrative(identifier, title, content):
    return {
        identifier[0]: identifier[1],
        "title": title,
        "description_html": f"<p>{content}</p>",
    }


def metadata(datasets):
    return {
        key: {
            "source_id": "atlocal",
            "run_id": "run-1",
            "file": f"{key}.json",
            "sha256": f"sha-{key}",
            "size": 1,
            "captured_at": "2026-01-01T00:00:00Z",
            "originating_system": "synthetic",
        }
        for key in datasets
    }


def test_recovered_offering_alias_and_narrative_people_preserve_legacy_relations():
    datasets = {
        "areas": envelope([]),
        "articles": envelope(
            [
                narrative(("article_id", 1), "ลุงแป๊ะ", "ปราโมช เชี่ยวชาญ จำหน่ายสินค้า"),
                narrative(("article_id", 2), "ศรีบาติก", "คุณป้าผลศรี เจ้าของร้านศรีบาติก"),
            ]
        ),
        "cultures": envelope([narrative(("culture_id", 15), "ศรีบาติก", "คุณป้าผลศรี")]),
        "entrepreneurs": envelope(
            [
                narrative(("entrepreneur_id", 1), "ศรีบาติก", "คุณป้าผลศรี"),
                narrative(("entrepreneur_id", 2), "ลุงแป๊ะ", "ปราโมช เชี่ยวชาญ"),
                narrative(("entrepreneur_id", 3), "กลุ่ม", "กลุ่มผู้ผลิต"),
                narrative(("entrepreneur_id", 4), "แบรนด์", "ผู้สร้างไม่ระบุชื่อ"),
            ]
        ),
        "festivals": envelope([]),
        "marketplace_products": envelope(
            [
                {
                    "marketplace_product_id": 390,
                    "name": "ก๋วยเตี๋ยว",
                    "description_raw": "Alias Shop",
                    "province": "กรุงเทพมหานคร",
                    "district": "เมือง",
                    "price_thb": 25,
                    "image_urls": [],
                }
            ]
        ),
        "product_map": envelope(
            [
                {
                    "map_product_id": 1274,
                    "name": "",
                    "shop_name": "Alias Shop 01",
                    "description_raw": "",
                    "province": "กรุงเทพมหานคร",
                    "district": "เมือง",
                    "price_thb": 25,
                    "image_urls": [],
                }
            ]
        ),
    }
    reviews = {
        "reviewed_cases.json": {
            "seller_aliases": {"Alias Shop 01": "Alias Shop"},
            "cannot_link_products": [],
            "unresolved_product_groups": [],
            "expected_supported_pairs": [],
            "festivals": {},
            "reviewed_operator_merges": [],
            "recovered_offering_pairs": [
                ["marketplace_products:390", "product_map:1274"]
            ],
            "code_only_operators_eligible": True,
        },
        "prior_product_components.json": {
            "components": [
                {
                    "prior_product_id": "prior-noodles",
                    "source_keys": ["marketplace_products:390"],
                }
            ]
        },
    }

    tables = build_tables(datasets, reviews, Geography(), metadata(datasets))

    listings = {row["source_key"]: row for row in tables["listing_observations"]}
    assert (
        listings["marketplace_products:390"]["product_id"]
        == listings["product_map:1274"]["product_id"]
    )
    assert (
        listings["marketplace_products:390"]["seller_id"]
        == listings["product_map:1274"]["seller_id"]
    )
    assert (
        listings["product_map:1274"]["product_eligibility"]
        == "source_reported_offering"
    )
    assert {row["display_name"] for row in tables["people"]} == {
        "ปราโมช เชี่ยวชาญ",
        "คุณป้าผลศรี",
    }
    assert all(
        row["row_locator"].startswith("evidence://")
        for row in tables["source_observations"]
    )
    assert all(
        set(row) == set(TABLE_COLUMNS[name])
        for name, rows in tables.items()
        for row in rows
    )
