import hashlib
import json
from pathlib import Path

import pytest

from tools.f2_pipeline import full_projection as projection
from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.measure_query import MeasureQuery



def test_c02_can_filter_by_province_without_enabling_a_person_map():
    definition = {
        "measure_id": "C02_COMMUNITY",
        "supported_filters": ["province"],
        "permitted_filter_combinations": [[], ["province"]],
        "map_availability": "unavailable",
    }

    assert projection._public_filter_contract(definition) == {
        "supported_filters": ["province"],
        "permitted_combinations": [[], ["province"]],
    }
    assert projection._map_availability(definition) == "unavailable"


def test_invalid_explicit_map_availability_fails_closed():
    with pytest.raises(PipelineError, match="Invalid map availability"):
        projection._map_availability(
            {"measure_id": "C02_COMMUNITY", "map_availability": "person"}
        )

class _PersonQuery:
    kind = "entity"

    def select(self, filters):
        return {
            "result": {
                "value": None,
                "display_value": "",
                "unit": "person",
                "status": "source_aggregate",
                "availability": "unavailable",
                "scope_key": "province/10",
                "requested_filters": filters,
                "applied_filters": {},
                "unavailable_reason": {"code": "unsupported_filter"},
            },
            "entity_ids": ["private-person-1"],
            "coverage": {},
        }


def test_person_scope_preserves_unavailable_result_without_directory_ids():
    scope = projection._scope(
        _PersonQuery(),
        {"province": ["10"]},
        {"private-person-1": {}},
        2,
        "C02_COMMUNITY",
    )
    assert scope["results"]["C02_COMMUNITY"]["value"] is None
    assert scope["coverage"] == {"C02_COMMUNITY": {}}
    assert scope["sections"] == [
        {
            "section_id": "c02_community",
            "title_th": "ประชากรนวัตกรชุมชนที่เกี่ยวข้อง",
            "kind": "related_population",
            "measure_ids": ["C02_COMMUNITY"],
            "scope_key": "province/10",
            "counted_total": None,
            "reconciles_with_headline": False,
            "detail_availability": "not_applicable",
            "unavailable_reason": {"code": "unsupported_filter"},
        }
    ]
    assert "private-person-1" not in json.dumps(scope)


def test_detail_chunks_are_atomic_complete_bounded_and_deterministic():
    details = {
        "a": {"entity_id": "a", "label": "A" * 100, "source_ids": ["source-a"]},
        "b": {"entity_id": "b", "label": "B" * 100, "source_ids": ["source-b"]},
        "c": {
            "entity_id": "c",
            "label": "C" * 100,
            "source_ids": ["source-a", "source-c"],
        },
    }
    topic = {
        "topic_id": "k12",
        "items_by_id": {entity_id: {} for entity_id in details},
        "details_by_id": details.copy(),
    }
    children = projection._detail_chunks(topic, details, {"release_id": "r"}, 300, 300)
    assert topic["details_by_id"] == {}
    assert sorted(topic["detail_artifacts"]) == ["a", "b", "c"]
    assert sorted(
        entity_id for child in children.values() for entity_id in child["details_by_id"]
    ) == ["a", "b", "c"]
    assert list(children) == [
        "details/k12-000.json",
        "details/k12-001.json",
        "details/k12-002.json",
    ]
    assert all(projection._encoded_size(child) <= 300 for child in children.values())
    assert topic["detail_artifacts"]["a"] == "f2/topic/k12/detail/000"
    assert children["details/k12-000.json"]["source_ids"] == ["source-a"]
    assert children["details/k12-001.json"]["source_ids"] == ["source-b"]
    assert children["details/k12-002.json"]["source_ids"] == ["source-a", "source-c"]


def test_aggregate_projection_uses_stable_public_members_and_exact_decimals():
    policy = {
        "sources": {
            "learning_dashboard": {
                "source_id": "f2_learning_dashboard",
                "originating_system": "Learning dashboard",
            }
        }
    }
    source_regions = {
        "source_region_a": {
            "label_th": "ภาคต้นทาง",
            "source_region_id": "source_region_a",
        }
    }
    projected = projection._safe_breakdowns(
        [
            {
                "measure_id": "K10",
                "breakdown_id": "components",
                "member_id": "private-source-member-key",
                "member_label": "ค่าจ้าง",
                "amount": "1.2500",
                "amount_unit": "million_THB_per_month",
                "result_divisor": "1.00",
                "evidence_id": "private",
                "raw_locator": "private",
                "evidence_table": "sources/f2_learning_dashboard/impact_components",
                "component": "localEmployeeExpense",
                "region": "ภาคต้นทาง",
            }
        ],
        policy,
        source_regions,
    )
    assert projected == [
        {
            "item_id": projection.stable_id(
                "aggregate_member",
                "K10",
                "components",
                "private-source-member-key",
                "f2_learning_dashboard",
            ),
            "label": "ค่าจ้าง",
            "amount": "1.2500",
            "amount_unit": "million_THB_per_month",
            "result_divisor": "1.00",
            "breakdown_id": "components",
            "component": "localEmployeeExpense",
            "source_region_id": "source_region_a",
            "source_region_label_th": "ภาคต้นทาง",
            "source_id": "f2_learning_dashboard",
        }
    ]
    assert "private-source-member-key" not in json.dumps(projected)
    assert "locator" not in json.dumps(projected)


