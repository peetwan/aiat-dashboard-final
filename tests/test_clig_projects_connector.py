from __future__ import annotations

import gzip
import io
import json
from pathlib import Path

import pytest
import httpx
from urllib.parse import parse_qs

from app.connectors.clig_projects import (
    CligProjectsConnector,
    candidate_record,
    is_policy_candidate,
    parse_project_detail,
    parse_project_list,
)
from app.connectors.base import ConnectorContext
from app.settings import Settings
from app.ingestion import IngestionFetchError, IngestionPipeline, ResponseRecorder, PolicyViolation
from app.catalog import load_catalog, load_ingestion_plans
from tools.evidence_store import StoreConfig, push_run
from tools.scrape_clig_projects import write_jsonl, write_manifest_input


LIST_HTML = """
<div class="table-responsive">
<table>
<tr><th>header</th></tr>
<tr>
  <td class="text-center">1</td>
  <td class="text-center">A13F660055</td>
  <td class="text-center">2566</td>
  <td class="text-truncate" title="การพัฒนานโยบายท้องถิ่นขององค์กรปกครองส่วนท้องถิ่น">
    <a href="Javascript:;" href-val="ZItoamyI" class="btn-dt">title</a>
  </td>
  <td class="text-center">2,027,400.00</td>
  <td class="text-center">-</td>
  <td class="text-center">ปิดโครงการ 18</td>
  <td class="text-center">8</td>
  <td class="text-center">1</td>
  <td class="text-center">0</td>
  <td class="text-center">0</td>
</tr>
</table>
<a class="page-link active" href-val="1">1</a>
<a class="page-link page" href-val="2">2</a>
</div>
"""

DETAIL_HTML = """
<html><body>
<h5 class="card-label">การพัฒนานโยบายท้องถิ่นขององค์กรปกครองส่วนท้องถิ่น</h5>
<table>
<tr><th>ชื่อ-นามสกุล (ภาษาไทย)</th><td>ผู้วิจัยตัวอย่าง</td></tr>
<tr><th>ชื่อ-นามสกุล (ภาษาอังกฤษ)</th><td>Example Researcher</td></tr>
<tr><th>ตำแหน่ง</th><td>นักวิจัย</td></tr>
<tr><th>สัญชาติ</th><td>ไทย</td></tr>
<tr><th>หน่วยงาน</th><td>มหาวิทยาลัยสงขลานครินทร์ คณะวิทยาการจัดการ</td></tr>
<tr><th>บทคัดย่อ (ภาษาไทย)</th><td>มีมาตรการและกลไกสำหรับ อปท.</td></tr>
<tr><th>Abstract</th><td>Policy innovation for local government.</td></tr>
<tr><th>งบประมาณ</th><td>2,027,400.00 บาท</td></tr>
<tr><th>เอกสารไฟล์โครงการ</th><td><a>finalreport.pdf</a></td></tr>
</table>
</body></html>
"""

EMPTY_HTML = '<table><tr><td class="text-danger" colspan="11">**ไม่พบข้อมูล**</td></tr></table>'


class TextResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class SequenceRecorder:
    def __init__(self, texts: list[str]) -> None:
        self.texts = iter(texts)
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return TextResponse(next(self.texts)), Path("fixture.html")


def context_for(recorder: SequenceRecorder) -> ConnectorContext:
    return ConnectorContext(
        source={"source_id": "clig_projects"},
        plan={
            "list_url": "https://clig.oas.psu.ac.th/api/project/search_project",
            "detail_url_template": "https://clig.oas.psu.ac.th/iframe/project/project_info?id={project_id}",
            "max_pages": 5,
        },
        settings=Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0),
        recorder=recorder,
    )


def test_parse_project_list_and_detail_extract_safe_fields() -> None:
    parsed = parse_project_list(LIST_HTML)
    assert parsed.page_numbers == [1, 2]
    assert parsed.projects[0]["contract_no"] == "A13F660055"
    assert parsed.projects[0]["budget_baht"] == 2027400.0
    assert parsed.projects[0]["area_count"] == 8

    detail = parse_project_detail(DETAIL_HTML)
    assert detail["lead_organization"] == "มหาวิทยาลัยสงขลานครินทร์ คณะวิทยาการจัดการ"
    assert detail["abstract_th"] == "มีมาตรการและกลไกสำหรับ อปท."
    assert detail["detail_budget_baht"] == 2027400.0
    assert detail["file_labels"] == ["finalreport.pdf"]
    assert "ชื่อ-นามสกุล (ภาษาไทย)" not in detail
    assert detail["researcher_name_th"] == "ผู้วิจัยตัวอย่าง"
    assert detail["researcher_name_en"] == "Example Researcher"
    assert detail["researcher_position"] == "นักวิจัย"
    assert "สัญชาติ" not in detail


