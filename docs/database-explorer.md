# AIAT Database Explorer

Database Explorer เป็น service แยกจาก Public Dashboard แต่ deploy อยู่ใน Railway project เดียวกันและอ่าน PostgreSQL ตัวเดียวกันผ่าน private service reference

## ขอบเขต

- อ่านอย่างเดียว ไม่มี endpoint สำหรับ insert/update/delete
- แสดงทะเบียน 28 sources, endpoints, operational run/count และ serving table counts
- อธิบายข้อมูลที่นำมาใช้, grain, public policy, สิ่งที่ไม่เผยแพร่ และ database targets ต่อ source
- ไม่เปิด raw payload, connection string, token, cookie, password หรือข้อมูลระบุตัวบุคคล
- refresh สถานะจาก Serving Database ทุก 30 วินาที; ไม่ fetch เว็บไซต์ต้นทางตอนเปิดหน้า

## รันบนเครื่อง

```powershell
python -m app.cli init-db
python -m explorer.server
```

เปิด `http://localhost:8080` และ OpenAPI ที่ `http://localhost:8080/docs`

## Railway service

Explorer ใช้ image จาก `Dockerfile.explorer` และตัวแปร:

```text
DATABASE_URL=${{Postgres-HY_j.DATABASE_URL}}
DASHBOARD_URL=https://aiat-dashboard-web-production.up.railway.app
APP_ENV=production
```

ชื่อ database service ใน reference ต้องตรงกับ service ที่ Dashboard ใช้อยู่จริง ห้ามคัดลอกค่าของ connection string ลง Git

Health check: `/health`

## API

| Endpoint | เนื้อหา |
|---|---|
| `/api/overview` | สถานะ backend และจำนวน live rows ภาพรวม |
| `/api/sources` | รายละเอียดครบ 28 sources พร้อม grain/endpoints/tables |
| `/api/source/{source_id}` | รายละเอียด source เดียว |
| `/api/schema` | 9 serving tables, live counts และ relationships |

