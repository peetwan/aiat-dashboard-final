from __future__ import annotations


# Presentation metadata only. Source identity, URL, policy, endpoints and live status
# continue to come from config/source_catalog.json and the serving database.
SOURCE_PROFILES: dict[str, dict[str, object]] = {
    "f1_sradss_ppaos": {
        "what_we_use_th": "ข้อมูลสรุประดับจังหวัดและปี ได้แก่ คะแนน/มิติความยากจน สถานการณ์ครัวเรือน การช่วยเหลือ ภาพรวมโครงการ กลุ่มโมเดลแก้จน (OM) และสรุปงานวิจัยจาก public aggregate APIs",
        "grain_th": "จังหวัด × ปี × ตัวชี้วัด หรือจังหวัด × ปี × ประเภทกิจกรรม ตาม endpoint ต้นทาง",
        "dashboard_use_th": "สถานการณ์และการดำเนินงาน SRA-DSS ในหน้าจังหวัด พร้อมแยก 20 จังหวัดเป้าหมายออกจาก 15 จังหวัดที่มีคะแนน",
        "excluded_th": "ไม่ใช้ household/person detail ที่ต้องล็อกอิน และไม่เผยแพร่ชื่อ เบอร์โทร อีเมลหรือรูปบุคคล",
        "database_targets": ["sources", "endpoints", "dashboard_records", "public_artifacts"],
    },
    "f1_pppconnext": {
        "what_we_use_th": "Aggregate 47 ระเบียนจาก API สาธารณะ 4 กลุ่ม: national bootstrap, province analytics, ศักยภาพทุน และสรุปการช่วยเหลือ",
        "grain_th": "หนึ่งค่า aggregate ของ widget/metric ต่อจังหวัด ปีสำรวจ และมิติที่ต้นทางกำหนด",
        "dashboard_use_th": "ภาพรวมครัวเรือน สมาชิก ความยากจน ทุน และการช่วยเหลือ โดยติดป้าย candidate",
        "excluded_th": "ไม่ใช้ survey analytics/detail ที่อยู่หลัง auth; snapshot chart เดิม 997,293 แถวเป็นหลักฐานประวัติ ไม่ใช่จำนวนครัวเรือน",
        "database_targets": ["sources", "endpoints", "dashboard_records", "public_artifacts"],
    },
    "f2_culturalmap_university": {
        "what_we_use_th": "ทุนวัฒนธรรมบนแผนที่, Inspiration, ผลิตภัณฑ์, กิจกรรม, Re-Creation และจำนวนข้อมูลสนับสนุนจาก public feed/listing",
        "grain_th": "หนึ่งระเบียนทุนวัฒนธรรม สถานที่ ผลิตภัณฑ์ หรือกิจกรรม ตามชุดข้อมูล",
        "dashboard_use_th": "จุดวัฒนธรรมบนแผนที่และจำนวนผลงานสนับสนุน; รายละเอียด public map 5,258 และ supporting 361 แบบ counts-only",
        "excluded_th": "ไม่เผยแพร่ข้อมูลติดต่อส่วนบุคคล และไม่เดาจังหวัดเมื่อพิกัด/ชื่อพื้นที่ไม่ยืนยัน",
        "database_targets": ["sources", "endpoints", "public_artifacts"],
    },
    "f2_cultural_market_civil": {
        "what_we_use_th": "ปัจจุบันเก็บเฉพาะทะเบียนเว็บไซต์; ข้อมูลที่ต้องสำรวจต่อคือสินค้า ผู้ประกอบการ และพื้นที่ตลาดวัฒนธรรม",
        "grain_th": "ยังไม่กำหนด เพราะยังไม่มี value dataset ใน Serving Database",
        "dashboard_use_th": "แสดงสถานะและ URL ใน Source Coverage เท่านั้น",
        "excluded_th": "ยังไม่เผยแพร่ค่าข้อมูลหรือสร้าง KPI",
        "database_targets": ["sources"],
    },
    "f2_icommunity": {
        "what_we_use_th": "ปัจจุบันเก็บเฉพาะทะเบียนเว็บไซต์; อยู่ระหว่างตรวจ profile/detail และความซ้ำซ้อนกับ AppTech",
        "grain_th": "ยังไม่กำหนด เพราะยังไม่มี value dataset ใน Serving Database",
        "dashboard_use_th": "แสดงสถานะและ URL ใน Source Coverage เท่านั้น",
        "excluded_th": "ยังไม่เผยแพร่ค่าข้อมูลหรือสร้าง KPI",
        "database_targets": ["sources"],
    },
    "f2_rmutdb": {
        "what_we_use_th": "ข้อมูลห้องสมุดนวัตกรรมจาก e-book สาธารณะ 11 เล่ม รวม snapshot 2,001 แถว แยก detail 1,006 และ annual summary 995",
        "grain_th": "หนึ่งระเบียนองค์ความรู้/นวัตกรรม หรือหนึ่งแถวสรุปรายปี; สอง grain นี้ไม่นับรวมกันตรง ๆ",
        "dashboard_use_th": "Source Insights และข้อมูล non-geo เพราะยังไม่มี field จังหวัดที่ยืนยันได้",
        "excluded_th": "ไม่เรียก JSON API ที่ตอบ 401 และไม่เดาจังหวัดจากชื่อสถาบัน",
        "database_targets": ["sources", "endpoints", "public_artifacts"],
    },
    "f2_apptech_mtr": {
        "what_we_use_th": "ทะเบียนเทคโนโลยี/นวัตกรรมสาธารณะ 630 ระเบียน พร้อมสถิติผู้ใช้ ปฏิสัมพันธ์ สถาบัน และข้อมูลแผนที่จาก RinMP public APIs",
        "grain_th": "หนึ่งระเบียนเทคโนโลยี/นวัตกรรม หรือหนึ่งค่า aggregate กิจกรรมแพลตฟอร์มรายจังหวัด",
        "dashboard_use_th": "ภาพรวมการใช้งาน AppTech, นวัตกรรม และการเชื่อมพื้นที่ โดยคงสถานะ needs_review",
        "excluded_th": "ตัด email/phone และไม่ใช้ข้อมูลที่ไม่ได้อยู่ใน public API",
        "database_targets": ["sources", "endpoints", "dashboard_records", "public_artifacts"],
    },
    "f2_apptech_mru": {
        "what_we_use_th": "Public snapshot 503 ระเบียน แยกนวัตกรรม โจทย์ความต้องการ และข่าว; API รายงานนวัตกรรม 501 รายการ",
        "grain_th": "หนึ่งนวัตกรรม หนึ่งโจทย์ความต้องการ หรือหนึ่งข่าว — ต้องแยกนับตาม record type",
        "dashboard_use_th": "นวัตกรรม, TRL, พื้นที่ใช้งาน, ทรัพย์สินทางปัญญา และ ROI/SROI ที่ต้นทางมี",
        "excluded_th": "ไม่ bypass หน้า login และไม่ publish partial fetch ที่จำนวน unique IDs ไม่ครบ",
        "database_targets": ["sources", "endpoints", "dashboard_records", "public_artifacts"],
    },
    "f2_target_household": {
        "what_we_use_th": "รายการนวัตกรรมสาธารณะจากหน้ารวม /search ของ pmua-apptech.com ตัดชื่อ เบอร์โทร อีเมล",
        "grain_th": "หนึ่งนวัตกรรมต่อหนึ่ง product_id จากหน้ารวม ไม่ใช่ครัวเรือนหรือบุคคลหนึ่งราย",
        "dashboard_use_th": "Candidate รายการสินค้า/เทคโนโลยีพร้อมใช้; ยังไม่ใช่ KPI และยังไม่แตกแผนที่ครัวเรือน",
        "excluded_th": "ไม่ใช้ login/EPMS, ไม่ GET หน้ารายละเอียดตอน ingest และไม่แตก /dashboard/familydashboard เป็นแถวครัวเรือน",
        "database_targets": ["sources", "endpoints", "dashboard_records", "public_artifacts"],
    },
    "f2_learning_dashboard": {
        "what_we_use_th": "Candidate aggregate ระดับจังหวัด 66 แถวจาก PMUA Dashboard สำหรับธุรกิจ/ผู้เข้าร่วมโครงการที่ต้นทางเลือก",
        "grain_th": "หนึ่งค่า aggregate ต่อจังหวัดของ selected-project scope ไม่ใช่จำนวนธุรกิจทั้งหมดในจังหวัด",
        "dashboard_use_th": "ภาพรวมธุรกิจชุมชนในกลุ่มผู้เข้าร่วมโครงการ",
        "excluded_th": "ไม่ตีความเป็นประชากรทั้งหมด และไม่ใช้เป็น accepted KPI จนกว่าจะยืนยัน scope/unit/as_of",
        "database_targets": ["sources", "endpoints", "dashboard_records", "public_artifacts"],
    },
    "f2_learning_area_based": {
        "what_we_use_th": "ระเบียนหน่วย/ผู้ประกอบการเข้าร่วม Area-Based 1,002 แถว ครอบคลุม 55 จังหวัด 256 อำเภอ และ 533 ตำบล",
        "grain_th": "หนึ่งระเบียนผู้เข้าร่วมหรือธุรกิจ ไม่ใช่หนึ่งโครงการ; โครงการ 73 กลุ่มเป็น provisional grouping จากชื่อ+ปี+หน่วยวิจัย",
        "dashboard_use_th": "ผู้เข้าร่วม โครงการชั่วคราว พื้นที่ หน่วยวิจัย นวัตกรรม และผลลัพธ์ในหน้าจังหวัด",
        "excluded_th": "6 ระเบียนที่จับคู่จังหวัดไม่ได้อยู่ใน unmapped; ไม่เดาพื้นที่และไม่เรียก 1,002 แถวว่า 1,002 โครงการ",
        "database_targets": ["sources", "endpoints", "dashboard_records", "public_artifacts"],
    },
    "f2_wallet_all_realtime": {
        "what_we_use_th": "Aggregate เดือนปัจจุบันของกระเป๋าครัวเรือนและธุรกิจจาก public POST {date:\"\"} สองเส้นทาง",
        "grain_th": "เดือนปัจจุบัน × ประเภทกระเป๋าหนึ่งชุด ไม่ใช่รายการธุรกรรมรายบุคคล",
        "dashboard_use_th": "Candidate ตัวเลขรวมที่หน้าข้อมูลเปิดแสดง; ยังต้องทบทวนหน่วย/ตัวหารก่อนเป็น KPI",
        "excluded_th": "ไม่ดึงประวัติรายเดือนทั้งหมดตอน serving และไม่ใช้ GET ที่ตอบ 405",
        "database_targets": ["sources", "endpoints", "dashboard_records", "public_artifacts"],
    },
    "f2_wallet_cluster_realtime": {
        "what_we_use_th": "Aggregate เดือนปัจจุบันเปรียบเทียบตามกลุ่มธุรกิจจาก public POST ว่าง สองเส้นทาง",
        "grain_th": "เดือนปัจจุบัน × กลุ่มธุรกิจ × ประเภทครัวเรือน/ธุรกิจ ไม่ใช่รายบุคคล",
        "dashboard_use_th": "Candidate ตัวเลขรวมรายกลุ่มที่หน้าข้อมูลเปิดแสดง; กลุ่มขนาดเล็กยัง needs_review",
        "excluded_th": "ไม่เทียบยอดรวมที่ frontend ฮาร์ดโค้ดกับผลรวมหมวด API และไม่แตกเป็นรายบุคคล",
        "database_targets": ["sources", "endpoints", "dashboard_records", "public_artifacts"],
    },
    "f3_city_capital_open_data": {
        "what_we_use_th": "ข้อมูลทุนเมือง 18 เมือง × นิยามตัวชี้วัด 39 รายการ รวม 702 city-metric observations จาก public snapshot",
        "grain_th": "หนึ่งเทศบาล/เมือง × หนึ่ง metric; ไม่ใช่ค่ารวมทั้งจังหวัด",
        "dashboard_use_th": "Source Insights และบริบททุนเมือง โดยคงระดับเทศบาล",
        "excluded_th": "ไม่ยกค่าเทศบาลเป็นค่าจังหวัดและไม่แทน 4 ค่า null ด้วยศูนย์",
        "database_targets": ["sources", "endpoints", "public_artifacts"],
    },
    "f3_nonthaburi_city_learning": {
        "what_we_use_th": "ชั้นข้อมูล ArcGIS/GIS ที่หน้าเว็บสาธารณะเปิดไว้ ใช้ตรวจใน local lane",
        "grain_th": "หนึ่ง GIS feature ตามชั้นข้อมูลต้นทาง",
        "dashboard_use_th": "Cloud แสดงเพียง metadata และสถานะ restricted",
        "excluded_th": "ไม่ส่ง values ขึ้น Cloud และตัดชื่อ เบอร์โทร อีเมลถ้ามี",
        "database_targets": ["sources"],
    },
    "f3_ruamthiao_lamphun": {
        "what_we_use_th": "ข้อมูลสาธารณะ 5 หน้า ได้แก่ homepage, สถานที่แนะนำ, การเดินทาง, กลุ่มโคม และ contact รวม 54 primary records/157 content items",
        "grain_th": "หนึ่งสถานี/สถานที่/คำแนะนำ/เส้นทาง/กลุ่มโคม หรือ content item ตามหน้าต้นทาง",
        "dashboard_use_th": "ข้อมูลการท่องเที่ยวและวัฒนธรรมของลำพูนใน Source Insights/หน้าจังหวัด",
        "excluded_th": "ไม่รวม contact fields ที่ระบุตัวบุคคล และไม่สร้าง as_of หากต้นทางไม่ระบุ",
        "database_targets": ["sources", "endpoints", "public_artifacts"],
    },
    "f3_ruamrian": {
        "what_we_use_th": "ปัจจุบันเก็บเฉพาะทะเบียนเว็บไซต์ร่วมเรียนและ URL; ต้องตรวจ canonical domain และชุดบทเรียน/สไลด์ต่อ",
        "grain_th": "ยังไม่กำหนด เพราะยังไม่มี value dataset ใน Serving Database",
        "dashboard_use_th": "แสดงสถานะและ URL ใน Source Coverage เท่านั้น",
        "excluded_th": "ยังไม่เผยแพร่ค่าข้อมูลหรือสร้าง KPI",
        "database_targets": ["sources"],
    },
    "f3_ruamkhai": {
        "what_we_use_th": "ปัจจุบันเก็บเฉพาะทะเบียนเว็บไซต์ร่วมขาย; ข้อมูลที่ต้องสำรวจต่อคือสินค้าและผู้ประกอบการ",
        "grain_th": "ยังไม่กำหนด เพราะยังไม่มี value dataset ใน Serving Database",
        "dashboard_use_th": "แสดงสถานะและ URL ใน Source Coverage เท่านั้น",
        "excluded_th": "ยังไม่เผยแพร่ค่าข้อมูลหรือสร้าง KPI",
        "database_targets": ["sources"],
    },
    "f3_ruamjai_thungsong": {
        "what_we_use_th": "ปัจจุบันเก็บเฉพาะทะเบียน Flood Dashboard; ต้องตรวจสถานี ค่าตรวจวัด timestamp และประวัติย้อนหลังต่อ",
        "grain_th": "คาดว่าเป็นสถานี × เวลา × ตัวแปรวัด แต่ยังไม่ยืนยัน contract",
        "dashboard_use_th": "แสดงสถานะและ URL ใน Source Coverage เท่านั้น",
        "excluded_th": "ยังไม่เผยแพร่ค่าข้อมูลหรือสร้าง KPI",
        "database_targets": ["sources"],
    },
    "f3_healthcare_nonthaburi": {
        "what_we_use_th": "GIS สุขภาพที่หน้าเว็บสาธารณะเรียก ใช้สำรวจใน local lane เท่านั้น",
        "grain_th": "หนึ่ง GIS/health observation ตามชั้นข้อมูลต้นทาง",
        "dashboard_use_th": "Cloud แสดงเพียง metadata และสถานะ restricted",
        "excluded_th": "ไม่ส่ง values ขึ้น Cloud และตัดชื่อ เบอร์โทร อีเมลถ้ามี",
        "database_targets": ["sources"],
    },
    "f3_ciap_smartcity": {
        "what_we_use_th": "ปัจจุบันเก็บเฉพาะทะเบียน Smart City Executive Dashboard และสถานะการเข้าถึง",
        "grain_th": "ยังไม่กำหนด; ต้องตรวจนิยาม indicator และระดับพื้นที่",
        "dashboard_use_th": "แสดงสถานะและ URL ใน Source Coverage เท่านั้น",
        "excluded_th": "ยังไม่เผยแพร่ค่าข้อมูลหรือสร้าง KPI",
        "database_targets": ["sources"],
    },
    "f3_learning_city_platform": {
        "what_we_use_th": "ปัจจุบันเก็บเฉพาะทะเบียน Learning City Platform; ต้องตรวจ city profile, assessment และ learning manager ต่อ",
        "grain_th": "ยังไม่กำหนด; คาดว่ามีทั้งเมือง ตัวชี้วัด และ profile",
        "dashboard_use_th": "แสดงสถานะและ URL ใน Source Coverage เท่านั้น",
        "excluded_th": "ยังไม่เผยแพร่ค่าข้อมูลหรือสร้าง KPI",
        "database_targets": ["sources"],
    },
    "f3_housing_portal": {
        "what_we_use_th": "CKAN 7 datasets/41 resources, public projection 7,259 แถว, Housing Demand 25,919 แถว และ spatial features 194,532 รายการ",
        "grain_th": "มีหลาย grain แยกกัน: resource observation, ผู้ตอบแบบสำรวจหนึ่งแถว, จุดที่อยู่อาศัยหนึ่งจุด และ grid/ขอบเขตหนึ่ง feature",
        "dashboard_use_th": "ความต้องการ/อุปทาน/เศรษฐกิจ/ดัชนีที่อยู่อาศัย สรุปรายจังหวัด และ 4 spatial layers",
        "excluded_th": "Demand ตัด source ID ชื่อ เบอร์โทร อีเมล; ห้ามรวม respondent, CKAN row และ spatial feature เป็นตัวเลขเดียว",
        "database_targets": ["sources", "endpoints", "public_artifacts", "spatial_layer_snapshots", "spatial_features", "housing_demand_snapshots", "housing_demand_records"],
    },
    "f4_research_dashboard_psu": {
        "what_we_use_th": "ปัจจุบันเก็บเฉพาะทะเบียน Research Dashboard; เป็น candidate สำคัญสำหรับข้อมูลระดับโครงการและต้องตรวจ export/API/auth ต่อ",
        "grain_th": "คาดว่าเป็นหนึ่งโครงการวิจัย แต่ยังไม่ยืนยัน contract",
        "dashboard_use_th": "แสดงสถานะและ URL ใน Source Coverage เท่านั้น",
        "excluded_th": "ยังไม่เผยแพร่ค่าข้อมูลหรือสร้าง KPI",
        "database_targets": ["sources"],
    },
    "clig_projects": {
        "what_we_use_th": "ข้อมูลโครงการวิจัยเสริมพลังท้องถิ่นจาก CLIG 107 โครงการ พร้อมรายละเอียด สถานะ ปีงบประมาณ เลขสัญญา หน่วยงานหลัก และงบประมาณเมื่อพบในหน้ารายละเอียด",
        "grain_th": "หนึ่งแถว = หนึ่งโครงการวิจัยจาก CLIG; policy_candidates เป็น subset ที่ tag จากคำเกี่ยวกับ อปท./นโยบาย/กลไก/มาตรการ",
        "dashboard_use_th": "ใช้เป็น evidence drilldown สำหรับ F4 นวัตกรรมเชิงนโยบาย รวมถึงสถานะโครงการ งบประมาณรวม และการจับคู่จังหวัดจากข้อความภาษาไทย",
        "excluded_th": "ไม่เรียก login/admin/write endpoints, ไม่ดาวน์โหลดไฟล์แนบ และไม่เผยแพร่ข้อมูลติดต่อหรือข้อมูลบุคคล",
        "database_targets": ["sources", "endpoints", "dashboard_records", "public_artifacts"],
    },
    "spu_sukhothai_care": {
        "what_we_use_th": "ปัจจุบันเก็บเฉพาะทะเบียน Sukhothai Care; ต้องสำรวจข้อมูลบริการ/ชุมชนที่หน้าเว็บเปิดต่อ",
        "grain_th": "ยังไม่กำหนด เพราะยังไม่มี value dataset ใน Serving Database",
        "dashboard_use_th": "แสดงสถานะและ URL ใน Source Coverage เท่านั้น",
        "excluded_th": "ยังไม่เผยแพร่ values; ตัดชื่อ เบอร์โทร อีเมลหากทำ extracted",
        "database_targets": ["sources"],
    },
    "spu_sukhothai_water": {
        "what_we_use_th": "ปัจจุบันเก็บเฉพาะทะเบียน Water/Disaster Dashboard; ต้องตรวจค่าตรวจวัดย้อนหลัง timestamp และ endpoint ต่อ",
        "grain_th": "คาดว่าเป็นจุด/สถานี × เวลา × ตัวแปรน้ำ แต่ยังไม่ยืนยัน contract",
        "dashboard_use_th": "แสดงสถานะและ URL ใน Source Coverage เท่านั้น",
        "excluded_th": "ยังไม่เผยแพร่ค่าข้อมูลหรือสร้าง KPI",
        "database_targets": ["sources"],
    },
    "spu_nsn_flood": {
        "what_we_use_th": "ปัจจุบันเก็บเฉพาะทะเบียน NSN Flood และสถานะโดเมน; ต้องตรวจ feed น้ำ/น้ำท่วมและ freshness ต่อ",
        "grain_th": "ยังไม่กำหนด; คาดว่าเป็นสถานีหรือเหตุการณ์ × เวลา",
        "dashboard_use_th": "แสดงสถานะและ URL ใน Source Coverage เท่านั้น",
        "excluded_th": "ยังไม่เผยแพร่ค่าข้อมูลหรือสร้าง KPI",
        "database_targets": ["sources"],
    },
    "spu_rawangphai_uru": {
        "what_we_use_th": "ปัจจุบันเก็บเฉพาะทะเบียน Smart Disaster Platform; ต้องตรวจ alert feed, incident history และ API/JSON ต่อ",
        "grain_th": "คาดว่าเป็นหนึ่ง alert/incident หรือหนึ่งสถานี × เวลา แต่ยังไม่ยืนยัน contract",
        "dashboard_use_th": "แสดงสถานะและ URL ใน Source Coverage เท่านั้น",
        "excluded_th": "ยังไม่เผยแพร่ค่าข้อมูลหรือสร้าง KPI",
        "database_targets": ["sources"],
    },
}


def validate_profile_coverage(source_ids: set[str]) -> None:
    profile_ids = set(SOURCE_PROFILES)
    if profile_ids != source_ids:
        missing = sorted(source_ids - profile_ids)
        extra = sorted(profile_ids - source_ids)
        raise RuntimeError(f"source profile coverage mismatch: missing={missing}, extra={extra}")
