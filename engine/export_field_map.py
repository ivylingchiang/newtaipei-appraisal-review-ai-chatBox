# -*- coding: utf-8 -*-
"""地價查估書表審查對照總覽 — 表3／表4／表5 欄位對照的互動式 HTML

每一個儲存格／欄位可點選，顯示：
  應對照的表格與欄位、評價基準明細表級距、計算公式、審查交叉規則、
  目前資料狀態（題目原載／可查表／外部推算／代理判準／覆蓋不足／留白）、
  以及留白者目前替代使用的開放資料 API 或計算方式。

資料全部由 datasets/ 與 engine/ 之既有對照表推導，無手寫數值。
    python3 engine/export_field_map.py
"""
import os, sys, json, html

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from loader import Dataset                                        # noqa: E402
from compute import (derive_segment_levels, derive_table4_individual,  # noqa: E402
                     OBS_TO_ITEM, IND_FROM_SEGMENT, IND_UPSTREAM)
from export_xlsx import (T3_LEVEL_CELL, T3_OBS_CELL, T3_NA_CELLS,      # noqa: E402
                         T5_ROW, T5_SUBTOTAL_ROW, T5_TOTAL_ROW,
                         T5_BASE_COLS, T5_COMP_COLS, T5_SUBTOTAL_COL,
                         T4_COMP)
from export_v3 import FAC_CELLS                                   # noqa: E402
from preview_html import render_sheet, LEGEND                    # noqa: E402

REGION = "shulin"
OUT = os.path.join(ROOT, "output", "fieldMapping")
FORMS_SRC = os.path.join(ROOT, "output", "log", "fourthVersion")
# 「完整書表」的排列順序：表3 勘查 → 表4 比較法 → 表5 區域因素明細
# （標題以書表編號為準，不帶 preview_html.FILES 的 5-1 分號與檔名）
# key 供人工審查的修正清單標示改在哪一份書表，並對應回 FORMS_SRC 的檔名
FORM_FILES = [
    ("t3", "表3 地價區段勘查表", "表3_地價區段勘查表_已填.xlsx"),
    ("t4", "表4 比較法調查估價表", "表4_比較法調查估價表_已填.xlsx"),
    ("t5", "表5 影響地價區域因素分析明細表", "表5-1_影響地價區域因素分析明細表_已填.xlsx"),
]
ITEM2OBS = {v: k for k, v in OBS_TO_ITEM.items()}

