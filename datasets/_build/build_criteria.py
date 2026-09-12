# -*- coding: utf-8 -*-
"""建置評價基準明細表結構化資料集（JSON + YAML），含完整驗證"""
import os, sys, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml
from parse_criteria import parse
from threshold import parse_threshold
import catalog as C

LEVEL_NAMES = {
    2: ["優","劣"],
    3: ["優","普通","劣"],
    5: ["優","稍優","普通","稍劣","劣"],
    7: ["極優","優","稍優","普通","稍劣","劣","極劣"],
    9: ["超極優","極優","優","稍優","普通","稍劣","劣","極劣","超極劣"],
}

REGIONS = {
    "shulin": {
        "region_code":"shulin","region_name":"新北市樹林區","land_use_code":"residential",
        "land_use_name":"普通住宅用地",
        "txt":"評價基準明細表.txt",
        "source_pdf":"doc/rules/評價基準明細表.pdf",
        "regional_catalog":C.SHULIN_REGIONAL,"individual_catalog":C.SHULIN_INDIVIDUAL,
        "role":"target",  # 待作答案件
    },
    "jinshan": {
        "region_code":"jinshan","region_name":"新北市金山區","land_use_code":"commercial",
        "land_use_name":"商業用地",
        "txt":"評價基準明細表範例.txt",
        "source_pdf":"doc/rules/評價基準明細表範例.pdf",
        "regional_catalog":C.JINSHAN_REGIONAL,"individual_catalog":C.JINSHAN_INDIVIDUAL,
        "role":"reference",  # 已填範例
    },
}

def build_item(region, factor_type, seq, meta, block, block_idx):
    gcode, gname, icode, iname, fno = meta
    rows = block["rows"]; n = len(rows)
    matrix = [r[1] for r in rows]
    labels = LEVEL_NAMES.get(n, [r[0] for r in rows])

    # 備註（級距定義），套用跨行截斷修補
    ov = C.NOTE_OVERRIDES.get(region, {})
    notes = {}
    for lbl, txt in block["notes"]:
        notes[lbl] = txt
    for (bi, lbl), txt in ov.items():
        if bi == block_idx: notes[lbl] = txt

    levels = []
    for rank, lbl in enumerate(labels, 1):
        raw_label = rows[rank-1][0]
        crit = notes.get(lbl) or notes.get(raw_label) or ""
        levels.append({
            "rank": rank, "label": lbl,
            "criterion": crit,
            "threshold": parse_threshold(crit),
        })

    max_adj = max(abs(v) for r in matrix for v in r)
    step = round(max_adj / (n - 1), 6) if n > 1 else 0.0
    step_printed = abs(matrix[0][1]) if n > 1 else 0.0
    # 方向：若最優級(rank1)之門檻下限大於最劣級，視為 higher_is_better
    direction = _direction(levels)

    item_id = f"{region}.{factor_type}.{icode}"
    return {
        "item_id": item_id,
        "region_code": region,
        "factor_type": factor_type,
        "seq": seq,
        "group_code": gcode, "group_name": gname,
        "item_code": icode, "item_name": iname,
        "field_no": fno,
        "level_count": n,
        "level_labels": labels,
        "max_adjustment": max_adj,
        "step": step,
        "step_printed": step_printed,
        "rule_type": "matrix",
        "levels": levels,
        "matrix": matrix,
        "direction": direction,
        "source_block_index": block_idx,
    }

def _direction(levels):
    """判斷距離/數值方向：nearer_is_better / farther_is_better / n/a"""
    def firstnum(lv):
        th = lv.get("threshold") or {}
        for r in th.get("ranges", []):
            if r.get("min") is not None: return r["min"]
            if r.get("max") is not None: return r["max"]
        return None
    a, b = firstnum(levels[0]), firstnum(levels[-1])
    if a is None or b is None: return "n/a"
    if levels[0]["threshold"].get("in_segment") or a < b: return "lower_is_better"
    return "higher_is_better"

