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

เติม entry ใต้ `sources` ใน `config/ingestion_plans.json` ตามโครงนี้ แล้วปรับ
request ให้ตรงกับที่ public frontend เรียกจริง:

```json
"<source_id>": {
  "driver": "<source_id>",
  "connector": "app.connectors.<source_id>:<ClassName>Connector",
  "requests": [
    {"url": "https://.../api/...", "params": {"page": "$PAGE"}}
  ],
  "explicit_exclusions": ["endpoint ที่ห้ามเรียก เช่น detail รายบุคคล"]
}
```

Source ที่มีแต่ snapshot ยังไม่ต้องมี plan — ระบบรองรับ snapshot fallback อยู่แล้ว

## ขั้น 6 — ตรวจแล้วเปิด PR

```powershell
python -m app.cli check
```

คำสั่งเดียวรันครบชุดเดียวกับ CI (compile, validate-pipeline, publication validate,
public-repo boundary, pytest) เปิด PR ตาม [CONTRIBUTING.md](../CONTRIBUTING.md)
ผลจาก connector เป็น Candidate เสมอ การเผยแพร่ค่าจริงต้องผ่าน
[Publication workflow](publication-workflow.md) แยกอีกชั้น

## ถาม-ตอบสั้น

- **ข้อมูลครัวเรือน/การเงินที่เว็บรัฐโชว์เอง ดึงได้ไหม?** ได้ — เก็บเป็น Candidate
  ตามปกติ กติกา privacy ตัดเฉพาะชื่อบุคคล เบอร์โทร อีเมล ที่อยู่บ้าน และเลขบัตร
- **เพิ่ม source แล้ว test จำนวนแหล่งจะพังไหม?** ไม่ — tests นับจาก catalog จริง
  มีแค่ 2 อย่างที่ต้องทำเพิ่ม: โปรไฟล์ Explorer (ขั้น 3) และ (ถ้าเป็นเลน restricted)
  อัปเดตรายการ restricted ใน tests อย่างตั้งใจ
- **รหัสโครงการขึ้นต้นด้วย 66/67 โดน redact เป็นเบอร์โทรไหม?** ไม่แล้ว —
  ตัว redact เบอร์โทรตรวจรูปแบบเบอร์ไทยจริงเท่านั้น
