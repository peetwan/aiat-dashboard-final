from __future__ import annotations

from datetime import datetime, timezone

from app.connectors.base import ConnectorContext, DatasetRecord

PRESENTATION_KEYS = {
    "avg_color", "color", "colors", "style", "styles",
    "class", "className", "background", "backgroundColor",
}


def _without_presentation(value):
    if isinstance(value, dict):
        return {
            k: _without_presentation(v)
            for k, v in value.items()
            if k not in PRESENTATION_KEYS
        }
    if isinstance(value, list):
        return [_without_presentation(v) for v in value]
    return value


def _data_payload(data):
    if isinstance(data, dict):
        if isinstance(data.get("data"), list):
            return data["data"]
        if isinstance(data.get("features"), list):
            return data["features"]
    if isinstance(data, list):
        return data
    raise RuntimeError("RawangPhai response has no supported object-list payload")


def _flatten_water_level(record, source_url, fetched_at):
    cleaned = _without_presentation(record)
    return {
        "source_url": source_url,
        "fetched_at": fetched_at,
        "station_id": cleaned.get("stationId"),
        "old_code": cleaned.get("oldCode"),
        "name_th": cleaned.get("nameTh"),
        "name_en": cleaned.get("nameEn"),
        "river": cleaned.get("river"),
        "province": cleaned.get("province"),
        "district": cleaned.get("district"),
        "subdistrict": cleaned.get("subdistrict"),
        "lat": cleaned.get("lat"),
        "lng": cleaned.get("lng"),
        "water_level_msl": cleaned.get("waterLevelMsl"),
        "water_level_msl_prev": cleaned.get("waterLevelMslPrev"),
        "bank_level": cleaned.get("bankLevel"),
        "ground_level": cleaned.get("groundLevel"),
        "storage_percent": cleaned.get("storagePercent"),
        "diff_from_bank": cleaned.get("diffFromBank"),
        "diff_from_bank_display": cleaned.get("diffFromBankDisplay"),
        "diff_from_bank_text": cleaned.get("diffFromBankText"),
        "situation_level": cleaned.get("situationLevel"),
        "situation_text": cleaned.get("situationText"),
        "measured_at": cleaned.get("measuredAt"),
        "updated_at": cleaned.get("updatedAt") or cleaned.get("datetime") or cleaned.get("timestamp"),
        "agency_name": cleaned.get("agencyName"),
    }


def _flatten_rain_analysis(record, source_url, fetched_at):
    cleaned = _without_presentation(record)
    utm = cleaned.get("utm_bounds") if isinstance(cleaned.get("utm_bounds"), dict) else {}
    pixel = cleaned.get("pixel_bounds") if isinstance(cleaned.get("pixel_bounds"), dict) else {}
    return {
        "source_url": source_url,
        "fetched_at": fetched_at,
        "id": cleaned.get("id") or cleaned.get("_id"),
        "timestamp": cleaned.get("timestamp"),
        "province": cleaned.get("province"),
        "point_no": cleaned.get("point_no"),
        "id_utm": cleaned.get("id_utm"),
        "image_file": cleaned.get("image_file"),
        "avg_rain_mm": cleaned.get("avg_rain_mm"),
        "max_rain_mm": cleaned.get("max_rain_mm"),
        "min_rain_mm": cleaned.get("min_rain_mm"),
        "avg_dbz": cleaned.get("avg_dbz"),
        "rain_coverage_percent": cleaned.get("rain_coverage_percent"),
        "is_active": cleaned.get("is_active"),
        "utm_min_x": utm.get("min_x"),
        "utm_max_x": utm.get("max_x"),
        "utm_min_y": utm.get("min_y"),
        "utm_max_y": utm.get("max_y"),
        "pixel_min_x": pixel.get("min_x"),
        "pixel_max_x": pixel.get("max_x"),
        "pixel_min_y": pixel.get("min_y"),
        "pixel_max_y": pixel.get("max_y"),
    }


def _flatten_shelter(record, source_url, fetched_at):
    cleaned = _without_presentation(record)
    return {
        "source_url": source_url,
        "fetched_at": fetched_at,
        "id": cleaned.get("id") or cleaned.get("_id"),
        "name": cleaned.get("name") or cleaned.get("nameTh") or cleaned.get("title"),
        "province": cleaned.get("province"),
        "district": cleaned.get("district"),
        "subdistrict": cleaned.get("subdistrict"),
        "village": cleaned.get("village"),
        "lat": cleaned.get("lat") or cleaned.get("latitude"),
        "lng": cleaned.get("lng") or cleaned.get("longitude"),
        "capacity": cleaned.get("capacity"),
        "electricity": cleaned.get("electricity"),
        "water": cleaned.get("water"),
        "toilets": cleaned.get("toilets"),
        "address": cleaned.get("address"),
    }


_FLATTEN_MAP = {
    "water_levels": _flatten_water_level,
    "rain_analysis": _flatten_rain_analysis,
    "shelters": _flatten_shelter,
}


class SpuRawangphaiUruConnector:
    driver_name = "spu_rawangphai_uru"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        records: list[DatasetRecord] = []
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        for dataset in context.plan["datasets"]:
            name = dataset["name"]
            url = dataset["url"]
            flatten = _FLATTEN_MAP.get(name)

            response, _ = context.recorder.request("GET", url, name=name)
            payload = response.json()
            rows = _data_payload(payload)

            for row in rows:
                if not isinstance(row, dict):
                    raise RuntimeError(f"RawangPhai {name} returned a non-object row")
                if flatten:
                    row = flatten(row, url, fetched_at)
                records.append((f"{name}.row", row))

            if (
                context.settings.max_records_per_source > 0
                and len(records) > context.settings.max_records_per_source
            ):
                raise RuntimeError(
                    "RawangPhai max_records_per_source would truncate a complete snapshot; "
                    "partial commits are forbidden"
                )

        return records
