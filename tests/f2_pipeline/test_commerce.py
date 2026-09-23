import copy

import pytest

from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.domains.commerce import TABLE_COLUMNS, build_tables, stable_id


CANONICAL = {
    "atlocal": "f2_cultural_market_civil",
    "cultural_map": "f2_culturalmap_university",
    "icommunity": "f2_icommunity",
}


def _raw(source_id):
    return {
        "datasets": {"items": {"data": [{"source": source_id}]}},
        "metadata": {
            "items": {
                "source_id": source_id,
                "run_id": "run",
                "file": "items.json",
                "sha256": "expanded-hash",
            }
        },
        "files": [
            {
                "path": "items.json",
                "sha256": "expanded-hash",
                "size": 1,
                "dataset_key": "items",
            },
            {
                "path": "items.json.gz",
                "sha256": "gzip-hash",
                "size": 1,
                "dataset_key": "items",
            },
        ],
    }


def _observation(source_id, observation_id, source_key):
    return {
        "observation_id": observation_id,
        "source_id": source_key,
        "source_key": source_key,
        "raw_file": "items.json",
        "row_locator": "data/0",
        "file_sha256": "expanded-hash",
    }


def _source_tables():
    atlocal = {
        "source_observations": [
            _observation(CANONICAL["atlocal"], "ao", "atlocal-source")
        ],
        "products": [
            {
                "product_id": "a-product",
                "name": "AtLocal Product",
                "aliases_json": '["AtLocal alias"]',
                "source_keys_json": '["atlocal-source"]',
                "identity_status": "reviewed_source_local",
                "name_quality": "named_offering",
            }
        ],
        "sellers": [
            {
                "seller_id": "a-seller",
                "name": "Shared Operator",
                "province": "Alpha",
                "district": "A",
                "province_code": "10",
                "district_code": "1001",
                "identity_status": "reviewed_source_local",
                "name_quality": "named_operator",
            }
        ],
        "listing_observations": [
            {
                "listing_id": "a-listing",
                "observation_id": "ao",
                "source_key": "atlocal-source",
                "product_id": "a-product",
                "seller_id": "a-seller",
                "name_raw": "AtLocal Product",
                "name_normalized": "AtLocal Product",
                "description": "A description",
                "category_raw": "craft",
                "source_url": "https://example.test/a",
                "product_eligibility": "source_reported_offering",
            }
        ],
        "seller_evidence": [
            {
                "seller_id": "a-seller",
                "observation_id": "ao",
                "source_key": "atlocal-source",
                "evidence": "Shared Operator",
                "basis": "seller_field",
            }
        ],
        "product_sellers": [
            {
                "product_id": "a-product",
                "seller_id": "a-seller",
                "observation_id": "ao",
                "relationship": "source_listed_product_operator",
            }
        ],
        "locations": [
            {
                "location_id": "a-product-location",
                "observation_id": "ao",
                "entity_id": "a-product",
                "source_key": "atlocal-source",
                "location_role": "offering_location",
                "province_raw": "Alpha",
                "district_raw": "A",
                "province_normalized": "Alpha",
                "province_code": "10",
                "district_normalized": "A",
                "district_code": "1001",
                "subdistrict_normalized": "",
                "subdistrict_code": "",
                "status": "resolved",
            },
            {
                "location_id": "a-operator-location",
                "observation_id": "ao",
                "entity_id": "a-seller",
                "source_key": "atlocal-source",
                "location_role": "operator_location",
                "province_raw": "Alpha",
                "district_raw": "A",
                "province_normalized": "Alpha",
                "province_code": "10",
                "district_normalized": "A",
                "district_code": "1001",
                "subdistrict_normalized": "",
                "subdistrict_code": "",
                "status": "resolved",
            },
        ],
        "product_prices": [
            {
                "observation_id": "ao",
                "product_id": "a-product",
                "source_key": "atlocal-source",
                "amount_raw": "25",
                "amount_thb": "25",
                "currency": "THB",
                "interpretation": "parsed",
            }
        ],
        "images": [
            {
                "image_id": "a-image",
                "observation_id": "ao",
                "product_id": "a-product",
                "source_key": "atlocal-source",
                "image_url": "https://example.test/a.jpg",
                "status": "source_reference_not_inspected",
            }
        ],
        "listing_channels": [
            {
                "observation_id": "ao",
                "product_id": "a-product",
                "source_key": "atlocal-source",
                "channel": "marketplace",
                "platform_shop_id": "shop-a",
                "sale_channel_json": "[]",
            }
        ],
        "people": [{"person_id": "a-person"}],
        "person_sellers": [
            {
                "person_id": "a-person",
                "seller_id": "a-seller",
                "observation_id": "ao",
                "relationship": "owner_operator",
            }
        ],
        "identity_decisions": [],
        "review_cases": [],
    }
    cultural = {
        "source_observations": [
            _observation(CANONICAL["cultural_map"], "co", "cultural-source")
        ],
        "offerings": [
            {
                "offering_id": "c-offering",
                "display_title": "Cultural Product",
                "aliases_json": "[]",
                "source_keys_json": '["cultural-source"]',
                "identity_status": "reviewed_source_local",
                "cultural_scope_eligibility": "eligible",
                "generic_name_flag": "False",
            }
        ],
        "sellers": [
            {
                "seller_id": "c-seller",
                "name": "Shared Operator",
                "identity_status": "reviewed_source_local",
                "source_scope": "cultural_map_only",
                "current_status": "source_reported_operator",
            }
        ],
        "offering_listing_observations": [
            {
                "listing_id": "c-listing",
                "offering_id": "c-offering",
                "observation_id": "co",
                "source_key": "cultural-source",
                "title_raw": "Cultural Product",
                "title_normalized": "Cultural Product",
                "description": "C description",
                "product_category_raw": "craft",
                "seller_id": "c-seller",
                "sales_channels_raw": "contact",
                "sales_accounts_json": "[]",
                "external_links_json": "[]",
                "source_url": "https://example.test/c",
            }
        ],
        "seller_evidence": [
            {
                "evidence_id": "c-seller-evidence",
                "seller_id": "c-seller",
                "offering_id": "c-offering",
                "observation_id": "co",
                "source_key": "cultural-source",
                "role": "source_reported_operator",
                "evidence_passage": "Shared Operator",
                "basis": "seller_field",
            }
        ],
        "product_sellers": [
            {
                "relationship_id": "c-edge",
                "offering_id": "c-offering",
                "seller_id": "c-seller",
                "observation_id": "co",
                "source_key": "cultural-source",
                "relationship": "source_listed_product_operator",
                "evidence_passage": "Shared Operator",
            }
        ],
        "offering_locations": [
            {
                "location_id": "c-location",
                "offering_id": "c-offering",
                "observation_id": "co",
                "source_key": "cultural-source",
                "location_role": "offering_location",
                "province_raw": "Beta",
                "district_raw": "B",
                "province_normalized": "Beta",
                "province_code": "20",
                "district_normalized": "B",
                "district_code": "2001",
                "subdistrict_normalized": "",
                "subdistrict_code": "",
                "status": "resolved",
            }
        ],
        "offering_prices": [
            {
                "price_id": "c-price",
                "offering_id": "c-offering",
                "observation_id": "co",
                "source_key": "cultural-source",
                "price_text_raw": "100",
                "amounts_json": '["100"]',
                "currency": "THB",
                "parse_status": "parsed",
            }
        ],
        "offering_media": [
            {
                "media_id": "c-media",
                "offering_id": "c-offering",
                "observation_id": "co",
                "source_key": "cultural-source",
                "media_kind": "image",
                "ordinal": "0",
                "url_or_value": "https://example.test/c.jpg",
                "label": "",
                "status": "source_reference_not_inspected",
            }
        ],
        "people": [],
        "person_role_evidence": [],
        "identity_decisions": [],
        "review_cases": [],
    }
    icommunity = {
        "source_observations": [
            _observation(CANONICAL["icommunity"], "io", "icommunity-source")
        ],
        "products": [
            {
                "product_id": "i-product",
                "observation_id": "io",
                "source_id": "source-product-i",
                "name": "iCommunity Product",
                "description": "I description",
                "permalink": "https://example.test/i",
                "categories_json": "[]",
                "images_json": '[{"src":"https://example.test/i.jpg","name":"I"}]',
                "identity_status": "source_listing_provisional",
            }
        ],
        "sellers": [
            {
                "seller_id": "i-seller",
                "name": "Third Operator",
                "province": "Gamma",
                "identity_status": "source_listed_operator_provisional",
            }
        ],
        "product_sellers": [
            {
                "product_id": "i-product",
                "seller_id": "i-seller",
                "observation_id": "io",
                "evidence_passage": "Third Operator",
                "relationship": "source_listed_product_operator",
            }
        ],
        "product_prices": [
            {
                "product_id": "i-product",
                "observation_id": "io",
                "price_kind": "price",
                "amount_raw": "5000",
                "minor_unit": "2",
                "currency": "THB",
                "amount_thb": "50",
            }
        ],
        "locations": [
            {
                "location_id": "i-location",
                "observation_id": "io",
                "entity_id": "i-product",
                "location_role": "cultural_product_area",
                "province_raw": "Gamma",
                "district_raw": "C",
                "province_normalized": "Gamma",
                "province_code": "30",
                "district_normalized": "C",
                "district_code": "3001",
                "subdistrict_normalized": "",
                "subdistrict_code": "",
                "status": "resolved",
            }
        ],
        "review_cases": [],
    }
    return {
        CANONICAL["atlocal"]: atlocal,
        CANONICAL["cultural_map"]: cultural,
        CANONICAL["icommunity"]: icommunity,
    }


