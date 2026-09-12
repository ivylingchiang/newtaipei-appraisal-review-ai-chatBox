# -*- coding: utf-8 -*-
"""資料集載入層"""
import os, json, glob, functools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(ROOT, "datasets")


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


class Dataset:
    """以 (region_code) 為單位載入基準表、區段、案件與共用規則"""

    def __init__(self, base=DS):
        self.base = base
        self.index = _load(os.path.join(base, "index.json"))
        self.common = {
            n: _load(os.path.join(base, "common", f"{n}.json"))
            for n in ("forms", "formulas", "review_rules", "case_rules", "legal_references")
        }

    @functools.lru_cache(maxsize=None)
    def criteria(self, region, factor_type):
        d = _load(os.path.join(self.base, "regions", region, "criteria", f"{factor_type}.json"))
        return {i["item_code"]: i for i in d["items"]}

    @functools.lru_cache(maxsize=None)
    def criteria_meta(self, region, factor_type):
        return _load(os.path.join(self.base, "regions", region, "criteria", f"{factor_type}.json"))

    def segments(self, region):
        out = {}
        for p in sorted(glob.glob(os.path.join(self.base, "regions", region, "segments", "P*.json"))):
            s = _load(p)
            out[s["segment_no"]] = s
        return out

    def cases(self, region):
        out = {}
        for p in sorted(glob.glob(os.path.join(self.base, "regions", region, "cases", "*.json"))):
            c = _load(p)
            out[c["case_no"]] = c
        return out

    def regions(self):
        return [r["region_code"] for r in self.index["regions"]]

    def region_info(self, region):
        return next(r for r in self.index["regions"] if r["region_code"] == region)
