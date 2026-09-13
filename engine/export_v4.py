#!/usr/bin/env python3
"""output/fourthVersion — 表4 個別因素 13~21 改以表3 記載與開放資料推算補填。

v3 → v4 的唯一差別在**表4**（表3、表5 與 v3 完全相同）：

| 表4 細項 | v3 | v4 | 來源 |
|---|---|---|---|
| 13 道路種類 | 資料不足 | 主要道路（名稱） | 表3 交通運輸「主要道路」 |
| 14 面前道路寬度 | 資料不足 | 寬度 M | 表3 交通運輸「主要道路」寬度 |
| 15~18 接近學校／市場／公園／車站 | 資料不足 | 設施名稱＋距離 | 表3 設施欄（區段中心直線距離） |
| 19 接近商圈 | 資料不足 | 零售聚集點＋距離 | OSM 代理判準 |
| 20 嫌惡設施 | 資料不足 | 最近嫌惡設施＋距離 | 表3 特殊設施／環境污染欄 |
| 21 停車方便性 | 資料不足 | 優／普通／劣 | 路外公共停車場距離 → 代理判準 |

⚠️ 13~21 全部是**區段層級資料推定至宗地層級**，不是宗地個別勘查：
   - 道路條件用的是「區段主要道路」，不是該宗地的面前道路；
   - 接近條件的距離自**區段中心點**起算，不是自宗地起算；
   - 同一區段內所有宗地會得到相同的值。
   底色即為信心等級，詳見 output/fourthVersion/README.md §0。
   7~12（面積、寬度、深度、形狀、臨街情形）仍無來源，故合計與試算價格仍不予產出。
"""
import os, sys, json, math

import openpyxl
from openpyxl.styles import PatternFill, Alignment

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_xlsx as X
import export_v3 as V3
import poi_infer as PI
from loader import Dataset
from compute import derive_segment_levels, derive_table4_individual
from grading import grade, adjust, Ungradable

ROOT = X.ROOT
OUT = os.path.join(ROOT, "output", "log", "fourthVersion")
INF = os.path.join(ROOT, "datasets", "external", "poi_inference.json")
REGION = X.REGION
os.makedirs(OUT, exist_ok=True)
X.OUT = OUT
V3.OUT = OUT

# ------------------------------------------------ 新增底色：代理判準（信心最低）
X.FILL["代理判準"] = PatternFill("solid", fgColor="FFE599")   # 金：級距或設施定義由本專案代理
X.LEGEND = X.LEGEND + [
    ("代理判準", "FFE599", "基準明細表之級距為敘述型（如『停車方便性優』）或該細項無官方"
                          "設施定義（如『商圈』），級距門檻由本專案代理設定，屬判準推估"),
]

# 信心由高至低；差異率格取兩端較低者
CONF_ORDER = ["題目原載", "AI判定", "推定", "外部推算", "外部推算OSM", "代理判準",
              "覆蓋不足", "資料不足"]


def worse(a, b):
    return a if CONF_ORDER.index(a) >= CONF_ORDER.index(b) else b


def conf_kind(conf):
    return "外部推算" if conf in ("A", "B") else "外部推算OSM"


# =============================================== 表4 個別因素 13~21 的外部來源
# 區段中心距離取自表3 已填之推算值（datasets/external/poi_inference.json），
# 與表3 同一組數字，確保兩表一致。
POI_ITEM = {                       # 表4 個別因素 → poi_inference 之區域因素細項
    "near_school": "near_school",
    "near_market": "near_market",
    "near_park": "near_park",
    "near_station": "near_station",
}
NUISANCE_ITEMS = ["utility_facility", "funeral_facility", "waste_facility", "pollution"]

# 21 停車方便性：基準明細表僅列「優／普通／劣」三級敘述，無距離門檻。
# 本專案以表4 接近條件群組共用之 250m／500m 門檻代理，屬判準推估（信心最低）。
PARKING_BANDS = [(250, "停車方便性優"), (500, "停車方便性普通"), (None, "停車方便性劣")]
PARKING_RULE = ("代理判準：基準明細表『停車方便性』為敘述型三級，無距離門檻；"
                "本專案以同表接近條件群組之 250m／500m 門檻代理："
                "未滿250m＝優、250~500m＝普通、500m以上＝劣")

