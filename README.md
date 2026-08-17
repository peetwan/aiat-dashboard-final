# AIAT Provincial Evidence Map

แดชบอร์ดสาธารณะแบบ map-first สำหรับสำรวจหลักฐานระดับจังหวัดจากแหล่งข้อมูลภาครัฐและมหาวิทยาลัย 28 แหล่ง ระบบแยกข้อมูลตาม grain รักษา provenance และแสดงเฉพาะ projection ที่ผ่าน publication/privacy gate แล้ว โดยไม่เท raw records หรือข้อมูล restricted ขึ้น Cloud

> สถานะข้อมูล: ทุกค่าที่เผยแพร่ยังเป็น `candidate` หรือ `needs_review` ไม่ใช่ KPI ที่รับรองแล้ว และไม่ควรใช้จัดลำดับงบประมาณโดยอัตโนมัติ

## ภาพรวมระบบ

| รายการ | สถานะปัจจุบัน |
|---|---:|
| Source registry | 28 แหล่ง |
| Public candidate | 11 แหล่ง |
| Metadata-only | 12 แหล่ง |
| Restricted local-only | 5 แหล่ง |
| จังหวัด | 77 จังหวัด |
| Public serving artifacts | 163 ชุด |
| Housing spatial features | 194,532 features ใน 4 layers |
| Production database | PostgreSQL บน Railway |
| Local database | SQLite สำหรับพัฒนาและทดสอบ |

Dashboard มีหน้าแผนที่จังหวัด หน้า `/province/{code}` สำหรับข้อมูลจังหวัดฉบับเต็ม หน้า `/insights` สำหรับข้อมูลข้ามจังหวัด/non-geo และ Public API สำหรับ source coverage, province summaries, briefings, สถานะระบบอัปเดต และไฟล์ดาวน์โหลดที่มี provenance

`explorer/` เป็น Database Explorer แบบ read-only สำหรับดูความสัมพันธ์ของทั้ง 28 sources, สิ่งที่นำมาจากแต่ละ URL, grain, endpoints, operational runs และ live Serving Database counts โดย deploy เป็น service/domain แยกใน Railway project เดียวกันและอ่าน PostgreSQL ตัวเดียวกับ Dashboard ดูรายละเอียดที่ [Database Explorer](docs/database-explorer.md)

## โครงสร้างข้อมูลเมื่อเลือกจังหวัด

Province panel แบ่งเป็น 5 แท็บตามคำถามตัดสินใจ ไม่ได้แบ่งตามชื่อระบบต้นทาง:

1. **ภาพรวม** — แสดงเฉพาะข้อมูลของจังหวัดที่เลือก: 3 ตัวเลขหลัก, flow กลุ่มโครงการ–ผู้เข้าร่วม–นวัตกรรม–ทรัพย์สินทางปัญญา–ROI/SROI, กราฟ TRL, ความครบของทะเบียนผลงาน, พื้นที่ระดับอำเภอ และทุนที่ผูกกับนวัตกรรม; ไม่แสดงจำนวนแหล่งข้อมูลในหน้านี้
2. **โครงการและงบ** — กลุ่มโครงการชั่วคราว, ระเบียนผู้เข้าร่วม, หน่วยวิจัย, พื้นที่, นวัตกรรม, ทุนที่ต้นทางกรอก และความพร้อมของผลลัพธ์
3. **คนและพื้นที่** — ครัวเรือน/กลุ่มเป้าหมาย, การช่วยเหลือและ OM ของ SRA-DSS, PPPConnext, เมือง, ที่อยู่อาศัย, วัฒนธรรมและท่องเที่ยว
4. **มิติการพัฒนา** — แยกบริบท/ความต้องการ, ปัจจัยนำเข้า, กิจกรรม, ผลผลิต และผลลัพธ์โดยไม่รวม metric ต่างหน่วย
5. **คุณภาพข้อมูล** — grain, record count, `as_of`, `fetched_at`, quality status, caveat และ URL ต้นทางราย source