# ────────────────────────────────────────────────────────────── 開放資料來源目錄
# 名稱與網址出自 doc/extraInfo/poi-links.md；信心等級判準見 thirdVersion/README §3
SOURCES = [
    {"id": "landmark", "name": "新北市重要地標資訊", "org": "新北市政府",
     "url": "https://data.ntpc.gov.tw/datasets/6dcff24a-838c-40fb-a9df-f1160afafe84",
     "conf": "A", "geo": "自帶座標",
     "fills": ["near_station", "near_school", "near_service", "near_tourism"],
     "note": "火車站、國中小高中、醫院、機關。捷運站 6 站全標示『施工中』，"
             "估價基準日 111.09.01 未通車，全數排除。"},
    {"id": "busstop", "name": "公車站位資訊", "org": "新北市政府",
     "url": "https://data.ntpc.gov.tw/datasets/34b402a8-53d9-483d-9406-24a682c2d6dc",
     "conf": "A", "geo": "自帶座標", "fills": ["near_busstop"],
     "note": "站牌 151 筆。屬站牌，不得代用為『客運站』。"},
    {"id": "parking", "name": "新北市路外公共停車場資訊", "org": "新北市政府",
     "url": "https://data.ntpc.gov.tw/datasets/b1464ef0-9c7c-4a6f-abf7-6bdf32847e68",
     "conf": "A", "geo": "自帶座標", "fills": ["parking", "parking_ease"],
     "note": "僅路外停車場；路邊停車格不在資料集內，不得據以判『無』。"},
    {"id": "interchange", "name": "高速公路交流道座標", "org": "交通部",
     "url": "https://data.gov.tw/dataset/166496", "conf": "A", "geo": "自帶座標",
     "fills": ["near_interchange"],
     "note": "樹林區基準明細表備註明定以直線距離計算，量測方式與判準一致。"},
    {"id": "dtm", "name": "2020 年版全臺 20 公尺網格 DTM", "org": "內政部國土測繪中心",
     "url": "https://data.gov.tw/dataset/138563", "conf": "A", "geo": "TWD97 TM2 網格",
     "fills": ["slope", "terrain", "drainage", "sunlight", "view"],
     "note": "傾斜度可完全自動判級（Horn 法 3×3 鄰域）；地勢／排水／日照／景觀僅能部分佐證。"
             "非 API，為 384 幅批次檔（新北市分幅 38.5 MB）。"},
    {"id": "funeral_moi", "name": "殯葬設施（全國）", "org": "內政部",
     "url": "https://data.gov.tw/dataset/7052", "conf": "B", "geo": "僅地址，座標須第三方補齊",
     "fills": ["funeral_facility"],
     "note": "5 筆無法定位（地址寫『保安街三段，7-11後方』『新北市樹林區無』等）→ 覆蓋不足。"},
    {"id": "cemetery_ntpc", "name": "公立公墓納骨塔查詢", "org": "新北市民政局",
     "url": "https://data.ntpc.gov.tw/datasets/1d228eab-23d4-41a6-bd33-f4014dd44660",
     "conf": "B", "geo": "僅地址", "fills": ["funeral_facility"], "note": "與內政部名冊交叉比對。"},
    {"id": "funeral_biz", "name": "禮儀服務業者查詢", "org": "新北市政府",
     "url": "https://data.ntpc.gov.tw/datasets/77676118-d894-4527-b88a-6d236a462923",
     "conf": "B", "geo": "僅地址", "fills": ["funeral_facility"], "note": "殯葬服務業，非設施本體。"},
    {"id": "incinerator", "name": "垃圾焚化廠位置", "org": "新北市政府",
     "url": "https://data.ntpc.gov.tw/datasets/39e17852-9ac9-45b7-bc60-d8d0ed7e3161",
     "conf": "B", "geo": "地址", "fills": ["waste_facility", "pollution"],
     "note": "與空污固定污染源雙來源地址一致，樹林焚化廠 1 筆。"},
    {"id": "air", "name": "空氣污染物監測設施之固定污染源", "org": "環境部",
     "url": "https://data.gov.tw/dataset/123721", "conf": "B", "geo": "地址",
     "fills": ["pollution"], "note": "樹林區僅焚化廠 1 筆，僅能覆蓋『廢氣污染』1 個子欄。"},
    {"id": "soil", "name": "土壤及地下水列管資訊", "org": "環境部",
     "url": "https://data.gov.tw/dataset/122974", "conf": "D", "geo": "僅地段地號，無座標",
     "fills": ["pollution"],
     "note": "樹林區 6 處，僅載地段地號；須先以地籍定位方可量距 → 本次未採用。"},
    {"id": "substation", "name": "二次變電所主變壓器裝置容量及負載", "org": "台灣電力公司",
     "url": "https://data.gov.tw/dataset/16960", "conf": "D", "geo": "所在地僅到『新北市樹林區』",
     "fills": ["utility_facility"], "note": "無法定位 → 改採 OSM power=*。"},
    {"id": "bank", "name": "金融機構基本資料查詢", "org": "金管會",
     "url": "https://data.gov.tw/dataset/6041", "conf": "D", "geo": "無座標",
     "fills": ["near_service"], "note": "樹林區 24 家有名冊無座標 → 改採 OSM amenity=bank（同為 24 家）。"},
    {"id": "market_ntpc", "name": "新北市公有市場及超市清冊", "org": "新北市政府",
     "url": "https://data.ntpc.gov.tw/datasets/785be91a-caaf-4e1c-91d6-f7d616d31a45",
     "conf": "D", "geo": "無座標", "fills": ["near_market"],
     "note": "樹林區僅 1 筆、全市超市僅 8 筆 → 改採 OSM marketplace／supermarket。"},
    {"id": "park_ntpc", "name": "新北市公園", "org": "新北市政府",
     "url": "https://data.ntpc.gov.tw/datasets/5fe3a136-29cc-4695-a17e-6636a32c3342",
     "conf": "D", "geo": "無座標，52% 無門牌", "fills": ["near_park"],
     "note": "樹林 25 筆中 13 筆無門牌號 → 改採 OSM leisure=park。"},
    {"id": "riverpark", "name": "河濱公園位置", "org": "新北市政府",
     "url": "https://data.ntpc.gov.tw/datasets/c3867812-6188-4b0a-a487-03bb4d93238d",
     "conf": "B", "geo": "地址", "fills": ["near_park"], "note": "一般公園之補充來源。"},
    {"id": "tourism", "name": "新北市觀光旅遊景點（中文）", "org": "新北市政府",
     "url": "https://data.ntpc.gov.tw/datasets/b3a30a19-4b89-4da2-8d99-18200dc5dfde",
     "conf": "B", "geo": "地址／座標", "fills": ["near_tourism"],
     "note": "Class1 代碼表未公開，清單含紀念碑／廟宇等非遊憩設施，須人工確認。"},
    {"id": "hotel", "name": "新北市合法一般旅館名冊", "org": "新北市政府",
     "url": "https://data.ntpc.gov.tw/datasets/8565597e-a174-4907-99c7-adb5ddee1326",
     "conf": "C", "geo": "地址", "fills": ["near_tourism"], "note": "觀光遊憩設施之輔助佐證。"},
    {"id": "dept", "name": "公司登記（依營業項目別）－百貨公司業", "org": "經濟部",
     "url": "https://data.gov.tw/dataset/45654", "conf": "C", "geo": "登記地址",
     "fills": ["near_market", "near_business"], "note": "登記地址非營業現址，僅供交叉比對。"},
    {"id": "osm", "name": "OpenStreetMap Overpass API", "org": "群眾協作（無機關背書）",
     "url": "https://overpass-api.de/api/interpreter", "conf": "C", "geo": "自帶座標",
     "fills": ["near_market", "near_park", "near_service", "utility_facility",
               "waste_facility", "near_business", "segment_center"],
     "note": "本案亦用於以界街幾何反推地價區段中心點（不確定半徑 25~66 m）。"
             "完整性與時效性均無保證。"},
    {"id": "lisp", "name": "地段代碼查詢（LISP／MMS）、國土測繪中心 ListLandSection",
     "org": "內政部", "url": "https://api.nlsc.gov.tw/other/ListLandSection/F/F17",
     "conf": "D", "geo": "僅段名↔段代碼對照", "fills": ["parcel_geometry"],
     "note": "實測回傳為 ISO 19115 圖資編目，無面積、四至座標全為 0；"
             "地籍圖形屬申購制，不在任何免費開放 API 上。"},
]
SRC_BY_ITEM = {}
for s in SOURCES:
    for f in s["fills"]:
        SRC_BY_ITEM.setdefault(f, []).append(s["id"])

