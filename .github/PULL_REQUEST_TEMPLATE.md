## เปลี่ยนอะไร

<!-- สรุปสิ่งที่แก้ เหตุผล และผลที่คาดหวัง -->

## ประเภทงาน

- [ ] Application/UI/API
- [ ] Connector/URL/contract
- [ ] Routine public-data refresh
- [ ] ตั้งหรือเปลี่ยน Public dataset/ความหมาย (manual review)
- [ ] Docs/tooling/deployment

## ขอบเขตข้อมูล

- [ ] ไม่มี secret, raw/database dump, ชื่อบุคคล, เบอร์โทร หรืออีเมล
- [ ] Connector output ยังเป็น Candidate; ไม่มีทางลัดเข้า `public_artifacts`
- [ ] ถ้าเป็น routine refresh: diff มีเฉพาะ output ที่ publication contract เดิมประกาศและ `data/public/publication_receipt.json`
- [ ] ถ้าเปลี่ยน URL/dataset/ความหมาย/contract/builder/`serving_manifest.json`, `data/spatial/` หรือ `data/demand/`: ระบุให้ทีม manual review

## ตรวจแล้ว

- [ ] `python -m app.cli check` ผ่านครบ (หรือรันแยก: `validate-pipeline`, `publication validate`, `tools/validate_public_repo.py`, `pytest -q`)
- [ ] Public data: `python -m app.cli publication receipt` แล้ว `python -m app.cli publication validate`
- [ ] ก่อน merge: Codex review ครอบคลุม head SHA ล่าสุด, ไม่มี P0/P1/conversation ค้าง และ required checks ผ่าน

## หลักฐาน/จุดที่อยากให้ตรวจ

<!-- ใส่ evidence path, count/schema ที่เปลี่ยน, ภาพ UI หรือเขียน "ไม่มี" -->
