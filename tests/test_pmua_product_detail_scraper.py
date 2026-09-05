from __future__ import annotations

from tools.scrape_pmua_product_details import parse_product_detail_html


def test_parse_product_detail_extracts_trl_and_coordinates() -> None:
    html = """
    <html>
      <head><meta property="og:title" content="ระบบไบโอฟลอคสำหรับการเลี้ยงปลา"></head>
      <body>
        <span id="viewMapLatLngText">13.816132,100.560259</span>
        <div class="sidebar-card">
          <h6 class="sidebar-header">ระดับความพร้อม (TRL)</h6>
          <div class="d-flex justify-content-between font-weight-bold mb-3">
            <span class="text-primary small">ระดับ 9</span>
            <span class="text-dark small">พร้อมใช้</span>
          </div>
        </div>
      </body>
    </html>
    """

    row = parse_product_detail_html(html, 3788, "https://pmua-apptech.com/product/show/3788")

    assert row["product_id"] == 3788
    assert row["title"] == "ระบบไบโอฟลอคสำหรับการเลี้ยงปลา"
    assert row["trl_level"] == 9
    assert row["trl_status"] == "พร้อมใช้"
    assert "roi_indicator" not in row
    assert "sroi_indicator" not in row
    assert row["latitude"] == 13.816132
    assert row["longitude"] == 100.560259


def test_parse_product_detail_omits_roi_placeholders() -> None:
    html = """
    <div class="content-card">
      <h5>ROI (Economic)</h5>
      <div><strong>ตัวชี้วัด:</strong> <span class="text-muted"></span></div>
      <div><strong>ปริมาณ:</strong> <span></span></div>
    </div>
    <div class="sidebar-card">
      <h6>ระดับความพร้อม (TRL)</h6>
      <span class="text-primary small">ระดับ 9</span>
      <span class="text-dark small">พร้อมใช้</span>
    </div>
    """

    row = parse_product_detail_html(html, 1, "https://pmua-apptech.com/product/show/1")

    assert row["trl_level"] == 9
    assert row["trl_status"] == "พร้อมใช้"
    assert "roi_indicator" not in row
    assert "roi_value" not in row
    assert "roi_unit" not in row


def test_metric_sections_do_not_borrow_values_from_the_next_heading() -> None:
    html = """
    <h5>ผลลัพธ์ (Outcomes)</h5><p>ยังไม่มีข้อมูล</p>
    <h5>ผลกระทบ (Impacts)</h5>
    <ul><li><span>ผลกระทบทดสอบ</span><span>12 <small>หน่วยทดสอบ</small></span></li></ul>
    """
    row = parse_product_detail_html(html, 1, "https://pmua-apptech.com/product/show/1")
    assert row["outcomes"] == []
    assert row["impacts"] == [{
        "label": "ผลกระทบทดสอบ", "value": 12, "value_text": "12",
        "unit": "หน่วยทดสอบ", "evidence_type": "source_reported",
    }]
