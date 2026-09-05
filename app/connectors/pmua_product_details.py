"""Public PMUA AppTech product-detail connector and parser."""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import ConnectorContext, DatasetRecord
from app.connectors.target_household import (
    SEARCH_URL,
    build_candidate_records,
    parse_search_page,
)


PRODUCT_SHOW_PREFIX = "https://pmua-apptech.com/product/show/"
DETAIL_URL_TEMPLATE = f"{PRODUCT_SHOW_PREFIX}{{product_id}}"
EXPECTED_METRICS = (("ROI", "Economic"), ("SROI", "Social"))
PLACEHOLDER_VALUES = {"", "-"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def parse_number(value: str) -> int | float | str | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = text.replace(",", "")
    try:
        numeric = float(normalized)
    except ValueError:
        return text
    return int(numeric) if numeric.is_integer() else numeric


def _is_missing(value: str, *, zero_is_missing: bool = False) -> bool:
    text = clean_text(value)
    return text in PLACEHOLDER_VALUES or (zero_is_missing and text in {"0", "0.0", "0.00"})


def _find_heading(soup: BeautifulSoup, label: str):
    return next(
        (
            heading
            for heading in soup.find_all(["h5", "h6"])
            if label in clean_text(heading.get_text(" ", strip=True))
        ),
        None,
    )


def _parse_metric_section(soup: BeautifulSoup, heading_label: str) -> list[dict[str, Any]]:
    heading = _find_heading(soup, heading_label)
    if not heading:
        return []
    metric_list = heading.find_next(["ul", "h5", "h6"])
    if not metric_list or metric_list.name != "ul":
        return []

    rows: list[dict[str, Any]] = []
    for item in metric_list.find_all("li", recursive=False):
        spans = item.find_all("span", recursive=False)
        if not spans:
            continue
        label = clean_text(spans[0].get_text(" ", strip=True))
        value_node = spans[-1]
        unit_node = value_node.find("small")
        unit = clean_text(unit_node.get_text(" ", strip=True) if unit_node else "")
        raw_value = clean_text(value_node.get_text(" ", strip=True))
        value_text = raw_value
        if unit and raw_value.endswith(unit):
            value_text = clean_text(raw_value[: -len(unit)])
        if _is_missing(label) and _is_missing(value_text) and _is_missing(unit):
            continue
        numeric = parse_number(value_text)
        rows.append(
            {
                "label": label,
                "value": numeric if isinstance(numeric, (int, float)) else None,
                "value_text": value_text,
                "unit": unit,
                "evidence_type": "source_reported",
            }
        )
    return rows


def _metric_card_value(card: BeautifulSoup, label: str) -> str:
    strong = card.find("strong", string=lambda value: value and label in value)
    if not strong or not strong.parent:
        return ""
    text = clean_text(strong.parent.get_text(" ", strip=True))
    return clean_text(text.replace(clean_text(strong.get_text(" ", strip=True)), "", 1))


def _parse_empirical_evidence(soup: BeautifulSoup) -> list[dict[str, Any]]:
    section_header = next(
        (
            node
            for node in soup.find_all(class_="section-header")
            if "ผลลัพธ์และผลกระทบเชิงประจักษ์" in clean_text(node.get_text(" ", strip=True))
        ),
        None,
    )
    section = section_header.find_parent("div", class_="content-card") if section_header else None
    metrics: list[dict[str, Any]] = []
    for metric, domain in EXPECTED_METRICS:
        heading = next(
            (
                node
                for node in section.find_all("h5")
                if re.search(rf"\b{metric}\s*\(", node.get_text(" ", strip=True), re.IGNORECASE)
            ),
            None,
        ) if section else None
        card = heading.find_parent("div", class_=lambda value: value and "p-4" in value.split()) if heading else None
        indicator_text = _metric_card_value(card, "ตัวชี้วัด:") if card else ""
        quantity_text = _metric_card_value(card, "ปริมาณ:") if card else ""
        status = "reported"
        if _is_missing(indicator_text) and _is_missing(quantity_text, zero_is_missing=True):
            status = "not_reported"
        metrics.append(
            {
                "metric": metric,
                "domain": domain,
                "indicator_text": indicator_text,
                "quantity_text": quantity_text,
                "status": status,
                "evidence_type": "source_reported",
            }
        )
    return metrics


def _evidence_status(
    empirical_evidence: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    impacts: list[dict[str, Any]],
) -> str:
    sections = [
        any(item.get("status") == "reported" for item in empirical_evidence if item.get("metric") == metric)
        for metric, _ in EXPECTED_METRICS
    ]
    sections.extend([bool(outcomes), bool(impacts)])
    if all(sections):
        return "complete"
    if any(sections):
        return "partial"
    return "not_reported"


def parse_product_detail_html(html: str, product_id: int | str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = clean_text(str(og_title["content"]))
    if not title:
        h1 = soup.find(["h1", "h2", "h3"])
        title = clean_text(h1.get_text(" ", strip=True) if h1 else "")

    trl_level = None
    trl_status = ""
    trl_header = soup.find(string=lambda value: value and "ระดับความพร้อม (TRL)" in value)
    if trl_header:
        trl_card = trl_header.find_parent(class_="sidebar-card")
        if trl_card:
            level_text = clean_text(trl_card.find(string=re.compile(r"ระดับ\s*\d+")) or "")
            level_match = re.search(r"ระดับ\s*(\d+)", level_text)
            if level_match:
                trl_level = int(level_match.group(1))
            status_span = trl_card.find("span", class_=lambda value: value and "text-dark" in value)
            trl_status = clean_text(status_span.get_text(" ", strip=True) if status_span else "")

    latitude = longitude = None
    latlng = soup.find(id="viewMapLatLngText")
    if latlng:
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", latlng.get_text(" ", strip=True))
        if match:
            latitude = float(match.group(1))
            longitude = float(match.group(2))

    outcomes = _parse_metric_section(soup, "ผลลัพธ์ (Outcomes)")
    impacts = _parse_metric_section(soup, "ผลกระทบ (Impacts)")
    empirical_evidence = _parse_empirical_evidence(soup)
    return {
        "product_id": int(product_id),
        "source_url": source_url,
        "title": title,
        "trl_level": trl_level,
        "trl_status": trl_status,
        "latitude": latitude,
        "longitude": longitude,
        "empirical_evidence": empirical_evidence,
        "outcomes": outcomes,
        "impacts": impacts,
        "evidence_status": _evidence_status(empirical_evidence, outcomes, impacts),
        "raw_html_bytes": len(html.encode("utf-8")),
        "raw_html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
    }


def _fetch_detail_with_retry(context: ConnectorContext, url: str, name: str):
    for attempt in range(3):
        try:
            response, _ = context.recorder.request("GET", url, name=name)
            return response
        except httpx.HTTPStatusError as error:
            status = error.response.status_code if error.response is not None else None
            if status not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
        except httpx.RequestError:
            if attempt == 2:
                raise
        time.sleep(min(2**attempt, 6))
    raise RuntimeError(f"failed to fetch PMUA detail page: {url}")


class PmuaProductDetailsConnector:
    driver_name = "f4_pmua_product_details"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        list_url = str(context.plan.get("list_url") or SEARCH_URL)
        detail_template = str(context.plan.get("detail_url_template") or DETAIL_URL_TEMPLATE)
        first_response, _ = context.recorder.request(
            "GET",
            list_url,
            name="pmua_product_detail_search_page_0001",
            params={"page": 1},
        )
        _, advertised_pages = parse_search_page(first_response.text)
        last_page = max(advertised_pages | {1})
        pages = {1: first_response.text}
        for page_number in range(2, last_page + 1):
            response, _ = context.recorder.request(
                "GET",
                list_url,
                name=f"pmua_product_detail_search_page_{page_number:04d}",
                params={"page": page_number},
            )
            pages[page_number] = response.text

        catalogue_records = build_candidate_records(pages)
        if not catalogue_records:
            raise RuntimeError("PMUA product-detail connector found zero products")

        details: list[DatasetRecord] = []
        fetched_at = utc_now_iso()
        for index, (_, catalogue_row) in enumerate(catalogue_records, start=1):
            product_id = str(catalogue_row["product_id"])
            source_url = detail_template.format(product_id=product_id)
            response = _fetch_detail_with_retry(
                context,
                source_url,
                f"pmua_product_detail_{index:04d}_{product_id}",
            )
            row = parse_product_detail_html(response.text, product_id, source_url)
            if not row["title"]:
                row["title"] = catalogue_row.get("title") or ""
            row["http_status"] = response.status_code
            row["fetched_at"] = fetched_at
            details.append(("public_product_detail", row))
        return details
