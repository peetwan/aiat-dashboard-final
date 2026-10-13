"""Measure results for every scope and filter the dashboard can ask for.

A scope is national, one province, or one source region (the regions the Learning dashboard reports, which
are not mapped to provinces). Count measures count entities in measure_members; source totals add up their
parts in measure_values. A filter a measure does not support gives an "unavailable" result with a reason,
never a borrowed value; where the selected place has no value, the national (and source region) values are
offered as context instead.
"""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from itertools import product

FILTER_ORDER = ("province", "category", "source_level", "source_region", "component", "source_dimension")
PLACE = ("province", "source_region")
UNSUPPORTED = {"code": "unsupported_filter", "message_th": "มาตรวัดนี้ไม่รองรับตัวกรองที่ขอ"}
UNKNOWN_PROVINCE = {"code": "unknown_province", "message_th": "ไม่พบค่าตัวกรองที่เลือกในข้อมูลมาตรวัด"}
MISSING_PART = {"code": "missing_breakdown", "message_th": "ไม่มีรายละเอียดต้นทางครบตามตัวกรองที่เลือก"}
DEFAULT_DIMENSION = "categories"  # C08_REPORTED_BUSINESSES without a filter shows this breakdown


def scope_key(requested: dict) -> str:
    for key in PLACE:
        if key in requested:
            return f"{key}/{requested[key][0]}"
    return "national"


