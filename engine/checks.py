# -*- coding: utf-8 -*-
"""審查檢查：對應作業手冊「審查重點」與 dev 文件之 R1~R14 跨表參照矩陣"""
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
import math

from engine.grading import grade, adjust, adjust_regional, split_conditions, Ungradable, item_unit

TOL = 1e-6          # 百分比比對容差
PRICE_TOL = 1       # 價格容差（元）：表上顯示值經進位，全精度連乘會差 ±1


@dataclass
class Finding:
    rule: str
    severity: str                 # error | warning | info | blocked
    target: str                   # 表別
    item: Optional[str] = None
    message: str = ""
    expected: Any = None
    actual: Any = None
    evidence: dict = field(default_factory=dict)

    def to_dict(self): return asdict(self)


def _fmt(x):
    return "—" if x is None else (f"{x:.2f}" if isinstance(x, float) else str(x))


# ---------------------------------------------------------------- R2
def check_R2(ds, region, case):
    """表5 修正百分比是否等於依基準明細表查得之值"""
    out = []
    crit = ds.criteria(region, "regional")
    for row in (case.get("table5") or {}).get("rows", []):
        code = row["item_code"]
        it = crit.get(code)
        lv = row.get("levels") or []
        adjs = row.get("adjustments") or []
        if not it or len(lv) < 2 or not adjs:
            continue
        base = lv[0]["rank"]
        for i, comp in enumerate(lv[1:]):
            if i >= len(adjs): break
            exp = adjust_regional(it, base, comp["rank"])
            got = adjs[i]
            if abs(exp - got) > TOL:
                out.append(Finding(
                    "R2", "error", "表5", it["item_name"],
                    f"修正百分比與基準明細表不符（比準地{lv[0]['label']}({base}) vs "
                    f"比較標的{i+1}{comp['label']}({comp['rank']})）",
                    exp, got,
                    {"segment_index": i + 1, "step": it["step"], "max": it["max_adjustment"]}))
    return out


# ---------------------------------------------------------------- R14
def check_R14(ds, region, case):
    """表5 各項百分比小計加總 = 影響地價區域因素總修正數"""
    out = []
    t5 = case.get("table5") or {}
    subs = (t5.get("subtotals") or {}).get("order") or []
    total = t5.get("total")
    if not subs or not total:
        return [Finding("R14", "blocked", "表5", None,
                        "小計或總修正數未填，無法核算加總", None, None)]
    n = max((len(s) for s in subs), default=0)
    for i in range(n):
        s = sum(x[i] for x in subs if len(x) > i)
        t = total[i] if len(total) > i else None
        if t is None: continue
        if abs(s - t) > TOL:
            out.append(Finding("R14", "error", "表5", None,
                               f"比較標的{i+1}：各項小計加總與總修正數不符", s, t,
                               {"subtotals": [x[i] for x in subs if len(x) > i]}))
    return out


# ---------------------------------------------------------------- R4
def check_R4(ds, region, case):
    """表5 總修正數 → 表4 區域因素調整百分率 必須相符"""
    t5 = case.get("table5") or {}
    t4 = case.get("table4") or {}
    total = t5.get("total")
    reg = ((t4.get("summary") or {}).get("regional") or {}).get("percents")
    if not total or reg is None:
        return [Finding("R4", "blocked", "表4/表5", None,
                        "表5 總修正數或表4 區域因素調整百分率未填，無法比對", total, reg)]
    out = []
    for i, t in enumerate(total):
        g = reg[i] if i < len(reg) else None
        if g is None:
            out.append(Finding("R4", "error", "表4", None,
                               f"比較標的{i+1}：表4 未填區域因素調整百分率", t, None))
        elif abs(t - g) > TOL:
            out.append(Finding("R4", "error", "表4", None,
                               f"比較標的{i+1}：與表5 總修正數不符", t, g))
    return out


