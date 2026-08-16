# Data workflow สำหรับ Public Evidence Map

## ภาพรวม

~~~text
Registry 28 URL
    |
    +-- 11 public candidate --> immutable evidence --> clean/join/summarize
    |                                                |
    |                                         data/public/*
    |                                                |
    |                                      PostgreSQL serving DB
    |                                                |
    |                                    FastAPI + WebGL dashboard
    |
    +-- 12 metadata-only ----> source status/catalog; ไม่มีค่าที่แต่งขึ้น
    |
    +-- 5 restricted --------> local-only; Cloud มี metadata แต่ไม่มี payload/value
~~~

ไฟล์ `data/public/*` เป็น deployment seed ที่ตรวจย้อนกลับได้ ส่วน API และหน้าเว็บอ่าน `public_artifacts` ใน database ก่อน ไฟล์ทำหน้าที่ fallback เมื่อใช้ CLI ก่อน initialize เท่านั้น

## ชั้นข้อมูล

1. **Evidence** — raw/API/export เดิมอยู่นอก repo Dashboard และไม่ถูกแก้ไข
2. **Clean projection** — builder คง source grain, unit, `as_of`, quality status และ provenance; ถ้าต้นทางไม่ระบุให้เป็น `null/ไม่ระบุ`
3. **Executive serving** — สรุปเฉพาะข้อมูลที่เปรียบเทียบกันได้ แยก geo, non-geo และ unmapped
4. **Database serving** — startup sync 161 JSON artifacts พร้อม SHA-256 เข้า PostgreSQL
5. **Public API/UI** — หน้า map โหลด summary ก่อน แล้วค่อยโหลดรายการเมื่อผู้ใช้เปิดข้อมูลพื้นที่

## Builder order

~~~powershell
python tools/build_source_catalog.py
python tools/build_learning_dashboard.py
python tools/build_source_insights.py
python tools/build_public_data.py
python tools/build_provincial_briefings.py
python tools/build_executive_summaries.py
python tools/build_source_coverage.py
~~~

ผลหลัก:

- `source_catalog.json` — metadata/policy 28 source
- `source_coverage.json` — สถานะ database/API/dashboard ของทุก URL
- `public_dashboard.json` — province profile 77 จังหวัด
- `source_insights.json` — source-level/non-geo analysis
- `unmapped_records.json` — แถวที่ไม่มี province key โดยไม่เดาพื้นที่
- `provincial_briefings/{code}.json` — รายการจริงของจังหวัด
- `executive_summaries/{code}.json` — ข้อมูลย่อยรายมิติ ไม่มี raw table
- GeoJSON 2 ชุด — province polygon และ cultural points

## วิธีตัดสินว่าจะวางข้อมูลที่ไหน

| ลักษณะข้อมูล | ปลายทาง |
|---|---|
| มีรหัส/ชื่อจังหวัดที่ match exact | แผนที่ + provincial summary/briefing |
| เป็น municipality และมี official crosswalk | เก็บ grain เมือง แล้วเชื่อมจังหวัดเพื่อค้นหา |
| ไม่มี geography ที่ยืนยัน | `/insights` หรือ non-geo section |
| จังหวัดว่าง/จับคู่ไม่ได้ | `unmapped_records.json`; ห้ามเติมจากชื่อหน่วยงานเอง |
| มีเฉพาะหน้าเว็บ/metadata | source coverage; ไม่สร้างตัวเลขสมมติ |
| restricted local-only | metadata บน Cloud, values อยู่ local เท่านั้น |

## API refresh workflow

`config/ingestion_plans.json` มี executable allowlist สำหรับ source ที่ endpoint ยืนยันแล้วเท่านั้น ปัจจุบันรวม SRA-DSS, AppTech MTR, AppTech MRU, Learning Dashboard, Area-Based และ Housing Portal

~~~powershell
python -m app.cli ingest --source f2_learning_dashboard
python -m app.cli ingest --all
python -m app.cli status
~~~

`--all` เลือกเฉพาะ public source ที่มี executable plan; metadata-only และ restricted ไม่ถูกเรียก API การ ingest สร้าง immutable runtime response + manifest และเก็บ sanitized rows ใน `dashboard_records` แต่ไม่ promote เข้า public KPI อัตโนมัติ ต้องกลับผ่าน clean/build/test ก่อนเสมอ

## Database contract

- `sources` — 28 rows ตาม registry
- `endpoints` — verified inventory; ไม่มี endpoint ที่เดาขึ้นเอง
- `public_artifacts` — cleaned data ที่ API/Dashboard อ่านจริง
- `dashboard_records` — operational candidate rows จาก API refresh
- `ingestion_runs` — run status, timestamps, counts และ manifest path

ตรวจ serving completeness ที่ `/api/public/v1/database-coverage` ต้องได้ 28 sources, 77 briefings, 77 summaries, restricted values 0 และสถานะ `complete`

## Update cycle

1. เก็บ raw runใหม่ตามกติกา workspace หลัก
2. validate schema, privacy, geography และ provenance
3. รัน builders ตามลำดับ
4. ตรวจ diff ของ values, counts, hashes และ unmapped records
5. รัน tests และ QA desktop/mobile
6. commit/push แล้ว deploy
7. ตรวจ PostgreSQL backend และ database coverage บน production
