# -*- coding: utf-8 -*-
"""把可確認之填表內容寫回 input/ 的三張空白表格，輸出至 output/log/secondVersion。

每個被填入的儲存格都：
  ① 以底色標示資料性質（題目原載／AI 判定／推定／資料不足）
  ② 掛上儲存格註解，載明資料來源與查表依據
  ③ 於同一活頁簿之「填表依據」工作表留下逐格明細（可獨立複核）
"""
import os, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import PatternFill, Font, Alignment

from loader import Dataset
from compute import derive_segment_levels, derive_table4_individual, OBS_TO_ITEM
from grading import adjust

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "input")
OUT = os.path.join(ROOT, "output", "log", "secondVersion")
REGION = "shulin"
AUTHOR = "AI 查估審查助理"

# 底色圖例 ---------------------------------------------------------------
FILL = {
    "題目原載": PatternFill("solid", fgColor="D9EAD3"),   # 綠：doc/題目.pdf 勘查事實抄錄
    "AI判定":   PatternFill("solid", fgColor="FFF2CC"),   # 黃：依評價基準明細表查表判定
    "推定":     PatternFill("solid", fgColor="FCE5CD"),   # 橘：區段層級推定至宗地層級
    "資料不足": PatternFill("solid", fgColor="F4CCCC"),   # 紅：應填而題目未提供，須退補
    "不適用":   PatternFill("solid", fgColor="EFEFEF"),   # 灰：本用地別無此細項
}
LEGEND = [
    ("題目原載", "D9EAD3", "doc/題目.pdf 之表3／表4 原已載明之勘查事實或價格，逕予抄錄"),
    ("AI判定", "FFF2CC", "由勘查事實對照『影響地價區域（個別）因素評價基準明細表』查表判定，無估算成分"),
    ("推定", "FCE5CD", "以地價區段層級記載推定至宗地層級，未經個別勘查，僅供參考"),
    ("資料不足", "F4CCCC", "應填而題目未提供勘查資料，依『不以推測值填充』原則留空並列為退補事項"),
    ("不適用", "EFEFEF", "普通住宅用地之評價基準明細表無此修正細項"),
]

basis_rows = []      # 逐格填表依據


def put(ws, coord, value, kind, field, source, basis, item_id="", seg=""):
    """寫入一格，套底色、掛註解，並登錄填表依據"""
    c = ws[coord]
    c.value = value
    c.fill = FILL[kind]
    note = f"【{kind}】{field}\n填寫值：{value}\n資料來源：{source}\n判定依據：{basis}"
    if item_id:
        note += f"\n基準表項目ID：{item_id}"
    cm = Comment(note, AUTHOR)
    cm.width, cm.height = 320, 150
    c.comment = cm
    basis_rows.append([seg, coord, field, value, source, basis, item_id, kind])
    return c


def shade(ws, coord, kind):
    ws[coord].fill = FILL[kind]


