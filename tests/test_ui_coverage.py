from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup


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
    province_panel = BeautifulSoup(template, "html.parser").find(id="provincePanel")
    assert province_panel is not None
    assert province_panel.find("table") is None


def test_dashboard_separates_departments_and_removes_old_province_tabs() -> None:
    template = read("app/templates/index.html")
    script = read("app/static/app.js")

    for label in ("ฝ่าย 1", "ฝ่าย 2", "ฝ่าย 3", "ฝ่าย 4", "ผู้บริหาร"):
        assert label in template
    assert 'data-panel-tab=' not in template
    assert 'id="provincePanelTabs"' not in template
    assert 'data-panel-view="department"' in template
    assert 'data-panel-view="f1"' in template
    assert 'data-panel-view="overview"' in template
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


def test_disaster_renderer_is_not_exposed_as_a_separate_top_level_tab() -> None:
    template = read("app/templates/index.html")
    script = read("app/static/app.js")
    styles = read("app/static/styles.css")

    assert "ติดตามภัย" in template
    assert 'data-map-mode="disaster"' not in template
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


def test_f4_workspace_preserves_r2_data_and_uses_department_navigation() -> None:
    template = read("app/templates/index.html")
    script = read("app/static/app.js")
    styles = read("app/static/styles.css")

    assert 'data-map-mode="f3"' in template
    assert 'data-map-mode="f4"' in template
    assert 'data-map-mode="executive"' in template
    assert template.index('data-map-mode="f3"') < template.index('data-map-mode="f4"')
    assert template.index('data-map-mode="f4"') < template.index('data-map-mode="executive"')
    assert "เสริมพลังท้องถิ่น" in template
    for element_id in (
        "f4CountryPanel",
        "f4PanelScopeLabel",
        "f4OverviewHeading",
        "showF4Country",
        "f4CountryCards",
        "f4EconomicImpactWrap",
        "f4EconomicImpactRows",
        "f4CountryNotes",
        "f4InnovationRows",
        "f4PolicyRows",
        "f4PolicyDonut",
        "f4PolicyBudget",
    ):
        assert f'id="{element_id}"' in template

    for endpoint in (
        "/api/public/v1/f4/overview",
        "/api/public/v1/f4/innovations",
        "/api/public/v1/f4/policy-projects",
        "/api/public/v1/f4/regions/",
        "/api/public/v1/f4/provinces/${normalized}",
    ):
        assert endpoint in script
    for function_name in (
        "applyF4TargetProvinceMembership",
        "renderF4CountryPanel",
        "renderF4EconomicImpactTable",
        "renderF4PolicySummary",
        "f4ReadinessLabel",
        "resetF4ToCountryOverview",
        "collapseF4Board",
        "showF4Board",
    ):
        assert function_name in script
    assert 'return ["f2", "f3"].includes(mode)' in script
    assert "f4_target_province" in script
    assert "trl_level" in script
    assert "budget_baht" in script
    assert "status_summary" in script
    assert ".f4-country-panel" in styles
    assert ".f4-economic-table" in styles
    assert ".f4-board-toggle" in styles
    assert ".f4-policy-window" in styles
    assert ".f4-donut" in styles
    assert ".f4-record-card" in styles


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


def test_f1_and_f4_share_the_department_panel_pattern() -> None:
    template = read("app/templates/index.html")
    script = read("app/static/app.js")
    styles = read("app/static/styles.css")

    assert 'class="department-panel department-panel--f1 f1-country-panel"' in template
    assert 'class="department-panel department-panel--f4 f4-country-panel"' in template
    assert 'class="department-panel workspace-panel"' in template
    assert 'class="department-board-toggle f1-board-toggle"' in template
    assert 'class="department-board-toggle f4-board-toggle"' in template
    assert 'class="department-board-toggle workspace-board-toggle"' in template
    assert 'class="department-flow f1-flow"' in template
    assert 'class="department-flow f4-flow"' in template
    for element_id in ("f4CountryStep", "f4RegionStep", "f4ProvinceStep"):
        assert f'id="{element_id}"' in template
    assert 'class="department-kpi-grid f1-country-kpis"' in template
    assert 'class="department-kpi-grid f4-card-grid"' in template
    assert 'class="department-kpi-card province-kpi f4-kpi"' in script
    assert 'class="department-kpi-card ${state.f1CountryMetric' in script
    assert 'regionStep.classList.toggle("active", Boolean(state.selectedRegion))' in script
    assert 'provinceStep.classList.toggle("active", Boolean(state.selectedCode))' in script
    assert 'card.match_type ?' not in script
    assert 'document.body.classList.toggle("f1-province-open"' in script
    assert 'document.getElementById("showF1Country").addEventListener("click", showF1CountryPanel)' in script
    assert 'document.getElementById("showWorkspacePanel").addEventListener("click", showWorkspacePanel)' in script
    assert 'function usesMobileMapFirst()' in script
    assert 'function syncResponsiveWorkspace()' in script
    assert 'mobileLayoutQuery.addEventListener("change", syncResponsiveWorkspace)' in script
    assert 'hideF1CountryPanel(true);' in script
    assert 'state.f4BoardCollapsed = usesMobileMapFirst() && !state.selectedCode' in script
    assert 'hideWorkspacePanel(true);' in script
    assert ".department-panel--f1" in styles
    assert ".department-panel--f4" in styles
    assert ".department-flow" in styles
    assert ".department-kpi-card" in styles
    assert ".department-board-toggle" in styles
    assert '.province-panel[aria-hidden="true"]' in styles
    assert "body.f1-province-open .mode-dock" in styles
    assert "width: min(620px, calc(100vw - 44px))" in styles
    assert "height: min(68dvh, 720px)" in styles
    assert '.department-dock button[data-map-mode="f1"]' in styles
    assert '.department-dock button[data-map-mode="f4"]' in styles
    assert "left: calc((100vw - min(620px, 100vw - 44px) - 22px) / 2)" in styles
    assert "body.workspace-panel-open .map-corner" in styles
    assert "@media (min-width: 721px) and (max-width: 949px)" in styles
    assert "grid-template-columns: repeat(5, minmax(0, 1fr))" in styles
    assert ".department-flow {\n    display: none;" in styles
    assert ".f4-country-tabs {\n    position: static;" in styles


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
