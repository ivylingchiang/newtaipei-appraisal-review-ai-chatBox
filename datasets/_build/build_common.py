# -*- coding: utf-8 -*-
"""建置跨區域共用知識：表單體系、計算規則、審查檢核清單、跨表參照矩陣"""
import os, json
import yaml

OUT = "datasets/common"
os.makedirs(OUT, exist_ok=True)
SRC = "doc/rules/土地徵收補償市價查估作業手冊.pdf"

FORMS = {
    "schema_version": "1.0",
    "source": {"pdf": SRC, "section": "肆、土地徵收補償市價查估書表製作流程"},
    "note": "條次為「土地徵收補償市價查估辦法」條次",
    "forms": [
        {"code":"表1-1","range":"表1-1~表1-3","article":"6~8","name":"買賣實例調查估價表","producer":"查估單位","count":3},
        {"code":"表2","article":"6~8","name":"收益法調查估價表（含附表—成本法調查估價表）","producer":"查估單位"},
        {"code":"表3","article":"9Ⅱ","name":"地價區段勘查表","producer":"查估單位","core":True},
        {"code":"表4","article":"19Ⅰ","name":"比較法調查估價表","producer":"查估單位","core":True},
        {"code":"表5","range":"表5-1~表5-5","article":"19Ⅲ","name":"影響地價區域因素分析明細表","producer":"查估單位","count":5,"core":True,
         "variants":[{"code":"表5-1","land_use":"住宅用地"},{"code":"表5-2","land_use":"商業用地"},
                     {"code":"表5-3","land_use":"工業用地"},{"code":"表5-4","land_use":"農業用地"},
                     {"code":"表5-5","land_use":"其他用地"}]},
        {"code":"表6","article":"20Ⅲ","name":"徵收土地宗地市價估計表","producer":"查估單位"},
        {"code":"表7","article":"20Ⅳ","name":"宗地個別因素清冊","producer":"需用土地人"},
        {"code":"表8-1","article":"25","name":"公共設施保留地地價加權平均計算表","producer":"查估單位"},
        {"code":"表8-2","article":"25","name":"公共設施保留地地價加權平均計算表（適用查估辦法第22條第4項）","producer":"查估單位"},
        {"code":"表9","article":"29","name":"徵收土地宗地市價評議表","producer":"直轄市、縣(市)政府"},
        {"code":"表10","article":"29","name":"徵收土地宗地市價清冊","producer":"查估單位"},
        {"code":"表11-1","article":"27","name":"市價變動幅度計算總表","producer":"直轄市、縣(市)政府"},
        {"code":"表11-2","article":"27","name":"市價變動幅度計算表（含續頁）","producer":"直轄市、縣(市)政府"},
        {"code":"表12","article":"30","name":"市價變動幅度評議表","producer":"直轄市、縣(市)政府"},
        {"code":"表13","article":"30","name":"市價變動幅度表","producer":"直轄市、縣(市)政府"},
        {"code":"表14","article":"19Ⅴ","name":"比準地地價估計表","producer":"查估單位"},
    ],
    "workflow": [
        {"step":1,"name":"蒐集基本資料、圖籍","outputs":[],"note":"需用土地人提供預定徵收範圍地籍圖"},
        {"step":2,"name":"調查實例及影響地價因素","outputs":["表3","表1-1","表2","表7"]},
        {"step":3,"name":"估計實例土地正常單價","outputs":["表1-1","表2"]},
        {"step":4,"name":"劃分或修正地價區段，繪製地價區段圖","outputs":[]},
        {"step":5,"name":"選取比準地","outputs":[],
         "note":"一般徵收土地於預定徵收範圍之地價區段選取；都計內公共設施保留地於毗鄰地價區段選取"},
        {"step":6,"name":"查估比準地地價","outputs":["表5","表4","表2","表14"],
         "note":"表5 須先於表4，因表4 之區域因素調整百分率引用表5 總修正數"},
        {"step":7,"name":"估計預定徵收土地宗地市價","outputs":["表6","表8-1","表8-2"]},
        {"step":8,"name":"宗地市價提評","outputs":["表9"]},
        {"step":9,"name":"評定結果提供需用土地人","outputs":["表10"]},
    ],
}

