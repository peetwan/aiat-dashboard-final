# เพิ่ม source/URL ใหม่ แบบครบวงจร (Quickstart สำหรับทีม)

เส้นทางรวมตั้งแต่ "มี URL ใหม่" จนถึง "เปิด PR ได้" — ใช้คู่กับ
[คู่มือเพิ่ม Connector](connector-development.md) ที่อธิบายรายละเอียดแต่ละชั้น

จำนวน source ไม่ถูกล็อกไว้ที่ 28: catalog, Explorer และ tests นับจาก generated
catalog จริง เพิ่มแหล่งใหม่แล้ว CI ไม่แดงเพราะ "จำนวนไม่ตรง" อีกต่อไป

## ขั้น 1 — ลงทะเบียน source ใน evidence workspace (ครั้งเดียวต่อ source)

ทำในโฟลเดอร์ AIAT_Project (canonical evidence workspace — ค่าเริ่มต้นของ
`AIAT_EVIDENCE_ROOT` คือโฟลเดอร์แม่ของ repo นี้อยู่แล้ว):

```powershell
python scripts/new_source.py https://เว็บใหม่.go.th/ --name "ชื่อไทย" --group "ฝ่าย 2"
```

คำสั่งเดียวได้ครบ: แถวใน `config/source_registry.json` + bump `total_records` +
โฟลเดอร์ `data/source_audit/<NN>_<source_id>/` (card skeleton) + regenerate board
ดูรายละเอียดที่ `docs/add_new_url.md` ของ workspace นั้น

ถ้าเครื่องยังไม่มี workspace: raw snapshot กลางของทีมอยู่บน evidence bucket
ดึงด้วย `python tools/evidence_pull.py <source_id>` และเมื่อดึงข้อมูลใหม่ของ source ตัวเอง
ให้ `evidence_push.py` ขึ้น bucket เป็น run ใหม่เสมอ — ดู [evidence-storage.md](evidence-storage.md)

## ขั้น 2 — Regenerate catalog/coverage (ใน repo นี้)

```powershell
python tools/build_source_catalog.py
python tools/build_source_coverage.py
```

ห้ามแก้ `config/source_catalog.json` หรือ `data/public/source_coverage.json` ด้วยมือ —
PR ต้องมี generated diff ที่ตรวจย้อนกลับได้

## ขั้น 3 — เพิ่มโปรไฟล์ Explorer

เพิ่ม entry ของ source ใหม่ใน `explorer/source_profiles.py` (`SOURCE_PROFILES`)
อธิบายเป็นภาษาไทยว่าใช้ข้อมูลอะไรและ grain คืออะไร — ระบบตรวจ coverage แบบ exact:
ถ้า catalog มี source ที่ไม่มีโปรไฟล์ test จะบอกชื่อที่ขาดให้เลย

## ขั้น 4 — สร้าง connector ตั้งต้น

```powershell
python tools/scaffold_connector.py <source_id> --transport <lower_snake_case> --dataset-key <key> --grain-th "หนึ่งแถวแทน..." --identity-fields <field[,field]> --geography-field <field> --as-of-field <field>
```

ได้ connector + contract + fixture (redacted) + offline test ตั้งต้น จากนั้นแก้
parser และ completeness ให้ตรงต้นทางจริง

Field ภูมิศาสตร์อย่าง `address_province`, `address_district` ประกาศได้ตามปกติ —
กติกา privacy ตัดเฉพาะข้อมูลติดต่อ/ระบุตัวบุคคล (ชื่อบุคคล เบอร์โทร อีเมล ที่อยู่บ้าน
เลขบัตร) ไม่ตัดภูมิศาสตร์ ตัวเลขรวม หรือรหัสโครงการ ถ้าสงสัยว่า field ไหนถูกตัดเพราะอะไร:

```python
from app.privacy import sanitize_payload
dropped = []
sanitize_payload(payload, dropped=dropped)
print(dropped)   # [(field, เหตุผล), ...]
```

## ขั้น 5 — เพิ่ม ingestion plan (เมื่อมี public endpoint ที่ดึงได้)

ก่อนเพิ่ม plan ต้องผ่านการอนุมัติ policy ก่อนหนึ่งจังหวะ: source ใหม่เริ่มต้นเป็น
`metadata_only` เสมอ ทีมต้อง review แล้วเพิ่ม `source_id` เข้า `APPROVED_PUBLIC_MODES`
ใน `tools/build_source_catalog.py` และ regenerate catalog (ขั้น 2) — ถ้าเพิ่ม plan
โดย source ยังไม่ถูกอนุมัติเป็น public candidate, `validate-pipeline` จะปฏิเสธว่า
source นั้นไม่ใช่ production-approved