# ─────────────────────────────────────────────── 區域因素 ↔ 個別因素 對應（避免重複修正）
REG2IND = {
    "zoning": [22], "bcr": [23], "far": [24],
    "build_ban": [25], "build_restrict": [25],
    "terrain": [12], "main_road_width": [14], "road_dev": [13],
    "near_school": [15], "near_market": [16, 19], "near_park": [17],
    "near_station": [18], "parking": [21],
    "utility_facility": [20], "funeral_facility": [20],
    "waste_facility": [20], "pollution": [20],
}
IND2REG = {}
for r, fns in REG2IND.items():
    for fn in fns:
        IND2REG.setdefault(fn, []).append(r)

# 表4 個別因素 13~21 於 fourthVersion 之替代填法（engine/export_v4.py）
IND_SUBSTITUTE = {
    "road_type": ("推定", "表3 區段『主要道路』推定為宗地面前道路種類",
                  "四個區段皆載有主要道路 → 同判第1級，差異率恆為 0.00%；"
                  "真正差異落在 14 面前道路寬度。"),
    "front_road_width": ("推定", "表3 區段『主要道路』寬度推定為宗地面前道路寬度",
                         "宗地若臨巷道，實際寬度遠小於區段主要道路；區段內道路平均寬度可作佐證。"),
    "near_school": ("外部推算", "表3 設施欄推算值（新北市重要地標，信心 A）", None),
    "near_market": ("外部推算OSM", "表3 設施欄推算值（OSM marketplace／supermarket，信心 C）", None),
    "near_park": ("外部推算OSM", "表3 設施欄推算值（OSM leisure=park，信心 C）", None),
    "near_station": ("外部推算", "表3 設施欄推算值（新北市重要地標，信心 A）", None),
    "near_business": ("代理判準", "OSM 零售聚集點（shop=mall／department_store／landuse=retail）最近者",
                      "18 個開放資料來源均無商圈範圍圖或名冊。本細項最大修正率 ±10%，"
                      "為接近條件群組中最大一項，必須由承辦單位認定商圈範圍後覆核。"),
    "nuisance": ("覆蓋不足", "表3 電業／殯葬／廢棄物／環境污染四類之最近者",
                 "殯葬 5 筆無法定位、掩埋場無來源、環境污染 5 子欄缺 4 → 推算值為樂觀上限。"),
    "parking_ease": ("代理判準", "路外公共停車場最近者，以 250m／500m 代理門檻分級",
                     "基準明細表『停車方便性』僅列優／普通／劣三級敘述，無距離門檻。"
                     "四段最近停車場皆在 250 M 內 → 同判『優』、差異率 0.00%，對結果無影響。"),
}

