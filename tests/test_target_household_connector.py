from __future__ import annotations

import pytest

from app.connectors.base import ConnectorContext
from app.connectors.target_household import (
    SEARCH_URL,
    TargetHouseholdConnector,
    build_candidate_records,
    parse_search_page,
)
from app.settings import Settings

PLAN = {
    "driver": "target_household",
    "connector": "app.connectors.target_household:TargetHouseholdConnector",
    "url": SEARCH_URL,
    "query_params": {"page": "$PAGE"},
}


class StubHtmlResponse:
    def __init__(self, html: str):
        self.text = html
        self.content = html.encode("utf-8")


class PageRecorder:
    def __init__(self, pages: dict[int, str]):
        self.pages = pages
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
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


def test_target_household_connector_paginates_public_search_without_network():
    pages = {
        1: search_html(1, last_page=2, products=[("10001", "นวัตกรรมตัวอย่าง ก")]),
        2: search_html(2, last_page=2, products=[("10002", "นวัตกรรมตัวอย่าง ข")]),
    }
    recorder = PageRecorder(pages)
    context = ConnectorContext(
        source={"source_id": "f2_target_household"},
        plan=PLAN,
        settings=Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0),
        recorder=recorder,
    )

    records = TargetHouseholdConnector().fetch(context)
    assert [key for key, _ in records] == ["public_product", "public_product"]
    assert [payload["product_id"] for _, payload in records] == ["10001", "10002"]
    assert all(payload["as_of"] is None for _, payload in records)
    assert [call[2]["params"]["page"] for call in recorder.calls] == [1, 2]
    assert all(call[1] == SEARCH_URL for call in recorder.calls)


def test_target_household_parser_reads_last_page_and_unique_product_ids():
    html = search_html(1, last_page=73, products=[("9285", "อาหารแพะผสมครบส่วน")])
    products, pages = parse_search_page(html)
    assert products == [("9285", "อาหารแพะผสมครบส่วน")]
    assert 73 in pages


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