จากนั้นเติม entry ใต้ `sources` ใน `config/ingestion_plans.json` — โครงด้านล่างตรงกับ
connector ที่ scaffold สร้างให้ (ขั้น 4) ซึ่งอ่าน `plan["url"]` เป็น GET หน้าแรก:

```json
"<source_id>": {
  "driver": "<source_id>",
  "connector": "app.connectors.<source_id>:<ClassName>Connector",
  "url": "https://.../api/...",
  "explicit_exclusions": ["endpoint ที่ห้ามเรียก เช่น detail รายบุคคล"]
}
```

ต้นทางที่ pagination หลายหน้า หรือหลาย endpoint ใช้โครงอื่นได้ (`requests`, `datasets`,
`package_show_url` — ดูตัวอย่างจริงใน `config/ingestion_plans.json`) แต่ connector
ต้องอ่าน field เดียวกับที่ plan ประกาศ ถ้าเปลี่ยนโครง plan ต้องแก้ `fetch()` ให้ตรงกันด้วย

Source ที่มีแต่ snapshot (ยังไม่มี public endpoint ให้ดึง) ให้ **ข้ามทั้งขั้น 4 และขั้น 5**
ไปก่อน — `validate-pipeline` บังคับให้ connector contract กับ plan ตรงกันแบบ exact
การ scaffold connector/contract ทิ้งไว้โดยไม่มี plan จะทำให้ validate fail
(`extra=[<source_id>]`) ค่อยกลับมาทำสองขั้นนี้พร้อมกันเมื่อ source เปิด executable ingestion

## ขั้น 6 — ตรวจแล้วเปิด PR

```powershell
python -m app.cli check
```

คำสั่งเดียวรันครบชุดเดียวกับ CI (compile, validate-pipeline, publication validate,
public-repo boundary, pytest) เปิด PR ตาม [CONTRIBUTING.md](../CONTRIBUTING.md)
ผลจาก connector เป็น Candidate เสมอ การเผยแพร่ค่าจริงต้องผ่าน
[Publication workflow](publication-workflow.md) แยกอีกชั้น

## ถาม-ตอบสั้น

- **ข้อมูลครัวเรือน/การเงินที่เว็บรัฐโชว์เอง ดึงได้ไหม?** ได้เฉพาะค่า **aggregate**
  เช่น ยอดรวมรายจังหวัด รายอำเภอ หรือรายพื้นที่ — ข้อมูล**ระดับบุคคลหรือรายครัวเรือน**
  (รายชื่อครัวเรือน รายได้/หนี้สินรายคน สุขภาพ) ต้องเข้า restricted lane (local-only)
  เสมอ แม้เว็บสาธารณะจะแสดงเองก็ตาม การตัดชื่อ เบอร์โทร หรือที่อยู่ออกไม่ทำให้
  record ระดับบุคคลปลอดภัยพอจะเป็น Candidate ใน repo นี้
  (ดูรายการ restricted ที่ตรวจไว้ใน `tests/test_policy.py`)
- **เพิ่ม source แล้ว test จำนวนแหล่งจะพังไหม?** ไม่ — tests นับจาก catalog จริง
  มีแค่ 2 อย่างที่ต้องทำเพิ่ม: โปรไฟล์ Explorer (ขั้น 3) และ (ถ้าเป็นเลน restricted)
  อัปเดตรายการ restricted ใน tests อย่างตั้งใจ
- **รหัสโครงการขึ้นต้นด้วยปี พ.ศ. เช่น `66079123456` โดน redact เป็นเบอร์โทรไหม?**
  ไม่ — รูปแบบ `66` ตามด้วยเลขศูนย์ไม่ตรงรูปเบอร์ไทย และรหัสขึ้นต้น `67` ขึ้นไป
  ไม่โดนอยู่แล้ว แต่ตัวเลขล้วน 10-11 หลักที่ขึ้นต้น `66` แล้วตามด้วยเลข 1-9
  (เช่น `6681234567`) แยกไม่ออกจากเบอร์รูปแบบสากลและยังถูก redact —
  ถ้ารหัสของ source เป็นทรงนั้น อย่าใช้เป็น identity field ให้ใช้ field
  ที่ไม่ใช่ตัวเลขล้วนหรือรหัสที่มีตัวคั่นแทน
