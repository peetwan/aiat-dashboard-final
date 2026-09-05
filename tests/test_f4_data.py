from __future__ import annotations

import gzip
import json

import pytest

from app import f4_data
from tools.evidence_store import StoreConfig


class FakeBody:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakeR2Client:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.calls: list[str] = []

    def get_object(self, Bucket: str, Key: str) -> dict:
        self.calls.append(Key)
        return {"Body": FakeBody(self.objects[Key])}


def gz_jsonl(rows: list[dict]) -> bytes:
    payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows).encode()
    return gzip.compress(payload)


@pytest.fixture()
def fake_r2(monkeypatch):
    # These fixtures cover R2-only behavior before an AppTech release is available.
    monkeypatch.setattr(f4_data, "load_public_artifact", lambda key, *_args: {"items": product_details} if key == "f4/pmua-product-details" else {})
    products = [
        {
            "title": "เทคโนโลยี A",
            "product_id": 1,
            "provinces": ["90"],
            "districts": ["9001"],
            "subdistricts": ["900101"],
            "source_url": "https://pmua-apptech.com/product/show/1",
            "fetched_at": "2026-08-18T16:20:30+00:00",
            "section_labels": ["ความรู้ / เทคโนโลยี"],
        },
        {
            "title": "เทคโนโลยี B",
            "product_id": 2,
            "provinces": ["50"],
            "districts": [],
            "subdistricts": [],
            "source_url": "https://pmua-apptech.com/product/show/2",
            "fetched_at": "2026-08-18T16:20:30+00:00",
            "section_labels": [],
        },
    ]
    projects = [
        {
            "project_title": "โครงการเพิ่มรายได้จังหวัดสงขลา",
            "project_id": "p1",
            "contract_no": "c1",
            "fiscal_year": "2569",
            "status": "อยู่ระหว่างดำเนินการ",
            "lead_organization": "มหาวิทยาลัย",
            "budget_baht": 100,
            "detail_url": "https://clig.oas.psu.ac.th/iframe/project/project_info?id=p1",
        },
        {
            "project_title": "โครงการไม่ระบุจังหวัด",
            "project_id": "p2",
            "contract_no": "",
            "fiscal_year": "2569",
            "status": "",
            "lead_organization": "หน่วยงาน",
            "budget_baht": 200,
            "detail_url": "https://clig.oas.psu.ac.th/iframe/project/project_info?id=p2",
        },
    ]
    districts = [
        {
            "district_code": "9001",
            "district_name_th": "อำเภอเมืองสงขลา",
            "province_code": "90",
            "province_name_th": "สงขลา",
        },
        {
            "district_code": "5001",
            "district_name_th": "อำเภอเมืองเชียงใหม่",
            "province_code": "50",
            "province_name_th": "เชียงใหม่",
        },
    ]
    subdistricts = [
        {
            "subdistrict_code": "900101",
            "subdistrict_name_th": "บ่อยาง",
            "district_code": "9001",
            "district_name_th": "อำเภอเมืองสงขลา",
            "province_code": "90",
            "province_name_th": "สงขลา",
        }
    ]
    product_details = [
        {
            "product_id": 1,
            "source_url": "https://pmua-apptech.com/product/show/1",
            "title": "เทคโนโลยี A",
            "trl_level": 9,
            "trl_status": "พร้อมใช้",
            "latitude": 7.1,
            "longitude": 100.6,
            "fetched_at": "2026-08-27T04:49:56Z",
        },
        {
            "product_id": 2,
            "source_url": "https://pmua-apptech.com/product/show/2",
            "title": "เทคโนโลยี B",
            "trl_level": 5,
            "trl_status": "ทดลอง",
            "latitude": None,
            "longitude": None,
            "fetched_at": "2026-08-27T04:49:56Z",
        },
    ]
    objects = {
        f4_data.LEARNING_SUMMARY_KEY: json.dumps({"province_rows": 67}).encode(),
        f4_data.LEARNING_DASHBOARD_KEY: json.dumps(
            {"provinces": [["Province", "ธุรกิจชุมชน"], ["สงขลา", 1], ["เชียงใหม่", 1]]},
            ensure_ascii=False,
        ).encode(),
        f4_data.PMUA_PRODUCTS_KEY: gz_jsonl(products),
        f4_data.PMUA_PROPOSE_KEY: "พบข้อมูลทั้งหมด <b>1,161</b> รายการ".encode(),
        f4_data.PMUA_AREA_DISTRICTS_KEY: gz_jsonl(districts),
        f4_data.PMUA_AREA_SUBDISTRICTS_KEY: gz_jsonl(subdistricts),
        f4_data.CLIG_MANIFEST_KEY: json.dumps(
            {"datasets": [{"dataset_key": "clig.projects", "row_count": 107}]}
        ).encode(),
        f4_data.CLIG_PROJECTS_KEY: gz_jsonl(projects),
    }
    client = FakeR2Client(objects)
    monkeypatch.setattr(
        f4_data,
        "config_from_env",
        lambda: StoreConfig(
            endpoint="https://example.invalid",
            bucket="bucket",
            access_key_id="access",
            secret_access_key="secret",
        ),
    )
    monkeypatch.setattr(f4_data, "make_client", lambda _config: client)
    f4_data.clear_f4_cache()
    yield client
    f4_data.clear_f4_cache()