# ---------------------------------------------------------------- R6
def check_R6(ds, region, case):
    """表4 個別因素差異率是否等於依基準明細表查得之值"""
    out = []
    crit = ds.criteria(region, "individual")
    by_field = {i.get("field_no"): i for i in crit.values() if i.get("field_no")}
    t4 = case.get("table4") or {}
    n_comp = len(((t4.get("summary") or {}).get("unit_price") or {}).get("values") or []) or 1
    for code, f in (t4.get("factors") or {}).items():
        it = by_field.get(f["field_no"])
        if not it: continue
        diffs = f.get("diffs") or []
        if not diffs: continue
        if it.get("rule_type") != "matrix":
            out.append(Finding("R6", "info", "表4", it["item_name"],
                               f"本細項無查表矩陣（{it.get('basis')}），差異率 {diffs} 須另依備註理由審查",
                               None, diffs))
            continue
        kind, vals = split_conditions(it, f.get("conditions") or [], n_comp)
        if len(vals) < 2:
            out.append(Finding("R6", "blocked", "表4", it["item_name"],
                               "條件欄位不足，無法重算差異率", None, diffs,
                               {"conditions": f.get("conditions")}))
            continue
        try:
            if kind == "value":
                rb, lb = grade(it, value=vals[0])
            else:
                rb, lb = grade(it, category=vals[0])
        except Ungradable as e:
            out.append(Finding("R6", "blocked", "表4", it["item_name"], str(e), None, diffs))
            continue
        for i, d in enumerate(diffs):
            j = 1 + i
            if j >= len(vals): break
            try:
                rc, lc = (grade(it, value=vals[j]) if kind == "value"
                          else grade(it, category=vals[j]))
            except Ungradable as e:
                out.append(Finding("R6", "blocked", "表4", it["item_name"], str(e), None, d))
                continue
            exp = adjust(it, rb, rc)
            if abs(exp - d) > TOL:
                out.append(Finding("R6", "error", "表4", it["item_name"],
                                   f"差異率與基準明細表不符（比準地 {vals[0]}→{lb}({rb})，"
                                   f"比較標的{i+1} {vals[j]}→{lc}({rc})）",
                                   exp, d, {"step": it["step"]}))
    return out


# ---------------------------------------------------------------- R7
def check_R7(ds, region, case):
    """權重邏輯：調整百分率絕對值加總愈大 → 權重應愈小"""
    t4 = case.get("table4") or {}
    s = t4.get("summary") or {}
    abs_sums = (s.get("abs_sum") or {}).get("percents") or []
    weights = (s.get("weight") or {}).get("percents") or []
    if not abs_sums or not weights:
        return [Finding("R7", "blocked", "表4", None,
                        "絕對值加總或權重未填，無法檢核", abs_sums, weights)]
    out = []
    tot = sum(weights)
    if abs(tot - 100.0) > 0.5:
        out.append(Finding("R7", "error", "表4", None, "比較標的權重合計不等於 100%", 100.0, tot))
    pairs = sorted(zip(abs_sums, weights), key=lambda x: x[0])
    for (a1, w1), (a2, w2) in zip(pairs, pairs[1:]):
        if a2 > a1 and w2 > w1:
            out.append(Finding("R7", "error", "表4", None,
                               f"權重邏輯反向：絕對值加總 {a2:.2f}% > {a1:.2f}% 但權重 "
                               f"{w2:.0f}% > {w1:.0f}%（加總愈大權重應愈小）", None, None))
    if len(weights) == 1 and abs(weights[0] - 100.0) > 0.5:
        out.append(Finding("R7", "error", "表4", None, "僅1件比較標的時權重應為100%", 100.0, weights[0]))
    return out


# ---------------------------------------------------------------- R13 / 價格鏈
def round_up_tier(x):
    """查估辦法第21條：地價尾數分級無條件進位"""
    if x is None: return None
    if x > 100000: q = 1000
    elif x > 1000: q = 100
    elif x > 100:  q = 10
    else:          q = 1
    return math.ceil(x / q) * q


def check_price_chain(ds, region, case):
    """表4 價格鏈重算：調整後單價、試算價格、絕對值加總"""
    out = []
    t4 = case.get("table4") or {}
    s = t4.get("summary") or {}
    unit = (s.get("unit_price") or {}).get("values") or []
    dadj = (s.get("date_adj") or {}).get("percents") or []
    adjp = (s.get("adjusted_price") or {}).get("values") or []
    reg = (s.get("regional") or {}).get("percents") or []
    tot = (s.get("total") or {}).get("percents") or []
    trial = (s.get("trial") or {}).get("values") or []
    abs_s = (s.get("abs_sum") or {}).get("percents") or []
    if not unit:
        return [Finding("PRICE", "blocked", "表4", None, "土地正常單價未填，無法重算價格鏈")]
    for i, u in enumerate(unit):
        d = dadj[i] if i < len(dadj) else None
        if d is None: continue
        exact = u * (1 + d / 100)
        if i < len(adjp) and abs(exact - adjp[i]) > PRICE_TOL:
            out.append(Finding("PRICE", "error", "表4", "調整至估價基準日單價",
                               f"比較標的{i+1}：{u:,.0f} × (1+{d:.2f}%) 不等於表上值",
                               round(exact), adjp[i]))
        r = reg[i] if i < len(reg) else 0.0
        t = tot[i] if i < len(tot) else None
        if t is None: continue
        exp_trial = round(exact * (1 + (r + t) / 100))
        if i < len(trial) and abs(exp_trial - trial[i]) > PRICE_TOL:
            out.append(Finding("PRICE", "error", "表4", "試算價格",
                               f"比較標的{i+1}：{exact:,.2f} × (1+{r:.2f}%+{t:.2f}%) 不等於表上值",
                               exp_trial, trial[i]))
    # 絕對值加總
    facs = t4.get("factors") or {}
    for i in range(len(unit)):
        parts = abs(dadj[i]) if i < len(dadj) else 0.0
        parts += abs(reg[i]) if i < len(reg) else 0.0
        parts += sum(abs(f["diffs"][i]) for f in facs.values()
                     if len(f.get("diffs") or []) > i)
        if i < len(abs_s) and abs(parts - abs_s[i]) > 0.01:
            out.append(Finding("R7", "error", "表4", "調整百分率絕對值加總",
                               f"比較標的{i+1}：逐項絕對值加總與表上值不符", round(parts, 2), abs_s[i]))
    return out


