#!/usr/bin/env python3
"""output/finalVersion — 依金山區範本之填寫方式產出可交付的表3／表4／表5。

與 fourthVersion 的差別只有「填寫方式」，資料來源完全相同：

  ① 表5 (6)特殊設施、(7)環境污染 比照金山範本逐項判級：
     以表3 已填之最近設施距離查表定級，小計與總修正數因而成立；
     連帶表4 第8列「區域因素調整百分率」得以填列。
     未查得之子欄（殯儀館、火葬場、掩埋場…）仍留空，不以「無」充填。
  ② 表格本體不寫入「資料不足」「不得加總」「待試算」等狀態字樣 ——
     金山範本的未填欄位就是空白，狀態說明改由本檔輸出摘要與
     各檔「填表依據」工作表承載。
  ③ 備註欄只保留題目原載之文字，移除本專案自行加註的說明。
  ④ 表4「合計」以下（合計、絕對值加總、相近程度、試算價格、權重、
     比準地比較價格）留白：個別因素 7~11 無宗地地籍資料，合計不成立。

產出：三份 xlsx（供 Excel 檢視，保留填表依據與儲存格註解）
      三份 PDF（黑白官方樣式，engine/export_pdf.py 排版）
"""
import json
import os
import re
import sys
import tempfile

import openpyxl
from openpyxl.styles import Alignment, PatternFill

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_pdf  # noqa: E402
import export_v3 as V3  # noqa: E402
import export_v4 as V4  # noqa: E402
import export_xlsx as X  # noqa: E402

ROOT = X.ROOT
OUT = os.path.join(ROOT, "output", "finalVersion")

# 以表3 已填之最近設施判級的三個嫌惡設施細項。poi_inference 對這三項標為
# usable_for_grading=false（子欄未齊 → 推算等級為樂觀上限），本版依承辦
# 單位指示比照金山範本填列，限制寫在 README 與填表依據，不寫進表格。
GRADE_ANYWAY = ["funeral_facility", "waste_facility", "pollution"]

# 表格本體不留這些狀態字樣（金山範本的未填欄位就是空白）
PLACEHOLDERS = {"資料不足", "不得加總", "待試算", "—", "(留空)", "（留空）"}

NOFILL = PatternFill(fill_type=None)

T5_TOTAL_ROW = X.T5_TOTAL_ROW
T5_SUB_ROWS = X.T5_SUBTOTAL_ROW
T5_COLS = X.T5_SUBTOTAL_COL                       # 比較標的 1~3 之小計欄
T4_REGIONAL_CELLS = ["J8", "N8", "R8"]            # 表4 區域因素調整百分率
T4_BELOW_TOTAL = [f"{c}{r}" for r in (29, 30, 31, 32)
                  for c in ("G", "I", "K", "M", "O", "Q")]
AI_NOTE_CELLS = {"表4": ["D33"], "表5": ["C43"]}   # 本專案自行加註之備註欄


