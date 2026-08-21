#!/usr/bin/env python3
"""แกนกลางของ team evidence store บน S3-compatible storage (Cloudflare R2).

กฎที่ module นี้บังคับ (รายละเอียดใน docs/evidence-storage.md):

- หนึ่ง run = หนึ่ง prefix ``raw/<department>/<source_id>/<run_id>/`` และห้ามเขียนทับ
  (push ปฏิเสธ run_id ที่มีอยู่แล้ว ไม่ใช่พึ่งวินัยคน)
- ``manifest.json`` ถูกอัปโหลดเป็นไฟล์สุดท้ายเสมอ run ที่ไม่มี manifest = ใช้ไม่ได้
- ``as_of`` และ ``grain`` ต้องมาจากคนที่รู้ข้อมูล เครื่องมือห้ามเดา (ตาม AGENTS.md)
- pull ตรวจ sha256 ทุกไฟล์ ไม่ตรง = ล้มเหลวทันที ไม่ใช่แค่เตือน
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]

TOOL_VERSION = "0.2.0"
MANIFEST_NAME = "manifest.json"
MANIFEST_INPUT_NAME = "manifest_input.json"
RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z$")
SOURCE_CATALOG_PATH = DASHBOARD_ROOT / "config" / "source_catalog.json"
DEPARTMENT_CODES = {
    "ฝ่าย 1": "f1",
    "ฝ่าย 2": "f2",
    "ฝ่าย 3": "f3",
    "ฝ่าย 4": "f4",
    "ฝ่าย SPU": "spu",
}
REQUIRED_ENV_KEYS = (
    "AIAT_S3_ENDPOINT",
    "AIAT_S3_BUCKET",
    "AIAT_S3_ACCESS_KEY_ID",
    "AIAT_S3_SECRET_ACCESS_KEY",
)


class EvidenceStoreError(RuntimeError):
    """ข้อผิดพลาดที่ผู้ใช้แก้เองได้ (config ผิด, input ไม่ครบ, hash ไม่ตรง)"""


class RunAlreadyExistsError(EvidenceStoreError):
    """พยายาม push ทับ run ที่มีอยู่แล้ว"""


class VerificationError(EvidenceStoreError):
    """ไฟล์ที่ดึงมาไม่ตรงกับ sha256 ใน manifest"""


@dataclass(frozen=True)
class StoreConfig:
    endpoint: str
    bucket: str
    access_key_id: str
    secret_access_key: str
    raw_prefix: str = "raw/"


def evidence_root() -> Path:
    return Path(
        os.environ.get("AIAT_EVIDENCE_ROOT", str(DASHBOARD_ROOT.parent))
    ).expanduser().resolve()


def load_dotenv(path: Path | None = None) -> None:
    """เติมค่า KEY=VALUE จาก .env ที่ root ของ repo เข้า os.environ เฉพาะ key ที่ยังว่าง"""
    env_path = path if path is not None else DASHBOARD_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def config_from_env() -> StoreConfig:
    load_dotenv()
    missing = [key for key in REQUIRED_ENV_KEYS if not os.environ.get(key)]
    if missing:
        raise EvidenceStoreError(
            "ยังไม่ได้ตั้งค่า: " + ", ".join(missing)
            + " (ใส่ใน .env ที่ root ของ repo หรือ export เอง; ดู docs/evidence-storage.md)"
        )
    return StoreConfig(
        endpoint=os.environ["AIAT_S3_ENDPOINT"],
        bucket=os.environ["AIAT_S3_BUCKET"],
        access_key_id=os.environ["AIAT_S3_ACCESS_KEY_ID"],
        secret_access_key=os.environ["AIAT_S3_SECRET_ACCESS_KEY"],
        raw_prefix=os.environ.get("AIAT_S3_RAW_PREFIX", "raw/"),
    )


def make_client(config: StoreConfig):
    # import ภายในฟังก์ชันเพื่อให้ test ที่ใช้ fake client รันได้โดยไม่ต้องมี boto3
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=config.endpoint,
        region_name="auto",
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def dataset_row_count(path: Path) -> int:
    """นับแถวของ dataset — jsonl นับบรรทัดที่ไม่ว่าง, json นับสมาชิก array (หรือ 1)"""
    name = path.name
    if name.endswith(".jsonl.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    if name.endswith(".jsonl"):
        with path.open(encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    if name.endswith(".json.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    elif name.endswith(".json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise EvidenceStoreError(
            f"นับแถวของ {name} ไม่ได้ — dataset ต้องเป็น .jsonl(.gz) หรือ .json(.gz)"
        )
    return len(payload) if isinstance(payload, list) else 1


def _safe_relative_name(name: str) -> str:
    """กัน path traversal จากชื่อไฟล์ใน manifest/manifest_input (ข้อมูลจากนอกเครื่อง)"""
    if not name or name.startswith(("/", "\\")) or ".." in Path(name).parts or "\\" in name:
        raise EvidenceStoreError(f"ชื่อไฟล์ไม่ปลอดภัย: {name!r}")
    return name


def _iter_keys(client, bucket: str, prefix: str) -> Iterator[str]:
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        response = client.list_objects_v2(**kwargs)
        for item in response.get("Contents", []):
            yield item["Key"]
        if not response.get("IsTruncated"):
            return
        token = response.get("NextContinuationToken")


def source_department(source_id: str) -> str:
    """คืนรหัสฝ่ายจาก generated source catalog ซึ่งเป็นสำเนาของ canonical registry"""
    try:
        catalog = json.loads(SOURCE_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceStoreError(f"อ่าน source catalog ไม่ได้: {SOURCE_CATALOG_PATH}: {exc}") from exc

    source = next(
        (item for item in catalog.get("sources", []) if item.get("source_id") == source_id),
        None,
    )
    if source is None:
        raise EvidenceStoreError(f"source_id ไม่มีใน config/source_catalog.json: {source_id}")
    group = source.get("group")
    department = DEPARTMENT_CODES.get(group)
    if department is None:
        raise EvidenceStoreError(f"ยังไม่มีรหัส R2 สำหรับ group={group!r} ของ {source_id}")
    return department


def remote_source_prefix(config: StoreConfig, source_id: str) -> str:
    department = source_department(source_id)
    return f"{config.raw_prefix}{department}/{source_id}/"


def remote_run_prefix(config: StoreConfig, source_id: str, run_id: str) -> str:
    return f"{remote_source_prefix(config, source_id)}{run_id}/"


def list_runs(client, config: StoreConfig, source_id: str) -> list[str]:
    prefix = remote_source_prefix(config, source_id)
    run_ids = set()
    for key in _iter_keys(client, config.bucket, prefix):
        run_id = key[len(prefix):].split("/", 1)[0]
        if RUN_ID_PATTERN.match(run_id):
            run_ids.add(run_id)
    return sorted(run_ids)


def _load_manifest_input(run_dir: Path) -> dict[str, Any]:
    input_path = run_dir / MANIFEST_INPUT_NAME
    if not input_path.exists():
        raise EvidenceStoreError(
            f"ไม่พบ {MANIFEST_INPUT_NAME} ใน {run_dir}\n"
            "ไฟล์นี้คือส่วนที่คนต้องกรอกเอง (ห้ามให้เครื่องมือเดา) ตัวอย่าง:\n"
            + json.dumps(
                {
                    "fetched_by": "ชื่อ github ของคนดึง",
                    "upstream": [{"url": "https://...", "http_status": 200}],
                    "datasets": [
                        {
                            "dataset_key": "sukhothaicare.incidents",
                            "file": "incidents.jsonl",
                            "as_of": "2026-08-17T23:00:00Z",
                            "grain": "หนึ่งแถว = หนึ่งเหตุการณ์ที่มีผู้แจ้ง",
                            "identity_fields": ["id"],
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    manifest_input = json.loads(input_path.read_text(encoding="utf-8"))
    if not str(manifest_input.get("fetched_by", "")).strip():
        raise EvidenceStoreError("manifest_input.json ต้องระบุ fetched_by")
    datasets = manifest_input.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise EvidenceStoreError("manifest_input.json ต้องมี datasets อย่างน้อย 1 รายการ")
    for entry in datasets:
        for required in ("dataset_key", "file", "as_of", "grain"):
            if not str(entry.get(required, "")).strip():
                raise EvidenceStoreError(
                    f"dataset {entry.get('dataset_key') or entry.get('file') or '?'} "
                    f"ขาด field บังคับ: {required} (as_of/grain ต้องกรอกเอง ห้ามเดา)"
                )
        _safe_relative_name(str(entry["file"]))
    return manifest_input


def push_run(
    client,
    config: StoreConfig,
    source_id: str,
    run_dir: Path,
    run_id: str | None = None,
) -> dict[str, Any]:
    """อัปโหลด run ใหม่: gzip + hash + นับแถว + สร้าง manifest แล้วส่งขึ้น bucket

    คืนค่า manifest ที่อัปโหลดแล้ว; โยน RunAlreadyExistsError ถ้า run_id ซ้ำ
    """
    run_dir = run_dir.expanduser().resolve()
    if not run_dir.is_dir():
        raise EvidenceStoreError(f"ไม่พบโฟลเดอร์ run: {run_dir}")
    manifest_input = _load_manifest_input(run_dir)

    if run_id is None:
        run_id = run_dir.name if RUN_ID_PATTERN.match(run_dir.name) else utc_now_run_id()
    if not RUN_ID_PATTERN.match(run_id):
        raise EvidenceStoreError(
            f"run_id ต้องอยู่ในรูป UTC timestamp เช่น 20260818T041500Z (ได้ {run_id!r})"
        )

    prefix = remote_run_prefix(config, source_id, run_id)
    if next(_iter_keys(client, config.bucket, prefix), None) is not None:
        raise RunAlreadyExistsError(
            f"run {source_id}/{run_id} มีอยู่แล้วใน bucket — ดึงใหม่ = run ใหม่ ห้ามทับของเก่า"
        )

    dataset_sources: set[Path] = set()
    datasets_out: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="evidence_push_") as staging_text:
        staging = Path(staging_text)
        uploads: list[tuple[Path, str]] = []  # (local path, ชื่อไฟล์บน bucket)

        for entry in manifest_input["datasets"]:
            source_path = run_dir / str(entry["file"])
            if not source_path.is_file():
                raise EvidenceStoreError(f"ไม่พบไฟล์ dataset: {source_path}")
            dataset_sources.add(source_path)
            row_count = dataset_row_count(source_path)
            if source_path.name.endswith((".jsonl", ".json")):
                staged_name = source_path.name + ".gz"
                staged_path = staging / staged_name
                # mtime=0 ให้ gzip ของเนื้อหาเดียวกันได้ byte เดียวกันเสมอ (hash นิ่ง)
                with source_path.open("rb") as raw_in, staged_path.open("wb") as raw_out:
                    with gzip.GzipFile(
                        filename="", mode="wb", fileobj=raw_out, mtime=0
                    ) as gz_out:
                        shutil.copyfileobj(raw_in, gz_out)
            else:
                staged_name = source_path.name
                staged_path = staging / staged_name
                shutil.copy2(source_path, staged_path)
            datasets_out.append(
                {
                    "dataset_key": entry["dataset_key"],
                    "file": staged_name,
                    "sha256": sha256_file(staged_path),
                    "row_count": row_count,
                    "as_of": entry["as_of"],
                    "grain": entry["grain"],
                    "identity_fields": entry.get("identity_fields", []),
                }
            )
            uploads.append((staged_path, staged_name))

        extra_files_out: list[dict[str, Any]] = []
        for path in sorted(run_dir.rglob("*")):
            if not path.is_file() or path in dataset_sources:
                continue
            relative = path.relative_to(run_dir).as_posix()
            if relative in (MANIFEST_INPUT_NAME, MANIFEST_NAME):
                continue
            _safe_relative_name(relative)
            extra_files_out.append({"file": relative, "sha256": sha256_file(path)})
            uploads.append((path, relative))

        manifest: dict[str, Any] = {
            "source_id": source_id,
            "run_id": run_id,
            "fetched_at": manifest_input.get(
                "fetched_at", datetime.now(timezone.utc).isoformat()
            ),
            "fetched_by": manifest_input["fetched_by"],
            "upstream": manifest_input.get("upstream", []),
            "datasets": datasets_out,
            "extra_files": extra_files_out,
            "tool_version": f"evidence_push.py {TOOL_VERSION}",
        }

        for local_path, remote_name in uploads:
            client.put_object(
                Bucket=config.bucket,
                Key=prefix + remote_name,
                Body=local_path.read_bytes(),
            )
        # manifest ไปท้ายสุดเสมอ: ถ้า push ล่มกลางทาง run จะไม่มี manifest = ถือว่าใช้ไม่ได้
        client.put_object(
            Bucket=config.bucket,
            Key=prefix + MANIFEST_NAME,
            Body=json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
    return manifest


def _expected_hashes(manifest: dict[str, Any]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for entry in manifest.get("datasets", []):
        expected[_safe_relative_name(str(entry["file"]))] = entry["sha256"]
    for entry in manifest.get("extra_files", []):
        expected[_safe_relative_name(str(entry["file"]))] = entry["sha256"]
    return expected


def _local_run_verifies(dest: Path, expected: dict[str, str]) -> bool:
    return all(
        (dest / name).is_file() and sha256_file(dest / name) == digest
        for name, digest in expected.items()
    )


def pull_run(
    client,
    config: StoreConfig,
    source_id: str,
    run: str = "latest",
    dest_root: Path | None = None,
    force: bool = False,
) -> Path:
    """ดึง run ลง ``<AIAT_EVIDENCE_ROOT>/data/raw/<source_id>/<run_id>/`` พร้อมตรวจ hash ครบทุกไฟล์"""
    if run == "latest":
        runs = list_runs(client, config, source_id)
        if not runs:
            raise EvidenceStoreError(f"ยังไม่มี run ของ {source_id} ใน bucket")
        run = runs[-1]
    if not RUN_ID_PATTERN.match(run):
        raise EvidenceStoreError(f"run_id ไม่ถูกรูปแบบ: {run!r}")

    prefix = remote_run_prefix(config, source_id, run)
    remote_keys = set(_iter_keys(client, config.bucket, prefix))
    manifest_key = prefix + MANIFEST_NAME
    if manifest_key not in remote_keys:
        raise EvidenceStoreError(
            f"run {source_id}/{run} ไม่มี {MANIFEST_NAME} — ถือว่า run ใช้ไม่ได้ (push อาจล่มกลางทาง)"
        )
    manifest = json.loads(
        client.get_object(Bucket=config.bucket, Key=manifest_key)["Body"].read()
    )
    if manifest.get("source_id") != source_id or manifest.get("run_id") != run:
        raise VerificationError(
            f"manifest ไม่ตรงกับตำแหน่งที่เก็บ: ได้ {manifest.get('source_id')}/{manifest.get('run_id')} "
            f"แต่คาด {source_id}/{run}"
        )
    expected = _expected_hashes(manifest)

    root = dest_root if dest_root is not None else evidence_root()
    dest = root / "data" / "raw" / source_id / run
    if dest.exists() and not force:
        if _local_run_verifies(dest, expected):
            return dest
        raise VerificationError(
            f"{dest} มีอยู่แล้วแต่ hash ไม่ตรง manifest — ตรวจว่าแก้ไฟล์ local หรือใช้ --force เพื่อดึงใหม่"
        )

    with tempfile.TemporaryDirectory(prefix="evidence_pull_") as staging_text:
        staging = Path(staging_text)
        for name, digest in expected.items():
            key = prefix + name
            if key not in remote_keys:
                raise VerificationError(f"ไฟล์ {name} อยู่ใน manifest แต่ไม่อยู่ใน bucket")
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                client.get_object(Bucket=config.bucket, Key=key)["Body"].read()
            )
            actual = sha256_file(target)
            if actual != digest:
                raise VerificationError(
                    f"sha256 ไม่ตรงของ {name}: manifest={digest} ได้={actual}"
                )
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(dest))
        # TemporaryDirectory จะพยายามลบ staging ที่ถูก move ไปแล้ว — สร้างใหม่กัน error
        staging.mkdir(exist_ok=True)
    return dest
