from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.connectors.base import ConnectorContext, DatasetRecord


LIST_URL = "https://clig.oas.psu.ac.th/api/project/search_project"
DETAIL_URL_TEMPLATE = "https://clig.oas.psu.ac.th/iframe/project/project_info?id={project_id}"
DEFAULT_KEYWORD = ""
DEFAULT_YEAR = ""
DEFAULT_MAX_PAGES = 500
POLICY_CANDIDATE_KEYWORDS = (
    "อปท.",
    "อปท",
    "องค์กรปกครองส่วนท้องถิ่น",
    "องค์การบริหารส่วน",
    "เทศบาล",
    "นโยบาย",
    "ข้อเสนอเชิงนโยบาย",
    "กลไก",
    "มาตรการ",
)


@dataclass(frozen=True)
class ParsedPage:
    projects: list[dict[str, Any]]
    page_numbers: list[int]
    no_data: bool


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def parse_int(value: str | None) -> int | None:
    text = clean_text(value)
    if not text or text == "-":
        return None
    digits = re.sub(r"[^\d-]", "", text)
    if not digits:
        return None
    return int(digits)


def parse_money(value: str | None) -> float | None:
    text = clean_text(value)
    if not text or text == "-":
        return None
    normalized = re.sub(r"[^\d.-]", "", text)
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def detail_url(project_id: str) -> str:
    return DETAIL_URL_TEMPLATE.format(project_id=quote(project_id, safe=""))


