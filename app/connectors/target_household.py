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

import json
import math
import re
from html import unescape

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
    # A missing value is a schema failure, not an observed zero.
    if type(value) is int and value >= 0:
        return value
    if type(value) is float and math.isfinite(value) and value >= 0 and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", value.strip()):
        return int(value.strip().replace(",", ""))
    raise RuntimeError("AppTech dashboard count is missing or is not a non-negative integer")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeError("AppTech dashboard contains a duplicate JSON key")
        result[key] = value
    return result


def _dashboard_object(html: str, pattern: re.Pattern, name: str, row_type: type) -> dict:
    match = pattern.search(html)
    if not match:
        raise RuntimeError(f"AppTech dashboard {name} is missing")
    try:
        payload = json.loads(match.group(1), object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AppTech dashboard {name} is not valid JSON") from exc
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError(f"AppTech dashboard {name} is empty")
    result: dict = {}
    for key, value in payload.items():
        name_key = clean_text(key)
        if not name_key or name_key in result or not isinstance(value, row_type):
            raise RuntimeError(f"AppTech dashboard {name} has an invalid or duplicate province")
        result[name_key] = value
    return result


def _count_map(value: object, name: str) -> dict[str, int]:
    if not isinstance(value, dict) or any(not clean_text(key) for key in value):
        raise RuntimeError(f"AppTech dashboard {name} is missing or invalid")
    return {key: parse_int(count) for key, count in value.items()}


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
    return _dashboard_object(html, PROV_DATA_RE, "provData", dict)


def parse_province_product_data(html: str) -> dict[str, list]:
    return _dashboard_object(html, PROVINCE_DATA_RE, "provinceData", list)


def parse_innovation_dashboard(html: str, year_filter: str = "all") -> list[DatasetRecord]:
    rows: list[DatasetRecord] = []
    for province_name, products in parse_province_product_data(html).items():
        if any(not isinstance(product, dict) or not product for product in products):
            raise RuntimeError("AppTech innovation dashboard contains an invalid product")
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
        level_counts = _count_map(payload.get("levels"), "levels")
        if set(level_counts) != {"1", "2", "3", "4"}:
            raise RuntimeError("AppTech innovator dashboard must contain levels 1-4")
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
                    "districts": _count_map(payload.get("districts"), "districts"),
                    "business_types": _count_map(payload.get("business_types"), "business_types"),
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
            key = "cost_reduced_baht"
        elif "รายได้สุทธิ" in normalized_label:
            key = "net_income_increased_baht"
        elif "รายได้" in normalized_label:
            key = "income_increased_baht"
        else:
            continue
        if key in values:
            raise RuntimeError("AppTech economic dashboard contains a duplicate measure")
        values[key] = amount
    if len(values) != 3:
        raise RuntimeError("AppTech economic dashboard must contain all three monetary measures")
    return (
        "household_economic_summary",
        {
            "year_filter": year_filter,
            **values,
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