_SOURCE_IDS = [
    "f2_apptech_mru",
    "f2_apptech_mtr",
    "f2_cultural_market_civil",
    "f2_culturalmap_university",
    "f2_icommunity",
    "f2_learning_area_based",
    "f2_learning_dashboard",
    "f2_target_household",
]
_SOURCE_ALIASES = {
    "apptech_mru": "f2_apptech_mru",
    "rinmp": "f2_apptech_mtr",
    "atlocal": "f2_cultural_market_civil",
    "cultural_map": "f2_culturalmap_university",
    "icommunity": "f2_icommunity",
    "learning_area_based": "f2_learning_area_based",
    "learning_dashboard": "f2_learning_dashboard",
    "pmua_apptech": "f2_target_household",
}
_MEASURE_SPECS = [
    (
        "K01A",
        "k01a",
        "headline",
        None,
        "province",
        "available_snapshot",
        ["province"],
        [[], ["province"]],
    ),
    (
        "K01B",
        "k01b",
        "headline",
        None,
        "area",
        "available_snapshot",
        ["province"],
        [[], ["province"]],
    ),
    (
        "K02",
        "k02",
        "headline",
        None,
        "person",
        "source_aggregate",
        ["province", "source_level"],
        [[], ["province"], ["source_level"], ["province", "source_level"]],
    ),
    (
        "K03",
        "k03",
        "headline",
        None,
        "activity",
        "substitute_measure",
        ["province"],
        [[], ["province"]],
    ),
    (
        "K04",
        "k04",
        "headline",
        None,
        "innovation",
        "available_snapshot",
        ["province"],
        [[], ["province"]],
    ),
    (
        "K05",
        "k05",
        "headline",
        None,
        "operator",
        "partial_coverage",
        ["province"],
        [[], ["province"]],
    ),
    ("K06", "k06", "headline", None, "person", "deferred", [], [[]]),
    (
        "K07",
        "k07",
        "headline",
        None,
        "offering_family",
        "substitute_partial_coverage",
        ["province"],
        [[], ["province"]],
    ),
    ("K08", "k08", "headline", None, "business", "deferred", [], [[]]),
    (
        "K09",
        "k09",
        "headline",
        None,
        "person_per_month",
        "source_aggregate",
        ["region"],
        [[], ["region"]],
    ),
    (
        "K10",
        "k10",
        "headline",
        None,
        "million_THB_per_month",
        "assumed_aggregate",
        ["region", "component"],
        [[], ["region"], ["component"], ["region", "component"]],
    ),
    ("K11A", "k11a", "headline", None, "THB", "deferred", [], [[]]),
    ("K11B", "k11b", "headline", None, "THB", "deferred", [], [[]]),
    (
        "K12",
        "k12",
        "headline",
        None,
        "record",
        "available_snapshot",
        ["province", "category"],
        [[], ["province"], ["category"], ["province", "category"]],
    ),
    (
        "C02_COMMUNITY",
        "k02",
        "companion",
        "K02",
        "person",
        "partial_coverage",
        [],
        [[]],
    ),
    (
        "C04_LISTED",
        "k04",
        "companion",
        "K04",
        "innovation",
        "available_snapshot",
        ["province"],
        [[], ["province"]],
    ),
    (
        "C08_PARTICIPATING",
        "k08",
        "companion",
        "K08",
        "business",
        "partial_coverage",
        ["province"],
        [[], ["province"]],
    ),
    (
        "C08_REPORTED_BUSINESSES",
        "k08",
        "companion",
        "K08",
        "business",
        "source_aggregate",
        ["source_dimension"],
        [[], ["source_dimension"]],
    ),
    (
        "C08_ASSESSED_PEOPLE",
        "k08",
        "companion",
        "K08",
        "person",
        "partial_coverage",
        [],
        [[]],
    ),
    (
        "C08_INCREASED_PEOPLE",
        "k08",
        "companion",
        "K08",
        "person",
        "partial_coverage",
        [],
        [[]],
    ),
    (
        "C10_ALTERNATIVE",
        "k10",
        "companion",
        "K10",
        "million_THB_per_month",
        "source_aggregate",
        ["region", "component"],
        [[], ["region"], ["component"], ["region", "component"]],
    ),
]


