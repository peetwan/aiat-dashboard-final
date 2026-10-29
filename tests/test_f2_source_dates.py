"""The two dates behind every F2 number: when we fetched a source (Clean) and when it says it last changed (Publish)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from tools.f2.clean import Raw, atlocal, cultural_map, fetched, icommunity, learning_area_based, rinmp, updated_dates
from tools.f2.publish import _sources

FETCHED = datetime(2026, 10, 13, 4, 48, tzinfo=timezone.utc)  # 11:48 in Thailand


def test_updated_dates_are_thai_days_up_to_the_fetch_day():
    values = ["2026-09-15T10:00:00.000Z", "2025-08-24 10:11:45", "2026-10-13T23:00:00", "2026-10-14", None, "", "soon"]
    assert updated_dates(values, FETCHED) == [date(2026, 9, 15), date(2025, 8, 24), date(2026, 10, 13)]
    # an evening UTC fetch is already the next day in Thailand: a stamp from that Thai morning counts
    evening = datetime(2026, 10, 13, 18, 30, tzinfo=timezone.utc)
    assert updated_dates(["2026-10-14T00:15:00+07:00", "2026-10-13T20:00:00Z"], evening) == [date(2026, 10, 14)] * 2


def test_fetched_reads_the_manifest_and_needs_a_time_zone(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"fetched_at": "2026-10-13T04:48:00+00:00"}), encoding="utf-8")
    assert fetched(tmp_path) == FETCHED
    (tmp_path / "manifest.json").write_text(json.dumps({"fetched_at": "2026-10-13T04:48:00"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="time zone"):
        fetched(tmp_path)
    (tmp_path / "manifest.json").unlink()
    with pytest.raises(SystemExit, match="fetched_at"):
        fetched(tmp_path)


def test_each_reader_takes_the_change_stamp_not_creation_or_scrape_dates(tmp_path):
    def raw(files: dict) -> Raw:
        for name, payload in files.items():
            (tmp_path / name).write_text(json.dumps({"scraped_at": "2026-10-13T00:00:00Z", "data": payload}), encoding="utf-8")
        return Raw(tmp_path)

    assert rinmp.updated(raw({"app_tech.json": {"records": [
        {"source_created_at": "2024-01-01T00:00:00", "source_last_update_at": "2026-10-06T08:00:00"}]}})) == ["2026-10-06T08:00:00"]
    assert atlocal.updated(raw({"marketplace_products.json": [
        {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-09-15T00:00:00Z"}]})) == ["2026-09-15T00:00:00Z"]
    assert cultural_map.updated(raw({"map_inspiration.json": {"records": [
        {"data": {"dates": {"inserted": "2021-09-12T14:08:45", "recorded": "2021-08-29", "updated": "2026-09-18T10:00:00"}}},
        {"data": {"dates": None}}, {"data": None}]}})) == ["2026-09-18T10:00:00", None, None]
    assert icommunity.updated(raw({"activity_posts.json": [{"published_at": "2023-09-12T00:00:00", "modified_at": "2025-09-09T17:16:00"}],
                                  "programme_background.json": [{"published_at": "2024-09-10T00:00:00", "modified_at": "2025-12-01T12:00:19"}]})
                              ) == ["2025-09-09T17:16:00", "2025-12-01T12:00:19"]
    assert learning_area_based.updated(raw({"area_based.json": [
        {"createdAt": "2025-01-01 00:00:00", "updatedAt": "2025-08-24 10:11:45", "fiscalYear": 2567}]})) == ["2025-08-24 10:11:45"]


def test_sources_say_whether_a_change_stamp_falls_within_the_window():
    config = {"source_ids": ["a", "b", "c"],
              "source_dates": {"updated_within_days": 365, "updated_basis_th": {"a": "นวัตกรรม", "b": "สินค้า"}}}
    stamp = FETCHED.isoformat()
    out = _sources(config, [("a", stamp, date(2025, 10, 13), 10, 4), ("b", stamp, date(2025, 10, 12), 3, 1), ("c", stamp, None, 0, 0)])
    assert out["updated_within_days"] == 365
    by_id = out["by_id"]
    assert by_id["a"] == {"source_id": "a", "fetched_at": stamp, "fetched_date": "2026-10-13", "freshness": "stamped_within_window",
                          "updated": {"latest": "2025-10-13", "records": 10, "days": 4, "basis_th": "นวัตกรรม"}}
    assert by_id["b"]["freshness"] == "none_within_window"  # 366 days before the fetch day
    assert by_id["c"]["updated"] is None and by_id["c"]["freshness"] == "no_date"
    # the fetch day is the Thai day: 18:30 UTC on 13 October is 14 October in Thailand
    late = _sources(config, [("a", "2026-10-13T18:30:00+00:00", date(2025, 10, 14), 1, 1), ("b", stamp, None, 0, 0), ("c", stamp, None, 0, 0)])
    assert late["by_id"]["a"]["fetched_date"] == "2026-10-14" and late["by_id"]["a"]["freshness"] == "stamped_within_window"

    with pytest.raises(SystemExit, match="no basis"):
        _sources(config, [("a", stamp, None, 0, 0), ("b", stamp, None, 0, 0), ("c", stamp, date(2026, 1, 1), 1, 1)])
    with pytest.raises(SystemExit, match="differ"):
        _sources(config, [("a", stamp, None, 0, 0)])
