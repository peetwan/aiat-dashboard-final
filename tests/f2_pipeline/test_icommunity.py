from tools.f2_pipeline.sources.icommunity import DATASET_KEYS, RoleReviews, build_tables


def test_icommunity_exposes_full_source_bundle_boundary():
    assert callable(build_tables)
    assert "location_assertions" in DATASET_KEYS


def test_role_review_retains_unreviewed_protection():
    assert RoleReviews({}).decision(0, "entrepreneur")["status"] == "unreviewed"