def _definitions():
    return [
        {
            "measure_id": measure_id,
            "topic_id": topic_id,
            "kind": kind,
            "parent_measure_id": parent,
            "label_th": f"ชื่อ {measure_id}",
            "unit": unit,
            "status": status,
            "formula": f"สูตร {measure_id}",
            "scope": f"ขอบเขต {measure_id}",
            "limitations": f"ข้อจำกัด {measure_id}",
            "display_order": index,
            "supported_filters": filters,
            "permitted_filter_combinations": combinations,
        }
        for index, (
            measure_id,
            topic_id,
            kind,
            parent,
            unit,
            status,
            filters,
            combinations,
        ) in enumerate(_MEASURE_SPECS, 1)
    ]


def _aggregate_row(
    measure_id,
    member_id,
    amount,
    *,
    breakdown_id="components",
    province_code="",
    province_name="",
    source_level="",
    region="",
    component="",
):
    source_id = (
        "f2_target_household" if measure_id == "K02" else "f2_learning_dashboard"
    )
    return {
        "measure_id": measure_id,
        "breakdown_id": breakdown_id,
        "member_id": member_id,
        "member_label": province_name or region or component or source_level,
        "amount": amount,
        "amount_unit": "person"
        if measure_id in {"K02", "K09"}
        else "million_THB_per_month",
        "result_divisor": "1",
        "province_code": province_code,
        "province_name": province_name,
        "source_level": source_level,
        "region": region,
        "component": component,
        "evidence_table": f"sources/{source_id}/aggregate_components",
        "evidence_key": "component_id",
        "evidence_id": f"evidence-{measure_id}-{member_id}",
        "raw_locator": f"evidence://{source_id}/private/{member_id}",
    }


