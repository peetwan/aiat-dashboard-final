# Security Policy

## Supported version

แก้ไขช่องโหว่บน `main` และ production revision ล่าสุดเท่านั้น

## การรายงานปัญหา

อย่าเปิด public issue หากรายงานมี credential, ข้อมูลส่วนบุคคล, URL ที่มี token, raw response หรือวิธีเข้าถึงข้อมูลที่ไม่ควรเผยแพร่

ให้ติดต่อ maintainer ผ่าน GitHub private vulnerability reporting ของ repository หากเปิดใช้งาน หรือส่งรายละเอียดส่วนตัวให้เจ้าของ repository `peetwan`

รายงานควรมี:

- ไฟล์/endpoint ที่ได้รับผลกระทบ โดยไม่ใส่ secret จริง
- ผลกระทบที่คาดการณ์
- ขั้นตอนตรวจสอบที่ไม่เผยแพร่ข้อมูลอ่อนไหว
- แนวทางแก้ไขถ้ามี

## ขอบเขตสำคัญ

- Public connector ใช้เฉพาะ endpoint ที่หน้าเว็บสาธารณะเรียก
- ห้ามเดารหัสผ่าน, bypass login/401/403 หรือแก้ CAPTCHA
- Operational Candidate ไม่ใช่ Public release
- Person-level household, health และ financial values ไม่ขึ้น public serving database
- Credential ที่เคย commit ถือว่าถูกเปิดเผยแล้ว ต้อง revoke/rotate แม้ลบออกจาก Git history ภายหลัง
