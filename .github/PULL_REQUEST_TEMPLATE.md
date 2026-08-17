## เปลี่ยนอะไร

<!-- อธิบายสั้น ๆ ว่าแก้อะไรและทำไม -->

## ประเภทงาน

- [ ] Application/UI/API
- [ ] Connector หรือ source contract
- [ ] Public artifact/data release
- [ ] Documentation/tooling
- [ ] Deployment/workflow

## Data boundary

- [ ] ไม่มี `.env`, credential, cookie, raw dump หรือ database dump
- [ ] ไม่มีชื่อบุคคล เบอร์โทร อีเมล ที่อยู่ หรือ identifier ส่วนบุคคลใน fixture/public artifact
- [ ] Connector output ยังเข้า Candidate เท่านั้น ไม่มี direct public promotion
- [ ] Grain, identity, geography, completeness และ privacy contract อัปเดตแล้ว (ถ้าเกี่ยวข้อง)

## Verification

- [ ] `python -m app.cli validate-pipeline`
- [ ] `python tools/validate_public_repo.py`
- [ ] `python -m pytest -q`
- [ ] ตรวจ diff ของ counts/hashes/public artifacts แล้ว (ถ้ามี data release)

## หลักฐานเฉพาะประเภทงาน

- [ ] UI/UX: แนบภาพ before/after และตรวจ mobile, keyboard navigation, focus state แล้ว (ถ้าเกี่ยวข้อง)
- [ ] Public release: อัปเดต `data/public/serving_manifest.json` แล้ว (ถ้าเกี่ยวข้อง)
- [ ] Public release: manifest ผูก `source_ids` ที่อนุมัติแล้ว และ payload ผ่าน privacy scan (ถ้าเกี่ยวข้อง)
- [ ] Public release: ตรวจ generic artifacts API รวมถึง `item_count` และ `content_hash` ตรงกับไฟล์ JSON แล้ว (ถ้าเกี่ยวข้อง)

## Review note

<!-- ระบุสิ่งที่ reviewer/Codex ควรตรวจเป็นพิเศษ หรือเขียน "ไม่มี" -->
