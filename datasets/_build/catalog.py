# -*- coding: utf-8 -*-
"""細項目錄（curated）— 依 PDF 中出現順序，對應解析出的矩陣區塊"""

# (group_code, group_name, item_code, item_name, field_no)
SHULIN_REGIONAL = [
    (1,"土地使用管制","urban_plan","都市計畫（內、外）",None),
    (1,"土地使用管制","zoning","使用分區（使用地類別）",None),
    (1,"土地使用管制","bcr","建蔽率",None),
    (1,"土地使用管制","far","容積率",None),
    (1,"土地使用管制","build_ban","有無禁止建築",None),
    (1,"土地使用管制","build_restrict","有無限制建築（整體開發、面積限制、高度限制……等）",None),
    (2,"交通運輸","main_road_width","主要道路寬度",None),
    (2,"交通運輸","avg_road_width","區段內道路平均寬度",None),
    (2,"交通運輸","near_station","接近大型車站之程度",None),
    (2,"交通運輸","near_busstop","站牌之接近程度或密集程度",None),
    (2,"交通運輸","near_interchange","交流道之有無及接近交流道之程度",None),
    (2,"交通運輸","road_dev","區段內道路規劃及闢建程度",None),
    (3,"自然條件","sunlight","日照",None),
    (3,"自然條件","view","景觀",None),
    (3,"自然條件","slope","傾斜度",None),
    (3,"自然條件","drainage","排水之良否",None),
    (3,"自然條件","terrain","地勢",None),
    (4,"土地改良","land_improve","建築基地改良（整平或填挖基地、開挖水溝、水土保持、鋪築道路、埋設管道、修築駁嵌等）或其他改良",None),
    (5,"公共建設","near_school","接近學校之程度（國小、國中、高中、大專院校）",None),
    (5,"公共建設","near_market","接近市場之程度（傳統市場、超級市場、超大型購物中心）",None),
    (5,"公共建設","near_park","接近公園（里鄰公園、一般公園）、廣場、徒步區之程度",None),
    (5,"公共建設","near_tourism","接近觀光遊憩設施之程度",None),
    (5,"公共建設","parking","停車場地之便利程度",None),
    (5,"公共建設","near_service","接近服務性設施的程度（郵局、銀行、醫院、機關等設施）",None),
    (6,"特殊設施","utility_facility","電業設施及公用氣體燃料設施之有無及接近程度",None),
    (6,"特殊設施","funeral_facility","殯葬設施之有無及接近程度",None),
    (6,"特殊設施","waste_facility","廢棄物處理設施之有無及接近程度",None),
    (7,"環境污染","pollution","水污染、噪音污染、廢氣污染、廢棄物污染等之有無及接近程度",None),
    (8,"其他影響因素","other","其他影響因素",None),
]

SHULIN_INDIVIDUAL = [
    (1,"宗地條件","area","面積",7),
    (1,"宗地條件","width","寬度",8),
    (1,"宗地條件","depth","深度",9),
    (1,"宗地條件","shape","形狀",10),
    (1,"宗地條件","street_frontage","臨街情形",11),
    (1,"宗地條件","terrain","地勢",12),
    (2,"道路條件","road_type","道路種類",13),
    (2,"道路條件","front_road_width","面前道路寬度",14),
    (3,"接近條件","near_school","接近學校之程度",15),
    (3,"接近條件","near_market","接近市場之程度",16),
    (3,"接近條件","near_park","接近公園、廣場之程度",17),
    (3,"接近條件","near_station","接近車站之程度",18),
    (3,"接近條件","near_business","接近商圈之程度",19),
    (4,"周邊環境條件","nuisance","嫌惡設施之有無",20),
    (4,"周邊環境條件","parking_ease","停車方便性",21),
    (5,"行政條件","zoning","使用分區或編定",22),
    (5,"行政條件","bcr","建蔽率",23),
    (5,"行政條件","build_ban_restrict","有無禁限建",25),
    (6,"其他","dead_end_alley","無尾巷",None),
]