def test_clig_researcher_attribution_survives_candidate_preparation() -> None:
    from app.connector_contracts import load_runtime_connector_contract, prepare_contract_records

    recorder = SequenceRecorder([LIST_HTML, DETAIL_HTML, EMPTY_HTML])
    records = CligProjectsConnector().fetch(context_for(recorder))
    prepared = prepare_contract_records(load_runtime_connector_contract("clig_projects"), records)
    assert len(prepared) == 2
    assert all(row.payload["researcher_name_th"] == "ผู้วิจัยตัวอย่าง" for row in prepared)


def test_connector_follows_detail_ids_and_stops_on_empty_page() -> None:
    recorder = SequenceRecorder([LIST_HTML, DETAIL_HTML, EMPTY_HTML])
    records = CligProjectsConnector().fetch(context_for(recorder))

    assert [call[0] for call in recorder.calls] == ["POST", "GET", "POST"]
    assert recorder.calls[0][2]["data"] == {"project_name": "", "project_year": "", "page": "1"}
    assert recorder.calls[1][1].endswith("project_info?id=ZItoamyI")
    assert [dataset for dataset, _ in records] == ["projects", "policy_candidates"]
    project = records[0][1]
    assert project["project_id"] == "ZItoamyI"
    assert is_policy_candidate(project)
    assert candidate_record(project)["candidate_keywords"]


def test_clig_fetch_uses_real_catalog_recorder_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.PROJECT_ROOT", tmp_path)
    source = next(row for row in load_catalog()["sources"] if row["source_id"] == "clig_projects")
    plan = load_ingestion_plans()["sources"]["clig_projects"]
    plan = {**plan, "catalog_expected_record_count": 1, "expected_policy_candidate_count": 1}
    settings = Settings(database_url="sqlite:///unused.sqlite", http_delay_seconds=0)
    recorder = ResponseRecorder("clig_projects", "fixture-run", settings, runtime_endpoints=source["endpoints"])
    calls = []

    def respond(request):
        calls.append(request)
        if request.method == "POST":
            form = parse_qs(request.content.decode(), keep_blank_values=True)
            assert set(form) == {"project_name", "project_year", "page"}
            body = LIST_HTML if form["page"] == ["1"] else EMPTY_HTML
        else:
            assert dict(request.url.params) == {"id": "ZItoamyI"}
            body = DETAIL_HTML
        return httpx.Response(200, text=body, headers={"content-type": "text/html"}, request=request)

    recorder.client.close()
    recorder.client = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        records = CligProjectsConnector().fetch(ConnectorContext(source=source, plan=plan, settings=settings, recorder=recorder))
        assert [row[0] for row in records] == ["projects", "policy_candidates"]
        assert [request.method for request in calls] == ["POST", "GET", "POST"]
        assert len(recorder.artifacts) == 3
        for method, url, kwargs in [
            ("POST", plan["list_url"], {"json_body": {"project_name": "", "project_year": "", "page": "1"}}),
            ("POST", plan["list_url"], {"data": {"page": "1", "unapproved": "value"}}),
            ("GET", plan["detail_url_template"].format(project_id="ZItoamyI") + "&unapproved=value", {}),
        ]:
            with pytest.raises(PolicyViolation):
                recorder.request(method, url, name="blocked", **kwargs)
        assert len(calls) == 3
    finally:
        recorder.close()


def test_template_query_values_keep_fixed_filters_and_parameter_names():
    recorder = object.__new__(ResponseRecorder)
    recorder.allowed_endpoints = [ResponseRecorder._endpoint_rule({
        "method": "GET", "url": "https://example.test/detail?id={record_id}&scope=public",
        "request_template": {"query": "lang=th"},
    })]
    assert recorder._request_is_allowed("GET", "https://example.test/detail?id=one&scope=public&lang=th", None)
    for query in ("id=one&scope=private&lang=th", "id=one&scope=public", "id=one&scope=public&lang=en", "id=one&id=two&scope=public&lang=th"):
        assert not recorder._request_is_allowed("GET", "https://example.test/detail?" + query, None)


