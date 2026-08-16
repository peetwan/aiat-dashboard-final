# Architecture and data workflow

เอกสารนี้อธิบายขอบเขตระบบ เส้นทางข้อมูล โครงสร้างฐานข้อมูล และวิธีอัปเดต AIAT Provincial Evidence Map

## System boundary

Repository นี้เป็น **public serving application** ไม่ใช่ evidence lake หลัก การเก็บ raw, การทำ source audit และการตัดสิน semantic gate เกิดใน AIAT evidence workspace ภายนอก repo นี้ จากนั้นจึงสร้าง cleaned deployment seeds ใน `data/public/`

```text
Source registry 28 แหล่ง
        │
        ├─ 11 public candidate ── evidence → clean → validate → summarize
        │                                              │
        │                                       data/public/*
        │                                              │
        │                                   public_artifacts table
        │                                              │
        │                                      FastAPI + MapLibre
        │
        ├─ 12 metadata-only ───── source status/catalog; ไม่มีค่าข้อมูล
        └─ 5 restricted ───────── local-only; Cloud มี metadata เท่านั้น
```

ไฟล์ `data/public/*` เป็น deployment seeds ที่มี provenance และ content hash เมื่อแอปเริ่มทำงาน ระบบจะ sync ไฟล์เหล่านี้เข้า database และ API จะอ่านจาก database ก่อน ไฟล์เป็น fallback สำหรับ CLI/local bootstrap เท่านั้น

## Data layers

1. **Evidence** — raw/API/export เดิมอยู่นอก repo Dashboard และเป็น immutable
2. **Clean projection** — builder รักษา source grain, unit, `as_of`, quality status และ provenance
3. **Executive serving** — แยกข้อมูลที่ผูกจังหวัด, non-geo และ unmapped โดยไม่เดา join key พร้อม semantic projection ระดับ `Need → Input → Activity → Output → Outcome`
4. **Database serving** — sync 161 JSON artifacts พร้อม SHA-256 เข้า PostgreSQL หรือ SQLite
5. **Public API/UI** — โหลด summary ก่อน แล้วโหลดรายละเอียดเมื่อผู้ใช้เลือกพื้นที่

ค่าไม่ทราบใช้ `null`/`ไม่ระบุ`; ระบบไม่แทน null ด้วยศูนย์และไม่สร้าง composite score จาก metric ต่างหน่วย โดยเฉพาะ:

- SRA target scope แยกจาก score availability: 20 จังหวัดอยู่ในทะเบียนเป้าหมาย แต่มีคะแนนปัจจุบัน 15 จังหวัด
- Area-Based participant rows แยกจาก provisional project groups; map และ summary ใช้ `area_based_project_groups` ไม่ใช้ participant count เป็นจำนวนโครงการ
- Funding ที่ผูกกับนวัตกรรมหลายจังหวัดไม่ถูกตีความเป็น provincial allocation และห้ามรวมยอดรายจังหวัดเป็นยอดประเทศ

## Database design

ระบบใช้ SQLAlchemy schema เดียวกันทั้ง PostgreSQL และ SQLite:

| Table | หน้าที่ | Key/constraint สำคัญ |
|---|---|---|
| `sources` | Registry, readiness และ publication policy ของ 28 แหล่ง | `source_id` เป็น primary key |
| `endpoints` | Verified endpoint inventory และ runtime allowlist | `endpoint_id`; FK ไป `sources` |
| `public_artifacts` | Cleaned payload ที่ Public API/Dashboard อ่านจริง | `artifact_key`; index ตาม group และ province |
| `dashboard_records` | Operational candidate rows จากการ refresh API | unique ตาม source, dataset, record ID และ record hash |
| `ingestion_runs` | สถานะ run, counts, timestamps และ manifest path | `run_id`; FK ไป `sources` |

`public_artifacts` และ `dashboard_records` มีหน้าที่ต่างกัน: ตารางแรกคือ serving projection ที่ผ่าน clean/build/test แล้ว ส่วนตารางหลังเป็น candidate staging จาก operational refresh และไม่ถูก promote สู่ public API อัตโนมัติ

Production ใช้ PostgreSQL ผ่าน `DATABASE_URL`; local default ใช้ `data/runtime/dashboard.sqlite` ซึ่งถูก ignore จาก Git

## Public artifact groups

- `source_catalog.json` — metadata/policy ครบ 28 แหล่ง
- `source_coverage.json` — สถานะ database/API/dashboard ของทุก URL
- `public_dashboard.json` — province profile 77 จังหวัด
- `source_insights.json` — source-level และ non-geo analysis
- `unmapped_records.json` — แถวที่ไม่มี province key โดยไม่เดาพื้นที่
- `provincial_briefings/{code}.json` — รายการข้อมูลรายจังหวัด รวม `project_master`, participant records, SRA activity, innovation/IP/ROI/SROI และ source-level provenance
- `executive_summaries/{code}.json` — สรุป 5 แท็บ, research portfolio, `decision_chain`, `data_quality_overview` และข้อมูลรายมิติ
- GeoJSON — ขอบเขตจังหวัดและ cultural points

## Geography rules

| ลักษณะข้อมูล | ปลายทาง |
|---|---|
| มีรหัส/ชื่อจังหวัดที่ exact match | แผนที่และ province summary/briefing |
| เป็นเทศบาลและมี official crosswalk | คง grain เมืองและเชื่อมจังหวัดเพื่อค้นหา |
| ไม่มี geography ที่ยืนยัน | `/insights` หรือ non-geo section |
| จังหวัดว่างหรือจับคู่ไม่ได้ | `unmapped_records.json` |
| มีเพียงหน้าเว็บ/metadata | source coverage; ไม่สร้าง record/KPI |
| restricted local-only | metadata บน Cloud; values อยู่ local เท่านั้น |

## Build order

```powershell
python tools/build_source_catalog.py
python tools/build_learning_dashboard.py
python tools/build_source_insights.py
python tools/build_public_data.py
python tools/build_provincial_briefings.py
python tools/build_executive_summaries.py
python tools/build_source_coverage.py
```

หลัง build ต้องตรวจ diff ของ values, counts, hashes และ unmapped records แล้วรัน `python -m pytest -q`

Release ปัจจุบันมี 77 briefings + 77 executive summaries และ regression contract ตรวจว่า 996 participant rows ไม่ถูกนับเป็น 996 โครงการ, 156 project–province links ตรงกันทุก projection และ SRA `null` ไม่ถูกแทนด้วยศูนย์

## Operational refresh

`config/ingestion_plans.json` เป็น executable allowlist สำหรับ source ที่ยืนยัน endpoint แล้วเท่านั้น:

```powershell
python -m app.cli ingest --source f2_learning_dashboard
python -m app.cli ingest --all
python -m app.cli status
```

`--all` เลือกเฉพาะ public source ที่มี executable plan; metadata-only และ restricted ไม่ถูกเรียก API ทุก response ถูกเก็บพร้อม run manifest ใน runtime storage และแถว sanitized ถูกเขียนเข้า `dashboard_records`

## Update cycle

1. เก็บ raw run ใหม่ใน evidence workspace
2. Validate schema, privacy, geography และ provenance
3. รัน builders ตามลำดับ
4. ตรวจ diff และ data audit
5. รัน tests และ QA desktop/mobile
6. Commit/push และ deploy
7. ตรวจ PostgreSQL backend กับ `/api/public/v1/database-coverage`

รายละเอียด publication/privacy gate อยู่ใน [Data governance](data-governance.md) และคำสั่ง production อยู่ใน [Deployment](deployment.md)
