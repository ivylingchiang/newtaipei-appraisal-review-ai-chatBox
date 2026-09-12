# -*- coding: utf-8 -*-
"""fourthVersion 表單預覽 Artifact：表4 個別因素補填總覽 ＋ 三張表逐格可點看填表依據。

與 export_artifact_html.py（v3）的差別：
  ① 讀 output/fourthVersion；② 新增「代理判準」底色；
  ③ 表4 置於首頁籤並加上 13~21 補填總覽（直接由 xlsx 儲存格與註解反算，不手寫數字）。
"""
import json, html, os, re, collections
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "output/fourthVersion")
INF = json.load(open(os.path.join(ROOT, "datasets/external/poi_inference.json"),
                     encoding="utf-8"))
E = lambda s: html.escape(str(s) if s is not None else "")

# Excel 底色 → (代號, 顯示名, 說明)
KIND = {
    "D9EAD3": ("orig", "題目原載", "doc/題目.pdf 原已載明之勘查事實或價格，逕予抄錄"),
    "FFF2CC": ("ai", "AI判定", "題目事實 × 評價基準明細表查表，無估算成分"),
    "FCE5CD": ("pres", "推定", "以區段層級記載推定至宗地層級，未經個別勘查"),
    "CFE2F3": ("ext", "外部推算 · 官方", "開放資料推算，官方名冊來源（信心 A／B）"),
    "E1D5E7": ("osm", "外部推算 · OSM", "僅 OpenStreetMap 群眾協作（信心 C）"),
    "FFE599": ("prox", "代理判準", "級距或設施定義由本專案代設（商圈、停車方便性）"),
    "F9CB9C": ("blk", "覆蓋不足", "嫌惡設施子欄缺漏，推算值僅為樂觀上限"),
    "F4CCCC": ("gap", "資料不足", "應填而無可用資料，留白並列為退補事項"),
    "EFEFEF": ("na", "不適用", "普通住宅用地之評價基準明細表無此修正細項"),
}

SHEETS = [                                   # 表4 置首：v4 的改動全在表4
    ("表4_比較法調查估價表_已填.xlsx", "表4 比較法調查估價表", False),
    ("表5-1_影響地價區域因素分析明細表_已填.xlsx", "表5-1 區域因素分析明細表", False),
    ("表3_地價區段勘查表_已填.xlsx", "表3 地價區段勘查表", True),
]
SEGS = ["P001-00", "P002-00", "P003-00", "P004-00"]
# 表4 個別因素列 → (excel 列號, 是否有距離數值欄)
T4_ROWS = [(13, 15), (14, 16), (15, 17), (16, 18), (17, 19),
           (18, 20), (19, 21), (20, 22), (21, 23)]
COND_COLS = ["D", "G", "K", "O"]             # 比準地 + 三個比較標的
VAL_COLS = ["E", "H", "L", "P"]
DIFF_COLS = [None, "J", "N", "R"]


def kind_of(cell):
    rgb = cell.fill.fgColor.rgb if cell.fill and cell.fill.fgColor else None
    if isinstance(rgb, str) and len(rgb) == 8 and rgb[2:] in KIND:
        return KIND[rgb[2:]][0]
    return ""


def rank_of(cell):
    m = re.search(r"判級：第(\d+)／共(\d+)級（(.+?)）", cell.comment.text if cell.comment else "")
    return (f"第{m.group(1)}／{m.group(2)}級 {m.group(3)}") if m else ""


def t4_summary(ws):
    """由表4 工作表反算 13~21 的補填總覽（值與等級都取自實際儲存格）"""
    rows = []
    for field_no, r in T4_ROWS:
        name = re.sub(r"^\d+", "", str(ws[f"C{r}"].value or "")).strip()
        cells = []
        for i, (cc, vc, dc) in enumerate(zip(COND_COLS, VAL_COLS, DIFF_COLS)):
            c = ws[f"{cc}{r}"]
            v = ws[f"{vc}{r}"].value
            d = ws[f"{dc}{r}"].value if dc else None
            cells.append({
                "cond": c.value, "val": v, "kind": kind_of(c), "rank": rank_of(c),
                "diff": (f"{d * 100:+.2f}%" if isinstance(d, float) else
                         (E(d) if d else "")),
                "sign": ("z" if abs(d) < 1e-9 else ("dn" if d < 0 else "up"))
                        if isinstance(d, float) else "",
            })
        rows.append({"no": field_no, "name": name, "cells": cells})
    return rows