def test_connector_rejects_duplicate_project_ids() -> None:
    second_row = LIST_HTML.split("<tr>", 2)[2].split("</table>", 1)[0]
    duplicate_html = LIST_HTML.replace("</table>", "<tr>" + second_row + "</table>")
    duplicate_html = duplicate_html.replace('<a class="page-link page" href-val="2">2</a>', "")
    recorder = SequenceRecorder([duplicate_html, DETAIL_HTML])
    with pytest.raises(RuntimeError, match="duplicate project_id"):
        CligProjectsConnector().fetch(context_for(recorder))


@pytest.mark.parametrize("counts,message", [
    ({"catalog_expected_record_count": 107}, "projects count mismatch: expected 107, got 1"),
    ({"catalog_expected_record_count": 1, "expected_policy_candidate_count": 2}, "policy_candidates count mismatch"),
    ({"catalog_expected_record_count": 1, "expected_policy_candidate_count": 0}, "policy_candidates count mismatch"),
])
def test_connector_rejects_incomplete_or_changed_counts(counts, message):
    context = context_for(SequenceRecorder([LIST_HTML, DETAIL_HTML, EMPTY_HTML]))
    context.plan.update(counts)
    with pytest.raises(RuntimeError, match=message):
        CligProjectsConnector().fetch(context)


def test_connector_rejects_page_limit_before_completion():
    context = context_for(SequenceRecorder([LIST_HTML, DETAIL_HTML]))
    context.plan["max_pages"] = 1
    with pytest.raises(RuntimeError, match="pagination exceeded max_pages"):
        CligProjectsConnector().fetch(context)


def test_pipeline_keeps_failed_manifest_for_truncated_clig_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.PROJECT_ROOT", tmp_path)
    real_client = httpx.Client
    def respond(request):
        if request.method == "GET":
            body = DETAIL_HTML
        else:
            form = parse_qs(request.content.decode(), keep_blank_values=True)
            body = LIST_HTML if form["page"] == ["1"] else EMPTY_HTML
        return httpx.Response(200, text=body, headers={"content-type": "text/html"}, request=request)
    monkeypatch.setattr("app.ingestion.httpx.Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    source = next(row for row in load_catalog()["sources"] if row["source_id"] == "clig_projects")
    pipeline = IngestionPipeline(None, Settings(database_url="sqlite:///unused.sqlite", http_delay_seconds=0))
    with pytest.raises(IngestionFetchError, match="projects count mismatch: expected 107, got 1") as exc:
        pipeline._fetch_api(source, "truncated-fixture")
    manifest = json.loads(exc.value.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["records_seen"] == 0
    assert len(manifest["artifacts"]) == 3
    assert all(artifact["sha256"] for artifact in manifest["artifacts"])


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_order: list[str] = []

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> dict:
        self.objects[Key] = bytes(Body)
        self.put_order.append(Key)
        return {}

    def list_objects_v2(self, Bucket: str, Prefix: str, **_: object) -> dict:
        keys = sorted(key for key in self.objects if key.startswith(Prefix))
        return {"Contents": [{"Key": key} for key in keys], "IsTruncated": False}


def test_clig_run_folder_is_compatible_with_evidence_push(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260823T010203Z"
    run_dir.mkdir()
    write_jsonl(run_dir / "projects.jsonl", [{"contract_no": "A", "project_id": "P1"}])
    write_jsonl(run_dir / "policy_candidates.jsonl", [{"contract_no": "A", "project_id": "P1"}])
    (run_dir / "projects.csv").write_text("contract_no,project_id\nA,P1\n", encoding="utf-8")
    (run_dir / "policy_candidates.csv").write_text("contract_no,project_id\nA,P1\n", encoding="utf-8")
    (run_dir / "network_observation.json").write_text(
        json.dumps({"upstream": []}), encoding="utf-8"
    )
    write_manifest_input(
        run_dir,
        fetched_at="2026-08-23T01:02:03+00:00",
        fetched_by="tester",
        upstream=[],
    )

    client = FakeS3Client()
    config = StoreConfig(
        endpoint="https://example.invalid",
        bucket="bucket",
        access_key_id="key",
        secret_access_key="secret",
    )
    manifest = push_run(client, config, "clig_projects", run_dir)

    assert [dataset["file"] for dataset in manifest["datasets"]] == [
        "projects.jsonl.gz",
        "policy_candidates.jsonl.gz",
    ]
    assert [dataset["row_count"] for dataset in manifest["datasets"]] == [1, 1]
    prefix = "raw/f4/clig_projects/20260823T010203Z/"
    assert gzip.decompress(client.objects[prefix + "projects.jsonl.gz"]).count(b"\n") == 1
    assert client.put_order[-1] == prefix + "manifest.json"