def _runtime(offering_reviews=0, operator_reviews=0):
    return {
        "schema_version": 1,
        "review_counts": {
            "offerings": offering_reviews,
            "operators": operator_reviews,
        },
        "review_file": "review-config://cross_source_offerings/reviews/reviewed_evidence.json",
        "source_input_pins": [
            {
                "path": f"evidence://{source_id}/run/items.json.gz",
                # The rebased URI may name the canonical gzip while the review
                # pins the expanded dataset hash.
                "sha256": "expanded-hash",
            }
            for source_id in CANONICAL.values()
        ]
        + [
            {
                "path": "normalized://source_local/atlocal-v1/products.csv",
                "sha256": "obsolete-derived-hash",
            },
            {
                "path": "normalized://source_local/cultural-map-v1/offerings.csv",
                "sha256": "obsolete-derived-hash",
            },
            {
                "path": "normalized://source_local/icommunity-v1/products.csv",
                "sha256": "obsolete-derived-hash",
            },
            {
                "path": "normalized://cross_source/people-v1/person_crosswalk.csv",
                "sha256": "obsolete-derived-hash",
            },
        ],
    }


def _citation(source):
    observation_id = {"atlocal": "ao", "cultural_map": "co", "icommunity": "io"}[source]
    source_key = {
        "atlocal": "atlocal-source",
        "cultural_map": "cultural-source",
        "icommunity": "icommunity-source",
    }[source]
    return {
        "observation_id": observation_id,
        "source_key": source_key,
        "raw_locator": f"evidence://{CANONICAL[source]}/run/items.json.gz#data/0",
    }


