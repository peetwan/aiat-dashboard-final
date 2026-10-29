"""บพท.'s slide figures shown beside ours (publish._official): every row must point at a published measure, sit in the
group that matches whether we have a value, and keep its value, unit, date and citations."""

from __future__ import annotations

import copy
import json

import pytest

from tools.f2.publish import CONFIG, _official

# Typed from the slide (ฝ่าย 2, ข้อมูล ณ วันที่ 30 กันยายน 2568) and the agreed mapping, not read from config.json:
# id: (value, unit, group, our measures)
SLIDE = {
    "target_provinces": (69, "จังหวัด", "different", ["K01A"]),
    "cultural_areas": (316, "แห่ง", "related", ["K01B"]),
    "community_innovators": (23753, "คน", "related", ["K02", "C02_COMMUNITY"]),
    "cultural_activities": (2089, "ครั้ง", "different", ["K03"]),
    "ready_innovations": (1739, "นวัตกรรม", "related", ["K04", "C04_LISTED"]),
    "cultural_shops": (1813, "ร้านค้า", "different", ["K05"]),
    "cultural_entrepreneurs": (8028, "คน", "unavailable", ["K06"]),
    "cultural_products": (1932, "รายการ", "different", ["K07"]),
    "community_businesses": (3650, "ธุรกิจชุมชน", "unavailable", ["K08"]),
    "local_employment": (10315, "คนต่อเดือน", "related", ["K09"]),
    "local_income": (212.5, "ล้านบาทต่อเดือน", "different", ["K10"]),
    "industry_clusters": (29, "คลัสเตอร์", "unavailable", ["K11A", "K11B"]),
    "cultural_map_items": (5000, "รายการ", "related", ["K12"]),
}


def _config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def test_the_configured_figures_are_the_slide():
    out = _official(_config())
    assert set(out) == {"source_th", "as_of", "groups", "rows"}
    assert out["as_of"] == "2025-09-30"
    assert [g["id"] for g in out["groups"]] == ["related", "different", "unavailable"]
    assert {r["id"]: (r["value"], r["unit_th"], r["group"], r["measure_ids"]) for r in out["rows"]} == SLIDE
    # the clusters figure is two quantities; the province count must not be lost
    assert next(r for r in out["rows"] if r["id"] == "industry_clusters")["qualifier_th"] == "ใน 34 จังหวัด"


@pytest.mark.parametrize("change, message", [
    (lambda o: o["rows"][0].update(measure_ids=["K99"]), "unknown measures"),
    (lambda o: o["rows"][0].update(measure_ids=[]), "names no measure"),
    (lambda o: o["rows"][0].update(group="nowhere"), "unknown group"),
    # K06 has no value, so its row cannot sit outside "unavailable", and a computed measure cannot sit inside it
    (lambda o: o["rows"][6].update(group="related"), "does not match"),
    (lambda o: o["rows"][12].update(group="unavailable"), "does not match"),
    (lambda o: o["rows"][0].update(measure_ids=["K01A", "K06"]), "does not match"),  # one of two has no value
    (lambda o: o["rows"][0].update(value=0), "lacks"),
    (lambda o: o["rows"][0].update(value=True), "lacks"),  # would show as 1
    (lambda o: o["rows"][0].update(unit_th=""), "lacks"),
    (lambda o: o["rows"][0].update(published=[{"where_th": "", "period_th": None}]), "lacks"),
    (lambda o: o["rows"].append(dict(o["rows"][0])), "repeated"),
    (lambda o: o.update(source_th=" "), "where the figures come from"),
])
def test_rows_that_would_mislead_stop_publish(change, message):
    config = copy.deepcopy(_config())
    assert config["official_figures"]["rows"][6]["id"] == "cultural_entrepreneurs"
    assert config["official_figures"]["rows"][12]["id"] == "cultural_map_items"
    change(config["official_figures"])
    with pytest.raises(SystemExit, match=message):
        _official(config)


def test_the_as_of_date_must_be_a_real_day():
    config = copy.deepcopy(_config())
    config["official_figures"]["as_of"] = "30 ก.ย. 68"
    with pytest.raises(ValueError):
        _official(config)