def spans(ws):
    m = {}
    for rg in ws.merged_cells.ranges:
        for r in range(rg.min_row, rg.max_row + 1):
            for c in range(rg.min_col, rg.max_col + 1):
                m[(r, c)] = ("skip" if (r, c) != (rg.min_row, rg.min_col)
                             else (rg.max_row - rg.min_row + 1,
                                   rg.max_col - rg.min_col + 1))
    return m


def render(ws, notes):
    sm = spans(ws)
    counts = collections.Counter()
    out = ['<table class="xl">']
    for r in range(1, ws.max_row + 1):
        out.append("<tr>")
        for c in range(1, ws.max_column + 1):
            info = sm.get((r, c))
            if info == "skip":
                continue
            cell = ws.cell(r, c)
            a = []
            if info:
                rs, cs = info
                if rs > 1: a.append(f'rowspan="{rs}"')
                if cs > 1: a.append(f'colspan="{cs}"')
            klass = []
            k = kind_of(cell)
            if k:
                klass.append("k-" + k)
                counts[k] += 1
            if cell.comment:
                nid = len(notes)
                notes.append(cell.comment.text)
                a.append(f'data-n="{nid}"')
                klass.append("hn")
            if klass:
                a.append(f'class="{" ".join(klass)}"')
            a.append(f'data-ref="{cell.coordinate}"')
            v = cell.value
            if v is None:
                v = ""
            elif isinstance(v, float):
                v = (f"{v * 100:+.2f}%" if cell.number_format == "0.00%"
                     else (f"{v:,.2f}".rstrip("0").rstrip(".") if v % 1 else f"{v:,.0f}"))
            out.append(f'<td {" ".join(a)}>{E(v).replace(chr(10), "<br>")}</td>')
        out.append("</tr>")
    out.append("</table>")
    return "\n".join(out), counts


notes, panels, tabs, summary = [], [], [], None
first = True
for fn, title, per_seg in SHEETS:
    wb = openpyxl.load_workbook(os.path.join(SRC, fn))
    for ws in wb.worksheets:
        if ws.title == "填表依據":
            continue
        if summary is None and fn.startswith("表4"):
            summary = t4_summary(ws)
        tid = f"t{len(tabs)}"
        label = ws.title if per_seg else title.split()[0]
        sub = title if not per_seg else "表3 地價區段勘查表"
        tbl, cnt = render(ws, notes)
        chips = "".join(
            f'<span class="chip k-{k}">'
            f'{E([KIND[h][1] for h in KIND if KIND[h][0] == k][0])}<b>{n}</b></span>'
            for k, n in sorted(cnt.items(), key=lambda kv: -kv[1]))
        tabs.append(f'<button class="tab{" on" if first else ""}" data-t="{tid}" '
                    f'role="tab" aria-selected="{"true" if first else "false"}" '
                    f'aria-controls="{tid}" id="tb-{tid}">'
                    f'<b>{E(label)}</b><i>{E(sub)}</i></button>')
        panels.append(f'<section class="pane{" on" if first else ""}" id="{tid}" '
                      f'role="tabpanel" aria-labelledby="tb-{tid}"'
                      f'{"" if first else " hidden"}>'
                      f'<div class="chips">{chips}</div>'
                      f'<div class="scroll">{tbl}</div></section>')
        first = False

NOTES_JSON = json.dumps(notes, ensure_ascii=False)

legend = "".join(
    f'<span class="lg k-{k}"><i></i><b>{E(nm)}</b><em>{E(desc)}</em></span>'
    for hexv, (k, nm, desc) in KIND.items())

segstrip = "".join(
    f'<div class="sg{" bench" if s == "P001-00" else ""}"><b>{s}</b>'
    f'<span class="xy">{INF["segments"][s]["center_twd97"][0]:,.0f} · '
    f'{INF["segments"][s]["center_twd97"][1]:,.0f}</span>'
    f'<span class="un">±{INF["segments"][s]["uncertainty_m"]:g} m</span></div>'
    for s in SEGS)