FORMULAS = {
    "schema_version": "1.0",
    "source": {"pdf": SRC, "xlsx": "doc/table/*.xlsx"},
    "level_scales": {
        "2": ["優","劣"], "3": ["優","普通","劣"],
        "5": ["優","稍優","普通","稍劣","劣"],
        "5_pollution": ["無","輕微","中度","嚴重","極嚴重"],
        "5_restriction": ["極輕微","輕微","普通","嚴格","極嚴格"],
        "7": ["極優","優","稍優","普通","稍劣","劣","極劣"],
        "9": ["超極優","極優","優","稍優","普通","稍劣","劣","極劣","超極劣"],
        "note": "出自手冊 伍、六(八)2。表3 左側 [N] [M] 表示第 N 級 / 共 M 級。",
    },
    "matrix": {
        "structure": "反對稱方陣，對角線為 0，相鄰級距差固定",
        "step": "step = max_adjustment / (level_count - 1)",
        "note": "表5（區域因素）與表4／表6（個別因素）查表方向相反，為本系統最易誤用之處；"
                "分別由 engine/grading.py 之 adjust_regional() 與 adjust() 實作，不可混用。",
        "table5_regional": {
            "lookup": "adjustment = (base_rank - comparable_rank) * step",
            "equivalence": "與查表 matrix[comparable_rank-1][base_rank-1] 等價",
            "sign_convention": "比較標的級距數字大於比準地（條件較劣）→ 修正百分比為負",
            "rationale": "依承辦單位認定：表5-1 同列並置「優劣等級序號」與「修正百分比」，"
                         "等級序號愈小代表條件愈優，修正百分比之正負須與"
                         "「比準地級距 − 比較標的級距」的大小關係一致，"
                         "以免同一列出現中文等級與數字正負相互矛盾。",
            "example": "樹林 P001-00(容積率260%,普通,3) vs P002-00(200%,稍劣,4) "
                       "→ (3-4)×6.25 = -6.25",
        },
        "table4_individual": {
            "lookup": "adjustment = (comparable_rank - base_rank) * step",
            "equivalence": "與查表 matrix[base_rank-1][comparable_rank-1] 等價",
            "sign_convention": "比較標的條件較差 → 差異率為正",
            "rationale": "以金山官方已填範本（doc/rules/查估書表範本.pdf 表4）校準，"
                         "五筆非零細項皆同向；改為相反方向則五筆全部對不上。",
            "evidence": [
                "面前道路寬度：比準地 18m(稍優) / 比較標的 6m(稍劣) → 範本填 +5.00%",
                "道路種類：比準地 主要道路(優) / 比較標的 次要道路(稍優) → 範本填 +2.00%",
                "停車方便性：比準地 可路邊停車(優) / 比較標的 不可路邊停車(劣) → 範本填 +2.00%",
                "深度：比準地 23m(普通) / 比較標的 16m(稍劣) → 範本填 +1.00%",
                "嫌惡設施：比準地 公墓260m(普通) / 比較標的 公墓80m(劣) → 範本填 +3.00%",
            ],
        },
    },
    "price_chain_table4": {
        "description": "表4 比較法：將比較標的價格調整為比準地價格",
        "steps": [
            {"name":"調整至估價基準日單價","formula":"土地正常單價 × (1 + 交易日期調整百分率)"},
            {"name":"試算價格","formula":"調整至估價基準日單價 × (1 + 區域因素調整百分率 + 個別因素合計)"},
            {"name":"調整百分率絕對值加總","formula":"|交易日期調整率| + |區域因素調整率| + Σ|各個別因素差異率|"},
            {"name":"比準地比較價格","formula":"Σ(各比較標的試算價格 × 權重)","rounding":"四捨五入至個位數"},
        ],
        "precision_note": "試算採全精度連乘；表上顯示值為進位後結果。核算應允許 ±1 元容差。",
    },
    "price_chain_table6": {
        "description": "表6 宗地市價：由比準地地價調整為各宗地價格",
        "steps": [
            {"name":"總調整率","formula":"Σ 各個別因素差異率"},
            {"name":"宗地市價試算價格","formula":"ROUND(比準地地價 × (1 + 總調整率), 0)"},
            {"name":"宗地市價","formula":"依尾數規則無條件進位"},
        ],
        "sign_convention": "宗地條件較優 → 差異率為正（與表4 方向相反）",
        "warning": "表4 與表6 的修正率符號方向相反，為審查最常見錯誤來源",
    },
    "rounding": {
        "article": "土地徵收補償市價查估辦法第21條",
        "applies_to": ["比準地地價", "宗地市價"],
        "unit": "元/平方公尺",
        "method": "無條件進位",
        "tiers": [
            {"max": 100, "round_to": "個位數", "excel": "ROUNDUP(x,0)"},
            {"min": 100, "max": 1000, "round_to": "十位數", "excel": "ROUNDUP(x,-1)"},
            {"min": 1000, "max": 100000, "round_to": "百位數", "excel": "ROUNDUP(x,-2)"},
            {"min": 100000, "round_to": "千位數", "excel": "ROUNDUP(x,-3)"},
        ],
        "excel_formula": "=IF(x>100000,ROUNDUP(x,-3),IF(x>1000,ROUNDUP(x,-2),IF(x>100,ROUNDUP(x,-1),ROUNDUP(x,0))))",
        "exceptions": [
            {"case":"依第27條市價變動幅度調整後之宗地市價單價","rule":"無條件進位至個位數（避免重複進位）"},
            {"case":"表4 比準地比較價格","rule":"四捨五入至個位數"},
            {"case":"公保地跨2個以上區段之宗地單位地價","rule":"無條件進位至個位數"},
        ],
    },
    "weighting": {
        "source": "手冊 伍、六(十一)；不動產估價技術規則第27條",
        "basis": "以「調整百分率絕對值加總」衡量價格形成因素之相近程度；加總愈大→權重愈小",
        "examples": [
            {"count":3,"abs_sums":[7,10,15],"similarity":["較高","普通","較低"],"weights":[0.5,0.3,0.2]},
            {"count":2,"abs_sums":[7,10],"similarity":["較高","普通"],"weights":[0.7,0.3]},
            {"count":1,"abs_sums":None,"similarity":["普通"],"weights":[1.0]},
        ],
        "note": "仍須配合蒐集資料可信度綜合決定",
    },
    "fill_conventions": {
        "exempt_vs_zero": {
            "source":"手冊 伍、六(七)2、七(四)1",
            "rule":"免修正項目之條件欄與差異率一律填『-』；應修正但無差異者填 0。兩者必須區分。",
            "extra":"經判斷屬免比較項目，應於全案備註欄加註理由。",
        },
        "far_individual": {
            "source":"手冊 伍、六(六)4",
            "rule":"行政條件容積率指法定容積率；需就現況容積率修正者於「其他」欄處理並於備註欄通案說明。",
        },
        "avoid_double_adjustment": {
            "source":"手冊 伍、六(九)",
            "rule":"區域與個別因素項目雷同者，若已完全於一方反應調整，則不需於另一方重複調整。",
        },
        "comparable_facilities": {
            "source":"手冊 伍、六(六)2(2)",
            "rule":"3接近條件各項設施及20嫌惡設施：比較標的原則填與比準地相同之標的；不同行政區案例須有同等級影響力設施才填載，否則填『無』。",
        },
        "flexibility": {
            "source":"手冊 伍、六(八)4",
            "rule":"各細項等級或價格修正率因情況特殊者，得於備註欄敘明理由後酌予調整，惟仍應在內政部『影響地價個別因素評價基準表』規定之最大影響範圍內。",
            "implication":"審查系統對超出查表值者不應直接判錯，應標記為『須確認備註理由』。",
        },
    },
}

