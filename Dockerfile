# IEEE 2030.5 BMS Client Dockerfile
FROM python:3.10-slim

# 設定環境變數
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 複製專案檔案
COPY pyproject.toml README.md ./
COPY src/ ./src/

# 安裝 Python 依賴
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# 建立非 root 使用者
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import bms_2030_5_client; print('OK')" || exit 1

# 啟動應用
CMD ["python", "-m", "bms_2030_5_client.main"]
