# dashboard_final

โฟลเดอร์นี้เป็นแอป standalone สำหรับเปลี่ยนข้อมูล audit ให้เป็น database และ dashboard โดยใช้หลัก API-first, snapshot fallback และ policy gate ก่อนขึ้น Railway

ข้อมูลทั้ง 12 source ยังเป็น candidate หรือ needs_review จึงต้องแสดงป้ายสถานะนี้เสมอ เมื่อ 2026-08-16 project owner อนุมัติ publication สำหรับ 10 source สาธารณะ ส่วน wallet 2 source ยังคง restricted local-only ตามกติกาโปรเจกต์

## โครงสร้างสำหรับมือใหม่

~~~text
dashboard_final/
├─ app/                 ตัว FastAPI, database, ingestion และหน้า dashboard
├─ config/              source catalog 12 แหล่ง + executable API plans
├─ data/
│  ├─ snapshots/        raw fallback บนเครื่อง (ไม่ push Git)
│  └─ runtime/          SQLite และ immutable fetch runs (ไม่ push Git)
├─ tools/               สร้าง catalog และเตรียม snapshot จากโปรเจกต์หลัก
├─ tests/               automated safety และ API tests
├─ SOURCE_MATRIX.md     ตารางตัดสินใจต่อ source
├─ WORKFLOW.md          ลำดับงานตั้งแต่ดึงข้อมูลถึง dashboard
├─ DEPLOY_RAILWAY.md    ขั้นตอนเปิด project ใหม่บน Railway
└─ SECURITY.md          กติกาข้อมูลและ approval gate
~~~

## เริ่มบนเครื่อง

ใช้ Python 3.12 แล้วรัน:

~~~powershell
cd dashboard_final
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.cli init-db
uvicorn app.main:app --reload
~~~

เปิด http://localhost:8000

## เตรียม snapshot จากชุด merged เดิม

คำสั่ง default จะเตรียมเฉพาะ snapshot-only, ไม่แตะ wallet และข้ามไฟล์ใหญ่กว่า 50 MB:

~~~powershell
python tools/prepare_snapshots.py
python -m app.cli ingest --source f2_rmutdb --strategy snapshot
~~~

ไฟล์ snapshot และ database ถูก ignore จาก Git เพื่อป้องกันการ push ข้อมูลหรือไฟล์ใหญ่ออกไปโดยไม่ตั้งใจ

## ดึง API

~~~powershell
python -m app.cli ingest --source f2_apptech_mtr
python -m app.cli ingest --source f2_apptech_mru
python -m app.cli ingest --source f2_learning_area_based
python -m app.cli ingest --source f3_housing_portal
python -m app.cli status
~~~

API plan จะเรียกเฉพาะ allowlist ใน config/ingestion_plans.json และจะไม่เรียก endpoint login, person, household หรือ write action

อ่าน WORKFLOW.md ก่อนเปิด ingestion บน Railway และอ่าน DEPLOY_RAILWAY.md เมื่อต้องการสร้าง project ใหม่