def test_f4_overview_parses_r2_snapshot_and_html_count(fake_r2):
    payload = f4_data.f4_overview({"สงขลา": "90", "เชียงใหม่": "50"})

    assert [card["key"] for card in payload["cards"]] == [
        "target_provinces",
        "innovations",
        "policy_projects",
        "local_innovators",
    ]
    assert payload["cards"][0]["value"] == 67
    assert payload["cards"][0]["membership_count"] == 2
    assert payload["target_province_codes"] == ["50", "90"]
    assert payload["target_province_membership_count"] == 2
    assert payload["cards"][1]["value"] == 1172
    assert payload["cards"][1]["drilldown_row_count"] == 2
    assert payload["cards"][2]["value"] == 107
    assert payload["economic_impact_rows"] == []
    assert "1,161" in " ".join(payload["evidence_notes"])


def test_f4_cache_reuses_r2_objects(fake_r2):
    f4_data.f4_overview()
    first_call_count = len(fake_r2.calls)
    f4_data.f4_overview()

    assert len(fake_r2.calls) == first_call_count


def test_public_f4_uses_reviewed_artifact_and_ignores_candidate_changes(fake_r2, monkeypatch):
    from fastapi.testclient import TestClient
    from app.database import SessionLocal
    from app.main import app
    from app.models import DashboardRecord, PublicArtifact
    from app.public_data import load_public_artifact

    monkeypatch.setattr(f4_data, "load_public_artifact", load_public_artifact)
    with TestClient(app) as client:
        before = client.get("/api/public/v1/f4/overview").json()
        with SessionLocal() as session:
            session.add(DashboardRecord(source_id=f4_data.APPTECH_SOURCE_ID, dataset_key="innovator_dashboard_province", source_record_id="candidate-only", record_hash="candidate-only", payload={"year_filter": "all", "province_name_th": "สงขลา", "total_inno": 999999, "gen_users": 0, "levels": {"1": 999999, "2": 0, "3": 0, "4": 0}}))
            session.add(DashboardRecord(source_id=f4_data.APPTECH_SOURCE_ID, dataset_key="household_economic_summary", source_record_id="candidate-country", record_hash="candidate-country", payload={"year_filter": "all", "cost_reduced_baht": 999999, "income_increased_baht": 999999, "net_income_increased_baht": 999999}))
            session.commit()
        after = client.get("/api/public/v1/f4/overview")
        assert after.status_code == 200
        assert after.json() == before
        assert next(card for card in before["cards"] if card["key"] == "economic_impact")["value"] != 999999
        with SessionLocal() as session:
            artifact = session.get(PublicArtifact, "f4/apptech-aggregates")
            revised = json.loads(json.dumps(artifact.payload))
            all_year = next(row for row in revised["household_economic_summary"] if row["year_filter"] == "all")
            all_year["net_income_increased_baht"] = 123
            artifact.payload = revised
            session.commit()
        served = client.get("/api/public/v1/f4/overview").json()
        assert next(card for card in served["cards"] if card["key"] == "economic_impact")["value"] == 123


