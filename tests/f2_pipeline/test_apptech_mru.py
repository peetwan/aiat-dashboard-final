from collections import defaultdict

import pytest
from tools.f2_pipeline.sources.apptech_mru import (
    AppTechMRUPilot,
    DATASET_KEYS,
    TABLE_COLUMNS,
    build_tables,
    validate_tables,
)


def test_mru_requires_complete_capture_bundle_before_reading_reviews():
    with pytest.raises(
        ValueError, match="datasets must be innovations and requirements"
    ):
        build_tables({}, {}, None, {})


def test_mru_preserves_legacy_table_contract_exports():
    assert DATASET_KEYS == ("innovations", "requirements")
    assert {
        "innovations",
        "people",
        "requirements",
        "role_assertions",
        "review_coverage",
    } <= set(TABLE_COLUMNS)


def _row(table, **values):
    row = dict.fromkeys(TABLE_COLUMNS[table])
    row.update(values)
    return row


def _requirement_tables():
    return {
        "requirements": [
            _row(
                "requirements",
                requirement_id="requirement-1",
                observation_id="requirement-observation-1",
                source_id="1",
            )
        ],
        "requirement_expertise": [],
        "requirement_impacts": [],
        "requirement_tags": [],
    }


def test_mru_requirement_role_does_not_inherit_same_numeric_innovation_id():
    pilot = AppTechMRUPilot.__new__(AppTechMRUPilot)
    pilot.config = {"non_person_subjects": {}}
    pilot.tables = defaultdict(list)
    pilot.innovation_ids = {"1": "innovation-1"}

    for record_type in ("requirement", "innovation"):
        pilot.add_role(
            record_type=record_type,
            source_id="1",
            observation_id=f"{record_type}-observation-1",
            role="listing_account_owner",
            role_index=0,
            name="",
            source_locator="synthetic://role",
            placeholder_flag=True,
        )

    requirement_role, innovation_role = pilot.tables["role_assertions"]
    assert requirement_role["requirement_id"]
    assert requirement_role["innovation_id"] == ""
    assert innovation_role["requirement_id"] == ""
    assert innovation_role["innovation_id"] == "innovation-1"


def test_mru_requirement_tables_accept_complete_owned_children_and_nullable_fields():
    tables = _requirement_tables()
    tables["requirement_expertise"].append(
        _row(
            "requirement_expertise",
            expertise_id="expertise-1",
            requirement_id="requirement-1",
            observation_id="requirement-observation-1",
            source_id="1",
        )
    )
    tables["requirement_impacts"].append(
        _row(
            "requirement_impacts",
            impact_id="impact-1",
            requirement_id="requirement-1",
            observation_id="requirement-observation-1",
            source_id="1",
        )
    )
    tables["requirement_tags"].append(
        _row(
            "requirement_tags",
            tag_id="tag-1",
            requirement_id="requirement-1",
            observation_id="requirement-observation-1",
            source_id="1",
        )
    )

    validate_tables(tables)


def test_mru_requirement_tables_reject_duplicate_requirement_identity():
    tables = _requirement_tables()
    tables["requirements"].append(tables["requirements"][0].copy())

    with pytest.raises(ValueError, match="duplicate requirement_id"):
        validate_tables(tables)


def test_mru_requirement_tables_reject_orphan_child():
    tables = _requirement_tables()
    tables["requirement_expertise"].append(
        _row(
            "requirement_expertise",
            expertise_id="expertise-1",
            requirement_id="missing-requirement",
            observation_id="requirement-observation-1",
            source_id="1",
        )
    )

    with pytest.raises(ValueError, match="references missing requirement_id"):
        validate_tables(tables)


@pytest.mark.parametrize(
    ("field", "value"),
    (("observation_id", "other-observation"), ("source_id", "other-source")),
)
def test_mru_requirement_tables_reject_mismatched_child_ownership(field, value):
    tables = _requirement_tables()
    child = _row(
        "requirement_impacts",
        impact_id="impact-1",
        requirement_id="requirement-1",
        observation_id="requirement-observation-1",
        source_id="1",
    )
    child[field] = value
    tables["requirement_impacts"].append(child)

    with pytest.raises(ValueError, match=f"{field} does not belong"):
        validate_tables(tables)


def test_mru_requirement_tables_reject_duplicate_child_identity():
    tables = _requirement_tables()
    child = _row(
        "requirement_tags",
        tag_id="tag-1",
        requirement_id="requirement-1",
        observation_id="requirement-observation-1",
        source_id="1",
    )
    tables["requirement_tags"].extend((child, child.copy()))

    with pytest.raises(ValueError, match="duplicate tag_id"):
        validate_tables(tables)


@pytest.mark.parametrize(
    ("table", "identity_field"),
    (
        ("requirement_expertise", "expertise_id"),
        ("requirement_impacts", "impact_id"),
        ("requirement_tags", "tag_id"),
    ),
)
def test_mru_requirement_tables_reject_missing_child_identity(table, identity_field):
    tables = _requirement_tables()
    tables[table].append(
        _row(
            table,
            **{
                identity_field: "",
                "requirement_id": "requirement-1",
                "observation_id": "requirement-observation-1",
                "source_id": "1",
            },
        )
    )

    with pytest.raises(ValueError, match=f"missing {identity_field}"):
        validate_tables(tables)


def test_mru_requirement_tables_reject_missing_child_relationship():
    tables = _requirement_tables()
    tables["requirement_tags"].append(
        _row(
            "requirement_tags",
            tag_id="tag-1",
            requirement_id="",
            observation_id="requirement-observation-1",
            source_id="1",
        )
    )

    with pytest.raises(ValueError, match="references missing requirement_id"):
        validate_tables(tables)
