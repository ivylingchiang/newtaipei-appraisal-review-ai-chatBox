# -*- coding: utf-8 -*-
"""輔助填表：由表3 觀測值推導表5 之優劣等級與修正百分比"""
import re
from grading import grade, adjust, adjust_regional, Ungradable

# 表3 觀測欄位 → 區域因素細項代碼
OBS_TO_ITEM = {
    "urban_plan": "urban_plan", "zoning": "zoning", "bcr": "bcr", "far": "far",
    "build_ban": "build_ban", "build_restrict": "build_restrict",
    "main_road": "main_road_width", "avg_road_width": "avg_road_width",
    "road_dev": "road_dev", "sunlight": "sunlight", "view": "view",
    "slope": "slope", "drainage": "drainage", "terrain": "terrain",
}


def _observed(seg, obs_code, item):
    """由區段觀測值取出可判級的輸入"""
    o = (seg.get("observations") or {}).get(obs_code) or {}
    raw, val = o.get("raw"), o.get("value")
    if obs_code == "zoning":
        vb = seg.get("valuation_basis") or {}
        raw = vb.get("zoning_for_valuation") or raw      # CR1：採變更前分區
    if val is not None:
        return {"value": val}
    if raw:
        return {"category": raw}
    return None


def _grade_land_improve(it, seg):
    """土地改良：基準表以『改良項數』分級（四項以上=優 … 無=劣），
    表3 以 ■ 勾選項記錄，故以勾選數量判級。"""
    n = len(seg.get("improvements") or [])
    # 級距文字為「四項以上／三項／二項/一項/無」，轉為項數門檻
    ZH = {"四": 4, "三": 3, "二": 2, "一": 1}
    best = None
    for lv in it["levels"]:
        c = (lv.get("criterion") or "").strip()
        if c == "無":
            if n == 0: return lv["rank"], lv["label"]
            continue
        m = re.match(r'([一二三四五六七八九])項(以上)?', c)
        if not m: continue
        k = ZH.get(m.group(1))
        if k is None: continue
        if m.group(2):                      # 「X項以上」
            if n >= k: return lv["rank"], lv["label"]
        elif n == k:
            return lv["rank"], lv["label"]
        best = best or (lv["rank"], lv["label"])
    return best or (None, None)


def derive_segment_levels(ds, region, seg):
    """回傳 {item_code: {rank, label, source, basis}}，含無法判定之原因"""
    crit = ds.criteria(region, "regional")
    out, gaps = {}, {}
    for obs_code, item_code in OBS_TO_ITEM.items():
        it = crit.get(item_code)
        if not it: continue
        arg = _observed(seg, obs_code, it)
        if not arg:
            gaps[item_code] = f"表3「{it['item_name']}」欄位空白"
            continue
        try:
            r, l = grade(it, **arg)
            out[item_code] = {"rank": r, "label": l, "input": arg,
                              "criterion": it["levels"][r - 1]["criterion"]}
        except Ungradable as e:
            gaps[item_code] = str(e)
    # 土地改良：依表3 勾選之改良項數判級
    it = crit.get("land_improve")
    if it and "land_improve" not in out:
        r, l = _grade_land_improve(it, seg)
        if r:
            out["land_improve"] = {"rank": r, "label": l,
                                   "input": {"improvement_count": len(seg.get("improvements") or []),
                                             "items": seg.get("improvements") or []},
                                   "criterion": it["levels"][r - 1]["criterion"]}
        else:
            gaps["land_improve"] = "表3 土地改良欄未勾選任何項目"

    # 設施類：以最近距離判級
    from collections import defaultdict
    byitem = defaultdict(list)
    for f in (seg.get("facilities") or []):
        if f.get("criteria_item_code"): byitem[f["criteria_item_code"]].append(f)
    for code, fs in byitem.items():
        it = crit.get(code)
        if not it or code in out: continue
        inseg = any(f.get("in_segment") for f in fs)
        ds_ = [f["distance_m"] for f in fs if f.get("distance_m") is not None]
        # 有實測距離時取最近者；否則若表3 明載「無」，則以「或無」級距判定
        is_none = (not ds_) and (not inseg) and any(f.get("is_none") for f in fs)
        if not ds_ and not inseg and not is_none:
            gaps[code] = "表3 設施欄未勾選且未填名稱（未勘查）"
            continue
        try:
            r, l = grade(it, value=min(ds_) if ds_ else None,
                         in_segment=inseg, is_none=is_none)
            out[code] = {"rank": r, "label": l,
                         "input": {"distance_m": min(ds_) if ds_ else None,
                                   "in_segment": inseg, "is_none": is_none},
                         "criterion": it["levels"][r - 1]["criterion"]}
        except Ungradable as e:
            gaps[code] = str(e)
    for code, it in crit.items():
        if code in out or code in gaps or it.get("rule_type") != "matrix":
            continue
        gaps[code] = "表3 無對應勘查資料（該欄未填或未勾選）"
    return out, gaps


