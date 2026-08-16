# Deploy Public Evidence Atlas บน Railway

Docker image เดียวเปิด public dashboard, public API และ optional operational ingestion ได้ โดย wallet sources ไม่ถูกบรรจุใน `data/public/`

## Mode A — Public dashboard (แนะนำสำหรับ go-live แรก)

Public projection ถูกเก็บแบบ read-only ใน image จึงไม่ต้องรอ PostgreSQL พร้อม ใช้ SQLite เฉพาะ metadata/runtime ภายใน service:

~~~text
APP_ENV=production
DATABASE_URL=sqlite:///./data/runtime/dashboard.sqlite
PUBLIC_DATA_VALUES_ENABLED=false
ALLOW_PENDING_OWNER_SOURCES=false
MAX_RECORDS_PER_SOURCE=0
SRA_YEAR=2569
~~~

ค่า `PUBLIC_DATA_VALUES_ENABLED=false` ปิดเฉพาะ operational raw-record endpoint; `/api/public/v1/*` และ `/downloads/*` ยังเปิดตามปกติ เพราะเป็น public projection ที่ผ่าน allowlist แล้ว

## Mode B — Full pipeline พร้อม PostgreSQL

เมื่อ database พร้อมและทดสอบ connection แล้ว เปลี่ยนเฉพาะ:

~~~text
DATABASE_URL=${{Postgres.DATABASE_URL}}
~~~

จากนั้นสร้าง scheduled service จาก image เดียวกัน:

- Start command: `python -m app.cli ingest --all`
- Schedule: weekly ในช่วงแรก
- ไม่มี public domain
- ใช้ `DATABASE_URL` เดียวกับ web service

API-first จะ fallback ไป snapshot ตาม policy แต่ scheduler ไม่ทำให้ public projection เปลี่ยนอัตโนมัติ ต้อง build/validate projection และ deploy image ใหม่เพื่อให้ public data เปลี่ยนอย่างตรวจสอบได้

## Railway setup

1. New Project → Deploy from GitHub repo
2. เลือก repository `peetwan/aiat-dashboard-final`
3. ตั้ง variables ตาม Mode A
4. Health check path: `/health`
5. Generate Domain
6. ตรวจหน้า `/`, `/health`, `/api/public/v1/overview` และไฟล์ download อย่างน้อยหนึ่งไฟล์

ถ้าต้องการ Mode B ให้เพิ่ม PostgreSQL service ภายหลัง ไม่จำเป็นต้องลบ service เดิมเพื่อเปิด public dashboard

## Raw snapshot fallback

ไฟล์ raw ขนาดใหญ่ไม่ควรอยู่ใน Git image:

- Mount Railway Volume แล้วตั้ง `SNAPSHOT_ROOT` ไปยัง volume หรือ
- ดาวน์โหลดจาก private object storage เข้า volume และตรวจ SHA-256 กับ manifest

ห้าม commit signed URL, token, `.env`, database หรือไฟล์ credential

## Pre-deploy checklist

1. `python tools/build_public_data.py`
2. ตรวจว่า manifest มี 10 public sources, 77 province boundaries และไม่มี wallet source
3. `python -m pytest -q`
4. `docker build -t aiat-dashboard-final .`
5. ตรวจ desktop/mobile, WebGL fallback, API และ download
6. push GitHub แล้ว deploy