def _synthetic_tables():
    provinces = [
        {
            "province_code": f"{index:02d}",
            "province_name_th": f"จังหวัด {index:02d}",
            "province_name_en": f"Province {index:02d}",
            "region_id": "dashboard_region_a" if index <= 39 else "dashboard_region_b",
            "region": "ภูมิภาคแดชบอร์ด ก" if index <= 39 else "ภูมิภาคแดชบอร์ด ข",
        }
        for index in range(1, 78)
    ]
    entity_ids = {
        "K01A": [row["province_code"] for row in provinces],
        "K01B": ["area-public"],
        "K03": ["activity-public"],
        "K04": ["innovation-shared"],
        "K05": ["operator-public"],
        "K07": ["family-public"],
        "K12": ["mapped-public", "mapped-private"],
        "C02_COMMUNITY": ["person-community-private", "person-inventor-private"],
        "C04_LISTED": ["innovation-shared", "innovation-listed-only"],
        "C08_PARTICIPATING": ["business-public"],
        "C08_ASSESSED_PEOPLE": ["person-assessed-private"],
        "C08_INCREASED_PEOPLE": ["person-increased-private"],
    }
    contributions = [
        {"measure_id": measure_id, "entity_id": entity_id, "label": entity_id}
        for measure_id, values in entity_ids.items()
        for entity_id in values
    ]
    memberships = [
        {
            "measure_id": "K01A",
            "entity_id": row["province_code"],
            "province_code": row["province_code"],
            "evidence_table": "domains/programme_coverage/province_evidence_index",
            "evidence_id": row["province_code"],
            "evidence_key": "province_code",
            "location_role": "programme_coverage",
        }
        for row in provinces
    ]
    for measure_id, values in entity_ids.items():
        if measure_id != "K01A":
            memberships.extend(
                {
                    "measure_id": measure_id,
                    "entity_id": entity_id,
                    "province_code": (
                        "40"
                        if measure_id == "C04_LISTED"
                        and entity_id == "innovation-listed-only"
                        else "01"
                    ),
                    "evidence_table": "sources/f2_culturalmap_university/locations",
                    "evidence_id": f"location-{measure_id}-{entity_id}",
                    "evidence_key": "location_id",
                    "location_role": "supported_item_location",
                }
                for entity_id in values
            )
    category_memberships = [
        {
            "measure_id": "K12",
            "entity_id": "mapped-public",
            "category_code": "A",
            "category_name_th": "หมวด ก",
            "category_kind": "primary",
            "evidence_table": "sources/f2_culturalmap_university/category_assertions",
            "evidence_id": "category-public-a",
            "evidence_key": "category_assertion_id",
        },
        {
            "measure_id": "K12",
            "entity_id": "mapped-public",
            "category_code": "B",
            "category_name_th": "หมวด ข",
            "category_kind": "additional",
            "evidence_table": "sources/f2_culturalmap_university/category_assertions",
            "evidence_id": "category-public-b",
            "evidence_key": "category_assertion_id",
        },
        {
            "measure_id": "K12",
            "entity_id": "mapped-private",
            "category_code": "A",
            "category_name_th": "หมวด ก",
            "category_kind": "primary",
            "evidence_table": "sources/f2_culturalmap_university/category_assertions",
            "evidence_id": "category-private-a",
            "evidence_key": "category_assertion_id",
        },
    ]
    aggregate_breakdowns = [
        _aggregate_row(
            "K02",
            "01:1",
            "2",
            breakdown_id="province_level",
            province_code="01",
            province_name="จังหวัด 01",
            source_level="1",
        ),
        _aggregate_row(
            "K02",
            "01:2",
            "3",
            breakdown_id="province_level",
            province_code="01",
            province_name="จังหวัด 01",
            source_level="2",
        ),
        _aggregate_row(
            "K09",
            "region-a-employment",
            "10",
            region="ภูมิภาคต้นทาง ก",
            component="localEmployeeAmount",
        ),
        _aggregate_row(
            "K09",
            "region-b-employment",
            "20",
            region="ภูมิภาคต้นทาง ข",
            component="localEmployeeAmount",
        ),
        _aggregate_row(
            "K10",
            "region-a-wage",
            "1.25",
            region="ภูมิภาคต้นทาง ก",
            component="localEmployeeExpense",
        ),
        _aggregate_row(
            "K10",
            "region-a-resource",
            "2.25",
            region="ภูมิภาคต้นทาง ก",
            component="localResourceExpense",
        ),
        _aggregate_row(
            "K10",
            "region-b-wage",
            "3",
            region="ภูมิภาคต้นทาง ข",
            component="localEmployeeExpense",
        ),
        _aggregate_row(
            "K10",
            "region-b-resource",
            "4",
            region="ภูมิภาคต้นทาง ข",
            component="localResourceExpense",
        ),
        _aggregate_row(
            "C10_ALTERNATIVE",
            "region-a-included",
            "1",
            region="ภูมิภาคต้นทาง ก",
            component="localResourceExpense",
        ),
        _aggregate_row(
            "C10_ALTERNATIVE",
            "region-a-excluded",
            "0.5",
            region="ภูมิภาคต้นทาง ก",
            component="excludedResourceExpense",
        ),
        _aggregate_row(
            "C10_ALTERNATIVE",
            "region-b-included",
            "2",
            region="ภูมิภาคต้นทาง ข",
            component="localResourceExpense",
        ),
        _aggregate_row(
            "C10_ALTERNATIVE",
            "region-b-excluded",
            "0.75",
            region="ภูมิภาคต้นทาง ข",
            component="excludedResourceExpense",
        ),
    ]
    for dimension in ("categories", "entityTypes", "geography", "provinces"):
        aggregate_breakdowns.append(
            _aggregate_row(
                "C08_REPORTED_BUSINESSES",
                f"dimension-{dimension}",
                "4",
                breakdown_id=dimension,
            )
            | {"member_label": f"สมาชิก {dimension}", "amount_unit": "business"}
        )
    evidence = []
    measure_ids = [row[0] for row in _MEASURE_SPECS]
    for index, measure_id in enumerate(measure_ids):
        if measure_id not in entity_ids:
            continue
        source_id = _SOURCE_IDS[index % len(_SOURCE_IDS)]
        evidence.append(
            {
                "measure_id": measure_id,
                "entity_id": entity_ids.get(measure_id, [f"aggregate-{measure_id}"])[0],
                "evidence_table": f"sources/{source_id}/measure_evidence",
                "evidence_id": f"evidence-{measure_id}",
                "evidence_key": "evidence_id",
                "evidence_role": "counted_identity",
            }
        )
    assertions = []
    for index, alias in enumerate(
        (
            "atlocal",
            "cultural_map",
            "icommunity",
            "learning_area_based",
            "learning_dashboard",
            "pmua_apptech",
            "rinmp",
        ),
        1,
    ):
        assertions.append(
            {
                "province_code": "01" if index < 5 else "02",
                "province_name": "จังหวัด 01" if index < 5 else "จังหวัด 02",
                "source": alias.replace("_", "-") + "-v1",
                "location_role": "declared_programme_location",
                "disposition": "qualifying_resolved",
                "evidence_kind": "record_derived",
                "lineage_status": "resolved",
                "reason": "กฎความครอบคลุมที่ผ่านการทบทวน",
                "raw_locator": f"evidence://{_SOURCE_ALIASES[alias]}/private",
                "observation_id": f"private-observation-{index}",
            }
        )
    return {
        "provinces": provinces,
        "entity_contributions": contributions,
        "province_memberships": memberships,
        "category_memberships": category_memberships,
        "aggregate_breakdowns": aggregate_breakdowns,
        "eligibility_evidence": evidence,
        "evidence_links": [],
        "domains/programme_coverage/coverage_assertions": assertions,
    }