def parse_project_list(html: str) -> ParsedPage:
    soup = BeautifulSoup(html, "html.parser")
    no_data = "ไม่พบข้อมูล" in soup.get_text(" ", strip=True)
    rows: list[dict[str, Any]] = []
    for tr in soup.select("table tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 11:
            continue
        link = cells[3].select_one("a.btn-dt[href-val]")
        if link is None:
            continue
        project_id = clean_text(link.get("href-val"))
        title = clean_text(cells[3].get("title") or link.get_text(" ", strip=True))
        row = {
            "row_number": parse_int(cells[0].get_text(" ", strip=True)),
            "contract_no": clean_text(cells[1].get_text(" ", strip=True)),
            "fiscal_year": clean_text(cells[2].get_text(" ", strip=True)),
            "project_title": title,
            "project_id": project_id,
            "budget_text": clean_text(cells[4].get_text(" ", strip=True)),
            "budget_baht": parse_money(cells[4].get_text(" ", strip=True)),
            "project_type": clean_text(cells[5].get_text(" ", strip=True)),
            "status": clean_text(cells[6].get_text(" ", strip=True)),
            "area_count": parse_int(cells[7].get_text(" ", strip=True)),
            "cooperation_count": parse_int(cells[8].get_text(" ", strip=True)),
            "product_count": parse_int(cells[9].get_text(" ", strip=True)),
            "link_count": parse_int(cells[10].get_text(" ", strip=True)),
            "detail_url": detail_url(project_id),
        }
        rows.append(row)

    page_numbers = []
    for link in soup.select(".page-link[href-val]"):
        number = parse_int(link.get("href-val"))
        if number is not None:
            page_numbers.append(number)
    return ParsedPage(projects=rows, page_numbers=sorted(set(page_numbers)), no_data=no_data)


def _detail_table_values(soup: BeautifulSoup) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for tr in soup.select("table tr"):
        th = tr.find("th")
        td = tr.find("td")
        if th is None or td is None:
            continue
        label = clean_text(th.get_text(" ", strip=True))
        if not label:
            continue
        if label == "ชื่อ-นามสกุล (ภาษาไทย)":
            values["researcher_name_th"] = clean_text(td.get_text(" ", strip=True))
        elif label == "ชื่อ-นามสกุล (ภาษาอังกฤษ)":
            values["researcher_name_en"] = clean_text(td.get_text(" ", strip=True))
        elif label == "ตำแหน่ง":
            values["researcher_position"] = clean_text(td.get_text(" ", strip=True))
        elif label == "หน่วยงาน":
            values["lead_organization"] = clean_text(td.get_text(" ", strip=True))
        elif label == "บทคัดย่อ (ภาษาไทย)":
            values["abstract_th"] = clean_text(td.get_text(" ", strip=True))
        elif label == "Abstract":
            values["abstract_en"] = clean_text(td.get_text(" ", strip=True))
        elif label == "งบประมาณ":
            budget_text = clean_text(td.get_text(" ", strip=True))
            values["detail_budget_text"] = budget_text
            values["detail_budget_baht"] = parse_money(budget_text)
        elif label == "เอกสารไฟล์โครงการ":
            values["file_labels"] = [
                clean_text(anchor.get_text(" ", strip=True))
                for anchor in td.find_all("a")
                if clean_text(anchor.get_text(" ", strip=True))
            ]
    return values


def parse_project_detail(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = clean_text(soup.select_one("h5.card-label").get_text(" ", strip=True)) if soup.select_one("h5.card-label") else ""
    values = _detail_table_values(soup)
    if title:
        values["detail_title"] = title
    return values


def is_policy_candidate(project: dict[str, Any]) -> bool:
    text = " ".join(
        str(project.get(key) or "")
        for key in (
            "project_title",
            "abstract_th",
            "abstract_en",
            "status",
            "lead_organization",
        )
    )
    return any(keyword in text for keyword in POLICY_CANDIDATE_KEYWORDS)


def candidate_keywords(project: dict[str, Any]) -> list[str]:
    text = " ".join(
        str(project.get(key) or "")
        for key in (
            "project_title",
            "abstract_th",
            "abstract_en",
            "status",
            "lead_organization",
        )
    )
    return [keyword for keyword in POLICY_CANDIDATE_KEYWORDS if keyword in text]


def candidate_record(project: dict[str, Any]) -> dict[str, Any]:
    row = dict(project)
    row["candidate_keywords"] = candidate_keywords(project)
    row["candidate_basis"] = "keyword_match_local_government_policy_mechanism_measure"
    return row


class CligProjectsConnector:
    driver_name = "clig_projects"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        list_url = context.plan.get("list_url", LIST_URL)
        detail_template = context.plan.get("detail_url_template", DETAIL_URL_TEMPLATE)
        keyword = context.plan.get("project_name", DEFAULT_KEYWORD)
        year = context.plan.get("project_year", DEFAULT_YEAR)
        max_pages = int(context.plan.get("max_pages", DEFAULT_MAX_PAGES))
        expected_projects = context.plan.get("catalog_expected_record_count")
        expected_candidates = context.plan.get("expected_policy_candidate_count")
        for label, expected, minimum in (("projects", expected_projects, 1), ("policy_candidates", expected_candidates, 0)):
            if expected is not None and (type(expected) is not int or expected < minimum):
                raise ValueError(f"CLIG {label} expected count must be an integer >= {minimum}")

        projects: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        page = 1
        while page <= max_pages:
            response, _ = context.recorder.request(
                "POST",
                list_url,
                name=f"clig_project_list_page_{page}",
                data={
                    "project_name": keyword,
                    "project_year": year,
                    "page": str(page),
                },
            )
            parsed = parse_project_list(response.text)
            if parsed.no_data or not parsed.projects:
                break
            for row in parsed.projects:
                project_id = str(row.get("project_id") or "")
                if not project_id:
                    raise RuntimeError("CLIG project row has no project_id")
                if project_id in seen_ids:
                    raise RuntimeError(f"CLIG duplicate project_id={project_id}")
                seen_ids.add(project_id)
                detail_response, _ = context.recorder.request(
                    "GET",
                    detail_template.format(project_id=quote(project_id, safe="")),
                    name=f"clig_project_detail_{project_id}",
                )
                row.update(parse_project_detail(detail_response.text))
                row["source_url"] = "https://clig.oas.psu.ac.th/project/search_project"
                row["list_endpoint_url"] = list_url
                row["fetched_at"] = utc_now_iso()
                projects.append(row)
            if not parsed.page_numbers or page >= max(parsed.page_numbers):
                break
            page += 1

        if page > max_pages:
            raise RuntimeError("CLIG pagination exceeded max_pages before completion")
        if not projects:
            raise RuntimeError("CLIG project connector fetched zero projects")
        if expected_projects is not None and len(seen_ids) != expected_projects:
            raise RuntimeError(f"CLIG projects count mismatch: expected {expected_projects}, got {len(seen_ids)}")
        candidates = [candidate_record(row) for row in projects if is_policy_candidate(row)]
        if expected_candidates is not None and len(candidates) != expected_candidates:
            raise RuntimeError(f"CLIG policy_candidates count mismatch: expected {expected_candidates}, got {len(candidates)}")
        records: list[DatasetRecord] = [("projects", row) for row in projects]
        records.extend(("policy_candidates", row) for row in candidates)
        return records
