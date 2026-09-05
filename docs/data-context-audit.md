# ผลตรวจบริบทข้อมูล 5 กันยายน 2026

เปลี่ยนการตัดชื่อและช่องทางติดต่อแบบเหมารวมเป็นการระบุความหมายของฟิลด์ใน contract ชื่อ PI ผู้วิจัย ผู้ประดิษฐ์ เจ้าของงาน และข้อมูลติดต่อที่ต้นทางประกาศไว้กับงานสามารถแสดงได้ ทั้ง Candidate, public artifact, API, download และ dashboard ใช้บริบทเดียวกัน

## ขอบเขตหลักฐาน

อ่าน bucket `aiat-data-evidence` แบบ read-only พบ 442 objects ใน 22 source prefixes มี 51 run manifests และ 117 dataset declarations ตรวจไฟล์ข้อมูล/HTML 395 objects, ZIP ที่มีข้อมูล 18 objects และ PDF 11 เล่ม รวม 1,240 หน้า เทียบ SHA-256 เมื่อมี manifest ประกาศไฟล์ไว้ ไม่พบไฟล์ข้อมูลหรือ archive member ที่อ่าน/parse ไม่สำเร็จ

อีก 13 objects เป็น headers, checksums, scripts และภาพประกอบ อีก 5 ZIP เป็น media bundles ไม่ได้ OCR ภาพหรือวิเคราะห์บุคคลในภาพ การตรวจครั้งนี้ครอบคลุม schema ข้อมูลและเส้นทางที่ pipeline ใช้ ไม่ใช่การตรวจทุก pixel ของ media

ตรวจ staged evidence ในเครื่องเพิ่มด้วย โดยเฉพาะ AppTech MTR ซึ่งไม่มี source prefix ของตัวเองใน R2 รอบนี้ การนับแต่ละแหล่งด้านล่างเป็นจำนวนระเบียนตาม grain ของต้นทาง ไม่ใช่จำนวนบุคคลที่ไม่ซ้ำ

## สิ่งที่คืนให้ใช้งาน

| ข้อมูล | ผลที่แก้ |
|---|---|
| AppTech MRU | คืนชื่อเจ้าของผลงาน 501 รายการ ชื่อผู้วิจัยหลัก 524 รายการ เจ้าของสิทธิ์ 483 รายการ และชื่อเจ้าของโจทย์ความต้องการเมื่อมีค่า |
| AppTech MTR | คืนทะเบียน 630 รายการ พร้อมชื่อเจ้าของและช่องทางติดต่อจาก public listing ตรวจ hash ของแต่ละหน้าและจับคู่ ID กับ Silver |
| RMUTDB | คืนทะเบียน PDF 2,001 ระเบียน แยกฉบับละเอียด 1,006 และฉบับสรุปประจำปี 995 มีผู้ประดิษฐ์ ผู้ประสานงาน และช่องทางติดต่อที่พิมพ์ไว้ในหนังสือ ไม่บวกสอง grain เป็นจำนวนผลงานที่ไม่ซ้ำ |
| Cultural Map | Map 5,258 รายการรองรับที่ตั้ง ผู้จัดทำ สังกัด และช่องทางติดต่องาน คืนทะเบียน Products 226, Activities 43, Re-Creation 80 และ Team 12 รวม 361 รายการ |
| ท่องเที่ยวลำพูน | คืนหมายเลขบริการฉุกเฉิน 6 รายการ ศูนย์บริการ 3 แห่งพร้อมเบอร์ 8 ช่อง กลุ่มทำโคม 10 กลุ่ม และหมายเลขบริการเดินทางที่ต้นทางระบุ |
| Housing public places | คืนชื่อสถานที่ ที่ตั้ง คะแนน และจำนวนรีวิวให้ 28,694 จุดจาก public place feed ตรวจ ID และ geometry ให้ตรง seed เดิม |
| CLIG | คืนเครดิต 107 โครงการ โดยมีชื่อไทย 96 และชื่ออังกฤษ 92 จับคู่ ID และ URL รายละเอียดตรงกันทั้ง 107 ระเบียนจากหลักฐาน PSU กับทะเบียน CLIG หน้า F4 แสดงชื่อผู้วิจัยและตำแหน่งจาก reviewed artifact พร้อมคืนชื่อโครงการฉบับเต็มหนึ่งรายการที่ listing เดิมตัดสั้น ส่วน parser เก็บชื่อได้ในการดึงรอบถัดไปด้วย |

ชื่อในช่องผู้จัดทำ Cultural Map ที่จริงเป็น account email ไม่ถูกแสดงเป็นชื่อบุคคล และไม่ส่ง account_identifier หรือข้อมูลผู้ให้สัมภาษณ์ออกไป ชื่อสมาชิกทีมที่ต้นทางแสดงเป็นเครดิตผลงานคงไว้ได้

