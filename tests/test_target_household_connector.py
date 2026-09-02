from __future__ import annotations

import json

import pytest

from app.connectors.base import ConnectorContext
from app.connectors.target_household import (
    DASHBOARD_URL,
    FAMILY_DASHBOARD_URL,
    INNOVATOR_DASHBOARD_URL,
    SEARCH_URL,
    TargetHouseholdConnector,
    build_candidate_records,
    parse_family_dashboard,
    parse_household_economic_summary,
    parse_innovation_dashboard,
    parse_innovator_dashboard,
    parse_search_page,
)
from app.settings import Settings

PLAN = {
    "driver": "target_household",
    "connector": "app.connectors.target_household:TargetHouseholdConnector",
    "url": SEARCH_URL,
    "query_params": {"page": "$PAGE"},
    "dashboard_year_filters": ["all"],
}


class StubHtmlResponse:
    def __init__(self, html: str):
        self.text = html
        self.content = html.encode("utf-8")


class PageRecorder:
    def __init__(self, pages: dict[int, str], dashboards: dict[str, str] | None = None):
        self.pages = pages
        self.dashboards = dashboards or {}
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url in self.dashboards:
            return StubHtmlResponse(self.dashboards[url]), None
        page = int(kwargs["params"]["page"])
        return StubHtmlResponse(self.pages[page]), None


def search_html(page: int, *, last_page: int, products: list[tuple[str, str]]) -> str:
    cards = []
    for product_id, title in products:
        cards.append(
            f'<a href="https://pmua-apptech.com/product/show/{product_id}" '
            f'class="prod-img-wrap-1x1"></a>'
            f'<a href="https://pmua-apptech.com/product/show/{product_id}" '
            f'class="prod-title" title="{title}">{title}</a>'
        )
    links = [
        f'<a href="https://pmua-apptech.com/search?page={number}" '
        f'data-ci-pagination-page="{number}">{number}</a>'
        for number in range(1, last_page + 1)
    ]
    links.append(
        f'<a href="https://pmua-apptech.com/search?page={last_page}" '
        f'data-ci-pagination-page="{last_page}">Last</a>'
    )
    return "<html><body>" + "".join(cards) + "<nav>" + "".join(links) + "</nav></body></html>"


def innovation_dashboard_html() -> str:
    return """
    <script>
    const provinceData = {"สงขลา":[{"prod_id":"1"},{"prod_id":"2"}],"เชียงใหม่":[{"prod_id":"3"}]};
    </script>
    """


def innovator_dashboard_html() -> str:
    return """
    <script>
    const provData = {
      "สงขลา":{"total_inno":787,"levels":{"1":85,"2":329,"3":250,"4":123},"gen_users":300},
      "เชียงใหม่":{"total_inno":563,"levels":{"1":128,"2":207,"3":168,"4":60},"gen_users":127}
    };
    </script>
    """


def family_dashboard_html() -> str:
    return """
    <section>
      <h3>มูลค่าต้นทุนที่ลดลงรวม</h3><strong>155,478,009 ฿</strong>
      <h3>มูลค่ารายได้ที่เพิ่มขึ้นรวม</h3><strong>844,299,479 ฿</strong>
      <h3>มูลค่ารายได้สุทธิเพิ่มขึ้น (Net)</h3><strong>999,777,488 ฿</strong>
    </section>
    <script>
    const provData = {
      "สงขลา":{
        "total_hh":1377,
        "total_members":1079,
        "total_inno":779,
        "total_gen":300,
        "districts":{"อำเภอเมืองสงขลา":175},
        "business_types":{"เกษตรกร":106}
      }
    };
    </script>
    """


def test_target_household_connector_paginates_public_search_without_network():
    pages = {
        1: search_html(1, last_page=2, products=[("10001", "นวัตกรรมตัวอย่าง ก")]),
        2: search_html(2, last_page=2, products=[("10002", "นวัตกรรมตัวอย่าง ข")]),
    }
    recorder = PageRecorder(
        pages,
        {
            DASHBOARD_URL: innovation_dashboard_html(),
            INNOVATOR_DASHBOARD_URL: innovator_dashboard_html(),
            FAMILY_DASHBOARD_URL: family_dashboard_html(),
        },
    )
    context = ConnectorContext(
        source={"source_id": "f2_target_household"},
        plan=PLAN,
        settings=Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0),
        recorder=recorder,
    )

    records = TargetHouseholdConnector().fetch(context)
    assert [key for key, _ in records[:2]] == ["public_product", "public_product"]
    assert [payload["product_id"] for _, payload in records[:2]] == ["10001", "10002"]
    assert all(payload["as_of"] is None for _, payload in records[:2])
    assert [call[2].get("params", {}).get("page") for call in recorder.calls if call[1] == SEARCH_URL] == [1, 2]
    assert {key for key, _ in records} == {
        "public_product",
        "innovation_dashboard_province",
        "innovator_dashboard_province",
        "household_dashboard_province",
        "household_economic_summary",
    }
    innovator_rows = [payload for key, payload in records if key == "innovator_dashboard_province"]
    assert innovator_rows[0]["total_inno"] == 787
    assert innovator_rows[0]["levels"] == {"1": 85, "2": 329, "3": 250, "4": 123}


