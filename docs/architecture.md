# Architecture

เอกสารนี้อธิบายว่า repository ทำอะไร ข้อมูลจาก URL ที่ต่างกันมากเข้า pipeline กลางอย่างไร ฐานข้อมูลแบ่งหน้าที่แบบไหน และ Railway deploy อะไรอัตโนมัติ

## 1. ขอบเขตระบบ

Repository นี้มี 3 หน้าที่:

1. เป็น Public Dashboard/API ที่อ่านเฉพาะข้อมูลซึ่งผ่าน publication gate แล้ว
2. เป็น framework สำหรับเพิ่ม connector ราย URL ผ่าน Pull Request
3. เป็น deployment seed สำหรับ serving database บน Railway

Repository นี้ไม่ใช่ raw data lake หลัก Raw evidence และ audit history ขนาดใหญ่อยู่ใน evidence workspace ภายนอก public repo เพื่อนร่วมทีม clone repo นี้แล้วพัฒนา connector, รัน tests, เปิด Dashboard และสร้าง local serving database ได้โดยไม่ต้องมี raw workspace สมาชิกทีมที่มี key อ่านของ team evidence bucket ดึง run ลงเครื่องด้วย `tools/evidence_pull.py` แล้วชี้ builder ไปที่ root นั้นด้วย `AIAT_EVIDENCE_ROOT` (ดู [evidence-storage.md](evidence-storage.md))

ขอบเขตปัจจุบันคือ catalog 28 แหล่ง แต่มี executable plans/connectors/contracts 6 แหล่ง แหล่งอื่นใช้ reviewed snapshot, metadata-only หรือ restricted lane จนกว่าจะเพิ่ม operational connector พร้อม contract และ tests

## 2. ภาพรวม component

```text
                 ┌──────────────────────────────────────┐
28 source URLs → │ Catalog 28 + executable plans 6      │
                 └──────────────────┬───────────────────┘
                                    │
                  ┌─────────────────▼─────────────────┐
                  │ Connector เฉพาะ 6 executable URLs │
                  │ JSON / form / CKAN                 │
                  └─────────────────┬─────────────────┘
                                    │ Candidate datasets
                  ┌─────────────────▼─────────────────┐
                  │ Central ingestion orchestrator    │
                  │ evidence, hash, manifest, privacy │
                  │ completeness, idempotent DB write │
                  └───────────┬───────────────────────┘
                              │
                     dashboard_records
                              │ ไม่มี auto-promote
                  ┌───────────▼───────────────────────┐
                  │ Review + deterministic builders  │
                  │ semantic / geography / privacy   │
                  └───────────┬───────────────────────┘
                              │
                         data/public/*
                              │ deploy/startup sync
                  ┌───────────▼───────────────────────┐
                  │ Shared PostgreSQL serving DB      │
                  └──────────────┬───────────────┬────┘
                                 │               │
                         Public Dashboard    DB Explorer
                           read + seed         read-only
```

## 3. Generalize ตรงไหน และแยกราย URL ตรงไหน

ข้อมูลของแต่ละเว็บอาจต่างกันโดยสิ้นเชิง จึงไม่ควรสร้าง parser ใหญ่ตัวเดียวที่มี `if/elif` ตามชื่อ source

| ส่วนที่ใช้ร่วมกัน | ส่วนที่ต้องแยกราย URL |
|---|---|
| source registry และ policy | request method, headers และ body ที่เว็บต้องการ |
| run ID, timestamps, response hash และ manifest | pagination และตำแหน่ง records ใน response |
| retry/failure rules | schema และ dataset keys |
| privacy projection และ secret scan | grain และ stable identity |
| record version/idempotency | geography fields และ source-specific crosswalk |
| Candidate/Public separation | completeness checks ของเว็บนั้น |
| CI และ PR checklist | fixture และ schema-drift tests |

ทุก executable source จึงมีคู่ไฟล์:

- `app/connectors/<source>.py` — วิธีคุยและ parse เว็บไซต์นั้น
- `config/connector_contracts/<source>.json` — สัญญาว่าข้อมูลคืออะไรและตรวจครบอย่างไร

`config/ingestion_plans.json` ชี้ `connector` ด้วย importable entrypoint ส่วน `app/ingestion.py` เป็น orchestrator กลางและไม่ต้องรู้รายละเอียด payload ของทุกเว็บ

## 4. Source states

`config/source_catalog.json` เป็น generated serving catalog ของ 28 แหล่งและแยก publication policy ดังนี้; canonical `config/source_registry.json` กับ source cards อยู่ใน evidence workspace และเป็น input ตอน regenerate:

