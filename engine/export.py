# -*- coding: utf-8 -*-
"""產出表3/表4/表5 中「可確認」之填表內容，每個數值附填寫依據"""
import os, sys, json, csv, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.loader import Dataset
from engine.compute import derive_segment_levels, derive_table4_individual, OBS_TO_ITEM
from engine.grading import adjust_regional

OUT = "output"
REGION = "shulin"
LEVEL_CODE = {1: "優", 2: "稍優", 3: "普通", 4: "稍劣", 5: "劣"}


def w_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def w_md(path, title, header, rows, note="", mode="w", level=1):
    with open(path, mode, encoding="utf-8") as f:
        if mode == "a": f.write("\n")
        f.write(f"{'#' * level} {title}\n\n")
        if note: f.write(note + "\n\n")
        f.write("| " + " | ".join(header) + " |\n")
        f.write("|" + "|".join("---" for _ in header) + "|\n")
        for r in rows:
            f.write("| " + " | ".join("" if c is None else str(c) for c in r) + " |\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    ds = Dataset()
    crit = ds.criteria(REGION, "regional")
    segs = ds.segments(REGION)
    case = list(ds.cases(REGION).values())[0]
    t5 = case["table5"]; t4 = case["table4"]
    seg_order = t5["segment_nos"]                    # [比準地, 比較標的1..3]
    base_no = seg_order[0]

    levels = {sn: derive_segment_levels(ds, REGION, segs[sn]) for sn in seg_order}
    ITEM2OBS = {v: k for k, v in OBS_TO_ITEM.items()}

    # ---------------- 表3：各區段優劣等級 ----------------
    t3_rows, basis_rows = [], []
    for sn in seg_order:
        lv, _gaps = levels[sn]
        seg = segs[sn]
        for code, it in sorted(crit.items(), key=lambda kv: kv[1]["seq"]):
            if code not in lv: continue
            g = lv[code]
            obs_code = ITEM2OBS.get(code)
            obs = (seg.get("observations") or {}).get(obs_code) or {}
            src = obs.get("raw")
            if code == "land_improve":
                src = f"勾選 {g['input']['improvement_count']} 項：" + "、".join(g["input"]["items"])
            t3_rows.append([sn, it["group_code"], it["group_name"], it["item_name"],
                            src, g["rank"], it["level_count"], g["label"]])
            basis_rows.append([
                "表3", sn, it["item_name"], f"{g['rank']}／{it['level_count']}級（{g['label']}）",
                f"表3 實測：{src}", f"基準表級距：{g['criterion']}",
                f"{REGION}.regional.{code}", "確認"])

    w_csv(f"{OUT}/表3_優劣等級.csv",
          ["地價區段號", "主要項目代號", "主要項目", "修正細項", "表3所載內容",
           "優劣等級序號", "總級數", "優劣等級"], t3_rows)
    w_md(f"{OUT}/表3_優劣等級.md", "表3 地價區段勘查表 — 優劣等級（可確認部分）",
         ["區段", "項目", "修正細項", "表3所載", "等級碼", "優劣等級"],
         [[r[0], f"({r[1]}){r[2]}", r[3], r[4], f"{r[5]} / {r[6]}", r[7]] for r in t3_rows],
         "> 等級碼格式為「第N級／共M級」，對應表3 各細項左側之兩位數字欄。")

    # ---------------- 表5：區域因素分析明細表 ----------------
    comps = seg_order[1:]
    t5_rows = []
    group_items, group_ok = {}, {}
    for code, it in sorted(crit.items(), key=lambda kv: kv[1]["seq"]):
        g = it["group_code"]
        group_items.setdefault(g, []).append(code)
        b = levels[base_no][0].get(code)
        row = {"group_code": g, "group_name": it["group_name"],
               "item_code": code, "item_name": it["item_name"],
               "base_rank": b["rank"] if b else None,
               "base_label": b["label"] if b else None,
               "comparables": [], "status": "確認" if b else "資料不足"}
        for sn in comps:
            c = levels[sn][0].get(code)
            if b and c:
                a = adjust_regional(it, b["rank"], c["rank"])
                row["comparables"].append({"segment": sn, "rank": c["rank"],
                                           "label": c["label"], "adjustment": a})
            else:
                row["comparables"].append({"segment": sn, "rank": None,
                                           "label": None, "adjustment": None})
                row["status"] = "資料不足"
        # 「其他影響因素」於原始題目之表5-1 已載明「無／0.00」，屬源文件既有資料
        if row["status"] != "確認":
            src = next((x for x in t5["rows"] if x["item_code"] == code), None)
            if src and src.get("adjustments") and len(src["adjustments"]) == len(comps):
                for i, a in enumerate(src["adjustments"]):
                    row["comparables"][i].update({"adjustment": a, "label": "無", "rank": None})
                row["status"] = "源文件已載"
                for i, sn in enumerate(comps):
                    basis_rows.append([
                        "表5", sn, it["item_name"], f"{src['adjustments'][i]:+.2f}%",
                        "doc/題目.pdf 表5-1 原已填載「無」", "非推導值，逕予採用",
                        f"{REGION}.regional.{code}", "源文件已載"])
        t5_rows.append(row)
        group_ok.setdefault(g, []).append(row["status"] in ("確認", "源文件已載"))
        if row["status"] == "確認":
            for cc in row["comparables"]:
                basis_rows.append([
                    "表5", cc["segment"], it["item_name"],
                    f"{cc['adjustment']:+.2f}%",
                    f"比準地 {base_no} {row['base_label']}({row['base_rank']}) ／ "
                    f"比較標的 {cc['label']}({cc['rank']})",
                    f"查表：{it['level_count']}級，最大±{it['max_adjustment']}%，"
                    f"級距 {it['step']}%；({cc['rank']}-{row['base_rank']})×{it['step']}",
                    f"{REGION}.regional.{code}", "確認"])

    # 小計：該主要項目之細項全部可算時才成立
    subtotals = {}
    for g, flags in group_ok.items():
        if all(flags):
            subtotals[g] = [sum(r["comparables"][i]["adjustment"]
                                for r in t5_rows if r["group_code"] == g)
                            for i in range(len(comps))]

    rows_md = []
    for r in t5_rows:
        cells = []
        for cc in r["comparables"]:
            cells += [f"{cc['rank']} {cc['label']}" if cc["rank"] else "—",
                      f"{cc['adjustment']:+.2f}" if cc["adjustment"] is not None else "—"]
        rows_md.append([f"({r['group_code']}){r['group_name']}", r["item_name"],
                        f"{r['base_rank']} {r['base_label']}" if r["base_rank"] else "—",
                        *cells, r["status"]])
    hdr = ["主要項目", "修正細項", f"比準地 {base_no}"]
    for sn in comps: hdr += [f"{sn} 等級", f"{sn} 修正%"]
    hdr += ["狀態"]
    w_md(f"{OUT}/表5-1_區域因素分析明細表.md",
         "表5-1 影響地價區域因素分析明細表（普通住宅用地）— 可確認部分",
         hdr, rows_md,
         f"> 案號 {case['case_no']}　比準地區段 {base_no}\n>\n"
         f"> 「—」表示表3 該欄未勘查，無法判級（非填 0）。")
    w_csv(f"{OUT}/表5-1_區域因素分析明細表.csv", hdr, rows_md)

    # ---------------- 表4：可驗算部分 ----------------
    s = t4["summary"]
    up = s["unit_price"]["values"]; da = s["date_adj"]["percents"]; ap = s["adjusted_price"]["values"]
    t4_rows = []
    for i, sn in enumerate(comps):
        if i >= len(up) or i >= len(da): continue
        exact = up[i] * (1 + da[i] / 100)
        ok = abs(exact - ap[i]) <= 1 if i < len(ap) else None
        t4_rows.append([f"比較標的{i+1}", sn, f"{up[i]:,.0f}", f"{da[i]:.2f}%",
                        f"{exact:,.2f}", f"{ap[i]:,.0f}" if i < len(ap) else "—",
                        "✅ 相符" if ok else "❌ 不符"])
        basis_rows.append([
            "表4", sn, "調整至估價基準日單價", f"{ap[i]:,.0f}",
            f"土地正常單價 {up[i]:,.0f} × (1 + {da[i]:.2f}%)",
            f"= {exact:,.2f}（表上值經進位）", "手冊 伍、六(四)", "驗算相符" if ok else "驗算不符"])
    w_md(f"{OUT}/表4_比較法調查估價表.md", "表4 比較法調查估價表 — 可確認部分",
         ["標的", "地價區段", "土地正常單價", "交易日期調整%", "計算值", "表上值", "驗算"],
         t4_rows,
         "> 本檔含兩個區塊：① 價格調整驗算　② 個別因素調整（7~25）逐項填表。\n"
         ">\n"
         "> 區域因素調整百分率（引用表5 總修正數）、合計、絕對值加總、權重、試算價格、\n"
         "> 比準地比較價格仍因上游資料不足而無法確認，詳 README §4。")
    w_csv(f"{OUT}/表4_比較法調查估價表.csv",
          ["標的", "地價區段", "土地正常單價", "交易日期調整率", "計算值", "表上值", "驗算結果"], t4_rows)

    # ---------------- 表4：個別因素調整（7~25） ----------------
    t4i = derive_table4_individual(ds, REGION, case, segs)
    ind_hdr = ["主要項目", "編號", "修正細項", f"比準地 {base_no} 條件"]
    for sn in comps: ind_hdr += [f"{sn} 條件", f"{sn} 差異率%"]
    ind_hdr += ["狀態", "依據／缺漏原因"]

    ind_rows = []
    for r in t4i["rows"]:
        cells = []
        for c in r["comparables"]:
            cells += [c["condition"] or "—",
                      f"{c['diff']:+.2f}" if c["diff"] is not None else "—"]
        ind_rows.append([f"({r['group_code']}){r['group_name']}",
                         r["field_no"] if r["field_no"] else "—", r["item_name"],
                         (r["base"] or {}).get("condition") or "—", *cells,
                         r["status"], r["gap"] or r["basis"] or ""])
        b = r["base"] or {}
        for c in r["comparables"]:
            label = (f"{r['field_no']}{r['item_name']}" if r["field_no"]
                     else f"6其他-{r['item_name']}")
            if c["diff"] is None:
                basis_rows.append([
                    "表4", c["segment"], label, "—",
                    (f"{r['basis']}；比準地「{b.get('condition')}」／比較標的「{c['condition']}」"
                     if c["condition"] else "表4 條件欄留白"),
                    r["gap"] or "資料不足",
                    f"{REGION}.individual.{r['item_code']}", r["status"]])
                continue
            it = ds.criteria(REGION, "individual")[r["item_code"]]
            basis_rows.append([
                "表4", c["segment"], label, f"{c['diff']:+.2f}%",
                f"{r['basis']}；比準地「{b.get('condition')}」／比較標的「{c['condition']}」",
                f"查表：{it['level_count']}級，最大±{it['max_adjustment']}%，級距 {it['step']}%；"
                f"({c['rank']}-{b.get('rank')})×{it['step']}",
                f"{REGION}.individual.{r['item_code']}", r["status"]])

    total_cells = []
    for i, sn in enumerate(comps):
        total_cells += ["—", f"{t4i['totals'][i]:+.2f}" if t4i["totals"] else "—"]
    ind_rows.append(["合計", "—", "個別因素差異率合計", "—", *total_cells,
                     "不得加總" if not t4i["totals"] else "確認",
                     t4i.get("total_note") or ""])

    w_md(f"{OUT}/表4_比較法調查估價表.md", "個別因素調整（7~25）", ind_hdr, ind_rows,
         f"> 宗地層級比較：比準地 {base_no} vs 各比較標的。條件欄上游為\n"
         "> 比準地 ← 表7 宗地個別因素清冊／地籍圖；比較標的 ← 表1-1 買賣實例調查估價表，\n"
         "> 兩者均未隨題目提供，僅行政條件（22~25）可由表3 之法定管制值認定。\n"
         ">\n"
         "> 24容積率之基準明細表列為敘述型（以土地開發分析法試算），無查表矩陣，\n"
         "> 故條件可填、差異率不可查表得出。",
         mode="a", level=2)
    w_csv(f"{OUT}/表4_個別因素調整.csv", ind_hdr, ind_rows)

    # ---------------- 依據明細 ----------------
    w_csv(f"{OUT}/填表依據明細.csv",
          ["表別", "地價區段", "修正細項", "填寫值", "資料來源", "計算/查表依據", "基準表項目ID", "狀態"],
          basis_rows)

    # ---------------- JSON 彙總 ----------------
    payload = {
        "generated_at": datetime.date.today().isoformat(),
        "case_no": case["case_no"], "region": REGION,
        "region_name": ds.region_info(REGION)["region_name"],
        "land_use": ds.region_info(REGION)["land_use_name"],
        "base_segment": base_no, "comparable_segments": comps,
        "table3_levels": t3_rows,
        "table5": {"rows": t5_rows,
                   "complete_subtotals": {str(k): v for k, v in sorted(subtotals.items())},
                   "incomplete_groups": sorted(set(g for g, f in group_ok.items() if not all(f))),
                   "total": None,
                   "total_note": "部分主要項目資料不足，總修正數不得計算"},
        "table4_verified": t4_rows,
        "table4_individual": t4i,
        "basis": basis_rows,
    }
    json.dump(payload, open(f"{OUT}/output.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    n_ok = sum(1 for r in t5_rows if r["status"] == "確認")
    print(f"表3 等級：{len(t3_rows)} 筆（{len(seg_order)} 區段 × {n_ok} 細項）")
    print(f"表5 可確認：{n_ok}/{len(t5_rows)} 細項 × {len(comps)} 個比較標的 = {n_ok*len(comps)} 個修正率")
    print(f"表5 完整小計：主要項目 {sorted(subtotals)}　不完整：{payload['table5']['incomplete_groups']}")
    print(f"表4 驗算：{len(t4_rows)} 筆")
    print(f"表4 個別因素：{t4i['computable_items']}/{t4i['total_items']} 細項可確認差異率，合計 {'可算' if t4i['totals'] else '不得加總'}")
    print(f"依據明細：{len(basis_rows)} 筆")
    return payload


if __name__ == "__main__":
    main()