def _policy():
    return {
        "schema_version": 1,
        "policy_id": "synthetic-review-policy",
        "publication_status": "staged_for_review",
        "staged_for_review": True,
        "owner_checkpoint_required": True,
        "additional_field_review_status": "pending_owner_acceptance",
        "publication_approval_claimed": False,
        "preview_count": 1,
        "max_overview_bytes": 500_000,
        "max_geography_bytes": 5_000_000,
        "max_topic_bytes": 1_000_000,
        "max_detail_child_bytes": 2_500_000,
        "max_file_bytes": 5_000_000,
        "limitations": ["ชุดทดสอบสังเคราะห์"],
        "detail_policies": {},
        "excluded_fields": [
            "raw_file",
            "row_locator",
            "raw_locator",
            "source_locator",
            "source_details_json",
            "profile_token",
            "development_scores",
            "development_assessments",
        ],
        "publication_field_contexts": {
            "/details_by_id/*/children/sections/*/attribution": "work_attribution",
            "/details_by_id/*/children/work_attributions/*/attribution": "work_attribution",
            "/details_by_id/*/children/organizations/*/organization": "organization",
            "/details_by_id/*/children/participations/*/research_unit": "organization",
        },
        "detail_field_contexts": {},
        "sources": {
            alias: {
                "source_id": source_id,
                "originating_system": f"ระบบ {alias}",
                "source_context_review": {
                    "status": "reviewed_for_staging",
                    "rationale": "ทบทวนขอบเขตการแสดงผลแล้ว",
                },
            }
            for alias, source_id in _SOURCE_ALIASES.items()
        },
    }


def _detail(entity_id, label, source_id, *, large=False):
    return {
        "entity_id": entity_id,
        "label": label,
        "identity_status": "reviewed",
        "province_codes": ["40"] if entity_id == "innovation-listed-only" else ["01"],
        "category_codes": ["A"] if entity_id.startswith("mapped") else [],
        "source_ids": [source_id],
        "descriptions": [
            {
                "kind": "summary",
                "text": "ข้อมูลสาธารณะที่ผ่านการทบทวน" + ("x" * 1_100_000 if large else ""),
                "is_excerpt": False,
                "was_sanitized": False,
                "source_id": source_id,
            }
        ],
        "listings": [],
        "locations": [],
        "media": [],
        "relationships": [],
        "children": {},
        "flags": {
            "limited_coverage": True,
            "identity_review": {
                "outcome": "source_record_only",
                "merge_scope": None,
                "counting": "separate",
                "name_quality": "supported",
            },
        },
        "originating_systems": ["ระบบทดสอบ"],
        "detail_availability": "staged_for_review",
    }


