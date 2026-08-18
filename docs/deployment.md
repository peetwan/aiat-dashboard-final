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
3. ขยาย `data/public/serving_manifest.json` แล้วตรวจ path, `source_ids` และ privacy ของ payload ทุกชุดก่อนแก้ `public_artifacts`
4. transaction-swap spatial และ housing demand snapshots
5. ตรวจ serving contract ที่ derive expected artifact/group counts จาก manifest ก่อนตอบ health ว่า `ok`

การ sync ใช้ key/hash จึงรันซ้ำได้ และมี PostgreSQL advisory lock กันการ deploy หลาย replica เขียนพร้อมกัน Explorer อ่านอย่างเดียวและไม่ seed database

การ merge connector ใหม่ไม่ทำให้ข้อมูลต้นทางถูก publish เอง Dataset/contract/builder/`serving_manifest.json` ใหม่ต้องผ่าน team review ก่อน ส่วน routine refresh ใช้ output เดิมตาม contract, receipt และ exact-revision review ตาม [Publication workflow](publication-workflow.md)

## Pre-merge checks

สามคำสั่งแรกเป็น required CI ที่ GitHub Actions รันจาก public clone:

```powershell
python -m app.cli validate-pipeline
python tools/validate_public_repo.py
python -m pytest -q
```

ถ้าเป็น routine public-data refresh ให้สร้าง receipt หลัง builder แล้วตรวจ release เพิ่ม:

```powershell
python -m app.cli publication receipt
python -m app.cli publication validate
```

GitHub รัน check `publication-gate` กับ head SHA ของ PR ถ้า `peetwan` เป็น PR author ให้ตรวจว่า Codex review ครอบคลุม head ล่าสุด ไม่มี P0/P1/conversation ค้าง และ `pipeline` กับ `publication-gate` ผ่าน แล้วกด squash merge เองได้โดยไม่ต้องรอ teammate Approve ส่วน PR ของ contributor ยังใช้ผู้ตรวจที่ไม่ใช่ author ใส่ `codex-publication-reviewed`; privileged workflow ตรวจ checks, label actor และ revision ซ้ำก่อนเปิด squash auto-merge

สองคำสั่งต่อไปเป็น local Docker build smoke test ที่แนะนำเมื่อแก้ Dockerfile/deployment config แต่ยังไม่ใช่ job ใน GitHub Actions ปัจจุบัน:

```powershell
docker build -t aiat-dashboard-final .
docker build -f Dockerfile.explorer -t aiat-database-explorer .
```

การ rebuild public release จาก raw evidence ทั้งหมดต้องใช้ evidence workspace ภายนอก public repo สมาชิกทีมที่ได้รับไฟล์ชุดนั้นตั้ง `AIAT_EVIDENCE_ROOT` แล้วรัน deterministic builder ได้ ผู้ทำ application/UI/connector PR ไม่ต้องมี raw data ชุดนั้น

## Verify production

หลัง merge ให้ตรวจ:

- [Dashboard `/health`](https://aiat-dashboard-web-production.up.railway.app/health) คืน `status=ok`, `database_backend=postgresql`
- [Database coverage](https://aiat-dashboard-web-production.up.railway.app/api/public/v1/database-coverage) คืน `status=complete`
- [Explorer `/health`](https://aiat-database-explorer-production.up.railway.app/health) เห็น source count 28
- Dashboard และ Explorer เห็น counts หลักตรงกัน
- restricted values published = 0
- หน้า `/`, `/insights` และจังหวัดตัวอย่างเปิดได้

Scheduled Codex/team automation ตรวจผล deploy และ health ได้ แต่ไม่เรียก production ingestion และไม่เขียน PostgreSQL โดยตรง Database เปลี่ยนเฉพาะเมื่อ Dashboard startup sync commit ที่ merge แล้ว

ณ 17 สิงหาคม 2569 serving contract คือ public artifacts 163 ชุด, spatial features 194,532 และ housing demand records 25,919

## Source refresh

Production ยังไม่เปิด source scheduler และ Web Service ไม่ fetch upstream ตอน startup, health check หรือ page request

เมื่อจะเปิด schedule ต้องสร้าง service/job แยก โดยมีอย่างน้อย:

- persistent evidence storage และ immutable manifest
- one-run lock, bounded retry และ timeout
- schema/count/uniqueness/privacy checks
- alert เมื่อ connector fail หรือ schema/count drift
- เปิด PR ผ่าน publication contract/gate; ห้าม auto-promote Candidate หรือเขียน production database จาก scheduled job

Schedule จะรันทุกกี่ชั่วโมงก็ได้ตาม freshness ของ source แต่ผล fetch ต้องหยุดที่ Candidate/immutable evidence จากนั้น deterministic builder จึงเปิด routine refresh PR ส่วน URL/dataset/ความหมาย/contract ใหม่และไฟล์ใต้ `data/spatial/` หรือ `data/demand/` ยังต้องให้ทีมตรวจเอง

## Rollback

1. Roll back app deployment ไป commit ที่ผ่าน health check ล่าสุด
2. อย่าแก้ database rows หรือ public artifacts ด้วยมือ
3. ถ้าเป็น data release ให้ rebuild จาก evidence revision เดิม รัน tests และ deploy commit ใหม่
4. ตรวจ `/health` และ `/api/public/v1/database-coverage` อีกครั้ง

กติกา data flow อยู่ใน [Architecture](architecture.md) และ publication gate อยู่ใน [Data governance](data-governance.md)
