# Railway deployment

## Production topology

Railway project: `aiat-dashboard-final`, environment: `production`

| Service | URL | Source/role |
|---|---|---|
| `aiat-dashboard-web` | [Dashboard](https://aiat-dashboard-web-production.up.railway.app) | GitHub `main`; FastAPI + serving DB seed writer |
| `aiat-database-explorer` | [Database Explorer](https://aiat-database-explorer-production.up.railway.app) | GitHub `main`; read-only DB viewer |
| Serving PostgreSQL | private network only | ทั้งสอง app ใช้ `DATABASE_URL` reference เดียวกัน |

ห้ามใส่ connection string จริงหรือชื่อ service ที่อาจเปลี่ยนลง Git ให้ตั้งค่าใน Railway Variables:

```text
DATABASE_URL=${{<serving-postgres>.DATABASE_URL}}
APP_ENV=production
```

Dashboard ใช้ตัวแปรเพิ่ม:

```text
PUBLIC_DATA_VALUES_ENABLED=false
ALLOW_PENDING_OWNER_SOURCES=false
MAX_RECORDS_PER_SOURCE=10000
SRA_YEAR=2569
```

Explorer ใช้ `DASHBOARD_URL=https://aiat-dashboard-web-production.up.railway.app`

## Build configuration

- Dashboard: `railway.json` + `Dockerfile`
- Explorer: `railway.explorer.json` + `Dockerfile.explorer`
- ทั้งคู่ health check ที่ `/health`
- ทั้งคู่ deploy จาก branch `main`; การเปลี่ยนแปลง production ต้องเข้าผ่าน PR ที่ required CI ผ่าน

## Database sync ตอน deploy

เฉพาะ Dashboard เป็น writer ตอน startup:

1. สร้างตารางที่ยังขาดโดยไม่ drop ตารางเดิม
2. sync `config/source_catalog.json`
3. sync reviewed artifacts จาก `data/public/`
4. transaction-swap spatial และ housing demand snapshots
5. ตรวจ serving contract ก่อนตอบ health ว่า `ok`

การ sync ใช้ key/hash จึงรันซ้ำได้ และมี PostgreSQL advisory lock กันการ deploy หลาย replica เขียนพร้อมกัน Explorer อ่านอย่างเดียวและไม่ seed database

การ merge connector ใหม่ไม่ทำให้ข้อมูลต้นทางถูก publish เอง ข้อมูลใหม่ต้องผ่าน Candidate → review/build/test → commit `data/public/*` ก่อน

## Pre-merge checks

คำสั่งเหล่านี้รันได้จาก public clone และเป็นชุดเดียวกับ GitHub Actions:

```powershell
python -m app.cli validate-pipeline
python tools/validate_public_repo.py
python -m pytest -q
docker build -t aiat-dashboard-final .
docker build -f Dockerfile.explorer -t aiat-database-explorer .
```

การ rebuild public release จาก raw evidence ทั้งหมดเป็น maintainer workflow ภายนอก public repo ผู้ทำ application/connector PR ไม่ต้องมี raw data ชุดนั้น

## Verify production

หลัง merge ให้ตรวจ:

- [Dashboard `/health`](https://aiat-dashboard-web-production.up.railway.app/health) คืน `status=ok`, `database_backend=postgresql`
- [Database coverage](https://aiat-dashboard-web-production.up.railway.app/api/public/v1/database-coverage) คืน `status=complete`
- [Explorer `/health`](https://aiat-database-explorer-production.up.railway.app/health) เห็น source count 28
- Dashboard และ Explorer เห็น counts หลักตรงกัน
- restricted values published = 0
- หน้า `/`, `/insights` และจังหวัดตัวอย่างเปิดได้

ณ 17 สิงหาคม 2569 serving contract คือ public artifacts 163 ชุด, spatial features 194,532 และ housing demand records 25,919

## Source refresh

Production ยังไม่เปิด source scheduler และ Web Service ไม่ fetch upstream ตอน startup, health check หรือ page request

เมื่อจะเปิด schedule ต้องสร้าง service/job แยก โดยมีอย่างน้อย:

- persistent evidence storage และ immutable manifest
- one-run lock, bounded retry และ timeout
- schema/count/uniqueness/privacy checks
- alert เมื่อ connector fail หรือ schema/count drift
- manual publication gate; ห้าม auto-promote Candidate

## Rollback

1. Roll back app deployment ไป commit ที่ผ่าน health check ล่าสุด
2. อย่าแก้ database rows หรือ public artifacts ด้วยมือ
3. ถ้าเป็น data release ให้ rebuild จาก evidence revision เดิม รัน tests และ deploy commit ใหม่
4. ตรวจ `/health` และ `/api/public/v1/database-coverage` อีกครั้ง

กติกา data flow อยู่ใน [Architecture](architecture.md) และ publication gate อยู่ใน [Data governance](data-governance.md)
