# ร่วมพัฒนา AIAT Provincial Evidence Map

ขอบคุณที่ช่วยพัฒนา repository นี้ งานทุกชิ้นเข้าผ่าน branch และ Pull Request เพื่อให้ code, data contract และ public-data boundary ถูกตรวจแบบเดียวกัน

## เริ่มใช้งาน

ต้องใช้ Python 3.12 ขึ้นไป

```powershell
git clone https://github.com/peetwan/aiat-dashboard-final.git
cd aiat-dashboard-final
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.cli validate-pipeline
python tools/validate_public_repo.py
python -m pytest -q
```

บน macOS/Linux ใช้ `source .venv/bin/activate` แทนคำสั่ง activate ของ PowerShell

## Workflow ของทีม

1. สร้าง issue หรืออธิบาย source/bug ที่จะทำ
2. สร้าง branch จาก `main` เช่น `feature/f2-new-source` หรือ `fix/apptech-pagination`
3. แก้เฉพาะขอบเขตที่จำเป็น พร้อม tests
4. รันคำสั่งตรวจทั้งสามคำสั่ง
5. เปิด Pull Request และกรอก checklist
6. รอ CI และ Codex review
7. แก้ P0/P1, failed checks และ review conversations ให้หมด
8. เมื่อพร้อม สมาชิกทีมที่มีสิทธิ์หรือ Codex automation จะใส่ label `codex-automerge`; GitHub จะ squash merge หลัง required checks ผ่าน

ห้าม push ตรงเข้า `main`

## เพิ่ม URL หรือ Connector

อ่าน [คู่มือเพิ่ม Connector](docs/connector-development.md) และเริ่มจาก `templates/connector/`

สร้าง connector + contract + fixture + offline test ตั้งต้นได้ด้วย:

```powershell
python tools/scaffold_connector.py <source_id> --transport <lower_snake_case> --dataset-key <key> --grain-th "หนึ่งแถวแทน..." --identity-fields <field[,field]>
```

เพิ่ม `--geography-field province`, `--as-of-field updated_at` หรือ `--dry-run` ได้ตามต้นทาง Tool นี้ไม่แก้ generated source catalog หรือ ingestion plan อัตโนมัติ สำหรับหนึ่งใน 28 แหล่งเดิมให้ใช้ catalog entry ที่มีอยู่แล้วและเพิ่ม plan เอง

ถ้าเป็น source ลำดับใหม่ที่ยังไม่อยู่ใน 28 แหล่ง ผู้ที่มี evidence workspace ต้องเพิ่ม canonical `config/source_registry.json` และ `data/source_audit/<ordinal>_<source_id>/source_card.json` แล้วรัน `tools/build_source_catalog.py` กับ `tools/build_source_coverage.py` ห้ามแก้ `config/source_catalog.json` หรือ `data/public/source_coverage.json` ด้วยมือ

หนึ่ง Pull Request ต้องมีอย่างน้อย:

- Existing generated catalog entry หรือ generated diff จาก canonical registry/source card สำหรับ source ใหม่
- Ingestion plan ใน `config/ingestion_plans.json`
- Module ใน `app/connectors/`
- Contract ใน `config/connector_contracts/`
- Fixture ขนาดเล็กที่ตัดข้อมูลส่วนบุคคลแล้ว
- Tests สำหรับ happy path, completeness failure และ schema drift

## แก้ UI/UX

| หน้า | HTML | CSS/JavaScript |
|---|---|---|
| Dashboard และ Insights | `app/templates/index.html`, `app/templates/insights.html` | `app/static/styles.css`, `app/static/app.js`, `app/static/insights.css`, `app/static/insights.js` |
| รายละเอียดจังหวัด | `app/templates/province.html` | `app/static/province.css`, `app/static/province.js` |
| Database Explorer | `explorer/templates/index.html` | `explorer/static/styles.css`, `explorer/static/app.js` |

ก่อนเปิด PR ให้เปิด Dashboard และ Explorer บนจอกว้าง/จอมือถือ ทดสอบลิงก์ ปุ่ม สถานะ loading/empty/error และรัน:

```powershell
python -m pytest -q tests/test_ui_coverage.py tests/test_api.py tests/test_explorer.py
```

UI อ่านได้เฉพาะ Public release หรือ safe preview ที่ API เตรียมให้ ห้ามเพิ่ม route ที่ส่ง raw payload, secret หรือข้อมูลระบุตัวบุคคลออกไปยัง browser

## ลองเอาข้อมูลเข้า Candidate database บนเครื่อง

`init-db` สร้าง SQLite ใน `data/runtime/` ของเครื่องตัวเอง ส่วน `ingest` เขียนผลเข้า `dashboard_records` ซึ่งยังเป็น Candidate:

```powershell
python -m app.cli init-db
python -m app.cli ingest --source <source_id> --strategy snapshot
python -m app.cli status
```

ใช้ `--strategy api` ได้เมื่อ plan ระบุ public endpoint ไว้แล้ว ผลจากคำสั่งนี้ไม่เข้า Public Dashboard อัตโนมัติ และห้าม commit SQLite/raw/runtime files

## ทำ reviewed Public release

