# Connector fixtures

เก็บเฉพาะ response ตัวอย่างขนาดเล็กที่ตัดชื่อบุคคล เบอร์โทร อีเมล ที่อยู่ token และ identifier ส่วนบุคคลแล้ว

- หนึ่ง source ใช้ไฟล์ `<source_id>.json` หนึ่งไฟล์ในโฟลเดอร์นี้
- fixture ต้องเล็กพอสำหรับ unit test และห้ามเป็น raw dump ทั้งชุด
- ใช้ค่าจำลองที่ระบุชัดว่าเป็น fixture หรือใช้โครงสร้างจริงที่ลบค่าระบุตัวบุคคลแล้ว
- ห้ามให้ test เรียกเว็บไซต์จริง เพราะ CI ต้องทำงานซ้ำได้แม้ต้นทางล่ม

รูปแบบไฟล์บังคับคือ `fixture_version: "1.0"`, `source_id` ต้องตรงกับ contract และ
`records` เป็นรายการ `{ "dataset_key": "...", "payload": { ... } }` ขนาดเล็ก
validator จะนำตัวอย่างนี้ผ่าน regex grain, identity options และ privacy sanitizer ชุดเดียวกับ runtime