class Results:
    def __init__(self, con, config: dict):
        self.measures = config["measures"]
        self.labels = config["labels"]
        self.regions = dict(sorted(config["source_regions"].items()))  # label -> id, in Thai order
        self.region_label = {v: k for k, v in self.regions.items()}
        self.members = defaultdict(lambda: defaultdict(set))  # measure -> province (None) -> entity ids
        self.everyone = defaultdict(set)
        for measure, entity_id, province in con.execute(
                "SELECT measure_id, entity_id, province_code FROM measure_members").fetchall():
            self.members[measure][province].add(entity_id)
            self.everyone[measure].add(entity_id)
        self.parts = defaultdict(list)
        cursor = con.execute("SELECT * FROM measure_values ORDER BY measure_id, ord")  # parts in the source's order
        names = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            row = dict(zip(names, row))
            self.parts[row["measure_id"]].append(row)
        # K12 category filter: the Cultural Map primary and additional category codes of a subject
        self.codes = defaultdict(set)
        for entity_id, category, categories in con.execute(
                """SELECT m.entity_id, c.category, c.categories FROM entity_members m
                   JOIN cultural_records c USING (source, record_id)
                   WHERE m.entity = 'cultural_record' AND c.source = 'cultural_map'""").fetchall():
            self.codes[entity_id] |= {category, *(c for c in _json_list(categories))} - {None}

    # values ----------------------------------------------------------------

    def is_total(self, measure: str) -> bool:
        return measure in self.parts

    def entities(self, measure: str, requested: dict) -> set[str]:
        province = requested.get("province", [None])[0]
        ids = self.everyone[measure] if province is None else self.members[measure].get(province, set())
        if "category" in requested:
            ids = {e for e in ids if requested["category"][0] in self.codes[e]}
        return ids

    def _parts(self, measure: str, requested: dict) -> tuple[list[dict], dict | None]:
        rows = self.parts[measure]
        if measure == "C08_REPORTED_BUSINESSES":
            dimension = requested.get("source_dimension", [DEFAULT_DIMENSION])[0]
            rows = [r for r in rows if r["breakdown"] == dimension]
        if "province" in requested:
            rows = [r for r in rows if r["province_code"] == requested["province"][0]]
            if not rows:
                return [], UNKNOWN_PROVINCE
        tests = {"source_level": "source_level", "component": "component"}
        for key, column in tests.items():
            if key in requested:
                rows = [r for r in rows if r[column] == requested[key][0]]
        if "source_region" in requested:
            rows = [r for r in rows if r["region"] == self.region_label.get(requested["source_region"][0])]
        return rows, None if rows else MISSING_PART

    def result(self, measure: str, requested: dict) -> dict:
        meta = self.measures[measure]
        base = {"requested_filters": requested, "scope_key": scope_key(requested), "status": meta["status"],
                "unit": meta["unit"]}

        def unavailable(reason: dict, applied: dict | None = None) -> dict:
            return {**base, "applied_filters": applied or {}, "availability": "unavailable", "display_value": "",
                    "unavailable_reason": reason, "value": None, "value_exact": None}

        if [k for k in FILTER_ORDER if k in requested] not in meta["permitted_combinations"]:
            return unavailable(UNSUPPORTED)
        if meta.get("unavailable_reason"):  # not calculated in this release (deferred / insufficient data)
            return unavailable(meta["unavailable_reason"], requested)
        if not self.is_total(measure):
            count = len(self.entities(measure, requested))
            return {**base, "applied_filters": requested, "availability": "available", "display_value": f"{count:,}",
                    "unavailable_reason": None, "value": count, "value_exact": None}
        rows, problem = self._parts(measure, requested)
        if problem:
            return unavailable(problem)
        divisor = Decimal(int(rows[0]["divisor"]))
        total = sum((Decimal(repr(r["value"])) for r in rows), Decimal(0)) / divisor
        exact = format(total.normalize(), "f")
        display = f"{int(total):,}" if divisor == 1 else f"{total.quantize(Decimal('0.1'), ROUND_HALF_UP):,}"
        applied = requested
        if measure == "C08_REPORTED_BUSINESSES" and "source_dimension" not in requested:
            applied = {**requested, "source_dimension": [DEFAULT_DIMENSION]}
        return {**base, "applied_filters": applied, "availability": "available", "display_value": display,
                "unavailable_reason": None, "value": float(total) if divisor != 1 else int(total), "value_exact": exact}

    def breakdowns(self, measure: str, requested: dict) -> list[dict]:
        """The parts behind a source total, as the source names them (C08 shows them as a table)."""
        rows, _ = self._parts(measure, requested)
        return [{"label": r["member"], "amount": format(Decimal(repr(r["value"])).normalize(), "f"),
                 "amount_unit": self.measures[measure]["unit"], "breakdown_id": r["breakdown"]} for r in rows]

    # filters ---------------------------------------------------------------

    def choice_ids(self, measure: str, key: str) -> list[str]:
        if key == "category":
            return sorted(set().union(*(self.codes[e] for e in self.everyone[measure])))
        if key == "source_region":
            present = {r["region"] for r in self.parts[measure]}
            return [i for label, i in self.regions.items() if label in present]
        if key == "component":
            return sorted({r["component"] for r in self.parts[measure] if r["component"]})
        return list(self.labels[key])  # source_level, source_dimension

    def label(self, key: str, value: str) -> str:
        if key == "source_region":
            return self.region_label[value]
        return self.labels.get(key, {}).get(value, value)

    def prepared(self, measure: str, place: dict, detail: bool) -> dict:
        """What the dashboard can select for one measure in one scope: the default result, every permitted
        filter selection, and the choices for each filter."""
        meta = self.measures[measure]
        default = {"result": self.result(measure, place)}
        selections = {}
        for combination in meta["permitted_combinations"]:
            if sorted(k for k in combination if k in PLACE) != sorted(place):
                continue
            keys = [k for k in combination if k not in PLACE]
            for values in product(*(self.choice_ids(measure, k) for k in keys)) if keys else ():
                requested = {**place, **{k: [v] for k, v in zip(keys, values)}}
                requested = {k: requested[k] for k in FILTER_ORDER if k in requested}
                selection = {"result": self.result(measure, requested)}
                if detail:
                    selection["item_ids"] = sorted(self.entities(measure, requested))
                selections["/".join(f"{k}/{v}" for k, v in zip(keys, values))] = selection
        if measure == "C08_REPORTED_BUSINESSES":
            for selection in [default, *selections.values()]:
                result = selection["result"]
                selection["breakdowns"] = self.breakdowns(measure, result["applied_filters"]) \
                    if result["availability"] == "available" else []
        choices = {}
        for key in meta["supported_filters"]:
            if key == "province" or default["result"]["unavailable_reason"] == UNSUPPORTED:
                continue
            options = []
            for value in self.choice_ids(measure, key):
                requested = {**place, key: [value]}
                requested = {k: requested[k] for k in FILTER_ORDER if k in requested}
                result = self.result(measure, requested)
                option = {"id": value, "label_th": self.label(key, value), "availability": result["availability"],
                          "unavailable_reason": result["unavailable_reason"]}
                if key == "category":
                    option["count"] = result["value"]
                options.append(option)
            choices[key] = options
        return {"choices": choices, "default": default, "selections": selections}

    def coverage(self, measure: str, place: dict) -> dict:
        if self.is_total(measure) or self.measures[measure].get("unavailable_reason"):
            return {"national_total": None, "province_sum_is_additive": False, "selected_count": None,
                    "with_province": None, "without_province": None}
        total = len(self.everyone[measure])
        placed = len(set().union(*(ids for p, ids in self.members[measure].items() if p is not None)))
        selected = len(self.entities(measure, place)) if "province" in place else total
        return {"national_total": total, "province_sum_is_additive": False, "selected_count": selected,
                "with_province": placed, "without_province": total - placed}

    def context(self, measures: list[str], place: dict) -> list[dict]:
        """For a place where a measure has no value: the national value, and for a province the source
        region values, each marked as context and never as the place's own value."""
        out = []
        if not place:
            return out
        for measure in measures:
            if self.result(measure, place)["availability"] == "available":
                continue
            national = self.result(measure, {})
            if national["availability"] != "available":
                continue
            out.append({"context_id": f"{measure.lower()}-national", "label_th": "บริบทระดับประเทศ (ไม่ใช่ค่าทดแทนของพื้นที่ที่เลือก)",
                        "measure_id": measure, "relationship": "national_context_not_fallback", "result": national})
            if "province" in place and "source_region" in self.measures[measure]["supported_filters"]:
                for label, region in self.regions.items():
                    if region in self.choice_ids(measure, "source_region"):
                        out.append({"context_id": f"{measure.lower()}-{region}", "label_th": f"บริบทภูมิภาคตามแหล่งข้อมูล: {label}",
                                    "measure_id": measure,
                                    "relationship": "independent_source_region_not_mapped_to_selected_dashboard_geography",
                                    "result": self.result(measure, {"source_region": [region]})})
        return out


def _json_list(value) -> list:
    if value is None:
        return []
    return json.loads(value) if isinstance(value, str) else list(value)
