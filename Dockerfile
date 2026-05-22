# ============================================================
# Dockerfile – LG ThinQ Klimatizace (webový server)
# Cílové prostředí: Linux (Docker), Python 3.12-slim
# ❗ tkinter NENÍ součástí tohoto obrazu – aplikace běží
#    výhradně v režimu --mode web.
# ============================================================

FROM python:3.12-slim

LABEL org.opencontainers.image.title="LG Klimatizace" \
      org.opencontainers.image.description="Webové rozhraní pro ovládání LG ThinQ klimatizace" \
      org.opencontainers.image.source="https://github.com/placeholder/lg-klimatizace"

WORKDIR /app

# --- Systémové závislosti ---
# gcc je potřeba pro sestavení některých Python balíčků (awscrt, cryptography).
# Po instalaci Pythonu balíčků layer odstraníme apt cache.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

# --- Python závislosti (vlastní vrstva pro cache) ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Zdrojový kód ---
COPY src/ ./src/

# --- Příprava datového adresáře ---
# Skutečná data (config.json, devices.json, ...) jsou připojena jako volume.
# Adresář musí existovat, aby mount fungoval i bez předpřipraveného volume.
RUN mkdir -p data

# --- Bezpečnost: neprivilegovaný uživatel ---
RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Port, na kterém uvicorn naslouchá
EXPOSE 8000

# --- Health check ---
# Zavolá /health endpoint; Docker označí kontejner jako unhealthy při selhání.
HEALTHCHECK --interval=30s \
            --timeout=10s \
            --start-period=20s \
            --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

# --- Spuštění ---
# sys.path setup je v src/main.py; --mode web spustí uvicorn programaticky.
CMD ["python", "src/main.py", "--mode", "web"]
