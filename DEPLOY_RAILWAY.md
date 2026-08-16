# Deploy บน Railway พร้อม PostgreSQL

Production ใช้หนึ่ง web service และหนึ่ง PostgreSQL service ใน project เดียวกัน หน้าเว็บไม่ต่อฐานข้อมูลตรงจาก browser; FastAPI ต่อผ่าน private networkแล้วเสิร์ฟ Public API

## Variables ของ web service

~~~text
APP_ENV=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
PUBLIC_DATA_VALUES_ENABLED=false
ALLOW_PENDING_OWNER_SOURCES=false
MAX_RECORDS_PER_SOURCE=10000
SRA_YEAR=2569
~~~

ชื่อ `Postgres` ใน reference ต้องตรงกับชื่อ database service บน Railway ตัวแปรนี้เป็น private service reference ไม่ต้องคัดลอกรหัสผ่านมาใส่ Git

`PUBLIC_DATA_VALUES_ENABLED=false` ปิด operational row payload endpoint แต่ไม่ปิด cleaned public API เพราะ public projection ผ่าน publication gate แยกแล้ว

## สิ่งที่เกิดตอน startup

1. FastAPI เชื่อม PostgreSQL และสร้างตารางที่ยังไม่มี
2. sync metadata ครบ 28 source และ verified endpoint inventory
3. sync cleaned public artifacts 161 ชุดพร้อม content hash
4. `/health` พร้อมเมื่อสัญญา serving ครบเท่านั้น: 28 sources, 141 endpoints, policy 11/12/5 และ public artifacts 161 ชุด

จึงไม่ต้องรัน raw ingestion เพื่อให้ Dashboard เปิดได้ และไม่ต้อง upload raw หลายล้านแถวขึ้น Cloud

## Pre-deploy

~~~powershell
python tools/build_source_catalog.py
python tools/build_learning_dashboard.py
python tools/build_source_insights.py
python tools/build_public_data.py
python tools/build_provincial_briefings.py
python tools/build_executive_summaries.py
python tools/build_source_coverage.py
python -m pytest -q
docker build -t aiat-dashboard-final .
~~~

จากนั้น commit/push repository และ deploy service โดยใช้ `Dockerfile` กับ health check `/health`

## Production verification

- `/health` → `database_backend: postgresql`
- `/api/public/v1/database-coverage` → `status: complete`
- source catalog = 28
- province briefings = 77
- executive summaries = 77
- restricted values published = 0
- `/`, `/insights`, จังหวัดตัวอย่าง และ mobile layout เปิดได้
- operational/debug routes เช่น `/api/sources` ต้องตอบ `404` บน production/PostgreSQL

## Operational API refresh

ตัว collector พร้อมใช้งานผ่าน `python -m app.cli ingest --all` แต่ public projection จะไม่เปลี่ยนอัตโนมัติ การเปิด cron ควรทำเมื่อมี persistent raw storage/manifest retention ก่อน เพื่อไม่ให้ traceability หายเมื่อ container จบงาน

แนะนำลำดับ:

1. mount persistent storage หรือ object storage สำหรับ runtime raw
2. ทดสอบทีละ source
3. ตั้ง cron weekly
4. review/validate candidate rows
5. rebuild public projection และ deploy revision ใหม่

restricted source ไม่เข้า executable plan และถูก block ซ้ำใน ingestion guard

## Raw snapshot

อย่า commit token, signed URL, `.env`, database dump หรือ credential ลง Git ถ้าต้องใช้ snapshot fallback ให้ mount storage และตรวจ SHA-256 กับ manifest ก่อน replay