UI ใช้หลัก **summary-first**: ค่า KPI และกราฟที่มีตัวเลขกำกับอยู่ก่อนรายละเอียดหลักฐาน ส่วนรายการยาว กฎคุณภาพ และ metadata ราย source เปิดดูเพิ่มได้เมื่อจำเป็น แท็บทั้ง 5 แสดงครบโดยไม่เลื่อนแนวนอนทั้ง desktop และ mobile และการ์ดในแถวเดียวกันรักษาความสูงเท่ากัน

หน้า `/province/{code}` แบ่งข้อมูลฉบับเต็มเป็น 6 section: ภาพรวม, โครงการและผลผลิต, คนและพื้นที่, รายมิติ, ที่มาข้อมูล และรอบอัปเดต แต่ละส่วนเริ่มจาก metric strip, narrative หรือกราฟ แล้วค่อยเปิด record digest ที่เลือกเฉพาะสาระสำคัญและลิงก์ต้นทาง รายการยาวค้นหา กรอง และโหลดเพิ่มได้โดยไม่ dump raw field หรือเปิดข้อมูล restricted

Semantic contract ของ release นี้:

- Area-Based 1,002 แถวเป็น participant/business grain: เชื่อมจังหวัดได้ 996 แถวใน 55 จังหวัด และมี 6 แถวอยู่ unmapped
- จำนวนโครงการเป็น **provisional grouping** จาก `project_name + fiscal_year + research_unit` เพราะต้นทางไม่มี Project ID ทางการ: ได้ 73 กลุ่มไม่ซ้ำ และ 156 project–province links
- SRA-DSS มีทะเบียนเป้าหมาย 20 จังหวัด: 15 จังหวัดมีคะแนนปี 2569 และ 5 จังหวัดอยู่ใน scope แต่คะแนนเป็น `null`; สถานะดังกล่าวไม่ใช่คะแนนศูนย์
- AppTech มีนวัตกรรม 501 รายการและ 555 innovation–province links; 29 รายการเชื่อมหลายจังหวัด เงินทุนจึงเป็น funding attached to innovation ไม่ใช่งบจัดสรร/เบิกจ่ายของจังหวัด
- Public source ทั้ง 11 แหล่งยังเป็น `candidate`/`needs_review`; accepted source = 0 จึงไม่ใช้ตัวเลขเป็น KPI รับรอง
- Connectivity audit วันที่ 16 สิงหาคม 2569 ทดสอบ allowlisted connector สด 6/6 สำเร็จ เห็น candidate records 9,652 ระเบียน แต่ไม่มีผลต่อ public projection จนกว่าจะผ่าน diff/privacy/quality approval
- Production ยังไม่เปิด automatic refresh และไม่ auto-promote ข้อมูล; แผนรอบดึงและ gate อยู่ใน `config/operations_policy.json`

## เริ่มใช้งานบนเครื่อง

ต้องใช้ Python 3.12 ขึ้นไป:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.cli init-db
python -m app.server
```

เปิด `http://localhost:8000` และ OpenAPI explorer ที่ `http://localhost:8000/docs`

`init-db` จะสร้างตาราง, sync catalog 28 แหล่ง, นำ cleaned public artifacts และ Housing spatial 194,532 features เข้า serving database โดยไม่ fetch หรือแก้ raw evidence

## เส้นทางข้อมูล

```text
AIAT evidence workspace
        │
        ├─ public candidate ── clean / validate / summarize
        │                                  │
        │                           data/public/*
        │                                  │
        │                     PostgreSQL / local SQLite
        │                                  │
        │                         FastAPI + MapLibre UI
        │
        ├─ metadata-only ────── source catalog เท่านั้น
        └─ restricted ───────── local-only; ไม่มี values บน Cloud
```

อ่านรายละเอียดที่ [สถาปัตยกรรมและ data workflow](docs/architecture.md)

## Public API หลัก

