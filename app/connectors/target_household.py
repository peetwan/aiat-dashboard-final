"""Public AppTech product listing from pmua-apptech.com/search.

The live site is a public innovation marketplace, not a household registry.
Serving ingest paginates ``/search?page=N`` (page=1 matches the unqueried
listing) and emits contact-free product IDs. It does not GET product detail
pages, login, EPMS, or explode ``/dashboard/familydashboard`` into household
rows. Listing count may drift; completeness is advertised pagination, unique
IDs, and non-empty pages.
"""

from __future__ import annotations

import re
from html import unescape

from app.connectors.base import ConnectorContext, DatasetRecord

SEARCH_URL = "https://pmua-apptech.com/search"
PRODUCT_SHOW_PREFIX = "https://pmua-apptech.com/product/show/"
PRODUCT_HREF_RE = re.compile(r"/product/show/(\d+)", re.I)
PAGE_QUERY_RE = re.compile(r"[?&]page=(\d+)", re.I)
PAGE_ATTR_RE = re.compile(r'data-ci-pagination-page="(\d+)"', re.I)
PROD_TITLE_RE = re.compile(
    r'<a\s+href="[^"]*?/product/show/(\d+)"\s+class="prod-title"\s+title="([^"]*)"',
    re.I,
)


def parse_search_page(html: str) -> tuple[list[tuple[str, str | None]], set[int]]:
    if not isinstance(html, str) or not html.strip():
        raise RuntimeError("target household search page is empty")
    titles: dict[str, str] = {}
    for product_id, raw_title in PROD_TITLE_RE.findall(html):
        title = unescape(raw_title).strip()
        if title:
            titles[product_id] = title
    products: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for product_id in PRODUCT_HREF_RE.findall(html):
        if product_id in seen:
            continue
        seen.add(product_id)
        products.append((product_id, titles.get(product_id)))
    pages = {int(value) for value in PAGE_QUERY_RE.findall(html)}
    pages.update(int(value) for value in PAGE_ATTR_RE.findall(html))
    return products, pages


def build_candidate_records(pages: dict[int, str]) -> list[DatasetRecord]:
    if 1 not in pages:
        raise RuntimeError("target household search is missing page 1")
    last_page: int | None = None
    seen_ids: set[str] = set()
    records: list[DatasetRecord] = []
    for page_number in sorted(pages):
        products, advertised_pages = parse_search_page(pages[page_number])
        advertised_last = max(advertised_pages | {page_number})
        if last_page is None:
            last_page = advertised_last
        elif advertised_last != last_page:
            raise RuntimeError(
                f"target household pagination changed: {last_page} -> {advertised_last}"
            )
        if not products:
            raise RuntimeError(f"target household search page {page_number} has no product links")
        for product_id, title in products:
            if product_id in seen_ids:
                raise RuntimeError(f"target household duplicate product_id={product_id}")
            seen_ids.add(product_id)
            records.append(
                (
                    "public_product",
                    {
                        "product_id": product_id,
                        "source_url": f"{PRODUCT_SHOW_PREFIX}{product_id}",
                        "title": title,
                        "as_of": None,
                    },
                )
            )
    if last_page is None:
        raise RuntimeError("target household search listing is empty")
    missing_pages = [page for page in range(1, last_page + 1) if page not in pages]
    if missing_pages:
        raise RuntimeError(
            "target household incomplete pagination: missing pages "
            + ", ".join(str(page) for page in missing_pages)
        )
    extra_pages = sorted(page for page in pages if page < 1 or page > last_page)
    if extra_pages:
        raise RuntimeError(
            "target household pagination includes unexpected pages "
            + ", ".join(str(page) for page in extra_pages)
        )
    if not records:
        raise RuntimeError("target household search listing is empty")
    return records


class TargetHouseholdConnector:
    driver_name = "target_household"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        url = str(context.plan.get("url") or SEARCH_URL)
        if url != SEARCH_URL:
            raise RuntimeError("target household serving ingest only paginates the public /search listing")
        first_html = _fetch_search_page(context, url, 1)
        _, advertised_pages = parse_search_page(first_html)
        last_page = max(advertised_pages | {1})
        pages = {1: first_html}
        for page_number in range(2, last_page + 1):
            pages[page_number] = _fetch_search_page(context, url, page_number)
        return build_candidate_records(pages)


def _fetch_search_page(context: ConnectorContext, url: str, page_number: int) -> str:
    response, _ = context.recorder.request(
        "GET",
        url,
        name=f"search_page_{page_number:04d}",
        params={"page": page_number},
    )
    text = getattr(response, "text", None)
    if not isinstance(text, str):
        content = getattr(response, "content", b"")
        text = content.decode("utf-8", "replace") if isinstance(content, (bytes, bytearray)) else str(content)
    return text
