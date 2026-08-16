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
