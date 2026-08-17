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
8. เมื่อพร้อม ผู้ดูแลหรือ Codex automation จะใส่ label `codex-automerge`; GitHub จะ squash merge หลัง required checks ผ่าน

ห้าม push ตรงเข้า `main`

## เพิ่ม URL หรือ Connector

อ่าน [คู่มือเพิ่ม Connector](docs/connector-development.md) และเริ่มจาก `templates/connector/`

หนึ่ง Pull Request ต้องมีอย่างน้อย:

- Registry entry ใน `config/source_catalog.json`
- Ingestion plan ใน `config/ingestion_plans.json`
- Module ใน `app/connectors/`
- Contract ใน `config/connector_contracts/`
- Fixture ขนาดเล็กที่ตัดข้อมูลส่วนบุคคลแล้ว
- Tests สำหรับ happy path, completeness failure และ schema drift

## Public repo กับ evidence workspace

Repository นี้ clone แล้วเปิด Dashboard, สร้าง serving database, validate connectors และรัน tests ได้ด้วยตัวเอง แต่ raw evidence/audit history หลักอยู่ใน workspace ภายในและไม่ถูก publish

Contributor ไม่ต้องมี raw workspace เพื่อแก้ application หรือสร้าง connector test ใหม่ ให้ใช้ fixture ที่ตัดข้อมูลอ่อนไหวแล้ว การ rebuild public release จาก evidence ทั้งหมดเป็นงานของ maintainer

## ข้อมูลที่ห้าม commit

- `.env`, token, cookie, API key, signed URL หรือ database credentials
- SQLite/database dump และ runtime manifests
- Raw response ทั้งชุด
- ชื่อบุคคล เบอร์โทร อีเมล ที่อยู่ หรือ identifier ส่วนบุคคล
- Household, health หรือ person-level financial values

หากพบข้อมูลดังกล่าวใน commit ให้หยุดและแจ้ง maintainer ตาม `SECURITY.md` ห้ามเปิด public issue ที่มีค่าจริง

## Codex review

Repository มี `AGENTS.md` สำหรับกฎ review เฉพาะระบบนี้ เมื่อเชื่อม repository กับ Codex cloud สามารถเปิด Automatic reviews หรือใช้ `@codex review` ใน PR ได้

Codex review เป็นด่านเสริม CI ไม่ใช่ด่านแทน CI การ merge ต้องมี required checks ผ่านและไม่มีปัญหาสำคัญที่ยังไม่แก้
