import json

import pytest

from tools.f2_pipeline.common import (
    PipelineError,
    digest,
    load_json,
    write_csv,
    write_json,
)
from tools.f2_pipeline.comparison_core import _baseline_reader
from tools.f2_pipeline.commerce_comparison import (
    COMMERCE_MEASURES,
    compare_commerce_content,
)
from tools.f2_pipeline.validation import load_release_tables, verify_release


def _write_frozen(root, tables):
    root.mkdir()
    files = {}
    for name, rows in tables.items():
        path = root / name
        write_csv(path, rows)
        files[name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    write_json(
        root / "manifest.json",
        {"release_id": "f2-dashboard-snapshot-v2", "files": files},
    )
    return root


def _commerce_tables(*, membership_role="variant", offering_global="offering-a"):
    return {
        "global_operators": [{"global_operator_id": "operator-a"}],
        "global_offerings": [
            {"global_offering_id": offering_global},
            {"global_offering_id": "offering-extra"},
        ],
        "operator_crosswalk": [
            {
                "global_operator_id": "operator-a",
                "source_operator_id": "operator-source-a",
            }
        ],
        "offering_crosswalk": [
            {
                "global_offering_id": offering_global,
                "source_offering_id": "offering-source-a",
            },
            {
                "global_offering_id": "offering-extra",
                "source_offering_id": "offering-source-extra",
            },
        ],
        "offering_families": [
            {
                "family_id": "family-a",
                "member_count": "2",
                "identity_status": "reviewed",
                "counting_basis": "product",
            }
        ],
        "offering_family_members": [
            {
                "family_id": "family-a",
                "global_offering_id": offering_global,
                "membership_role": "family_representation",
            },
            {
                "family_id": "family-a",
                "global_offering_id": "offering-extra",
                "membership_role": membership_role,
            },
        ],
        "reviewed_identity_decisions": [{"effective_decision": "accepted"}],
        "review_coverage": [
            {
                "candidate_id": "candidate-a",
                "source": "synthetic",
                "entity_kind": "offering",
                "status": "reviewed",
                "basis": "manual",
                "global_entity_id": offering_global,
                "output_type": "identity",
                "unit_basis": "row",
            }
        ],
        "reviewed_evidence": [
            {
                "candidate_id": "candidate-a",
                "source": "synthetic",
                "global_innovation_id": "innovation-a",
            }
        ],
        "identity_decisions": [{"effective_decision": "accepted"}],
        "listing_evidence": [
            {
                "source_listing_id": "listing-a",
                "global_offering_id": offering_global,
                "global_operator_id": "operator-a",
                "listing_eligibility": "included",
            }
        ],
        "seller_evidence": [
            {
                "source_seller_evidence_id": "seller-a",
                "global_operator_id": "operator-a",
                "global_offering_id": offering_global,
                "role": "seller",
            }
        ],
        "locations": [
            {
                "source_location_id": "location-a",
                "source_entity_id": "entity-a",
                "source_operator_id": "operator-source-a",
                "global_operator_id": "operator-a",
                "source_offering_id": "offering-source-a",
                "global_offering_id": offering_global,
                "province_code": "10",
                "location_role": "operator",
            }
        ],
        "operator_offering_edges": [
            {
                "source_operator_offering_edge_id": "edge-a",
                "source_operator_id": "operator-source-a",
                "global_operator_id": "operator-a",
                "source_offering_id": "offering-source-a",
                "global_offering_id": offering_global,
                "relationship": "offers",
            }
        ],
        "reviewed_relationships": [
            {
                "relationship_id": "relationship-a",
                "subject_global_id": "operator-a",
                "object_global_id": offering_global,
                "relationship": "offers",
            }
        ],
    }


def _fixture_tables(
    *,
    remove_k05_province=False,
    membership_role="variant",
    offering_global="offering-a",
):
    baseline_entities = [
        {"measure_id": measure, "entity_id": f"entity-{measure}"}
        for measure in COMMERCE_MEASURES
    ]
    current_entities = [
        {"measure_id": measure, "entity_id": f"current-{measure}"}
        if measure != "K05"
        else {"measure_id": measure, "entity_id": "entity-K05"}
        for measure in COMMERCE_MEASURES
    ]
    baseline_provinces = [
        {"measure_id": measure, "entity_id": f"entity-{measure}", "province_code": "10"}
        for measure in COMMERCE_MEASURES
    ]
    current_provinces = [
        {
            "measure_id": measure,
            "entity_id": f"current-{measure}",
            "province_code": "10",
        }
        for measure in COMMERCE_MEASURES
        if measure != "K05"
    ]
    if not remove_k05_province:
        current_provinces.append(
            {"measure_id": "K05", "entity_id": "entity-K05", "province_code": "10"}
        )
    baseline_categories = [
        {
            "measure_id": measure,
            "entity_id": f"entity-{measure}",
            "category_code": "category-a",
        }
        for measure in COMMERCE_MEASURES
    ]
    current_categories = [
        {
            "measure_id": measure,
            "entity_id": f"current-{measure}",
            "category_code": "category-a",
        }
        if measure != "K05"
        else {
            "measure_id": measure,
            "entity_id": "entity-K05",
            "category_code": "category-a",
        }
        for measure in COMMERCE_MEASURES
    ]
    reference = {
        "kpi_results.csv": [
            {"measure_id": measure, "value": str(index)}
            for index, measure in enumerate(COMMERCE_MEASURES)
        ],
        "companion_results.csv": [{"measure_id": "unused", "value": "0"}],
        "entity_contributions.csv": baseline_entities,
        "province_memberships.csv": baseline_provinces,
        "category_memberships.csv": baseline_categories,
        "support/derived/cross-source/innovations-v1/innovation_crosswalk.csv": [
            {
                "global_innovation_id": "innovation-a",
                "source": "synthetic",
                "local_innovation_id": "innovation-source-a",
            }
        ],
        "support/derived/cross-source/people-v1/person_crosswalk.csv": [
            {
                "global_person_id": "person-a",
                "source": "synthetic",
                "source_local_id": "person-source-a",
            }
        ],
        "support/derived/cross-source/activities-coverage-v1/coverage_assertions.csv": [
            {
                "source": "icommunity-v1",
                "source_table": "activities",
                "source_row_id": "coverage-a",
                "raw_locator": "data/icommunity/activities.json#data/0",
                "province_code": "10",
                "location_role": "operator",
                "disposition": "qualifying_resolved",
            }
        ],
    }
    reference.update(
        {
            f"support/derived/cross-source/offerings-v2/{name}.csv": rows
            for name, rows in _commerce_tables().items()
        }
    )
    current = {
        "entity_contributions": current_entities,
        "province_memberships": current_provinces,
        "category_memberships": current_categories,
        "domains/innovations/innovation_crosswalk": [
            {
                "global_innovation_id": "innovation-a",
                "source": "synthetic",
                "local_innovation_id": "innovation-source-a",
            }
        ],
        "domains/people/person_crosswalk": [
            {
                "global_person_id": "person-a",
                "source": "synthetic",
                "source_local_id": "person-source-a",
            }
        ],
        "domains/programme_coverage/coverage_assertions": [
            {
                **row,
                "raw_locator": "evidence://f2_icommunity/run/activities.json#/data/0",
            }
            for row in reference[
                "support/derived/cross-source/activities-coverage-v1/coverage_assertions.csv"
            ]
        ],
    }
    current.update(
        {
            f"domains/commerce/{name}": rows
            for name, rows in _commerce_tables(
                membership_role=membership_role, offering_global=offering_global
            ).items()
        }
    )
    return reference, current


def _write_release(root, tables, *, profile="phase5", complete=False):
    catalog = []
    for name, rows in tables.items():
        write_csv(root / f"{name}.csv", rows)
        catalog.append({"table": name, "path": f"{name}.csv", "row_count": len(rows)})
    write_csv(root / "table_catalog.csv", catalog)
    write_json(
        root / "results.json",
        {
            measure: {"value": index + 100}
            for index, measure in enumerate(COMMERCE_MEASURES)
        },
    )
    files = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": digest(path),
            "size": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]
    write_json(
        root / "manifest.json",
        {
            "schema_version": 1,
            "release_id": "synthetic-phase5",
            "profile": profile,
            "complete": complete,
            "publication_status": "complete" if complete else "development_only",
            "validation_status": "passed",
            "enabled_measures": list(reversed(COMMERCE_MEASURES)),
            "files": files,
        },
    )
    return root


