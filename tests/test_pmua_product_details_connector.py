"""ทดสอบ PMUA detail แบบ offline ทั้ง parser, completeness และ endpoint allowlist."""
import gzip
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from app.catalog import load_catalog, load_ingestion_plans
from app.connectors.base import ConnectorContext
from app.connectors.pmua_product_details import PmuaProductDetailsConnector, parse_product_detail_html
from app.ingestion import PolicyViolation, ResponseRecorder
from app.settings import Settings
from tools.build_pmua_product_details import build, project_details

DETAIL = '''<meta property="og:title" content="นวัตกรรมตัวอย่าง">
<div class="sidebar-card"><h6>ระดับความพร้อม (TRL)</h6><span>ระดับ 9</span></div>
<div class="content-card"><div class="section-header">ผลลัพธ์และผลกระทบเชิงประจักษ์</div>
<div class="p-4"><h5>ROI (Economic)</h5><div><strong>ตัวชี้วัด:</strong> ลดต้นทุน</div>
<div><strong>ปริมาณ:</strong> 0 บาท</div></div></div>
<h5>ผลลัพธ์ (Outcomes)</h5><ul><li><span>ผลลัพธ์ตัวอย่าง</span><span>0 <small>หน่วย</small></span></li></ul>
<h5>ผลกระทบ (Impacts)</h5><p>ยังไม่รายงาน</p>'''


def listing(product_id, last_page=2):
    return f'<a href="https://pmua-apptech.com/product/show/{product_id}">ตัวอย่าง</a><a href="?page={last_page}" data-ci-pagination-page="{last_page}">Last</a>'


class Recorder:
    def __init__(self, pages=None, details=None):
        self.pages = pages or {1: listing(10001), 2: listing(10002)}
        self.details = details or {}
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append(url)
        if "params" in kwargs:
            text = self.pages[kwargs["params"]["page"]]
        else:
            text = self.details.get(url.rsplit("/", 1)[-1], DETAIL)
            if isinstance(text, Exception):
                raise text
        return httpx.Response(200, text=text, request=httpx.Request(method, url)), None


def fetch(recorder):
    return PmuaProductDetailsConnector().fetch(ConnectorContext(
        source={"source_id": "f4_pmua_product_details"},
        plan={"detail_retries": 1}, settings=Settings(max_records_per_source=1), recorder=recorder,
    ))


def test_connector_collects_every_detail_without_truncating():
    rows = fetch(Recorder())
    assert [row[1]["product_id"] for row in rows] == [10001, 10002]
    assert all(key == "public_product_detail" and row["as_of"] is None for key, row in rows)
    row = rows[0][1]
    assert row["empirical_evidence"][0]["quantity_text"] == "0 บาท"
    assert row["empirical_evidence"][0]["status"] == "reported"
    assert row["empirical_evidence"][1]["status"] == "not_reported"
    assert row["outcomes"][0]["value"] == 0
    assert row["evidence_status"] == "partial"


@pytest.mark.parametrize("pages", [
    {1: listing(10001), 2: listing(10001)},
    {1: listing(10001), 2: listing(10002, 3)},
    {1: listing(10001), 2: '<a href="?page=2">2</a>'},
])
def test_connector_rejects_duplicate_missing_or_changing_pages(pages):
    with pytest.raises(RuntimeError):
        fetch(Recorder(pages=pages))


@pytest.mark.parametrize("detail", [
    "<html><h1>Login</h1></html>",
    DETAIL + '<meta property="og:url" content="https://pmua-apptech.com/product/show/99999">',
    httpx.ConnectError("fixture failure"),
])
def test_connector_fails_the_run_if_any_detail_is_invalid(detail):
    with pytest.raises((RuntimeError, httpx.RequestError)):
        fetch(Recorder(details={"10002": detail}))


def test_generated_numeric_endpoint_allowlist_stays_scoped():
    source = next(s for s in load_catalog()["sources"] if s["source_id"] == "f4_pmua_product_details")
    recorder = object.__new__(ResponseRecorder)
    recorder.allowed_endpoints = [ResponseRecorder._endpoint_rule(e) for e in source["endpoints"]]
    assert recorder._request_is_allowed("GET", "https://pmua-apptech.com/product/show/10001", None)
    for url in ("https://other.invalid/product/show/10001", "https://pmua-apptech.com/product/show/login",
                "https://pmua-apptech.com/product/show/10001/edit", "https://pmua-apptech.com/product/show/10001?edit=1"):
        assert not recorder._request_is_allowed("GET", url, None)
    assert not recorder._request_is_allowed("POST", "https://pmua-apptech.com/product/show/10001", None)
    from tools.build_source_catalog import load_plan_endpoints
    plan = load_ingestion_plans()["sources"]["f4_pmua_product_details"]
    assert load_plan_endpoints(source["source_id"], plan, source["cloud_policy"], source["acquisition_mode"]) == source["endpoints"]
    with pytest.raises(PolicyViolation):
        ResponseRecorder._endpoint_rule({"url": "https://example.invalid/{id}", "path_template": "/{id}"})


def test_publication_preserves_values_and_requires_complete_valid_evidence(tmp_path):
    row = parse_product_detail_html(DETAIL, 10001, "https://pmua-apptech.com/product/show/10001")
    row.update(http_status=200, fetched_at="2026-09-05T00:00:00Z", fetch_error="")
    projected = project_details([row], expected_count=1)[0]
    for field in ("trl_level", "empirical_evidence", "outcomes", "impacts", "evidence_status"):
        assert projected[field] == row[field]
    with pytest.raises(ValueError, match="duplicated"):
        project_details([row, row], expected_count=2)
    with pytest.raises(ValueError, match="count"):
        project_details([row], expected_count=2)
    with pytest.raises(ValueError, match="failed detail"):
        project_details([{**row, "http_status": 404}], expected_count=1)
    raw = gzip.compress(json.dumps(row).encode())
    (tmp_path / "product_details.jsonl.gz").write_bytes(raw)
    (tmp_path / "manifest.json").write_text(json.dumps({
        "source_id": "f4_pmua_product_details", "run_id": "20260905T000000Z", "fetched_at": row["fetched_at"],
        "datasets": [{"file": "product_details.jsonl.gz", "row_count": 1, "sha256": hashlib.sha256(raw).hexdigest()}],
    }))
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    build(tmp_path, first, expected_count=1)
    build(tmp_path, second, expected_count=1)
    assert first.read_bytes() == second.read_bytes()
    (tmp_path / "product_details.jsonl.gz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        build(tmp_path, second, expected_count=1)