- `public_candidate` 11 แหล่ง — มี reviewed projection ที่อนุญาตให้แสดงพร้อมคำเตือน
- `metadata_only` 12 แหล่ง — แสดงชื่อ URL และสถานะ แต่ยังไม่เอาค่าข้อมูลขึ้น Dashboard
- `restricted_local_only` 5 แหล่ง — Cloud เก็บ metadata เท่านั้นและไม่มี executable public connector

การมี HTTP 200 หรือดึงข้อมูลได้ไม่เปลี่ยน source ให้เป็น accepted KPI โดยอัตโนมัติ

## 5. Data flow สองเลน

### Operational lane

```text
URL → connector → evidence/manifest → sanitize → dashboard_records
```

ใช้ตรวจ connectivity และเก็บ Candidate เวอร์ชันใหม่ ตารางนี้ไม่ใช่ข้อมูลที่ Public API อ่าน

### Publication lane

```text
immutable evidence → deterministic builders → contract-declared data/public/*
publication contracts ───────────────┘                 ↓
                                        publication_receipt.json
                                                  ↓
                           publication-gate + exact-revision review
                                                  ↓
                         merge → Railway startup sync → public_artifacts
```

ไม่มี code path ที่ copy `dashboard_records` ไป `public_artifacts` เอง Publication contract ประกาศ grain, identity, geography, `as_of`, unit/denominator, completeness, privacy และ output ของแต่ละ dataset ส่วน `serving_manifest.json` ระบุ artifact ที่ Dashboard นำเข้า database แต่ละ seed loader ตรวจ manifest/hash/privacy ของ seed นั้นก่อนเริ่มแก้ rows ของตารางชุดนั้น; การรวมทุก seed เป็น transaction เดียวเป็นงาน hardening แยกต่างหาก

การเพิ่ม URL/dataset/ความหมาย/contract/builder/`serving_manifest.json` ใหม่ รวมถึง `data/spatial/` และ `data/demand/` ต้องให้ทีมตรวจเอง Routine refresh เปลี่ยนได้เฉพาะ output ที่ contract เดิมประกาศใต้ `data/public/` พร้อม deterministic receipt; CI และผู้ตรวจผูกการอนุมัติกับ commit SHA นั้น Runtime ยอมรับเฉพาะ source ที่ catalog อนุมัติ โดย preflight `data/public` ทั้ง release ก่อน sync และให้ spatial/demand loader ตรวจ seed ของตนก่อนแก้ตารางของ seed นั้น

## 6. Database design

SQLAlchemy ใช้ schema เดียวกันบน PostgreSQL (production) และ SQLite (local):

| Table | หน้าที่ |
|---|---|
| `sources` | registry และ policy ของ 28 sources |
| `endpoints` | verified endpoints และ runtime allowlist |
| `ingestion_runs` | สถานะ/count/timestamps ของการดึงแต่ละรอบ |
| `dashboard_records` | Candidate records จาก operational ingestion |
| `public_artifacts` | reviewed JSON payload ที่ Dashboard/API อ่านจริง |
| `spatial_layer_snapshots` | manifest ของ public spatial layer |
| `spatial_features` | features ที่ผ่าน privacy projection |
| `housing_demand_snapshots` | manifest ของ Housing demand release |
| `housing_demand_records` | demand rows ที่ตัด source identifier/contact แล้ว |

Housing live connector ไม่ดาวน์โหลด respondent CSV ของ `demand` และไม่โหลด `policy-assessment`; connector ใช้ demand package เพื่อยืนยัน schema/resource count เท่านั้น ส่วน `housing_demand_records` ใน serving database มาจาก pre-redacted reviewed artifact คนละ publication lane

ความสัมพันธ์หลัก:

```text
sources 1 ── many endpoints
sources 1 ── many ingestion_runs
sources 1 ── many dashboard_records
sources 1 ── many spatial/demand rows
public_artifacts แยกจาก Candidate lane โดยตั้งใจ
```

JSON ใน `public_artifacts.payload` คือ cleaned projection หนึ่งชุด ไม่ใช่ raw JSON dump ทั้งเว็บไซต์ แต่ละแถวมี `artifact_key`, group, province code (ถ้ามี), source path และ SHA-256 เพื่อ sync แบบ idempotent ส่วน `source_ids` เป็น provenance/publication gate ใน serving manifest ปัจจุบัน ไม่ใช่คอลัมน์ในตาราง `public_artifacts`