def _compare(current, reference):
    manifest = verify_release(current)
    reference_manifest, baseline = _baseline_reader(reference)
    return compare_commerce_content(
        manifest,
        reference_manifest,
        baseline,
        load_release_tables(current),
        load_json(current / "results.json"),
    )


def _releases(tmp_path, **changes):
    reference_tables, current_tables = _fixture_tables(**changes)
    reference = _write_frozen(tmp_path / "frozen-v2", reference_tables)
    current = _write_release(tmp_path / "phase5", current_tables)
    return current, reference


def test_compare_commerce_reports_measures_and_k05_geography_correction(
    tmp_path,
):
    current, reference = _releases(tmp_path, remove_k05_province=True)

    result = _compare(current, reference)

    assert result["profile_measures"] == list(COMMERCE_MEASURES)
    assert set(result["measures"]) == set(COMMERCE_MEASURES)
    for index, measure in enumerate(COMMERCE_MEASURES):
        comparison = result["measures"][measure]
        assert comparison["reference_value"] == index
        assert comparison["current_value"] == index + 100
        if measure == "K05":
            assert (
                comparison["entities"]["added"]
                == comparison["entities"]["removed"]
                == 0
            )
            assert comparison["province_pairs"]["removed_keys"] == [
                ("entity-K05", "10")
            ]
        else:
            assert comparison["entities"]["added_keys"] == [(f"current-{measure}",)]
            assert comparison["entities"]["removed_keys"] == [(f"entity-{measure}",)]
    assert result["measures"]["K07"]["category_pairs"]["added_keys"] == [
        ("current-K07", "category-a")
    ]
    assert result["commerce"]["operator_offering_relationships"]["added"] == 0
    assert result["commerce"]["reviewed_relationships"]["removed"] == 0
    assert result["programme_coverage"]["assertion_memberships"]["added"] == 0
    assert result["programme_coverage"]["source_province_memberships"]["removed"] == 0
    assert result["programme_coverage"]["source_citation_assertions"]["added"] == 0
    assert result["programme_coverage"]["source_citation_assertions"]["removed"] == 0


