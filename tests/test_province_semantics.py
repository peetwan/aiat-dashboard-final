from __future__ import annotations

import json
from pathlib import Path


PUBLIC_ROOT = Path(__file__).parents[1] / "data" / "public"
CONTRACT_ROOT = Path(__file__).parents[1] / "config" / "publication_contracts"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_provinces_keep_project_participant_and_unknown_semantics() -> None:
    profiles = read_json(PUBLIC_ROOT / "public_dashboard.json")["provinces"]
    briefings = {
        path.stem: read_json(path)
        for path in (PUBLIC_ROOT / "provincial_briefings").glob("[0-9][0-9].json")
    }
    summaries = {
        path.stem: read_json(path)
        for path in (PUBLIC_ROOT / "executive_summaries").glob("[0-9][0-9].json")
    }

    dashboard_contract = read_json(CONTRACT_ROOT / "dashboard_core.json")
    expected_provinces = next(
        output["expected_count"]
        for output in dashboard_contract["outputs"]
        if output.get("path") == "data/public/public_dashboard.json"
    )
    assert len(profiles) == len(briefings) == len(summaries) == expected_provinces

    for profile in profiles:
        code = profile["province_code"]
        briefing = briefings[code]
        summary = summaries[code]
        portfolio = summary["research_portfolio"]

        assert profile["area_based_participant_records"] == briefing["sections"]["area_based"]["total_records"]
        assert profile["area_based_project_groups"] == briefing["sections"]["project_master"]["total_records"]
        assert profile["area_based_participant_records"] >= 0
        assert profile["area_based_project_groups"] >= 0
        assert portfolio["participant_record_count"] == briefing["sections"]["area_based"]["total_records"]
        assert portfolio["project_count"] == briefing["sections"]["project_master"]["total_records"]
        assert [stage["key"] for stage in summary["decision_chain"]] == [
            "need",
            "input",
            "activity",
            "output",
            "outcome",
        ]
        assert summary["data_quality_overview"]["accepted_source_count"] == 0
        assert summary["methodology"]["project_count_method"] == (
            "provisional_project_name_fiscal_year_research_unit_grouping"
        )
        assert summary["methodology"]["funding_attribution"] == (
            "linked_innovation_funding_not_provincial_allocation"
        )

        if profile["sra_scope_status"] == "in_scope_no_current_value":
            assert profile["sra_overall_score"] is None
            assert briefing["sections"]["sra"]["scope_status"] == "in_scope"
            assert briefing["sections"]["sra"]["score_status"] == "in_scope_no_current_value"


def test_multi_province_innovation_funding_is_never_a_provincial_allocation() -> None:
    summaries = [
        read_json(path)
        for path in (PUBLIC_ROOT / "executive_summaries").glob("[0-9][0-9].json")
    ]
    multi_province = [
        summary["research_portfolio"]["funding"]
        for summary in summaries
        if summary["research_portfolio"]["funding"]["multi_province_innovation_count"] > 0
    ]

    assert multi_province
    assert all(item["cross_province_sum_warning"] is True for item in multi_province)
    assert all(
        item["allocation_status"] == "linked_innovation_funding_not_provincial_allocation"
        for item in multi_province
    )