# 19 接近商圈：18 個開放資料來源均無「商圈」定義或範圍圖。
# 以 OSM 零售聚集點（shop=mall／department_store 或 landuse=retail，含夜市、黃昏市場）
# 之最近者代理，屬判準推估（信心最低）。
BUSINESS_PRED = (lambda t: t.get("shop") in ("mall", "department_store")
                 or t.get("landuse") == "retail")
BUSINESS_RULE = ("代理判準：本案 18 個開放資料來源均無商圈範圍或名冊；"
                 "以 OSM 零售聚集點（shop=mall／department_store 或 landuse=retail）"
                 "最近者代理，非官方商圈認定")


def business_pts():
    """OSM 零售聚集點（商圈代理）"""
    return PI._osm_pts(BUSINESS_PRED)


def _fname(agg):
    """OSM 未命名圖徵不得以『(未命名)』入表，改標示其來源性質"""
    if agg["facility"] in ("(未命名)", "（未命名）"):
        return "OSM 未命名圖徵"
    return agg["facility"]


def _rec(name, value, arg, kind, source, basis):
    return {"name": name, "value": value, "arg": arg, "kind": kind,
            "source": source, "basis": basis}


def build_individual_ext(segs, seg_order, inf, crit_ind):
    """回傳 {item_code: {segment_no: rec}}；rec 為表4 條件欄之外部補填內容"""
    ext = {c: {} for c in ("road_type", "front_road_width", "near_business",
                           "nuisance", "parking_ease", *POI_ITEM)}
    bp = business_pts()

    for sn in seg_order:
        seg = segs[sn]
        sc = inf["segments"][sn]
        cx, cy = sc["center_twd97"]
        geo = (f"區段中心 TWD97 ({cx:.0f}, {cy:.0f}) ±{sc['uncertainty_m']:.0f}m"
               f"（由 OSM 界街交會點求得）")
        mr = (seg.get("observations") or {}).get("main_road") or {}

        # --- 13 道路種類：表3 主要道路 ---------------------------------------
        if mr.get("road_name"):
            ext["road_type"][sn] = _rec(
                f"主要道路（{mr['road_name']}）", None, {"category": "主要道路"}, "推定",
                f"表3 {sn} 交通運輸「主要道路」：{mr['raw']}",
                "表3 所載之區段主要道路推定為宗地面前道路種類；"
                "宗地實際面前道路可能為次要道路或巷道，須以現場勘查為準")

        # --- 14 面前道路寬度：表3 主要道路寬度 -------------------------------
        if mr.get("value") is not None:
            ext["front_road_width"][sn] = _rec(
                mr.get("road_name"), mr["value"], {"value": mr["value"]}, "推定",
                f"表3 {sn} 交通運輸「主要道路」：{mr['raw']}",
                "表3 所載之區段主要道路寬度推定為宗地面前道路寬度；"
                f"區段內道路平均寬度為 "
                f"{((seg.get('observations') or {}).get('avg_road_width') or {}).get('raw')}，"
                "宗地若臨巷道則實際寬度較小，須以現場勘查為準")

        # --- 15~18 接近條件：表3 設施欄之推算距離 ----------------------------
        for code, poi_code in POI_ITEM.items():
            it = inf["items"][poi_code]
            agg = (it["by_segment"].get(sn) or {}).get("aggregated")
            if not agg:
                continue
            kind = conf_kind(agg["confidence"])
            if not it["coverage"]["usable_for_grading"]:
                kind = "覆蓋不足"
            ext[code][sn] = _rec(
                f"{agg['sub']}：{_fname(agg)}", agg["distance_m"],
                {"value": agg["distance_m"]}, kind,
                f"表3 {sn}「{it['label']}」推算值／{agg['source']}（信心 {agg['confidence']}）",
                f"區段中心點至最近者之直線距離 {agg['distance_m']} M｜{geo}｜"
                "個別因素應自宗地起算並採路線距離（手冊伍、一(二)8(3)），"
                "本值為區段中心直線距離之替代，偏向高估便利性")

        # --- 19 接近商圈：OSM 零售聚集點（代理判準） -------------------------
        if bp:
            b = min(bp, key=lambda p: math.hypot(p["x"] - cx, p["y"] - cy))
            d = round(math.hypot(b["x"] - cx, b["y"] - cy))
            ext["near_business"][sn] = _rec(
                f"{b['name']}（{b['tag']}）", d, {"value": d}, "代理判準",
                f"OpenStreetMap {b['tag']}（信心 C）",
                f"{BUSINESS_RULE}｜區段中心直線距離 {d} M｜{geo}")

        # --- 20 嫌惡設施：表3 特殊設施／環境污染各欄之最近者 -----------------
        cands = []
        for code in NUISANCE_ITEMS:
            it = inf["items"][code]
            agg = (it["by_segment"].get(sn) or {}).get("aggregated")
            if agg:
                cands.append((agg["distance_m"], code, it, agg))
        if cands:
            d, code, it, agg = min(cands, key=lambda t: t[0])
            complete = all(inf["items"][c]["coverage"]["usable_for_grading"]
                           for c in NUISANCE_ITEMS)
            ext["nuisance"][sn] = _rec(
                f"{agg['sub']}：{_fname(agg)}", d, {"value": d},
                conf_kind(agg["confidence"]) if complete else "覆蓋不足",
                f"表3 {sn}「{it['label']}」推算值／{agg['source']}（信心 {agg['confidence']}）",
                f"取表3 電業／殯葬／廢棄物／環境污染四類之最近者 {d} M｜{geo}｜"
                "⚠️ 殯葬（5 筆名冊無法定位）、廢棄物（掩埋場無來源）、"
                "環境污染（5 子欄缺 4）覆蓋不完整，真實最近者可能更近，"
                "本值為樂觀上限（等級偏優），不得據以認定無嫌惡設施")

        # --- 21 停車方便性：路外公共停車場距離（代理判準） -------------------
        it = inf["items"]["parking"]
        agg = (it["by_segment"].get(sn) or {}).get("aggregated")
        if agg:
            d = agg["distance_m"]
            cat = next(c for lim, c in PARKING_BANDS if lim is None or d < lim)
            ext["parking_ease"][sn] = _rec(
                f"{cat[len('停車方便性'):]}（{_fname(agg)}）", d, {"category": cat},
                "代理判準",
                f"表3 {sn}「停車場地之便利程度」推算值／{agg['source']}"
                f"（信心 {agg['confidence']}）",
                f"{PARKING_RULE}｜最近路外公共停車場 {d} M｜{geo}｜"
                "路邊停車格不在資料集內，未納入判定")
    return ext


