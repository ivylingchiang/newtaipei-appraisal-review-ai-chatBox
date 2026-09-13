# -*- coding: utf-8 -*-
"""把「完整書表」分頁的人工審查修正，套回 output/<版本>/ 的原始 xlsx。

服務端是無狀態的：讀原始 xlsx → 在記憶體套用修正 → 回傳一包 zip，
過程中不寫任何磁碟，也不改動 output/ 底下的檔案。頁面重整就回到 AI 產出。

在瀏覽器端自行組 xlsx 會丟掉底色、合併儲存格與填表依據註解，所以走這條路。
"""
import csv, io, json, os, re, zipfile
from datetime import datetime, timezone, timedelta

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Border, Side

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 過程版本（firstVersion~fourthVersion）歸檔在 output/log/ 之下
OUTPUT = os.path.join(ROOT, "output", "log")

# 只允許改這三份書表，檔名寫死在服務端；請求帶進來的東西一律不當成路徑用
FORM_FILES = {
    "t3": ("表3 地價區段勘查表", "表3_地價區段勘查表_已填.xlsx"),
    "t4": ("表4 比較法調查估價表", "表4_比較法調查估價表_已填.xlsx"),
    "t5": ("表5 影響地價區域因素分析明細表", "表5-1_影響地價區域因素分析明細表_已填.xlsx"),
}
DEFAULT_SRC = "fourthVersion"

REF_RE = re.compile(r"^[A-Z]{1,3}[1-9][0-9]{0,6}$")
SRC_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
MAX_EDITS = 2000
MAX_LEN = 32767                      # Excel 單一儲存格字數上限
TPE = timezone(timedelta(hours=8))

# 人工更正過的格加粗紅外框：不動原本的底色，填表狀態的語意才不會被蓋掉
MARK = Border(*(Side(style="medium", color="FFC00000"),) * 4)


class PatchError(ValueError):
    """請求內容不合法；訊息會直接回給前端顯示。"""


def _num(cell_value, text):
    """原本是數字的格就盡量還原成數字，否則 Excel 會把它當文字。"""
    if not isinstance(cell_value, (int, float)) or isinstance(cell_value, bool):
        return text
    t = text.strip().replace(",", "")
    if not t:
        return text
    try:
        return int(t) if re.fullmatch(r"-?\d+", t) else float(t)
    except ValueError:
        return text


def _validate(payload):
    if not isinstance(payload, dict):
        raise PatchError("請求格式不正確")
    src = payload.get("forms_src") or DEFAULT_SRC
    if not SRC_RE.match(str(src)):
        raise PatchError("書表版本名稱不合法")
    src_dir = os.path.join(OUTPUT, str(src))
    if os.path.realpath(src_dir) != os.path.join(OUTPUT, str(src)) \
            or not os.path.isdir(src_dir):
        raise PatchError(f"找不到書表版本 {src}")

    edits = payload.get("edits")
    if not isinstance(edits, list) or not edits:
        raise PatchError("沒有任何修正內容")
    if len(edits) > MAX_EDITS:
        raise PatchError(f"修正筆數過多（{len(edits)}），上限 {MAX_EDITS} 筆")

    clean = []
    for i, e in enumerate(edits, 1):
        if not isinstance(e, dict):
            raise PatchError(f"第 {i} 筆修正格式不正確")
        key, ref = e.get("file"), str(e.get("ref") or "").upper()
        if key not in FORM_FILES:
            raise PatchError(f"第 {i} 筆指向未知的書表：{key}")
        if not REF_RE.match(ref):
            raise PatchError(f"第 {i} 筆儲存格座標不合法：{e.get('ref')}")
        now = "" if e.get("now") is None else str(e["now"])
        if len(now) > MAX_LEN:
            raise PatchError(f"第 {i} 筆內容過長（{len(now)} 字）")
        clean.append({"file": key, "sheet": str(e.get("sheet") or ""), "ref": ref,
                      "was": "" if e.get("was") is None else str(e["was"]),
                      "now": now, "why": str(e.get("why") or "")})
    return str(src), clean