JINSHAN_REGIONAL = [
    (1,"土地使用管制","urban_plan","都市計畫（內、外）",None),
    (1,"土地使用管制","zoning","使用分區（編定）",None),
    (1,"土地使用管制","bcr","建蔽率",None),
    (1,"土地使用管制","far","容積率",None),
    (1,"土地使用管制","build_ban","有無禁止建築",None),
    (1,"土地使用管制","build_restrict","有無限制建築",None),
    (2,"交通運輸","main_road_width","主要道路寬度",None),
    (2,"交通運輸","avg_road_width","區段內道路平均寬度",None),
    (2,"交通運輸","near_station","接近大型車站之程度",None),
    (2,"交通運輸","near_busstop","站牌之接近程度或密集程度",None),
    (2,"交通運輸","near_interchange","交流道之有無及接近交流道之程度",None),
    (2,"交通運輸","road_dev","區段內道路規劃及闢建程度",None),
    (3,"自然條件","drainage","排水之良否",None),
    (3,"自然條件","terrain","地勢",None),
    (4,"公共建設","near_market","接近市場之程度（傳統市場、超級市場、超大型購物中心）",None),
    (4,"公共建設","near_park","接近公園（里鄰公園、一般公園）、廣場、徒步區之程度",None),
    (4,"公共建設","near_tourism","接近觀光遊憩設施之程度",None),
    (4,"公共建設","parking","停車場地之便利程度",None),
    (5,"特殊設施","utility_facility","電業設施及公用氣體燃料設施之有無及接近程度",None),
    (5,"特殊設施","funeral_facility","殯葬設施之有無及接近程度",None),
    (5,"特殊設施","waste_facility","廢棄物處理設施之有無及接近程度",None),
    (6,"環境污染","pollution","水污染、噪音污染、廢氣污染、廢棄物污染等之有無及接近程度",None),
    (7,"工商活動","dept_store","百貨公司之有無、數量、接近程度",None),
    (7,"工商活動","financial","金融機構之有無、數量、接近程度",None),
    (7,"工商活動","entertainment","娛樂設施之有無、數量、接近程度",None),
    (7,"工商活動","exhibition_hotel","大型展示中心或觀光飯店之有無、數量、接近程度",None),
    (7,"工商活動","customer_flow","顧客通行量之多寡",None),
    (7,"工商活動","shop_adjacency","店舖之毗連狀態",None),
]

JINSHAN_INDIVIDUAL = [
    (1,"宗地條件","area","面積",7),
    (1,"宗地條件","width","寬度",8),
    (1,"宗地條件","depth","深度",9),
    (1,"宗地條件","shape","形狀",10),
    (1,"宗地條件","street_frontage","臨街情形",11),
    (1,"宗地條件","terrain","地勢",12),
    (2,"道路條件","road_type","道路種類",13),
    (2,"道路條件","front_road_width","面前道路寬度",14),
    (3,"接近條件","near_school","接近學校之程度",15),
    (3,"接近條件","near_market","接近市場之程度",16),
    (3,"接近條件","near_park","接近公園、廣場之程度",17),
    (3,"接近條件","near_station","接近車站之程度",18),
    (3,"接近條件","near_business","接近商圈之程度",19),
    (4,"周邊環境條件","nuisance","嫌惡設施之有無",20),
    (4,"周邊環境條件","parking_ease","停車方便性",21),
    (5,"行政條件","zoning","使用分區或編定",22),
    (5,"行政條件","bcr","建蔽率",23),
    (5,"行政條件","far","容積率",24),
    (5,"行政條件","build_ban_restrict","有無禁限建",25),
]

# 跨行截斷之備註修補 (block_index, level_label) -> 正確文字
NOTE_OVERRIDES = {
    "shulin": {
        (1,  "普通"): "甲建、乙建、特定專用區、多目標使用之其他公共設施用地",
        (44, "普通"): "甲建、乙建、特定專用區、多目標使用之其他公共設施用地",
        (29, "優"):   "600m2以上",
    },
    "jinshan": {},
}

# 樹林個別因素「容積率」無矩陣，以備註方式規定
SHULIN_FAR_INDIVIDUAL = {
    "item_code": "far", "item_name": "容積率", "field_no": 24,
    "group_code": 5, "group_name": "行政條件",
    "level_count": None, "max_adjustment": None, "step": None,
    "matrix": None, "levels": [],
    "rule_type": "narrative",
    "basis": "詳備註",
    "notes": [
        "容積率差異以土地開發分析法進行試算調整",
        "本項需與區域因素容積率併同考量，調整不足者另於區域因素補充調整",
    ],
}

# 來源資料已知瑕疵（OCR/原文誤植）
SOURCE_ANOMALIES = {
    "jinshan": [
        {"item_code":"near_busstop","factor_type":"regional","level":3,
         "text":"200km以上未滿400m","issue":"單位誤植 km，應為 m","parsed_as":"200m以上未滿400m"},
        {"item_code":"near_tourism","factor_type":"regional","level":4,
         "text":"1,000km以上未滿1,500m","issue":"單位誤植 km，應為 m","parsed_as":"1,000m以上未滿1,500m"},
    ],
    "shulin": [],
}
