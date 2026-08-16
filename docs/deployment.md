# Deployment on Railway

Production ใช้ Railway Web Service หนึ่งชุดและ PostgreSQL Service หนึ่งชุดใน project เดียวกัน Browser ติดต่อ FastAPI เท่านั้น; การเชื่อมฐานข้อมูลเกิดผ่าน private network ฝั่ง server

## Environment variables

```text
APP_ENV=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
PUBLIC_DATA_VALUES_ENABLED=false
ALLOW_PENDING_OWNER_SOURCES=false
MAX_RECORDS_PER_SOURCE=10000
SRA_YEAR=2569
```

ชื่อ `Postgres` ต้องตรงกับชื่อ database service บน Railway ตัวแปร `DATABASE_URL` เป็น private service reference และไม่ควรถูกคัดลอกเป็นค่าจริงลง Git

`PUBLIC_DATA_VALUES_ENABLED=false` ปิด operational row payload endpoint แต่ไม่ปิด cleaned Public API เพราะ public projection ใช้ publication gate แยกต่างหาก

## Startup contract

เมื่อ service เริ่มทำงาน ระบบจะ:

1. เชื่อม PostgreSQL และสร้างตารางที่ยังไม่มี
2. Sync metadata 28 sources และ verified endpoint inventory 141 รายการ
3. Sync cleaned public artifacts 161 ชุดพร้อม content hash
4. เปิด `/health` เมื่อ serving contract ครบ: sources 28, policy 11/12/5 และ artifacts 161

Dashboard จึงเปิดได้โดยไม่รัน raw ingestion และไม่ต้อง upload raw records หลายล้านแถวขึ้น Cloud

## Pre-deploy

```powershell
python tools/build_source_catalog.py
python tools/build_learning_dashboard.py
python tools/build_source_insights.py
python tools/build_public_data.py
python tools/build_provincial_briefings.py
python tools/build_executive_summaries.py
python tools/build_source_coverage.py
python -m pytest -q
python ..\scripts\validate_all.py
docker build -t aiat-dashboard-final .
```

ตรวจ Git diff ของ catalog, counts, hashes และ public artifacts ก่อน commit/push จากนั้น Railway ใช้ `Dockerfile` และ health check `/health`

## Production verification

- `/health` รายงาน `database_backend: postgresql`
- `/api/public/v1/database-coverage` รายงาน `status: complete`
- Sources = 28
- Endpoints = 141
- Province briefings = 77
- Executive summaries = 77
- Restricted values published = 0
- SRA target scope = 20, current numeric scores = 15, target-with-null = 5
- Area-Based participant records = 996 และ project–province links = 156 โดยไม่ปน grain
- หน้า `/`, `/insights`, จังหวัดตัวอย่าง และ mobile layout เปิดได้
- หน้า `/province/{code}` โหลด summary, briefing และ operations ครบ; metric/chart แสดงค่า ค้นหา/กรอง/โหลดเพิ่มได้ และ record digest ไม่ dump raw field
- `/api/public/v1/operations` รายงาน connector audit 6/6, 9,652 candidate records และ `automatic_refresh_enabled: false`
- Operational/debug routes เช่น `/api/sources` ตอบ `404` บน production/PostgreSQL

## Operational refresh

Collector ใช้งานผ่าน `python -m app.cli ingest --all` แต่ public projection จะไม่เปลี่ยนอัตโนมัติ Live audit วันที่ 16 สิงหาคม 2569 ผ่าน 6/6 connector รวม 9,652 candidate records; ตัวเลขนี้เป็น records seen ระหว่าง audit ไม่ใช่ public release count

Production ปัจจุบัน **ยังไม่มี daily scheduler** และค่าที่หน้า `/api/public/v1/operations` ต้องคง `automatic_refresh_enabled: false` จนกว่าจะผ่าน operation gate

ลำดับที่แนะนำ:

1. จัด persistent volume หรือ object storage สำหรับ runtime raw/failed manifests
2. กำหนด retention, run lock, alert destination และ bounded retry
3. สร้าง Railway Scheduled Job แยกจาก Web Service; daily probe ตาม `config/operations_policy.json`
4. Full fetch เฉพาะเมื่อ count/hash/watermark เปลี่ยน แล้ว validate schema/count/uniqueness/privacy/freshness
5. เก็บเป็น candidate; owner ตรวจ diff และอนุมัติ
6. Rebuild public projection, รัน tests, commit และ deploy revision ใหม่

Restricted sources ไม่มี executable plan และถูก block ซ้ำใน ingestion guard

## Rollback

1. Roll back Railway deployment ไป revision ที่ผ่าน health check ล่าสุด
2. ห้ามแก้ public artifacts หรือ database rows ด้วยมือเพื่อให้ตัวเลขกลับมา
3. Rebuild artifacts จาก evidence revision เดิมและตรวจ hashes
4. รัน tests แล้ว deploy ใหม่

## Security checklist

- ไม่ commit `.env`, token, signed URL, cookie, API key หรือ database dump
- `data/runtime/`, `data/snapshots/` และ `*.sqlite` ต้องไม่เข้า Git/Docker image
- ตรวจ publication/privacy checklist ใน [Data governance](data-governance.md)
- ตรวจ database coverage หลัง deploy ทุกครั้ง

รายละเอียด data flow อยู่ใน [Architecture](architecture.md)
