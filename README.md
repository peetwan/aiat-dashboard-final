# AIAT Provincial Evidence Map

Public Executive Dashboard แบบ map-first สำหรับอ่านข้อมูลจังหวัดจาก URL สาธารณะของหน่วยงานรัฐและมหาวิทยาลัย ข้อมูลถูก clean, แยก grain และสรุปก่อนแสดงผล จึงไม่เท raw cell จำนวนมากให้ผู้บริหารตีความเอง

สถานะปัจจุบัน:

- Registry และ database catalog ครบ 28 URL
- 11 source มี public candidate data สำหรับ Dashboard
- 12 source เป็น metadata/discovery เพราะยังไม่มี structured data contract ที่ยืนยันแล้ว
- 5 source เป็น restricted local-only; เผยแพร่เฉพาะ metadata และไม่มีค่าข้อมูลบน Railway
- แผนที่ WebGL ครบ 77 จังหวัด พร้อม briefing และ executive summary จังหวัดละหนึ่งชุด
- Public serving artifacts 161 ชุดถูก sync เข้า PostgreSQL ตอนแอปเริ่มทำงาน
- ข้อมูลทุกชุดยังเป็น `candidate` หรือ `needs_review` ไม่ใช่ KPI หรือคำแนะนำจัดสรรงบอัตโนมัติ

## หน้าเว็บมีอะไร

- แผนที่ประเทศไทยแบบ 2D flat choropleth โทนสว่าง อ่านง่ายสำหรับคนทั่วไป คลิกจังหวัดเพื่ออ่านข้อมูลจริง
- บล็อก "โครงการวิจัยและทุน บพท." ตอบคำถามผู้บริหาร: จำนวนโครงการรายปี/รายหน่วยวิจัย/รายอำเภอ ทุนที่ปรากฏในทะเบียนนวัตกรรม และ drill-down กดอำเภอเพื่อเจอผู้ประกอบการ/กลุ่มเป้าหมายจริง พร้อมระบุตรงๆ ว่าข้อมูลใดที่แหล่งสาธารณะยังไม่มี (PI, สถานะเบิกจ่าย)
- แท็บ "โครงการวิจัย" มีตัวกรองปีงบประมาณ อำเภอ และช่องค้นหาโครงการ/ผู้ประกอบการ
- สรุปสถานการณ์รายมิติ เช่น ที่อยู่อาศัย ความเสี่ยง ทุนดำรงชีพ เมือง โครงการ นวัตกรรม และวัฒนธรรม
- รายการท่องเที่ยวและทุนวัฒนธรรมโหลดเมื่อเปิดดูข้อมูลพื้นที่
- หน้า `/insights` แสดงภาพรวมข้ามจังหวัด, non-geo data, unmapped records และสถานะครบทั้ง 28 URL
- สีและชื่อจังหวัดปรับตามความครอบคลุม โดยไม่ทำให้จังหวัดที่ข้อมูลน้อยรกแผนที่
- ฟอนต์ Anuphan, contrast และ layout สำหรับ desktop/mobile
- Public JSON API, CSV, GeoJSON และไฟล์ดาวน์โหลดพร้อม provenance

## โครงสร้างสำหรับมือใหม่

~~~text
dashboard_final/
├─ app/
│  ├─ main.py              หน้าเว็บและ API routes
│  ├─ models.py            ตาราง PostgreSQL/SQLite
│  ├─ public_artifacts.py  sync serving JSON เข้า database
│  ├─ public_data.py       อ่าน database ก่อน ใช้ไฟล์เป็น fallback
│  ├─ ingestion.py         API allowlist สำหรับ operational refresh
│  ├─ static/              JavaScript และ CSS
│  └─ templates/           หน้า map และ insights
├─ config/
│  ├─ source_catalog.json  metadata/policy ครบ 28 URL
│  └─ ingestion_plans.json API ที่เรียกได้จริงเท่านั้น
├─ data/
│  ├─ public/              cleaned serving artifacts ที่ deploy ได้
│  ├─ snapshots/           local fallback; ไม่ push raw อัตโนมัติ
│  └─ runtime/             local DB และ runtime fetch; ไม่ commit
├─ tools/                  builders สำหรับ clean/join/summarize
├─ tests/                  data, API, policy และ UI contract tests
├─ SOURCE_MATRIX.md        ตารางครบ 28 source
├─ WORKFLOW.md             data flow ฉบับอ่านง่าย
└─ DEPLOY_RAILWAY.md       วิธี deploy พร้อม PostgreSQL
~~~

## เริ่มบนเครื่อง

ใช้ Python 3.12:

~~~powershell
cd dashboard_final
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.cli init-db
python -m app.server
~~~

เปิด `http://localhost:8000`

`init-db` จะสร้างตาราง, sync source catalog 28 แถว และนำ cleaned public artifactsเข้า serving database โดยไม่แตะ raw evidence

## Public Data API

| Endpoint | เนื้อหา |
|---|---|
| `/api/public/v1/overview` | ภาพรวม นิยาม metric และคำเตือน |
| `/api/public/v1/sources` | 11 public candidate sources |
| `/api/public/v1/source-coverage` | สถานะครบทั้ง 28 URL |
| `/api/public/v1/database-coverage` | หลักฐานว่า serving artifacts อยู่ใน database ครบ |
| `/api/public/v1/unmapped-records` | ข้อมูลสาธารณะที่ไม่เดาจังหวัดให้เอง |
| `/api/public/v1/learning-dashboard` | Source 10 แบบ clean พร้อม scope warning |
| `/api/public/v1/provinces/{code}/summary` | สรุปรายมิติสำหรับผู้บริหาร |
| `/api/public/v1/provinces/{code}/briefing` | รายการและ provenance ของจังหวัด |
| `/api/public/v1/source-insights` | ข้อมูลข้ามจังหวัดและ non-geo |
| `/api/public/v1/map/provinces` | GeoJSON ขอบเขต 77 จังหวัด |
| `/api/public/v1/map/cultural-points` | จุดวัฒนธรรมที่ผ่าน public projection |
| `/docs` | OpenAPI explorer |

ไฟล์ cleaned data ดาวน์โหลดได้ที่ `/downloads/` เช่น `source_coverage.json`, `unmapped_records.json`, `province_evidence.csv` และ GeoJSON

## สร้างข้อมูลใหม่

รันตามลำดับจากโฟลเดอร์นี้ หลัง data layer หลักผ่าน validation แล้ว:

~~~powershell
python tools/build_source_catalog.py
python tools/build_learning_dashboard.py
python tools/build_source_insights.py
python tools/build_public_data.py
python tools/build_provincial_briefings.py
python tools/build_executive_summaries.py
python tools/build_source_coverage.py
python -m pytest -q
~~~

อ่าน [WORKFLOW.md](WORKFLOW.md), [SECURITY.md](SECURITY.md) และ [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md) ก่อน deploy