# ────────────────────────────────────────────────────────────────── 全案缺口清單
GAPS = [
    {"id": "G1", "title": "地價區段界線圖資（SHP／WFS）", "impact": "表3 全部設施欄之『本區段內／外』核取、所有距離之起算點",
     "affects": ["表3 設施欄 29 格核取方塊", "表5 全部 13 個設施類細項"], "max_pct": "間接影響全部",
     "current": "以 OSM 界街幾何求界街兩兩交會點，取形心為區段中心（不確定半徑 25~66 m）",
     "status": "替代中", "need": "地政局地價區段界線圖資；取得後可消除 8 組臨界判定並正確判定區段內外",
     "note": "目前表3『本區段內』核取方塊沒有任何一格被勾選 —— 這不代表沒有設施位於區段內，"
             "而是無界線可判定。某些基準表中『區段內有』自成一級，此欄誤判直接差一級。"},
    {"id": "G2", "title": "宗地地籍圖形（面積／寬度／深度／形狀／臨街情形）", "impact": "表4 個別因素 7~11",
     "affects": ["表4 #7 面積", "表4 #8 寬度", "表4 #9 深度", "表4 #10 形狀", "表4 #11 臨街情形"],
     "max_pct": "±10 / ±5 / ±5 / ±5 / ±10 ＝ 合計 ±35%",
     "current": "無替代。LISP／NLSC 僅提供段名↔段代碼；地籍圖形屬臨櫃或線上申購制",
     "status": "無替代", "need": "4 筆地號之宗地多邊形（地籍圖申購／地政局 WFS），或表7 宗地個別因素清冊"},
    {"id": "G3", "title": "表7 宗地個別因素清冊", "impact": "表4 比準地（宗地流水號 0003）條件欄 7~25",
     "affects": ["表4 比準地條件欄 D9:D27"], "max_pct": "—",
     "current": "以表3 區段層級記載推定（地勢、道路、行政條件）",
     "status": "替代中", "need": "需用土地人提供之表7；比準地在徵收範圍內，表7 同編號欄位即可直接抄錄"},
    {"id": "G4", "title": "比較標的宗地之個別因素勘查資料", "impact": "表4 比較標的條件欄 7~25",
     "affects": ["表4 G/K/O 欄 條件", "表4 J/N/R 欄 差異率"], "max_pct": "—",
     "current": "以表3 各該區段層級記載推定（同區段內所有宗地得到相同值，不具宗地個別性）",
     "status": "替代中", "need": "查估單位就各該買賣實例宗地另行勘查（表1-1 僅載坐落、面積、交易日期、正常單價）"},
    {"id": "G5", "title": "殯葬設施完整座標", "impact": "表5 (6) 特殊設施小計 → 總修正數",
     "affects": ["表3 T18", "表5 第35列", "表4 #20 嫌惡設施"], "max_pct": "±10%",
     "current": "內政部＋新北市民政局名冊 × OSM landuse=cemetery 交叉比對（33 筆）",
     "status": "覆蓋不足（不採用）",
     "need": "5 筆名冊設施之座標。P001-00 距樹林區第五公墓僅 123 M —— 列為外業第 1 優先查證"},
    {"id": "G6", "title": "垃圾場或掩埋場位置", "impact": "表5 (6) 特殊設施小計 → 總修正數",
     "affects": ["表3 T23", "表5 第36列", "表4 #20"], "max_pct": "±15%（廢棄物處理設施）",
     "current": "18 個開放資料來源皆無；OSM 亦為 0 筆。污水處理場僅 OSM 1 筆",
     "status": "覆蓋不足（不採用）", "need": "環保局掩埋場、污水處理場位置清冊"},
    {"id": "G7", "title": "環境污染 5 子欄缺 4", "impact": "表5 (7) 環境污染小計 → 總修正數",
     "affects": ["表3 T25 水污染", "表3 T26 噪音污染", "表3 T28 廢棄物污染", "表3 T29 其他污染",
                 "表5 第38列"], "max_pct": "±20%（單項最大）",
     "current": "僅廢氣污染有來源（空污固定污染源，樹林區 1 筆）；土壤列管檔 6 處僅載地段地號",
     "status": "覆蓋不足（不採用）", "need": "噪音監測資料；土壤／地下水列管地號之地籍定位"},
    {"id": "G8", "title": "台電輸配電設施座標", "impact": "表5 (6) 電業設施判級之可信度",
     "affects": ["表3 T14", "表5 第34列"], "max_pct": "±10%",
     "current": "OSM power=*（83 座高壓鐵塔＋變電所，信心 C）。四段皆判 5 劣 → 修正率 0.00%",
     "status": "替代中（風險低）", "need": "向台電索取輸配電設施座標；台電開放檔『所在地』僅到區級"},
    {"id": "G9", "title": "商圈範圍圖或名冊", "impact": "表4 #19 接近商圈之程度",
     "affects": ["表4 第21列"], "max_pct": "±10%（接近條件群組最大）",
     "current": "代理判準：OSM 零售聚集點（shop=mall／department_store／landuse=retail）最近者",
     "status": "代理判準", "need": "承辦單位認定之商圈範圍。推算結果已落在 −5.00%，必須覆核"},
    {"id": "G10", "title": "停車方便性之距離門檻", "impact": "表4 #21 停車方便性",
     "affects": ["表4 第23列"], "max_pct": "±5%",
     "current": "代理判準：以接近條件群組共用之 250m／500m 門檻代理三級敘述",
     "status": "代理判準（風險低）", "need": "基準明細表僅列『優／普通／劣』敘述。"
     "四段最近停車場皆在 250 M 內 → 同判優、差異率 0.00%，對結果無影響"},
    {"id": "G11", "title": "高鐵站、客運站、捷運站", "impact": "表3 大型車站子欄",
     "affects": ["表3 H13 高鐵站", "表3 H15 客運站", "表3 H16 捷運站"], "max_pct": "±10%（接近大型車站）",
     "current": "高鐵：新北市境內無；客運站：無對應開放資料（公車站位屬站牌不得代用）；"
                "捷運：樹林區 6 站全標示『施工中』，估價基準日未通車 → 有證據排除",
     "status": "留白（唯一有證據之『無』為捷運站）",
     "need": "客運站點位清冊。此三格一律留白標紅，沒有一格被填成『無』"},
    {"id": "G12", "title": "大專院校、廣場徒步區", "impact": "表3 學校／公園子欄",
     "affects": ["表3 I38 大專院校", "表3 I44 廣場、徒步區"], "max_pct": "±8%（兩細項各）",
     "current": "大專院校：樹林區 0 所，有效半徑 1,000 M 內亦無；廣場徒步區：無對應開放資料",
     "status": "留白", "need": "實地勘查確認。正向設施留白＝最劣級，不得逕填『無』"},
    {"id": "G13", "title": "24 容積率之個別因素差異率", "impact": "表4 #24",
     "affects": ["表4 第26列 差異率"], "max_pct": "基準表未列上限（敘述型）",
     "current": "無。基準明細表列為敘述型（以土地開發分析法試算調整），無查表矩陣",
     "status": "無替代（待試算）",
     "need": "都市計畫書容積規定＋土地開發分析法試算；並須與表5 容積率修正擇一（手冊六(九) 禁止重複修正）"},
    {"id": "G14", "title": "路線距離（routing）", "impact": "所有須通達之正向設施判級",
     "affects": ["表3 學校／市場／公園／車站／站牌／停車場／服務性設施", "表4 #15~#19"],
     "max_pct": "系統性偏誤，非單項",
     "current": "一律採直線距離。直線距離恆 ≤ 路線距離 → 系統性高估便利性，等級偏優",
     "status": "已知系統性偏誤",
     "need": "路網 routing 服務。手冊伍、一(二)8(3)：須通達者宜採路線距離，"
             "嫌惡設施採直線距離即可（故嫌惡設施之量測方式已與手冊一致）"},
    {"id": "G15", "title": "表5 總修正數 → 表4 整條價格鏈", "impact": "表4 區域因素調整率以下全部欄位",
     "affects": ["表4 J8/N8/R8 區域因素調整百分率", "表4 第29列 個別因素合計",
                 "表4 第30列 調整百分率絕對值加總／相近程度", "表4 第31列 試算價格／權重",
                 "表4 G32 比準地比較價格"], "max_pct": "—",
     "current": "不予產出。(6)(7) 小計不成立，缺口 ±55% 大於已算出之 ±26.25%",
     "status": "連鎖阻斷", "need": "補齊 G5～G7 後表5 總修正數方成立，價格鏈才能往下計算"},
]