REVIEW = {
    "schema_version": "1.0",
    "source": {"pdf": SRC, "section": "參、七、(一) 提交地價評議委員會評議前之審查作業"},
    "official_checklist": [
        {"id":"i","target":None,"content":"確認是否已檢附應備資料"},
        {"id":"ii","target":"表7","content":"宗地個別因素清冊是否由需用土地人逐級核章、行政條件是否符合規範、已踐行協議價購者是否填寫協議金額"},
        {"id":"iii","target":"表3","automatable":True,"content":"區段範圍描述是否與現況相符、各用地別應評價細項是否皆已填載、優劣等級是否依區域因素評價基準明細表填列"},
        {"id":"iv","target":"地價區段圖","content":"地價區段劃設是否符合規定；地價區段圖及略圖是否清晰正確、標註路名或地標足以辨識"},
        {"id":"v","target":"表1-1","content":"交易日期是否在蒐集期間、總價格是否與實價登錄相符、成本價格是否符合估價師公會第4號公報、區分所有建物應敘明土地正常買賣單價修正過程、案例選取適合性"},
        {"id":"vi","target":"表5","automatable":True,"content":"修正細項優劣等級是否與各該地價區段勘查表所載內容一致；修正百分比是否依區域因素評價基準明細表調整"},
        {"id":"vii","target":"表4","automatable":True,"content":"交易日期與買賣實例調查表一致、區域因素調整百分率與表5總修正數相符、個別因素差異率依個別因素評價基準明細表填列、各比較標的權重是否符合邏輯"},
        {"id":"viii","target":"表2","content":"月租金推估、收益面積與租金是否與實價登錄相符、有效總收入/總費用計算、資本化率是否符合估價技術規則第43條、決定理由是否適當"},
        {"id":"ix","target":"表14","automatable":True,"content":"區段號、比準地標示及估值應與比較法/收益法調查估價表結果一致；權重與決定理由是否合理；比準地地價尾數是否符合規定"},
        {"id":"x","target":"表6","automatable":True,"content":"各宗地條件是否與宗地個別因素清冊一致、個別因素差異率是否依基準明細表填列、宗地地價尾數是否符合規定"},
        {"id":"xi","target":"表8","content":"區段號、區段地價及計算結果是否正確；毗鄰含公共設施用地區段時是否從高計算；查估辦法第22條第4項情形是否以3個同使用性質區段平均計算或從高"},
    ],
    "cross_reference_matrix": [
        {"id":"R1","from":"表3 各細項勘查結果","to":"表5 優劣等級欄","check":"優劣等級須與表3 所載內容一致","checklist":"vi","priority":3},
        {"id":"R2","from":"區域因素評價基準明細表","to":"表5 修正百分比","check":"修正率須依基準明細表查得","checklist":"vi","priority":2},
        {"id":"R3","from":"表3 區段編號","to":"表5/表4 地價區段號","check":"區段號一致","checklist":"vi","priority":8},
        {"id":"R4","from":"表5 影響地價區域因素總修正數","to":"表4 區域因素調整百分率","check":"數值必須相符","checklist":"vii","priority":1},
        {"id":"R5","from":"表1-1 買賣實例調查估價表","to":"表4 交易日期/土地正常單價/實例編號","check":"交易日期與單價一致","checklist":"vii","priority":9},
        {"id":"R6","from":"個別因素評價基準明細表","to":"表4 個別因素差異率","check":"差異率須依基準明細表填列","checklist":"vii","priority":2},
        {"id":"R7","from":"表4 調整百分率絕對值加總","to":"表4 相近程度/權重","check":"加總愈大權重愈小","checklist":"vii","priority":5},
        {"id":"R8","from":"表7 宗地個別因素清冊","to":"表4 比準地條件欄 / 表6 各宗地條件欄","check":"條件值一致","checklist":"x","priority":7},
        {"id":"R9","from":"表4 比較價格 + 表2 收益價格","to":"表14 估值欄","check":"估值與各該表結果一致","checklist":"ix","priority":10},
        {"id":"R10","from":"表14 比準地地價","to":"表6 比準地價格","check":"一致（Excel: 表6!C5 = 表14!J7）","checklist":"x","priority":10},
        {"id":"R11","from":"表3 區段範圍描述","to":"現況 / 地價區段圖","check":"描述與現況相符","checklist":"iii,iv","priority":11},
        {"id":"R12","from":"各用地別應評價細項","to":"表3","check":"應評價細項是否皆已填載","checklist":"iii","priority":6},
        {"id":"R13","from":"尾數規則（查估辦法第21條）","to":"表14 比準地地價 / 表6 宗地地價","check":"尾數計算符合規定","checklist":"ix,x","priority":6},
        {"id":"R14","from":"表5 各項百分比小計","to":"表5 總修正數","check":"總修正數 = (1)+(2)+…+(8)","checklist":"vi","priority":4},
    ],
}

