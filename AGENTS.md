# AGENTS.md

คำแนะนำนี้ใช้กับ contributor และ coding agent ทุกตัวใน repository นี้

## เป้าหมายของ repository

นี่คือ public serving application ที่ catalog ครอบทุกแหล่งใน canonical registry (ชุดตรวจรับแรก 28 แหล่ง และทีมเพิ่มได้ต่อเนื่อง) และ connector-based operational ingestion สำหรับ 10 แหล่งปัจจุบัน ที่เหลืออยู่ใน snapshot/metadata/restricted lane ไม่ใช่ raw evidence lake หลัก

## คำสั่งตรวจที่ต้องผ่าน

```bash
python -m app.cli check
```

คำสั่งเดียวรันครบชุดเดียวกับ CI: compile, `validate-pipeline`, `publication validate`,
`tools/validate_public_repo.py` และ `pytest -q` (รันแยกทีละคำสั่งได้เหมือนเดิม;
`--skip-tests` สำหรับรอบเร็วระหว่างแก้งาน)

CI ต้องไม่เรียก upstream network ใช้ fixture หรือ fake recorder เท่านั้น

## งานที่พบบ่อย (สำหรับ builder agent)

| งาน | ทำที่ไหน |
|---|---|
| เพิ่ม source ใหม่ทั้งเส้นทาง | ตาม [docs/add-new-source.md](docs/add-new-source.md) ทีละขั้น — ขั้น 1 อยู่ใน evidence workspace, ขั้น 2-6 อยู่ใน repo นี้ |
| สร้าง connector ตั้งต้น | `python tools/scaffold_connector.py <source_id> ...` แล้วแก้ parser/completeness ให้ตรงต้นทางจริง |
| แก้ connector เดิม | `app/connectors/<source_id>.py` + contract ใน `config/connector_contracts/` + fixture ใน `tests/fixtures/connectors/` |
| ดึง/อัปโหลด raw snapshot กับ team bucket | `python tools/evidence_pull.py <source_id>` / `python tools/evidence_push.py <source_id> <run_dir>` ตาม [docs/evidence-storage.md](docs/evidence-storage.md) — canonical run ห้ามเขียนทับ; ลบได้เฉพาะ legacy R2 key ที่ verify แล้วว่าเป็นสำเนา |
| regenerate catalog/coverage | `python tools/build_source_catalog.py` แล้ว `python tools/build_source_coverage.py` (ต้องมี evidence workspace; ถ้าไม่มีจะได้ข้อความบอกทางไม่ใช่ traceback) |
| publish ข้อมูลเข้า dashboard | builder ใน `tools/` → `python -m app.cli publication receipt` → ตาม [docs/publication-workflow.md](docs/publication-workflow.md) |
| แก้ UI | Dashboard: `app/templates/` + `app/static/`; Explorer: `explorer/templates/` + `explorer/static/` |

ก่อนเปิด PR ทุกครั้ง: `python -m app.cli check` ต้องผ่านครบ

## กติกาแกนข้อมูล

- Source เดิมต้องมี entry ใน generated `config/source_catalog.json`; source ลำดับใหม่ต้องเพิ่ม canonical `config/source_registry.json` + source card ใน evidence workspace แล้ว regenerate ห้ามแก้ catalog ด้วยมือ
- Executable source ต้องมี plan, importable connector, contract และ tests
- Connector คืน Candidate records เท่านั้น ห้ามเขียน `public_artifacts` หรือ publish เอง
- Raw response ต้องผ่าน central `ResponseRecorder` เพื่อให้มี SHA-256 และ manifest
- Canonical raw บน team bucket (`raw/<department>/<source_id>/<run_id>/`) ห้าม overwrite และห้ามลบ ดึงใหม่คือ run ใหม่
- ข้อยกเว้น: ลบ legacy R2 key รูปแบบ `raw/<source_id>/<run_id>/<file>` ได้เมื่อตรวจคู่สำเนากับ canonical key แล้วว่า `Content-Length` และ `ETag` ตรงกันทุกไฟล์ ห้ามลบ canonical object ห้าม overwrite และห้ามขยายข้อยกเว้นนี้ไปยัง run ที่ไม่มีสำเนาคู่
- ห้ามเดา grain, unit, geography, `as_of`, denominator หรือความหมาย field
- ห้าม commit `.env`, token, cookie, database dump และ raw response; ชื่อเจ้าของผลงาน ผู้วิจัย หน่วยงาน ช่องทางติดต่อสาธารณะ และที่ตั้งสถานที่เผยแพร่ได้ตาม `field_contexts` ใน contract ดู [docs/field-contexts.md](docs/field-contexts.md)
- แยกการเก็บหลักฐาน การเข้า Candidate และการเผยแพร่: การพบชื่อ/ข้อมูลติดต่อใน raw ไม่ใช่เหตุให้ปฏิเสธทั้ง dataset ให้จัด projection ตามบริบทของแต่ละฟิลด์
- Restricted source ห้ามมี executable connector ใน public application
- Public revision เปลี่ยนได้หลัง deterministic build, privacy/semantic tests และ review เท่านั้น

## กติกาออกแบบ Connector

- Generalize ที่ `Connector` interface, recorder และ contract; เก็บ parser/pagination/schema ไว้ใน module ราย source
- ห้ามเพิ่ม `if/elif` ตาม source ใน central orchestrator เมื่อทำเป็น connector module ได้
- Source เดียวมีหลาย grain ได้ ให้แยก `dataset_key` และ contract ต่อ grain
- Completeness ต้อง fail ก่อน commit เมื่อจำนวนรวมเปลี่ยน, pagination ขาด, ID ซ้ำ หรือ schema drift
- อย่าแก้ payload เพื่อให้เหมือน source อื่นจนความหมายเดิมหาย

## Code Review Rules

### Publication boundary

- Flag any path that copies `dashboard_records` or connector output directly into `public_artifacts`, public API, downloads, or UI. The safe path is Candidate → validation/privacy/semantic review → deterministic public artifact build → reviewed release.

### Connector completeness

- Flag a connector that can commit partial pagination, accepts changing totals, lacks stable identity checks, or truncates a source whose contract requires a complete snapshot. The safe path is to fail the run before database commit and preserve the failed manifest.

### Public data safety

- Flag tracked raw payloads, credentials, private contact values and person-level financial/health/household disclosures. Public work attribution, organization names, published work/business contacts and public locations are supported through scoped `field_contexts`; do not flag them merely for containing a name, email, phone or address. Check the source context and the declared leaf fields. Keep fixtures small and synthetic; public output remains a reviewed projection.

### Evidence storage

- Flag overwrite or deletion of canonical R2 keys `raw/<department>/<source_id>/<run_id>/...`.
- Do not flag deletion of legacy keys `raw/<source_id>/<run_id>/...` when a verify report already shows a canonical copy with matching `Content-Length` and `ETag`. Flag the deletion if any key has no verified pair, if a canonical object would be removed, or if any object would be overwritten.

### Repository workflow

- Flag an executable source without matching registry, plan, connector contract, fixture-based tests, or CI coverage. Do not treat AI review as a replacement for deterministic checks or branch protection.
- Flag startup/network code that fetches upstream URLs during web deploy, health checks, or page requests. Production startup may sync only reviewed files already committed under `data/public/`.