def patched_inference():
    """把三個嫌惡設施細項改為可判級，回傳暫存檔路徑。原始檔不動。"""
    inf = json.load(open(V4.INF, encoding="utf-8"))
    for code in GRADE_ANYWAY:
        cov = inf["items"][code]["coverage"]
        cov["usable_for_grading"] = True
        cov["reason"] = (cov["reason"] + "｜本版依承辦單位指示，比照金山區範本"
                                         "以已查得之最近設施判級，並於備註列明限制")
    fd, path = tempfile.mkstemp(suffix=".json", prefix="poi_inference_final_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(inf, f, ensure_ascii=False)
    return path


def anchor(ws, ref):
    """合併儲存格只有左上角可寫；非起始格回傳 None"""
    cell = ws[ref]
    if type(cell).__name__ == "MergedCell":
        for m in ws.merged_cells.ranges:
            if cell.coordinate in m:
                return ws.cell(m.min_row, m.min_col)
        return None
    return cell


def strip_placeholders(ws):
    """清掉狀態字樣與其紅色底色；回傳清掉的格數"""
    n = 0
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.strip() in PLACEHOLDERS:
                c.value = None
                c.fill = NOFILL
                n += 1
    return n


def decolor(wb, keep_sheets=()):
    """移除填表狀態底色（黑白官方樣式）。填表依據工作表的表頭保留。"""
    for ws in wb.worksheets:
        if ws.title in keep_sheets:
            continue
        for row in ws.iter_rows():
            for c in row:
                c.fill = NOFILL


# 金山範本之「條件」欄只寫設施名稱（金山國小／金山第一公墓／主要道路），
# 不寫類別前綴，也不寫資料來源標註。以下把本案的用語對齊該格式。
FUNERAL_AGG = "墓地／殯儀館／火葬場／納骨塔"
UNNAMED = "OSM 未命名圖徵"
OSM_TAG = re.compile(r"（(?:shop|amenity|landuse)=[^）]*）")


def facility_name(text, keep_type=False):
    """「類別：名稱」→「名稱」；未命名者退回類別並註明（未命名）"""
    t = OSM_TAG.sub("", str(text)).strip()
    kind, _, name = t.partition("：")
    if not name:
        kind, name = "", kind
    if UNNAMED in name or not name:
        kind = kind.replace(FUNERAL_AGG, "殯葬設施")
        return f"{kind}（未命名）" if kind else ""
    return f"{kind}：{name}" if keep_type and kind else name


T4_WORDING = {                       # 表4 列號 → 改寫方式
    15: lambda v: str(v).split("（")[0],            # 13道路種類 →「主要道路」
    17: facility_name, 18: facility_name, 19: facility_name,
    20: facility_name, 21: facility_name,
    22: facility_name,                              # 20嫌惡設施（類型／名稱）
    23: lambda v: str(v).split("（")[0],            # 21停車方便性 →「優」
}
T4_COND_COLS = ["D", "G", "K", "O"]
T4_VAL_COL = {"D": ("E", "F"), "G": ("H", "I"), "K": ("L", "M"), "O": ("P", "Q")}


def align_wording_t4(ws):
    """條件欄改為金山範本的寫法；21 停車方便性無距離級距，清掉距離欄"""
    n = 0
    for row, fn in T4_WORDING.items():
        for col in T4_COND_COLS:
            cell = ws[f"{col}{row}"]
            if not isinstance(cell.value, str):
                continue
            new = fn(cell.value)
            if new != cell.value:
                cell.value = new
                n += 1
            if row == 23:                            # 條件為敘述級距，非距離
                for c2 in T4_VAL_COL[col]:
                    ws[f"{c2}{row}"].value = None
    return n


def align_wording_t3(ws):
    """表3 設施名稱欄：移除資料來源標註"""
    n = 0
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and UNNAMED in c.value:
                c.value = (c.value.replace(FUNERAL_AGG, "殯葬設施")
                           .replace(f"（{UNNAMED}）", "（未命名）")
                           .replace(f"：{UNNAMED}", "（未命名）"))
                n += 1
    return n


def finish_table5(path):
    """補上總修正數（(1)~(8) 小計之和），清狀態字樣、移除自行加註之備註"""
    wb = openpyxl.load_workbook(path)
    ws = wb.worksheets[0]
    totals = []
    for i, col in enumerate(T5_COLS):
        vals = [ws[f"{col}{r}"].value for r in sorted(T5_SUB_ROWS.values())]
        if any(not isinstance(v, (int, float)) for v in vals):
            totals.append(None)
            continue
        t = round(sum(vals), 2)
        cell = ws[f"{col}{T5_TOTAL_ROW}"]
        cell.value = t
        cell.number_format = "0.00"
        cell.alignment = Alignment(horizontal="center")
        totals.append(t)
    for ref in AI_NOTE_CELLS["表5"]:
        anchor(ws, ref).value = None
    n = strip_placeholders(ws)
    decolor(wb, keep_sheets=("填表依據",))
    wb.save(path)
    return totals, n


def finish_table4(path, totals):
    """填入區域因素調整百分率（＝表5 總修正數），合計以下留白"""
    wb = openpyxl.load_workbook(path)
    ws = wb.worksheets[0]
    for ref, t in zip(T4_REGIONAL_CELLS, totals):
        cell = anchor(ws, ref)
        if t is None:
            cell.value = None
            continue
        cell.value = t / 100
        cell.number_format = "0.00%"
        cell.alignment = Alignment(horizontal="center")
    for ref in T4_BELOW_TOTAL:
        c = anchor(ws, ref)
        if c is not None:
            c.value = None
    for ref in AI_NOTE_CELLS["表4"]:
        anchor(ws, ref).value = None
    align_wording_t4(ws)
    n = strip_placeholders(ws)
    decolor(wb, keep_sheets=("填表依據",))
    wb.save(path)
    return n


def finish_table3(path):
    wb = openpyxl.load_workbook(path)
    sheets = [ws for ws in wb.worksheets if ws.title != "填表依據"]
    for ws in sheets:
        align_wording_t3(ws)
    n = sum(strip_placeholders(ws) for ws in sheets)
    decolor(wb, keep_sheets=("填表依據",))
    wb.save(path)
    return n


def main():
    os.makedirs(OUT, exist_ok=True)
    inf_path = patched_inference()
    orig_inf, orig_outs = V4.INF, (V3.OUT, V4.OUT, X.OUT)
    V4.INF = inf_path
    V3.OUT = V4.OUT = X.OUT = OUT
    try:
        r = V4.main()
    finally:
        V4.INF = orig_inf
        V3.OUT, V4.OUT, X.OUT = orig_outs
        os.unlink(inf_path)

    p3, p4, p5 = r["table3"], r["table4"], r["table5"]
    totals, n5 = finish_table5(p5)
    n4 = finish_table4(p4, totals)
    n3 = finish_table3(p3)
    print(f"\n表5 影響地價區域因素總修正數：{totals}")
    print(f"清除狀態字樣：表3 {n3} 格、表4 {n4} 格、表5 {n5} 格")

    pdfs = []
    for src, name in ((p3, "表3_地價區段勘查表.pdf"),
                      (p4, "表4_比較法調查估價表.pdf"),
                      (p5, "表5-1_影響地價區域因素分析明細表.pdf")):
        dst = os.path.join(OUT, name)
        pages = export_pdf.render(src, dst, skip_sheets=("填表依據",))
        pdfs.append(dst)
        print(f"PDF → {os.path.relpath(dst, ROOT)}（{pages} 頁）")
    return {"table3": p3, "table4": p4, "table5": p5, "pdfs": pdfs,
            "totals": totals}


if __name__ == "__main__":
    main()
