# 地價查估產出 HTTP 服務 —— 純標準庫，不需要安裝任何套件
#
# 從專案根目錄建置（build context 必須是根目錄，映像要帶 output/ 進去）：
#     docker build -f service/Dockerfile -t ntpc-appraisal-output .
#     docker run --rm -p 8000:8000 ntpc-appraisal-output
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app
COPY service/ /app/service/
COPY output/ /app/output/

# 只讀取檔案，不需要 root
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import os,urllib.request as u; \
u.urlopen('http://127.0.0.1:%s/' % os.environ['PORT'], timeout=4).read(1)"

CMD ["python3", "service/server.py", "--host", "0.0.0.0"]