def derive_table5(ds, region, case, segments):
    """以表5 之區段順序（比準地, 比較標的…）推導整張表5"""
    t5 = case.get("table5") or {}
    segs = t5.get("segment_nos") or []
    if len(segs) < 2:
        return {"segment_nos": segs, "rows": [], "note": "比較標的與比準地同區段或區段數不足"}
    crit = ds.criteria(region, "regional")
    levels = {sn: derive_segment_levels(ds, region, segments[sn])
              for sn in segs if sn in segments}
    rows, subtotals = [], {}
    for code, it in sorted(crit.items(), key=lambda kv: kv[1]["seq"]):
        base = levels.get(segs[0], ({}, {}))[0].get(code)
        cells, adjs, gaps = [], [], []
        for sn in segs[1:]:
            lv, gp = levels.get(sn, ({}, {}))
            c = lv.get(code)
            if base and c:
                cells.append(c); adjs.append(adjust_regional(it, base["rank"], c["rank"]))
            else:
                cells.append(None); adjs.append(None)
                gaps.append(gp.get(code) or
                            (levels.get(segs[0], ({}, {}))[1].get(code)) or "資料不足")
        rows.append({"item_code": code, "item_name": it["item_name"],
                     "group_code": it["group_code"], "group_name": it["group_name"],
                     "base": base, "comparables": cells,
                     "adjustments": adjs, "gaps": gaps,
                     "computable": base is not None and all(c is not None for c in cells)})
        g = it["group_code"]
        subtotals.setdefault(g, [0.0] * len(segs[1:]))
        for i, a in enumerate(adjs):
            if a is not None: subtotals[g][i] += a
    computable = [r for r in rows if r["computable"]]
    totals = [sum(subtotals[g][i] for g in subtotals) for i in range(len(segs) - 1)]
    return {
        "segment_nos": segs,
        "base_segment": segs[0],
        "rows": rows,
        "subtotals": {str(k): v for k, v in sorted(subtotals.items())},
        "totals_partial": totals,
        "computable_items": len(computable),
        "total_items": len(rows),
        "complete": len(computable) == len(rows),
    }


# ---------------------------------------------------------------- 表4 個別因素
# 表4「個別因素調整」7~25 為**宗地層級**比較（比準地 vs 各比較標的）。
# 條件欄是「每一宗地自身的勘查資料」：地籍圖（面積/寬度/深度/形狀/臨街）、
# 現場勘查（地勢/道路/接近距離/嫌惡設施/停車）、都市計畫書圖（行政條件）。
# 表7 宗地個別因素清冊之欄位編號 7~25 與本表完全相同，若比準地位於徵收範圍內
# （本案比準地宗地流水號 0003，屬範圍內），表7 即直接提供比準地該欄。
# 表1-1 買賣實例調查估價表只載實例之坐落、土地面積、交易日期與土地正常單價，
# **不含**其餘個別因素；比較標的之條件須由查估單位就該實例宗地另行勘查建立。
# 本案上述資料均未隨題目提供，僅「行政條件」可由表3 之區段法定管制值直接認定。
IND_FROM_SEGMENT = {
    # 個別因素細項 → (表3 觀測欄位, 狀態, 依據說明)
    "terrain": ("terrain", "推定",
                "表3 區段層級「地勢」；宗地地勢未經個別勘查，屬區段推定"),
    "zoning": ("zoning", "確認",
               "表3 區段層級「使用分區」；分區為法定管制，宗地與所在區段一致"),
    "bcr": ("bcr", "確認",
            "表3 區段層級「建蔽率」；法定管制值，宗地與所在區段一致"),
    "far": ("far", "確認",
            "表3 區段層級「容積率」；法定管制值，宗地與所在區段一致"),
}

# 條件欄無法自表3 取得者，逐項記錄其上游來源（供退補指名）
_T7 = "比準地（宗地流水號0003，在徵收範圍內）可由表7 宗地個別因素清冊同編號欄位取得"
IND_UPSTREAM = {
    1: f"地籍圖／土地登記（面積、寬度、深度、形狀、臨街情形）＋現場勘查（地勢）；{_T7}；"
       "比較標的須就該買賣實例宗地另行勘查（表1-1 僅載坐落、面積、交易日期、正常單價）",
    2: f"現場勘查：道路種類、面前道路名稱與寬度；{_T7}；比較標的須另行勘查",
    3: f"現場勘查實地量距：設施名稱＋距離(M)；{_T7}；比較標的須另行勘查",
    4: f"現場勘查：嫌惡設施名稱＋距離(M)、停車方便性；{_T7}；比較標的須另行勘查",
    5: "都市計畫書圖／表3 區段法定管制值",
    6: f"現場勘查，並於備註欄敘明調整理由（手冊 六(二)6）；{_T7}",
}


