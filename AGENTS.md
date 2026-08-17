# AGENTS.md

คำแนะนำนี้ใช้กับ contributor และ coding agent ทุกตัวใน repository นี้

## เป้าหมายของ repository

นี่คือ public serving application และ connector-based ingestion pipeline สำหรับข้อมูล 28 แหล่ง ไม่ใช่ raw evidence lake หลัก

## คำสั่งตรวจที่ต้องผ่าน

```bash
python -m app.cli validate-pipeline
python tools/validate_public_repo.py
python -m pytest -q
```

CI ต้องไม่เรียก upstream network ใช้ fixture หรือ fake recorder เท่านั้น

## กติกาแกนข้อมูล

- Source ใหม่ต้องอยู่ใน `config/source_catalog.json` ก่อน
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