def test_compare_commerce_detects_k07_range_evidence_role_change_without_family_count_change(
    tmp_path,
):
    current, reference = _releases(tmp_path, membership_role="range_evidence")

    result = _compare(current, reference)

    assert result["commerce"]["family_definitions"]["added"] == 0
    assert result["commerce"]["family_definitions"]["removed"] == 0
    memberships = result["commerce"]["family_memberships"]
    assert memberships["removed_keys"] == [("family-a", "offering-extra", "variant")]
    assert memberships["added_keys"] == [
        ("family-a", "offering-extra", "range_evidence")
    ]


def test_compare_commerce_detects_offering_crosswalk_change_without_member_grouping_change(
    tmp_path,
):
    current, reference = _releases(tmp_path, offering_global="offering-b")

    result = _compare(current, reference)

    offerings = result["identities"]["offerings"]
    assert offerings["grouping"]["added"] == offerings["grouping"]["removed"] == 0
    assert offerings["member_keys"]["added"] == offerings["member_keys"]["removed"] == 0
    assert offerings["source_to_global"]["removed_keys"] == [
        ("offering-source-a", "offering-a")
    ]
    assert offerings["source_to_global"]["added_keys"] == [
        ("offering-source-a", "offering-b")
    ]


@pytest.mark.parametrize(
    "path",
    [
        "support/derived/cross-source/offerings-v2/offering_families.csv",
        "support/derived/cross-source/activities-coverage-v1/coverage_assertions.csv",
    ],
)
def test_compare_commerce_rejects_tampered_manifest_backed_frozen_inputs(tmp_path, path):
    current, reference = _releases(tmp_path)
    (reference / path).write_text("tampered\n")

    with pytest.raises(PipelineError, match="hash mismatch"):
        _compare(current, reference)


