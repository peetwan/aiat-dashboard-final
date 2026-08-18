# AGENTS.md

คำแนะนำนี้ใช้กับ contributor และ coding agent ทุกตัวใน repository นี้

## เป้าหมายของ repository

นี่คือ public serving application ที่ catalog ครอบทุกแหล่งใน canonical registry (ชุดตรวจรับแรก 28 แหล่ง และทีมเพิ่มได้ต่อเนื่อง) และ connector-based operational ingestion สำหรับ 6 แหล่งปัจจุบัน ที่เหลืออยู่ใน snapshot/metadata/restricted lane ไม่ใช่ raw evidence lake หลัก

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
| regenerate catalog/coverage | `python tools/build_source_catalog.py` แล้ว `python tools/build_source_coverage.py` (ต้องมี evidence workspace; ถ้าไม่มีจะได้ข้อความบอกทางไม่ใช่ traceback) |
| publish ข้อมูลเข้า dashboard | builder ใน `tools/` → `python -m app.cli publication receipt` → ตาม [docs/publication-workflow.md](docs/publication-workflow.md) |
| แก้ UI | Dashboard: `app/templates/` + `app/static/`; Explorer: `explorer/templates/` + `explorer/static/` |

ก่อนเปิด PR ทุกครั้ง: `python -m app.cli check` ต้องผ่านครบ

## กติกาแกนข้อมูล

- Source เดิมต้องมี entry ใน generated `config/source_catalog.json`; source ลำดับใหม่ต้องเพิ่ม canonical `config/source_registry.json` + source card ใน evidence workspace แล้ว regenerate ห้ามแก้ catalog ด้วยมือ
- Executable source ต้องมี plan, importable connector, contract และ tests
- Connector คืน Candidate records เท่านั้น ห้ามเขียน `public_artifacts` หรือ publish เอง
- Raw response ต้องผ่าน central `ResponseRecorder` เพื่อให้มี SHA-256 และ manifest
- ห้ามเดา grain, unit, geography, `as_of`, denominator หรือความหมาย field
- ห้าม commit `.env`, token, cookie, database dump, raw response, ชื่อบุคคล เบอร์โทร อีเมล หรือที่อยู่
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

- Flag tracked raw payloads, credentials, personal contact values, person-level financial/health/household values, or changes that weaken forbidden-field/contact scans. Keep fixtures small and redacted; public output must remain a reviewed projection.

### Repository workflow

- Flag an executable source without matching registry, plan, connector contract, fixture-based tests, or CI coverage. Do not treat AI review as a replacement for deterministic checks or branch protection.
- Flag startup/network code that fetches upstream URLs during web deploy, health checks, or page requests. Production startup may sync only reviewed files already committed under `data/public/`.