def _review(review_id, decision, kind, left, right):
    return {
        "review_id": review_id,
        "decision": decision,
        "decision_origin": "analyst_review",
        "entity_kind": kind,
        "left": {
            "source": left[0],
            "local_id": left[1],
            "citations": [_citation(left[0])],
        },
        "right": {
            "source": right[0],
            "local_id": right[1],
            "citations": [_citation(right[0])],
        },
        "reason": "synthetic reviewed identity decision",
        "status": "reviewed",
    }


def _inputs(additional_reviews=(), *, offering_reviews=0, operator_reviews=0):
    source_tables = _source_tables()
    reviews = {
        "cross_source_offerings/runtime.json": _runtime(
            offering_reviews, operator_reviews
        ),
        "cross_source_offerings/reviews/reviewed_evidence.json": {
            "offering_reviews": [],
            "operator_reviews": [],
            "additional_reviews": list(additional_reviews),
        },
    }
    raw_inputs = {source_id: _raw(source_id) for source_id in CANONICAL.values()}
    people_tables = {
        "person_crosswalk": [
            {
                "source_entity_id": "atlocal:a-person",
                "global_person_id": "global_person_approved",
            }
        ]
    }
    return source_tables, reviews, raw_inputs, people_tables


def test_build_preserves_all_source_evidence_and_role_specific_locations():
    source_tables, reviews, raw_inputs, people_tables = _inputs()
    before = copy.deepcopy((source_tables, reviews, raw_inputs, people_tables))

    tables = build_tables(
        source_tables, reviews, raw_inputs, geography=None, people_tables=people_tables
    )

    assert (source_tables, reviews, raw_inputs, people_tables) == before
    assert set(tables) == set(TABLE_COLUMNS)
    assert all(
        tuple(row) == TABLE_COLUMNS[table]
        for table, rows in tables.items()
        for row in rows
    )
    canonical_raw = next(
        row
        for row in tables["source_files"]
        if row["path"] == "evidence://f2_cultural_market_civil/run/items.json.gz"
    )
    assert canonical_raw == {
        "path": "evidence://f2_cultural_market_civil/run/items.json.gz",
        "sha256": "gzip-hash",
        "fingerprint_kind": "raw_file",
        "reviewed_sha256": "expanded-hash",
    }
    assert len(tables["listing_evidence"]) == 3
    assert len(tables["operator_offering_edges"]) == 3
    assert len(tables["prices"]) == 3
    assert len(tables["media"]) == 3
    assert tables["person_operator_links"][0]["global_person_id"] == (
        "global_person_approved"
    )
    assert len(tables["channels"]) == 2
    offering_location = next(
        row
        for row in tables["locations"]
        if row["source_location_id"] == "atlocal:a-product-location"
    )
    operator_location = next(
        row
        for row in tables["locations"]
        if row["source_location_id"] == "atlocal:a-operator-location"
    )
    assert offering_location["global_offering_id"]
    assert not offering_location["global_operator_id"]
    assert operator_location["global_operator_id"]
    assert not operator_location["global_offering_id"]
    contextual_product_location = next(
        row
        for row in tables["locations"]
        if row["source_location_id"] == "icommunity:i-location"
    )
    assert contextual_product_location["source_operator_id"]
    assert (
        contextual_product_location["source_entity_id"]
        == contextual_product_location["source_offering_id"]
    )
    assert (
        contextual_product_location["source_entity_id"]
        != contextual_product_location["source_operator_id"]
    )
    assert all(
        row["raw_locator"].startswith("evidence://")
        for row in tables["listing_evidence"]
    )


