from copy import deepcopy

import pytest

from app.f4_data import _project_row
from tools.build_clig_work_attribution import project_attributions
from app.publication import SourceUrlRule, _canonical_url, _url_matches_rule


def example():
    project = {"project_id": "work-1", "project_title": "โครงการตัวอย่าง", "detail_url": "https://example.org/work/1"}
    detail = {"detail_ref": "work-1", "project_name": "โครงการตัวอย่างฉบับละเอียด",
              "source_url": project["detail_url"], "raw_html_sha256": "a" * 64, "fetched_at": "2026-08-25T00:00:00Z",
              "fields": {"ชื่อ-นามสกุล (ภาษาไทย)": "ผู้วิจัยตัวอย่าง", "ตำแหน่ง": "หัวหน้าโครงการ",
                         "สัญชาติ": "ไม่เผยแพร่", "เพศ": "ไม่เผยแพร่", "phone": "private-value"}}
    return project, detail


def test_clig_public_attribution_reaches_project_response_without_raw_person_details():
    project, detail = example()
    item = project_attributions([project], [detail])[0]
    assert item["researcher_name_th"] == "ผู้วิจัยตัวอย่าง"
    assert "fields" not in item and "phone" not in item and "เพศ" not in item
    assert _project_row(project, item)["researcher_name_th"] == "ผู้วิจัยตัวอย่าง"
    assert "researcher_name_th" not in _project_row({**project, "researcher_name_th": "unreviewed-value"})
    mismatched = {**item, "source_url": "https://example.org/work/another"}
    assert "researcher_name_th" not in _project_row(project, mismatched)


@pytest.mark.parametrize("drift", ["missing", "duplicate", "url"])
def test_clig_attribution_rejects_incomplete_or_mismatched_evidence(drift):
    project, detail = example()
    rows = [detail]
    if drift == "missing": rows = []
    elif drift == "duplicate": rows.append(deepcopy(detail))
    else: detail["source_url"] = "https://example.org/work/another"
    with pytest.raises(ValueError):
        project_attributions([project], rows)


def test_registered_detail_query_template_accepts_ids_without_opening_other_routes():
    rule = SourceUrlRule(_canonical_url("https://example.org/details?id={project_id}&scope=public", catalog=True), False)
    assert _url_matches_rule(_canonical_url("https://example.org/details?id=work-1&scope=public", catalog=False), rule)
    for url in (
        "https://example.org/details?id=work-1&scope=private",
        "https://example.org/details?id=&scope=public",
        "https://example.org/details?id=work-1&scope=public&extra=value",
        "https://example.org/admin?id=work-1&scope=public",
    ):
        assert not _url_matches_rule(_canonical_url(url, catalog=False), rule)
