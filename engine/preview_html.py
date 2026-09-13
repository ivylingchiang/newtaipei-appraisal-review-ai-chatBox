# -*- coding: utf-8 -*-
"""把 output/log/secondVersion 的三個已填 xlsx 轉成單一 HTML 預覽頁。

用途：本機沒有 Excel／LibreOffice 時，仍可檢視填表結果、底色與儲存格註解。
註解以滑鼠停留（title）顯示，與 Excel 中的儲存格註解內容相同。
"""
import os, html
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "output", "log",
                   os.environ.get("PREVIEW_VERSION", "secondVersion"))
FILES = [
    ("表3 地價區段勘查表", "表3_地價區段勘查表_已填.xlsx"),
    ("表5-1 影響地價區域因素分析明細表", "表5-1_影響地價區域因素分析明細表_已填.xlsx"),
    ("表4 比較法調查估價表", "表4_比較法調查估價表_已填.xlsx"),
]
LEGEND = [("題目原載", "D9EAD3"), ("AI判定", "FFF2CC"), ("推定", "FCE5CD"),
          ("資料不足", "F4CCCC"), ("不適用", "EFEFEF"),
          ("外部推算(官方A/B)", "CFE2F3"), ("外部推算(OSM C)", "E1D5E7"),
          ("覆蓋不足", "F9CB9C"), ("代理判準", "FFE599")]


def span_map(ws):
    """(row, col) → ('anchor', rowspan, colspan) 或 'skip'"""
    m = {}
    for rng in ws.merged_cells.ranges:
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                m[(r, c)] = ("skip" if (r, c) != (rng.min_row, rng.min_col)
                             else ("anchor", rng.max_row - rng.min_row + 1,
                                   rng.max_col - rng.min_col + 1))
    return m


# 「不適用」的灰格改了沒有意義，人工審查時不開放編輯；其餘有底色的格
# 都是填出來的值（AI判定／推定／外部推算／題目原載…），都可能需要更正。
NOEDIT_FILL = {"EFEFEF"}


def render_sheet(ws, max_col=None, editable=False):
    """把工作表渲染成 HTML table。

    editable=True 時額外輸出人工審查編輯所需的標記：
      table[data-sheet]  工作表名稱
      td[data-ref]       儲存格座標（如 C5），合併儲存格取左上角那一格
      td[contenteditable] 有底色且非「不適用」的格才開放改
    這些標記只加屬性，不動版面，靜態檢視時與原本完全一樣。
    """
    sm = span_map(ws)
    max_col = max_col or ws.max_column
    tag = (f'<table data-sheet="{html.escape(ws.title)}">' if editable else '<table>')
    out = [tag]
    for r in range(1, ws.max_row + 1):
        out.append("<tr>")
        for c in range(1, max_col + 1):
            info = sm.get((r, c))
            if info == "skip":
                continue
            cell = ws.cell(r, c)
            attrs, classes = [], []
            if info:
                _, rs, cs = info
                if rs > 1: attrs.append(f'rowspan="{rs}"')
                if cs > 1: attrs.append(f'colspan="{cs}"')
            rgb = cell.fill.fgColor.rgb if cell.fill and cell.fill.fgColor else None
            fill = rgb[2:] if (isinstance(rgb, str) and len(rgb) == 8
                               and rgb[2:] != "000000") else None
            if fill:
                attrs.append(f'style="background:#{fill}"')
            if cell.comment:
                attrs.append(f'title="{html.escape(cell.comment.text)}"')
                classes.append("has-note")
            if editable:
                attrs.append(f'data-ref="{cell.coordinate}"')
                if fill and fill not in NOEDIT_FILL:
                    attrs.append('contenteditable="true"')
                    classes.append("ed")
                    classes.append(f"f-{fill}")     # 供前端依填表狀態分類
            if classes:
                attrs.append(f'class="{" ".join(classes)}"')
            v = cell.value
            if v is None:
                v = ""
            elif isinstance(v, float):
                v = f"{v:,.2f}".rstrip("0").rstrip(".") if v % 1 else f"{v:,.0f}"
            txt = html.escape(str(v)).replace("\n", "<br>")
            out.append(f'<td {" ".join(attrs)}>{txt}</td>')
        out.append("</tr>")
    out.append("</table>")
    return "\n".join(out)


def main():
    parts = []
    for title, fn in FILES:
        wb = openpyxl.load_workbook(os.path.join(SRC, fn))
        parts.append(f'<h2>{html.escape(title)}<span class="fn">{html.escape(fn)}</span></h2>')
        for ws in wb.worksheets:
            if ws.title == "填表依據":
                continue
            parts.append(f'<h3>工作表：{html.escape(ws.title)}</h3>')
            parts.append('<div class="scroll">' + render_sheet(ws) + "</div>")

    legend = "".join(
        f'<span class="lg"><i style="background:#{c}"></i>{n}</span>' for n, c in LEGEND)
    doc = f"""<!doctype html><meta charset="utf-8">
<title>樹林區 表3／表4／表5 填表預覽</title>
<style>
 body{{font:13px/1.5 -apple-system,"PingFang TC",sans-serif;margin:24px;background:#fafafa;color:#222}}
 h1{{font-size:20px}} h2{{font-size:16px;margin-top:32px;border-bottom:2px solid #333;padding-bottom:4px}}
 h3{{font-size:13px;color:#666;margin:14px 0 6px}}
 .fn{{font-weight:400;font-size:11px;color:#888;margin-left:10px}}
 .scroll{{overflow-x:auto;background:#fff;border:1px solid #ddd}}
 table{{border-collapse:collapse;font-size:11px;white-space:nowrap}}
 td{{border:1px solid #c8c8c8;padding:2px 5px;vertical-align:middle;max-width:340px;
     overflow:hidden;text-overflow:ellipsis}}
 td.has-note{{cursor:help}}
 .lg{{display:inline-flex;align-items:center;margin-right:14px;font-size:12px}}
 .lg i{{width:14px;height:14px;border:1px solid #999;margin-right:5px;display:inline-block}}
 .note{{background:#fff;border-left:3px solid #888;padding:8px 12px;margin:12px 0;font-size:12px}}
</style>
<h1>新北市樹林區（普通住宅用地）　表3／表4／表5 填表預覽</h1>
<p>案號 1110901-99-XXX　比準地 P001-00　比較標的 P002-00／P003-00／P004-00</p>
<p>{legend}</p>
<div class="note">本頁僅為 <code>output/{os.path.basename(SRC)}/</code> 三個 xlsx 的畫面預覽，
正式交付檔仍為 Excel。有底色的儲存格把滑鼠移上去可看到填表依據（與 Excel 內的儲存格註解相同）。
逐格依據明細請看各 xlsx 的「填表依據」工作表。</div>
{''.join(parts)}
"""
    p = os.path.join(SRC, "預覽.html")
    open(p, "w", encoding="utf-8").write(doc)
    print("→", os.path.relpath(p, ROOT))
    return p


if __name__ == "__main__":
    main()
