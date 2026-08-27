from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = ROOT / "data" / "public"


def read_json(name: str) -> dict:
    return json.loads((PUBLIC_ROOT / name).read_text(encoding="utf-8"))


def test_f1_projection_has_all_reviewed_province_district_and_tambon_rows() -> None:
    payload = read_json("f1_detail_projection.json")

    assert payload["as_of"] == "2569"
    assert payload["coverage"] == {
        "province_count": 20,
        "district_list_count": 293,
        "district_data_count": 132,
        "tambon_list_count": 1136,
        "tambon_data_count": 757,
    }
    assert len(payload["provinces"]) == 20

    provinces = list(payload["provinces"].values())
    districts = [district for province in provinces for district in province["districts"]]
    tambons = [tambon for district in districts for tambon in district["tambons"]]

    assert len(districts) == payload["coverage"]["district_list_count"]
    assert sum(bool(row["has_current_data"]) for row in districts) == payload["coverage"]["district_data_count"]
    assert len(tambons) == payload["coverage"]["tambon_list_count"]
    assert sum(bool(row["has_current_data"]) for row in tambons) == payload["coverage"]["tambon_data_count"]
    assert all(row["district_name"] for row in districts)
    assert all(row["tambon_name"] for row in tambons)


def test_f1_projection_keeps_every_detailed_public_section() -> None:
    payload = read_json("f1_detail_projection.json")
    capital_keys = {"human", "physical", "financial", "natural_res", "social"}
    project_keys = {
        "project_households",
        "poor_people",
        "local_people",
        "area_researcher",
        "area_developer",
        "freelance_worker",
        "entrepreneur",
        "support_org",
        "vvn_org",
        "apptech_institute",
        "apptech_rmu",
        "innovation",
    }

    for province in payload["provinces"].values():
        assert set(province["livelihood_capitals"]["scores"]) == capital_keys | {"overall"}
        assert set(province["livelihood_capitals"]["score_spread"]) == {
            f"{key}_sd" for key in capital_keys | {"overall"}
        }
        details = province["livelihood_capitals"]["details"]
        assert {row["key"] for row in details} == capital_keys
        assert all(row["sections"] or row["detail_available"] is False for row in details)
        assert all(row["sections"] == [] for row in details if row["detail_available"] is False)
        assert {row["key"] for row in province["project"]["items"]} == project_keys
        assert province["project"]["year"] in province["project"]["years_with_data"]
        assert len(province["assistance"]["dimensions"]) == 5
        assert province["assistance"]["yearly"]["years"]
        assert len(province["poverty_models"]) == 4


def test_f1_projection_and_endpoint_publish_aggregate_data_only() -> None:
    payload = read_json("f1_detail_projection.json")
    assert payload["privacy"] == {
        "grain": "ข้อมูลรวมระดับจังหวัด อำเภอ และตำบล",
        "aggregate_only": True,
        "individual_records_included": False,
        "direct_identifiers_included": False,
    }

    with TestClient(app) as client:
        response = client.get("/api/public/v1/f1/provinces/18")
        missing = client.get("/api/public/v1/f1/provinces/10")

    assert response.status_code == 200
    province = response.json()["province"]
    assert province["province_name_th"] == "ชัยนาท"
    assert province["coverage"] == {
        "district_list_count": 8,
        "district_data_count": 3,
        "tambon_list_count": 21,
        "tambon_data_count": 15,
    }
    assert len(province["districts"]) == 8
    assert len(province["livelihood_capitals"]["details"]) == 5
    assert missing.status_code == 404


def test_f1_ui_opens_directly_and_keeps_its_tabs_within_reach() -> None:
    script = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    template = (ROOT / "app/templates/index.html").read_text(encoding="utf-8")
    f1_script = script.split("const F1_PROJECT_LABELS", 1)[1].split("function isObservedStatus", 1)[0]

    for label in (
        "พื้นที่",
        "คนและครัวเรือน",
        "ทุน 5 ด้าน",
        "แนวทางแก้จน",
        "ผลงานโครงการ",
        "คนทำงาน",
        "เครือข่าย",
        "ความช่วยเหลือ",
        "แผนจังหวัด",
    ):
        assert label in f1_script
    assert 'id="f1ProvinceToolbar"' in template
    assert 'id="f1ProvinceKpis"' in template
    assert 'id="provincePanelTabs"' not in template
    assert 'data-panel-tab=' not in template
    assert 'data-map-mode="f1"' in template
    for department_mode in ("f2", "f3", "f4", "executive"):
        assert f'data-map-mode="{department_mode}"' in template
    assert "position: sticky" in styles
    assert 'fetch(`/api/public/v1/f1/provinces/${code}`' in script
    assert 'document.getElementById("panelContent")' in f1_script
    assert 'initialParams.get("mode")' in script
    assert 'initialParams.get("f1tab")' in script
    for field_reference in (
        "people.household_groups",
        "people.people_groups",
        "district.people_groups",
        "row.gender?.male",
        "capital.score_spread",
        "poor_income_sum_baht",
        "assistance.yearly?.years",
        "item.yoy_pct",
        "state.f1Overview.province_groups",
    ):
        assert field_reference in f1_script
    assert "·" not in f1_script


def test_dashboard_uses_five_separate_workspaces() -> None:
    script = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    template = (ROOT / "app/templates/index.html").read_text(encoding="utf-8")

    modes = ("f1", "f2", "f3", "f4", "executive")
    positions = [template.index(f'data-map-mode="{mode}"') for mode in modes]
    assert positions == sorted(positions)
    assert 'mapMode: "f1"' in script
    assert 'const WORKSPACE_MODES = ["f1", "f2", "f3", "f4", "executive"]' in script
    assert "WORKSPACE_MODES.includes(initialMode)" in script
    assert "function renderWorkspacePanel()" in script
    assert "function renderDepartmentProvince(province)" in script
    assert 'data-panel-view="department"' in template
    assert 'id="workspacePanel"' in template
    assert "ยังไม่มีข้อมูลของฝ่าย" in script
    assert "ภาพรวมพื้นที่" in script
    assert ".department-dock" in styles
    assert ".workspace-panel" in styles
    assert ".department-province-card" in styles

    for removed_mode in ("projects", "sra", "innovation", "coverage", "disaster"):
        assert f'data-map-mode="{removed_mode}"' not in template
