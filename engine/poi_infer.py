#!/usr/bin/env python3
"""以開放資料推算表3 設施類欄位，並依評價基準明細表判級。

⚠️ 產出為【外部資料推算】，不是法定勘查記錄。用途是供查估／審查人員核對，
   不得取代承辦單位之實地勘查（理由見 output/thirdVersion/README.md §0）。

流程：
  1. 由 OSM 界街幾何求各地價區段中心點（表3 距離之量測基準，手冊伍、一(二)6）
  2. 各設施子欄取「最近者」（手冊伍、一(二)8(2)：同細項多設施取影響最大者）
  3. 對照 datasets/regions/shulin/criteria/regional.json 級距判級
  4. 敏感度檢定：距離落在級距邊界 ±（區段中心不確定半徑）內 → 標記「臨界」

輸出：datasets/external/poi_inference.json
"""
import json, math, os, itertools, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "datasets", "external", "cache")
OUTJSON = os.path.join(ROOT, "datasets", "external", "poi_inference.json")
REGION = "shulin"

# ---------------------------------------------------------------- 座標換算
_A = 6378137.0
_F = 1 / 298.257222101
_E2 = _F * (2 - _F)
_K0, _FE, _LON0 = 0.9999, 250000.0, math.radians(121)


def wgs_to_tm2(lon, lat):
    """WGS84 經緯度 → TWD97 TM2（中央經線 121°E、k0=0.9999、東偏 250km）"""
    lon, lat = math.radians(float(lon)), math.radians(float(lat))
    ep2 = _E2 / (1 - _E2)
    N = _A / math.sqrt(1 - _E2 * math.sin(lat) ** 2)
    T = math.tan(lat) ** 2
    C = ep2 * math.cos(lat) ** 2
    A = (lon - _LON0) * math.cos(lat)
    M = _A * ((1 - _E2 / 4 - 3 * _E2 ** 2 / 64 - 5 * _E2 ** 3 / 256) * lat
              - (3 * _E2 / 8 + 3 * _E2 ** 2 / 32 + 45 * _E2 ** 3 / 1024) * math.sin(2 * lat)
              + (15 * _E2 ** 2 / 256 + 45 * _E2 ** 3 / 1024) * math.sin(4 * lat)
              - (35 * _E2 ** 3 / 3072) * math.sin(6 * lat))
    x = _FE + _K0 * N * (A + (1 - T + C) * A ** 3 / 6
                         + (5 - 18 * T + T ** 2 + 72 * C - 58 * ep2) * A ** 5 / 120)
    y = _K0 * (M + N * math.tan(lat) * (A ** 2 / 2
               + (5 - T + 9 * C + 4 * C ** 2) * A ** 4 / 24
               + (61 - 58 * T + T ** 2 + 600 * C - 330 * ep2) * A ** 6 / 720))
    return x, y


