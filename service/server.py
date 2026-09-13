# -*- coding: utf-8 -*-
"""把 output/ 的產出以 HTTP 服務對外提供，讓外部程式碼可以直接接進來。

路由：
    GET /                           欄位對照總覽（output/fieldMapping/index.html）
    GET /fieldMapping/index.html    同上
    GET /output/                    output/ 目錄索引
    GET /output/<路徑>              output/ 底下的檔案（各版本 html / xlsx / csv / md）

回應一律帶 Access-Control-Allow-Origin: *，且不送 X-Frame-Options，
所以外部程式可以直接 fetch()，也可以用 <iframe> 內嵌。

純標準庫，不需安裝任何套件：
    python3 service/server.py --port 8000
"""
import argparse, gzip, html, mimetypes, os, posixpath, sys
from email.utils import formatdate, parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.realpath(os.path.join(ROOT, "output"))
FIELD_MAP = os.path.join(OUTPUT, "fieldMapping", "index.html")

# 欄位對照總覽單檔就有 670 KB 純文字，壓縮後送出差很多
GZIP_TYPES = ("text/", "application/json", "application/javascript", "image/svg+xml")
GZIP_MIN = 1024

mimetypes.add_type("text/markdown", ".md")
mimetypes.add_type("text/csv", ".csv")
mimetypes.add_type("application/vnd.openxmlformats-officedocument."
                   "spreadsheetml.sheet", ".xlsx")

# 這些路徑都指向同一份欄位對照總覽，讓外部程式怎麼接都接得到
FIELD_MAP_PATHS = {"/", "/index.html", "/fieldMapping", "/fieldMapping/",
                   "/fieldMapping/index.html"}


def content_type(path):
    ctype, _ = mimetypes.guess_type(path)
    ctype = ctype or "application/octet-stream"
    # 表單內容全是中文，純文字型別一定要標 utf-8，否則瀏覽器會亂碼
    if ctype.startswith("text/") or ctype in ("application/json",
                                              "application/javascript"):
        ctype += "; charset=utf-8"
    return ctype


def safe_path(rel):
    """把 URL 相對路徑解成 output/ 底下的真實路徑；跳脫目錄的一律回 None。"""
    rel = posixpath.normpath("/" + rel.strip("/")).lstrip("/")
    target = os.path.realpath(os.path.join(OUTPUT, rel))
    if target != OUTPUT and not target.startswith(OUTPUT + os.sep):
        return None
    return target


def dir_index(path, url_path):
    """產生簡單的目錄索引，方便用瀏覽器翻 output/ 底下的各版本產出。"""
    entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name))
    rows = []
    if url_path.rstrip("/") != "/output":
        rows.append('<li><a href="../">../</a></li>')
    for e in entries:
        if e.name.startswith("."):
            continue
        name = e.name + ("/" if e.is_dir() else "")
        size = "" if e.is_dir() else f" <span>{e.stat().st_size:,} bytes</span>"
        rows.append(f'<li><a href="{html.escape(name)}">{html.escape(name)}</a>{size}</li>')
    title = html.escape(url_path)
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font:14px/1.7 -apple-system,BlinkMacSystemFont,"Noto Sans TC","PingFang TC",sans-serif;
     max-width:760px;margin:40px auto;padding:0 16px;color:#1b1f24}}
h1{{font-size:16px;font-family:ui-monospace,Menlo,monospace}}
ul{{list-style:none;padding:0}} li{{padding:4px 0;border-bottom:1px solid #e2e6ea}}
a{{color:#1f5fa8;text-decoration:none}} a:hover{{text-decoration:underline}}
span{{color:#5b6570;font-size:12px;float:right}}
</style></head><body><h1>{title}</h1><ul>{''.join(rows)}</ul></body></html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "NTPCAppraisalOutput/1.0"
    protocol_version = "HTTP/1.1"

    # ── 回應組裝 ─────────────────────────────────────────────
    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def send_body(self, body, ctype, mtime=None, head_only=False):
        payload, encoding = body, None
        if (len(body) >= GZIP_MIN and any(ctype.startswith(t) for t in GZIP_TYPES)
                and "gzip" in self.headers.get("Accept-Encoding", "")):
            payload, encoding = gzip.compress(body, 6), "gzip"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        if encoding:
            self.send_header("Content-Encoding", encoding)
            self.send_header("Vary", "Accept-Encoding")
        if mtime is not None:
            self.send_header("Last-Modified", formatdate(mtime, usegmt=True))
        # 產出會重新生成，所以每次都回來問一次，由 Last-Modified 決定要不要重送
        self.send_header("Cache-Control", "no-cache")
        self.cors()
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def send_error_page(self, code, message):
        body = f"{code} {message}\n".encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.cors()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def not_modified(self, mtime):
        ims = self.headers.get("If-Modified-Since")
        if not ims:
            return False
        try:
            since = parsedate_to_datetime(ims).timestamp()
        except (TypeError, ValueError):
            return False
        return int(mtime) <= int(since)

    def send_file(self, path, head_only=False):
        try:
            mtime = os.path.getmtime(path)
            with open(path, "rb") as fh:
                body = fh.read()
        except OSError:
            return self.send_error_page(404, "Not Found")
        if self.not_modified(mtime):
            self.send_response(304)
            self.send_header("Last-Modified", formatdate(mtime, usegmt=True))
            self.cors()
            self.end_headers()
            return
        self.send_body(body, content_type(path), mtime, head_only)

    # ── 路由 ─────────────────────────────────────────────────
    def route(self, head_only=False):
        path = unquote(urlsplit(self.path).path)
        if path in FIELD_MAP_PATHS:
            return self.send_file(FIELD_MAP, head_only)
        if path == "/output" or path.startswith("/output/"):
            target = safe_path(path[len("/output"):])
            if target is None:
                return self.send_error_page(403, "Forbidden")
            if os.path.isdir(target):
                if not path.endswith("/"):        # 目錄索引裡的連結是相對的
                    self.send_response(301)
                    self.send_header("Location", path + "/")
                    self.send_header("Content-Length", "0")
                    self.cors()
                    self.end_headers()
                    return
                return self.send_body(dir_index(target, path),
                                      "text/html; charset=utf-8",
                                      os.path.getmtime(target), head_only)
            return self.send_file(target, head_only)
        self.send_error_page(404, "Not Found")

    def do_GET(self):
        self.route()

    def do_HEAD(self):
        self.route(head_only=True)

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("%s  %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    ap = argparse.ArgumentParser(description="地價查估產出 HTTP 服務")
    ap.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"),
                    help="監聽位址（預設 0.0.0.0；只給本機用可設 127.0.0.1）")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)),
                    help="監聽埠號（預設 8000）")
    a = ap.parse_args()
    if not os.path.exists(FIELD_MAP):
        sys.exit(f"找不到 {FIELD_MAP}，請先產生欄位對照總覽")
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    shown = "localhost" if a.host in ("0.0.0.0", "") else a.host
    print(f"欄位對照總覽  http://{shown}:{a.port}/")
    print(f"產出目錄索引  http://{shown}:{a.port}/output/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n服務已停止")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
