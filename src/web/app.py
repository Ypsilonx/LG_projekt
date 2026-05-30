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

from command_executor import execute_plan
from command_policy import build_command_plan
from server_api import ThinQAPI
from web.routes.devices import router as devices_router
from web.routes.control import router as control_router
from web.routes.ws import router as ws_router, manager as ws_manager
from web.routes.mode import router as mode_router
from web.routes.weather import router as weather_router
from web.routes.schedule import router as schedule_router
from web.routes.energy import router as energy_router

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent
_STATE_FILE = BASE_DIR.parent.parent / "data" / "state.json"


def _load_control_mode() -> str:
    """
    Načte naposledy uložený control_mode z data/state.json.

    Returns:
        str: "AUTO" nebo "HAND". Výchozí je "AUTO" pokud soubor neexistuje nebo je chybný.
    """
    try:
        if _STATE_FILE.exists():
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            mode = data.get("control_mode", "AUTO")
            return mode if mode in ("AUTO", "HAND") else "AUTO"
    except Exception as exc:
        logger.warning("Nelze načíst state.json: %s", exc)
    return "AUTO"


# ---------------------------------------------------------------------------
# Scheduler – background task
# ---------------------------------------------------------------------------

async def _run_schedule_on(api: ThinQAPI, device_id: str, action: dict) -> None:
    """
    Provede time_on akci plánu: zapne zařízení a aplikuje nastavení.

    Postup:
        1. Zapnutí (nebo přímá změna módu, která zapnutí zahrnuje).
        2. Nastavení cílové teploty (pokud je v akci).
        3. Nastavení intenzity ventilátoru (pokud je v akci).

    Args:
        api:       Inicializovaná ThinQAPI instance.
        device_id: ThinQ ID cílového zařízení.
        action:    Slovník ``{mode, temperature, wind_strength}`` z plánu.
    """
    try:
        status = await api.get_device_status(device_id)

        # Krok 1: zapnout – change_mode zahrnuje power_on precondition
        if action.get("mode"):
            plan = build_command_plan("change_mode", (action["mode"],), status)
        else:
            plan = build_command_plan("power_on", (), status)

        if not plan.should_skip:
            await execute_plan(api, device_id, plan, status)
            await asyncio.sleep(1.5)
            status = await api.get_device_status(device_id)

        # Krok 2: teplota
        if action.get("temperature") is not None:
            plan = build_command_plan("set_temperature", (action["temperature"],), status)
            if not plan.should_skip:
                await execute_plan(api, device_id, plan, status)
                await asyncio.sleep(1.0)
                status = await api.get_device_status(device_id)

        # Krok 3: ventilátor
        if action.get("wind_strength"):
            plan = build_command_plan("set_wind_strength", (action["wind_strength"],), status)
            if not plan.should_skip:
                await execute_plan(api, device_id, plan, status)

        logger.info("✅ Plánovač: time_on akce dokončena (%s...)", device_id[:8])
    except Exception as exc:
        logger.error("❌ Plánovač: chyba při time_on: %s", exc)


async def _run_schedule_off(api: ThinQAPI, device_id: str) -> None:
    """
    Provede time_off akci plánu: vypne zařízení.

    Args:
        api:       Inicializovaná ThinQAPI instance.
        device_id: ThinQ ID cílového zařízení.
    """
    try:
        status = await api.get_device_status(device_id)
        plan = build_command_plan("power_off", (), status)
        if not plan.should_skip:
            await execute_plan(api, device_id, plan, status)
        logger.info("✅ Plánovač: time_off akce dokončena (%s...)", device_id[:8])
    except Exception as exc:
        logger.error("❌ Plánovač: chyba při time_off: %s", exc)