## ตรวจครบตาม source prefix ใน R2

| Source | ข้อสรุปและการจัดการ |
|---|---|
| `clig_projects` | มี 107 โครงการ snapshot เดิมไม่มีชื่อเพราะ parser ตัดออก แก้ parser/contract และการ regenerate catalog แล้ว |
| `f4_research_dashboard_psu` | รายละเอียดโครงการใช้ยืนยันเครดิตผู้วิจัยใน CLIG source นี้ยังเป็น metadata ใน catalog เพื่อไม่ซ้ำสองทะเบียน |
| `f1_pppconnext` | เป็นข้อมูล aggregate และรหัสระเบียน แก้ phone detector ที่เคยจับตัวเลขใน ID/hash โดยผิดบริบท |
| `f1_sradss_ppaos` | ตัวเลขโครงการและ aggregate ใช้ได้ แก้ hash ที่ถูกมองเป็นโทรศัพท์ ส่วน flags เรื่อง authorization/cookie เป็น metadata ของหลักฐาน ไม่ใช่ความลับจริงและไม่ต้องตัดทั้ง dataset |
| `f2_apptech_mru` | คืนเครดิตเจ้าของงาน ผู้วิจัย และเจ้าของสิทธิ์ ตรวจข้อมูลใน ZIP และ Silver ประกอบ |
| `f2_culturalmap_university` | คืนรายละเอียดสถานที่ เครดิตผู้จัดทำ และช่องทางติดต่องาน แยก account IDs ออกจากข้อมูลผู้รับผิดชอบ |
| `f2_learning_area_based` | 1,002 รายการ ชื่อธุรกิจ โครงการ หน่วยวิจัย และพื้นที่ยังใช้ได้ ไม่มีเหตุให้ห้ามทั้งชุด |
| `f2_learning_dashboard` | ข้อมูลจังหวัดและ aggregate คงเดิม ไม่เปลี่ยนยอดผู้เข้าร่วมให้เป็นรายชื่อบุคคล |
| `f2_rmutdb` | อ่าน PDF สาธารณะครบ 11 เล่ม คืนผู้ประดิษฐ์/ผู้ประสานงานและข้อมูลติดต่องาน |
| `f2_target_household` | เส้นทางที่ใช้อยู่เป็นตลาดผลงานสาธารณะ ไม่ตีความชื่อ source ว่าเป็นข้อมูลครัวเรือนทั้งหมด แก้ข้อความกฎที่เหมารวมและ false positive ใน hash |
| `f2_wallet_all_realtime` | เป็นยอดรวมครัวเรือน/ธุรกิจ ใช้ได้ตาม grain เดิม |
| `f2_wallet_cluster_realtime` | เป็น aggregate ระดับกลุ่ม ใช้ได้ตาม grain เดิม |
| `f3_city_capital_open_data` | ข้อมูลระดับเมือง/เทศบาลใช้ได้ ไม่พบเครดิตผลงานที่ถูกตัดในเส้นทางนี้ |
| `f3_housing_portal` | คืนรายละเอียด public places 28,694 จุด แยกจาก respondent demand ซึ่งเป็นคนละ dataset |
| `f3_learning_city_platform` | พบข้อมูลติดต่อสำนักงานในหน้าเว็บและ raw text ใช้ public_contact ได้เมื่อสร้าง projection ของแหล่งนี้ ปัจจุบันยังไม่มี value builder จึงไม่เพิ่มข้อมูลดิบลง public โดยตรง |
| `f3_ruamthiao_lamphun` | คืนข้อมูลติดต่อบริการและผู้ผลิตตามหน้าสาธารณะ |
| `pmua_area_lookup` | เป็นข้อมูลพื้นที่ ไม่มีฟิลด์เจ้าของงานให้คืน |
| `pmua_product_details` | 1,160 รายการ schema ที่เก็บไม่มีฟิลด์เจ้าของงาน จึงไม่สร้างชื่อขึ้นเอง |
| `spu_nsn_flood` | ใช้ข้อมูลสถานการณ์และพื้นที่ แก้ hash false positive ที่พบในหลักฐาน |
| `spu_rawangphai_uru` | ข้อมูลสถานี/สถานะ ไม่มีการตัดชื่อเจ้าของผลงานในเส้นทางนี้ |
| `spu_sukhothai_care` | address ผูกกับเหตุการณ์และผู้แจ้ง ไม่ใช่ข้อมูลติดต่องานของเจ้าของผลงาน จึงยังไม่เปลี่ยนเป็น public_location ทั้งคอลัมน์ ข้อมูลเหตุการณ์ส่วนอื่นยังใช้ได้ |
| `spu_sukhothai_water` | ตัวเลขและสถานีสาธารณะใช้ได้ ไม่มีเครดิตเจ้าของงานที่ต้องคืน |

