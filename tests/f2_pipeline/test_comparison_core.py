import json
import pytest
from tools.f2_pipeline.common import PipelineError, digest
from tools.f2_pipeline.comparison_core import (
    ENTITY_MEASURES,
    _baseline_reader,
    _compare_identity,
    _compare_measure_tables,
    _groups,
    _set_delta,
    _source_local_member,
)


def frozen(tmp_path, files):
    root = tmp_path / "v2"
    root.mkdir()
    manifest = {"release_id": "f2-dashboard-snapshot-v2", "files": {}}
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        manifest["files"][name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root


def test_delta_reports_only_filtered_member_keys():
    result = _set_delta({("K04", "old")}, {("K04", "new")})
    assert result["added_keys"] == [("K04", "new")]
    assert result["removed_keys"] == [("K04", "old")]


def test_baseline_reader_rejects_unlisted_or_tampered_files(tmp_path):
    root = frozen(tmp_path, {"kpi_results.csv": "measure_id,value\nK04,1\n"})
    _, read = _baseline_reader(root)
    with pytest.raises(PipelineError):
        read("missing.csv")
    (root / "kpi_results.csv").write_text("changed")
    with pytest.raises(PipelineError):
        read("kpi_results.csv")


def test_people_members_are_source_and_local_id_not_source_only():
    rows = [
        {"global_person_id": "merged", "source": "one", "source_local_id": "a"},
        {"global_person_id": "merged", "source": "one", "source_local_id": "b"},
    ]
    assert set(_groups(rows, "global_person_id", _source_local_member)) == {
        ("one:a", "one:b")
    }
    split = [{**row, "global_person_id": row["source_local_id"]} for row in rows]
    assert set(_groups(split, "global_person_id", _source_local_member)) == {
        ("one:a",),
        ("one:b",),
    }
    with pytest.raises(PipelineError, match="repeated ownership"):
        _groups(split + [rows[0]], "global_person_id", _source_local_member)


def test_public_compare_filters_each_measure_independently(tmp_path):
    values = {
        measure: int(measure in {"K04", "C04_LISTED", "K12"})
        for measure in ENTITY_MEASURES
    }
    reference = frozen(
        tmp_path,
        {
            "kpi_results.csv": "measure_id,value\n"
            + "".join(f"{key},{value}\n" for key, value in values.items()),
            "companion_results.csv": "measure_id,value\n",
            "entity_contributions.csv": "measure_id,entity_id\nK04,old\nC04_LISTED,old\nK12,unchanged\n",
            "province_memberships.csv": "measure_id,entity_id,province_code\nK04,old,10\nK12,unchanged,20\n",
            "category_memberships.csv": "measure_id,entity_id,category_code\nK12,unchanged,CS\n",
            "support/derived/cross-source/innovations-v1/innovation_crosswalk.csv": "global_innovation_id,source,local_innovation_id\nold,synthetic,innovation-one\n",
            "support/derived/cross-source/people-v1/person_crosswalk.csv": "global_person_id,source,source_local_id\nold-person,synthetic,person-one\n",
        },
    )
    tables = {
        "entity_contributions": [
            {"measure_id": "K04", "entity_id": "new"},
            {"measure_id": "C04_LISTED", "entity_id": "new"},
            {"measure_id": "K12", "entity_id": "unchanged"},
        ],
        "province_memberships": [
            {"measure_id": "K04", "entity_id": "new", "province_code": "10"},
            {"measure_id": "K12", "entity_id": "unchanged", "province_code": "20"},
        ],
        "category_memberships": [
            {"measure_id": "K12", "entity_id": "unchanged", "category_code": "CS"}
        ],
        "domains/innovations/innovation_crosswalk": [
            {
                "global_innovation_id": "new",
                "source": "synthetic",
                "local_innovation_id": "innovation-one",
            },
        ],
        "domains/people/person_crosswalk": [
            {
                "global_person_id": "new-person",
                "source": "synthetic",
                "source_local_id": "person-one",
            },
        ],
    }
    _, baseline = _baseline_reader(reference)
    result = {
        "measures": _compare_measure_tables(
            baseline,
            tables,
            {key: {"value": value} for key, value in values.items()},
            ENTITY_MEASURES,
        ),
        "identities": {
            kind: _compare_identity(baseline, tables, kind)
            for kind in ("innovations", "people")
        },
    }
    assert result["measures"]["K04"]["entities"]["added_keys"] == [("new",)]
    assert result["measures"]["K04"]["entities"]["removed_keys"] == [("old",)]
    assert result["measures"]["K04"]["province_pairs"]["added_keys"] == [("new", "10")]
    assert result["measures"]["K12"]["entities"]["added"] == 0
    assert result["measures"]["K12"]["province_pairs"]["removed"] == 0
    assert result["measures"]["K12"]["category_pairs"]["added"] == 0
    assert result["measures"]["C02_COMMUNITY"]["entities"]["current_distinct"] == 0
    for identity in result["identities"].values():
        assert identity["grouping"]["added"] == identity["grouping"]["removed"] == 0
        assert (
            identity["member_keys"]["added"] == identity["member_keys"]["removed"] == 0
        )