async def _scheduler_loop(app: FastAPI) -> None:
    """
    Pozadí smyčka plánovače – každou minutu kontroluje schedule.json.

    Čeká vždy na začátek příští minuty, pak projde aktivní záznamy
    a spustí time_on / time_off akce, jejichž čas odpovídá aktuálnímu
    HH:MM a den v týdnu je v povoleném seznamu (nebo je seznam prázdný).

    Akce se provedou jen pokud je v settings.json zapnuto
    ``enable_scheduler`` i ``auto_execute``. Každá akce se v danou minutu
    provede nejvýše jednou (deduplication přes ``_executed`` set).

    Args:
        app: FastAPI aplikační instance (přístup k app.state.api).
    """
    _executed: set[str] = set()  # "entry_id:YYYY-MM-DD HH:MM:on/off"
    schedule_path = BASE_DIR.parent.parent / "data" / "schedule.json"
    logger.info("⏰ Plánovač spuštěn")

    while True:
        # Počkat na začátek příští minuty (+0.1 s tolerance)
        now = datetime.now()
        await asyncio.sleep(60 - now.second + 0.1)

        now = datetime.now()
        current_hhmm = now.strftime("%H:%M")
        weekday = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][now.weekday()]
        today = now.strftime("%Y-%m-%d")

        try:
            if not schedule_path.exists():
                continue

            sched_data = json.loads(schedule_path.read_text(encoding="utf-8"))
            settings = sched_data.get("settings", {})

            if not settings.get("enable_scheduler") or not settings.get("auto_execute"):
                continue

            api: ThinQAPI | None = getattr(app.state, "api", None)
            if api is None:
                continue

            device_ids = list(getattr(app.state, "known_device_ids", set()))
            if not device_ids:
                # Záloha: načíst device IDs ze souboru devices.json
                # (používá se pokud get_devices() selhalo při startu serveru)
                _devices_file = BASE_DIR.parent.parent / "data" / "devices.json"
                if _devices_file.exists():
                    try:
                        _devs = json.loads(_devices_file.read_text(encoding="utf-8"))
                        device_ids = [
                            d["deviceId"]
                            for d in _devs
                            if d.get("deviceId")
                            and d.get("deviceInfo", {}).get("deviceType") == "DEVICE_AIR_CONDITIONER"
                        ]
                        if device_ids:
                            logger.info(
                                "⏰ Plánovač: known_device_ids prázdné, záloha ze souboru (%d AC)",
                                len(device_ids),
                            )
                    except Exception as _exc:
                        logger.warning("⏰ Plánovač: záloha devices.json selhala: %s", _exc)
            if not device_ids:
                continue
            device_id = next(iter(device_ids))

            for entry in sched_data.get("schedules", []):
                if not entry.get("enabled"):
                    continue

                days = entry.get("days") or []
                if days and weekday not in days:
                    continue

                entry_id = entry.get("id", "")
                action = entry.get("action") or {}
                name = entry.get("name", entry_id)

                # time_on
                key_on = f"{entry_id}:{today} {current_hhmm}:on"
                if entry.get("time_on") == current_hhmm and key_on not in _executed:
                    _executed.add(key_on)
                    logger.info("⏰ Plánovač: time_on pro '%s' (%s)", name, current_hhmm)
                    await _run_schedule_on(api, device_id, action)

                # time_off
                time_off = entry.get("time_off")
                key_off = f"{entry_id}:{today} {current_hhmm}:off"
                if time_off and time_off == current_hhmm and key_off not in _executed:
                    _executed.add(key_off)
                    logger.info("⏰ Plánovač: time_off pro '%s' (%s)", name, current_hhmm)
                    await _run_schedule_off(api, device_id)

            # Vyčistit záznamy staršího dne
            _executed = {k for k in _executed if f":{today} " in k}

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("❌ Plánovač: chyba v hlavní smyčce: %s", exc)