MANUAL = {
    "dist_origin": "手冊 伍、一、(二)6：距離自本地價區段中心點起算",
    "dist_max": "手冊 伍、一、(二)8(2)：同一細項有多處設施時，取對地價影響最大者（＝最近者）",
    "dist_kind": "手冊 伍、一、(二)8(3)：須通達者宜採路線距離；嫌惡設施採直線距離",
    "threshold": "手冊 伍、一、(二)8(1)：級距門檻因地制宜，以該區該用地別之評價基準明細表為準",
    "t5_purpose": "手冊 伍、五、(六)1：表5 係掌握各地價區段間設施之相對距離關係",
    "t5_before_t4": "手冊 肆、步驟6：表5 須先於表4，因表4 之區域因素調整百分率引用表5 總修正數",
    "no_double": "手冊 伍、六、(九)：區域因素與個別因素項目雷同者，已於一方完全反應者不得重複調整",
    "exempt": "手冊 伍、六、(七)2、七、(四)1：免修正項目條件欄與差異率填『-』；應修正但無差異者填 0",
    "flexible": "手冊 伍、六、(八)4：情況特殊者得於備註欄敘明理由後酌予調整，"
                "惟仍應在內政部評價基準表規定之最大影響範圍內",
    "review_iii": "手冊 參、七、(一) 審查重點 iii：各用地別應評價之細項是否皆已填載、"
                  "優劣等級是否依區域因素評價基準明細表填列",
    "review_vi": "手冊 參、七、(一) 審查重點 vi：表5 修正細項優劣等級是否與各該表3 一致；"
                 "修正百分比是否依區域因素評價基準明細表調整",
    "review_vii": "手冊 參、七、(一) 審查重點 vii：表4 區域因素調整百分率與表5 總修正數相符；"
                  "個別因素差異率依個別因素評價基準明細表填列；各比較標的權重是否符合邏輯",
    "levels": "手冊 伍、六、(八)2：表3 左側 [N][M] 表示第 N 級／共 M 級",
    "weight": "手冊 伍、六、(十一)＋不動產估價技術規則第27條：以調整百分率絕對值加總衡量"
              "價格形成因素之相近程度，加總愈大→權重愈小",
    "round": "土地徵收補償市價查估辦法第21條：宗地市價與比準地地價之尾數無條件進位；"
             "表4 比準地比較價格例外，四捨五入至個位數",
}


# 本案專屬規則（doc/rules/extra.md ＋ 承辦單位確認）掛到受影響之細項
CASE_RULE_ITEM = {
    "zoning": ("CR1", "捷運開發區以「變更前」之使用分區認定",
               "P001-00 之 scope_desc 載明「捷運開發區(變更前為第一種住宅區)」，"
               "使用分區之優劣等級依變更前之第一種住宅區查表 → 樹林住宅基準表「稍優」(第2級)。"
               "表3『土地利用現況』勾選之「商業用」屬現況描述，不作為使用分區優劣判定依據。"),
    "far": ("CR2", "8公尺以下道路旁住宅區之基準容積率為200%",
            "交叉檢核用：都市計畫內住宅區且主要道路寬 ≤8m 且無特別獎勵者，"
            "基準容積率常規劃為 200%。不符者標記待確認，不逕行判錯（severity: warning）。"
            "本案 P001-00 主要道路寬 28m，CR2 不適用。"),
}


def rate_cell(item, base_rank, comp_rank, direction):
    """回傳兩種方向之查表說明"""
    step = item.get("step")
    if step is None:
        return None
    if direction == "regional":
        return {"expr": "修正百分比 ＝（比較標的等級序號 − 比準地等級序號）× 級距",
                "equiv": "≡ matrix[比準地等級−1][比較標的等級−1]",
                "sign": "比較標的級距數字較大（條件較劣）→ 修正百分比為正",
                "step": step}
    return {"expr": "差異率 ＝（比較標的等級序號 − 比準地等級序號）× 級距",
            "equiv": "≡ matrix[比準地等級−1][比較標的等級−1]",
            "sign": "比較標的條件較差 → 差異率為正",
            "step": step}