def test_reviewed_operator_match_does_not_merge_unrelated_products_and_ids_are_stable():
    review = _review(
        "operator-match",
        "match",
        "operator",
        ("atlocal", "a-seller"),
        ("cultural_map", "c-seller"),
    )
    source_tables, reviews, raw_inputs, people_tables = _inputs(
        [review], operator_reviews=1
    )

    tables = build_tables(
        source_tables, reviews, raw_inputs, geography=None, people_tables=people_tables
    )

    matched = next(
        row for row in tables["global_operators"] if row["source_count"] == 2
    )
    assert matched["global_operator_id"] == stable_id(
        "operator", "atlocal:a-seller", "cultural_map:c-seller"
    )
    assert len(tables["global_offerings"]) == 3
    assert len({row["global_offering_id"] for row in tables["offering_crosswalk"]}) == 3
    assert {
        row["global_offering_id"]
        for row in tables["operator_offering_edges"]
        if row["global_operator_id"] == matched["global_operator_id"]
    } == {
        stable_id("offering", "atlocal:a-product"),
        stable_id("offering", "cultural_map:c-offering"),
    }


def test_protected_separation_blocks_a_transitive_review_bridge():
    reviews_to_apply = [
        _review(
            "01-atlocal-cultural-match",
            "match",
            "offering",
            ("atlocal", "a-product"),
            ("cultural_map", "c-offering"),
        ),
        _review(
            "02-atlocal-icommunity-separate",
            "keep_separate",
            "offering",
            ("atlocal", "a-product"),
            ("icommunity", "i-product"),
        ),
        _review(
            "03-cultural-icommunity-match",
            "match",
            "offering",
            ("cultural_map", "c-offering"),
            ("icommunity", "i-product"),
        ),
    ]
    source_tables, reviews, raw_inputs, people_tables = _inputs(
        reviews_to_apply, offering_reviews=3
    )

    with pytest.raises(PipelineError, match="protected component boundary"):
        build_tables(
            source_tables,
            reviews,
            raw_inputs,
            geography=None,
            people_tables=people_tables,
        )


def test_review_raw_locator_must_resolve_to_its_current_listing():
    review = _review(
        "operator-match",
        "match",
        "operator",
        ("atlocal", "a-seller"),
        ("cultural_map", "c-seller"),
    )
    review["left"]["citations"][0]["raw_locator"] = (
        "evidence://f2_cultural_market_civil/old/items.json.gz#data/0"
    )
    source_tables, reviews, raw_inputs, people_tables = _inputs(
        [review], operator_reviews=1
    )

    with pytest.raises(PipelineError, match="review raw locator is stale"):
        build_tables(
            source_tables,
            reviews,
            raw_inputs,
            geography=None,
            people_tables=people_tables,
        )