1. สร้าง cleaned JSON object ด้วย deterministic builder และวางไว้ใต้ `data/public/`
2. เพิ่ม entry ใน `data/public/serving_manifest.json` โดย artifact ใหม่ที่ไม่ใช่ serving core ต้องระบุ `source_ids`
3. เพิ่ม tests ที่ตรวจ schema, count/completeness, privacy และ semantic diff ของชุดนั้น
4. รัน tests ทั้งหมด เปิด PR ให้ทีม review diff และ merge เมื่อ required checks ผ่าน
5. Railway จะ deploy `main`; Dashboard startup จะตรวจ manifest และ payload ทั้งชุดก่อน sync เข้า `public_artifacts` แบบ idempotent

ตัวอย่าง entry สำหรับไฟล์เดียว:

```json
{
  "key": "learning-dashboard",
  "group": "source_dataset",
  "path": "learning_dashboard.json",
  "source_ids": ["f2_learning_dashboard"]
}
```

- `key` ใช้ตัวพิมพ์เล็ก ตัวเลข `_`, `/` หรือ `-`; `group` ใช้ `lower_snake_case`
- `path` ต้องเป็น relative path ใต้ `data/public/` และไฟล์ต้องเป็น JSON object
- `source_ids` ต้องไม่ซ้ำ และทุกค่าในรายการต้องมี `production_values_allowed=true` กับ `cloud_policy=team_approved_public` ใน generated source catalog
- หากเป็นชุดหลายไฟล์ให้ใช้ `path_glob`, `key_template` และ `expected_count` ตามรูปแบบ province entries ที่มีอยู่ พร้อม test ความครบของรหัสจังหวัด
- ตัวตรวจจะปฏิเสธทั้ง release ก่อนแก้ database หากเจอ field/value ที่เป็นอีเมล เบอร์โทร ข้อมูลติดต่อ ที่อยู่ หรือ restricted source identifier ตัวตรวจนี้เป็น guardrail; ผู้ review ยังต้องตรวจความหมายและข้อมูลส่วนบุคคลชนิดอื่นใน diff

ห้าม copy `dashboard_records` ไป `public_artifacts` ตรงๆ หรือเพิ่ม JSON โดยไม่ลง manifest/review เพราะ Candidate ยังไม่ใช่ข้อมูลที่อนุมัติให้เผยแพร่

## Public repo กับ evidence workspace

Repository นี้ clone แล้วเปิด Dashboard, สร้าง serving database, validate connectors และรัน tests ได้ด้วยตัวเอง แต่ raw evidence/audit history หลักอยู่ใน workspace ภายในและไม่ถูก publish

Contributor ไม่ต้องมี evidence workspace เพื่อแก้ application, UI หรือ connector tests ให้ใช้ fixture ที่ตัดข้อมูลอ่อนไหวแล้ว ส่วนการ rebuild จาก immutable evidence ทำได้โดยสมาชิกทีมคนใดก็ได้ที่ได้รับ evidence package ซึ่งมีสิทธิ์ใช้

ตั้ง root ที่มี `config/source_registry.json` และ `data/raw`, `data/staged`, `data/qa`, `data/source_audit` ก่อนรัน dated-path builders:

```powershell
$env:AIAT_EVIDENCE_ROOT = 'D:\approved-aiat-evidence'
python tools/build_source_catalog.py
```

`AIAT_EVIDENCE_ROOT` เปลี่ยนเฉพาะ root ของ path; builder ยังคงต้องการ run ID และไฟล์หลักฐานตรงตามที่ระบุ จึงไม่ทำให้ public clone มี raw evidence ขึ้นมาเอง

## สิทธิ์ GitHub และ Railway

Repository ถูกสร้างเริ่มต้นใต้บัญชี GitHub `peetwan`; ชื่อบัญชีใน URL เป็น provenance ของการสร้าง repository ไม่ได้หมายความว่าโครงการมีเจ้าของเพียงคนเดียว `CODEOWNERS` ระบุบัญชีผู้ร่วมดูแล ส่วน GitHub จะส่งคำขอ review ได้เฉพาะบัญชีที่ยอมรับ collaborator invitation และมีสิทธิ์ใน repository แล้ว

สิทธิ์ GitHub ไม่ได้ให้ Railway access โดยอัตโนมัติ ผู้ที่ได้รับเชิญเข้า Railway project เท่านั้นจึงจะเห็น variables/logs หรือแก้ service settings ได้ สมาชิกทีมที่มีสิทธิ์ merge บน GitHub ยังส่งการเปลี่ยนแปลงเข้า auto-deploy ได้ผ่าน PR/merge โดยไม่ต้องเห็น production secret

## ข้อมูลที่ห้าม commit

- `.env`, token, cookie, API key, signed URL หรือ database credentials
- SQLite/database dump และ runtime manifests
- Raw response ทั้งชุด
- ชื่อบุคคล เบอร์โทร อีเมล ที่อยู่ หรือ identifier ส่วนบุคคล
- Household, health หรือ person-level financial values

หากพบข้อมูลดังกล่าวใน commit ให้หยุดและแจ้งทีมผ่านช่องทางใน `SECURITY.md` ห้ามเปิด public issue ที่มีค่าจริง

## Codex review

Repository มี `AGENTS.md` สำหรับกฎ review เฉพาะระบบนี้ เมื่อเชื่อม repository กับ Codex cloud สามารถเปิด Automatic reviews หรือใช้ `@codex review` ใน PR ได้

Codex review เป็นด่านเสริม CI ไม่ใช่ด่านแทน CI การ merge ต้องมี required checks ผ่านและไม่มีปัญหาสำคัญที่ยังไม่แก้