Source ที่ไม่มีข้อมูลใน R2 รอบนี้คงสถานะตามหลักฐานเดิม ไม่อ้างว่าได้ตรวจค่าที่ไม่มีอยู่ แหล่ง Nonthaburi ที่เป็นข้อมูลสุขภาพ/ครัวเรือนระดับบุคคลยังคง restricted ส่วน source metadata อื่นไม่ได้ถูกเปลี่ยนเป็น restricted เพียงเพราะอาจมีชื่อคน

Source card ของ CLIG อยู่ที่ `data/source_audit/29_clig_projects/source_card.json` ใน evidence workspace, SHA-256 `30522aada66715ef567678f0b77eda2762cefb08b18fce7f0f733351242bc66d` อ้าง manifest ของ `raw/f4/clig_projects/20260823T072251Z/` และ `raw/f4/f4_research_dashboard_psu/20260825T033958Z/` พร้อมผลตรวจ hash และการจับคู่ 107 โครงการ Catalog/coverage ต้องอ่าน source card จริง ไม่ใช้ connector contract แทนหลักฐานการตรวจ

## ทำงานร่วมกันง่ายขึ้น

- ประกาศ `field_contexts` ครั้งเดียวต่อ grain/output ใช้ซ้ำทุกรอบ ไม่ขออนุญาตทีละ record
- `tools/preview_privacy.py` แสดง path ที่เปลี่ยนและเหตุผล โดยไม่พิมพ์ค่าข้อมูลติดต่อ ทดลองกับ JSON, JSONL, CSV และ gzip ได้
- Candidate ingest/status แยกจากการโหลด public release จึงทดลอง connector ได้แม้กำลังแก้ public artifact อยู่
- ตัวตรวจ connector ยอมให้พัฒนา non-restricted source ก่อนเปิดค่าใน production ได้ โดย production gate ยังตรวจตอนนำไปใช้งานจริง
- scaffold publication รองรับ `--field-context` จึงไม่ต้องเปลี่ยนชื่อคอลัมน์เพื่อหลบข้อห้าม
- ตัวตรวจโทรศัพท์แยก hash, รหัสที่ติดตัวอักษร และเลขทศนิยมออกจากเบอร์โทร หากเป็นรหัสตัวเลขล้วนที่กำกวม ใช้ record_identifier หรือ public_measure ตามหลักฐาน
- หน้า Insights มีทะเบียนที่ค้นหาชื่อผลงาน/ผู้รับผิดชอบได้ และหน้า dashboard แสดงเครดิต MRU, Cultural Map และเบอร์บริการลำพูน

รายละเอียดวิธีใช้อยู่ใน [field-contexts.md](field-contexts.md) ใช้ deterministic build และ `python -m app.cli check` เป็นชุดตรวจเดียวของทีม ไม่ได้แก้หรือลบ canonical R2 objects และยังไม่มีการ deploy การเปลี่ยนแปลงนี้

## ผลตรวจหลังแก้

- `python -m app.cli check` ผ่านครบ compile, connector validation, publication validation, public repository boundary และ pytest
- Publication ตรวจ 178 ไฟล์, 14 contracts และ 176 artifacts ผ่าน
- pytest รอบก่อน review ผ่าน 477 ข้อ ข้าม 1 ข้อที่ต้องมีชุด endpoint evidence เต็มนอก public clone; หลัง review เพิ่ม regression เรื่อง source card, ชื่อผู้รับผิดชอบ 9 รูปแบบ และเบอร์โทรติดข้อความไทย โดยชุดตรวจเฉพาะส่วนผ่าน 53 ข้อ ผล CI ของ revision ล่าสุดดูที่ PR
- สร้าง public builders ซ้ำด้วย inputs และ timestamp เดิมได้ bytes เดิม รวมการตรวจ CLIG เพิ่มแยกอีกครั้ง
- ตรวจหน้า Insights จริง: ค้นหา สลับ MTR/RMUTDB/Cultural Map และแสดงรายการเพิ่มได้ ข้อมูลชื่อและช่องทางติดต่องานปรากฏในการ์ด
- ตรวจ API และหน้า F4 จริง: ส่ง 107 โครงการ พร้อมชื่อผู้วิจัยไทย 96 และอังกฤษ 92 รายการ และแสดงชื่อในการ์ดโครงการ ไม่มี browser console error ระหว่างตรวจ
- ตัวตรวจ URL รองรับ query template ที่ registry ประกาศ เช่น `id={project_id}` พร้อมทดสอบว่าการเปลี่ยน route, fixed filter หรือเพิ่ม parameter อื่นยังไม่ผ่าน