def test_review_observation_id_rebases_only_through_same_endpoint_and_raw_record():
    review = _review(
        "operator-match",
        "match",
        "operator",
        ("atlocal", "a-seller"),
        ("cultural_map", "c-seller"),
    )
    source_tables, reviews, raw_inputs, people_tables = _inputs(
        [review], operator_reviews=1
    )
    cultural = source_tables[CANONICAL["cultural_map"]]
    cultural["source_observations"][0]["observation_id"] = "co-current"
    for table in (
        "offering_listing_observations",
        "seller_evidence",
        "product_sellers",
        "offering_locations",
        "offering_prices",
        "offering_media",
    ):
        cultural[table][0]["observation_id"] = "co-current"

    tables = build_tables(
        source_tables,
        reviews,
        raw_inputs,
        geography=None,
        people_tables=people_tables,
    )

    assert any(row["source_count"] == 2 for row in tables["global_operators"])


def test_cross_source_reviews_cannot_collapse_two_source_local_operators():
    source_tables, reviews, raw_inputs, people_tables = _inputs(operator_reviews=1)
    atlocal = source_tables[CANONICAL["atlocal"]]
    atlocal["source_observations"].append(
        _observation(CANONICAL["atlocal"], "ao2", "atlocal-second")
    )
    atlocal["products"].append(
        {
            "product_id": "a-product-2",
            "name": "Second Product",
            "aliases_json": "[]",
            "source_keys_json": '["atlocal-second"]',
            "identity_status": "reviewed_source_local",
            "name_quality": "named_offering",
        }
    )
    atlocal["sellers"].append(
        {
            "seller_id": "a-seller-2",
            "name": "Second Operator",
            "identity_status": "reviewed_source_local",
            "name_quality": "named_operator",
        }
    )
    atlocal["listing_observations"].append(
        {
            "listing_id": "a-listing-2",
            "observation_id": "ao2",
            "source_key": "atlocal-second",
            "product_id": "a-product-2",
            "seller_id": "a-seller-2",
            "name_raw": "Second Product",
            "name_normalized": "Second Product",
            "description": "",
            "category_raw": "",
            "source_url": "",
            "product_eligibility": "source_reported_offering",
        }
    )
    atlocal["seller_evidence"].append(
        {
            "seller_id": "a-seller-2",
            "observation_id": "ao2",
            "source_key": "atlocal-second",
            "evidence": "Second Operator",
            "basis": "seller_field",
        }
    )
    atlocal["product_sellers"].append(
        {
            "product_id": "a-product-2",
            "seller_id": "a-seller-2",
            "observation_id": "ao2",
            "relationship": "source_listed_product_operator",
        }
    )
    citation = {
        "observation_id": "ao2",
        "source_key": "atlocal-second",
        "raw_locator": "evidence://f2_cultural_market_civil/run/items.json.gz#data/0",
    }
    reviews["cross_source_offerings/reviews/reviewed_evidence.json"][
        "additional_reviews"
    ] = [
        {
            "review_id": "invalid-same-source-match",
            "decision": "match",
            "decision_origin": "analyst_review",
            "entity_kind": "operator",
            "left": {
                "source": "atlocal",
                "local_id": "a-seller",
                "citations": [_citation("atlocal")],
            },
            "right": {
                "source": "atlocal",
                "local_id": "a-seller-2",
                "citations": [citation],
            },
            "reason": "synthetic invalid merge",
            "status": "reviewed",
        }
    ]

    with pytest.raises(PipelineError, match="collapses source-local identities"):
        build_tables(
            source_tables,
            reviews,
            raw_inputs,
            geography=None,
            people_tables=people_tables,
        )


def test_normalized_pin_resolves_the_fresh_table_not_its_obsolete_csv_hash():
    source_tables, reviews, raw_inputs, people_tables = _inputs()

    first = build_tables(
        source_tables, reviews, raw_inputs, geography=None, people_tables=people_tables
    )
    path = "normalized://source_local/atlocal-v1/products.csv"
    first_fingerprint = next(
        row for row in first["source_files"] if row["path"] == path
    )
    source_tables[CANONICAL["atlocal"]]["products"][0]["name"] = "Changed Product"
    second = build_tables(
        source_tables, reviews, raw_inputs, geography=None, people_tables=people_tables
    )
    second_fingerprint = next(
        row for row in second["source_files"] if row["path"] == path
    )
    assert first_fingerprint["fingerprint_kind"] == "canonical_json_table"
    assert second_fingerprint["sha256"] != first_fingerprint["sha256"]
    assert (
        second_fingerprint["reviewed_sha256"]
        == first_fingerprint["reviewed_sha256"]
        == "obsolete-derived-hash"
    )
    del source_tables[CANONICAL["atlocal"]]["products"]

    with pytest.raises(PipelineError, match="missing normalized producer endpoint"):
        build_tables(
            source_tables,
            reviews,
            raw_inputs,
            geography=None,
            people_tables=people_tables,
        )
