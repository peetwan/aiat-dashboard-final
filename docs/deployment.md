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
- หน้า `/`, `/insights`, จังหวัดตัวอย่าง และ mobile layout เปิดได้
- Operational/debug routes เช่น `/api/sources` ตอบ `404` บน production/PostgreSQL

## Operational refresh

Collector ใช้งานผ่าน `python -m app.cli ingest --all` แต่ public projection จะไม่เปลี่ยนอัตโนมัติ ก่อนเปิด scheduled refresh ต้องมี persistent storage สำหรับ raw responses และ manifests

ลำดับที่แนะนำ:

1. จัด persistent volume หรือ object storage สำหรับ runtime raw
2. ทดสอบทีละ source
3. ตั้ง schedule หลัง retention/traceability ผ่าน review
4. Validate candidate rows
5. Rebuild public projection และ deploy revision ใหม่

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