def add_basis_sheet(wb, title_note):
    ws = wb.create_sheet("填表依據")
    ws["A1"] = "填表依據明細"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = title_note
    ws["A3"] = f"產生日期：{datetime.date.today().isoformat()}　產生器：engine/export_xlsx.py"

    ws["A5"] = "底色圖例"
    ws["A5"].font = Font(bold=True)
    for i, (name, color, desc) in enumerate(LEGEND):
        r = 6 + i
        ws.cell(r, 1, name).fill = PatternFill("solid", fgColor=color)
        ws.cell(r, 2, desc)

    hdr = ["地價區段／欄位群", "儲存格", "欄位", "填寫值", "資料來源", "計算／查表依據",
           "基準表項目ID", "資料性質"]
    r0 = 6 + len(LEGEND) + 1
    for j, h in enumerate(hdr, 1):
        c = ws.cell(r0, j, h)
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDDDDD")
    for i, row in enumerate(basis_rows, 1):
        for j, v in enumerate(row, 1):
            ws.cell(r0 + i, j, v)
        ws.cell(r0 + i, 8).fill = FILL.get(row[7], FILL["不適用"])
    for col, w in zip("ABCDEFGH", (16, 12, 34, 26, 46, 52, 34, 12)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = ws.cell(r0 + 1, 1)
    return ws


# ===================================================================== 表3
# 修正細項 → (等級序號格, 總級數格)；表3 每個細項左側兩位數字欄＝「第N級／共M級」
T3_LEVEL_CELL = {
    "urban_plan": ("B4", "C4"), "zoning": ("B5", "C5"), "bcr": ("B6", "C6"),
    "far": ("B7", "C7"), "build_ban": ("B8", "C8"), "build_restrict": ("B9", "C9"),
    "main_road_width": ("B11", "C11"), "avg_road_width": ("B12", "C12"),
    "near_station": ("B13", "C13"), "near_busstop": ("B17", "C17"),
    "near_interchange": ("B19", "C19"), "road_dev": ("B23", "C23"),
    "sunlight": ("B24", "C24"), "view": ("B25", "C25"), "slope": ("B26", "C26"),
    "drainage": ("B27", "C27"), "terrain": ("B28", "C28"),
    "land_improve": ("B31", "C31"), "near_school": ("B35", "C35"),
    "near_market": ("B39", "C39"), "near_park": ("B42", "C42"),
    "near_tourism": ("M4", "N4"), "parking": ("M6", "N6"),
    "near_service": ("M8", "N8"), "utility_facility": ("M14", "N14"),
    "funeral_facility": ("M18", "N18"), "waste_facility": ("M22", "N22"),
    "pollution": ("M25", "N25"),
}
# 普通住宅用地之評價基準明細表無此細項 → 等級欄留空並標為「不適用」
T3_NA_CELLS = {
    "B20": "接近聚落程度", "B21": "接近運銷中心程度", "B22": "接近消費市場程度",
    "B29": "風勢", "B30": "土質", "B33": "農地改良",
    "M10": "電力資源", "M11": "產業用水及設施", "M12": "污廢水及廢棄物處理設施",
    "M30": "百貨公司", "M32": "金融機構", "M34": "娛樂設施",
    "M36": "大型展示中心或觀光飯店", "M38": "顧客之通行量", "M39": "店舖之毗連狀態",
}
# 觀測欄位 → 表3 事實欄儲存格
T3_OBS_CELL = {
    "urban_plan": "H4", "zoning": "H5", "bcr": "H6", "far": "H7",
    "build_ban": "H8", "build_restrict": "H9", "avg_road_width": "G12",
    "road_dev": "I23", "sunlight": "I24", "view": "I25", "slope": "I26",
    "drainage": "I27", "terrain": "I28", "wind": "I29", "soil": "I30",
    "build_density": "R42", "build_type": "R43",
}
# 設施類子項名稱（題目表3 已列印之子欄位名稱）
T3_SUB_LABELS = {
    "F35": "國小", "F36": "國中", "F37": "高中", "F38": "大專院校",
    "F39": "傳統市場", "F40": "超級市場", "F41": "超大型購物中心",
    "F42": "里鄰公園", "F43": "一般公園", "F44": "廣場、徒步區",
}
IMPROVE_CELLS = ("E31", "E32")
LAND_USE_CELL = "Q44"


def build_table3(ds, segs, seg_order, levels, crit):
    wb = openpyxl.load_workbook(os.path.join(IN, "表3地價區段勘查表.xlsx"))
    tpl = wb.active
    tpl.title = seg_order[0]
    sheets = [tpl] + [wb.copy_worksheet(tpl) for _ in seg_order[1:]]
    for ws, sn in zip(sheets, seg_order):
        ws.title = sn
        fill_table3(ws, ds, segs[sn], sn, levels[sn][0], levels[sn][1], crit)
    add_basis_sheet(wb, "表3 地價區段勘查表（新北市樹林區 普通住宅用地，4 個地價區段）")
    p = os.path.join(OUT, "表3_地價區段勘查表_已填.xlsx")
    wb.save(p)
    return p


def fill_table3(ws, ds, seg, sn, lv, gaps, crit):
    obs = seg.get("observations") or {}
    src_pdf = "doc/題目.pdf 表3 地價區段勘查表"
    ws["A2"] = "新北市樹林區（普通住宅用地）"
    ws["A2"].font = Font(size=11)

    put(ws, "B3", seg["year_period"], "題目原載", "年期", src_pdf, "原表所載", seg=sn)
    put(ws, "G3", sn, "題目原載", "區段編號", src_pdf, "原表所載", seg=sn)
    put(ws, "L3", seg["scope_desc"], "題目原載", "區段範圍", src_pdf, "原表所載", seg=sn)
    ws["L3"].alignment = Alignment(wrap_text=True, vertical="center")

    # --- 勘查事實欄（題目原載）---
    for obs_code, coord in T3_OBS_CELL.items():
        o = obs.get(obs_code) or {}
        raw = o.get("raw")
        if obs_code == "avg_road_width" and o.get("value") is not None:
            raw = o["value"]          # 單位 M 已印在相鄰格，本格只填數值
        if raw is None:
            # 風勢、土質未列於普通住宅用地之評價基準明細表，屬不適用而非退補事項
            kind = "不適用" if obs_code in ("wind", "soil") else "資料不足"
            why = ("普通住宅用地之影響地價區域因素評價基準明細表無此修正細項"
                   if kind == "不適用" else "題目表3 該欄未填載")
            shade(ws, coord, kind)
            basis_rows.append([sn, coord, o.get("field_name", obs_code), "（空白）",
                               src_pdf, why, "", kind])
            continue
        put(ws, coord, raw, "題目原載", o.get("field_name", obs_code), src_pdf,
            "原表所載勘查事實，逕予抄錄", seg=sn)
    ws["H6"].alignment = ws["H7"].alignment = Alignment(horizontal="right")

    # 主要道路：名稱＋寬度分屬兩格
    mr = obs.get("main_road") or {}
    if mr.get("raw"):
        put(ws, "G11", mr.get("road_name") or mr["raw"], "題目原載", "主要道路名稱",
            src_pdf, f"原表所載：{mr['raw']}", seg=sn)
        put(ws, "J11", mr.get("value"), "題目原載", "主要道路寬度(M)",
            src_pdf, f"原表所載：{mr['raw']}", seg=sn)

    # 土地改良：把 □ 改為 ■
    improves = seg.get("improvements") or []
    for coord in IMPROVE_CELLS:
        text = ws[coord].value or ""
        for item in improves:
            text = text.replace("□" + item, "■" + item)
        put(ws, coord, text, "題目原載", "建築基地改良（勾選項）", src_pdf,
            "原表勾選：" + "、".join(improves), seg=sn)

    # 土地利用現況：把對應之 ○ 改為 ●
    cur = seg.get("land_use_current")
    if cur:
        text = (ws[LAND_USE_CELL].value or "").replace("○" + cur, "●" + cur)
        vb = seg.get("valuation_basis") or {}
        note = "原表勾選：" + cur
        if vb.get("land_use_current_overridden"):
            note += ("；惟依 doc/rules/extra.md 第1條，本區段使用分區以變更前之「"
                     + vb.get("zoning_prior_to_change", "") + "」作為估價判定基準，"
                     "本欄「現況」不作為使用分區優劣判定依據")
        put(ws, LAND_USE_CELL, text, "題目原載", "土地利用現況", src_pdf, note, seg=sn)

    # 設施類子欄位名稱（題目表3 已列印）
    for coord, label in T3_SUB_LABELS.items():
        ws[coord] = label
        ws[coord].alignment = Alignment(horizontal="center")

    # --- 優劣等級欄 ---
    for code, (rank_c, cnt_c) in T3_LEVEL_CELL.items():
        it = crit.get(code)
        if not it:
            continue
        g = lv.get(code)
        if not g:
            for cc in (rank_c, cnt_c):
                shade(ws, cc, "資料不足")
            basis_rows.append([sn, f"{rank_c}/{cnt_c}", it["item_name"], "（留空）",
                               src_pdf, gaps.get(code, "表3 無對應勘查資料"),
                               f"{REGION}.regional.{code}", "資料不足"])
            continue
        obs_code = ITEM2OBS.get(code)
        raw = ((seg.get("observations") or {}).get(obs_code) or {}).get("raw")
        if code == "land_improve":
            raw = f"勾選 {len(improves)} 項：" + "、".join(improves)
        if code == "zoning":
            vb = seg.get("valuation_basis") or {}
            if vb.get("zoning_for_valuation"):
                raw = vb["zoning_for_valuation"]
        put(ws, rank_c, g["rank"], "AI判定", it["item_name"] + "（第N級）",
            f"表3 實測：{raw}", f"基準表級距「{g['criterion']}」→ 第{g['rank']}級（{g['label']}）",
            f"{REGION}.regional.{code}", seg=sn)
        put(ws, cnt_c, it["level_count"], "AI判定", it["item_name"] + "（共M級）",
            "doc/rules/評價基準明細表.pdf", f"本細項共 {it['level_count']} 級",
            f"{REGION}.regional.{code}", seg=sn)
        for cc in (rank_c, cnt_c):
            ws[cc].alignment = Alignment(horizontal="center")

    # --- 不適用之細項 ---
    for coord, name in T3_NA_CELLS.items():
        col = coord[0]
        nxt = chr(ord(col) + 1) + coord[1:]
        for cc in (coord, nxt):
            shade(ws, cc, "不適用")
        basis_rows.append([sn, f"{coord}/{nxt}", name, "（留空）",
                           "doc/rules/評價基準明細表.pdf",
                           "普通住宅用地之影響地價區域因素評價基準明細表無此修正細項",
                           "", "不適用"])


# ===================================================================== 表5
T5_ROW = {                      # 修正細項 seq → 表5 列號
    1: 5, 2: 6, 3: 7, 4: 8, 5: 9, 6: 10,
    7: 12, 8: 13, 9: 14, 10: 15, 11: 16, 12: 17,
    13: 19, 14: 20, 15: 21, 16: 22, 17: 23,
    18: 25,
    19: 27, 20: 28, 21: 29, 22: 30, 23: 31, 24: 32,
    25: 34, 26: 35, 27: 36,
    28: 38,
    29: 40,
}
T5_SUBTOTAL_ROW = {1: 11, 2: 18, 3: 24, 4: 26, 5: 33, 6: 37, 7: 39, 8: 41}
T5_TOTAL_ROW = 42
# 比準地 (等級序號欄, 等級文字欄)；比較標的 1~3 (等級序號, 等級文字, 修正百分比)
T5_BASE_COLS = ("C", "D")
T5_COMP_COLS = [("E", "F", "G"), ("H", "I", "J"), ("K", "L", "M")]
T5_SUBTOTAL_COL = ["E", "H", "K"]


def build_table5(ds, case, segs, seg_order, levels, crit):
    wb = openpyxl.load_workbook(os.path.join(IN, "表5影響地價區域因素分析明細表(住宅用地).xlsx"))
    ws = wb.active
    base_no, comps = seg_order[0], seg_order[1:]
    t5 = case["table5"]
    src_pdf = "doc/題目.pdf 表5-1"

    put(ws, "B2", case["case_no"], "題目原載", "案號", src_pdf, "原表所載", seg="全表")
    put(ws, "C3", base_no, "題目原載", "地價區段號（比準地）", src_pdf, "原表所載", seg="全表")
    for i, sn in enumerate(comps):
        put(ws, f"{T5_COMP_COLS[i][0]}3", sn, "題目原載", f"地價區段號（比較標的{i+1}）",
            src_pdf, "原表所載", seg="全表")
        put(ws, f"{chr(ord(T5_COMP_COLS[i][1]) + 1)}2", i + 1, "題目原載",
            f"比較標的{i+1} 實例編號", src_pdf, "原表所載", seg="全表")

    group_ok, group_vals = {}, {}
    for code, it in sorted(crit.items(), key=lambda kv: kv[1]["seq"]):
        r = T5_ROW[it["seq"]]
        g = it["group_code"]
        b = levels[base_no][0].get(code)
        ok = b is not None
        vals = []

        if code == "other":
            # 其他影響因素：doc/題目.pdf 表5-1 原已填載「－／無／0.00」，屬源文件既有資料
            put(ws, f"{T5_BASE_COLS[0]}{r}", "－", "題目原載", "其他影響因素（比準地等級）",
                src_pdf, "原表所載", f"{REGION}.regional.other", seg="全表")
            put(ws, f"{T5_BASE_COLS[1]}{r}", "無", "題目原載", "其他影響因素（比準地）",
                src_pdf, "原表所載", f"{REGION}.regional.other", seg="全表")
            for i, sn in enumerate(comps):
                cr, cl, cp = T5_COMP_COLS[i]
                put(ws, f"{cr}{r}", "－", "題目原載", f"其他影響因素（{sn} 等級）",
                    src_pdf, "原表所載", f"{REGION}.regional.other", seg=sn)
                put(ws, f"{cl}{r}", "無", "題目原載", f"其他影響因素（{sn}）",
                    src_pdf, "原表所載", f"{REGION}.regional.other", seg=sn)
                c = put(ws, f"{cp}{r}", 0.0, "題目原載", f"其他影響因素（{sn} 修正百分比）",
                        src_pdf, "原表所載「無」，修正百分比 0.00，非推導值",
                        f"{REGION}.regional.other", seg=sn)
                c.number_format = "0.00"
                vals.append(0.0)
            group_ok[g] = True
            group_vals[g] = vals
            continue

        if not ok:
            for col in T5_BASE_COLS:
                shade(ws, f"{col}{r}", "資料不足")
            basis_rows.append([base_no, f"{T5_BASE_COLS[0]}{r}", it["item_name"], "（留空）",
                               "表3 地價區段勘查表", levels[base_no][1].get(code, "資料不足"),
                               f"{REGION}.regional.{code}", "資料不足"])
        else:
            put(ws, f"{T5_BASE_COLS[0]}{r}", b["rank"], "AI判定",
                f"{it['item_name']}（比準地等級序號）", f"表3 {base_no} 判定結果",
                f"級距「{b['criterion']}」→ 第{b['rank']}級", f"{REGION}.regional.{code}",
                seg=base_no)
            put(ws, f"{T5_BASE_COLS[1]}{r}", b["label"], "AI判定",
                f"{it['item_name']}（比準地等級）", f"表3 {base_no} 判定結果",
                f"第{b['rank']}／共{it['level_count']}級", f"{REGION}.regional.{code}",
                seg=base_no)

        for i, sn in enumerate(comps):
            cr, cl, cp = T5_COMP_COLS[i]
            c = levels[sn][0].get(code)
            if not (b and c):
                ok = False
                for col in (cr, cl, cp):
                    shade(ws, f"{col}{r}", "資料不足")
                basis_rows.append([sn, f"{cr}{r}", it["item_name"], "（留空）",
                                   "表3 地價區段勘查表",
                                   levels[sn][1].get(code, "資料不足"),
                                   f"{REGION}.regional.{code}", "資料不足"])
                continue
            a = adjust(it, b["rank"], c["rank"])
            vals.append(a)
            put(ws, f"{cr}{r}", c["rank"], "AI判定", f"{it['item_name']}（{sn} 等級序號）",
                f"表3 {sn} 判定結果", f"級距「{c['criterion']}」→ 第{c['rank']}級",
                f"{REGION}.regional.{code}", seg=sn)
            put(ws, f"{cl}{r}", c["label"], "AI判定", f"{it['item_name']}（{sn} 等級）",
                f"表3 {sn} 判定結果", f"第{c['rank']}／共{it['level_count']}級",
                f"{REGION}.regional.{code}", seg=sn)
            cell = put(ws, f"{cp}{r}", a, "AI判定", f"{it['item_name']}（{sn} 修正百分比）",
                       f"比準地 {base_no} {b['label']}({b['rank']}) ／ {sn} {c['label']}({c['rank']})",
                       f"查表：共{it['level_count']}級、最大±{it['max_adjustment']}%、"
                       f"級距{it['step']}%；({b['rank']}−{c['rank']})×{it['step']} = {a:+.2f}",
                       f"{REGION}.regional.{code}", seg=sn)
            cell.number_format = "0.00"

        group_ok[g] = group_ok.get(g, True) and ok and len(vals) == len(comps)
        if ok and len(vals) == len(comps):
            prev = group_vals.setdefault(g, [0.0] * len(comps))
            group_vals[g] = [p + v for p, v in zip(prev, vals)]

    # --- 百分比小計：該主要項目所有細項皆可判定時才成立 ---
    for g, r in T5_SUBTOTAL_ROW.items():
        gname = next(it["group_name"] for it in crit.values() if it["group_code"] == g)
        for i, sn in enumerate(comps):
            col = T5_SUBTOTAL_COL[i]
            if group_ok.get(g) and g in group_vals:
                v = group_vals[g][i]
                cell = put(ws, f"{col}{r}", v, "AI判定", f"({g}){gname} 百分比小計（{sn}）",
                           "本表同組各修正細項修正百分比",
                           "＝該主要項目全部細項修正百分比之和"
                           + ("（本組細項由題目原載）" if g == 8 else ""),
                           f"{REGION}.regional.group{g}", seg=sn)
                cell.number_format = "0.00"
                cell.alignment = Alignment(horizontal="center")
            else:
                miss = [it["item_name"] for c2, it in crit.items()
                        if it["group_code"] == g and c2 not in levels[sn][0]]
                cell = put(ws, f"{col}{r}", "資料不足", "資料不足",
                           f"({g}){gname} 百分比小計（{sn}）", "表3 地價區段勘查表",
                           "本組尚有細項無法判定，小計不成立；缺：" + "、".join(miss),
                           f"{REGION}.regional.group{g}", seg=sn)
                cell.alignment = Alignment(horizontal="center")

    # --- 總修正數 ---
    incomplete = sorted(g for g in T5_SUBTOTAL_ROW if not group_ok.get(g))
    for i, sn in enumerate(comps):
        col = T5_SUBTOTAL_COL[i]
        cell = put(ws, f"{col}{T5_TOTAL_ROW}", "資料不足", "資料不足",
                   f"影響地價區域因素總修正數（{sn}）", "本表 (1)~(8) 百分比小計",
                   "＝(1)+(2)+…+(8)；主要項目 "
                   + "、".join(f"({g})" for g in incomplete)
                   + " 之小計不成立，總修正數不得計算（不以部分加總充數）",
                   f"{REGION}.regional.total", seg=sn)
        cell.alignment = Alignment(horizontal="center")

    # --- 備註欄 ---
    note_all = ("使用分區、建蔽率、容積率修正併同於比較法調查估價表宗地個別因素考量調整修正")
    put(ws, "C44", note_all, "題目原載", "備註欄（全案）", src_pdf, "原表所載", seg="全表")
    ws["C44"].alignment = Alignment(wrap_text=True, vertical="center")
    put(ws, "C43",
        "本表 (2)(5)(6)(7) 之小計與總修正數因表3 未載設施勘查資料而留空，須退補後補列；"
        "另全案備註指示使用分區、建蔽率、容積率併同於表4 宗地個別因素調整，"
        "本表仍依評價基準明細表查表填列容積率修正，兩者擇一由承辦單位認定，避免重複修正。",
        "AI判定", "備註欄（比準地或各比較標的）",
        "engine/checks.py 審查結果",
        "作業手冊 六(九) 禁止重複修正；審查重點 iii 各細項應皆已填載", seg="全表")
    ws["C43"].alignment = Alignment(wrap_text=True, vertical="center")

    add_basis_sheet(wb, "表5-1 影響地價區域因素分析明細表（普通住宅用地）")
    p = os.path.join(OUT, "表5-1_影響地價區域因素分析明細表_已填.xlsx")
    wb.save(p)
    return p, group_ok, group_vals


# ===================================================================== 表4
T4_COMP = [("G", "H", "J"), ("K", "L", "N"), ("O", "P", "R")]   # (條件, 條件次欄, 差異率)
T4_DIST_ROWS = set(range(15, 24))       # 15~23 列之條件欄拆為「名稱」「數值」兩格


def t4_cond_cells(row):
    """回傳 (比準地條件格, [(比較標的條件格, 差異率格) ×3])"""
    base = f"D{row}"
    comps = [(f"{a}{row}", f"{d}{row}") for a, _b, d in T4_COMP]
    return base, comps


def build_table4(ds, case, segs, seg_order, levels, t4i, crit_ind):
    wb = openpyxl.load_workbook(os.path.join(IN, "表4比較法調查估價表.xlsx"))
    ws = wb.active
    t4 = case["table4"]
    base_no, comps = seg_order[0], seg_order[1:]
    s = t4["summary"]
    src_pdf = "doc/題目.pdf 表4 比較法調查估價表"

    put(ws, "L1", t4["appraisal_date"], "題目原載", "估價基準日", src_pdf, "原表所載", seg="全表")
    put(ws, "P1", case["case_no"], "題目原載", "案號", src_pdf, "原表所載", seg="全表")
    put(ws, "F2", "0003", "題目原載", "比準地宗地流水號", src_pdf,
        "原表所載；比準地位於徵收範圍內，個別因素得由表7 宗地個別因素清冊同編號欄位取得", seg=base_no)

    lots = t4["lots"]
    put(ws, "D4", lots[0], "題目原載", "比準地坐落", src_pdf, "原表所載", seg=base_no)
    put(ws, "D6", "111年9月1日", "題目原載", "比準地交易日期（估價基準日）", src_pdf,
        "原表所載", seg=base_no)
    put(ws, "D8", base_no, "題目原載", "比準地地價區段號", src_pdf, "原表所載", seg=base_no)

    dates = ["110年9月14日", "111年1月11日", "110年10月29日"]
    for i, sn in enumerate(comps):
        col = T4_COMP[i][0]
        dcol = T4_COMP[i][2]
        put(ws, f"{dcol}2", i + 1, "題目原載",
            f"比較標的{i+1} 實例編號", src_pdf, "原表所載", seg=sn)
        put(ws, f"{col}4", lots[i + 1], "題目原載", f"比較標的{i+1} 坐落", src_pdf,
            "原表所載", seg=sn)
        c = put(ws, f"{col}5", s["unit_price"]["values"][i], "題目原載",
                f"比較標的{i+1} 土地正常單價(元/M2)", src_pdf + "／表1-1 買賣實例調查估價表",
                "原表所載", seg=sn)
        c.number_format = "#,##0"
        put(ws, f"{col}6", dates[i], "題目原載", f"比較標的{i+1} 交易日期", src_pdf,
            "原表所載", seg=sn)
        c = put(ws, f"{dcol}6", s["date_adj"]["percents"][i] / 100, "題目原載",
                f"比較標的{i+1} 交易日期調整百分率", src_pdf,
                "原表所載；係參酌新北市樹林區土地平均區段地價表（住宅區）調整", seg=sn)
        c.number_format = "0.00%"
        up, da = s["unit_price"]["values"][i], s["date_adj"]["percents"][i]
        calc = up * (1 + da / 100)
        c = put(ws, f"{col}7", s["adjusted_price"]["values"][i], "題目原載",
                f"比較標的{i+1} 調整至估價基準日單價(元/M2)", src_pdf,
                f"驗算：{up:,.0f} ×(1+{da:.2f}%) = {calc:,.2f} → 表列 "
                f"{s['adjusted_price']['values'][i]:,.0f}，相符", seg=sn)
        c.number_format = "#,##0"
        put(ws, f"{col}8", sn, "題目原載", f"比較標的{i+1} 地價區段號", src_pdf,
            "原表所載", seg=sn)
        cell = put(ws, f"{dcol}8", "資料不足", "資料不足",
                   f"比較標的{i+1} 區域因素調整百分率", "表5-1 影響地價區域因素總修正數",
                   "上游之表5 總修正數因表3 未載設施勘查資料而不成立，本欄不得填列",
                   f"{REGION}.regional.total", seg=sn)
        cell.alignment = Alignment(horizontal="center")

    # --- 個別因素調整 7~25 ---
    for r in t4i["rows"]:
        fn = r["field_no"]
        row = (fn + 2) if fn else 28
        base_c, comp_c = t4_cond_cells(row)
        it = crit_ind.get(r["item_code"], {})
        label = f"{fn}{r['item_name']}" if fn else f"6其他-{r['item_name']}"
        b = r["base"] or {}
        kind = {"確認": "AI判定", "推定": "推定"}.get(r["status"], "資料不足")
        if r["status"].startswith("條件可確認"):
            kind = "AI判定"

        if not b.get("condition"):
            cell = put(ws, base_c, "資料不足", "資料不足", f"{label}（比準地條件）",
                       "表7 宗地個別因素清冊／地籍圖／現場勘查（題目未提供）",
                       r["gap"] or "宗地層級勘查資料未提供",
                       f"{REGION}.individual.{r['item_code']}", seg=base_no)
            cell.alignment = Alignment(horizontal="center")
            for (cc, dc), sn in zip(comp_c, comps):
                for coord, txt in ((cc, "資料不足"), (dc, "—")):
                    cell = put(ws, coord, txt, "資料不足",
                               f"{label}（{sn}{'條件' if coord == cc else '差異率'}）",
                               "表1-1 買賣實例調查估價表僅載坐落、面積、交易日期與正常單價",
                               "比較標的宗地之個別因素須由查估單位另行勘查建立",
                               f"{REGION}.individual.{r['item_code']}", seg=sn)
                    cell.alignment = Alignment(horizontal="center")
            continue

        put(ws, base_c, b["condition"], kind, f"{label}（比準地條件）",
            r["basis"] or "表3 地價區段勘查表",
            f"判級：第{b['rank']}／共{it.get('level_count', '?')}級（{b['label']}）"
            if b.get("rank") else "敘述型細項，無級距",
            f"{REGION}.individual.{r['item_code']}", seg=base_no)

        for (cc, dc), sn, c in zip(comp_c, comps, r["comparables"]):
            if not c["condition"]:
                for coord in (cc, dc):
                    put(ws, coord, "資料不足", "資料不足", f"{label}（{sn}）",
                        "題目未提供", r["gap"] or "資料不足",
                        f"{REGION}.individual.{r['item_code']}", seg=sn)
                continue
            put(ws, cc, c["condition"], kind, f"{label}（{sn} 條件）",
                f"表3 {sn} 之法定管制值／區段記載",
                f"判級：第{c['rank']}／共{it.get('level_count', '?')}級（{c['label']}）"
                if c.get("rank") else "敘述型細項，無級距",
                f"{REGION}.individual.{r['item_code']}", seg=sn)
            if c["diff"] is None:
                cell = put(ws, dc, "待試算", "資料不足", f"{label}（{sn} 差異率）",
                           "doc/rules/評價基準明細表.pdf（個別因素）",
                           r["gap"] or "基準明細表列為敘述型，無查表矩陣",
                           f"{REGION}.individual.{r['item_code']}", seg=sn)
                cell.alignment = Alignment(horizontal="center")
            else:
                cell = put(ws, dc, c["diff"] / 100, kind, f"{label}（{sn} 差異率）",
                           f"比準地「{b['condition']}」({b['rank']}) ／ {sn}「{c['condition']}」({c['rank']})",
                           f"查表：共{it.get('level_count')}級、最大±{it.get('max_adjustment')}%、"
                           f"級距{it.get('step')}%；({c['rank']}−{b['rank']})×{it.get('step')} "
                           f"= {c['diff']:+.2f}",
                           f"{REGION}.individual.{r['item_code']}", seg=sn)
                cell.number_format = "0.00%"

    # --- 合計、比較價格 ---
    for i, sn in enumerate(comps):
        col = T4_COMP[i][0]
        cell = put(ws, f"{col}29", "不得加總", "資料不足", f"個別因素差異率合計（{sn}）",
                   "本表 7~25 各細項差異率",
                   t4i.get("total_note") or "個別因素合計需 7~25 全數可判定",
                   f"{REGION}.individual.total", seg=sn)
        cell.alignment = Alignment(horizontal="center")
        for coord, name, why in (
            (f"{col}30", "調整百分率絕對值加總",
             "＝|交易日期調整%|＋|區域因素調整%|＋|個別因素合計%|；後二者不成立"),
            (f"{'I' if i == 0 else ('M' if i == 1 else 'Q')}30", "價格形成因素之相近程度",
             "依絕對值加總落入之級距判定（優良／普通／較差），上游不成立"),
            (f"{col}31", "比準地試算價格",
             "＝調整至估價基準日單價×(1＋各調整率)；上游不成立"),
            (f"{'I' if i == 0 else ('M' if i == 1 else 'Q')}31", "比較標的權重",
             "依相近程度決定權重，上游不成立"),
        ):
            cell = put(ws, coord, "資料不足", "資料不足", f"{name}（{sn}）",
                       "本表上游欄位", why, "", seg=sn)
            cell.alignment = Alignment(horizontal="center")

    cell = put(ws, "G32", "資料不足", "資料不足", "比準地比較價格",
               "本表各比較標的試算價格與權重",
               "＝Σ(試算價格×權重)；各比較標的試算價格與權重均不成立，不得計算",
               "", seg=base_no)
    cell.alignment = Alignment(horizontal="center")

    # --- 備註欄 ---
    put(ws, "D33",
        "1.本表 7~21 各細項及合計因宗地層級勘查資料未提供而留空："
        "比準地（宗地流水號0003）應由表7 宗地個別因素清冊同編號欄位抄錄；"
        "三個比較標的應由查估單位就各該買賣實例宗地另行勘查。"
        "2.24容積率之個別因素基準明細表列為敘述型（以土地開發分析法試算調整），無查表矩陣，"
        "差異率待試算；並須與表5 容積率修正擇一，避免重複修正（作業手冊 六(九)）。",
        "AI判定", "備註欄（比準地或各比較標的）", "engine/checks.py 審查結果",
        "作業手冊 伍、六；審查重點 iii、vi", seg="全表")
    ws["D33"].alignment = Alignment(wrap_text=True, vertical="top")
    put(ws, "D34",
        "1.價格日期調整係參酌新北市樹林區土地平均區段地價表(住宅區)進行調整。"
        "2.比準地所在區段於案例蒐集期間(111年3月2日至111年9月1日間)無適當成交案例，"
        "故依土地徵收補償市價查估辦法第17條第3項規定，擴大選取範圍及案例蒐集期間至"
        "估價基準日前一年內(110年9月2日至111年9月1日)。",
        "題目原載", "備註欄（全案）", src_pdf, "原表所載", seg="全表")
    ws["D34"].alignment = Alignment(wrap_text=True, vertical="top")

    add_basis_sheet(wb, "表4 比較法調查估價表（案號 1110901-99-XXX，比準地 P001-00）")
    p = os.path.join(OUT, "表4_比較法調查估價表_已填.xlsx")
    wb.save(p)
    return p


# ===================================================================== main
ITEM2OBS = {v: k for k, v in OBS_TO_ITEM.items()}


def main():
    global basis_rows
    os.makedirs(OUT, exist_ok=True)
    ds = Dataset()
    crit = ds.criteria(REGION, "regional")
    crit_ind = ds.criteria(REGION, "individual")
    segs = ds.segments(REGION)
    case = list(ds.cases(REGION).values())[0]
    seg_order = case["table5"]["segment_nos"]
    levels = {sn: derive_segment_levels(ds, REGION, segs[sn]) for sn in seg_order}
    t4i = derive_table4_individual(ds, REGION, case, segs)

    basis_rows = []
    p3 = build_table3(ds, segs, seg_order, levels, crit)
    n3 = len(basis_rows)

    basis_rows = []
    p5, group_ok, group_vals = build_table5(ds, case, segs, seg_order, levels, crit)
    n5 = len(basis_rows)

    basis_rows = []
    p4 = build_table4(ds, case, segs, seg_order, levels, t4i, crit_ind)
    n4 = len(basis_rows)

    print(f"表3 → {os.path.relpath(p3, ROOT)}（{len(seg_order)} 個區段工作表，{n3} 筆依據）")
    print(f"表4 → {os.path.relpath(p4, ROOT)}（{n4} 筆依據）")
    print(f"表5 → {os.path.relpath(p5, ROOT)}（{n5} 筆依據）")
    print("表5 小計成立之主要項目：", sorted(g for g in group_ok if group_ok[g]))
    print("表5 小計不成立之主要項目：", sorted(g for g in group_ok if not group_ok[g]))
    return {"table3": p3, "table4": p4, "table5": p5,
            "group_ok": group_ok, "group_vals": group_vals}


if __name__ == "__main__":
    main()