def patch_rows(t4i, ext, crit_ind, seg_order):
    """把外部補填結果寫回 derive_table4_individual 之 rows"""
    base_no, comps = seg_order[0], seg_order[1:]
    for r in t4i["rows"]:
        code = r["item_code"]
        if code not in ext or not ext[code]:
            continue
        it = crit_ind[code]
        b = ext[code].get(base_no)
        if not b:
            continue
        try:
            b_rank, b_label = grade(it, **b["arg"])
        except Ungradable:
            continue
        r["base"] = {"condition": b["name"], "rank": b_rank, "label": b_label}
        r["basis"] = b["source"]
        r["_ext_base"] = b
        r["_ext_comps"] = []
        r["comparables"] = []
        kinds = [b["kind"]]
        for sn in comps:
            c = ext[code].get(sn)
            if not c:
                r["comparables"].append({"segment": sn, "condition": None, "rank": None,
                                         "label": None, "diff": None})
                r["_ext_comps"].append(None)
                continue
            try:
                c_rank, c_label = grade(it, **c["arg"])
            except Ungradable:
                c_rank = c_label = None
            d = adjust(it, b_rank, c_rank) if b_rank and c_rank else None
            r["comparables"].append({"segment": sn, "condition": c["name"],
                                     "rank": c_rank, "label": c_label, "diff": d})
            r["_ext_comps"].append(c)
            kinds.append(c["kind"])
        r["status"] = "外部補填"
        r["_kind"] = kinds[0]
        for k in kinds[1:]:
            r["_kind"] = worse(r["_kind"], k)
    # 合計仍須 7~25 全數可判定；7~12 無來源，維持不得加總
    t4i["complete"] = all(rr["base"] and all(c["diff"] is not None
                                             for c in rr["comparables"])
                          for rr in t4i["rows"])
    if not t4i["complete"]:
        t4i["total_note"] = ("個別因素合計需 7~25 全數可判定；13~21 已由表3 與開放資料補填，"
                             "但 7~11（面積、寬度、深度、形狀、臨街情形）須宗地地籍幾何，"
                             "24 容積率為敘述型，仍不得加總")
    return t4i


