# -*- coding: utf-8 -*-
"""抽取 PDF 中的圖像：嵌入點陣圖(地圖/照片) + 頁面渲染(表單/基準表/圖例)"""
import os, re, json, hashlib, subprocess, shutil, glob, sys

OUT = "datasets"
TMP = "/tmp/_imgbuild"

# (pdf, region, doc_id, pages_to_render, extract_embedded_pages)
SOURCES = [
    ("doc/題目.pdf", "shulin", "case_forms", "1-6", None),
    ("doc/rules/評價基準明細表.pdf", "shulin", "criteria_tables", "all", None),
    ("doc/rules/查估書表範本.pdf", "jinshan", "reference_forms", "1-6", "4-6"),
    ("doc/rules/評價基準明細表範例.pdf", "jinshan", "criteria_tables", "all", None),
    ("doc/rules/土地徵收補償市價查估作業手冊.pdf", "_common", "manual", "16,64-75", None),
    ("doc/【命題文件】地政局-新北市政府AI黑客松競賽.pdf", "_common", "problem_statement", "1", None),
]

def sh(*a):
    r = subprocess.run(a, capture_output=True, text=True)
    return r.stdout

def npages(pdf):
    return int(re.search(r'Pages:\s+(\d+)', sh("pdfinfo", pdf)).group(1))

def page_text(pdf, p):
    return sh("pdftotext", "-f", str(p), "-l", str(p), pdf, "-").strip()

def caption(txt):
    for line in txt.split("\n"):
        s = line.strip()
        if len(s) >= 6 and not s.startswith(("比例尺",)): return s[:80]
    return ""

def expand(spec, total):
    if spec == "all": return list(range(1, total+1))
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-"); out += list(range(int(a), min(int(b), total)+1))
        else:
            if int(part) <= total: out.append(int(part))
    return out

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]

def main():
    shutil.rmtree(TMP, ignore_errors=True); os.makedirs(TMP)
    manifest = []
    for pdf, region, doc_id, render_spec, embed_spec in SOURCES:
        if not os.path.exists(pdf): print("缺檔:", pdf); continue
        total = npages(pdf)
        imgdir = os.path.join(OUT, "regions", region, "img") if region != "_common" \
                 else os.path.join(OUT, "common", "img")
        os.makedirs(imgdir, exist_ok=True)

        # 1) 頁面渲染
        for p in expand(render_spec, total):
            base = os.path.join(TMP, f"{doc_id}_p{p:03d}")
            sh("pdftoppm", "-jpeg", "-r", "150", "-f", str(p), "-l", str(p), pdf, base)
            got = glob.glob(base + "*.jpg")
            if not got: continue
            name = f"{doc_id}_p{p:03d}.jpg"
            dst = os.path.join(imgdir, name); shutil.move(got[0], dst)
            txt = page_text(pdf, p)
            manifest.append({
                "image_id": f"{region}.{doc_id}.p{p:03d}",
                "region": region, "doc_id": doc_id, "kind": "page_render",
                "source_pdf": pdf, "page": p,
                "path": os.path.relpath(dst, OUT).replace(os.sep, "/"),
                "caption": caption(txt),
                "text_len": len(txt),
                "tags": _tags(doc_id, txt),
                "sha256_16": sha(dst),
                "bytes": os.path.getsize(dst),
            })

        # 2) 嵌入點陣圖（地圖 / 現況照片）
        if embed_spec:
            for p in expand(embed_spec, total):
                pref = os.path.join(TMP, f"emb_{doc_id}_p{p}")
                sh("pdfimages", "-png", "-f", str(p), "-l", str(p), pdf, pref)
                txt = page_text(pdf, p)
                for f in sorted(glob.glob(pref + "*.png")):
                    dim = sh("sips", "-g", "pixelWidth", "-g", "pixelHeight", "-g", "space", f)
                    w = int(re.search(r'pixelWidth: (\d+)', dim).group(1))
                    h = int(re.search(r'pixelHeight: (\d+)', dim).group(1))
                    sp = re.search(r'space: (\w+)', dim)
                    space = sp.group(1) if sp else ""
                    if w < 150 or h < 150:      # 濾掉文字標籤小圖
                        os.remove(f); continue
                    if space == "Gray":         # pdfimages 會把 alpha 遮罩(smask)另存為灰階圖
                        os.remove(f); continue
                    kind = "map" if w > 1000 else "photo"
                    idx = len([m for m in manifest if m.get("page") == p
                               and m["kind"] in ("map", "photo") and m["doc_id"] == doc_id])
                    name = f"{doc_id}_p{p:03d}_{kind}_{idx:02d}.png"
                    dst = os.path.join(imgdir, name); shutil.move(f, dst)
                    manifest.append({
                        "image_id": f"{region}.{doc_id}.p{p:03d}.{kind}{idx:02d}",
                        "region": region, "doc_id": doc_id, "kind": kind,
                        "source_pdf": pdf, "page": p,
                        "path": os.path.relpath(dst, OUT).replace(os.sep, "/"),
                        "caption": caption(txt),
                        "width": w, "height": h,
                        "tags": _tags(doc_id, txt) + ([ "地價區段略圖" ] if kind == "map" else ["現況照片"]),
                        "sha256_16": sha(dst),
                        "bytes": os.path.getsize(dst),
                    })
    os.makedirs(os.path.join(OUT, "common"), exist_ok=True)
    json.dump({"schema_version": "1.0", "count": len(manifest), "images": manifest},
              open(os.path.join(OUT, "common", "images.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    shutil.rmtree(TMP, ignore_errors=True)
    from collections import Counter
    print(f"共 {len(manifest)} 張")
    for k, v in Counter((m['region'], m['kind']) for m in manifest).items(): print(f"  {k}: {v}")
    print(f"總計 {sum(m['bytes'] for m in manifest)/1e6:.1f} MB")

def _tags(doc_id, txt):
    t = []
    for kw, tag in [("地價區段勘查表","表3"),("比較法調查估價表","表4"),
                    ("影響地價區域因素分析明細表","表5"),("區域因素評價基準明細表","基準表-區域因素"),
                    ("個別因素評價基準明細表","基準表-個別因素"),("略圖","地價區段略圖"),
                    ("使用分區圖","使用分區圖"),("區段圖","地價區段圖")]:
        if kw in txt: t.append(tag)
    return t

if __name__ == "__main__": main()
