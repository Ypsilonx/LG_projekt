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
# curl je potřeba pro instalaci UV. Po instalaci odstraníme apt cache.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/*

# --- Instalace UV (správce závislostí) ---
# UV nahrazuje pip; --no-modify-path zamezí úpravě PATH v systémovém shellu.
RUN curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh

# --- Python závislosti (vlastní vrstva pro cache) ---
# Kopírujeme pouze soubory potřebné pro instalaci závislostí (pro efektivní Docker cache).
# --frozen: použije přesné verze z uv.lock; --no-dev: vynechá vývojové závislosti;
# --no-editable: neinstaluje projekt samotný (src/ se kopíruje přímo).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

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
    CMD [".venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

# --- Spuštění ---
# sys.path setup je v src/main.py; --mode web spustí uvicorn programaticky.
CMD [".venv/bin/python", "src/main.py", "--mode", "web"]
