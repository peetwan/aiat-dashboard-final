from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_province_panel_has_clean_tourism_and_requirement_sections() -> None:
    template = read("app/templates/index.html")
    script = read("app/static/app.js")

    assert 'id="tourismSection"' in template
    assert 'id="tourismFacts"' in template
    assert 'id="requirementsSection"' in template
    assert "renderTourism(briefing.sections.tourism)" in script
    assert "renderRequirements(briefing.sections.requirements)" in script
    assert "recommendations.length" in script
    assert "trainServices.length + tramServices.length" in script
    assert "tel:" not in script
    assert "phone_display" not in script
    assert "<table" not in template.lower()


def test_province_panel_separates_decisions_projects_people_and_quality() -> None:
    template = read("app/templates/index.html")
    script = read("app/static/app.js")

    for label in ("ภาพรวม", "โครงการและงบ", "คนและพื้นที่", "มิติการพัฒนา", "คุณภาพข้อมูล"):
        assert label in template
    for element_id in (
        "overviewFlow",
        "researchSection",
        "sraAreaSection",
        "povertySection",
        "dataQualitySummary",
    ):
        assert f'id="{element_id}"' in template
    assert "briefing.sections.project_master" in script
    assert "briefing.sections.area_based" not in script
    assert "province.area_based_project_groups" in script
    assert "in_scope_no_current_value" in script
    assert "ไม่แทนค่าที่ไม่พบด้วยศูนย์" in template
    assert "linked_province_count" in script


def test_insights_exposes_all_source_coverage_without_controls() -> None:
    template = read("app/templates/insights.html")
    script = read("app/static/insights.js")

    assert 'id="coverage"' in template
    assert 'id="sourceCoverageGrid"' in template
    assert "ทะเบียน 28 แหล่งข้อมูล" in template
    assert 'id="unmapped"' in template
    assert 'id="learningSummary"' in template
    assert "/downloads/source_coverage.json" in script
    assert "/api/public/v1/source-coverage" in script
    assert "/api/public/v1/learning-dashboard" in script
    assert "/downloads/learning_dashboard.json" in script
    assert "/downloads/unmapped_records.json" in script
    assert "/api/public/v1/unmapped-records" in script
    assert "ข้อมูลที่อยู่อาศัยนอกชั้นจังหวัด" in script
    assert "source_geography_not_at_province_grain" in script
    assert "known_omissions" in script
    assert "not.province" in script
    assert "ทะเบียน public projection ยังไม่ถูกสร้าง" in script
    assert "<select" not in template.lower()
    assert "<table" not in template.lower()


def test_coverage_styles_are_responsive_and_high_contrast() -> None:
    styles = read("app/static/insights.css")

    assert ".source-coverage-grid" in styles
    assert ".source-coverage-card.is-local-only" in styles
    assert ".loose-data-grid" in styles
    assert "@media (max-width: 640px)" in styles
    assert "word-break: normal" in styles


def test_successful_province_load_hides_the_error_state() -> None:
    styles = read("app/static/styles.css")

    assert ".panel-error[hidden]" in styles
    assert "display: none" in styles


def test_executive_ui_is_summary_first_and_mobile_tabs_do_not_clip() -> None:
    template = read("app/templates/index.html")
    script = read("app/static/app.js")
    styles = read("app/static/styles.css")

    assert 'id="peopleOverviewSection"' in template
    assert 'id="peopleAreaOverview"' in template
    assert "renderPeopleAreaOverview(state.currentSummary, briefing)" in script
    assert 'class="quality-ring"' in script
    assert 'class="dimension-evidence"' in script
    assert 'class="source-row ${escapeHtml(source.status)}"' in script
    assert "item.display_value ||" in script
    assert "width: min(700px, calc(100vw - 40px))" in styles
    assert "grid-template-columns: repeat(6, minmax(0, 1fr))" in styles
    assert ".panel-tabs button:nth-child(-n + 3)" in styles
    assert ".panel-tabs button:nth-child(n + 4)" in styles
    assert ".research-stats span" in styles
    assert "white-space: normal" in styles


def test_province_preview_visualizes_only_province_data_and_links_to_full_detail() -> None:
    template = read("app/templates/index.html")
    script = read("app/static/app.js")
    styles = read("app/static/styles.css")
    overview_template = template.split('data-panel-view="overview"', 1)[1].split('data-panel-view="projects"', 1)[0]
    overview_script = script.split("function renderOverview(summary)", 1)[1].split("function renderSraArea", 1)[0]
    overview_styles = styles.split("/* Province preview:", 1)[1].split("/* Executive readability pass:", 1)[0]

    assert "ข้อมูลสำคัญของจังหวัด" in overview_template
    for element_id in (
        "overviewMetrics",
        "overviewFlow",
        "overviewTrlChart",
        "overviewOutcomeChart",
        "overviewDistricts",
        "overviewFunding",
        "fullProvinceLink",
    ):
        assert f'id="{element_id}"' in overview_template
    assert "เปิดข้อมูลจังหวัดฉบับเต็ม" in overview_template
    assert "ตอบได้ตอนนี้" not in overview_script
    assert "ยังตอบไม่ได้" not in overview_script
    assert "available_source_count" not in overview_script
    assert "public_source_count" not in overview_script
    assert 'id="coverageLabel"' not in template
    assert 'id="coverageCount"' not in template
    assert "trl_distribution" in overview_script
    assert "TRL" in overview_template
    assert "ROI / SROI" in overview_script
    assert "`/province/${province.province_code}`" in script
    assert ".province-kpi-grid" in overview_styles
    assert ".overview-flow" in overview_styles
    assert ".overview-bar-row" in overview_styles
    assert ".overview-full-cta" in overview_styles
    assert "gradient" not in overview_styles
    assert "→" not in overview_template


def test_full_province_page_exposes_every_public_section_with_progressive_detail() -> None:
    template = read("app/templates/province.html")
    script = read("app/static/province.js")
    styles = read("app/static/province.css")

    for section_id in ("executive", "research", "people", "dimensions", "sources", "operations"):
        assert f'id="{section_id}"' in template
    assert 'id="peopleSearch"' in template
    assert "/api/public/v1/operations" in script
    assert "ดูทุก field ของรายการนี้" in script
    assert "data-load-section" in script
    assert "restricted" in template
    assert ".record-search" in styles
    assert "@media (max-width: 620px)" in styles
