"""Accepted Thai administrative normalization against pinned local references."""
from __future__ import annotations

import re
from pathlib import Path

from .common import PipelineError, digest, load_json, local_path, normalize


class ThaiGeography:
    def __init__(self, directory: Path):
        directory = Path(directory)
        manifest_path = directory / "thailand_geography_manifest.json"
        manifest = load_json(manifest_path)
        for name, metadata in manifest["files"].items():
            path = local_path(directory, name)
            if not path.is_file() or digest(path) != metadata["sha256"]:
                raise PipelineError("Changed or missing geography reference")
        self.reference_version = digest(manifest_path)
        self.provinces = load_json(directory / "provinces.json")
        self.districts = load_json(directory / "districts.json")
        self.subdistricts = load_json(directory / "subdistricts.json")
        codes = [str(row["provinceCode"]).zfill(2) for row in self.provinces]
        if len(codes) != len(set(codes)):
            raise PipelineError("Duplicate province reference code")

    def resolve(self, province, district):
        p = re.sub(r"^(?:จังหวัด|จ\.)\s*", "", normalize(province))
        d = re.sub(r"^(?:อำเภอ|อ\.|เขต)\s*", "", normalize(district))
        p = {"กรุงเทพฯ": "กรุงเทพมหานคร", "กรุงเทพ": "กรุงเทพมหานคร"}.get(p, p)
        d = {"สุไหง-โกลก": "สุไหงโก-ลก"}.get(d, d)
        provinces = [v for v in self.provinces if v["provinceNameTh"] == p]
        pc = str(provinces[0]["provinceCode"]).zfill(2) if len(provinces) == 1 else ""
        if d == "เมือง" and pc:
            d = "เมือง" + p
        matches = [v for v in self.districts if v["districtNameTh"] == d]
        local = [v for v in matches if str(v["provinceCode"]).zfill(2) == pc]
        status = "unresolved_district" if d else "province_only"
        reason = ""
        match = local[0] if len(local) == 1 else None
        if match:
            status = "hierarchy_match"
        elif len(matches) == 1 and (not pc or str(matches[0]["provinceCode"]).zfill(2) != pc):
            # Preserve the raw claim; only a unique lower-level reference corrects it.
            match = matches[0]
            pc = str(match["provinceCode"]).zfill(2)
            p = next(v["provinceNameTh"] for v in self.provinces if str(v["provinceCode"]).zfill(2) == pc)
            status = "province_corrected_from_unique_district"
            reason = "Unique district in the pinned national reference; raw province retained"
        subcode, subname = "", ""
        if not match and d:
            subs = [v for v in self.subdistricts if v["subdistrictNameTh"] == d and str(v["provinceCode"]).zfill(2) == pc]
            if len(subs) == 1:
                sub = subs[0]
                match = next(v for v in self.districts if v["districtCode"] == sub["districtCode"])
                subname, subcode = d, str(sub["subdistrictCode"])
                status = "subdistrict_in_district_field"
                reason = "Written district uniquely matches a subdistrict within the stated province"
        if not pc:
            status = "unresolved_province"
        return {
            "province_raw": province, "district_raw": district,
            "province_normalized": p, "province_code": pc,
            "district_normalized": match["districtNameTh"] if match else d,
            "district_code": str(match["districtCode"]) if match else "",
            "subdistrict_normalized": subname, "subdistrict_code": subcode,
            "status": status, "correction_reason": reason,
        }

    def check_dashboard(self, provinces: list[dict]) -> None:
        dashboard = {row["province_code"]: row["province_name_th"] for row in provinces}
        reference = {str(row["provinceCode"]).zfill(2): row["provinceNameTh"] for row in self.provinces}
        if len(dashboard) != len(provinces) or dashboard != reference:
            raise PipelineError("Dashboard province codes/names differ from normalization reference")
