# -*- coding: utf-8 -*-
"""案件層級判定規則（來源：doc/rules/extra.md、承辦單位確認）"""
import re

CASE_RULES = {
    "schema_version": "1.0",
    "source": ["doc/rules/extra.md", "承辦單位口頭確認（2026-09）"],
    "rules": [
        {
            "id": "CR1",
            "name": "捷運開發區以「變更前」之使用分區認定",
            "source": "doc/rules/extra.md 第1條：捷運開發地要用變身分之前的土地規格為準則（一般住宅規格）",
            "confirmed_by": "承辦單位確認：本案 P001-00 以第一種住宅區判斷",
            "trigger": {"field": "scope_desc", "contains": "捷運開發區"},
            "action": {
                "zoning_for_valuation": "取 scope_desc 中「變更前為X」之 X；若無明載則依一般住宅規格",
                "override_land_use_current": True,
                "reason": "捷運開發區係都市計畫變更後之暫時地位，估價應回歸變更前之土地規格",
            },
            "notes": [
                "表3『土地利用現況』欄可能勾選與變更前分區不一致之項目（本案 P001-00 勾選商業用），"
                "該欄為現況描述，不作為使用分區優劣判定依據。",
                "使用分區之優劣等級應依『變更前』分區查表；本案為第一種住宅區 → 樹林住宅基準表『稍優』(rank 2)。",
            ],
        },
        {
            "id": "CR2",
            "name": "8公尺以下道路旁住宅區之基準容積率為200%",
            "source": "doc/rules/extra.md 第2條：都市計畫中，未特別獎勵或一般巷道（8公尺寬以下道路）旁之住宅區，基準容積率常規劃為 200%",
            "condition": {
                "urban_plan": "都市計畫內",
                "zoning_contains": "住宅區",
                "main_road_width_m": {"max": 8.0, "max_inclusive": True},
                "no_special_bonus": True,
            },
            "expected_far_percent": 200,
            "usage": "交叉檢核：表3 所載容積率與主要道路寬度是否相容；不符者標記待確認，不逕行判錯",
            "severity": "warning",
        },
    ],
}


def apply_cr1(seg):
    """回傳 valuation_basis 區塊；非捷運開發區則回 None"""
    scope = seg.get("scope_desc") or ""
    if "捷運開發" not in scope:
        return None
    m = re.search(r'變更前為([^)）,，]+)', scope)
    prior = m.group(1).strip() if m else None
    declared = (seg.get("observations", {}).get("zoning", {}) or {}).get("raw")
    return {
        "rule_applied": "CR1",
        "zoning_label_in_scope": "捷運開發區",
        "zoning_prior_to_change": prior,
        "zoning_declared_in_form": declared,
        "zoning_for_valuation": prior or declared,
        "land_use_current_in_form": seg.get("land_use_current"),
        "land_use_current_overridden": True,
        "note": ("依 extra.md 第1條及承辦單位確認，捷運開發區以變更前之使用分區"
                 f"（{prior or declared}）作為估價判定基準；表3『土地利用現況』所勾選之"
                 f"「{seg.get('land_use_current')}」屬現況描述，不作為使用分區優劣判定依據。"),
    }


def check_cr2(seg):
    """回傳 CR2 檢核結果；不適用則回 None"""
    o = seg.get("observations", {})
    zoning = (o.get("zoning", {}) or {}).get("raw") or ""
    vb = seg.get("valuation_basis") or {}
    zoning_eff = vb.get("zoning_for_valuation") or zoning
    if "住宅區" not in zoning_eff:
        return None
    road = (o.get("main_road", {}) or {}).get("value")
    far = (o.get("far", {}) or {}).get("value")
    if road is None or far is None:
        return None
    applicable = road <= 8.0
    consistent = (far == 200) if applicable else None
    return {
        "rule": "CR2",
        "main_road_width_m": road,
        "far_percent": far,
        "applicable": applicable,
        "expected_far_percent": 200 if applicable else None,
        "consistent": consistent,
        "severity": "info" if (consistent is not False) else "warning",
        "message": (f"主要道路寬 {road}m ≤ 8m，基準容積率預期 200%，實際 {far:.0f}%"
                    f"{'（相符）' if consistent else '（不符，請確認是否另有獎勵或特殊規定）'}")
                   if applicable else
                   f"主要道路寬 {road}m > 8m，CR2 不適用（實際容積率 {far:.0f}%）",
    }