LEGAL = {
    "schema_version": "1.0",
    "articles": [
        {"law":"土地徵收條例","article":"30","content":"按徵收當期市價補償；公保地按毗鄰非保留地平均市價；每6個月評定市價變動幅度"},
        {"law":"土地徵收補償市價查估辦法","article":"17Ⅲ","content":"無適當成交案例時得擴大選取範圍及蒐集期間至估價基準日前一年內"},
        {"law":"土地徵收補償市價查估辦法","article":"18","content":"比準地選取時機及原則"},
        {"law":"土地徵收補償市價查估辦法","article":"19","content":"比準地地價查估之作業依據；第2項得擴大蒐集範圍"},
        {"law":"土地徵收補償市價查估辦法","article":"20","content":"以比準地地價參酌宗地個別因素調整各宗地市價"},
        {"law":"土地徵收補償市價查估辦法","article":"21","content":"地價尾數計算規定"},
        {"law":"土地徵收補償市價查估辦法","article":"22~25","content":"都市計畫區內公共設施保留地市價查估與計算"},
        {"law":"土地徵收補償市價查估辦法","article":"27","content":"市價變動幅度作業步驟及計算單位"},
        {"law":"土地徵收補償市價查估辦法","article":"29","content":"市價評議期程、評議結果適用期間"},
        {"law":"不動產估價技術規則","article":"27","content":"應採3件以上比較標的，考量可信度與相近程度決定比較價格"},
        {"law":"不動產估價技術規則","article":"43","content":"收益資本化率"},
    ],
    "extra_rules": {
        "source": "doc/rules/extra.md",
        "rules": [
            "捷運開發地要用變身分之前的土地規格為準則（一般住宅規格）",
            "都市計畫中，未特別獎勵或一般巷道（8公尺寬以下道路）旁之住宅區，基準容積率常規劃為 200%",
        ],
    },
}

from datasets._build.case_rules import CASE_RULES

for name, doc in [("forms", FORMS), ("formulas", FORMULAS), ("case_rules", CASE_RULES),
                  ("review_rules", REVIEW), ("legal_references", LEGAL)]:
    json.dump(doc, open(f"{OUT}/{name}.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
    yaml.safe_dump(doc, open(f"{OUT}/{name}.yaml","w",encoding="utf-8"),
                   allow_unicode=True, sort_keys=False, width=200)
    print(f"  {name}.json / .yaml")
print("common 資料建置完成")