def _apply(src_dir, key, edits, stamp, case_no):
    """套用單一書表的修正，回傳 (檔名, xlsx bytes, 實際套用的筆數)"""
    title, fn = FORM_FILES[key]
    path = os.path.join(src_dir, fn)
    if not os.path.isfile(path):
        raise PatchError(f"找不到原始書表：{fn}")
    wb = openpyxl.load_workbook(path)

    applied = 0
    for e in edits:
        sheet = e["sheet"]
        if sheet not in wb.sheetnames:
            raise PatchError(f"{title} 沒有工作表「{sheet}」")
        ws = wb[sheet]
        try:
            cell = ws[e["ref"]]
        except (ValueError, KeyError):
            raise PatchError(f"{title} {sheet} 的座標 {e['ref']} 不存在")
        # 合併儲存格只有左上角能寫；前端輸出的座標本來就只取左上角
        if type(cell).__name__ == "MergedCell":
            raise PatchError(f"{title} {sheet} 的 {e['ref']} 是合併儲存格的非起始格")

        cell.value = _num(cell.value, e["now"])
        cell.border = MARK
        note = (f"【人工審查更正 {stamp}】\n"
                f"AI 原值：{e['was'] or '（空白）'}\n"
                f"更正為：{e['now'] or '（清空）'}"
                + (f"\n理由：{e['why']}" if e["why"] else ""))
        old = cell.comment.text if cell.comment else ""
        # 原本的填表依據要留著，人工更正接在後面
        cell.comment = Comment(f"{old}\n\n{note}" if old else note, "人工審查")
        applied += 1

    # 每份書表附一張「人工審查更正」工作表，Excel 打開就看得到改了哪些格
    ws = wb.create_sheet("人工審查更正")
    ws.append(["案號", case_no])
    ws.append(["產生時間", stamp])
    ws.append([])
    ws.append(["工作表", "儲存格", "AI 原值", "更正為", "修正理由"])
    for e in edits:
        ws.append([e["sheet"], e["ref"], e["was"], e["now"], e["why"]])
    for col, w in zip("ABCDE", (14, 10, 30, 30, 40)):
        ws.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return fn, buf.getvalue(), applied


def build_zip(payload):
    """回傳 (zip bytes, 摘要文字)。payload 為前端送來的修正清單。"""
    src, edits = _validate(payload)
    src_dir = os.path.join(OUTPUT, src)
    case_no = str(payload.get("case_no") or "")
    stamp = datetime.now(TPE).strftime("%Y-%m-%d %H:%M:%S (UTC+8)")

    by_file = {}
    for e in edits:
        by_file.setdefault(e["file"], []).append(e)

    zbuf = io.BytesIO()
    done = []
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for key, group in by_file.items():
            fn, data, n = _apply(src_dir, key, group, stamp, case_no)
            z.writestr(fn, data)
            done.append((FORM_FILES[key][0], fn, n))

        csv_buf = io.StringIO()
        w = csv.writer(csv_buf)
        w.writerow(["書表", "工作表", "儲存格", "AI原值", "更正為", "修正理由"])
        for e in edits:
            w.writerow([FORM_FILES[e["file"]][0], e["sheet"], e["ref"],
                        e["was"], e["now"], e["why"]])
        z.writestr("審查修正清單.csv", "﻿" + csv_buf.getvalue())
        z.writestr("審查修正清單.json",
                   json.dumps(payload, ensure_ascii=False, indent=2))

        lines = [f"人工審查修正後書表　{stamp}", f"案號：{case_no}",
                 f"來源版本：output/log/{src}/", "",
                 f"共 {len(edits)} 格經人工審查更正："]
        lines += [f"　・{t}（{fn}）：{n} 格" for t, fn, n in done]
        lines += ["",
                  "更正過的儲存格加了粗紅外框，並在儲存格註解裡保留 AI 原值與修正理由；",
                  "原本的填表依據註解仍在，接在人工更正說明之前。",
                  "每份 xlsx 另附「人工審查更正」工作表，列出該份書表的全部更正。",
                  "",
                  "注意：小計與總計並未重算。這三份書表的數字是 engine 推導後寫入的",
                  "靜態值，不是 Excel 公式，改了上游欄位不會自動連動。若更正的欄位會",
                  "影響小計／總修正數，請一併確認或重跑 engine。"]
        z.writestr("說明.txt", "\n".join(lines))

    summary = "；".join(f"{t} {n} 格" for t, _, n in done)
    return zbuf.getvalue(), summary