def _details():
    shared = _detail("innovation-shared", "นวัตกรรมร่วม", "f2_target_household")
    listed_only = _detail("innovation-listed-only", "นวัตกรรมในบัญชี", "f2_apptech_mru")
    return {
        "K01B": {
            "details": {
                "area-public": _detail(
                    "area-public", "พื้นที่สาธารณะ", "f2_cultural_market_civil"
                )
            },
            "withheld": {},
        },
        "K03": {
            "details": {
                "activity-public": _detail(
                    "activity-public", "กิจกรรมสาธารณะ", "f2_culturalmap_university"
                )
            },
            "withheld": {},
        },
        "K04": {"details": {"innovation-shared": shared}, "withheld": {}},
        "C04_LISTED": {
            "details": {
                "innovation-shared": shared,
                "innovation-listed-only": listed_only,
            },
            "withheld": {},
        },
        "K05": {
            "details": {
                "operator-public": _detail(
                    "operator-public", "ธุรกิจสาธารณะ", "f2_learning_area_based"
                )
            },
            "withheld": {},
        },
        "K07": {
            "details": {
                "family-public": _detail(
                    "family-public", "ตระกูลผลงานสาธารณะ", "f2_icommunity"
                )
            },
            "withheld": {},
        },
        "C08_PARTICIPATING": {
            "details": {
                "business-public": _detail(
                    "business-public", "ผู้เข้าร่วมสาธารณะ", "f2_learning_area_based"
                )
            },
            "withheld": {},
        },
        "K12": {
            "details": {
                "mapped-public": _detail(
                    "mapped-public",
                    "รายการสาธารณะ",
                    "f2_culturalmap_university",
                    large=True,
                )
            },
            "withheld": {"mapped-private": "unapproved_person_bearing_subject"},
        },
    }


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_full_synthetic_projection_covers_public_surface_and_privacy_boundary(
    tmp_path, monkeypatch
):
    release = tmp_path / "release"
    output = tmp_path / "stage"
    release.mkdir()
    definitions = _definitions()
    tables = _synthetic_tables()
    policy = _policy()
    manifest = {
        "release_id": "f2-dashboard-snapshot-v3",
        "release_date": "2026-09-12",
        "input_lock_sha256": "1" * 64,
        "profile": "full",
        "complete": True,
        "publication_status": "internal_only",
        "validation_status": "passed",
        "enabled_sources": _SOURCE_IDS,
    }
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (release / "projection_policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    (release / "definitions.json").write_text(
        json.dumps({"measures": definitions}), encoding="utf-8"
    )
    queries = {
        row["measure_id"]: MeasureQuery(row, tables, tables["provinces"])
        for row in definitions
    }
    stored = {
        measure_id: query.select()["result"] for measure_id, query in queries.items()
    }
    (release / "results.json").write_text(json.dumps(stored), encoding="utf-8")
    monkeypatch.setattr(
        projection, "verify_release", lambda *_args, **_kwargs: manifest
    )
    monkeypatch.setattr(projection, "load_release_tables", lambda _path: tables)
    from tools.f2_pipeline import public_details

    monkeypatch.setattr(
        public_details, "build_details", lambda *_args, **_kwargs: _details()
    )
    actual_privacy = projection._privacy_problems
    privacy_calls = []

    def record_privacy(payload, **kwargs):
        privacy_calls.append(kwargs)
        return actual_privacy(payload, **kwargs)

    monkeypatch.setattr(projection, "_privacy_problems", record_privacy)
    proof = {
        "release_id": manifest["release_id"],
        "release_manifest_sha256": projection.digest(release / "manifest.json"),
        "scope": "internal_release_only",
        "public_promotion_approved": False,
        "comparison_sha256": "2" * 64,
        "review_sha256": "3" * 64,
    }
    report = projection.build_full_projection(release, output, comparison_proof=proof)

    public_manifest = _load(output / "manifest.json")
    overview = _load(output / "overview.json")
    geography = _load(output / "geography.json")
    topics = {
        path.stem: _load(path) for path in sorted((output / "topics").glob("*.json"))
    }
    assert report.release_id == "f2-dashboard-snapshot-v3"
    assert report.topic_count == 14
    assert len(overview["headlines"]) == 14
    assert sum(len(row["companions"]) for row in overview["headlines"]) == 7
    assert len(geography["national"]["results"]) == 21
    assert len(geography["provinces"]) == 77
    assert all(len(row["results"]) == 21 for row in geography["provinces"].values())
    assert set(topics) == {
        "k01a",
        "k01b",
        "k02",
        "k03",
        "k04",
        "k05",
        "k06",
        "k07",
        "k08",
        "k09",
        "k10",
        "k11a",
        "k11b",
        "k12",
    }

    assert public_manifest["source_ids"] == sorted(_SOURCE_IDS)
    assert public_manifest["complete"] is True
    assert public_manifest["validation_status"] == "passed"
    assert public_manifest["owner_checkpoint_required"] is True
    assert public_manifest["publication_approval_claimed"] is False
    assert public_manifest["source_snapshots"] == {}
    assert (
        "fiscal_year"
        not in topics["k08"]["filter_contracts"]["C08_PARTICIPATING"][
            "supported_filters"
        ]
    )
    assert public_manifest["internal_review"] == proof
    assert (
        public_manifest["internal_manifest_sha256"] == proof["release_manifest_sha256"]
    )
    assert "counted_total" not in public_manifest
    assert public_manifest["counts_by_measure"]["K04"] == {
        "counted_entity_total": 1,
        "public_detail_total": 1,
        "withheld_detail_total": 0,
    }
    assert public_manifest["counts_by_measure"]["C04_LISTED"] == {
        "counted_entity_total": 2,
        "public_detail_total": 2,
        "withheld_detail_total": 0,
    }
    assert public_manifest["counts_by_measure"]["K10"]["counted_entity_total"] is None
    assert (
        public_manifest["detail_inventory"]["detail_record_count"]
        == report.detail_record_count
    )
    for measure_id in projection._DETAIL_MEASURES:
        counts = public_manifest["counts_by_measure"][measure_id]
        assert counts["counted_entity_total"] == (
            counts["public_detail_total"] + counts["withheld_detail_total"]
        )

    manifest_entries = {row["path"]: row for row in public_manifest["files"]}
    assert len(manifest_entries) == report.file_count - 1
    for relative, entry in manifest_entries.items():
        data = (output / relative).read_bytes()
        assert entry["size"] == len(data)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert set(entry) == {"path", "artifact_key", "sha256", "size", "source_ids"}
        assert entry["source_ids"] == json.loads(data)["source_ids"]
    assert len(privacy_calls) == len(manifest_entries) + 1
    topic_contexts = policy["publication_field_contexts"]
    for call in privacy_calls:
        path = call["artifact_path"].removeprefix("data/public/f2/")
        assert call["field_contexts"] == (
            topic_contexts if path.startswith(("topics/", "details/")) else {}
        )

    for relative in [*manifest_entries, "manifest.json"]:
        payload = _load(output / relative)
        assert payload["internal_review"] == proof
        assert (
            payload["projection_policy_sha256"]
            == public_manifest["projection_policy_sha256"]
        )
        assert payload["publication_approval_claimed"] is False
        assert payload["additional_field_review_status"] == "pending_owner_acceptance"

    geography_text = json.dumps(geography, ensure_ascii=False)
    assert '"sections"' not in geography_text
    assert '"items_by_id"' not in geography_text
    assert '"prepared_filters"' not in geography_text
    province = geography["provinces"]["01"]
    assert province["results"]["K09"]["value"] is None
    k09_context = [
        row for row in province["context_results"] if row["measure_id"] == "K09"
    ]
    assert {row["relationship"] for row in k09_context} == {
        "national_context_not_fallback",
        "independent_source_region_not_mapped_to_selected_dashboard_geography",
    }
    assert geography["source_region_scheme"]["dashboard_region_mapping"] is None
    assert all(
        row["dashboard_region_link"] is None
        and row["source_region_id"] not in geography["regions"]
        for row in geography["source_regions"].values()
    )

    k01a_assertions = topics["k01a"]["scopes"]["province/01"]["sections"][0][
        "supporting_assertions"
    ]
    assert k01a_assertions
    assert set(k01a_assertions[0]) == {
        "province_code",
        "province_name_th",
        "source_id",
        "location_role",
        "disposition",
        "evidence_rule",
        "lineage_status",
        "reason",
        "assertion_count",
    }
    assert not (
        {"raw_locator", "observation_id", "source_table"} & set(k01a_assertions[0])
    )

    k02_scope = topics["k02"]["scopes"]["province/01"]
    assert set(k02_scope["coverage"]) == {"K02", "C02_COMMUNITY"}
    assert set(k02_scope["prepared_filters"]) == {"K02", "C02_COMMUNITY"}
    assert {
        row["id"]
        for row in k02_scope["prepared_filters"]["K02"]["choices"]["source_level"]
    } == {"1", "2"}
    k02_text = json.dumps(topics["k02"], ensure_ascii=False)
    assert "person-community-private" not in k02_text
    assert "person-inventor-private" not in k02_text

    c08_prepared = topics["k08"]["scopes"]["national"]["prepared_filters"][
        "C08_REPORTED_BUSINESSES"
    ]
    assert {row["id"] for row in c08_prepared["choices"]["source_dimension"]} == {
        "categories",
        "entityTypes",
        "geography",
        "provinces",
    }
    k08_text = json.dumps(topics["k08"], ensure_ascii=False)
    assert "person-assessed-private" not in k08_text
    assert "person-increased-private" not in k08_text

    source_region_ids = sorted(geography["source_regions"])
    k09_prepared = topics["k09"]["scopes"]["national"]["prepared_filters"]["K09"]
    assert {row["id"] for row in k09_prepared["choices"]["source_region"]} == set(
        source_region_ids
    )
    k10_prepared = topics["k10"]["scopes"]["national"]["prepared_filters"]["K10"]
    c10_prepared = topics["k10"]["scopes"]["national"]["prepared_filters"][
        "C10_ALTERNATIVE"
    ]
    assert {
        f"component/{value}"
        for value in ("localEmployeeExpense", "localResourceExpense")
    } <= set(k10_prepared["selections"])
    assert {row["source_id"] for row in topics["k10"]["sources"]} == {
        "f2_learning_dashboard"
    }
    assert all(
        f"source_region/{region_id}/component/{component}" in k10_prepared["selections"]
        for region_id in source_region_ids
        for component in ("localEmployeeExpense", "localResourceExpense")
    )
    assert all(
        f"source_region/{region_id}/component/{component}" in c10_prepared["selections"]
        for region_id in source_region_ids
        for component in ("excludedResourceExpense", "localResourceExpense")
    )
    assert (
        topics["k10"]["scopes"]["national"]["results"]["K10"]["value_exact"] == "10.5"
    )

    k04 = topics["k04"]
    item_lists = k04["item_ids_by_measure_and_scope"]
    assert set(k04["items_by_id"]) == {
        "innovation-listed-only",
        "innovation-shared",
    }
    assert item_lists["K04"]["national"] == ["innovation-shared"]
    assert item_lists["C04_LISTED"]["national"] == [
        "innovation-listed-only",
        "innovation-shared",
    ]
    assert item_lists["K04"]["region/dashboard_region_b"] == []
    assert item_lists["C04_LISTED"]["region/dashboard_region_b"] == [
        "innovation-listed-only"
    ]
    national_k04 = next(
        section
        for section in k04["scopes"]["national"]["sections"]
        if section["measure_ids"] == ["K04"]
    )
    assert national_k04["item_list_scope"] == "national"
    assert "item_ids" not in national_k04
    assert (
        "item_ids"
        not in k04["scopes"]["national"]["prepared_filters"]["K04"]["default"]
    )

    k12 = topics["k12"]
    assert set(k12["items_by_id"]) == {"mapped-public"}
    assert set(k12["items_by_id"]["mapped-public"]) == {
        "label",
        "identity_status",
        "province_codes",
        "category_codes",
        "source_ids",
        "identity_review",
    }
    assert k12["items_by_id"]["mapped-public"]["identity_review"] == {
        "outcome": "source_record_only",
        "merge_scope": None,
        "counting": "separate",
        "name_quality": "supported",
    }
    province_categories = k12["scopes"]["province/01"]["prepared_filters"]["K12"]
    assert province_categories["selections"]["category/A"]["item_ids"] == [
        "mapped-public"
    ]
    k12_text = json.dumps(k12, ensure_ascii=False)
    assert "mapped-private" not in k12_text
    assert k12["details_by_id"] == {}
    lookup = k12["detail_artifacts"]["mapped-public"]
    assert k12["detail_lookup"] == {
        "records_pointer": "/details_by_id",
        "identity": "items_by_id key",
        "default_artifact_key": "f2/topic/k12",
        "artifact_keys_by_id": "detail_artifacts",
    }
    child_entry = next(
        entry for entry in manifest_entries.values() if entry["artifact_key"] == lookup
    )
    child = _load(output / child_entry["path"])
    assert child["details_by_id"]["mapped-public"]["entity_id"] == "mapped-public"
    assert projection._encoded_size(child) <= policy["max_detail_child_bytes"]

    aggregate_member = topics["k10"]["scopes"]["national"]["sections"][0]["breakdowns"][
        0
    ]
    assert {
        "item_id",
        "label",
        "amount",
        "amount_unit",
        "result_divisor",
        "source_id",
    } <= set(aggregate_member)
    assert not (
        {"member_id", "evidence_id", "raw_locator", "evidence_table"}
        & set(aggregate_member)
    )


