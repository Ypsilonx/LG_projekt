# -*- coding: utf-8 -*-
"""
FastAPI webová aplikace pro LG ThinQ Klimatizace.

Hlavní vstupní bod webového serveru:
- Inicializuje sdílené prostředky (ThinQAPI, MQTT) přes lifespan.
- Mountuje statické soubory a Jinja2 šablony.
- Registruje routery pro jednotlivé oblasti funkcionality.

Spouštění (přes main.py):
    python src/main.py --mode web
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server_api import ThinQAPI
from web.routes.devices import router as devices_router
from web.routes.control import router as control_router
from web.routes.ws import router as ws_router, manager as ws_manager

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Životní cyklus aplikace.

    Startup:  Inicializuje sdílenou instanci ThinQAPI (HTTP session).
              Pokud inicializace selže (chybějící config.json, neplatný token),
              aplikace přesto nastartuje – endpointy vyžadující API vrátí HTTP 503.
    Shutdown: Čistě odpojí MQTT a uzavře HTTP session.
    """
    # --- Startup ---
    try:
        api = ThinQAPI()
        await api.initialize()
        app.state.api = api
        app.state.api_error = None
        logger.info("✅ ThinQAPI inicializováno")
    except Exception as exc:
        logger.error(f"❌ ThinQAPI inicializace selhala: {exc}")
        app.state.api = None
        app.state.api_error = str(exc)

    # --- MQTT bridge → WebSocket ---
    # Zachytíme aktuální asyncio smyčku, která bude použita pro
    # přechod z C++ vlákna AWS CRT SDK do asyncio (run_coroutine_threadsafe).
    loop = asyncio.get_event_loop()

    def _on_mqtt_message(topic, payload, dup, qos, retain, **kwargs):
        """
        MQTT callback volaný z AWS CRT C++ vlákna.
        Přemostí zprávu do asyncio smyčky a odešle všem WS klientům.
        """
        try:
            if isinstance(payload, (bytes, bytearray)):
                data = json.loads(payload.decode("utf-8"))
            else:
                data = payload if isinstance(payload, dict) else {}

            # Stav zařízení je zabalen v event.push (viz GUI mixin)
            device_status = data.get("event", {}).get("push", data)

            message = {
                "type": "device_status",
                "data": device_status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            asyncio.run_coroutine_threadsafe(ws_manager.broadcast(message), loop)
        except Exception as exc:
            logger.error(f"❌ MQTT→WS bridge chyba: {exc}")

    if app.state.api is not None:
        mqtt_ok = await app.state.api.connect_mqtt(on_message=_on_mqtt_message)
        app.state.mqtt_connected = mqtt_ok
        if mqtt_ok:
            logger.info("✅ MQTT připojeno – real-time push aktivní")
        else:
            logger.warning("⚠️ MQTT nepřipojeno – WS push nebude aktivní")
    else:
        app.state.mqtt_connected = False

    yield

    # --- Shutdown ---
    api_instance: ThinQAPI | None = getattr(app.state, "api", None)
    if api_instance is not None:
        await api_instance.close()
        logger.info("ThinQAPI session uzavřena")


app = FastAPI(
    title="LG Klimatizace",
    description="Webové rozhraní pro ovládání LG ThinQ klimatizace",
    version="1.0.0",
    lifespan=lifespan,
    # Swagger UI dostupný na /docs, ReDoc na /redoc
)

# Statické soubory (CSS, JS, obrázky)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Jinja2 šablony
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# ---------------------------------------------------------------------------
# Routery
# ---------------------------------------------------------------------------
app.include_router(devices_router)
app.include_router(control_router)
app.include_router(ws_router)


# ---------------------------------------------------------------------------
# Základní endpointy
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    Používá se Docker HEALTHCHECK direktivou i externím monitoringem.

    Returns:
        dict: Stav služby ``{"status": "ok"}``.
    """
    return {"status": "ok", "service": "lg-klimatizace"}


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """
    Hlavní dashboard – přehled stavu zařízení.

    Args:
        request: HTTP požadavek (předáván do Jinja2 kontextu).

    Returns:
        HTMLResponse: Vyrendrovaný dashboard.html.
    """
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={},
    )
