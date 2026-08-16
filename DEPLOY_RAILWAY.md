# Deploy บน Railway project ใหม่

โครงนี้พร้อม build ด้วย Dockerfile และมี health check ที่ /health; project-owner approval ของ 10 source ถูกบันทึกแล้ว ส่วน wallet 2 source ไม่ถูก deploy

## 1. Push เป็น GitHub repository

ตรวจให้แน่ใจว่า .env, data/snapshots, data/runtime และ database ไม่อยู่ใน commit

## 2. สร้าง Railway project และ PostgreSQL

ผ่านหน้า Railway:

1. New Project → Deploy from GitHub repo
2. เลือก repository นี้
3. Add Service → Database → PostgreSQL
4. ที่ web service ตั้ง DATABASE_URL ให้ reference ตัวแปร DATABASE_URL ของ PostgreSQL service
5. Generate Domain และตรวจ /health

หรือใช้ CLI:

~~~powershell
railway login
railway init
railway add --database postgres
railway up
~~~

## 3. Variables ของ web service

~~~text
APP_ENV=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
PUBLIC_DATA_VALUES_ENABLED=false
ALLOW_PENDING_OWNER_SOURCES=false
MAX_RECORDS_PER_SOURCE=10000
SRA_YEAR=2569
~~~

อย่าใส่ค่า secret ลง GitHub หรือเอกสาร

## 4. Scheduled ingestion service

สร้าง service ที่สองจาก repo เดียวกันสำหรับ scheduled ingestion:

- Start command: python -m app.cli ingest --all
- Schedule: เริ่ม weekly ก่อน แล้วค่อยปรับตาม maintenance policy
- ใช้ DATABASE_URL เดียวกับ web service
- API-first จะ fallback ไป snapshot เมื่อ API ล้มเหลว

Cron service ไม่ควรเปิด public domain

## 5. Raw snapshot fallback

ไฟล์ใหญ่ไม่ควรอยู่ใน Git image ใช้หนึ่งในสองแบบ:

- Mount Railway Volume แล้วตั้ง SNAPSHOT_ROOT เป็น path ของ volume
- เก็บใน private object storage แล้วทำ one-time download เข้า volume โดยตรวจ SHA-256 จาก manifest

ตัวอย่างรูปแบบ manifest อยู่ที่ data/snapshot_manifest.example.json อย่า commit signed URL

## 6. Go-live gate

ก่อนเปิดค่าจริง:

1. ยืนยันว่าเป็นหนึ่งใน 10 source ที่ production_values_allowed=true
2. ยืนยันว่าไม่ใช่ wallet/household restricted lane
3. deploy ใหม่
4. ingest source นั้น
5. ตรวจ record count, manifest และ privacy projection
6. ตั้ง PUBLIC_DATA_VALUES_ENABLED=true โดยคง needs_review label
