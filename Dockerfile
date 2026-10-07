FROM python:3.12.14-slim-bookworm
LABEL org.opencontainers.image.title="PixCake Bridge" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.licenses="MIT"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# GNU cp supplies reflink; Python supplies the final byte-copy fallback.
RUN apt-get update && apt-get install -y --no-install-recommends coreutils && rm -rf /var/lib/apt/lists/*
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps . && useradd -u 1001 -m bridge && mkdir -p /data && chown bridge:bridge /data
USER 1001:1001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"
CMD ["uvicorn", "pixcake_bridge.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log"]
