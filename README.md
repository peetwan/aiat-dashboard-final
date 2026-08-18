# AIAT Provincial Evidence Map

Public dashboard ที่มี source catalog ครบ 28 แหล่ง และ central connector pipeline สำหรับ 6 แหล่งที่เปิด operational ingestion อยู่ในปัจจุบัน แหล่งที่เหลือใช้ snapshot, metadata-only หรือ restricted lane ตาม policy; เมื่อเปิด source เพิ่ม จึงค่อยมี connector และ contract เฉพาะ URL นั้น ส่วนระบบกลางดูแลหลักฐาน ความครบ privacy, versioning และการเขียนฐานข้อมูลแบบเดียวกัน

> ข้อมูลที่เผยแพร่ยังเป็น `candidate`/`needs_review` ไม่ใช่ KPI ที่หน่วยงานรับรอง และระบบไม่เดา grain, หน่วย, ปี หรือจังหวัดเมื่อหลักฐานไม่พอ

## ระบบที่เปิดใช้งาน

| บริการ | URL | หน้าที่ |
|---|---|---|
| Public Dashboard | [aiat-dashboard-web-production.up.railway.app](https://aiat-dashboard-web-production.up.railway.app) | แผนที่ จังหวัด Insights และ Public API |
| Database Explorer | [aiat-database-explorer-production.up.railway.app](https://aiat-database-explorer-production.up.railway.app) | แผนผังตาราง ตัวอย่างข้อมูล และสถานะฐานข้อมูลแบบ read-only |
| GitHub | [peetwan/aiat-dashboard-final](https://github.com/peetwan/aiat-dashboard-final) | Source code, Issues, Pull Requests และ CI |

Production ใช้ Railway project `aiat-dashboard-final` และ PostgreSQL ผ่าน private service reference ปัจจุบันฐานข้อมูลมี source catalog 28 แหล่ง, public artifacts 163 ชุด และ spatial features 194,532 รายการ

Repository ถูกสร้างเริ่มต้นใต้บัญชี `peetwan` แต่ดูแลร่วมกันโดยทีม; `CODEOWNERS` ระบุ co-maintainers ไว้ ส่วน GitHub จะส่งคำขอ review ได้เมื่อบัญชีนั้นยอมรับ collaborator invitation และมีสิทธิ์ใน repository แล้ว การเปลี่ยนแปลงทั้งหมดเข้าผ่าน Pull Request

## สิ่งที่ทำอัตโนมัติ

| เหตุการณ์ | ผลที่เกิดขึ้น |
|---|---|
| เปิด Pull Request | GitHub Actions รัน `pipeline`; ถ้าแตะ Public data จะรัน `publication-gate` กับ revision นั้นด้วย |
| PR ที่ `peetwan` เป็นผู้เขียนผ่าน Codex review | Peet ตรวจว่า review ครอบคลุม head SHA ล่าสุด, ไม่มี P0/P1 ค้าง และ required checks ผ่าน แล้วกด squash merge เองได้โดยไม่ต้องรอ teammate Approve |
| Routine public-data refresh ของ contributor ผ่าน review | Codex/team automation ใส่ `codex-publication-reviewed`; GitHub เปิด squash auto-merge ให้ revision ที่ตรวจแล้วเท่านั้น |
| PR ผ่านและ merge เข้า `main` | Railway auto-deploy Dashboard และ Explorer จาก branch `main` |
| Dashboard เริ่มทำงาน | สร้าง schema ที่ขาด ขยาย `data/public/serving_manifest.json` และ sync reviewed artifacts เข้า serving database แบบ idempotent |
| Explorer เริ่มทำงาน | อ่านฐานข้อมูลเดียวกันเท่านั้น ไม่แก้ข้อมูลและไม่ fetch เว็บไซต์ต้นทาง |
| เว็บไซต์ต้นทางเปลี่ยน | Connector เก็บเป็น Candidate; ยังไม่มีการย้ายเข้า Public หรือเขียน production database อัตโนมัติ |

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

จุดแก้ UI หลักคือ `app/templates/` + `app/static/` สำหรับ Dashboard และ `explorer/templates/` + `explorer/static/` สำหรับ Database Explorer ดู checklist จอกว้าง/มือถือใน [CONTRIBUTING.md](CONTRIBUTING.md)

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
        ↓  deterministic builder + publication contract
contract-declared data/public/* + publication_receipt.json
        ↓  publication-gate + exact-revision review
        ↓  merge → Railway deploy/startup sync
public_artifacts + spatial tables → API / Dashboard / Explorer
```

ระบบ generalize ที่ “ขั้นตอนและกติกา” ไม่ใช่บังคับ schema เดียวกับทุกเว็บ ตัวอย่างเช่น CKAN อาจคืน CSV หลาย resource, Dashboard บางแห่งคืน header-array และ AppTech ใช้ pagination JSON แต่ทั้งหมดต้องประกาศ grain, identity, geography, completeness และ forbidden fields ใน contract รูปแบบเดียวกัน

Dataset/ความหมาย/contract/builder/`serving_manifest.json` ใหม่ต้องให้ทีมตรวจเองก่อน รอบ refresh ถัดไปจึงใช้เลนอัตโนมัติที่เปลี่ยนได้เฉพาะ output เดิมใต้ `data/public/` พร้อม receipt ดูขั้นตอนและความต่างของ manifest ทั้งสามแบบที่ [Publication workflow](docs/publication-workflow.md)

## เพิ่ม Connector หรือ URL

ถ้าเป็นหนึ่งใน 28 แหล่งเดิม ให้ใช้ entry ที่มีอยู่ใน generated `config/source_catalog.json` แล้วเพิ่ม operational pieces ที่ยังขาด หนึ่ง Pull Request ต้องมี:

1. executable plan ใน `config/ingestion_plans.json` เมื่อมี public endpoint ที่ดึงได้
2. connector ใน `app/connectors/`
3. contract ใน `config/connector_contracts/`
4. fixture ขนาดเล็กที่ตัดข้อมูลส่วนบุคคลแล้ว
5. tests สำหรับ happy path, incomplete response และ schema drift

ถ้าเป็นแหล่งลำดับใหม่ที่ยังไม่อยู่ใน 28 แหล่ง ห้ามเพิ่มแถวลง `config/source_catalog.json` ด้วยมือ เพราะไฟล์นี้ generated ต้องให้สมาชิกที่มี evidence workspace เพิ่ม canonical `config/source_registry.json` และ `data/source_audit/<ordinal>_<source_id>/source_card.json` แล้วรัน builder เพื่อส่ง diff ของ catalog/coverage มาพร้อม PR

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
| [เพิ่ม source ใหม่ (Quickstart)](docs/add-new-source.md) | มี URL ใหม่และอยากรู้ทุกขั้นจนเปิด PR ได้ |
| [CONTRIBUTING.md](CONTRIBUTING.md) | workflow branch, PR และ review |
| [Architecture](docs/architecture.md) | เข้าใจ connector, database, Railway และ publication flow |
| [Connector development](docs/connector-development.md) | เพิ่มหรือแก้ URL |
| [Publication workflow](docs/publication-workflow.md) | เลือกเลน release, สร้าง receipt และใช้ auto-merge อย่างปลอดภัย |
| [Data governance](docs/data-governance.md) | ตรวจ classification, privacy และ publication gate |
| [Deployment](docs/deployment.md) | deploy, health check และ rollback |
| [Database Explorer](docs/database-explorer.md) | รันและใช้ Explorer |
| [AGENTS.md](AGENTS.md) | กติกาสำหรับ Codex/AI coding agents |

## โครงสร้าง repository

```text
app/                    FastAPI, database, orchestrator และ connectors
config/                 generated source catalog, ingestion plans และ connector/publication contracts
data/public/            reviewed deployment seeds และ deterministic publication receipt
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
