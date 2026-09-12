# -*- coding: utf-8 -*-
"""將級距文字（如「360%以上未滿460%」）解析為可機器比對的結構"""
import re

UNIT_MAP = {'㎡':'m2','m2':'m2','m':'m','M':'m','%':'percent','％':'percent','度':'degree'}
NUM = r'(\d+(?:,\d{3})*(?:\.\d+)?)'

def _n(s): return float(s.replace(',', ''))

def _unit(s):
    for k in ('㎡','m2','m','M','%','％','度'):
        if k in s: return UNIT_MAP[k]
    return None

def parse_threshold(text):
    """回傳 dict: {kind, ranges[], in_segment, or_none, unit, categories[], raw}"""
    raw = (text or '').strip()
    if not raw:
        return {"kind": "unknown", "raw": raw}

    # m2/M2 一律正規化為 ㎡，避免 "600m2以上" 中的 2 被當成數值
    t = raw.replace('％', '%')
    t = re.sub(r'[mM]2(?![0-9])', '㎡', t)
    in_segment = '區段內有' in t
    or_none = bool(re.search(r'或無\s*$', t)) or '或無' in t

    # 移除語意標記，保留數值表達式
    work = t
    work = re.sub(r'區段內有[^，,或]*?(?=或|$)', '', work)
    work = re.sub(r'或無\s*$', '', work)
    work = re.sub(r'^或', '', work)
    work = work.replace('距離', '').strip()

    unit = _unit(work) or _unit(t)
    ranges = []
    # 以「或」切分多段（如「未滿7m 或 60m以上」）
    for part in re.split(r'\s*或\s*', work):
        p = part.strip()
        if not p: continue
        m = re.search(NUM + r'\s*\D{0,3}?以上未滿\s*' + NUM, p)
        if m:
            ranges.append({"min": _n(m.group(1)), "max": _n(m.group(2)),
                           "min_inclusive": True, "max_inclusive": False}); continue
        m = re.search(r'未滿\s*' + NUM, p)
        if m:
            ranges.append({"max": _n(m.group(1)), "max_inclusive": False}); continue
        m = re.search(NUM + r'\s*\D{0,3}?以上', p)
        if m:
            ranges.append({"min": _n(m.group(1)), "min_inclusive": True}); continue
        m = re.search(NUM + r'\s*\D{0,3}?以下', p)
        if m:
            ranges.append({"max": _n(m.group(1)), "max_inclusive": True}); continue

    if ranges:
        return {"kind": "numeric", "unit": unit, "ranges": ranges,
                "in_segment": in_segment, "or_none": or_none, "raw": raw}
    if in_segment:
        return {"kind": "numeric", "unit": unit, "ranges": [],
                "in_segment": True, "or_none": or_none, "raw": raw}
    cats = [c.strip() for c in re.split(r'[、,，]', raw) if c.strip()]
    return {"kind": "categorical", "categories": cats, "raw": raw}


def match_level(value, levels, in_segment=False, is_none=False):
    """給定數值(或 in_segment/無)，回傳符合之 level rank；找不到回 None"""
    if is_none:
        r = _match_none(levels)
        if r: return r
    for lv in levels:
        th = lv.get("threshold") or {}
        if th.get("kind") != "numeric": continue
        if is_none and th.get("or_none"): return lv["rank"]
        if in_segment and th.get("in_segment"): return lv["rank"]
        if value is None: continue
        for r in th.get("ranges", []):
            lo, hi = r.get("min"), r.get("max")
            ok = True
            if lo is not None:
                ok &= (value >= lo) if r.get("min_inclusive", True) else (value > lo)
            if hi is not None:
                ok &= (value <= hi) if r.get("max_inclusive", False) else (value < hi)
            if ok and (lo is not None or hi is not None): return lv["rank"]
    return None


def _match_none(levels):
    """表3 明載「無此設施」時之判級。

    多數基準表以「2000m以上或無」明列，直接命中；少數（如金山商業用地之
    環境污染、廢棄物處理設施）僅寫距離級距而未寫「或無」。後者依語意處理：
    無此設施＝距離無限遠，故落在上界開放（「X 以上」）的那一級。
    """
    for lv in levels:
        th = lv.get("threshold") or {}
        if th.get("kind") == "numeric" and th.get("or_none"):
            return lv["rank"]
    for lv in levels:
        th = lv.get("threshold") or {}
        if th.get("kind") != "numeric":
            continue
        for r in th.get("ranges", []):
            if r.get("min") is not None and r.get("max") is None:
                return lv["rank"]
    return None