def validate(item, errs):
    n, m, iid = item["level_count"], item["matrix"], item["item_id"]
    if any(len(r) != n for r in m): errs.append(f"{iid}: 矩陣非方陣")
    for i in range(n):
        if abs(m[i][i]) > 1e-9: errs.append(f"{iid}: 對角線非零 [{i}][{i}]={m[i][i]}")
        for j in range(n):
            if abs(m[i][j] + m[j][i]) > 1e-6:
                errs.append(f"{iid}: 非反對稱 [{i}][{j}]={m[i][j]} vs [{j}][{i}]={m[j][i]}")
            exp = (j - i) * item["step"]
            if abs(m[i][j] - exp) > 0.02:   # 容差：原表數值為四捨五入至小數 2 位
                errs.append(f"{iid}: 步長不一致 [{i}][{j}]={m[i][j]} 期望 ≈{exp:.4f}")
    for lv in item["levels"]:
        if not lv["criterion"]: errs.append(f"{iid}: level {lv['rank']}({lv['label']}) 缺級距定義")

def main():
    S = sys.argv[1]  # scratchpad 目錄（含 pdftotext 輸出）
    OUT = "datasets"
    all_errs, summary = [], {}
    for rk, rc in REGIONS.items():
        blocks = parse(os.path.join(S, rc["txt"]))
        nreg = len(rc["regional_catalog"]); nind = len(rc["individual_catalog"])
        # 樹林個別因素容積率無矩陣，故矩陣區塊數少 1
        expect = nreg + nind
        if len(blocks) != expect:
            all_errs.append(f"{rk}: 區塊數 {len(blocks)} != 期望 {expect}")
        items = {"regional": [], "individual": []}
        for seq, meta in enumerate(rc["regional_catalog"]):
            it = build_item(rk, "regional", seq+1, meta, blocks[seq], seq)
            validate(it, all_errs); items["regional"].append(it)
        off = nreg
        icat = list(rc["individual_catalog"])
        bi = off
        for seq, meta in enumerate(icat):
            if rk == "shulin" and meta[2] == "far":
                continue  # 稍後插入 narrative 版本
            it = build_item(rk, "individual", seq+1, meta, blocks[bi], bi)
            validate(it, all_errs); items["individual"].append(it); bi += 1
        if rk == "shulin":
            far = dict(C.SHULIN_FAR_INDIVIDUAL)
            far.update({"item_id":"shulin.individual.far","region_code":"shulin",
                        "factor_type":"individual","seq":18,"direction":"n/a",
                        "level_labels":[],"source_block_index":None})
            items["individual"].insert(17, far)

        for ft in ("regional","individual"):
            d = os.path.join(OUT,"regions",rk,"criteria"); os.makedirs(d, exist_ok=True)
            doc = {
                "schema_version":"1.0",
                "region_code":rc["region_code"],"region_name":rc["region_name"],
                "land_use_code":rc["land_use_code"],"land_use_name":rc["land_use_name"],
                "factor_type":ft,
                "table_name":f"{rc['region_name']}{rc['land_use_name']}影響地價{'區域' if ft=='regional' else '個別'}因素評價基準明細表",
                "source":{"pdf":rc["source_pdf"],"role":rc["role"]},
                "source_anomalies":[a for a in C.SOURCE_ANOMALIES.get(rk,[]) if a["factor_type"]==ft],
                "item_count":len(items[ft]),
                "items":items[ft],
            }
            json.dump(doc, open(os.path.join(d,f"{ft}.json"),"w",encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            yaml.safe_dump(doc, open(os.path.join(d,f"{ft}.yaml"),"w",encoding="utf-8"),
                           allow_unicode=True, sort_keys=False, width=200)
        summary[rk] = {ft: len(items[ft]) for ft in items}
    print("=== 建置摘要 ===")
    for k,v in summary.items(): print(f"  {k}: 區域因素 {v['regional']} 項, 個別因素 {v['individual']} 項")
    print(f"\n=== 驗證 ===\n{'✅ 全部通過' if not all_errs else '❌ ' + str(len(all_errs)) + ' 項錯誤'}")
    for e in all_errs[:40]: print("  -", e)

if __name__ == "__main__": main()