def _ind_condition(seg, item):
    """由表3 區段觀測值取出表4 個別因素之條件欄，回傳 (顯示文字, grade 參數, 狀態, 依據)"""
    code = item["item_code"]
    obs = seg.get("observations") or {}
    if code == "build_ban_restrict":
        ban = (obs.get("build_ban") or {}).get("raw")
        res = (obs.get("build_restrict") or {}).get("raw")
        if ban is None or res is None:
            return None
        if ban.strip() == "無" and res.strip() == "無":
            return ("無禁止或限制建築", {"category": "無禁止或限制建築"}, "確認",
                    f"表3 有無禁止建築「{ban}」、有無限制建築「{res}」")
        return (f"禁建：{ban}／限建：{res}", {"category": res}, "推定",
                "表3 禁限建欄位非「無」，須依實際限制內容對應級距")
    spec = IND_FROM_SEGMENT.get(code)
    if not spec:
        return None
    obs_code, status, basis = spec
    o = obs.get(obs_code) or {}
    raw, val = o.get("raw"), o.get("value")
    if code == "zoning":
        raw = (seg.get("valuation_basis") or {}).get("zoning_for_valuation") or raw
    if val is not None:
        return (raw or str(val), {"value": val}, status, f"{basis}：{raw or val}")
    if raw:
        return (raw, {"category": raw}, status, f"{basis}：{raw}")
    return None


def derive_table4_individual(ds, region, case, segments):
    """推導表4「個別因素調整」7~25 各細項之條件與差異率。

    回傳 rows：每列含比準地與各比較標的之條件、等級、差異率與狀態。
    條件欄若已載於題目之表4（factors[*].conditions）則優先採用，否則回退至表3。
    """
    crit = ds.criteria(region, "individual")
    t4 = case.get("table4") or {}
    seg_order = t4.get("segment_nos") or (case.get("table5") or {}).get("segment_nos") or []
    if len(seg_order) < 2:
        return {"segment_nos": seg_order, "rows": [], "totals": None,
                "note": "比較標的數不足"}
    base_no, comps = seg_order[0], seg_order[1:]
    given = t4.get("factors") or {}

    rows = []
    for code, it in sorted(crit.items(), key=lambda kv: kv[1]["seq"]):
        src = next((f for f in given.values() if f.get("field_no") == it.get("field_no")), None)
        row = {"field_no": it.get("field_no"), "item_code": code,
               "item_name": it["item_name"], "group_code": it["group_code"],
               "group_name": it["group_name"], "rule_type": it.get("rule_type"),
               "base": None, "comparables": [], "status": "資料不足",
               "gap": None, "basis": None}

        if src and (src.get("conditions") or src.get("diffs")):
            # 題目已填之條件欄（本案全部留白，保留此路徑供已填卷宗覆核）
            row["status"] = "源文件已載"
            row["basis"] = "doc/題目.pdf 表4 條件欄"
            row["source_conditions"] = src.get("conditions")
            row["source_diffs"] = src.get("diffs")
            rows.append(row)
            continue

        b = _ind_condition(segments.get(base_no) or {}, it)
        if not b:
            row["gap"] = ("表4 條件欄留白，且表3 無對應之宗地層級資料；上游："
                          + IND_UPSTREAM.get(it["group_code"], "表7／表1-1"))
            row["comparables"] = [{"segment": sn, "condition": None, "rank": None,
                                   "label": None, "diff": None} for sn in comps]
            rows.append(row)
            continue

        b_text, b_arg, b_status, b_basis = b
        row["basis"] = b_basis
        status = b_status
        try:
            b_rank, b_label = grade(it, **b_arg)
        except Ungradable:
            b_rank = b_label = None
        row["base"] = {"condition": b_text, "rank": b_rank, "label": b_label}

        for sn in comps:
            c = _ind_condition(segments.get(sn) or {}, it)
            if not c:
                row["comparables"].append({"segment": sn, "condition": None,
                                           "rank": None, "label": None, "diff": None})
                status = "資料不足"
                continue
            c_text, c_arg, c_status, _ = c
            if c_status == "推定":
                status = "推定" if status == "確認" else status
            try:
                c_rank, c_label = grade(it, **c_arg)
            except Ungradable:
                c_rank = c_label = None
            d = (adjust(it, b_rank, c_rank)
                 if it.get("rule_type") == "matrix" and b_rank and c_rank else None)
            row["comparables"].append({"segment": sn, "condition": c_text,
                                       "rank": c_rank, "label": c_label, "diff": d})

        if it.get("rule_type") != "matrix":
            row["gap"] = (f"基準表列為敘述型（{it.get('basis')}）："
                          + "；".join(it.get("notes") or [])
                          + "，差異率無查表矩陣可得")
            status = "條件可確認／差異率不可查表"
        elif any(c["diff"] is None for c in row["comparables"]):
            status = "資料不足"
        row["status"] = status
        rows.append(row)

    computable = [r for r in rows
                  if r["status"] in ("確認",) and all(c["diff"] is not None
                                                     for c in r["comparables"])]
    complete = len(computable) == len(rows)
    totals = ([sum(r["comparables"][i]["diff"] for r in rows) for i in range(len(comps))]
              if complete else None)
    return {"segment_nos": seg_order, "base_segment": base_no, "comparables": comps,
            "rows": rows, "computable_items": len(computable), "total_items": len(rows),
            "complete": complete, "totals": totals,
            "total_note": None if complete else
            "個別因素合計需 7~25 全數可判定，本案尚缺宗地層級資料，不得加總"}