## 7. Geography และ grain

- หนึ่ง dataset ต้องประกาศว่า “หนึ่ง record แทนอะไร” ใน connector contract
- มีรหัส/ชื่อจังหวัด exact match จึงเชื่อม province view
- official crosswalk ใช้ได้เมื่อมีหลักฐานชัด
- ไม่มี geography ที่ยืนยันให้ไป non-geo/Insights
- จับคู่ไม่ได้ให้เก็บใน `unmapped_records` ห้ามเดาจากชื่อหน่วยงาน
- `null` ไม่ใช่ศูนย์ และ `fetched_at` ไม่ใช่ `as_of`

ตัวอย่าง: participant 1 แถวไม่เท่ากับ project 1 โครงการ และ funding ที่ผูกกับ innovation หลายจังหวัดไม่ใช่งบจัดสรรของแต่ละจังหวัด

## 8. Railway production

ตรวจสถานะจริงวันที่ 17 สิงหาคม 2569:

| Component | Production |
|---|---|
| Project | `aiat-dashboard-final` |
| Dashboard | [aiat-dashboard-web-production.up.railway.app](https://aiat-dashboard-web-production.up.railway.app) |
| Explorer | [aiat-database-explorer-production.up.railway.app](https://aiat-database-explorer-production.up.railway.app) |
| Source | GitHub `peetwan/aiat-dashboard-final`, branch `main` |
| Database | PostgreSQL ผ่าน private `DATABASE_URL` reference เดียวกัน |
| Health | ทั้งสอง service `SUCCESS`; database backend = `postgresql` |

Dashboard startup ทำงานตามลำดับ:

1. `create_all` เฉพาะตารางที่ยังไม่มี (ไม่ drop table)
2. ใช้ PostgreSQL advisory lock กันสอง instance sync ซ้อนกัน
3. ขยาย `serving_manifest.json` และ sync reviewed public artifacts รวมถึง spatial/housing data จากไฟล์ที่ commit อยู่ใน repo
4. เปิด `/health` เมื่อ counts ใน database ตรงกับ serving contract ที่ derive จาก manifest

Explorer ไม่มี startup writer และไม่มี insert/update/delete endpoint จึงอ่านฐานข้อมูลอย่างเดียวทุก 30 วินาที

## 9. Auto-deploy กับ database

Railway ผูกทั้งสอง application services กับ branch `main` จึง auto-deploy หลัง PR ถูก merge

- merge code อย่างเดียว → deploy code ใหม่; seeds เดิมถูก sync แบบ idempotent
- merge `data/public/*` revision ใหม่ → Dashboard startup sync artifact/hash ใหม่เข้า database
- connector fetch → เขียน Candidate เท่านั้นและไม่เปลี่ยน Public Dashboard
- เปิดหน้าเว็บหรือ `/health` → ไม่ fetch upstream URL

Production ยังไม่มี daily source scheduler (`automatic_refresh_enabled=false`) การเปิด scheduler ในอนาคตต้องเป็น Railway Scheduled Job แยกจาก Web Service พร้อม persistent evidence storage, retention, lock และ alerting

## 10. Team workflow

```text
PR ของ peetwan → Codex review latest SHA → no unresolved P0/P1
                 → pipeline + publication-gate → Peet squash merge
routine data refresh → receipt → publication-gate → exact-revision review
PR ของ contributor → codex-publication-reviewed → squash auto-merge
                     → Railway auto-deploy/startup sync
```

ก่อนเปิด PR รัน:

```powershell
python -m app.cli validate-pipeline
python tools/validate_public_repo.py
python -m pytest -q
```

Routine public-data refresh ต้องรัน `python -m app.cli publication receipt` แล้ว `python -m app.cli publication validate` เพิ่มด้วย Scheduled review/automation ตรวจ PR และ production health เท่านั้น ไม่ fetch ด้วย production secret และไม่เขียน database โดยตรง

Public clone รัน application และ connector tests ได้ครบ ส่วน integration tests ที่เทียบ raw evidence ทั้งชุดจะทำงานเมื่อ `AIAT_EVIDENCE_ROOT` ชี้ไปยัง evidence workspace ที่มีไฟล์ตรงตาม dated run ที่ builder ระบุ

อ่านวิธีเพิ่ม source ที่ [Connector development](connector-development.md), ขั้นตอน release ที่ [Publication workflow](publication-workflow.md), กติกา publication ที่ [Data governance](data-governance.md) และ production runbook ที่ [Deployment](deployment.md)