# ---- 補填總覽表 -------------------------------------------------------------
srows = []
for row in summary:
    tds = []
    for i, c in enumerate(row["cells"]):
        val = (f'<span class="m">{c["val"]:,.0f}<em> M</em></span>'
               if isinstance(c["val"], (int, float)) else "")
        diff = (f'<span class="df {c["sign"]}">{c["diff"]}</span>'
                if c["diff"] else "")
        tds.append(
            f'<td class="k-{c["kind"]}">'
            f'<span class="cn">{E(c["cond"])}</span>{val}'
            f'<span class="rk">{E(c["rank"])}</span>{diff}</td>')
    srows.append(f'<tr><th><span class="no">{row["no"]}</span>{E(row["name"])}</th>'
                 + "".join(tds) + "</tr>")
SUMMARY = (
    '<div class="scroll sm"><table class="sum">'
    '<thead><tr><th>個別因素細項</th>'
    + "".join(f'<th>{s}{"<em>比準地</em>" if s == "P001-00" else "<em>比較標的</em>"}</th>'
              for s in SEGS)
    + "</tr></thead><tbody>" + "".join(srows) + "</tbody></table></div>")

CSS = """
:root{
 --ground:#F5F7F3;--surface:#FFFFFF;--sunk:#EAEEE7;
 --ink:#19211C;--ink2:#3C4842;--muted:#6B776F;--faint:#93A098;
 --rule:#D5DCD2;--rule2:#BFC9BB;--accent:#0E5C4A;--accent-w:#E1EDE8;
 --k-orig:#D9EAD3;--k-ai:#FFF2CC;--k-pres:#FCE5CD;--k-ext:#CFE2F3;
 --k-osm:#E1D5E7;--k-prox:#FFE599;--k-blk:#F9CB9C;--k-gap:#F4CCCC;--k-na:#EFEFEF;
 --cell-ink:#19211C;--blk:#B26A1F;--up:#8A3324;--dn:#0E5C4A;
 --shadow:0 1px 2px rgba(25,33,28,.07),0 6px 20px rgba(25,33,28,.06);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
 --ground:#111614;--surface:#191F1B;--sunk:#222A25;
 --ink:#E8EDE7;--ink2:#C2CCC4;--muted:#93A099;--faint:#6C7872;
 --rule:#2C352E;--rule2:#3C4740;--accent:#63BFA3;--accent-w:#1D2C26;
 --k-orig:#2E4A2C;--k-ai:#4D4422;--k-pres:#4E3A25;--k-ext:#24445C;
 --k-osm:#3E3352;--k-prox:#5A4A18;--k-blk:#59391A;--k-gap:#542B28;--k-na:#2A322C;
 --cell-ink:#EAEFE9;--blk:#E0A05A;--up:#E08D7A;--dn:#63BFA3;
 --shadow:0 1px 2px rgba(0,0,0,.5),0 6px 20px rgba(0,0,0,.35);
}}
:root[data-theme="dark"]{
 --ground:#111614;--surface:#191F1B;--sunk:#222A25;
 --ink:#E8EDE7;--ink2:#C2CCC4;--muted:#93A099;--faint:#6C7872;
 --rule:#2C352E;--rule2:#3C4740;--accent:#63BFA3;--accent-w:#1D2C26;
 --k-orig:#2E4A2C;--k-ai:#4D4422;--k-pres:#4E3A25;--k-ext:#24445C;
 --k-osm:#3E3352;--k-prox:#5A4A18;--k-blk:#59391A;--k-gap:#542B28;--k-na:#2A322C;
 --cell-ink:#EAEFE9;--blk:#E0A05A;--up:#E08D7A;--dn:#63BFA3;
 --shadow:0 1px 2px rgba(0,0,0,.5),0 6px 20px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{background:var(--ground);color:var(--ink);margin:0;
 font:15px/1.7 "Noto Sans TC",-apple-system,"PingFang TC","Microsoft JhengHei",sans-serif;
 -webkit-font-smoothing:antialiased}
.wrap{max-width:1320px;margin:0 auto;padding-inline:18px}
h1,h2{font-family:"Noto Serif TC",serif;margin:0;text-wrap:balance}
.mono,code,.xy,.un,.chip b,.lg b,.m,.df,.no{font-family:"IBM Plex Mono",ui-monospace,monospace;
 font-variant-numeric:tabular-nums}

.mast{padding-block:30px 0}
.eyebrow{font-size:11px;letter-spacing:.22em;color:var(--accent);font-weight:700;
 margin-bottom:9px}
.mast h1{font-size:clamp(23px,3.6vw,32px);line-height:1.3;font-weight:700}
.mast p{color:var(--ink2);max-width:66ch;margin:11px 0 0;font-size:14.5px}
.warn{margin-top:18px;background:var(--surface);border:1px solid var(--rule2);
 border-left:4px solid var(--blk);padding:13px 17px;font-size:13.5px;color:var(--ink2);
 line-height:1.7}
.warn b{color:var(--ink)}

.segs{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}
.sg{background:var(--surface);border:1px solid var(--rule);padding:7px 13px;
 display:flex;gap:11px;align-items:baseline;font-size:12px}
.sg.bench{border-color:var(--accent);box-shadow:inset 3px 0 0 var(--accent)}
.sg b{font-family:"IBM Plex Mono",monospace;font-size:12.5px}
.sg .xy{color:var(--muted);font-size:11.5px}
.sg .un{color:var(--accent);font-weight:600;font-size:11.5px}

h2.sec{font-size:17px;margin-top:34px;display:flex;align-items:baseline;gap:11px;
 border-bottom:2px solid var(--rule2);padding-bottom:7px}
h2.sec em{font-style:normal;font-size:12px;color:var(--muted);font-family:"Noto Sans TC",sans-serif;
 font-weight:400}

.scroll{overflow-x:auto;background:var(--surface);border:1px solid var(--rule2);
 box-shadow:var(--shadow)}
.scroll.sm{margin-top:13px}
table.sum{border-collapse:collapse;width:100%;font-size:12.5px}
table.sum th{text-align:left;font-weight:600;border:1px solid var(--rule);
 padding:7px 10px;background:var(--sunk);white-space:nowrap;vertical-align:baseline}
table.sum thead th{font-size:12px;font-family:"IBM Plex Mono",monospace}
table.sum thead th em{display:block;font-style:normal;font-size:10.5px;color:var(--muted);
 font-family:"Noto Sans TC",sans-serif;letter-spacing:.05em}
table.sum tbody th{font-weight:500;font-size:13px}
table.sum tbody th .no{display:inline-block;min-width:22px;color:var(--accent);
 font-size:11.5px;font-weight:600}
table.sum td{border:1px solid var(--rule);padding:7px 10px;vertical-align:top;
 color:var(--cell-ink);min-width:148px}
.cn{display:block;font-size:12px;line-height:1.45}
.m{display:block;font-size:15px;font-weight:600;margin-top:2px}
.m em{font-style:normal;font-size:10px;color:var(--muted);font-weight:400}
.rk{display:block;font-size:10.5px;color:var(--muted);letter-spacing:.03em}
.df{display:inline-block;margin-top:5px;font-size:13px;font-weight:600;color:var(--ink2)}
.df.up{color:var(--up)} .df.dn{color:var(--dn)}
.df.z{color:var(--faint);font-weight:400}
td.k-orig{background:var(--k-orig)} td.k-ai{background:var(--k-ai)}
td.k-pres{background:var(--k-pres)} td.k-ext{background:var(--k-ext)}
td.k-osm{background:var(--k-osm)} td.k-prox{background:var(--k-prox)}
td.k-blk{background:var(--k-blk)} td.k-gap{background:var(--k-gap)}
td.k-na{background:var(--k-na)}

.gaps{display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));
 margin-top:13px}
.gp{background:var(--surface);border:1px solid var(--rule);border-left:3px solid var(--k-gap);
 padding:9px 13px;font-size:12.5px;line-height:1.6}
.gp b{display:block;font-size:12.5px;color:var(--ink)}
.gp span{color:var(--muted);font-size:11.5px}

.legend{display:grid;gap:6px;grid-template-columns:repeat(auto-fit,minmax(226px,1fr));
 margin-top:16px}
.lg{display:flex;align-items:baseline;gap:8px;font-size:12px;background:var(--surface);
 border:1px solid var(--rule);padding:6px 10px;line-height:1.5}
.lg i{width:12px;height:12px;flex:none;border:1px solid var(--rule2);display:block;
 position:relative;top:2px}
.lg b{font-size:11.5px;white-space:nowrap;font-weight:600}
.lg em{font-style:normal;color:var(--faint);font-size:11px}
.lg.k-orig i{background:var(--k-orig)} .lg.k-ai i{background:var(--k-ai)}
.lg.k-pres i{background:var(--k-pres)} .lg.k-ext i{background:var(--k-ext)}
.lg.k-osm i{background:var(--k-osm)} .lg.k-prox i{background:var(--k-prox)}
.lg.k-blk i{background:var(--k-blk)} .lg.k-gap i{background:var(--k-gap)}
.lg.k-na i{background:var(--k-na)}

.tabs{display:flex;margin-top:13px;border-bottom:2px solid var(--rule2);
 overflow-x:auto;scrollbar-width:thin}
.tab{background:none;border:0;border-bottom:2px solid transparent;margin-bottom:-2px;
 padding:9px 15px;cursor:pointer;color:var(--muted);font-family:inherit;
 display:flex;flex-direction:column;align-items:flex-start;white-space:nowrap;
 line-height:1.35}
.tab b{font-family:"IBM Plex Mono",monospace;font-size:13.5px;font-weight:600}
.tab i{font-style:normal;font-size:10.5px;letter-spacing:.05em}
.tab:hover{color:var(--ink)}
.tab.on{color:var(--accent);border-bottom-color:var(--accent)}
.tab:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}

.pane{margin-top:14px}
.pane[hidden]{display:none}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.chip{font-size:11px;padding:2px 9px;border:1px solid var(--rule2);display:inline-flex;
 gap:6px;align-items:baseline;color:var(--ink2)}
.chip b{font-size:11.5px}
.chip.k-orig{background:var(--k-orig)} .chip.k-ai{background:var(--k-ai)}
.chip.k-pres{background:var(--k-pres)} .chip.k-ext{background:var(--k-ext)}
.chip.k-osm{background:var(--k-osm)} .chip.k-prox{background:var(--k-prox)}
.chip.k-blk{background:var(--k-blk)} .chip.k-gap{background:var(--k-gap)}
.chip.k-na{background:var(--k-na)}

table.xl{border-collapse:collapse;font-size:11px;white-space:nowrap;color:var(--cell-ink)}
table.xl td{border:1px solid var(--rule);padding:3px 6px;vertical-align:middle;
 max-width:330px;overflow:hidden;text-overflow:ellipsis;line-height:1.5}
table.xl td.hn{cursor:pointer;position:relative}
table.xl td.hn::after{content:"";position:absolute;top:1px;right:1px;width:0;height:0;
 border-top:5px solid var(--accent);border-left:5px solid transparent}
table.xl td.sel{outline:2px solid var(--accent);outline-offset:-2px}

.panel{position:sticky;bottom:0;background:var(--surface);border-top:2px solid var(--accent);
 box-shadow:0 -4px 18px rgba(0,0,0,.1);padding:13px 18px;z-index:5}
.panel .ph{display:flex;gap:11px;align-items:baseline;margin-bottom:6px}
.panel .ref{font-family:"IBM Plex Mono",monospace;font-size:12px;background:var(--accent);
 color:var(--ground);padding:1px 8px;font-weight:600}
.panel .hint{color:var(--faint);font-size:12px}
.panel pre{margin:0;white-space:pre-wrap;font-size:12.5px;line-height:1.75;
 font-family:inherit;color:var(--ink2);max-height:148px;overflow-y:auto}
.panel button.x{margin-left:auto;background:none;border:1px solid var(--rule2);
 color:var(--muted);cursor:pointer;font-size:11px;padding:2px 9px;font-family:inherit}

footer{margin-top:34px;padding-block:18px 40px;border-top:1px solid var(--rule2);
 font-size:11.5px;color:var(--faint);line-height:1.9}
footer code{font-size:11px}
@media (max-width:640px){
 .legend{grid-template-columns:1fr} .lg em{display:none}
 .panel pre{max-height:110px}
 table.sum td{min-width:136px}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

JS = """
const NOTES=%s;
const tabs=[...document.querySelectorAll('.tab')];
tabs.forEach(t=>t.addEventListener('click',()=>{
 tabs.forEach(o=>{o.classList.toggle('on',o===t);o.setAttribute('aria-selected',o===t);});
 document.querySelectorAll('.pane').forEach(p=>{
  const on=p.id===t.dataset.t; p.classList.toggle('on',on); p.hidden=!on;});
}));
const panel=document.getElementById('panel'),pref=document.getElementById('pref'),
      ptxt=document.getElementById('ptxt');