def test_f4_filters_province_lists(fake_r2):
    province_names = {"90": "สงขลา", "50": "เชียงใหม่"}

    summary = f4_data.f4_province_summary("90", "สงขลา", province_names)
    innovations = f4_data.f4_innovations("90", province_names)
    projects = f4_data.f4_policy_projects("สงขลา")

    assert summary["is_target_province"] is True
    assert summary["target_membership_source"] == f4_data.LEARNING_DASHBOARD_KEY
    assert summary["cards"][0]["key"] == "target_membership"
    assert summary["cards"][0]["value"] == 1
    assert summary["cards"][1]["value"] == 1
    assert summary["cards"][2]["value"] == 1
    assert innovations["total"] == 1
    assert innovations["rows"][0]["province_names"] == ["สงขลา"]
    assert innovations["rows"][0]["district_names"] == ["อำเภอเมืองสงขลา"]
    assert innovations["rows"][0]["subdistrict_names"] == ["บ่อยาง"]
    assert innovations["rows"][0]["trl_level"] == 9
    assert innovations["rows"][0]["trl_status"] == "พร้อมใช้"
    assert "roi_indicator" not in innovations["rows"][0]
    assert "roi_value" not in innovations["rows"][0]
    assert "roi_unit" not in innovations["rows"][0]
    assert projects["total"] == 1
    assert projects["rows"][0]["project_id"] == "p1"
    assert projects["budget_baht_total"] == 100
    assert projects["status_summary"] == [{"label": "อยู่ระหว่างดำเนินการ", "count": 1}]


def test_f4_region_summary_and_lists_filter_by_region(fake_r2):
    province_names = {"90": "สงขลา", "50": "เชียงใหม่"}

    summary = f4_data.f4_region_summary("ภาคทดสอบ", ["90", "50"], province_names)
    innovations = f4_data.f4_innovations(province_codes=["90", "50"], province_names_by_code=province_names)
    projects = f4_data.f4_policy_projects(province_names_th=["สงขลา", "เชียงใหม่"])

    assert summary["cards"][0]["value"] == 2
    assert summary["cards"][1]["value"] == 2
    assert summary["cards"][2]["value"] == 1
    assert summary["cards"][3]["value"] is None
    assert innovations["total"] == 2
    assert projects["total"] == 1
    assert projects["rows"][0]["project_id"] == "p1"


def test_f4_uses_apptech_connector_innovator_aggregates(monkeypatch, fake_r2):
    province_names = {"90": "สงขลา", "50": "เชียงใหม่"}

    def fake_apptech_records(dataset_key: str, year_filter: str = "all") -> list[dict]:
        assert year_filter in ("all", None)
        if dataset_key == "innovator_dashboard_province":
            assert year_filter == "all"
            return [
                {
                    "year_filter": "all",
                    "province_name_th": "สงขลา",
                    "total_inno": 787,
                    "gen_users": 300,
                    "levels": {"1": 85, "2": 329, "3": 250, "4": 123},
                },
                {
                    "year_filter": "all",
                    "province_name_th": "เชียงใหม่",
                    "total_inno": 563,
                    "gen_users": 127,
                    "levels": {"1": 128, "2": 207, "3": 168, "4": 60},
                },
            ]
        if dataset_key == "household_economic_summary":
            assert year_filter is None
            return [
                {
                    "year_filter": "all",
                    "cost_reduced_baht": 10,
                    "income_increased_baht": 20,
                    "net_income_increased_baht": 30,
                    "geography_note_th": "national only",
                },
                {
                    "year_filter": "2025",
                    "cost_reduced_baht": 7,
                    "income_increased_baht": 11,
                    "net_income_increased_baht": 18,
                    "geography_note_th": "national only",
                }
            ]
        return []

    monkeypatch.setattr(f4_data, "_latest_apptech_records", fake_apptech_records)

    overview = f4_data.f4_overview(province_names)
    local = next(card for card in overview["cards"] if card["key"] == "local_innovators")
    economic = next(card for card in overview["cards"] if card["key"] == "economic_impact")
    assert local["value"] == 1350
    assert local["source_behavior"] == "apptech_connector_aggregate"
    assert local["level_counts"] == {"1": 213, "2": 536, "3": 418, "4": 183}
    assert local["gen_users"] == 427
    assert economic["value"] == 30
    assert economic["geography"] == "country"
    assert overview["economic_impact_rows"] == [
        {
            "year_filter": "all",
            "label": "รวมทั้งหมด",
            "cost_reduced_baht": 10,
            "income_increased_baht": 20,
            "net_income_increased_baht": 30,
            "geography": "country",
            "geography_note_th": "national only",
        },
        {
            "year_filter": "2025",
            "label": "2025",
            "cost_reduced_baht": 7,
            "income_increased_baht": 11,
            "net_income_increased_baht": 18,
            "geography": "country",
            "geography_note_th": "national only",
        }
    ]

    province = f4_data.f4_province_summary("90", "สงขลา", province_names)
    province_local = next(card for card in province["cards"] if card["key"] == "local_innovators")
    province_economic = next(card for card in province["cards"] if card["key"] == "economic_impact")
    assert province_local["value"] == 787
    assert province_local["level_counts"]["2"] == 329
    assert province_economic["value"] is None
    assert province_economic["source_behavior"] == "not_available_by_province"

    region = f4_data.f4_region_summary("ภาคทดสอบ", ["90", "50"], province_names)
    region_local = next(card for card in region["cards"] if card["key"] == "local_innovators")
    region_economic = next(card for card in region["cards"] if card["key"] == "economic_impact")
    assert region_local["value"] == 1350
    assert region_local["gen_users"] == 427
    assert region_economic["value"] is None
    assert region_economic["source_behavior"] == "not_available_by_region"