def build():
    ds = Dataset()
    reg = ds.criteria(REGION, "regional")
    ind = ds.criteria(REGION, "individual")
    segs = ds.segments(REGION)
    case = list(ds.cases(REGION).values())[0]
    seg_order = case["table5"]["segment_nos"]
    base_no, comps = seg_order[0], seg_order[1:]
    inf = json.load(open(os.path.join(ROOT, "datasets", "external",
                                      "poi_inference.json"), encoding="utf-8"))
    levels = {sn: derive_segment_levels(ds, REGION, segs[sn]) for sn in seg_order}
    t4i = derive_table4_individual(ds, REGION, case, segs)

    # 設施子欄：item → [{cell, name, note, candidate_count, unlocatable}]
    fac_subs = {c: e["subs"] for c, e in inf["items"].items()}
    fac_cov = {c: e["coverage"] for c, e in inf["items"].items()}

    # ─────────────────────────────────────────────── 區域因素細項（表3 ↔ 表5）
    reg_fields = []
    for code, it in sorted(reg.items(), key=lambda kv: kv[1]["seq"]):
        seq = it["seq"]
        row5 = T5_ROW.get(seq)
        lvl_cell = T3_LEVEL_CELL.get(code)
        obs_code = ITEM2OBS.get(code)
        fact_cell = T3_OBS_CELL.get(obs_code) if obs_code else None
        subs = fac_subs.get(code)
        cov = fac_cov.get(code)

        # 現況
        base_lv = levels[base_no][0].get(code)
        base_gap = levels[base_no][1].get(code)
        if code in inf["items"]:
            if not cov["usable_for_grading"]:
                status, status_label = "insufficient", "覆蓋不足（不得判級）"
            else:
                confs = {s.get("confidence") for sn in seg_order
                         for s in [(inf["items"][code]["by_segment"].get(sn) or {})
                                   .get("aggregated") or {}] if s.get("confidence")}
                status = "ext" if confs <= {"A", "B"} else "ext_osm"
                status_label = ("外部推算（官方名冊 A／B）" if status == "ext"
                                else "外部推算（OpenStreetMap，信心 C）")
        elif code == "other":
            status = "ok"
            status_label = ("題目原載：doc/題目.pdf 表5 原已填載「等級－／無／修正 0.00」，"
                            "屬源文件既有資料，非推導值")
        elif base_lv:
            status, status_label = "ok", "題目原載事實 → 可直接查表判級"
        else:
            status, status_label = "missing", "表3 未載，無法判級"

        # 距離／門檻說明
        thresholds = [{"rank": lv["rank"], "label": lv["label"],
                       "criterion": lv.get("criterion") or "（基準表未列）"}
                      for lv in it["levels"]]

        # 各區段現況
        per_seg = []
        for sn in seg_order:
            lv = levels[sn][0].get(code)
            e = (inf["items"].get(code) or {}).get("by_segment", {}).get(sn) or {}
            if e.get("rank"):
                agg = e.get("aggregated") or {}
                fac = agg.get("facility", "")
                if fac in ("(未命名)", "（未命名）"):
                    fac = "OSM 未命名圖徵"
                per_seg.append({"seg": sn, "rank": e["rank"], "label": e.get("level_label"),
                                "value": fac,
                                "detail": f"{agg.get('sub','')}：{fac} {agg.get('distance_m','')} M",
                                "src": (e.get("aggregated") or {}).get("source"),
                                "conf": (e.get("aggregated") or {}).get("confidence"),
                                "borderline": e.get("borderline")})
            elif lv:
                iv = lv.get("input") or {}
                if iv.get("items") is not None:
                    dtl = (f"已勾選 {len(iv['items'])} 項："
                           + "、".join(iv["items"]) if iv["items"] else "未勾選任何項目")
                else:
                    dtl = str(iv.get("value") if iv.get("value") is not None
                              else (iv.get("category") or ""))
                per_seg.append({"seg": sn, "rank": lv["rank"], "label": lv["label"],
                                "detail": dtl,
                                "src": "doc/題目.pdf 表3", "conf": None, "borderline": False})
            elif code == "other":
                per_seg.append({"seg": sn, "rank": None, "label": "無",
                                "detail": "題目原載：等級欄「－」、優劣等級「無」、修正百分比 0.00",
                                "src": "doc/題目.pdf 表5", "conf": None, "borderline": False})
            else:
                per_seg.append({"seg": sn, "rank": None, "label": None,
                                "detail": levels[sn][1].get(code) or "資料不足",
                                "src": None, "conf": None, "borderline": False})

        reg_fields.append({
            "id": f"reg.{code}", "kind": "regional", "code": code, "seq": seq,
            "name": it["item_name"], "group": it["group_code"], "group_name": it["group_name"],
            "level_count": it["level_count"], "level_labels": it.get("level_labels"),
            "max_adjustment": it["max_adjustment"], "step": it.get("step"),
            "direction": it.get("direction"), "rule_type": it.get("rule_type"),
            "matrix": it.get("matrix"), "thresholds": thresholds,
            "t3": {"level_cell": lvl_cell[0] if lvl_cell else None,
                   "count_cell": lvl_cell[1] if lvl_cell else None,
                   "fact_cell": fact_cell,
                   "fact_field": (segs[base_no]["observations"].get(obs_code) or {})
                                 .get("field_name") if obs_code else None,
                   "subs": subs},
            "t5": {"row": row5,
                   "base_rank_cell": f"{T5_BASE_COLS[0]}{row5}" if row5 else None,
                   "base_label_cell": f"{T5_BASE_COLS[1]}{row5}" if row5 else None,
                   "comp_cells": [{"seg": comps[i],
                                   "rank": f"{T5_COMP_COLS[i][0]}{row5}",
                                   "label": f"{T5_COMP_COLS[i][1]}{row5}",
                                   "pct": f"{T5_COMP_COLS[i][2]}{row5}"}
                                  for i in range(len(comps))] if row5 else [],
                   "subtotal_row": T5_SUBTOTAL_ROW.get(it["group_code"])},
            "t4_fields": REG2IND.get(code, []),
            "coverage": cov, "status": status, "status_label": status_label,
            "gap": None if code == "other" else base_gap, "per_seg": per_seg,
            "sources": SRC_BY_ITEM.get(code, []),
            "case_rule": CASE_RULE_ITEM.get(code),
            "manual": [MANUAL["threshold"], MANUAL["review_iii"], MANUAL["review_vi"]]
                      + ([MANUAL["dist_origin"], MANUAL["dist_max"], MANUAL["dist_kind"]]
                         if code in inf["items"] else [])
                      + ([MANUAL["no_double"]] if code in REG2IND else []),
            "lookup": rate_cell(it, None, None, "regional"),
        })

    # ─────────────────────────────────────────────── 個別因素細項（表4）
    t4rows = {r["item_code"]: r for r in t4i["rows"]}
    ind_fields = []
    for code, it in sorted(ind.items(), key=lambda kv: kv[1]["seq"]):
        fn = it.get("field_no")
        row = (fn + 2) if fn else 28
        r = t4rows.get(code, {})
        sub = IND_SUBSTITUTE.get(code)
        if code in IND_FROM_SEGMENT or code == "build_ban_restrict":
            status = "derived" if r.get("status") == "確認" else "assumed"
            status_label = ("表3 區段法定管制值 → 宗地一致（可確認）" if status == "derived"
                            else "表3 區段層級推定至宗地層級")
        elif sub:
            kind = sub[0]
            status = {"推定": "assumed", "外部推算": "ext", "外部推算OSM": "ext_osm",
                      "代理判準": "proxy", "覆蓋不足": "insufficient"}[kind]
            status_label = {"推定": "表3 區段層級推定至宗地層級",
                            "外部推算": "外部推算（官方名冊 A／B）→ 區段層級",
                            "外部推算OSM": "外部推算（OpenStreetMap，信心 C）→ 區段層級",
                            "代理判準": "代理判準（級距或設施定義由本專案代設）",
                            "覆蓋不足": "覆蓋不足（等級為樂觀上限）"}[kind]
        elif it.get("rule_type") != "matrix":
            status, status_label = "narrative", "基準表列為敘述型，無查表矩陣"
        else:
            status, status_label = "missing", "無宗地層級勘查資料，留白退補"

        ind_fields.append({
            "id": f"ind.{code}", "kind": "individual", "code": code, "seq": it["seq"],
            "field_no": fn, "name": it["item_name"],
            "group": it["group_code"], "group_name": it["group_name"],
            "level_count": it.get("level_count"), "level_labels": it.get("level_labels"),
            "max_adjustment": it.get("max_adjustment"), "step": it.get("step"),
            "direction": it.get("direction"), "rule_type": it.get("rule_type"),
            "matrix": it.get("matrix"),
            "thresholds": [{"rank": lv["rank"], "label": lv["label"],
                            "criterion": lv.get("criterion") or "（基準表未列）"}
                           for lv in it.get("levels", [])],
            "notes": it.get("notes"), "basis": it.get("basis"),
            "t4": {"row": row, "base_cell": f"D{row}",
                   "comp_cells": [{"seg": comps[i], "cond": f"{T4_COMP[i][0]}{row}",
                                   "cond2": f"{T4_COMP[i][1]}{row}",
                                   "diff": f"{T4_COMP[i][2]}{row}"}
                                  for i in range(len(comps))]},
            "upstream": IND_UPSTREAM.get(it["group_code"]),
            "from_segment": IND_FROM_SEGMENT.get(code, [None, None, None])[2]
                            if code in IND_FROM_SEGMENT else None,
            "reg_items": IND2REG.get(fn, []) if fn else [],
            "substitute": {"kind": sub[0], "how": sub[1], "warn": sub[2]} if sub else None,
            "status": status, "status_label": status_label,
            "gap": r.get("gap"),
            "sources": SRC_BY_ITEM.get(code, []),
            "manual": [MANUAL["threshold"], MANUAL["review_vii"]]
                      + ([MANUAL["no_double"]] if (fn in IND2REG if fn else False) else [])
                      + ([MANUAL["dist_kind"], MANUAL["dist_max"]] if code in
                         ("near_school", "near_market", "near_park", "near_station",
                          "near_business", "nuisance", "parking_ease") else [])
                      + ([MANUAL["exempt"], MANUAL["flexible"]]),
            "lookup": rate_cell(it, None, None, "individual"),
        })

    # ─────────────────────────────────────────────── 表3 其他欄位（無評價細項對應）
    t3_extra = []
    obs = segs[base_no]["observations"]
    for oc, cell in T3_OBS_CELL.items():
        if OBS_TO_ITEM.get(oc):
            continue
        t3_extra.append({"cell": cell, "name": (obs.get(oc) or {}).get("field_name", oc),
                         "code": oc,
                         "raw": (obs.get(oc) or {}).get("raw"),
                         "why": "普通住宅用地之評價基準明細表無此細項；表3 仍為勘查記錄欄位，"
                                "供區段特性描述與後續用地別轉換使用"})
    for cell, nm in sorted(T3_NA_CELLS.items()):
        t3_extra.append({"cell": cell, "name": nm, "code": None, "raw": None,
                         "why": "普通住宅用地之評價基準明細表無此細項 → 等級欄留空並標為『不適用』"
                                "（不得填 0，亦不得填『無』）"})

    payload = {
        "case": {"case_no": case["case_no"], "region": "新北市樹林區",
                 "land_use": case["table5"].get("land_use_label"),
                 "date": "民國111年9月1日（西元 2022-09-01）",
                 "base_segment": base_no, "comparables": comps,
                 "criteria_table": "doc/rules/評價基準明細表.pdf（樹林區·普通住宅用地）",
                 "manual": "doc/rules/土地徵收補償市價查估作業手冊.pdf（內政部，169頁）"},
        "regional": reg_fields, "individual": ind_fields, "t3_extra": t3_extra,
        "t5_layout": {"subtotal_rows": T5_SUBTOTAL_ROW, "total_row": T5_TOTAL_ROW,
                      "subtotal_cols": T5_SUBTOTAL_COL[:len(comps)],
                      "base_cols": list(T5_BASE_COLS),
                      "comp_cols": [list(c) for c in T5_COMP_COLS[:len(comps)]]},
        "t4_layout": {"comp_cols": [list(c) for c in T4_COMP[:len(comps)]]},
        "sources": SOURCES, "gaps": GAPS, "manual_refs": MANUAL,
        "formulas": ds.common["formulas"], "review_rules": ds.common["review_rules"],
        "case_rules": ds.common["case_rules"], "forms": ds.common["forms"],
        "checks_implemented": ["R1", "R2", "R4", "R6", "R7", "R12", "R14"],
        # 人工審查改完要回寫哪一份原始 xlsx（服務端據此開檔套用修正）
        "form_files": [{"key": k, "title": t, "file": f} for k, t, f in FORM_FILES],
        "forms_src": os.path.basename(FORMS_SRC),
    }
    return payload