# ======================================================================== 表4
DIST_ROWS = set(range(16, 24))          # 16~23：條件欄拆為「名稱」「數值(M)」兩格
VAL_COL = {"D": "E", "G": "H", "K": "L", "O": "P"}


def build_table4_v4(ds, case, segs, seg_order, levels, t4i, crit_ind):
    wb = openpyxl.load_workbook(os.path.join(X.IN, "表4比較法調查估價表.xlsx"))
    ws = wb.active
    t4 = case["table4"]
    base_no, comps = seg_order[0], seg_order[1:]
    s = t4["summary"]
    src_pdf = "doc/題目.pdf 表4 比較法調查估價表"

    # ---- 0~6 列：題目原載（與 v2/v3 相同）------------------------------------
    X.put(ws, "L1", t4["appraisal_date"], "題目原載", "估價基準日", src_pdf, "原表所載", seg="全表")
    X.put(ws, "P1", case["case_no"], "題目原載", "案號", src_pdf, "原表所載", seg="全表")
    X.put(ws, "F2", "0003", "題目原載", "比準地宗地流水號", src_pdf,
          "原表所載；比準地位於徵收範圍內，個別因素得由表7 宗地個別因素清冊同編號欄位取得",
          seg=base_no)
    lots = t4["lots"]
    X.put(ws, "D4", lots[0], "題目原載", "比準地坐落", src_pdf, "原表所載", seg=base_no)
    X.put(ws, "D6", "111年9月1日", "題目原載", "比準地交易日期（估價基準日）", src_pdf,
          "原表所載", seg=base_no)
    X.put(ws, "D8", base_no, "題目原載", "比準地地價區段號", src_pdf, "原表所載", seg=base_no)

    dates = ["110年9月14日", "111年1月11日", "110年10月29日"]
    for i, sn in enumerate(comps):
        col, dcol = X.T4_COMP[i][0], X.T4_COMP[i][2]
        X.put(ws, f"{dcol}2", i + 1, "題目原載", f"比較標的{i+1} 實例編號", src_pdf,
              "原表所載", seg=sn)
        X.put(ws, f"{col}4", lots[i + 1], "題目原載", f"比較標的{i+1} 坐落", src_pdf,
              "原表所載", seg=sn)
        c = X.put(ws, f"{col}5", s["unit_price"]["values"][i], "題目原載",
                  f"比較標的{i+1} 土地正常單價(元/M2)", src_pdf + "／表1-1 買賣實例調查估價表",
                  "原表所載", seg=sn)
        c.number_format = "#,##0"
        X.put(ws, f"{col}6", dates[i], "題目原載", f"比較標的{i+1} 交易日期", src_pdf,
              "原表所載", seg=sn)
        c = X.put(ws, f"{dcol}6", s["date_adj"]["percents"][i] / 100, "題目原載",
                  f"比較標的{i+1} 交易日期調整百分率", src_pdf,
                  "原表所載；係參酌新北市樹林區土地平均區段地價表（住宅區）調整", seg=sn)
        c.number_format = "0.00%"
        up, da = s["unit_price"]["values"][i], s["date_adj"]["percents"][i]
        c = X.put(ws, f"{col}7", s["adjusted_price"]["values"][i], "題目原載",
                  f"比較標的{i+1} 調整至估價基準日單價(元/M2)", src_pdf,
                  f"驗算：{up:,.0f} ×(1+{da:.2f}%) = {up * (1 + da / 100):,.2f} → 表列 "
                  f"{s['adjusted_price']['values'][i]:,.0f}，相符", seg=sn)
        c.number_format = "#,##0"
        X.put(ws, f"{col}8", sn, "題目原載", f"比較標的{i+1} 地價區段號", src_pdf,
              "原表所載", seg=sn)
        cell = X.put(ws, f"{dcol}8", "資料不足", "資料不足",
                     f"比較標的{i+1} 區域因素調整百分率", "表5-1 影響地價區域因素總修正數",
                     "上游之表5 總修正數因表3 特殊設施(6)、環境污染(7) 覆蓋不足而不成立，"
                     "本欄不得填列", f"{REGION}.regional.total", seg=sn)
        cell.alignment = Alignment(horizontal="center")

    # ---- 個別因素 7~25 -------------------------------------------------------
    for r in t4i["rows"]:
        fn = r["field_no"]
        row = (fn + 2) if fn else 28
        base_c, comp_c = X.t4_cond_cells(row)
        it = crit_ind.get(r["item_code"], {})
        label = f"{fn}{r['item_name']}" if fn else f"6其他-{r['item_name']}"
        b = r["base"] or {}
        kind = {"確認": "AI判定", "推定": "推定",
                "外部補填": r.get("_kind", "外部推算")}.get(r["status"], "資料不足")
        if r["status"].startswith("條件可確認"):
            kind = "AI判定"
        ext_b = r.get("_ext_base")
        ext_c = r.get("_ext_comps") or [None] * len(comps)

        if not b.get("condition"):
            cell = X.put(ws, base_c, "資料不足", "資料不足", f"{label}（比準地條件）",
                         "表7 宗地個別因素清冊／地籍圖／現場勘查（題目未提供）",
                         r["gap"] or "宗地層級勘查資料未提供",
                         f"{REGION}.individual.{r['item_code']}", seg=base_no)
            cell.alignment = Alignment(horizontal="center")
            for (cc, dc), sn in zip(comp_c, comps):
                for coord, txt in ((cc, "資料不足"), (dc, "—")):
                    cell = X.put(ws, coord, txt, "資料不足",
                                 f"{label}（{sn}{'條件' if coord == cc else '差異率'}）",
                                 "表1-1 買賣實例調查估價表僅載坐落、面積、交易日期與正常單價",
                                 "比較標的宗地之個別因素須由查估單位另行勘查建立",
                                 f"{REGION}.individual.{r['item_code']}", seg=sn)
                    cell.alignment = Alignment(horizontal="center")
            continue

        # 條件欄（名稱）＋ 數值欄（距離／寬度 M）
        bk = ext_b["kind"] if ext_b else kind
        X.put(ws, base_c, b["condition"], bk, f"{label}（比準地條件）",
              (ext_b["source"] if ext_b else r["basis"]) or "表3 地價區段勘查表",
              (ext_b["basis"] + f"｜判級：第{b['rank']}／共{it.get('level_count', '?')}級"
               f"（{b['label']}）") if ext_b else
              (f"判級：第{b['rank']}／共{it.get('level_count', '?')}級（{b['label']}）"
               if b.get("rank") else "敘述型細項，無級距"),
              f"{REGION}.individual.{r['item_code']}", seg=base_no)
        if ext_b and ext_b["value"] is not None and row in DIST_ROWS:
            c = X.put(ws, f"{VAL_COL['D']}{row}", ext_b["value"], bk,
                      f"{label}（比準地數值 M）", ext_b["source"], ext_b["basis"],
                      f"{REGION}.individual.{r['item_code']}", seg=base_no)
            c.number_format = "0"
            c.alignment = Alignment(horizontal="center")

        for i, ((cc, dc), sn, c) in enumerate(zip(comp_c, comps, r["comparables"])):
            e = ext_c[i] if i < len(ext_c) else None
            if not c["condition"]:
                for coord in (cc, dc):
                    X.put(ws, coord, "資料不足", "資料不足", f"{label}（{sn}）",
                          "題目未提供", r["gap"] or "資料不足",
                          f"{REGION}.individual.{r['item_code']}", seg=sn)
                continue
            ck = e["kind"] if e else kind
            X.put(ws, cc, c["condition"], ck, f"{label}（{sn} 條件）",
                  (e["source"] if e else f"表3 {sn} 之法定管制值／區段記載"),
                  (e["basis"] + f"｜判級：第{c['rank']}／共{it.get('level_count', '?')}級"
                   f"（{c['label']}）") if e else
                  (f"判級：第{c['rank']}／共{it.get('level_count', '?')}級（{c['label']}）"
                   if c.get("rank") else "敘述型細項，無級距"),
                  f"{REGION}.individual.{r['item_code']}", seg=sn)
            if e and e["value"] is not None and row in DIST_ROWS:
                cell = X.put(ws, f"{VAL_COL[cc[0]]}{row}", e["value"], ck,
                             f"{label}（{sn} 數值 M）", e["source"], e["basis"],
                             f"{REGION}.individual.{r['item_code']}", seg=sn)
                cell.number_format = "0"
                cell.alignment = Alignment(horizontal="center")
            if c["diff"] is None:
                cell = X.put(ws, dc, "待試算", "資料不足", f"{label}（{sn} 差異率）",
                             "doc/rules/評價基準明細表.pdf（個別因素）",
                             r["gap"] or "基準明細表列為敘述型，無查表矩陣",
                             f"{REGION}.individual.{r['item_code']}", seg=sn)
                cell.alignment = Alignment(horizontal="center")
            else:
                dk = worse(bk, ck)
                cell = X.put(ws, dc, c["diff"] / 100, dk, f"{label}（{sn} 差異率）",
                             f"比準地「{b['condition']}」({b['rank']}) ／ "
                             f"{sn}「{c['condition']}」({c['rank']})",
                             f"查表：共{it.get('level_count')}級、最大±{it.get('max_adjustment')}%、"
                             f"級距{it.get('step')}%；({c['rank']}−{b['rank']})×{it.get('step')} "
                             f"= {c['diff']:+.2f}"
                             + ("｜條件欄為區段層級推算值，差異率之信心不高於條件欄"
                                if dk in ("推定", "外部推算", "外部推算OSM", "代理判準",
                                          "覆蓋不足") else ""),
                             f"{REGION}.individual.{r['item_code']}", seg=sn)
                cell.number_format = "0.00%"

    # ---- 合計、比較價格：仍不得加總 -----------------------------------------
    part = {sn: 0.0 for sn in comps}
    ok_items = []
    for r in t4i["rows"]:
        if r["base"] and all(c["diff"] is not None for c in r["comparables"]):
            ok_items.append(r["item_name"])
            for c in r["comparables"]:
                part[c["segment"]] += c["diff"]
    for i, sn in enumerate(comps):
        col = X.T4_COMP[i][0]
        cell = X.put(ws, f"{col}29", "不得加總", "資料不足", f"個別因素差異率合計（{sn}）",
                     "本表 7~25 各細項差異率",
                     (t4i.get("total_note") or "個別因素合計需 7~25 全數可判定")
                     + f"｜已可判定之 {len(ok_items)} 細項部分合計為 {part[sn]:+.2f}%"
                       "（僅供參考，不得填入本欄）",
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
            cell = X.put(ws, coord, "資料不足", "資料不足", f"{name}（{sn}）",
                         "本表上游欄位", why, "", seg=sn)
            cell.alignment = Alignment(horizontal="center")

    cell = X.put(ws, "G32", "資料不足", "資料不足", "比準地比較價格",
                 "本表各比較標的試算價格與權重",
                 "＝Σ(試算價格×權重)；各比較標的試算價格與權重均不成立，不得計算",
                 "", seg=base_no)
    cell.alignment = Alignment(horizontal="center")

    # ---- 備註欄 --------------------------------------------------------------
    X.put(ws, "D33",
          "1.本表 13~21 各細項係以表3 地價區段勘查表之區段層級記載與開放資料推算補填（底色標示"
          "信心等級）：13、14 取自表3「主要道路」名稱與寬度；15~20 之距離為自區段中心點起算之"
          "直線距離，非自宗地起算，亦非路線距離；21 之級距為代理判準。同一區段內各宗地均得相同"
          "值，不具宗地個別性，須以現場勘查或表7 宗地個別因素清冊覆核。"
          "2.本表 7~11（面積、寬度、深度、形狀、臨街情形）因無宗地地籍幾何資料仍留空："
          "比準地（宗地流水號0003）應由表7 宗地個別因素清冊同編號欄位抄錄；"
          "三個比較標的應由查估單位就各該買賣實例宗地另行勘查。"
          "3.20嫌惡設施之距離因殯葬、廢棄物、環境污染各欄覆蓋不完整，為樂觀上限（等級偏優）。"
          "4.24容積率之個別因素基準明細表列為敘述型（以土地開發分析法試算調整），無查表矩陣，"
          "差異率待試算；並須與表5 容積率修正擇一，避免重複修正（作業手冊 六(九)）。",
          "AI判定", "備註欄（比準地或各比較標的）", "engine/export_v4.py 補填結果",
          "作業手冊 伍、六；審查重點 iii、vi", seg="全表")
    ws["D33"].alignment = Alignment(wrap_text=True, vertical="top")
    X.put(ws, "D34",
          "1.價格日期調整係參酌新北市樹林區土地平均區段地價表(住宅區)進行調整。"
          "2.比準地所在區段於案例蒐集期間(111年3月2日至111年9月1日間)無適當成交案例，"
          "故依土地徵收補償市價查估辦法第17條第3項規定，擴大選取範圍及案例蒐集期間至"
          "估價基準日前一年內(110年9月2日至111年9月1日)。",
          "題目原載", "備註欄（全案）", src_pdf, "原表所載", seg="全表")
    ws["D34"].alignment = Alignment(wrap_text=True, vertical="top")

    X.add_basis_sheet(wb, "表4 比較法調查估價表（案號 1110901-99-XXX，比準地 P001-00）"
                          "／個別因素 13~21 為表3 區段層級記載與開放資料之推算值，非宗地勘查")
    p = os.path.join(OUT, "表4_比較法調查估價表_已填.xlsx")
    wb.save(p)
    return p, ok_items, part


def main():
    inf = json.load(open(INF, encoding="utf-8"))
    ds = Dataset()
    crit = ds.criteria(REGION, "regional")
    crit_ind = ds.criteria(REGION, "individual")
    segs = ds.segments(REGION)
    case = list(ds.cases(REGION).values())[0]
    seg_order = case["table5"]["segment_nos"]
    levels = {sn: derive_segment_levels(ds, REGION, segs[sn]) for sn in seg_order}
    t4i = derive_table4_individual(ds, REGION, case, segs)

    fac_by_seg = {sn: {c: {"rank": e["by_segment"][sn]["rank"],
                           "label": e["by_segment"][sn]["level_label"],
                           "criterion": e["by_segment"][sn]["criterion"]}
                       for c, e in inf["items"].items()
                       if e["coverage"]["usable_for_grading"]
                       and e["by_segment"].get(sn, {}).get("rank")}
                  for sn in seg_order}
    merged_levels = {sn: ({**levels[sn][0], **fac_by_seg[sn]}, levels[sn][1])
                     for sn in seg_order}

    ext = build_individual_ext(segs, seg_order, inf, crit_ind)
    t4i = patch_rows(t4i, ext, crit_ind, seg_order)

    X.basis_rows = []
    p3 = V3.build_table3_v3(ds, segs, seg_order, levels, crit, inf)
    n3 = len(X.basis_rows)

    X.basis_rows = []
    p5, group_ok, group_vals = X.build_table5(ds, case, segs, seg_order, merged_levels, crit)
    n5 = len(X.basis_rows)

    X.basis_rows = []
    p4, ok_items, part = build_table4_v4(ds, case, segs, seg_order, merged_levels,
                                         t4i, crit_ind)
    n4 = len(X.basis_rows)

    print(f"表3 → {os.path.relpath(p3, ROOT)}（{len(seg_order)} 個區段工作表，{n3} 筆依據）")
    print(f"表4 → {os.path.relpath(p4, ROOT)}（{n4} 筆依據）")
    print(f"表5 → {os.path.relpath(p5, ROOT)}（{n5} 筆依據）")
    print(f"表4 個別因素可判定細項（{len(ok_items)}）：{'、'.join(ok_items)}")
    print("   部分合計（僅供參考，未填入表）：",
          {k: round(v, 2) for k, v in part.items()})
    ng = sorted(g for g in group_ok if not group_ok[g])
    print("表5 小計不成立之主要項目：", ng)
    return {"table3": p3, "table4": p4, "table5": p5, "ext": ext, "t4i": t4i}


if __name__ == "__main__":
    main()