def test_f4_policy_projects_summarizes_status_and_budget(fake_r2):
    payload = f4_data.f4_policy_projects()

    assert payload["budget_baht_total"] == 300
    assert payload["budget_known_rows"] == 2
    assert payload["status_summary"] == [
        {"label": "อยู่ระหว่างดำเนินการ", "count": 1},
        {"label": "ไม่ระบุสถานะ", "count": 1},
    ]


def test_f4_policy_status_summary_strips_trailing_codes():
    rows = (
        [{"status": "อยู่ระหว่างดำเนินการ 22", "budget_baht": 1}] * 28
        + [{"status": "อยู่ระหว่างดำเนินการ 21", "budget_baht": 1}] * 21
        + [{"status": "อยู่ระหว่างดำเนินการ 20", "budget_baht": 1}] * 7
        + [{"status": "อยู่ระหว่างดำเนินการ 19", "budget_baht": 1}] * 2
        + [{"status": "PMU กำลังตรวจสอบ 22", "budget_baht": 1}]
        + [{"status": "ปิดโครงการ 18", "budget_baht": 1}] * 22
        + [{"status": "ปิดโครงการ 19", "budget_baht": 1}] * 14
        + [{"status": "ปิดโครงการ 20", "budget_baht": 1}] * 6
        + [{"status": "ยุติโครงการ 18", "budget_baht": 1}] * 4
        + [{"status": "ยุติโครงการ 19", "budget_baht": 1}] * 2
    )

    summary = f4_data._policy_project_summary(rows)

    assert summary["total"] == 107
    assert summary["budget_baht_total"] == 107
    assert summary["status_summary"] == [
        {"label": "อยู่ระหว่างดำเนินการ", "count": 58},
        {"label": "PMU กำลังตรวจสอบ", "count": 1},
        {"label": "ปิดโครงการ", "count": 42},
        {"label": "ยุติโครงการ", "count": 6},
    ]


def test_province_coverage_excludes_other_provinces_in_shared_records(fake_r2):
    snapshot = f4_data._snapshot()
    snapshot["products"][0]["provinces"] = ["90", "50"]
    snapshot["clig_projects"][0]["project_title"] = "โครงการสงขลาและเชียงใหม่"
    summary = f4_data.f4_province_summary("90", "สงขลา", {"90": "สงขลา", "50": "เชียงใหม่"})
    assert summary["covered_province_codes"] == ["90"]
    assert summary["coverage_province_codes_by_source"] == {"pmua_apptech": ["90"], "clig": ["90"]}
    assert [section["province_count"] for section in summary["source_sections"]] == [1, 1]


def test_overview_source_summaries_preserve_project_totals(fake_r2):
    overview = f4_data.f4_overview({"สงขลา": "90", "เชียงใหม่": "50"})
    assert overview["coverage_province_codes_by_source"] == {"pmua_apptech": ["50", "90"], "clig": ["90"]}
    clig = next(section for section in overview["source_sections"] if section["key"] == "clig")
    assert clig["project_summary"] == f4_data._policy_project_summary(f4_data.f4_policy_projects()["rows"])
    assert clig["project_summary"]["total"] == 2
    assert clig["project_summary"]["budget_baht_total"] == 300