def test_projection_rejects_unbound_review_and_protected_output_overlap(
    tmp_path, monkeypatch
):
    release = tmp_path / "release"
    release.mkdir()
    (release / "manifest.json").write_text("{}", encoding="utf-8")
    manifest = {"release_id": "f2-dashboard-snapshot-v3"}
    good_hash = projection.digest(release / "manifest.json")
    with pytest.raises(PipelineError, match="does not bind"):
        projection._review_proof(
            release,
            manifest,
            {
                "release_id": manifest["release_id"],
                "release_manifest_sha256": good_hash,
                "scope": "internal_release_only",
                "public_promotion_approved": True,
            },
        )
    monkeypatch.setattr(
        projection,
        "verify_release",
        lambda *_args, **_kwargs: pytest.fail(
            "release read before output boundary check"
        ),
    )
    with pytest.raises(PipelineError, match="overlaps"):
        projection.build_full_projection(
            release,
            release / "nested-output",
            comparison_proof={},
        )
    repository = Path(projection.__file__).resolve().parents[2]
    for protected in (
        repository / "data/public/f2/new-stage",
        repository / "data/runtime/f2/raw/new-stage",
        repository / "data/runtime/f2/reviews/new-stage",
        repository / "config/f2_pipeline/new-stage",
    ):
        with pytest.raises(PipelineError, match="overlaps"):
            projection.ensure_new_output(
                protected, projection._protected_paths(release)
            )


def test_final_payload_rejects_raw_detail_fields_before_privacy_write():
    policy = _policy()
    with pytest.raises(PipelineError, match="excluded fields"):
        projection._validate_payload(
            "details/k12-000.json",
            {
                "release_id": "f2-dashboard-snapshot-v3",
                "details_by_id": {
                    "mapped-public": {
                        "entity_id": "mapped-public",
                        "raw_locator": "evidence://private",
                    }
                },
            },
            policy,
        )
