from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.connectors.base import ConnectorContext, DatasetRecord


def _nested_name(value: Any, lang: str = "th") -> str | None:
    if isinstance(value, dict):
        return value.get(lang) or value.get("en")
    if value is None:
        return None
    return str(value)


def _geocode_province_th(record: dict) -> str | None:
    geocode = record.get("geocode") if isinstance(record.get("geocode"), dict) else {}
    province = geocode.get("province_name") if isinstance(geocode.get("province_name"), dict) else {}
    return province.get("th")


def _flatten_water_level(record: dict, source_url: str, fetched_at: str) -> dict:
    station = record.get("station") if isinstance(record.get("station"), dict) else {}
    geocode = record.get("geocode") if isinstance(record.get("geocode"), dict) else {}
    agency = record.get("agency") if isinstance(record.get("agency"), dict) else {}
    basin = record.get("basin") if isinstance(record.get("basin"), dict) else {}
    return {
        "source_url": source_url,
        "fetched_at": fetched_at,
        "id": record.get("id"),
        "waterlevel_datetime": record.get("waterlevel_datetime"),
        "station_id": station.get("id"),
        "station_code": station.get("tele_station_oldcode"),
        "station_name_th": _nested_name(station.get("tele_station_name"), "th"),
        "station_name_en": _nested_name(station.get("tele_station_name"), "en"),
        "station_type": record.get("station_type") or station.get("tele_station_type"),
        "lat": station.get("tele_station_lat"),
        "lng": station.get("tele_station_long"),
        "province_th": _geocode_province_th(record),
        "province_en": _nested_name((geocode.get("province_name") or {}), "en"),
        "amphoe_th": _nested_name((geocode.get("amphoe_name") or {}), "th"),
        "tumbon_th": _nested_name((geocode.get("tumbon_name") or {}), "th"),
        "river_name": record.get("river_name"),
        "basin_th": _nested_name((basin.get("basin_name") or {}), "th"),
        "waterlevel_m": record.get("waterlevel_m"),
        "waterlevel_msl": record.get("waterlevel_msl"),
        "waterlevel_msl_previous": record.get("waterlevel_msl_previous"),
        "storage_percent": record.get("storage_percent"),
        "diff_wl_bank": record.get("diff_wl_bank"),
        "diff_wl_bank_text": record.get("diff_wl_bank_text"),
        "situation_level": record.get("situation_level"),
        "left_bank": station.get("left_bank"),
        "right_bank": station.get("right_bank"),
        "min_bank": station.get("min_bank"),
        "ground_level": station.get("ground_level"),
        "agency_name_th": _nested_name((agency.get("agency_name") or {}), "th"),
        "agency_shortname_th": _nested_name((agency.get("agency_shortname") or {}), "th"),
    }


def _flatten_rain_24h(record: dict, source_url: str, fetched_at: str) -> dict:
    station = record.get("station") if isinstance(record.get("station"), dict) else {}
    geocode = record.get("geocode") if isinstance(record.get("geocode"), dict) else {}
    agency = record.get("agency") if isinstance(record.get("agency"), dict) else {}
    basin = record.get("basin") if isinstance(record.get("basin"), dict) else {}
    return {
        "source_url": source_url,
        "fetched_at": fetched_at,
        "id": record.get("id"),
        "rainfall_datetime": record.get("rainfall_datetime"),
        "station_id": station.get("id"),
        "station_code": station.get("tele_station_oldcode"),
        "station_name_th": _nested_name(station.get("tele_station_name"), "th"),
        "station_name_en": _nested_name(station.get("tele_station_name"), "en"),
        "station_type": record.get("station_type") or station.get("tele_station_type"),
        "lat": station.get("tele_station_lat"),
        "lng": station.get("tele_station_long"),
        "province_th": _geocode_province_th(record),
        "province_en": _nested_name((geocode.get("province_name") or {}), "en"),
        "amphoe_th": _nested_name((geocode.get("amphoe_name") or {}), "th"),
        "tumbon_th": _nested_name((geocode.get("tumbon_name") or {}), "th"),
        "basin_th": _nested_name((basin.get("basin_name") or {}), "th"),
        "rain_24h": record.get("rain_24h"),
        "rain_1h": record.get("rain_1h"),
        "agency_name_th": _nested_name((agency.get("agency_name") or {}), "th"),
        "agency_shortname_th": _nested_name((agency.get("agency_shortname") or {}), "th"),
    }