def test_target_household_parser_reads_last_page_and_unique_product_ids():
    html = search_html(1, last_page=73, products=[("9285", "อาหารแพะผสมครบส่วน")])
    products, pages = parse_search_page(html)
    assert products == [("9285", "อาหารแพะผสมครบส่วน")]
    assert 73 in pages


def test_target_household_dashboard_parsers_extract_public_aggregates():
    innovation_rows = parse_innovation_dashboard(innovation_dashboard_html())
    innovator_rows = parse_innovator_dashboard(innovator_dashboard_html())
    family_rows = parse_family_dashboard(family_dashboard_html())
    _, economic = parse_household_economic_summary(family_dashboard_html())

    assert innovation_rows[0][1] == {
        "year_filter": "all",
        "province_name_th": "สงขลา",
        "innovation_count": 2,
    }
    assert innovator_rows[0][1]["total_inno"] == 787
    assert innovator_rows[0][1]["gen_users"] == 300
    assert family_rows[0][1]["total_hh"] == 1377
    assert economic["cost_reduced_baht"] == 155478009
    assert economic["income_increased_baht"] == 844299479
    assert economic["net_income_increased_baht"] == 999777488
    assert economic["geography"] == "country"


def test_target_household_fails_closed_on_incomplete_or_duplicate_pagination():
    with pytest.raises(RuntimeError, match="incomplete pagination"):
        build_candidate_records(
            {
                1: search_html(1, last_page=2, products=[("10001", "ก")]),
            }
        )
    with pytest.raises(RuntimeError, match="duplicate product_id=10001"):
        build_candidate_records(
            {
                1: search_html(1, last_page=2, products=[("10001", "ก")]),
                2: search_html(2, last_page=2, products=[("10001", "ข")]),
            }
        )
    with pytest.raises(RuntimeError, match="has no product links"):
        build_candidate_records(
            {
                1: search_html(1, last_page=2, products=[("10001", "ก")]),
                2: (
                    "<html><nav>"
                    '<a href="https://pmua-apptech.com/search?page=2" data-ci-pagination-page="2">2</a>'
                    "</nav></html>"
                ),
            }
        )


@pytest.mark.parametrize("value", [None, "", True, -1, 1.5, "unknown", "1,2", "12 people"])
def test_dashboard_rejects_missing_or_invalid_counts(value):
    payload = {"สงขลา": {"total_inno": value, "gen_users": 0, "levels": {str(n): 0 for n in range(1, 5)}}}
    with pytest.raises(RuntimeError, match="count"):
        parse_innovator_dashboard(f"const provData = {json.dumps(payload)};")


def test_dashboard_preserves_explicit_zero_counts():
    payload = {"สงขลา": {"total_inno": 0, "gen_users": 0, "levels": {str(n): 0 for n in range(1, 5)}}}
    rows = parse_innovator_dashboard(f"const provData = {json.dumps(payload)};")
    assert rows[0][1]["total_inno"] == 0
    zero_money = family_dashboard_html().replace("155,478,009", "0").replace("844,299,479", "0").replace("999,777,488", "0")
    assert parse_household_economic_summary(zero_money)[1]["net_income_increased_baht"] == 0


@pytest.mark.parametrize("html", [
    'const provData = {"สงขลา": {}, "เชียงใหม่": []};',
    'const provData = {"สงขลา": {}, "สงขลา": {}};',
    'const provData = {"สงขลา": {}, " สงขลา ": {}};',
    'const provData = {"": {}};',
    'const provData = {};',
])
def test_dashboard_rejects_partial_or_duplicate_province_schema(html):
    with pytest.raises(RuntimeError):
        parse_innovator_dashboard(html)


def test_dashboard_requires_levels_and_family_count_fields():
    with pytest.raises(RuntimeError, match="levels"):
        parse_innovator_dashboard(innovator_dashboard_html().replace('"4":123', '"5":123'))
    with pytest.raises(RuntimeError, match="count"):
        parse_family_dashboard(family_dashboard_html().replace('"total_hh":1377,', ""))
    with pytest.raises(RuntimeError, match="districts"):
        parse_family_dashboard(family_dashboard_html().replace('"districts":{"อำเภอเมืองสงขลา":175}', '"districts":null'))
    with pytest.raises(RuntimeError, match="province"):
        parse_innovation_dashboard('const provinceData = {"สงขลา":[],"เชียงใหม่":{}};')


@pytest.mark.parametrize("html", ["<html>layout changed</html>", family_dashboard_html().replace("999,777,488 ฿", "missing"), family_dashboard_html() * 2])
def test_economic_dashboard_requires_each_measure_exactly_once(html):
    with pytest.raises(RuntimeError, match="economic dashboard"):
        parse_household_economic_summary(html)


def test_connector_does_not_return_partial_records_when_last_dashboard_is_invalid():
    recorder = PageRecorder(
        {1: search_html(1, last_page=1, products=[("10001", "ตัวอย่าง")])},
        {DASHBOARD_URL: innovation_dashboard_html(), INNOVATOR_DASHBOARD_URL: innovator_dashboard_html(), FAMILY_DASHBOARD_URL: family_dashboard_html().replace("999,777,488 ฿", "missing")},
    )
    context = ConnectorContext(source={"source_id": "f2_target_household"}, plan=PLAN, settings=Settings(_env_file=None), recorder=recorder)
    with pytest.raises(RuntimeError, match="economic dashboard"):
        TargetHouseholdConnector().fetch(context)