let sel=null;
document.addEventListener('click',ev=>{
 const td=ev.target.closest('td.hn'); if(!td)return;
 if(sel)sel.classList.remove('sel'); sel=td; td.classList.add('sel');
 pref.textContent=td.dataset.ref; ptxt.textContent=NOTES[+td.dataset.n];
 panel.hidden=false;
});
document.getElementById('pclose').addEventListener('click',()=>{
 panel.hidden=true; if(sel){sel.classList.remove('sel');sel=null;}
});
""" % NOTES_JSON

GAPS = [
    ("7 面積、8 寬度、9 深度、10 形狀、11 臨街情形",
     "需 4 筆地號的宗地多邊形（地籍圖 WFS／表7 宗地個別因素清冊）"),
    ("24 容積率差異率", "基準明細表列為敘述型，須以土地開發分析法試算"),
    ("個別因素合計（第29列）", "需 7~25 全數可判定，故仍填「不得加總」"),
    ("區域因素調整百分率、試算價格、比準地比較價格",
     "上游之表5 總修正數因特殊設施(6)、環境污染(7) 覆蓋不足而不成立"),
]
gaps = "".join(f'<div class="gp"><b>{E(a)}</b><span>{E(b)}</span></div>' for a, b in GAPS)

DOC = f"""<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;600;700&family=Noto+Serif+TC:wght@600;700&family=IBM+Plex+Mono:wght@400;600&display=swap">
<title>樹林區表4 個別因素補填</title>
<style>{CSS}</style>
<div class="wrap">
<div class="mast">
 <div class="eyebrow">OUTPUT / FOURTHVERSION　·　新北市樹林區　普通住宅用地　案號 1110901-99-XXX</div>
 <h1>表4 個別因素 13~21 補填結果</h1>
 <p>表4「個別因素調整」原本 7~21 全部留白。本版以<b>表3 地價區段勘查表已載的主要道路</b>
 與<b>開放資料推算的設施距離</b>補填 13~21 共 9 個細項，可判定細項由 4 項增為 13 項。
 <b>有底色的格子點一下，頁面下方會顯示該格的填表依據</b>（與 Excel 儲存格註解相同）。</p>
 <div class="warn"><b>13~21 是「區段層級推定到宗地層級」，不是宗地個別勘查。</b>
 道路條件用的是<b>區段主要道路</b>而非該宗地的面前道路；接近條件的距離自<b>區段中心點</b>
 （±25~66 m）起算的<b>直線距離</b>，非自宗地起算、亦非路線距離，因此系統性高估便利性。
 同一區段內所有宗地會得到相同的值 —— 本表可作外業前的候選值與審查合理性檢核，
 <b>不得逕行送件</b>。</div>
 <div class="segs">{segstrip}</div>
