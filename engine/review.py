# -*- coding: utf-8 -*-
"""審查主流程"""
import engine.checks as C
from engine.compute import derive_table5


def review_case(ds, region, case_no=None):
    cases = ds.cases(region)
    case = cases[case_no] if case_no else list(cases.values())[0]
    segments = ds.segments(region)
    findings = []
    findings += C.check_R1(ds, region, case, segments)
    findings += C.check_R2(ds, region, case)
    findings += C.check_R14(ds, region, case)
    findings += C.check_R4(ds, region, case)
    findings += C.check_R6(ds, region, case)
    findings += C.check_R7(ds, region, case)
    findings += C.check_price_chain(ds, region, case)
    findings += C.check_R12(ds, region, case, segments)
    findings += C.check_case_rules(ds, region, case, segments)
    return {
        "region": region,
        "region_name": ds.region_info(region)["region_name"],
        "land_use": ds.region_info(region)["land_use_name"],
        "case_no": case["case_no"],
        "role": case["source"]["role"],
        "findings": findings,
        "derived_table5": derive_table5(ds, region, case, segments),
    }


SEV_ORDER = {"error": 0, "warning": 1, "blocked": 2, "info": 3}
SEV_ICON = {"error": "❌", "warning": "⚠️ ", "blocked": "⛔", "info": "ℹ️ "}


def format_report(r, show_derived=True):
    L = []
    A = L.append
    A("═" * 76)
    A(f"審查報告　{r['region_name']}{r['land_use']}　案號 {r['case_no']}　[{r['role']}]")
    A("═" * 76)
    fs = sorted(r["findings"], key=lambda f: (SEV_ORDER.get(f.severity, 9), f.rule))
    counts = {}
    for f in fs: counts[f.severity] = counts.get(f.severity, 0) + 1
    A("　".join(f"{SEV_ICON[k].strip()} {k} {v}" for k, v in
               sorted(counts.items(), key=lambda kv: SEV_ORDER.get(kv[0], 9))) or "無發現")
    A("")
    cur = None
    for f in fs:
        if f.severity != cur:
            cur = f.severity
            A(f"── {SEV_ICON[cur].strip()} {cur.upper()} " + "─" * 50)
        head = f"  [{f.rule}] {f.target}"
        if f.item: head += f"／{f.item}"
        A(head)
        A(f"      {f.message}")
        if f.expected is not None or f.actual is not None:
            A(f"      應為 {f.expected}　實際 {f.actual}")
        if f.evidence.get("missing_items"):
            m = f.evidence["missing_items"]
            A(f"      缺項：{'、'.join(m[:8])}{' …等' if len(m) > 8 else ''}")
    if show_derived:
        d = r["derived_table5"]
        A("")
        A("═" * 76)
        A(f"表5 推導結果（比準地 {d.get('base_segment')}）"
          f"　可算 {d.get('computable_items')}/{d.get('total_items')} 項")
        A("═" * 76)
        if d.get("rows"):
            segs = d["segment_nos"][1:]
            A(f"  {'細項':<26s}{'比準地':>8s}" + "".join(f"{s:>12s}" for s in segs))
            for row in d["rows"]:
                if not row["computable"]: continue
                b = row["base"]
                line = f"  {row['item_name'][:24]:<26s}{b['label']:>8s}"
                for c, a in zip(row["comparables"], row["adjustments"]):
                    line += f"{c['label']+f'({a:+.2f})':>12s}"
                A(line)
            nc = [r2 for r2 in d["rows"] if not r2["computable"]]
            if nc:
                A("")
                A(f"  ⛔ 無法計算 {len(nc)} 項（資料不足）：")
                for row in nc[:30]:
                    A(f"      {row['item_name'][:30]:<32s} {row['gaps'][0] if row['gaps'] else ''}")
            A("")
            A(f"  各項小計（部分）：{d['subtotals']}")
            A(f"  總修正數（僅計可算項目，非最終值）："
              + "　".join(f"{s}={t:+.2f}%" for s, t in zip(segs, d["totals_partial"])))
            if not d["complete"]:
                A("  ⚠️  上列總修正數不完整，不得直接填入表5")
        else:
            A(f"  {d.get('note', '')}")
    return "\n".join(L)
