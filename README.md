# AIAT Provincial Evidence Map

Public Executive Dashboard แบบ map-first สำหรับเปิดข้อมูลจริงของแต่ละจังหวัดจากข้อมูลสาธารณะ 10 แหล่ง ผู้ใช้คลิกพื้นที่บนแผนที่สามมิติแล้วระบบเรียก Gold Provincial API เพื่อแสดงตัวชี้วัด โครงการ นวัตกรรม ทุนวัฒนธรรม และแถวข้อมูลจาก URL ต้นทาง

ข้อมูลทั้งหมดในรุ่นนี้ยังเป็น `candidate` หรือ `needs_review` จึงไม่ถูกเรียกว่า KPI และไม่ถูกนำไปรวมเป็นคะแนนแนะนำงบอัตโนมัติ ส่วน `f2_wallet_all_realtime` และ `f2_wallet_cluster_realtime` ถูกตัดออกจาก public projection และคงเป็น local-only

## สิ่งที่มีในหน้าเว็บ

- แผนที่ประเทศไทย 77 จังหวัดแบบ WebGL/3D ด้วย MapLibre GL JS 5.12
- ชื่อจังหวัดบนแผนที่และตัวเลือกค้นหาสำหรับ keyboard/mobile
- Provincial command panel ที่เปิดเมื่อคลิกจังหวัด
- “ข้อมูลสำคัญต่อการตัดสินใจ” ใช้ค่าจริง เช่น house-price-to-income, overcrowding, การผ่านสินเชื่อ และพื้นที่เสี่ยงน้ำท่วม
- รายการชื่อจริงจาก Area-Based, AppTech และ Cultural Map พร้อมรายละเอียดและ URL ต้นทาง
- “ข้อมูลอื่นทั้งหมด” แยกตาม CKAN resource และเปิด Gold JSON ฉบับเต็มได้
- สถานะครบทั้ง 10 URL ว่า `มีข้อมูล`, `ไม่มีรายการจังหวัดนี้` หรือ `ไม่ผูกจังหวัด`
- จุดวัฒนธรรมสาธารณะ 5,258 จุดแบบเปิดปิดได้
- Public JSON API, CSV, GeoJSON และ build manifest พร้อม SHA-256
- Operational API/ingestion/database เดิมสำหรับผู้ดูแลระบบ

## โครงสร้างสำหรับมือใหม่

~~~text
dashboard_final/
├─ app/
│  ├─ main.py             FastAPI routes: public + operations
│  ├─ public_data.py      โหลด public projection แบบ read-only
│  ├─ ingestion.py        API-first + snapshot fallback
│  ├─ database.py         SQLite หรือ PostgreSQL
│  ├─ static/             WebGL UI, CSS และ JavaScript
│  └─ templates/          หน้า Public Evidence Atlas
├─ config/
│  ├─ source_catalog.json ทะเบียน 12 source และ policy
│  └─ ingestion_plans.json allowlist ของ API ที่เรียกได้
├─ data/
│  ├─ public/             ไฟล์ aggregate ที่ push/deploy ได้
│  │  └─ provincial_briefings/ Gold JSON ครบ 77 จังหวัด
│  ├─ snapshots/          raw fallback บนเครื่อง ไม่ push Git
│  └─ runtime/            database/raw fetch runs ไม่ push Git
├─ tools/
│  ├─ build_public_data.py สร้าง map/catalog projection
│  └─ build_provincial_briefings.py สร้าง Gold API data จากค่าจริง
├─ tests/                 API, privacy และ publication tests
├─ WORKFLOW.md            data flow ตั้งแต่ source ถึง dashboard
├─ DEPLOY_RAILWAY.md      วิธี deploy public-only หรือ full pipeline
└─ DESIGN_REFERENCES.md   Mobbin และ public-dashboard references
~~~

## เริ่มบนเครื่อง

ใช้ Python 3.12:

~~~powershell
cd dashboard_final
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.cli init-db
uvicorn app.main:app --reload
~~~

เปิด http://localhost:8000

## Public Data API

| Endpoint | เนื้อหา |
|---|---|
| `/api/public/v1/overview` | summary, metric definitions และ methodology |
| `/api/public/v1/sources` | 10 public sources พร้อม URL/readiness |
| `/api/public/v1/provinces` | public evidence projection รายจังหวัด |
| `/api/public/v1/provinces/{code}` | จังหวัดเดียวด้วยรหัส 2 หลัก |
| `/api/public/v1/provinces/{code}/briefing` | Gold projection: ค่าจริงและรายการครบของจังหวัด |
| `/api/public/v1/map/provinces` | GeoJSON ขอบเขต 77 จังหวัด + metric properties |
| `/api/public/v1/map/cultural-points` | GeoJSON จุดวัฒนธรรม 5,258 จุด |
| `/docs` | OpenAPI explorer |

ไฟล์ดาวน์โหลดอยู่ที่ `/downloads/` ได้แก่ `province_evidence.csv`, `source_inventory.csv`, `cultural_points.geojson`, `thailand_provinces.geojson` และ `manifest.json`

## สร้าง public projection ใหม่

รันจาก workspace หลักที่มี merged evidence:

~~~powershell
python tools/build_public_data.py
python tools/build_provincial_briefings.py
~~~

หากต้องการ refresh ขอบเขตจังหวัดจาก ArcGIS REST ของกรมป้องกันและบรรเทาสาธารณภัย:

~~~powershell
python tools/build_public_data.py --refresh-boundaries
~~~

สอง script จะตรวจ public source ที่อนุมัติ 10 แหล่ง, ขอบเขตครบ 77 จังหวัด และสร้าง Gold JSON พร้อม byte size/SHA-256 รายจังหวัด

## Operational ingestion

~~~powershell
python tools/prepare_snapshots.py
python -m app.cli ingest --source f2_learning_area_based
python -m app.cli ingest --source f3_housing_portal
python -m app.cli status
~~~

ค่า row-level ใน `/api/records?include_payload=true` ยังคงปิดเมื่อ `PUBLIC_DATA_VALUES_ENABLED=false` ส่วน public aggregate API เปิดได้เสมอเพราะผ่าน publication projection แยกแล้ว

ก่อน deploy ให้อ่าน [WORKFLOW.md](WORKFLOW.md), [SECURITY.md](SECURITY.md) และ [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md)