async def _weather_refresh_loop(app: FastAPI) -> None:
    """
    Pozadí smyčka pro periodickou aktualizaci předpovědi počasí z ČHMÚ.

    Stahuje čerstvý forecast jednou za hodinu a ukládá výsledek do
    ``app.state.weather_cache``. Běží nezávisle na ``control_mode`` –
    data jsou aktuální vždy; automatika i manuální režim z nich čtou.

    Při startu aplikace se první fetch provede okamžitě (bez úvodního
    čekání), aby byla data dostupná ihned po spuštění serveru.

    Args:
        app: FastAPI aplikační instance (přístup k app.state).
    """
    from web.routes.weather import _fetch_weather_data, _load_weather_config

    logger.info("🌤️ Weather refresh loop spuštěn")

    while True:
        try:
            config = _load_weather_config()
            if config.get("enabled", False):
                result = await _fetch_weather_data(config)
                if "error" not in result:
                    app.state.weather_cache = result
                    app.state.weather_cache_time = datetime.now(timezone.utc)
                    logger.info("🌤️ Počasí aktualizováno z ČHMÚ meteogram")
                else:
                    logger.warning("⚠️ Počasí: aktualizace selhala – %s", result.get("error"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("❌ Počasí: neočekávaná chyba v refresh loop: %s", exc)

        await asyncio.sleep(3600)  # 1 hodina


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
        # Pre-cache device IDs pro MQTT topic parsing
        try:
            devs = await api.get_devices()
            app.state.known_device_ids = {
                d.get("device_id", "") for d in devs if d.get("device_id")
            }
        except Exception:
            app.state.known_device_ids = set()
    except Exception as exc:
        logger.error(f"❌ ThinQAPI inicializace selhala: {exc}")
        app.state.api = None
        app.state.api_error = str(exc)
        app.state.known_device_ids = set()

    # Inicializace sdíleného in-memory stavu (mode se načítá z state.json)
    app.state.control_mode = _load_control_mode()
    app.state.weather_cache = None
    app.state.weather_cache_time = None

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

            # Pokus o extrakci device_id z MQTT tématu
            device_id = None
            topic_str = str(topic) if topic else ""
            for dev_id in getattr(app.state, "known_device_ids", set()):
                if dev_id and dev_id in topic_str:
                    device_id = dev_id
                    break

            message = {
                "type": "device_status",
                "device_id": device_id,
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
            # Přihlásit event subscripci pro každé zařízení.
            # Bez tohoto volání LG platforma neposílá změny stavu zařízení
            # z externích zdrojů (telefon, dálkový ovladač) přes MQTT.
            for _dev_id in app.state.known_device_ids:
                await app.state.api.subscribe_device_events(_dev_id)
        else:
            logger.warning("⚠️ MQTT nepřipojeno – WS push nebude aktivní")
    else:
        app.state.mqtt_connected = False

    # Spustit background tasky
    scheduler_task = asyncio.create_task(_scheduler_loop(app))
    weather_task = asyncio.create_task(_weather_refresh_loop(app))

    yield

    # --- Shutdown ---
    scheduler_task.cancel()
    weather_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        logger.info("⏰ Plánovač zastaven")
    try:
        await weather_task
    except asyncio.CancelledError:
        logger.info("🌤️ Weather refresh loop zastaven")

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
app.include_router(mode_router)
app.include_router(weather_router)
app.include_router(schedule_router)
app.include_router(energy_router)


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
        context={"active_page": "dashboard"},
    )


@app.get("/automation", response_class=HTMLResponse)
async def automation_page(request: Request):
    """
    Stránka automatizace – přepínač HAND/AUTO a předpověď počasí.

    Args:
        request: HTTP požadavek.

    Returns:
        HTMLResponse: Vyrendrovaný automation.html.
    """
    return templates.TemplateResponse(
        request=request,
        name="automation.html",
        context={"active_page": "automation"},
    )


@app.get("/scheduler", response_class=HTMLResponse)
async def scheduler_page(request: Request):
    """
    Stránka plánování – přehled naplánovaných akcí.

    Args:
        request: HTTP požadavek.

    Returns:
        HTMLResponse: Vyrendrovaný scheduler.html.
    """
    return templates.TemplateResponse(
        request=request,
        name="scheduler.html",
        context={"active_page": "scheduler"},
    )
