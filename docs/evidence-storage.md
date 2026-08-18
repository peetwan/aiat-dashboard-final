# Team evidence storage (Cloudflare R2)

ที่เก็บ raw snapshot กลางของทีม แทน Google Drive + path เครื่องส่วนตัว
เป้าหมาย: ใครก็ pull ไป build ซ้ำได้ผลเหมือนกัน และตอบได้เสมอว่าไฟล์ไหนมาจากไหนเมื่อไร

- Bucket: `aiat-data-evidence` (Cloudflare R2, private เสมอ — raw อาจมีข้อมูลส่วนบุคคล)
- Layout บน bucket:

```text
raw/<source_id>/<run_id>/
    manifest.json              # สร้างโดย evidence_push.py — run ที่ไม่มีไฟล์นี้ = ใช้ไม่ได้
    <dataset>.jsonl.gz         # ข้อมูลตามที่ดึงมา (push ทำ gzip ให้)
    network_observation.json   # ไฟล์ประกอบอื่น ๆ อัปโหลดตามจริง
```

- `run_id` = UTC timestamp รูปแบบ `20260818T041500Z`
- กฎเหล็ก: หนึ่ง run = หนึ่งโฟลเดอร์ ห้ามแก้ย้อนหลัง — ดึงใหม่คือ run ใหม่
  (`evidence_push.py` ปฏิเสธ run_id ซ้ำ และ bucket ตั้ง lock กันลบ/ทับบน prefix `raw/`)

## ภาพรวม data flow ของทีม

```text
[1] คนดูแล source (เครื่องตัวเอง, มี network)
        ดึงข้อมูลจาก URL ที่รับผิดชอบ
        → จัดโฟลเดอร์ + เขียน manifest_input.json (กรอกเอง: fetched_by, as_of, grain)
        → python tools/evidence_push.py <source_id> <dir>
              (tool ทำให้: gzip, sha256, row_count, manifest.json อัปโหลดท้ายสุด
               และปฏิเสธ run_id ซ้ำ — เขียนทับไม่ได้)
        ↓
[2] Team bucket (Cloudflare R2, private)
        raw/<source_id>/<run_id>/ ... immutable, หนึ่งครั้งดึง = หนึ่ง run
        ↓
[3] ทุกคนในทีม (key read-only)
        python tools/evidence_pull.py <source_id>
        → AIAT_EVIDENCE_ROOT/data/raw/<source_id>/<run_id>/  (ตรวจ sha256 ทุกไฟล์)
        ↓
[4] เอาเข้า database บนเครื่องตัวเอง (Candidate เท่านั้น)
        - SPU flood 4 ตัว: python -m app.cli import-flood-snapshots
          (ใช้ AIAT_EVIDENCE_ROOT ตัวเดียวกับตอน pull; จำนวนแถวตรวจกับ manifest ของ run)
        - source ที่ operational: connector pipeline ผ่าน ResponseRecorder ตามปกติ
        ↓
[5] Publication — เหมือนเดิมทุกอย่าง
        deterministic builders → data/public/* + receipt → PR
        → CI (fixture-only) → review → squash merge
        ↓
[6] Serving
        merge → Railway deploy → startup sync → serving Postgres → Dashboard/Explorer/API
        (web runtime ไม่อ่าน bucket และ workspace — อ่านเฉพาะของที่ review แล้วใน data/public/)
```

ใครต้องมีอะไร:

| บทบาท | ต้องมี | ทำอะไรได้ |
|---|---|---|
| แก้ UI / connector / tests | แค่ clone (ไม่ต้องมี key) | ทำงานด้วย fixture + `python -m app.cli check` |
| สมาชิกทุกคน | key read-only ใน `.env` | pull ทุก run, import, build ซ้ำได้ผลเหมือนกันทุกเครื่อง |
| คนดูแล source | key read-write เพิ่ม | push run ใหม่ของ source ตัวเอง |

กติกาที่ทำให้ทั้งทีมไม่ชนกัน: (1) run ห้ามแก้ย้อนหลัง — ดึงใหม่ = run ใหม่
(2) เส้นทาง raw (push / pull / flood importer) อ่าน hash และจำนวนแถวจาก manifest ของ run
ไม่อ่านค่าที่ฝังในโค้ด (3) CI ไม่มี credential — ความถูกต้องของ PR พิสูจน์ด้วย fixture เท่านั้น

ข้อจำกัดปัจจุบัน: dated-path builders บางตัว (`build_public_data.py`,
`build_source_insights.py` ฯลฯ) ยังปักพาธ run เฉพาะใน `data/qa` / `data/staged` ที่
`evidence_pull.py` ไม่ได้สร้าง — งาน rebuild release เต็มรูปจึงยังต้องใช้ canonical
workspace ตามที่ระบุใน [CONTRIBUTING.md](../CONTRIBUTING.md) จนกว่า bucket จะครอบส่วนนั้น

## ตั้งค่าครั้งแรก

สร้าง `.env` ที่ root ของ repo (gitignore แล้ว ห้าม commit):