</div>

<h2 class="sec">個別因素補填總覽<em>底色＝信心等級　·　數值下方為差異率，正值代表比較標的條件較差</em></h2>
{SUMMARY}

<h2 class="sec">仍不能算的部分<em>四項缺口，順序即補齊的先後</em></h2>
<div class="gaps">{gaps}</div>

<h2 class="sec">三張表完整內容<em>共 {len(notes)} 格附填表依據，點擊即可展開</em></h2>
<div class="legend">{legend}</div>
<div class="tabs" role="tablist">{''.join(tabs)}</div>
{''.join(panels)}

<footer>
 表3、表5-1 與 thirdVersion 相同，本版只動表4。19 個開放資料來源 ＋ OpenStreetMap；
 區段中心點由界街幾何交會求得，不確定半徑 25–66 m。<br>
 級距與修正矩陣：新北市樹林區普通住宅用地影響地價個別因素評價基準明細表　·
 填表規範：內政部土地徵收補償市價查估作業手冊（104年3月）<br>
 產出：<code>engine/export_v4.py</code>　·　逐格明細見各 xlsx 的「填表依據」工作表　·
 推算日期 {INF['generated_at']}
</footer>
</div>

<div class="panel" id="panel" hidden>
 <div class="ph"><span class="ref" id="pref">—</span>
  <span class="hint">填表依據</span>
  <button class="x" id="pclose">關閉</button></div>
 <pre id="ptxt"></pre>
</div>
<script>{JS}</script>
"""
out = os.environ.get("OUT_HTML") or os.path.join(SRC, "artifact_單檔預覽.html")
open(out, "w", encoding="utf-8").write(DOC)
print("→", os.path.relpath(out, ROOT), f"{len(DOC)/1024:.0f} KB",
      "| notes:", len(notes), "| panes:", len(panels))
