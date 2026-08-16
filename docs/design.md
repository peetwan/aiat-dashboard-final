# Product and interface design

AIAT Provincial Evidence Map เป็น public decision-support interface ไม่ใช่ monitoring console ของทีม data เป้าหมายคือให้ผู้บริหารและประชาชนเริ่มจากพื้นที่ เห็นบริบทของตัวเลข และย้อนกลับไปยังแหล่งข้อมูลได้โดยไม่ต้องอ่าน raw tables

## Design principles

1. **Map first** — แผนที่ประเทศไทยแบบ 2D flat choropleth เป็น interaction หลัก
2. **Evidence before judgment** — สีแสดงความครอบคลุมหลักฐาน ไม่ใช่ performance score
3. **Progressive disclosure** — แสดง summary ก่อน แล้วโหลดรายละเอียดเมื่อผู้ใช้เลือกจังหวัด
4. **Preserve meaning** — ไม่รวม metric ต่างหน่วย ไม่แทน `null` ด้วยศูนย์ และไม่สร้าง budget ranking
5. **Honest geography** — ข้อมูลที่ผูกจังหวัดไม่ได้อยู่ non-geo/unmapped
6. **Public-safe by design** — Browser ได้เฉพาะ cleaned projection; ไม่มี raw/restricted payload

## Current interaction model

- Default view แสดงแผนที่ 77 จังหวัด, legend และตัวเลือกจังหวัด
- Desktop ใช้ side panel; mobile ใช้ bottom sheet
- Province panel โหลด `/summary` ก่อนและโหลด `/briefing` สำหรับรายละเอียด/provenance
- เนื้อหาแบ่งเป็น 5 แท็บตามงานตัดสินใจ:
  - **ภาพรวม** — ตัวเลขหลัก, decision chain, narrative และ context metrics
  - **โครงการและงบ** — provisional project groups, participant records, innovation, research/IP/ROI/SROI และ funding caveat
  - **คนและพื้นที่** — SRA/PPPConnext target groups และ area context
  - **มิติการพัฒนา** — context/need, input, activity, output, outcome labels
  - **คุณภาพข้อมูล** — grain, status, `as_of`, `fetched_at`, record count และ source URL
- หน้า `/insights` รองรับ cross-province, national/non-geo, unmapped และ coverage 28 sources
- ชื่อจังหวัดและสีปรับตาม evidence coverage เพื่อไม่ให้แผนที่รก
- ใช้ฟอนต์ Anuphan, contrast และ touch targets ที่รองรับ desktop/mobile

## Visual encoding contract

- แผนที่มี lens สำหรับ project groups, SRA, innovation และ evidence coverage; project lens ใช้ provisional project-group count ไม่ใช้ participant rows
- SRA region lens นับจังหวัดใน target registry ทั้ง 20 จังหวัด ส่วน province color ใช้คะแนนเฉพาะ 15 จังหวัดที่มีค่า
- จำนวน records ไม่ถูกใช้เป็นค่าความสูง สี performance หรือ proxy ของความต้องการงบ
- Metric card เปรียบเทียบภายใน metric/grain ที่เข้ากันได้เท่านั้น
- รายการวัฒนธรรม ท่องเที่ยว และโครงการโหลดเมื่อเปิดรายละเอียดพื้นที่
- Quality status, unit, `as_of` และ caveat ต้องอยู่ใกล้ค่าที่แสดง
- ไม่แสดง `0` เมื่อสถานะคือ not-found/unknown; แสดง `—` และเหตุผลแทน
- Funding ของ innovation ที่เชื่อมหลายจังหวัดต้องมีคำเตือนและห้ามใช้เป็น provincial allocation

## Reference patterns

แนวทางที่นำมาศึกษา ไม่ใช่หน้าจอที่คัดลอก:

- [UNDP GeoHub](https://geohub.data.undp.org/) — map-led discovery และ metadata
- [UNDP SDG Push Diagnostic](https://sdgdiagnostics.data.undp.org/) — แยก evidence, policy choice และ scenario
- [USAspending Agency Profiles](https://www.usaspending.gov/agency) — drill-down จากภาพรวมไปแหล่งข้อมูล
- [Seattle Budget Dashboard](https://www.seattle.gov/council/topics/budget-dashboard) — อธิบายบริบทก่อนตัวเลข
- [Open Treasury](https://www.opentreasury.org/) — การสื่อสารงบด้วยภาษาคนทั่วไป
- [PMUA Data Command Center Mockup](https://pmua-dashboard-mock.poomzi.com/) — หัวข้อเดิมด้าน source coverage, พื้นที่ และงบประมาณ

Reference screens ที่ใช้ศึกษารูปแบบ interaction:

- [Squarespace — Geography analytics](https://mobbin.com/screens/be6a849b-1fde-42ca-a6f2-f69ffcf4439c)
- [Cloudflare — Account analytics](https://mobbin.com/screens/254f6c74-2e18-4638-ad6f-ff8dc6c5c297)
- [Navattic — Analytics](https://mobbin.com/screens/a5be5a57-9c24-49a2-9ce5-ccd5edc17a1b)
- [Hotjar — Custom dashboard](https://mobbin.com/screens/f43a5082-26d2-40d3-ba2a-6c4bee3958b5)
- [Deel — Global Hiring Guide](https://mobbin.com/screens/a6cb49ca-18e2-49d4-9a58-da555b0c4855)
- [Profound — Answer Engine Insights](https://mobbin.com/screens/98b82305-3239-4d52-b0c9-0e7f701dc127)
- [Felt — Operational Map](https://mobbin.com/screens/e3ac649f-a644-4545-a798-9d50366385db)
- [Rocket Money — Budget](https://mobbin.com/screens/e8e471f9-dc5d-47a7-8d02-8b62c096149b)
- [Origin — Spending](https://mobbin.com/screens/d74b56f7-a4f0-43c9-b708-6615de691c5c)

## Review checklist

- ผู้ใช้เข้าใจว่าสีหมายถึง coverage ไม่ใช่คะแนนหรือ ranking
- จังหวัดที่ไม่มีข้อมูลไม่แสดงเป็นศูนย์
- ทุกค่ามี source/quality context ที่เพียงพอ
- UI ไม่แสดง raw table, contact field หรือ restricted value
- Keyboard, touch, contrast และ responsive layout ใช้งานได้
- Province panel และ `/insights` แสดง non-geo/unmapped อย่างตรงไปตรงมา
- Project count, participant count และ innovation–province link ผ่าน regression test แยก grain ทั้ง 77 จังหวัด

ข้อจำกัดข้อมูลที่ UI ต้องรักษาอยู่ใน [Data audit](data-audit.md)
