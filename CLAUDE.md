# CLAUDE.md

จุดเริ่มต้นสำหรับ AI coding agent (Claude Code, Codex, Cursor ฯลฯ) ที่ถูกชี้มาที่ repo นี้
กติกาเต็มอยู่ที่ [AGENTS.md](AGENTS.md) — ไฟล์นี้เป็นแผนที่นำทาง ไม่ใช่กติกาชุดใหม่

## Repo นี้คืออะไร

Public serving application ของ AIAT Provincial Evidence Map (FastAPI + SQLAlchemy, deploy บน Railway)
`config/source_catalog.json` เป็นไฟล์ **generated** จาก canonical evidence workspace (AIAT_Project)
ผ่าน `tools/build_source_catalog.py` — ห้ามแก้ catalog ด้วยมือ

ความสัมพันธ์สองฝั่ง:

- **AIAT_Project** (evidence workspace, ไม่อยู่บน GitHub): registry, source cards, raw/staged evidence
  ค่าเริ่มต้นของ `AIAT_EVIDENCE_ROOT` คือโฟลเดอร์แม่ของ repo นี้
  raw snapshot กลางอยู่บน team bucket (Cloudflare R2) — ดึงด้วย `python tools/evidence_pull.py <source_id>`
- **repo นี้**: connector pipeline, review gates, publication contracts และ Dashboard/Explorer ที่ deploy จริง
- Clone ที่ไม่มี evidence workspace ทำงานได้ปกติทุกอย่าง ยกเว้นการ regenerate catalog/coverage

## คำสั่งเดียวที่ต้องผ่านก่อนเปิด PR

```powershell
python -m app.cli check
```

รันชุดเดียวกับ CI ครบทุกขั้น (compile → validate-pipeline → publication validate →
public-repo boundary → pytest) เพิ่ม `--skip-tests` เมื่ออยากได้รอบเร็วระหว่างแก้งาน

บนเครื่อง Windows ที่ยังไม่ activate venv: ใช้ `.venv\Scripts\python.exe -m app.cli check`

## จะทำงานอะไร → อ่านอะไร

| งาน | เริ่มที่ |
|---|---|
| เพิ่ม source/URL ใหม่ทั้งเส้นทาง | [docs/add-new-source.md](docs/add-new-source.md) |
| เขียนหรือแก้ connector | [docs/connector-development.md](docs/connector-development.md) + `python tools/scaffold_connector.py` |
| เอาข้อมูลเข้า public dashboard (publish) | [docs/publication-workflow.md](docs/publication-workflow.md) |
| เข้าใจโครงระบบก่อนแก้ | [docs/architecture.md](docs/architecture.md) |
| ดึง/อัปโหลด raw snapshot (evidence bucket) | [docs/evidence-storage.md](docs/evidence-storage.md) |
| branch/PR/review workflow ของทีม | [CONTRIBUTING.md](CONTRIBUTING.md) |
| กติกาบังคับทั้งหมด + review rules | [AGENTS.md](AGENTS.md) |

## เส้นแดงที่ห้ามข้าม (สรุปจาก AGENTS.md)

- ห้าม commit secret, `.env`, token, cookie, database dump, raw response, ชื่อบุคคล เบอร์โทร อีเมล ที่อยู่
- Connector คืน Candidate เท่านั้น — ห้ามเขียน `public_artifacts` หรือ auto-promote เป็น Public
- Restricted source (ดูรายการใน `tests/test_policy.py`) ห้ามมี executable connector ใน repo นี้
- CI และ tests ห้ามเรียก upstream network — ใช้ fixture/fake recorder เท่านั้น
- ห้ามเดา grain, unit, geography, `as_of` — ไม่รู้ให้คงเป็น `null`/`needs_review`
- ไฟล์ generated (`config/source_catalog.json`, `data/public/source_coverage.json`, `docs/data-governance.md`) แก้ผ่าน builder เท่านั้น