def load(name):
    with open(os.path.join(CACHE, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------- 1. 地價區段中心點（OSM 界街）
# scope_desc 之四至界街，逐字取自 datasets/regions/shulin/segments/*.json
SEG_BOUNDARY = {
    "P001-00": ["八德街", "啟智街", "啟智街187巷"],
    "P002-00": ["樹人街", "長壽街21巷", "啟智街14巷", "樹德街136巷"],
    "P003-00": ["東榮街", "鎮前街411巷1弄", "東榮街88巷", "鎮前街367巷"],
    "P004-00": ["潭興街", "潭興街107巷21弄", "潭興街91巷"],
}
CORNER_TOL_M = 40.0          # 兩界街視為交會之最大間距


def _pt_seg(p, q, r):
    (px, py), (ax, ay), (bx, by) = p, q, r
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L == 0:
        return math.hypot(px - ax, py - ay), (ax, ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy), (cx, cy)


def segment_centers():
    ways = {}
    for e in load("osm_streets"):
        n = (e.get("tags") or {}).get("name")
        if not n:
            continue
        ways.setdefault(n, []).append(
            [wgs_to_tm2(g["lon"], g["lat"]) for g in e.get("geometry", [])])

    def closest(a, b):
        best = (1e18, None)
        for pa in ways.get(a, []):
            for pb in ways.get(b, []):
                for p in pa:
                    for i in range(len(pb) - 1):
                        d, c = _pt_seg(p, pb[i], pb[i + 1])
                        if d < best[0]:
                            best = (d, ((p[0] + c[0]) / 2, (p[1] + c[1]) / 2))
        return best

    out = {}
    for sid, names in SEG_BOUNDARY.items():
        corners, missing = [], [n for n in names if n not in ways]
        for a, b in itertools.combinations(names, 2):
            d, pt = closest(a, b)
            if pt and d < CORNER_TOL_M:
                corners.append({"pair": f"{a}×{b}", "gap_m": round(d, 1), "xy": pt})
        if not corners:
            out[sid] = {"located": False, "missing_streets": missing}
            continue
        cx = sum(c["xy"][0] for c in corners) / len(corners)
        cy = sum(c["xy"][1] for c in corners) / len(corners)
        rad = max(math.hypot(c["xy"][0] - cx, c["xy"][1] - cy) for c in corners)
        out[sid] = {
            "located": True, "center_twd97": [round(cx, 1), round(cy, 1)],
            "uncertainty_m": round(max(rad, 25.0), 1),   # 下限 25m：界街本身有寬度
            "corner_count": len(corners), "missing_streets": missing,
            "corners": [{"pair": c["pair"], "gap_m": c["gap_m"],
                         "xy": [round(c["xy"][0], 1), round(c["xy"][1], 1)]} for c in corners],
        }
    return out


# ------------------------------------------------------------ 2. 設施點位來源
# 信心等級：A 官方名冊＋官方座標／B 官方名冊＋OSM座標（名稱交叉比對）／
#          C 僅 OSM 群眾協作／D 無法定位或無來源
SHULIN = "樹林區"


def _osm_pts(pred):
    out = []
    for e in load("osm_poi"):
        t = e.get("tags") or {}
        if not pred(t):
            continue
        c = e.get("center") or ({"lat": e.get("lat"), "lon": e.get("lon")}
                                if e.get("lat") else None)
        if not c:
            continue
        x, y = wgs_to_tm2(c["lon"], c["lat"])
        out.append({"name": t.get("name") or "(未命名)", "x": x, "y": y,
                    "src": "OSM", "conf": "C", "tag": _osm_key(t)})
    return out


def _osm_key(t):
    for k in ("leisure", "amenity", "shop", "landuse", "power", "man_made"):
        if k in t:
            return f"{k}={t[k]}"
    return "?"


def landmark_pts(*types, exclude_kw=()):
    out = []
    for r in load("landmark"):
        if r.get("行政區") != SHULIN or r.get("地標類型") not in types:
            continue
        nm = r.get("地標名稱") or ""
        if any(k in nm for k in exclude_kw):
            continue
        out.append({"name": nm, "x": float(r["twd97_x"]), "y": float(r["twd97_y"]),
                    "src": "新北市重要地標", "conf": "A", "tag": r["地標類型"]})
    return out


def busstop_pts():
    seen, out = set(), []
    for r in load("busstop"):
        if SHULIN not in (r.get("address") or "") or not r.get("longitude"):
            continue
        k = r.get("stoplocationid")          # 依站位去重（原始為路線×站位）
        if k in seen:
            continue
        seen.add(k)
        x, y = wgs_to_tm2(r["longitude"], r["latitude"])
        out.append({"name": r["namezh"], "x": x, "y": y,
                    "src": "公車站位資訊", "conf": "A", "tag": "站牌"})
    return out


def parking_pts():
    return [{"name": r["NAME"], "x": float(r["TW97X"]), "y": float(r["TW97Y"]),
             "src": "路外公共停車場", "conf": "A", "tag": "路外停車場"}
            for r in load("parking") if r.get("AREA") == SHULIN and r.get("TW97X")]


def interchange_pts():
    out = []
    for r in load("interchange"):
        nm = (r.get("設施名稱") or "").strip()
        if "交流道" not in nm:
            continue                      # 排除「基隆端」「轉接道」等非交流道設施
        try:
            x, y = wgs_to_tm2(r["位置座標X"], r["位置座標Y"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append({"name": f"{nm}（{r.get('_國道','')}）", "x": x, "y": y,
                    "src": "高速公路交流道座標", "conf": "A", "tag": "交流道"})
    return out


def tourism_pts():
    out = []
    for r in load("tourism"):
        if SHULIN not in (r.get("Add") or "") or not r.get("Px"):
            continue
        out.append({"name": r["Name"], "x": wgs_to_tm2(r["Px"], r["Py"])[0],
                    "y": wgs_to_tm2(r["Px"], r["Py"])[1],
                    "src": "新北市觀光旅遊景點", "conf": "B", "tag": f"Class1={r.get('Class1')}"})
    return out


def riverpark_pts():
    """河濱公園無行政區欄，以座標落在樹林區外接矩形內篩選"""
    out = []
    for r in load("riverpark"):
        x, y = wgs_to_tm2(r["longitude"], r["latitude"])
        if 286000 < x < 296000 and 2760000 < y < 2770000:
            out.append({"name": r["name"], "x": x, "y": y,
                        "src": "河濱公園位置", "conf": "B", "tag": "河濱公園"})
    return out


def official_cemetery_names():
    """內政部殯葬設施＋新北市公立公墓納骨塔，樹林區之官方名冊（無座標）"""
    names = []
    for r in load("funeral_moi"):
        if r.get("管轄所屬縣市") == "新北市" and SHULIN in (r.get("地址") or ""):
            names.append((r["類別"], r["名稱"], r.get("地址", ""), r.get("公/私立", "")))
    for r in load("cemetery"):
        if r.get("district") == SHULIN:
            names.append((r["facilityclassification"], r["facilityname"],
                          r.get("facilityaddress", ""), "公立"))
    return names


def _norm(s):
    return (s or "").replace("樹林區", "").replace("新北市", "").replace("市立", "") \
                    .replace("第", "").replace("　", "").replace(" ", "")


def funeral_pts():
    """官方名冊 × OSM 座標交叉比對：對得上→B 級，對不上→僅列候選（無座標）"""
    osm = _osm_pts(lambda t: t.get("landuse") == "cemetery"
                   or t.get("amenity") in ("grave_yard", "crematorium", "funeral_hall"))
    official = official_cemetery_names()
    pts, matched_osm = [], set()
    for kind, nm, addr, pub in official:
        hit = None
        for i, o in enumerate(osm):
            if o["name"] == "(未命名)":
                continue
            if _norm(nm) and (_norm(nm) in _norm(o["name"]) or _norm(o["name"]) in _norm(nm)):
                hit = (i, o)
                break
        if hit:
            i, o = hit
            matched_osm.add(i)
            pts.append({"name": nm, "x": o["x"], "y": o["y"],
                        "src": f"官方名冊({kind})×OSM座標", "conf": "B",
                        "tag": f"{kind}/{pub}", "official_addr": addr})
        else:
            pts.append({"name": nm, "x": None, "y": None,
                        "src": f"官方名冊({kind})", "conf": "D",
                        "tag": f"{kind}/{pub}", "official_addr": addr,
                        "note": "官方名冊有載，但地址為描述性或缺漏，無法定位"})
    for i, o in enumerate(osm):            # OSM 有、官方名冊比對不到者
        if i not in matched_osm:
            pts.append({**o, "note": "僅 OSM 有，未能與官方名冊比對"})
    return pts


def incinerator_pts():
    """焚化爐：官方資料集提供名稱與門牌，座標由 OSM『樹林焚化爐』圖徵取得。

    交叉驗證：垃圾焚化廠位置（環保局）與空污固定污染源（F0703948）兩個獨立官方
    來源，地址皆為「新北市樹林區中山路三段212號」；OSM 同名圖徵位於中山路三段沿線，
    三者一致 → 信心 B（官方名冊＋第三方座標）。
    """
    osm = _osm_pts(lambda t: "焚化" in (t.get("name") or ""))
    if not osm:                      # OSM 查無 → 不臆造座標
        return [{"name": r["chinese_name"], "x": None, "y": None,
                 "src": "垃圾焚化廠位置(官方)", "conf": "D", "tag": "焚化爐",
                 "official_addr": r.get("address", ""),
                 "note": "官方名冊有載但無座標，OSM 亦無對應圖徵，無法定位"}
                for r in load("incinerator") if SHULIN in (r.get("address") or "")]
    out = []
    for r in load("incinerator"):
        if SHULIN in (r.get("address") or ""):
            o = osm[0]
            out.append({"name": r["chinese_name"], "x": o["x"], "y": o["y"],
                        "src": "垃圾焚化廠位置(官方)×OSM座標", "conf": "B",
                        "tag": "焚化爐", "official_addr": r["address"]})
    return out


# ------------------------------------------ 3. 表3 子欄 → 點位來源對照（表5 細項聚合）
def build_specs():
    return {
        "near_station": {
            "label": "接近大型車站之程度",
            "subs": [
                ("H13", "高鐵站", lambda: [], "重要地標無『高鐵站』類型；新北市境內無高鐵站"),
                ("H14", "火車站", lambda: landmark_pts("火車站"), ""),
                ("H15", "客運站", lambda: [], "無對應開放資料（公車站位屬站牌，不得代用）"),
                ("H16", "捷運站", lambda: landmark_pts("捷運站", exclude_kw=("施工中", "規劃中")),
                 "樹林區 6 站全標示『施工中』，估價基準日 111.09.01 未通車，全數排除"),
            ]},
        "near_busstop": {
            "label": "站牌之接近程度或密集程度",
            "subs": [("H17", "站牌", busstop_pts, "")]},
        "near_interchange": {
            "label": "交流道之有無及接近交流道之程度",
            "subs": [("I19", "交流道", interchange_pts,
                      "基準明細表備註：以各地價區段至交流道直線距離計算")]},
        "near_school": {
            "label": "接近學校之程度（國小、國中、高中、大專院校）",
            "subs": [
                ("I35", "國小", lambda: landmark_pts("國民小學"), ""),
                ("I36", "國中", lambda: landmark_pts("國民中學", "完全中學"), ""),
                ("I37", "高中", lambda: landmark_pts("高中職", "完全中學"), ""),
                ("I38", "大專院校", lambda: landmark_pts("大專院校"),
                 "樹林區內 0 所；有效半徑 1,000m 內亦無鄰區大專院校"),
            ]},
        "near_market": {
            "label": "接近市場之程度（傳統市場、超級市場、超大型購物中心）",
            "subs": [
                ("I39", "傳統市場", lambda: _osm_pts(lambda t: t.get("amenity") == "marketplace"),
                 "公有市場清冊樹林區僅1筆且無座標；改採 OSM marketplace"),
                ("I40", "超級市場", lambda: _osm_pts(lambda t: t.get("shop") == "supermarket"),
                 "公有清冊全市僅8筆超市；改採 OSM shop=supermarket"),
                ("I41", "超大型購物中心", lambda: _osm_pts(
                    lambda t: t.get("shop") in ("mall", "department_store")), ""),
            ]},
        "near_park": {
            "label": "接近公園（里鄰公園、一般公園）、廣場、徒步區之程度",
            "subs": [
                ("I42", "里鄰公園", lambda: _osm_pts(lambda t: t.get("leisure") == "park"),
                 "新北市公園資料集無座標且 52% 無門牌；改採 OSM leisure=park"),
                ("I43", "一般公園", riverpark_pts, ""),
                ("I44", "廣場、徒步區", lambda: [], "無對應開放資料"),
            ]},
        "near_tourism": {
            "label": "接近觀光遊憩設施之程度",
            "subs": [("T4", "觀光遊憩設施", tourism_pts,
                      "Class1 代碼表未公開，清單含紀念碑／廟宇等非遊憩設施，須人工確認")]},
        "parking": {
            "label": "停車場地之便利程度",
            "subs": [("T6", "停車場地", parking_pts,
                      "僅路外停車場；路邊停車格不在資料集內，不得據以判『無』")]},
        "near_service": {
            "label": "接近服務性設施的程度（郵局、銀行、醫院、機關等設施）",
            "subs": [
                ("T8a", "醫院", lambda: landmark_pts("地區醫院", "區域醫院", "醫學中心", "衛生所"), ""),
                ("T8b", "機關", lambda: landmark_pts(
                    "警察機關", "消防機關", "戶政事務所", "公所", "稅捐機關",
                    "地政事務所", "監理機關", "其他機關", "縣市政府"), ""),
                ("T8c", "銀行", lambda: _osm_pts(lambda t: t.get("amenity") == "bank"),
                 "金管會名冊有樹林區24家但無座標；改採 OSM amenity=bank"),
                ("T8d", "郵局", lambda: _osm_pts(lambda t: t.get("amenity") == "post_office"),
                 "18 個開放資料來源皆無郵局；改採 OSM amenity=post_office"),
            ]},
        "utility_facility": {
            "label": "電業設施及公用氣體燃料設施之有無及接近程度",
            "subs": [
                ("T14", "變電所或高壓鐵塔", lambda: _osm_pts(
                    lambda t: t.get("power") in ("substation", "tower", "plant")),
                 "台電二次變電所檔所在地僅到『新北市樹林區』無法定位；改採 OSM power=*"),
                ("T16", "瓦斯槽或儲油槽", lambda: _osm_pts(
                    lambda t: t.get("man_made") in ("storage_tank", "gasometer")), ""),
            ]},
        "funeral_facility": {
            "label": "殯葬設施之有無及接近程度",
            "subs": [("T18", "墓地／殯儀館／火葬場／納骨塔", funeral_pts,
                      "官方名冊（內政部＋新北市民政局）與 OSM 座標交叉比對")]},
        "waste_facility": {
            "label": "廢棄物處理設施之有無及接近程度",
            "subs": [
                ("T22", "污水處理場", lambda: _osm_pts(
                    lambda t: t.get("man_made") == "wastewater_plant"), "18 個來源皆無；改採 OSM"),
                ("T23", "垃圾場或掩埋場", lambda: _osm_pts(
                    lambda t: t.get("landuse") == "landfill"), "18 個來源皆無；改採 OSM"),
                ("T24", "焚化爐", incinerator_pts, "官方資料集＋空污固定污染源雙來源地址一致"),
            ]},
        "pollution": {
            "label": "水污染、噪音污染、廢氣污染、廢棄物污染等之有無及接近程度",
            "subs": [
                ("T25", "水污染", lambda: [], "土壤及地下水列管檔僅載地段地號，須地籍定位"),
                ("T26", "噪音污染", lambda: [], "無對應開放資料"),
                ("T27", "廢氣污染", incinerator_pts, "空污固定污染源樹林區僅焚化廠1筆"),
                ("T28", "廢棄物污染", lambda: [], "土壤列管樹林區6筆僅載地段地號，須地籍定位"),
                ("T29", "其他污染", lambda: [], "定義開放，無固定來源"),
            ]},
    }


# ------------------------------------------------------------------ 4. 判級
def match_rank(item, dist_m, is_none):
    """依 criteria 級距判級。回傳 (rank, label, criterion)"""
    levels = item["levels"]
    if is_none:
        for lv in levels:                                    # D5：先找「或無」
            if lv["threshold"].get("or_none"):
                return lv["rank"], lv["label"], lv["criterion"]
        for lv in levels:                                    # 再找上界開放級
            for rg in lv["threshold"].get("ranges", []):
                if rg.get("min") is not None and rg.get("max") is None:
                    return lv["rank"], lv["label"], lv["criterion"]
        return None, None, None
    for lv in levels:                                        # D6：逐級比對區間
        for rg in lv["threshold"].get("ranges", []):
            lo, hi = rg.get("min"), rg.get("max")
            ok = True
            if lo is not None:
                ok &= dist_m >= lo if rg.get("min_inclusive", True) else dist_m > lo
            if hi is not None:
                ok &= dist_m < hi if not rg.get("max_inclusive", False) else dist_m <= hi
            if ok:
                return lv["rank"], lv["label"], lv["criterion"]
    return None, None, None


def boundaries(item):
    b = set()
    for lv in item["levels"]:
        for rg in lv["threshold"].get("ranges", []):
            for v in (rg.get("min"), rg.get("max")):
                if v is not None:
                    b.add(float(v))
    return sorted(b)


def main():
    crit = {i["item_code"]: i for i in json.load(
        open(os.path.join(ROOT, "datasets", "regions", REGION,
                          "criteria", "regional.json"), encoding="utf-8"))["items"]}
    centers = segment_centers()
    specs = build_specs()
    pool = {}
    for code, sp in specs.items():
        for cell, name, fn, note in sp["subs"]:
            pool[(code, cell)] = fn()

    result = {
        "generated_at": datetime.date.today().isoformat(),
        "generator": "engine/poi_infer.py",
        "disclaimer": "外部開放資料推算值，非法定勘查記錄；僅供查估／審查人員核對參考。",
        "segments": centers, "items": {},
    }

    for code, sp in specs.items():
        item = crit[code]
        entry = {"label": sp["label"], "max_adjustment": item["max_adjustment"],
                 "step": item["step"], "level_count": item["level_count"],
                 "direction": item.get("direction"),
                 "subs": [], "by_segment": {}}
        bnds = boundaries(item)
        n_sub = n_covered = n_unloc = 0
        for cell, name, fn, note in sp["subs"]:
            cnt = len([p for p in pool[(code, cell)] if p.get("x") is not None])
            unl = [p["name"] for p in pool[(code, cell)] if p.get("x") is None]
            n_sub += 1
            n_covered += 1 if cnt else 0
            n_unloc += len(unl)
            entry["subs"].append({"cell": cell, "name": name, "note": note,
                                  "candidate_count": cnt, "unlocatable": unl})
        # --- 覆蓋率評估：決定判級結果可不可以用 --------------------------------
        # 嫌惡設施（direction=higher_is_better，近者為劣）子欄有缺 → 真實最近者
        # 只可能「更近」，故推算等級為【樂觀上限】，不得作為判級依據。
        # 正向設施（lower_is_better）子欄有缺 → 真實最近者只可能更近＝更優，
        # 故推算等級為【保守下限】，偏向低估本區段條件，可用但須註明。
        adverse = item.get("direction") == "higher_is_better"
        complete = (n_covered == n_sub) and n_unloc == 0
        entry["coverage"] = {
            "sub_total": n_sub, "sub_with_data": n_covered,
            "unlocatable_count": n_unloc,
            "complete": complete,
            "bound": None if complete else ("optimistic" if adverse else "conservative"),
            "usable_for_grading": complete or not adverse,
            "reason": ("子欄資料齊備" if complete else
                       ("嫌惡設施子欄缺漏，真實最近設施可能更近 → 推算等級僅為樂觀上限，"
                        "不得據以判級，更不得據以填『無』" if adverse else
                        "正向設施子欄缺漏，真實最近設施可能更近 → 推算等級為保守下限，"
                        "偏向低估本區段條件")),
        }
        for sid, sc in centers.items():
            if not sc.get("located"):
                entry["by_segment"][sid] = {"status": "區段未定位"}
                continue
            cx, cy = sc["center_twd97"]
            unc = sc["uncertainty_m"]
            subres, best = [], None
            for cell, name, fn, note in sp["subs"]:
                pts = [p for p in pool[(code, cell)] if p.get("x") is not None]
                if not pts:
                    subres.append({"cell": cell, "name": name, "found": False, "note": note})
                    continue
                p = min(pts, key=lambda q: math.hypot(q["x"] - cx, q["y"] - cy))
                d = math.hypot(p["x"] - cx, p["y"] - cy)
                subres.append({"cell": cell, "name": name, "found": True,
                               "nearest": p["name"], "distance_m": round(d),
                               "source": p["src"], "confidence": p["conf"], "note": note})
                if best is None or d < best[0]:
                    best = (d, p, name)
            if best is None:
                rank, label, crit_txt = match_rank(item, None, True)
                entry["by_segment"][sid] = {
                    "status": "全部子欄無可定位設施", "aggregated": None,
                    "rank": None, "note": "不得逕填『無』——查無資料 ≠ 無設施"}
                entry["by_segment"][sid]["subs"] = subres
                continue
            d, p, subname = best
            rank, label, crit_txt = match_rank(item, d, False)
            near_b = min((abs(d - b) for b in bnds), default=1e9)
            entry["by_segment"][sid] = {
                "status": "已推算",
                "aggregated": {"sub": subname, "facility": p["name"],
                               "distance_m": round(d), "source": p["src"],
                               "confidence": p["conf"]},
                "rank": rank, "level_label": label, "criterion": crit_txt,
                "borderline": near_b <= unc,
                "nearest_boundary_gap_m": round(near_b),
                "segment_uncertainty_m": unc,
                "subs": subres,
            }
        result["items"][code] = entry

    # 表5 修正百分比：matrix[比準地等級-1][比較標的等級-1]
    base = "P001-00"
    comps = ["P002-00", "P003-00", "P004-00"]
    for code, entry in result["items"].items():
        m = crit[code]["matrix"]
        rb = entry["by_segment"].get(base, {}).get("rank")
        entry["adjustments"] = {}
        usable = entry.get("coverage", {}).get("usable_for_grading", True)
        for c in comps:
            rc = entry["by_segment"].get(c, {}).get("rank")
            entry["adjustments"][c] = (None if (rb is None or rc is None or not usable)
                                       else round(m[rb - 1][rc - 1], 2))
        if not usable:
            entry["adjustments_blocked_reason"] = entry["coverage"]["reason"]

    with open(OUTJSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"→ {os.path.relpath(OUTJSON, ROOT)}")
    for sid, sc in centers.items():
        if sc.get("located"):
            print(f"  {sid} 中心 {sc['center_twd97']} ±{sc['uncertainty_m']}m "
                  f"（{sc['corner_count']} 個界街交會點）")
    print()
    for code, e in result["items"].items():
        r = [e["by_segment"][s].get("rank") for s in [base] + comps]
        bl = sum(1 for s in [base] + comps if e["by_segment"][s].get("borderline"))
        cov = e["coverage"]
        flag = "" if cov["complete"] else ("  ⛔覆蓋不足(樂觀上限)" if cov["bound"] == "optimistic"
                                           else f"  ◐子欄{cov['sub_with_data']}/{cov['sub_total']}")
        print(f"  {e['label'][:24]:26s} 等級={r}  調整={list(e['adjustments'].values())}"
              + (f"  ⚠臨界×{bl}" if bl else "") + flag)


if __name__ == "__main__":
    main()
