"""Public AppTech product listing and aggregate dashboards.

The live site is a public innovation marketplace, not a household registry.
Serving ingest paginates ``/search?page=N`` (page=1 matches the unqueried
listing) and emits contact-free product IDs. It also reads public dashboard
aggregate pages for AppTech province/year summaries. It does not GET product
detail pages, login, EPMS, or explode ``/dashboard/familydashboard`` into
household rows. Listing count may drift; completeness is advertised pagination,
unique IDs, and non-empty pages.
"""

from __future__ import annotations

import re
from html import unescape
import json

from app.connectors.base import ConnectorContext, DatasetRecord

SEARCH_URL = "https://pmua-apptech.com/search"
DASHBOARD_URL = "https://pmua-apptech.com/dashboard"
INNOVATOR_DASHBOARD_URL = "https://pmua-apptech.com/dashboard/innovatordashboard"
FAMILY_DASHBOARD_URL = "https://pmua-apptech.com/dashboard/familydashboard"
PRODUCT_SHOW_PREFIX = "https://pmua-apptech.com/product/show/"
PRODUCT_HREF_RE = re.compile(r"/product/show/(\d+)", re.I)
PAGE_QUERY_RE = re.compile(r"[?&]page=(\d+)", re.I)
PAGE_ATTR_RE = re.compile(r'data-ci-pagination-page="(\d+)"', re.I)
PROD_TITLE_RE = re.compile(
    r'<a\s+href="[^"]*?/product/show/(\d+)"\s+class="prod-title"\s+title="([^"]*)"',
    re.I,
)
PROV_DATA_RE = re.compile(r"const\s+provData\s*=\s*(\{[\s\S]*?\});", re.I)
PROVINCE_DATA_RE = re.compile(r"const\s+provinceData\s*=\s*(\{[\s\S]*?\});", re.I)
MONEY_RE = re.compile(r"(มูลค่า[^<\n\r]+?)\s*</[^>]+>\s*<[^>]+>\s*([0-9,]+)\s*฿", re.I)


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_int(value: object) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = re.sub(r"[^\d.-]", "", str(value))
    if not text:
        return 0
    return int(float(text))


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


def parse_prov_data(html: str) -> dict[str, dict]:
    match = PROV_DATA_RE.search(html)
    if not match:
        raise RuntimeError("AppTech dashboard provData is missing")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise RuntimeError("AppTech dashboard provData is not valid JSON") from exc
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError("AppTech dashboard provData is empty")
    return {clean_text(key): value for key, value in payload.items() if clean_text(key) and isinstance(value, dict)}


def parse_province_product_data(html: str) -> dict[str, list]:
    match = PROVINCE_DATA_RE.search(html)
    if not match:
        raise RuntimeError("AppTech innovation dashboard provinceData is missing")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise RuntimeError("AppTech innovation dashboard provinceData is not valid JSON") from exc
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError("AppTech innovation dashboard provinceData is empty")
    return {clean_text(key): value for key, value in payload.items() if clean_text(key) and isinstance(value, list)}


def parse_innovation_dashboard(html: str, year_filter: str = "all") -> list[DatasetRecord]:
    rows: list[DatasetRecord] = []
    for province_name, products in parse_province_product_data(html).items():
        rows.append(
            (
                "innovation_dashboard_province",
                {
                    "year_filter": year_filter,
                    "province_name_th": province_name,
                    "innovation_count": len(products),
                },
            )
        )
    return rows


def parse_innovator_dashboard(html: str, year_filter: str = "all") -> list[DatasetRecord]:
    rows: list[DatasetRecord] = []
    for province_name, payload in parse_prov_data(html).items():
        levels = payload.get("levels") if isinstance(payload.get("levels"), dict) else {}
        level_counts = {str(level): parse_int(levels.get(str(level))) for level in range(1, 5)}
        rows.append(
            (
                "innovator_dashboard_province",
                {
                    "year_filter": year_filter,
                    "province_name_th": province_name,
                    "total_inno": parse_int(payload.get("total_inno")),
                    "gen_users": parse_int(payload.get("gen_users")),
                    "levels": level_counts,
                },
            )
        )
    return rows


def parse_family_dashboard(html: str, year_filter: str = "all") -> list[DatasetRecord]:
    rows: list[DatasetRecord] = []
    for province_name, payload in parse_prov_data(html).items():
        rows.append(
            (
                "household_dashboard_province",
                {
                    "year_filter": year_filter,
                    "province_name_th": province_name,
                    "total_hh": parse_int(payload.get("total_hh")),
                    "total_members": parse_int(payload.get("total_members")),
                    "total_inno": parse_int(payload.get("total_inno")),
                    "total_gen": parse_int(payload.get("total_gen")),
                    "districts": payload.get("districts") if isinstance(payload.get("districts"), dict) else {},
                    "business_types": payload.get("business_types") if isinstance(payload.get("business_types"), dict) else {},
                },
            )
        )
    return rows


def parse_household_economic_summary(html: str, year_filter: str = "all") -> DatasetRecord:
    values: dict[str, int] = {}
    for label, raw_value in MONEY_RE.findall(html):
        normalized_label = clean_text(unescape(label))
        amount = parse_int(raw_value)
        if "ต้นทุน" in normalized_label:
            values["cost_reduced_baht"] = amount
        elif "รายได้สุทธิ" in normalized_label:
            values["net_income_increased_baht"] = amount
        elif "รายได้" in normalized_label:
            values["income_increased_baht"] = amount
    return (
        "household_economic_summary",
        {
            "year_filter": year_filter,
            "cost_reduced_baht": values.get("cost_reduced_baht", 0),
            "income_increased_baht": values.get("income_increased_baht", 0),
            "net_income_increased_baht": values.get("net_income_increased_baht", 0),
            "geography": "country",
            "geography_note_th": "AppTech public household dashboard exposes economic totals at national/year scope only.",
        },
    )


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
        records = build_candidate_records(pages)
        records.extend(_fetch_dashboard_aggregates(context))
        return records


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


def _response_text(response) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(response, "content", b"")
    return content.decode("utf-8", "replace") if isinstance(content, (bytes, bytearray)) else str(content)


def _fetch_dashboard_page(context: ConnectorContext, url: str, name: str, year_filter: str = "all") -> str:
    params = None if year_filter == "all" else {"year_filter": year_filter}
    response, _ = context.recorder.request("GET", url, name=name, params=params)
    return _response_text(response)


def _fetch_dashboard_aggregates(context: ConnectorContext) -> list[DatasetRecord]:
    records: list[DatasetRecord] = []
    dashboard_years = list(context.plan.get("dashboard_year_filters") or ["all"])
    for year_filter in dashboard_years:
        suffix = "all" if year_filter == "all" else str(year_filter)
        dashboard_html = _fetch_dashboard_page(context, DASHBOARD_URL, f"innovation_dashboard_{suffix}", str(year_filter))
        records.extend(parse_innovation_dashboard(dashboard_html, str(year_filter)))

        innovator_html = _fetch_dashboard_page(
            context,
            INNOVATOR_DASHBOARD_URL,
            f"innovator_dashboard_{suffix}",
            str(year_filter),
        )
        records.extend(parse_innovator_dashboard(innovator_html, str(year_filter)))

        family_html = _fetch_dashboard_page(context, FAMILY_DASHBOARD_URL, f"family_dashboard_{suffix}", str(year_filter))
        records.extend(parse_family_dashboard(family_html, str(year_filter)))
        records.append(parse_household_economic_summary(family_html, str(year_filter)))
    return records