def _flatten_dam(record: dict, source_url: str, fetched_at: str, dataset: str) -> dict:
    dam = record.get("dam") if isinstance(record.get("dam"), dict) else {}
    geocode = record.get("geocode") if isinstance(record.get("geocode"), dict) else {}
    agency = record.get("agency") if isinstance(record.get("agency"), dict) else {}
    basin = record.get("basin") if isinstance(record.get("basin"), dict) else {}
    return {
        "source_url": source_url,
        "fetched_at": fetched_at,
        "dataset": dataset,
        "id": record.get("id"),
        "dam_date": record.get("dam_date") or record.get("smalldam_datetime"),
        "dam_id": dam.get("id"),
        "dam_code": dam.get("dam_oldcode") or dam.get("tele_station_oldcode"),
        "dam_name_th": _nested_name(dam.get("dam_name") or dam.get("smalldam_name"), "th"),
        "dam_name_en": _nested_name(dam.get("dam_name") or dam.get("smalldam_name"), "en"),
        "lat": dam.get("dam_lat") or dam.get("tele_station_lat"),
        "lng": dam.get("dam_long") or dam.get("tele_station_long"),
        "province_th": _geocode_province_th(record),
        "province_en": _nested_name((geocode.get("province_name") or {}), "en"),
        "amphoe_th": _nested_name((geocode.get("amphoe_name") or {}), "th"),
        "tumbon_th": _nested_name((geocode.get("tumbon_name") or {}), "th"),
        "basin_th": _nested_name((basin.get("basin_name") or {}), "th"),
        "dam_storage": record.get("dam_storage") or record.get("volume"),
        "dam_storage_percent": record.get("dam_storage_percent") or record.get("percent_storage"),
        "dam_uses_water": record.get("dam_uses_water"),
        "dam_uses_water_percent": record.get("dam_uses_water_percent"),
        "dam_inflow": record.get("dam_inflow"),
        "dam_released": record.get("dam_released"),
        "water_level": record.get("water_level") or record.get("dam_level"),
        "normal_storage": dam.get("normal_storage"),
        "min_storage": dam.get("min_storage"),
        "agency_name_th": _nested_name((agency.get("agency_name") or {}), "th"),
        "agency_shortname_th": _nested_name((agency.get("agency_shortname") or {}), "th"),
    }


class SpuSukhothaiWaterConnector:
    driver_name = "spu_sukhothai_water"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        records: list[DatasetRecord] = []
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        for dataset in context.plan["datasets"]:
            name = dataset["name"]
            url = dataset["url"]
            response, _ = context.recorder.request("GET", url, name=name)
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError(f"ThaiWater {name} response is not an object")

            if name == "water_levels":
                waterlevel_data = payload.get("waterlevel_data")
                if not isinstance(waterlevel_data, dict) or not isinstance(
                    waterlevel_data.get("data"), list
                ):
                    raise RuntimeError("ThaiWater water_levels response has unexpected schema")
                rows = waterlevel_data["data"]
                for row in rows:
                    if not isinstance(row, dict):
                        raise RuntimeError("ThaiWater water_levels returned a non-object row")
                    records.append(("water_levels.row", _flatten_water_level(row, url, fetched_at)))
            elif name == "rain_24h":
                rows = payload.get("data")
                if not isinstance(rows, list):
                    raise RuntimeError("ThaiWater rain_24h response has unexpected schema")
                for row in rows:
                    if not isinstance(row, dict):
                        raise RuntimeError("ThaiWater rain_24h returned a non-object row")
                    records.append(("rain_24h.row", _flatten_rain_24h(row, url, fetched_at)))
            elif name == "dams":
                data = payload.get("data")
                if not isinstance(data, dict):
                    raise RuntimeError("ThaiWater dams response has unexpected schema")
                for dam_dataset, rows in data.items():
                    if not isinstance(rows, list):
                        raise RuntimeError(
                            f"ThaiWater dams.{dam_dataset} is not an array"
                        )
                    for row in rows:
                        if not isinstance(row, dict):
                            raise RuntimeError(
                                f"ThaiWater dams.{dam_dataset} returned a non-object row"
                            )
                        records.append((f"dams.{dam_dataset}", _flatten_dam(row, url, fetched_at, dam_dataset)))
            else:
                raise RuntimeError(f"ThaiWater plan contains unsupported dataset: {name}")

            if (
                context.settings.max_records_per_source > 0
                and len(records) > context.settings.max_records_per_source
            ):
                raise RuntimeError(
                    "ThaiWater max_records_per_source would truncate a complete snapshot; "
                    "partial commits are forbidden"
                )

        return records
