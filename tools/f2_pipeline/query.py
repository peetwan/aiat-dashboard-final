"""Indexed entity-measure query semantics for internal releases."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class EntityQuery:
    """Query one entity-count measure without inventing aggregate semantics."""

    def __init__(self, definition: dict, tables: dict, provinces: list[dict]):
        if not isinstance(definition, dict) or not isinstance(tables, dict) or not isinstance(provinces, list):
            raise ValueError("EntityQuery requires definition, tables, and province rows")
        self.definition = definition
        self.measure_id = self._required(definition, "measure_id")
        self.unit = self._required(definition, "unit")
        self.status = self._required(definition, "status")
        supported = definition.get("supported_filters", [])
        if isinstance(supported, dict):
            supported = [key for key, enabled in supported.items() if enabled]
        if not isinstance(supported, list) or not all(isinstance(value, str) for value in supported):
            raise ValueError("supported_filters must be a list of filter names")
        self.supported_filters = set(supported)
        unsupported = definition.get("unsupported_filters", [])
        if (
            "province" in self.supported_filters
            and "region" not in unsupported
        ):
            self.supported_filters.add("region")
        self.provinces, self.regions = self._index_provinces(provinces)
        self.entities = self._index_contributions(tables.get("entity_contributions", []))
        self.province_memberships = self._index_memberships(tables.get("province_memberships", []), "province_code", self.provinces)
        self.category_memberships, self.categories = self._index_categories(tables.get("category_memberships", []))
        self.with_province = set().union(*self.province_memberships.values()) if self.province_memberships else set()

    @staticmethod
    def _required(row: dict, key: str) -> str:
        value = row.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"definition requires {key}")
        return value

    def _index_provinces(self, rows: list[dict]) -> tuple[dict[str, dict], dict[str, set[str]]]:
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError("province rows must be objects")
        provinces: dict[str, dict] = {}
        regions: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            code = self._required(row, "province_code")
            if code in provinces:
                raise ValueError(f"duplicate province code: {code}")
            self._required(row, "province_name_th")
            region_id = self._required(row, "region_id")
            self._required(row, "region")
            provinces[code] = row
            regions[region_id].add(code)
        return provinces, dict(regions)

    def _index_contributions(self, rows: Any) -> set[str]:
        if not isinstance(rows, list):
            raise ValueError("entity_contributions must be a list")
        entities: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("entity contribution must be an object")
            if row.get("measure_id") != self.measure_id:
                continue
            entity_id = self._required(row, "entity_id")
            if entity_id in entities:
                raise ValueError(f"duplicate contribution for {self.measure_id}/{entity_id}")
            entities.add(entity_id)
        return entities

    def _index_memberships(self, rows: Any, field: str, valid_values: dict[str, Any]) -> dict[str, set[str]]:
        if not isinstance(rows, list):
            raise ValueError("province_memberships must be a list")
        indexed: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("province membership must be an object")
            if row.get("measure_id") != self.measure_id:
                continue
            entity_id, value = self._required(row, "entity_id"), self._required(row, field)
            if entity_id not in self.entities:
                raise ValueError(f"membership points to absent contribution: {entity_id}")
            if value not in valid_values:
                raise ValueError(f"membership points to unknown {field}: {value}")
            indexed[value].add(entity_id)
        return dict(indexed)

    def _index_categories(self, rows: Any) -> tuple[dict[str, set[str]], dict[str, str | None]]:
        if not isinstance(rows, list):
            raise ValueError("category_memberships must be a list")
        indexed: dict[str, set[str]] = defaultdict(set)
        names: dict[str, str | None] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("category membership must be an object")
            if row.get("measure_id") != self.measure_id:
                continue
            entity_id, code = self._required(row, "entity_id"), self._required(row, "category_code")
            if entity_id not in self.entities:
                raise ValueError(f"category membership points to absent contribution: {entity_id}")
            name = row.get("category_name_th") or None
            if name is not None and not isinstance(name, str):
                raise ValueError(f"category membership has invalid label: {code}")
            if name is not None and code in names and names[code] is not None and names[code] != name:
                raise ValueError(f"category code has conflicting labels: {code}")
            if code not in names or names[code] is None:
                names[code] = name
            indexed[code].add(entity_id)
        return dict(indexed), names

    def _coverage(self, selected: set[str]) -> dict[str, Any]:
        return {"national_total": len(self.entities), "with_province": len(self.with_province), "without_province": len(self.entities - self.with_province), "selected_count": len(selected), "province_sum_is_additive": False}

    @staticmethod
    def _reason(code: str, message_th: str) -> dict[str, str]:
        return {"code": code, "message_th": message_th}

    def _scope_key(self, filters: dict[str, list[str]]) -> str:
        if "region" in filters:
            return f"region/{filters['region'][0]}"
        if "province" in filters:
            return "province/" + ",".join(filters["province"])
        return "national"

    def _unavailable(self, requested: dict[str, list[str]], scope_key: str, code: str, message_th: str) -> dict[str, Any]:
        return {"result": {"value": None, "display_value": "", "unit": self.unit, "status": self.status, "availability": "unavailable", "scope_key": scope_key, "requested_filters": requested, "applied_filters": {}, "unavailable_reason": self._reason(code, message_th)}, "entity_ids": [], "coverage": self._coverage(set())}

    def select(self, filters: dict | None = None) -> dict[str, Any]:
        if filters is None:
            filters = {}
        if not isinstance(filters, dict):
            raise ValueError("filters must be an object")
        requested: dict[str, list[str]] = {}
        for name, values in filters.items():
            if not isinstance(name, str) or not isinstance(values, list) or not values or not all(isinstance(value, str) and value for value in values):
                return self._unavailable({}, "national", "invalid_filter", "รูปแบบตัวกรองไม่ถูกต้อง")
            requested[name] = sorted(set(values))
        scope_key = self._scope_key({key: value for key, value in requested.items() if key in {"province", "region"}})
        unsupported = sorted((set(requested) - self.supported_filters) | (set(requested) - {"province", "region", "category"}))
        if unsupported:
            return self._unavailable(requested, scope_key, "unsupported_filter", "มาตรวัดนี้ไม่รองรับตัวกรองที่ขอ")
        if "province" in requested and "region" in requested:
            return self._unavailable(requested, scope_key, "unsupported_filter_combination", "ไม่สามารถเลือกจังหวัดและภูมิภาคพร้อมกันได้")
        if "region" in requested and len(requested["region"]) != 1:
            return self._unavailable(requested, scope_key, "invalid_region_filter", "เลือกได้ครั้งละหนึ่งภูมิภาค")
        unknown_provinces = set(requested.get("province", [])) - set(self.provinces)
        if unknown_provinces:
            return self._unavailable(requested, scope_key, "unknown_province", "ไม่พบจังหวัดที่เลือกในชุดอ้างอิง")
        unknown_regions = set(requested.get("region", [])) - set(self.regions)
        if unknown_regions:
            return self._unavailable(requested, scope_key, "unknown_region", "ไม่พบภูมิภาคที่เลือกในชุดอ้างอิง")
        unknown_categories = set(requested.get("category", [])) - set(self.categories)
        if unknown_categories:
            return self._unavailable(requested, scope_key, "unknown_category", "ไม่พบหมวดหมู่ที่เลือกในข้อมูลมาตรวัด")
        selected = set(self.entities)
        if "province" in requested:
            selected &= set().union(*(self.province_memberships.get(code, set()) for code in requested["province"]))
        if "region" in requested:
            selected &= set().union(*(self.province_memberships.get(code, set()) for code in self.regions[requested["region"][0]]))
        if "category" in requested:
            selected &= set().union(*(self.category_memberships.get(code, set()) for code in requested["category"]))
        entity_ids = sorted(selected)
        return {"result": {"value": len(entity_ids), "display_value": f"{len(entity_ids):,}", "unit": self.unit, "status": self.status, "availability": "available", "scope_key": scope_key, "requested_filters": requested, "applied_filters": requested, "unavailable_reason": None}, "entity_ids": entity_ids, "coverage": self._coverage(selected)}
