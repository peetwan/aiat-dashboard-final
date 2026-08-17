# AIAT Provincial Evidence Map

Public dashboard และ central connector pipeline สำหรับข้อมูลภาครัฐ/มหาวิทยาลัย 28 แหล่ง ข้อมูลแต่ละเว็บไซต์ไม่จำเป็นต้องมีหน้าตาเหมือนกัน: แต่ละ URL มี connector และ contract ของตัวเอง ส่วนระบบกลางดูแลการเก็บหลักฐาน การตรวจความครบ privacy, versioning และการเขียนฐานข้อมูลให้เหมือนกัน

> ข้อมูลที่เผยแพร่ยังเป็น `candidate`/`needs_review` ไม่ใช่ KPI ที่หน่วยงานรับรอง และระบบไม่เดา grain, หน่วย, ปี หรือจังหวัดเมื่อหลักฐานไม่พอ

## ระบบที่เปิดใช้งาน

| บริการ | URL | หน้าที่ |
|---|---|---|
| Public Dashboard | [aiat-dashboard-web-production.up.railway.app](https://aiat-dashboard-web-production.up.railway.app) | แผนที่ จังหวัด Insights และ Public API |
| Database Explorer | [aiat-database-explorer-production.up.railway.app](https://aiat-database-explorer-production.up.railway.app) | แผนผังตาราง ตัวอย่างข้อมูล และสถานะฐานข้อมูลแบบ read-only |
| GitHub | [peetwan/aiat-dashboard-final](https://github.com/peetwan/aiat-dashboard-final) | Source code, Issues, Pull Requests และ CI |

Production ใช้ Railway project `aiat-dashboard-final` และ PostgreSQL ผ่าน private service reference ปัจจุบันฐานข้อมูลมี source catalog 28 แหล่ง, public artifacts 163 ชุด และ spatial features 194,532 รายการ

## สิ่งที่ทำอัตโนมัติ

| เหตุการณ์ | ผลที่เกิดขึ้น |
|---|---|
| เปิด Pull Request | GitHub Actions ตรวจ connector contracts, public-repo safety และ tests |
| PR ผ่านและ merge เข้า `main` | Railway auto-deploy Dashboard และ Explorer จาก branch `main` |
| Dashboard เริ่มทำงาน | สร้าง schema ที่ขาดและ sync เฉพาะไฟล์ใน `data/public/` เข้า serving database แบบ idempotent |
| Explorer เริ่มทำงาน | อ่านฐานข้อมูลเดียวกันเท่านั้น ไม่แก้ข้อมูลและไม่ fetch เว็บไซต์ต้นทาง |
| เว็บไซต์ต้นทางเปลี่ยน | ยังไม่ publish อัตโนมัติ; connector เก็บเป็น Candidate และต้อง review/build/test ก่อน release ใหม่ |

ดังนั้น “merge code แล้ว database เปลี่ยนไหม” มีคำตอบสองแบบ:

- ถ้า PR เปลี่ยน `data/public/` ที่ผ่านการตรวจแล้ว: Dashboard จะ sync revision นั้นเข้าฐานข้อมูลเมื่อ deploy
- ถ้า PR แค่ดึงข้อมูลใหม่เข้า `dashboard_records`: ข้อมูลยังเป็น Candidate และไม่ถูกส่งเข้า Public Dashboard เอง

## เริ่มใช้งานบนเครื่อง

ต้องใช้ Python 3.12 ขึ้นไป:

```powershell
git clone https://github.com/peetwan/aiat-dashboard-final.git
cd aiat-dashboard-final
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.cli init-db
python -m app.server
```

เปิด Dashboard ที่ `http://localhost:8000` และ API docs ที่ `http://localhost:8000/docs`

รัน Database Explorer แยกอีก terminal:

```powershell
python -m explorer.server
```

เปิด `http://localhost:8080`

## Central pipeline

```text
source_catalog.json
        ↓
ingestion_plans.json + connector contract
        ↓
connector เฉพาะ URL ── API / form JSON / CKAN CSV / snapshot
        ↓
central orchestrator ── evidence / hash / manifest / privacy / idempotency
        ↓
dashboard_records (Candidate)
        ↓  review + deterministic builders + tests
data/public/*
        ↓  deploy/startup sync
public_artifacts + spatial tables → API / Dashboard / Explorer
```

ระบบ generalize ที่ “ขั้นตอนและกติกา” ไม่ใช่บังคับ schema เดียวกับทุกเว็บ ตัวอย่างเช่น CKAN อาจคืน CSV หลาย resource, Dashboard บางแห่งคืน header-array และ AppTech ใช้ pagination JSON แต่ทั้งหมดต้องประกาศ grain, identity, geography, completeness และ forbidden fields ใน contract รูปแบบเดียวกัน

## เพิ่ม URL ใหม่

หนึ่ง Pull Request ต้องมี:

1. source entry ใน `config/source_catalog.json`
2. executable plan ใน `config/ingestion_plans.json` เมื่อมี public endpoint ที่ดึงได้
3. connector ใน `app/connectors/`
4. contract ใน `config/connector_contracts/`
5. fixture ขนาดเล็กที่ตัดข้อมูลส่วนบุคคลแล้ว
6. tests สำหรับ happy path, incomplete response และ schema drift

เริ่มจาก `templates/connector/` และอ่าน [คู่มือเพิ่ม Connector](docs/connector-development.md)

คำสั่งตรวจมาตรฐาน:

```powershell
python -m app.cli validate-pipeline
python tools/validate_public_repo.py
python -m pytest -q
```

## เอกสารที่ทีมต้องใช้

| เอกสาร | ใช้เมื่อ |
|---|---|
| [CONTRIBUTING.md](CONTRIBUTING.md) | workflow branch, PR และ review |
| [Architecture](docs/architecture.md) | เข้าใจ connector, database, Railway และ publication flow |
| [Connector development](docs/connector-development.md) | เพิ่มหรือแก้ URL |
| [Data governance](docs/data-governance.md) | ตรวจ classification, privacy และ publication gate |
| [Deployment](docs/deployment.md) | deploy, health check และ rollback |
| [Database Explorer](docs/database-explorer.md) | รันและใช้ Explorer |
| [AGENTS.md](AGENTS.md) | กติกาสำหรับ Codex/AI coding agents |

## โครงสร้าง repository

```text
app/                    FastAPI, database, orchestrator และ connectors
config/                 source registry, ingestion plans และ contracts
data/public/            reviewed deployment seeds
explorer/               read-only Database Explorer
templates/connector/    จุดเริ่มต้น connector ใหม่
tests/                   unit, contract, privacy และ serving tests
tools/                   deterministic builders และ public-repo validator
.github/                 CI, templates, CODEOWNERS และ safe auto-merge
docs/                    architecture และ runbooks ที่ทีมต้องใช้
```

## กติกาหลัก

- ห้าม commit secret, `.env`, cookie, database dump, raw response หรือข้อมูลระบุตัวบุคคล
- Connector คืน Candidate เท่านั้น ห้ามเขียน `public_artifacts` โดยตรง
- Unknown unit, denominator, `as_of` หรือ geography ต้องคงเป็น `null`/`needs_review`
- CI ห้ามเรียก upstream network ให้ใช้ fixture/fake recorder
- ทุกการเปลี่ยนแปลงเข้า `main` ผ่าน Pull Request และ required checks

ดูรายละเอียดทั้งหมดใน [Architecture](docs/architecture.md) และ [CONTRIBUTING.md](CONTRIBUTING.md)
