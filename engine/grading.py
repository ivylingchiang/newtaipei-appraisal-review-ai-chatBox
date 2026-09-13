# -*- coding: utf-8 -*-
"""判級與修正率查表：事實 → 優劣等級 → 修正百分比"""
import re, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "datasets", "_build"))
from threshold import match_level  # noqa: E402


class Ungradable(Exception):
    """資料不足或條件無法對應到任一級距"""


def item_unit(item):
    for lv in item.get("levels", []):
        u = (lv.get("threshold") or {}).get("unit")
        if u: return u
    return None


def is_categorical(item):
    return all((lv.get("threshold") or {}).get("kind") == "categorical"
               for lv in item.get("levels", []) if lv.get("criterion"))


def grade(item, value=None, category=None, in_segment=False, is_none=False):
    """回傳 (rank, label)；無法判定則拋 Ungradable"""
    if item.get("rule_type") != "matrix":
        raise Ungradable(f"{item['item_code']}：非矩陣型（{item.get('basis')}）")
    if category is not None:
        cat = str(category).strip()
        # 表3 常直接抄錄基準表的級距文字（如「平均坡度未滿5度」「普通完善」），
        # 此類欄位在基準表中被解析為數值型，無 categories 可比，需先比對級距原文。
        for lv in item["levels"]:
            if lv.get("criterion") and lv["criterion"].strip() == cat:
                return lv["rank"], lv["label"]
        cands = [(lv, c) for lv in item["levels"]
                 for c in ((lv.get("threshold") or {}).get("categories") or []) if c]
        # 1) 完全相符優先。單靠子字串會誤判：「可路邊停車」是「不可路邊停車」的子字串，
        #    寬鬆比對會把「不可路邊停車」判成「優」。
        for lv, c in cands:
            if c == cat: return lv["rank"], lv["label"]
        # 2) 其次取最長的包含相符（「第一種住宅區」→ 級距「住宅區」）
        hits = [(len(c), lv) for lv, c in cands if c in cat or cat in c]
        if hits:
            lv = max(hits, key=lambda x: x[0])[1]
            return lv["rank"], lv["label"]
    if value is not None or in_segment or is_none:
        r = match_level(value, item["levels"], in_segment=in_segment, is_none=is_none)
        if r: return r, item["levels"][r - 1]["label"]
    raise Ungradable(f"{item['item_code']}：條件 value={value!r} category={category!r} 無法對應級距")


def adjust(item, base_rank, comp_rank):
    """修正率／差異率＝(比較標的級距 − 比準地級距) × 級距差

    即查表 matrix[比準地][比較標的]。**表5 區域因素、表4 與表6 個別因素同一方向**，共用本函式。

    承辦單位認定之通則：**比準地優於對造（比較標的或宗地）時，修正率一律為正**。
    表4 方向另以金山官方已填範本（查估書表範本 表4）反算校準：
    比準地 18m(稍優) ／ 比較標的 6m(稍劣) → 範本填 +5.00%，五筆非零細項皆同向。

    表6 由宗地擔任對造，查表方式不變。惟官方 Excel 表6 範本的示範資料與上開通則相反
    （宗地較優填正值，9 細項 × 5 宗地一致），差異記於 datasets/common/formulas.json 之
    price_chain_table6.open_issue；本專案未實作表6，實作前應先向承辦單位確認。

    注意：曾一度把表5 改成相反方向（matrix[比較標的][比準地]，比較標的較劣為負），
    理由是「同列的中文等級與數字正負須一致」。該判斷經承辦單位澄清為誤判，已回復
    單一方向。若日後再次出現同向／反向的疑問，請以金山官方範本反算為準，勿再分家。
    """
    return item["matrix"][base_rank - 1][comp_rank - 1]


NUM = re.compile(r'^-?[\d,]+(?:\.\d+)?$')
PCT = re.compile(r'^(-?[\d,]+(?:\.\d+)?)\s*[%％]$')


def split_conditions(item, conditions, n_comp=1):
    """把表4 條件欄位切成 [比準地, 比較標的...]，依細項單位決定取數值或文字"""
    unit = item_unit(item)
    if unit == "percent":
        vals = [float(m.group(1).replace(",", "")) for x in conditions
                if (m := PCT.match(str(x)))]
        return ("value", vals) if len(vals) >= 1 + n_comp else ("value", vals)
    if unit in ("m", "m2", "degree"):
        vals = [float(str(x).replace(",", "")) for x in conditions if NUM.match(str(x))]
        return "value", vals
    texts = [str(x) for x in conditions if not NUM.match(str(x)) and not PCT.match(str(x))]
    return "category", texts
