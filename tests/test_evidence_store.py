from __future__ import annotations

import gzip
import io
import json
from pathlib import Path

import pytest

from tools.evidence_store import (
    EvidenceStoreError,
    RunAlreadyExistsError,
    StoreConfig,
    VerificationError,
    list_runs,
    pull_run,
    push_run,
    sha256_file,
)


CONFIG = StoreConfig(
    endpoint="https://example.invalid",
    bucket="test-bucket",
    access_key_id="k",
    secret_access_key="s",
)


class FakeS3Client:
    """S3 client จำลองใน memory — CI ห้ามแตะ network จริงตามกฎ repo"""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_order: list[str] = []

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> dict:
        assert Bucket == CONFIG.bucket
        self.objects[Key] = bytes(Body)
        self.put_order.append(Key)
        return {}

    def get_object(self, Bucket: str, Key: str) -> dict:
        return {"Body": io.BytesIO(self.objects[Key])}

    def list_objects_v2(self, Bucket: str, Prefix: str, **_: object) -> dict:
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        return {
            "Contents": [{"Key": k, "Size": len(self.objects[k])} for k in keys],
            "IsTruncated": False,
            "KeyCount": len(keys),
        }


def make_run_dir(tmp_path: Path, rows: int = 3) -> Path:
    run_dir = tmp_path / "20260818T041500Z"
    run_dir.mkdir(parents=True)
    lines = [json.dumps({"id": i, "value": f"row-{i}"}) for i in range(rows)]
    (run_dir / "incidents.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run_dir / "network_observation.json").write_text(
        json.dumps({"url": "https://example.invalid", "http_status": 200}),
        encoding="utf-8",
    )
    (run_dir / "manifest_input.json").write_text(
        json.dumps(
            {
                "fetched_by": "tester",
                "upstream": [{"url": "https://example.invalid", "http_status": 200}],
                "datasets": [
                    {
                        "dataset_key": "test.incidents",
                        "file": "incidents.jsonl",
                        "as_of": "2026-08-17T23:00:00Z",
                        "grain": "หนึ่งแถว = หนึ่งเหตุการณ์",
                        "identity_fields": ["id"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return run_dir


def test_push_builds_manifest_and_uploads_gzip(tmp_path: Path) -> None:
    client = FakeS3Client()
    manifest = push_run(client, CONFIG, "test_source", make_run_dir(tmp_path))

    assert manifest["run_id"] == "20260818T041500Z"
    (dataset,) = manifest["datasets"]
    assert dataset["file"] == "incidents.jsonl.gz"
    assert dataset["row_count"] == 3
    assert dataset["as_of"] == "2026-08-17T23:00:00Z"

    prefix = "raw/test_source/20260818T041500Z/"
    uploaded = client.objects[prefix + "incidents.jsonl.gz"]
    decompressed = gzip.decompress(uploaded).decode("utf-8")
    assert decompressed.count("\n") == 3
    assert [e["file"] for e in manifest["extra_files"]] == ["network_observation.json"]
    # manifest ต้องเป็นไฟล์สุดท้าย: push ที่ล่มกลางทางจะไม่ทิ้ง run ที่ดูสมบูรณ์ไว้
    assert client.put_order[-1] == prefix + "manifest.json"


def test_push_refuses_existing_run(tmp_path: Path) -> None:
    client = FakeS3Client()
    run_dir = make_run_dir(tmp_path)
    push_run(client, CONFIG, "test_source", run_dir)
    with pytest.raises(RunAlreadyExistsError):
        push_run(client, CONFIG, "test_source", run_dir)


def test_push_requires_as_of_and_grain(tmp_path: Path) -> None:
    run_dir = make_run_dir(tmp_path)
    manifest_input = json.loads((run_dir / "manifest_input.json").read_text("utf-8"))
    del manifest_input["datasets"][0]["as_of"]
    (run_dir / "manifest_input.json").write_text(
        json.dumps(manifest_input, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(EvidenceStoreError, match="as_of"):
        push_run(FakeS3Client(), CONFIG, "test_source", run_dir)


def test_pull_roundtrip_verifies_and_writes_layout(tmp_path: Path) -> None:
    client = FakeS3Client()
    push_run(client, CONFIG, "test_source", make_run_dir(tmp_path / "src"))

    dest_root = tmp_path / "workspace"
    dest = pull_run(client, CONFIG, "test_source", dest_root=dest_root)

    assert dest == dest_root / "data/raw/test_source/20260818T041500Z"
    manifest = json.loads((dest / "manifest.json").read_text("utf-8"))
    dataset_file = dest / manifest["datasets"][0]["file"]
    assert sha256_file(dataset_file) == manifest["datasets"][0]["sha256"]
    with gzip.open(dataset_file, "rt", encoding="utf-8") as handle:
        assert sum(1 for line in handle if line.strip()) == 3
    # pull ซ้ำโดยไม่ force ต้องจบเงียบ ๆ เพราะของ local ตรง hash อยู่แล้ว
    assert pull_run(client, CONFIG, "test_source", dest_root=dest_root) == dest


def test_pull_fails_on_corruption_and_leaves_no_partial_dir(tmp_path: Path) -> None:
    client = FakeS3Client()
    push_run(client, CONFIG, "test_source", make_run_dir(tmp_path / "src"))
    key = "raw/test_source/20260818T041500Z/incidents.jsonl.gz"
    client.objects[key] = client.objects[key] + b"tampered"

    dest_root = tmp_path / "workspace"
    with pytest.raises(VerificationError, match="sha256"):
        pull_run(client, CONFIG, "test_source", dest_root=dest_root)
    assert not (dest_root / "data/raw/test_source/20260818T041500Z").exists()


def test_pull_rejects_unsafe_manifest_paths(tmp_path: Path) -> None:
    client = FakeS3Client()
    push_run(client, CONFIG, "test_source", make_run_dir(tmp_path / "src"))
    key = "raw/test_source/20260818T041500Z/manifest.json"
    manifest = json.loads(client.objects[key])
    manifest["extra_files"] = [{"file": "../../evil.txt", "sha256": "0" * 64}]
    client.objects[key] = json.dumps(manifest).encode("utf-8")

    with pytest.raises(EvidenceStoreError, match="ไม่ปลอดภัย"):
        pull_run(client, CONFIG, "test_source", dest_root=tmp_path / "workspace")


def test_list_runs_and_latest(tmp_path: Path) -> None:
    client = FakeS3Client()
    early = make_run_dir(tmp_path / "a")
    push_run(client, CONFIG, "test_source", early)
    late = make_run_dir(tmp_path / "b")
    push_run(client, CONFIG, "test_source", late, run_id="20260819T090000Z")

    assert list_runs(client, CONFIG, "test_source") == [
        "20260818T041500Z",
        "20260819T090000Z",
    ]
    dest = pull_run(client, CONFIG, "test_source", run="latest", dest_root=tmp_path / "w")
    assert dest.name == "20260819T090000Z"


def test_run_without_manifest_is_unusable(tmp_path: Path) -> None:
    client = FakeS3Client()
    # จำลอง push ที่ล่มกลางทาง: มีไฟล์ dataset แต่ไม่มี manifest.json
    client.objects["raw/test_source/20260818T041500Z/incidents.jsonl.gz"] = b"x"
    with pytest.raises(EvidenceStoreError, match="manifest"):
        pull_run(client, CONFIG, "test_source", dest_root=tmp_path / "w")