```text
AIAT_S3_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
AIAT_S3_BUCKET=aiat-data-evidence
AIAT_S3_ACCESS_KEY_ID=<ขอจากคนดูแล bucket>
AIAT_S3_SECRET_ACCESS_KEY=<ขอจากคนดูแล bucket>
```

- ทุกคนได้ key ชุด read-only / เฉพาะคนดูแล source ที่ต้อง push ได้ key ชุด read-write
- ติดตั้ง dependency: `pip install -r requirements.txt` (มี boto3 แล้ว)
- CI ไม่มี credential และห้ามมี: CI รันด้วย fixture เท่านั้นตามกฎ repo

## ดึงข้อมูล (ทุกคน)

```bash
python tools/evidence_pull.py <source_id>                 # run ล่าสุด
python tools/evidence_pull.py <source_id> --run <run_id>  # run ที่ระบุ
python tools/evidence_pull.py <source_id> --list          # ดู run ทั้งหมด
```

ปลายทางคือ `<AIAT_EVIDENCE_ROOT>/data/raw/<source_id>/<run_id>/`
(ค่าเริ่มต้นของ `AIAT_EVIDENCE_ROOT` = โฟลเดอร์แม่ของ repo นี้ ตรงกับที่
`tools/build_source_catalog.py` และเพื่อน ๆ ใช้อยู่แล้ว)

pull ตรวจ sha256 ทุกไฟล์เทียบ manifest — ไม่ตรงคือ exit code 2 ไม่ใช่คำเตือน
`latest` = run_id ที่มากที่สุดตามลำดับตัวอักษร (timestamp UTC เรียงได้ตรงตัว)

## อัปโหลด run ใหม่ (คนดูแล source)

1. จัดไฟล์ที่ดึงมาไว้ในโฟลเดอร์เดียว แล้วเขียน `manifest_input.json` ในโฟลเดอร์นั้น —
   นี่คือส่วนเดียวที่คนต้องกรอกเอง เพราะห้ามให้เครื่องมือเดา (ตาม AGENTS.md):

```json
{
  "fetched_by": "thanden11",
  "upstream": [{"url": "https://...", "http_status": 200, "content_type": "application/json"}],
  "datasets": [
    {
      "dataset_key": "sukhothaicare.incidents",
      "file": "incidents.jsonl",
      "as_of": "2026-08-17T23:00:00Z",
      "grain": "หนึ่งแถว = หนึ่งเหตุการณ์ที่มีผู้แจ้ง",
      "identity_fields": ["id"]
    }
  ]
}
```

2. push:

```bash
python tools/evidence_push.py <source_id> ./out/<run_dir>
```

เครื่องมือทำให้เอง: gzip dataset, คำนวณ sha256 + row_count, สร้าง `manifest.json`
และอัปโหลด manifest เป็นไฟล์สุดท้าย (push ที่ล่มกลางทางจะไม่ทิ้ง run ที่ดูสมบูรณ์ไว้)

- `row_count` / `sha256` อยู่ที่ run ไม่ hardcode ในซอร์สโค้ด
- `as_of` ต้องมีทุก dataset — ข้อมูลที่ไม่มีเวลาอ้างอิงตีความไม่ได้
- `grain` เป็นข้อความที่คนเขียนเอง

## ข้อห้ามที่เกี่ยวข้อง

- ห้ามอ่านจาก bucket ตอน startup/request ของ web app — bucket ใช้ตอน build เท่านั้น
- ห้าม commit key ลง repo (`.env` ถูก gitignore แล้ว)
- ห้ามแชร์ key ในช่องทางสาธารณะ ส่งตรงถึงตัวเท่านั้น และ roll ได้ทันทีจาก
  Cloudflare dashboard → R2 → Manage API tokens เมื่อสงสัยว่ารั่ว

## ใช้กับ flood snapshot importer

run แรกของ SPU flood sources ทั้ง 4 ตัว (`spu_sukhothai_care`, `spu_sukhothai_water`,
`spu_nsn_flood`, `spu_rawangphai_uru` — run `20260815T…Z` migrate มาจาก Drive เดิม)
อยู่บน bucket แล้ว ขั้นตอนเอาเข้า `dashboard_records` บนเครื่องตัวเอง:

```bash
python tools/evidence_pull.py spu_sukhothai_care     # ทำครบทั้ง 4 source
export AIAT_EVIDENCE_ROOT=<root เดียวกับที่ pull เขียนลง>   # ค่าเริ่มต้นของ pull คือโฟลเดอร์แม่ของ repo
python -m app.cli import-flood-snapshots
```

(หรือส่ง `--evidence-root "$AIAT_EVIDENCE_ROOT"` แทนการ export ก็ได้ — สำคัญแค่ต้องเป็น
root เดียวกับที่ pull ใช้ ไม่งั้น importer จะหา `data/raw` ไม่เจอ)

importer ตรวจจำนวนแถวกับ `row_count` ใน manifest ของ run — ไม่มีตัวเลข hardcode
ในซอร์สโค้ดอีกแล้ว และคำสั่งนี้ต้องระบุ `--evidence-root` (หรือ export
`AIAT_EVIDENCE_ROOT`) เสมอ เพราะ web runtime ห้ามแตะ workspace โดย default