| Endpoint | เนื้อหา |
|---|---|
| `/health` | สุขภาพระบบและ database backend |
| `/api/public/v1/overview` | ภาพรวม นิยาม metric และคำเตือน |
| `/api/public/v1/sources` | 11 public candidate sources |
| `/api/public/v1/source-coverage` | สถานะครบทั้ง 28 แหล่ง |
| `/api/public/v1/database-coverage` | ความครบของ serving artifacts ใน database |
| `/api/public/v1/operations` | ผลตรวจ connector ล่าสุด รอบดึงที่เสนอ และ publication gate |
| `/api/public/v1/unmapped-records` | ข้อมูลที่ไม่เดาจังหวัดให้เอง |
| `/api/public/v1/provinces/{code}/summary` | Executive summary รายจังหวัด |
| `/api/public/v1/provinces/{code}/briefing` | รายการข้อมูลและ provenance รายจังหวัด |
| `/api/public/v1/source-insights` | ข้อมูลข้ามจังหวัดและ non-geo |
| `/api/public/v1/map/provinces` | GeoJSON ขอบเขต 77 จังหวัด |
| `/api/public/v1/map/cultural-points` | จุดวัฒนธรรมที่ผ่าน public projection |

ไฟล์ดาวน์โหลดอยู่ที่ `/downloads/` เช่น `source_coverage.json`, `province_evidence.csv`, `unmapped_records.json` และ GeoJSON

## สร้าง public artifacts ใหม่

รันตามลำดับหลัง data layer หลักผ่าน validation แล้ว:

```powershell
python tools/build_source_catalog.py
python tools/build_learning_dashboard.py
python tools/build_source_insights.py
python tools/build_public_data.py
python tools/build_provincial_briefings.py
python tools/build_executive_summaries.py
python tools/build_source_coverage.py
python -m pytest -q
```

Builder จะคง `source_id`, grain, unit, `as_of`, quality status และ provenance; ถ้าต้นทางไม่ระบุ ระบบใช้ `null`/`ไม่ระบุ` แทนการเดา

หลัง build ให้รัน regression suite ของ Dashboard และ validator ระดับ workspace:

```powershell
python -m pytest -q
python ..\scripts\validate_all.py
```

Regression suite ตรวจ 77 จังหวัด รวม project/participant grain, SRA scope/null semantics, funding attribution, privacy และ API/UI contract

## เอกสาร

| เอกสาร | ใช้เมื่อ |
|---|---|
| [Architecture](docs/architecture.md) | ต้องการเข้าใจ data flow, database และ update cycle |
| [Data governance](docs/data-governance.md) | ตรวจ publication approval, privacy และ source classification |
| [Data audit](docs/data-audit.md) | ตรวจ coverage, geography, dimensions และข้อจำกัด |
| [Deployment](docs/deployment.md) | deploy หรือ verify ระบบบน Railway/PostgreSQL |
| [Design](docs/design.md) | ทำความเข้าใจ UX contract และเหตุผลด้านการออกแบบ |

## โครงสร้าง repository

```text
app/            FastAPI, database models, API และหน้าเว็บ
config/         source catalog และ ingestion allowlist
data/public/    cleaned deployment seeds ที่ตรวจย้อนกลับได้
docs/           เอกสารหลัก 5 เรื่อง
tests/          data, API, privacy, policy และ UI contracts
tools/          deterministic builders สำหรับ public artifacts
```

## กติกาสำคัญ

- ห้าม commit `.env`, token, cookie, API key, signed URL, database dump หรือ raw payload
- ห้ามนำข้อมูล household, health, financial หรือ person-level ขึ้น Cloud
- `HTTP 200`, `candidate` และ `needs_review` ไม่ได้แปลว่า fact ผ่านการรับรอง
- ห้าม join จังหวัดจากชื่อหน่วยงานหรือบริบทโดยไม่มี exact match/official crosswalk
- Operational ingestion ไม่ promote ข้อมูลเข้า public artifacts อัตโนมัติ

ก่อน deploy ให้อ่าน [Data governance](docs/data-governance.md) และ [Deployment](docs/deployment.md) แล้วรัน test suite ทุกครั้ง