# ---------------------------------------------------------------- R1
def check_R1(ds, region, case, segments):
    """表3 所載優劣等級 ↔ 表5 優劣等級 一致性"""
    out = []
    t5 = case.get("table5") or {}
    segs = t5.get("segment_nos") or []
    if not segs:
        return [Finding("R1", "blocked", "表3/表5", None, "表5 未載地價區段號")]
    # 建立 表3 每個區段的 (item_code → rank)：來自設施對應與欄位等級碼
    seg_levels = {}
    for sn in segs:
        s = segments.get(sn)
        if not s: continue
        lv = {}
        for code, o in (s.get("observations") or {}).items():
            if o.get("level_rank"): lv[code] = o["level_rank"]
        for f in (s.get("facilities") or []):
            c = f.get("criteria_item_code")
            if c and f.get("level_rank"): lv.setdefault(c, f["level_rank"])
        seg_levels[sn] = lv
    for row in t5.get("rows", []):
        code, lvs = row["item_code"], (row.get("levels") or [])
        for i, l in enumerate(lvs):
            if i >= len(segs): break
            t3 = seg_levels.get(segs[i], {}).get(code)
            if t3 is None: continue
            if t3 != l["rank"]:
                out.append(Finding("R1", "error", "表5", row["item_label"],
                                   f"區段 {segs[i]}：表5 等級與表3 所載不一致", t3, l["rank"]))
    if not any(seg_levels.values()):
        out.append(Finding("R1", "blocked", "表3", None,
                           "表3 未載優劣等級碼，無法與表5 比對"))
    return out


# ---------------------------------------------------------------- R12
def check_R12(ds, region, case, segments):
    """各用地別應評價之細項是否皆已具備可判定之資料"""
    out = []
    crit = ds.criteria(region, "regional")
    t5 = case.get("table5") or {}
    segs = t5.get("segment_nos") or []
    for sn in segs:
        s = segments.get(sn)
        if not s: continue
        # 觀測欄位代碼與基準表細項代碼不同名（如 main_road → main_road_width），需轉換
        from engine.compute import OBS_TO_ITEM
        have = set(OBS_TO_ITEM.get(k, k) for k, o in (s.get("observations") or {}).items()
                   if o.get("raw"))
        have |= set(f["criteria_item_code"] for f in (s.get("facilities") or [])
                    if f.get("criteria_item_code")
                    and (f.get("distance_m") is not None or f.get("in_segment")
                         or f.get("is_none")))
        missing = [it["item_name"] for c, it in crit.items()
                   if c not in have and it.get("rule_type") == "matrix" and c != "other"]
        if missing:
            out.append(Finding("R12", "warning", "表3", None,
                               f"區段 {sn}：{len(missing)}/{len(crit)} 個應評價細項缺乏可判定資料",
                               0, len(missing), {"missing_items": missing}))
    return out


# ---------------------------------------------------------------- CR1 / CR2
def check_case_rules(ds, region, case, segments):
    out = []
    for sn, s in segments.items():
        vb = s.get("valuation_basis")
        if vb:
            out.append(Finding("CR1", "info", "表3", "使用分區",
                               f"區段 {sn}：{vb['note']}",
                               vb.get("zoning_for_valuation"), vb.get("land_use_current_in_form")))
        for ck in (s.get("rule_checks") or []):
            if ck.get("consistent") is False:
                out.append(Finding(ck["rule"], "warning", "表3", "容積率",
                                   f"區段 {sn}：{ck['message']}",
                                   ck.get("expected_far_percent"), ck.get("far_percent")))
    return out