def forms_html():
    """「完整書表」分頁：表3 → 表5 → 表4 三份已填 xlsx 的完整版面。

    與 output/fourthVersion/預覽.html 共用 preview_html.render_sheet，
    底色、合併儲存格與填表依據（title 提示）皆與該頁一致。

    這裡以 editable=True 渲染：每個 table 帶 data-file／data-sheet，每個儲存格
    帶 data-ref，有底色（非「不適用」）者可直接改，供人工審查更正 AI 判定。
    """
    import openpyxl

    legend = "".join(f'<span class="lg"><i style="background:#{c}"></i>{n}</span>'
                     for n, c in LEGEND)
    parts = [f"<p>{legend}</p>"]
    sheets = 0
    for key, title, fn in FORM_FILES:
        path = os.path.join(FORMS_SRC, fn)
        if not os.path.exists(path):
            parts.append(f"<h2>{html.escape(title)}</h2>"
                         f'<div class="empty">找不到 {html.escape(fn)}，'
                         "請先執行 engine/export_v4.py</div>")
            continue
        wb = openpyxl.load_workbook(path)
        parts.append(f"<h2>{html.escape(title)}</h2>")
        for ws in wb.worksheets:
            if ws.title == "填表依據":
                continue
            parts.append(f"<h3>工作表：{html.escape(ws.title)}</h3>")
            parts.append(f'<div class="scroll" data-file="{key}">'
                         + render_sheet(ws, editable=True) + "</div>")
            sheets += 1
    return "\n".join(parts), sheets


def render(payload, forms):
    with open(os.path.join(HERE, "field_map_template.html"), encoding="utf-8") as f:
        tpl = f.read()
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return tpl.replace("/*__DATA__*/null", blob).replace("<!--__FORMS__-->", forms)


def main():
    os.makedirs(OUT, exist_ok=True)
    payload = build()
    forms, sheets = forms_html()
    p = os.path.join(OUT, "index.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(render(payload, forms))
    print(f"  區域因素 {len(payload['regional'])} 細項｜個別因素 {len(payload['individual'])} 細項"
          f"｜表3 其他 {len(payload['t3_extra'])} 欄｜缺口 {len(payload['gaps'])} 項"
          f"｜資料來源 {len(payload['sources'])} 個｜完整書表 {sheets} 張工作表")
    print(f"  -> {os.path.relpath(p, ROOT)}")


if __name__ == "__main__":
    main()
