"""Query entity, aggregate, and unavailable internal measures."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .query import EntityQuery


AGGREGATE_MEASURES = {"K02", "K09", "K10", "C10_ALTERNATIVE", "C08_REPORTED_BUSINESSES"}
NULL_MEASURES = {"K06", "K08", "K11A", "K11B"}
_FILTER_FIELDS = {
    "province": "province_code",
    "source_level": "source_level",
    "source_dimension": "breakdown_id",
    "region": "region",
    "component": "component",
}


class MeasureQuery:
    """Select one measure without turning source aggregates into entities."""

    def __init__(self, definition: dict, tables: dict, provinces: list[dict]):
        if (
            not isinstance(definition, dict)
            or not isinstance(tables, dict)
            or not isinstance(provinces, list)
        ):
            raise ValueError(
                "MeasureQuery requires definition, tables, and province rows"
            )
        measure_id = definition.get("measure_id")
        if not isinstance(measure_id, str) or not measure_id:
            raise ValueError("definition requires measure_id")
        self.definition, self.tables, self.provinces, self.measure_id = (
            definition,
            tables,
            provinces,
            measure_id,
        )
        self.unit = self._required(definition, "unit")
        self.status = self._required(definition, "status")
        supported = definition.get("supported_filters", [])
        if isinstance(supported, dict):
            supported = [name for name, enabled in supported.items() if enabled]
        if not isinstance(supported, list) or not all(
            isinstance(name, str) for name in supported
        ):
            raise ValueError("supported_filters must be a list of filter names")
        self.supported_filters = set(supported)
        self.kind = (
            "entity"
            if measure_id not in AGGREGATE_MEASURES | NULL_MEASURES
            else ("aggregate" if measure_id in AGGREGATE_MEASURES else "methodology")
        )
        self._entity = (
            EntityQuery(definition, tables, provinces)
            if self.kind == "entity"
            else None
        )
        self.rows = self._aggregate_rows() if self.kind == "aggregate" else []

    @staticmethod
    def _required(row: dict, key: str) -> str:
        value = row.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"definition requires {key}")
        return value

    def _aggregate_rows(self) -> list[dict]:
        rows = self.tables.get("aggregate_breakdowns", [])
        if not isinstance(rows, list):
            raise ValueError("aggregate_breakdowns must be a list")
        selected = []
        seen: set[tuple[str, str, str]] = set()
        required = (
            "measure_id",
            "breakdown_id",
            "member_id",
            "amount_unit",
            "evidence_table",
            "evidence_key",
            "evidence_id",
        )
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("aggregate breakdown must be an object")
            if row.get("measure_id") != self.measure_id:
                continue
            for key in required:
                self._required(row, key)
            key = (row["measure_id"], row["breakdown_id"], row["member_id"])
            if key in seen:
                raise ValueError(f"duplicate aggregate member: {'/'.join(key)}")
            seen.add(key)
            amount, divisor = (
                self._decimal(row.get("amount")),
                self._decimal(row.get("result_divisor")),
            )
            if not amount.is_finite() or not divisor.is_finite() or divisor <= 0:
                raise ValueError(
                    "aggregate amount must be finite and result_divisor positive"
                )
            selected.append(row)
        return selected

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
            raise ValueError(
                "aggregate amount and result_divisor must be exact decimal values"
            )
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError(
                "aggregate amount and result_divisor must be exact decimal values"
            ) from None

    @staticmethod
    def _reason(code: str, message_th: str) -> dict[str, str]:
        return {"code": code, "message_th": message_th}

    def _scope_key(self, filters: dict[str, list[str]]) -> str:
        for name in (
            "region",
            "province",
            "source_level",
            "source_dimension",
            "component",
        ):
            if name in filters:
                return f"{name}/" + ",".join(filters[name])
        return "national"

    def _coverage(self) -> dict[str, Any]:
        return {
            "national_total": None,
            "with_province": None,
            "without_province": None,
            "selected_count": None,
            "province_sum_is_additive": False,
        }

    def _unavailable(
        self,
        requested: dict[str, list[str]],
        scope_key: str,
        code: str,
        message_th: str,
    ) -> dict[str, Any]:
        return {
            "query_kind": self.kind,
            "result": {
                "value": None,
                "value_exact": None,
                "display_value": "",
                "unit": self.unit,
                "status": self.status,
                "availability": "unavailable",
                "scope_key": scope_key,
                "requested_filters": requested,
                "applied_filters": {},
                "unavailable_reason": self._reason(code, message_th),
            },
            "entity_ids": [],
            "aggregate_breakdowns": [],
            "coverage": self._coverage(),
        }

    def _filters(
        self, filters: dict | None
    ) -> tuple[dict[str, list[str]], str] | dict[str, Any]:
        if filters is None:
            filters = {}
        if not isinstance(filters, dict):
            return self._unavailable(
                {}, "national", "invalid_filter", "รูปแบบตัวกรองไม่ถูกต้อง"
            )
        requested: dict[str, list[str]] = {}
        for name, values in filters.items():
            if (
                not isinstance(name, str)
                or not isinstance(values, list)
                or not values
                or not all(isinstance(value, str) and value for value in values)
            ):
                return self._unavailable(
                    {}, "national", "invalid_filter", "รูปแบบตัวกรองไม่ถูกต้อง"
                )
            requested[name] = sorted(set(values))
        scope_key = self._scope_key(requested)
        if set(requested) - self.supported_filters:
            return self._unavailable(
                requested, scope_key, "unsupported_filter", "มาตรวัดนี้ไม่รองรับตัวกรองที่ขอ"
            )
        if set(requested) not in {
            frozenset(values)
            for values in self.definition.get("permitted_filter_combinations", [[]])
        }:
            return self._unavailable(
                requested,
                scope_key,
                "unsupported_filter_combination",
                "ไม่สามารถใช้ตัวกรองร่วมกันได้",
            )
        return requested, scope_key

    @staticmethod
    def _decimal_text(value: Decimal) -> str:
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text

    def _display(self, value: Decimal) -> str:
        if self.measure_id in {"K10", "C10_ALTERNATIVE"}:
            return f"{value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):,.1f}"
        return (
            f"{value:,.0f}"
            if value == value.to_integral()
            else self._decimal_text(value)
        )

    def _aggregate(self, filters: dict | None) -> dict[str, Any]:
        parsed = self._filters(filters)
        if isinstance(parsed, dict):
            return parsed
        requested, scope_key = parsed
        applied = requested
        if self.measure_id == "C08_REPORTED_BUSINESSES":
            dimensions = sorted(
                {
                    row.get("breakdown_id")
                    for row in self.rows
                    if row.get("breakdown_id")
                }
            )
            totals = {
                dimension: sum(
                    (
                        self._decimal(row["amount"])
                        / self._decimal(row["result_divisor"])
                        for row in self.rows
                        if row.get("breakdown_id") == dimension
                    ),
                    Decimal(),
                )
                for dimension in dimensions
            }
            if not dimensions or len(set(totals.values())) != 1:
                return self._unavailable(
                    requested,
                    scope_key,
                    "inconsistent_source_dimension",
                    "ยอดรวมแต่ละมิติข้อมูลต้นทางไม่สอดคล้องกัน",
                )
            if "source_dimension" not in requested:
                applied = {"source_dimension": [dimensions[0]]}
            elif len(requested["source_dimension"]) != 1:
                return self._unavailable(
                    requested,
                    scope_key,
                    "invalid_source_dimension_filter",
                    "เลือกได้ครั้งละหนึ่งมิติข้อมูลต้นทาง",
                )
        for name, values in applied.items():
            field = _FILTER_FIELDS[name]
            known = {row.get(field) for row in self.rows}
            if not set(values) <= known:
                return self._unavailable(
                    requested,
                    scope_key,
                    f"unknown_{name}",
                    "ไม่พบค่าตัวกรองที่เลือกในข้อมูลมาตรวัด",
                )
        selected = [
            row
            for row in self.rows
            if all(
                row.get(_FILTER_FIELDS[name]) in values
                for name, values in applied.items()
            )
        ]
        if not selected:
            return self._unavailable(
                requested,
                scope_key,
                "missing_breakdown",
                "ไม่มีรายละเอียดต้นทางครบตามตัวกรองที่เลือก",
            )
        if (
            self.measure_id == "K02"
            and "province" in applied
            and "source_level" in applied
        ):
            pairs = {
                (row.get("province_code"), row.get("source_level")) for row in selected
            }
            expected = {
                (province, level)
                for province in applied["province"]
                for level in applied["source_level"]
            }
            if pairs != expected:
                return self._unavailable(
                    requested,
                    scope_key,
                    "missing_breakdown",
                    "ไม่มีรายละเอียดจังหวัดและระดับครบตามตัวกรองที่เลือก",
                )
        if "region" in applied and "component" in applied:
            pairs = {(row.get("region"), row.get("component")) for row in selected}
            expected = {
                (region, component)
                for region in applied["region"]
                for component in applied["component"]
            }
            if pairs != expected:
                return self._unavailable(
                    requested,
                    scope_key,
                    "missing_breakdown",
                    "ไม่มีรายละเอียดภูมิภาคและองค์ประกอบครบตามตัวกรองที่เลือก",
                )
        total = sum(
            (
                self._decimal(row["amount"]) / self._decimal(row["result_divisor"])
                for row in selected
            ),
            Decimal(),
        )
        return {
            "query_kind": "aggregate",
            "result": {
                "value": int(total) if total == total.to_integral() else float(total),
                "value_exact": self._decimal_text(total),
                "display_value": self._display(total),
                "unit": self.unit,
                "status": self.status,
                "availability": "available",
                "scope_key": scope_key,
                "requested_filters": requested,
                "applied_filters": applied,
                "unavailable_reason": None,
            },
            "entity_ids": [],
            "aggregate_breakdowns": selected,
            "coverage": self._coverage(),
        }

    def _methodology(self, filters: dict | None) -> dict[str, Any]:
        parsed = self._filters(filters)
        if isinstance(parsed, dict):
            return parsed
        requested, scope_key = parsed
        explanation = (
            self.definition.get("limitations")
            or self.definition.get("formula")
            or "ไม่มีข้อมูลเพียงพอ"
        )
        code = "deferred" if self.status == "deferred" else "insufficient_data"
        return self._unavailable(requested, scope_key, code, explanation)

    def select(self, filters: dict | None = None) -> dict[str, Any]:
        """Return the existing entity result or an aggregate/methodology result."""
        if self.kind == "entity":
            if (
                self.measure_id == "C08_PARTICIPATING"
                and isinstance(filters, dict)
                and "region" in filters
            ):
                requested = {"region": filters["region"]}
                values = filters["region"]
                scope_key = (
                    "region/" + ",".join(values)
                    if isinstance(values, list)
                    and all(isinstance(value, str) for value in values)
                    else "national"
                )
                result = self._entity.select({"region": []})
                result["result"] = {
                    "value": None,
                    "display_value": "",
                    "unit": self.unit,
                    "status": self.status,
                    "availability": "unavailable",
                    "scope_key": scope_key,
                    "requested_filters": requested,
                    "applied_filters": {},
                    "unavailable_reason": self._reason(
                        "unsupported_filter", "มาตรวัดนี้ไม่รองรับตัวกรองที่ขอ"
                    ),
                }
                result["query_kind"] = "entity"
                result["aggregate_breakdowns"] = []
                return result
            result = self._entity.select(filters)
            result["query_kind"] = "entity"
            result["aggregate_breakdowns"] = []
            return result
        return (
            self._aggregate(filters)
            if self.kind == "aggregate"
            else self._methodology(filters)
        )