def test_compare_commerce_rejects_missing_required_table(tmp_path):
    reference_tables, current_tables = _fixture_tables()
    reference = _write_frozen(tmp_path / "frozen-v2", reference_tables)
    missing_table = _write_release(
        tmp_path / "missing-table",
        {
            name: rows
            for name, rows in current_tables.items()
            if name != "domains/commerce/locations"
        },
    )

    with pytest.raises(PipelineError, match="missing implemented domain tables"):
        _compare(missing_table, reference)


def test_compare_preserves_split_innovations_when_correcting_reviewed_citation_context(
    tmp_path,
):
    reference_tables, current_tables = _fixture_tables()
    second_innovation = {
        "global_innovation_id": "innovation-b",
        "source": "synthetic",
        "local_innovation_id": "innovation-source-b",
    }
    reference_tables[
        "support/derived/cross-source/innovations-v1/innovation_crosswalk.csv"
    ].append(second_innovation)
    current_tables["domains/innovations/innovation_crosswalk"].append(second_innovation)
    current_tables["domains/commerce/reviewed_evidence"].append(
        {
            "candidate_id": "candidate-a",
            "source": "synthetic",
            "global_innovation_id": "innovation-b",
        }
    )
    reference = _write_frozen(tmp_path / "frozen-v2", reference_tables)
    current = _write_release(tmp_path / "phase5", current_tables)
    result = _compare(current, reference)
    contexts = result["commerce"]["reviewed_candidate_innovation_contexts"]
    assert contexts["added_keys"] == [("candidate-a", "synthetic", "innovation-b")]
    assert contexts["removed"] == 0
    assert result["identities"]["innovations"]["grouping"]["added"] == 0
    assert result["identities"]["innovations"]["grouping"]["removed"] == 0
    assert result["commerce"]["family_memberships"]["added"] == 0


def test_incomplete_historical_release_cannot_enter_public_projection(tmp_path):
    from tools.f2_pipeline.public_projection import build_public_projection

    current, _ = _releases(tmp_path)
    output = tmp_path / "not-published"
    with pytest.raises(PipelineError, match="Incomplete"):
        build_public_projection(current, output)
    assert not output.exists()


def test_coverage_comparison_preserves_occurrence_counts_when_ids_are_regenerated(
    tmp_path,
):
    reference_tables, current_tables = _fixture_tables()
    path = "support/derived/cross-source/activities-coverage-v1/coverage_assertions.csv"
    reference_tables[path].append(
        {**reference_tables[path][0], "source_row_id": "another-old-assertion"}
    )
    current_tables["domains/programme_coverage/coverage_assertions"][0][
        "source_row_id"
    ] = "new-assertion"
    reference = _write_frozen(tmp_path / "frozen-v2", reference_tables)
    current = _write_release(tmp_path / "phase5", current_tables)
    compared = _compare(current, reference)["programme_coverage"]
    assert compared["assertion_memberships"]["added"] == 1
    assert compared["source_citation_assertions"]["added"] == 0
    assert compared["source_citation_assertions"]["removed"] == 1
