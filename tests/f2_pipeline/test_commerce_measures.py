import copy

import pytest

from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.domains import commerce, reviewed_commerce, programme_coverage
from tools.f2_pipeline.commerce_comparison import COMMERCE_MEASURES
from tools.f2_pipeline.commerce_measures import assemble_commerce_measures
from tools.f2_pipeline.commerce_validation import validate_commerce_tables
from tools.f2_pipeline.query import EntityQuery


def _fixture():
    domains = {
        "commerce_baseline": {name: [] for name in commerce.TABLE_COLUMNS},
        "commerce": {name: [] for name in reviewed_commerce.TABLE_COLUMNS},
        "programme_coverage": {name: [] for name in programme_coverage.TABLE_COLUMNS},
    }
    business = domains["commerce"]
    business["global_operators"] = [
        {"global_operator_id": "operator", "display_name": "Reviewed operator"}
    ]
    business["global_offerings"] = [
        {"global_offering_id": item, "display_name": item}
        for item in ("product-a", "product-b")
    ]
    business["operator_crosswalk"] = [
        {
            "source_operator_id": local,
            "global_operator_id": "operator",
            "source_details_json": "{}",
        }
        for local in ("source-a:seller", "source-b:seller")
    ]
    business["offering_crosswalk"] = [
        {
            "source_offering_id": "source-" + suffix + ":product",
            "global_offering_id": "product-" + suffix,
        }
        for suffix in ("a", "b")
    ]
    business["offering_families"] = [
        {
            "family_id": "family",
            "display_name": "One reviewed family",
            "member_count": 2,
        }
    ]
    business["offering_family_members"] = [
        {
            "family_id": "family",
            "global_offering_id": "product-a",
            "membership_role": "family_representation",
        },
        {
            "family_id": "family",
            "global_offering_id": "product-b",
            "membership_role": "variant",
        },
    ]
    business["seller_evidence"] = [
        {"source_seller_evidence_id": "seller-proof", "global_operator_id": "operator"}
    ]
    business["listing_evidence"] = [
        {
            "source_listing_id": "listing-" + suffix,
            "global_offering_id": "product-" + suffix,
        }
        for suffix in ("a", "b")
    ]
    business["measure_contributions"] = [
        {"measure": "K05_source_supported_operators", "entity_id": "operator"},
        {"measure": "K07_source_reported_offerings", "entity_id": "family"},
    ]
    business["locations"] = [
        {
            "source_location_id": "product-location-" + suffix,
            "source_entity_id": "source-" + suffix + ":product",
            "source_offering_id": "source-" + suffix + ":product",
            "global_offering_id": "product-" + suffix,
            "source_operator_id": "source-" + suffix + ":seller",
            "global_operator_id": "operator",
            "province_code": code,
            "location_role": "offering_listing_address",
        }
        for suffix, code in (("a", "10"), ("b", "20"))
    ] + [
        {
            "source_location_id": "operator-location",
            "source_entity_id": "source-a:seller",
            "source_operator_id": "source-a:seller",
            "global_operator_id": "operator",
            "source_offering_id": "source-a:product",
            "global_offering_id": "product-a",
            "province_code": "30",
            "location_role": "source_operator_address",
        }
    ]
    for name in domains["commerce_baseline"]:
        domains["commerce_baseline"][name] = copy.deepcopy(business[name])
    domains["commerce_baseline"]["measure_contributions"] = [
        {"measure": "K05_source_supported_operators", "entity_id": "operator"},
        *(
            {"measure": "K07_source_reported_offerings", "entity_id": item}
            for item in ("product-a", "product-b")
        ),
    ]
    coverage = domains["programme_coverage"]
    coverage["coverage_assertions"] = [
        {
            "coverage_assertion_id": "accepted",
            "province_code": "10",
            "disposition": "qualifying_resolved",
        },
        {
            "coverage_assertion_id": "unknown",
            "province_code": "",
            "disposition": "qualifying_unknown_province",
        },
        {
            "coverage_assertion_id": "institution",
            "province_code": "20",
            "disposition": "excluded_role_or_context",
        },
    ]
    coverage["province_evidence_index"] = [
        {"province_code": "10", "province_name": "A", "qualifying_assertion_count": 1}
    ]
    coverage["measure_contributions"] = [
        {
            "measure": "K01A_supported_target_provinces",
            "entity_id": "th-province:10",
            "province_code": "10",
            "contributor_ids_json": '["accepted"]',
        }
    ]
    root = {
        name: []
        for name in (
            "entity_contributions",
            "evidence_links",
            "eligibility_evidence",
            "province_memberships",
            "category_memberships",
            "aggregate_breakdowns",
        )
    }
    provinces = [
        {
            "province_code": code,
            "province_name_th": name,
            "region": "Region",
            "region_id": "r",
        }
        for code, name in (("10", "A"), ("20", "B"), ("30", "C"))
    ]
    return root, domains, provinces


def test_family_union_preserves_variants_without_borrowing_relationship_geography():
    original, domains, provinces = _fixture()
    before = copy.deepcopy((original, domains))
    root = assemble_commerce_measures(original, domains)
    assert all(
        row["status"] == "passed"
        for row in validate_commerce_tables(
            root, domains, provinces, list(COMMERCE_MEASURES)
        )
    )
    assert (original, domains) == before
    memberships = {
        (row["measure_id"], row["entity_id"], row["province_code"])
        for row in root["province_memberships"]
    }
    assert memberships == {
        ("K01A", "10", "10"),
        ("K05", "operator", "30"),
        ("K07", "family", "10"),
        ("K07", "family", "20"),
    }
    query = EntityQuery(
        {
            "measure_id": "K07",
            "unit": "product_family",
            "status": "substitute_partial_coverage",
            "supported_filters": ["province"],
        },
        root,
        provinces,
    )
    assert query.select({"province": ["10", "20"]})["result"]["value"] == 1
    assert query.select({"province": ["30"]})["result"]["value"] == 0
    assert {
        row["evidence_id"]
        for row in root["eligibility_evidence"]
        if row["measure_id"] == "K07"
    } == {"listing-a", "listing-b"}


@pytest.mark.parametrize(
    "fault",
    [
        "borrow_product_province",
        "drop_variant_proof",
        "count_unknown_province",
        "drop_offering_variant",
    ],
)
def test_commerce_validation_rejects_semantic_breaks_even_when_national_counts_can_match(
    fault,
):
    original, domains, provinces = _fixture()
    root = assemble_commerce_measures(original, domains)
    if fault == "borrow_product_province":
        product = next(
            row for row in root["province_memberships"] if row["measure_id"] == "K07"
        )
        root["province_memberships"].append(
            {**product, "measure_id": "K05", "entity_id": "operator"}
        )
    elif fault == "drop_variant_proof":
        root["eligibility_evidence"] = [
            row
            for row in root["eligibility_evidence"]
            if row["evidence_id"] != "listing-b"
        ]
    elif fault == "count_unknown_province":
        root["entity_contributions"].append(
            {"measure_id": "K01A", "entity_id": "20", "label": "Excluded institution"}
        )
    else:
        domains["commerce"]["offering_family_members"].pop()
    with pytest.raises(PipelineError, match="Commerce relationship validation failed"):
        validate_commerce_tables(root, domains, provinces, list(COMMERCE_MEASURES))


