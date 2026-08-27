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
    assert "research_lead_affiliations" in script
    assert "research_lead_names" not in script


def test_disaster_lens_uses_connected_counts_and_normalized_cards() -> None:
    template = read("app/templates/index.html")
    script = read("app/static/app.js")
    styles = read("app/static/styles.css")

    assert "ติดตามภัย" in template
    assert 'data-map-mode="disaster"' in template
    assert "chart.js" in template.lower()
    assert "province.disaster_source_count" in script
    assert "province.disaster_record_count" in script
    assert "quality_label_th" in script
    assert "renderDisasterInsights" in script
    assert "renderDisasterTrends" in script
    assert "renderDisasterLineChart" in script
    assert "renderDisasterLatestPoints" in script
    assert "openStationHistoryModal" in script
    assert "data-disaster-history" in script
    assert "data-history-grain" in script
    assert "disaster-stations" in script
    assert "new Chart" in script
    assert "if (!points.length) return" in script
    assert "renderDisasterRecord" in script
    disaster_script = script.split("async function renderDisaster()", 1)[1].split("function renderHousing", 1)[0]
    assert "<table" not in disaster_script.lower()
    assert "Object.entries(record)" not in disaster_script
    assert ".disaster-source-card" in styles
    assert ".disaster-metrics" in styles
    assert ".disaster-trend" in styles
    assert ".disaster-latest-grid" in styles
    assert ".station-history-modal" in styles
    assert ".station-history-controls" in styles
    assert "overflow-x: auto" in styles
    assert ".disaster-record table" not in styles


def test_f4_lens_is_r2_backed_and_before_disaster() -> None:
    template = read("app/templates/index.html")
    script = read("app/static/app.js")
    styles = read("app/static/styles.css")

    assert 'data-map-mode="f4"' in template
    assert template.index('data-map-mode="f4"') < template.index('data-map-mode="disaster"')
    assert "เสริมพลังท้องถิ่น" in template
    for element_id in (
        "f4CountryPanel",
        "f4PanelScopeLabel",
        "f4OverviewHeading",
        "showF4Country",
        "f4CountryCards",
        "f4CountryNotes",
        "f4InnovationRows",
        "f4PolicyRows",
        "f4PolicyDonut",
        "f4PolicyBudget",
    ):
        assert f'id="{element_id}"' in template
    assert "f4ProvinceSection" not in template
    assert "data-f4-province" not in template
    assert "/api/public/v1/f4/overview" in script
    assert "/api/public/v1/f4/innovations" in script
    assert "/api/public/v1/f4/policy-projects" in script
    assert "/api/public/v1/f4/regions/" in script
    assert "/api/public/v1/f4/provinces/${encodeURIComponent(state.selectedCode)}" in script
    assert "/api/public/v1/f4/provinces/${normalized}" in script
    assert "setF4CountryTab" in script
    assert "PROVINCE KPI" in script
    assert "Overview KPI ระดับภาค" in script
    assert "state.f4BoardCollapsed = true" in script
    assert "renderF4PolicySummary" in script
    assert "f4ReadinessLabel" in script
    assert "f4RoiLabel" not in script
    assert "section_labels || []).join" not in script
    assert ".f4-record-metrics" in styles
    assert "resetF4ToCountryOverview" in script
    assert "collapseF4Board" in script
    assert "showF4Board" in script
    assert "applyF4TargetProvinceMembership" in script
    assert "f4_target_province" in script
    assert 'state.mapMode === "f4"' in script
    assert "raw/f2" not in script
    assert "AIAT_S3" not in script
    assert ".f4-country-panel" in styles
    assert ".f4-board-toggle" in styles
    assert ".f4-policy-window" in styles
    assert ".f4-donut" in styles
    assert ".f4-record-card" in styles
    assert '.filter((card) => ["innovations", "policy_projects"].includes(card.key))' in script
    assert "openPanelLoading(provinceMeta)" in script
    assert "loadF4ProvinceOverview(normalized)" in script
    assert "Overview KPI ระดับจังหวัด" in script
    assert "right: 820" not in script
    assert "[-330, 0]" not in script
    assert "f4BoardIsOpen" in script
    assert "mapPanelPadding" in script
    assert "mapPanelOffset" in script
    assert "[-340, 0]" in script
    assert "return [0, 0]" in script
    assert "offset: mapPanelOffset()" in script
    assert "position: fixed" in styles


def test_insights_exposes_all_source_coverage_without_controls() -> None:
    template = read("app/templates/insights.html")
    script = read("app/static/insights.js")

    assert 'id="coverage"' in template
    assert 'id="sourceCoverageGrid"' in template
    assert "ทะเบียน 29 แหล่งข้อมูล" in template
    assert 'id="unmapped"' in template
    assert 'id="learningSummary"' in template
    assert 'id="executivePortfolio"' in template
    assert 'id="executiveKpis"' in template
    assert 'id="auditReadiness"' in template
    assert 'id="businessTypeChart"' in template
    assert 'id="culturalChart"' in template
    assert 'id="housingSpatialChart"' in template
    assert 'id="tourismChart"' in template
    assert 'id="cityCompletenessChart"' in template
    assert 'id="sourceHealthGrid"' in template
    assert "renderExecutivePortfolio(payload.executive_portfolio)" in script
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
    assert "ยังไม่มีรายชื่อแหล่งข้อมูลในระบบนี้" in script
    assert "<select" not in template.lower()
    assert "<table" not in template.lower()
    assert "→" not in template
    assert "→" not in script


def test_coverage_styles_are_responsive_and_high_contrast() -> None:
    styles = read("app/static/insights.css")

    assert ".source-coverage-grid" in styles
    assert ".source-coverage-card.is-local-only" in styles
    assert ".loose-data-grid" in styles
    assert ".portfolio-kpis" in styles
    assert ".readiness-donut" in styles
    assert ".portfolio-chart-grid" in styles
    assert ".source-health-grid" in styles
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
    overview_script = script.split("function renderProvinceOverview(summary)", 1)[1].split("function renderSraArea", 1)[0]
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
    assert "ดูข้อมูลจังหวัดทั้งหมด" in overview_template
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


def test_map_and_province_overviews_use_distinct_function_names() -> None:
    script = read("app/static/app.js")

    assert "function renderMapOverview()" in script
    assert "function renderProvinceOverview(summary)" in script
    assert "renderMapOverview();" in script
    assert "renderProvinceOverview(summary);" in script
    assert "function renderOverview(" not in script


def test_full_province_page_summarizes_every_public_section_without_raw_field_dump() -> None:
    template = read("app/templates/province.html")
    script = read("app/static/province.js")
    styles = read("app/static/province.css")

    for section_id in ("executive", "research", "people", "dimensions", "sources", "operations"):
        assert f'id="{section_id}"' in template
    assert 'id="peopleSearch"' in template
    assert "/api/public/v1/operations" in script
    assert "ดูสาระสำคัญ" in script
    assert "ดูทุก field ของรายการนี้" not in script
    assert "Object.entries(item)" not in script
    assert "renderProjectDigest" in script
    assert "renderInnovationDigest" in script
    assert 'role="img"' in script
    assert "data-people-category" in script
    assert "data-load-section" in script
    assert "ข้อมูลที่จำกัดสิทธิ์จะไม่แสดง" in template
    assert ".record-search" in styles
    assert ".metric-strip" in styles
    assert ".chart-row" in styles
    assert '@media (max-width: 480px)' in styles
