# -*- coding: utf-8 -*-
"""
Router: Počasí – GET /api/weather/forecast + GET /api/weather/config.

Stahuje hodinová meteorologická data z ČHMÚ meteogram API (model ALADIN)
a vrací strukturovaný forecast. Každý bod obsahuje teplotu, oblačnost,
srážky, vlhkost, rýchlost a směr větru, nárazy, tlak a ikonu počasí.
Klíč ``current`` ukazuje na nejbližší (aktuální) hodinový bod.

Výsledek je cachován v ``app.state.weather_cache`` po dobu nastavenou
v ``automation_rules.json`` (výchozí: 3 hodiny).
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp
from fastapi import APIRouter, Request
from poer_api import fetch_poer_status_cached

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/weather", tags=["Počasí"])

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_METEOGRAM_BASE = "https://data-provider.chmi.cz/api/graphs/graf.meteogram"

# Soubor pro perzistenci poslední úspěšně stažené předpovědi. Umožňuje
# zobrazit data ihned po restartu serveru (bez čekání na první fetch) a
# slouží jako základ pro budoucí plánovací automatiku (24h plány dle
# předpovědi). Přepisuje se při každé úspěšné aktualizaci.
_CACHE_FILE = _DATA_DIR / "weather_cache.json"


def _load_weather_config() -> dict:
    """
    Načte sekci ``weather`` z data/automation_rules.json.

    Returns:
        dict: Weather konfigurace nebo prázdný dict při chybě čtení.
    """
    path = _DATA_DIR / "automation_rules.json"
    if not path.exists():
        return {}
    try:
        rules = json.loads(path.read_text(encoding="utf-8"))
        return rules.get("weather", {})
    except Exception:
        return {}


def _read_ac_indoor_temperature_proxy_offset(config: dict) -> float:
    """Return temporary AC indoor proxy offset from weather config.

    The value is a transitional workaround for the built-in AC indoor sensor.
    It must never be applied to outdoor forecast data.

    Args:
        config: Weather configuration object.

    Returns:
        float: Temporary indoor proxy offset in Celsius.
    """

    raw_value = config.get(
        "ac_indoor_temperature_proxy_offset_c",
        config.get("sensor_offset_c", 0.0),
    )
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        logger.warning("Neplatna hodnota AC indoor proxy offsetu: %s", raw_value)
        return 0.0


def _normalize_weather_config_for_clients(config: dict) -> dict:
    """Normalize weather config for UI clients and future sensor integration.

    Args:
        config: Raw weather section from automation rules.

    Returns:
        dict: Client-safe configuration with explicit field names.
    """

    normalized = dict(config)
    normalized["ac_indoor_temperature_proxy_offset_c"] = (
        _read_ac_indoor_temperature_proxy_offset(config)
    )

    configured_indoor_source = str(
        config.get("indoor_current_temperature_source", "ac_builtin_sensor_proxy")
    ).strip() or "ac_builtin_sensor_proxy"

    indoor_override_c = _read_optional_float(config.get("indoor_current_temperature_c"))
    if indoor_override_c is None:
        normalized["indoor_current_temperature_c"] = None
        if configured_indoor_source == "poer_api":
            normalized["indoor_temperature_is_estimated"] = False
            normalized["indoor_temperature_source"] = "poer_api"
        else:
            normalized["indoor_temperature_is_estimated"] = True
            normalized["indoor_temperature_source"] = "ac_builtin_sensor_proxy"
    else:
        normalized["indoor_current_temperature_c"] = indoor_override_c
        normalized["indoor_temperature_is_estimated"] = False
        normalized["indoor_temperature_source"] = configured_indoor_source

    # room_target + correction = AC target
    normalized["setpoint_correction_c"] = -normalized["ac_indoor_temperature_proxy_offset_c"]

    if "outdoor_current_temperature_c" not in normalized:
        normalized["outdoor_current_temperature_c"] = config.get("current_temperature_c")
    if "outdoor_current_temperature_source" not in normalized:
        normalized["outdoor_current_temperature_source"] = config.get(
            "current_temperature_source",
            "forecast",
        )
    if "outdoor_current_temperature_url" not in normalized:
        normalized["outdoor_current_temperature_url"] = config.get("current_temperature_url")

    return normalized


def _read_optional_float(value: object) -> float | None:
    """Convert a value to float when possible."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_temperature_from_payload(payload: object) -> float | None:
    """Extract a temperature value from a JSON payload.

    The helper accepts several common shapes such as
    ``{"temperature_c": 12.3}``, ``{"temp_c": 12.3}`` or nested objects.
    """
    if payload is None:
        return None

    if isinstance(payload, (int, float)):
        return float(payload)

    if isinstance(payload, dict):
        for key in ("current_temperature_c", "temperature_c", "temp_c", "value", "current_temp_c"):
            value = _read_optional_float(payload.get(key))
            if value is not None:
                return value

        for nested_key in ("current", "data", "result"):
            nested_value = payload.get(nested_key)
            if nested_value is not None:
                extracted = _extract_temperature_from_payload(nested_value)
                if extracted is not None:
                    return extracted

    if isinstance(payload, (list, tuple)):
        for item in payload:
            extracted = _extract_temperature_from_payload(item)
            if extracted is not None:
                return extracted

    return None


def _extract_temperature_from_chmi_html(html_text: str) -> float | None:
    """Extract the latest temperature from the CHMI station HTML page.

    The page contains values like ``22,0 °C`` in a measurement table. The
    parser looks for the first temperature occurrence in the document and
    converts the comma decimal separator to a dot.
    """
    if not html_text:
        return None

    match = re.search(r"(\d{1,2}),\s*(\d)\s*°C", html_text)
    if match is None:
        return None

    whole = int(match.group(1))
    fractional = int(match.group(2))
    return round(float(f"{whole}.{fractional}"), 1)


async def _fetch_external_current_temperature(
    config: dict,
    session: aiohttp.ClientSession | None = None,
) -> tuple[float | None, str]:
    """Fetch current outdoor temperature from an external HTTP endpoint.

    The endpoint can return a simple JSON object, for example
    ``{"temperature_c": 12.3}`` or ``{"current": {"temp_c": 12.3}}``.
    If the fetch fails or the payload is invalid, the function returns
    ``(None, "forecast")`` so the existing forecast fallback remains active.
    """
    override_value = config.get("outdoor_current_temperature_c", config.get("current_temperature_c"))
    if override_value is None:
        override_value = (
            os.getenv("LG_WEATHER_OUTDOOR_CURRENT_TEMPERATURE_C")
            or os.getenv("LG_WEATHER_CURRENT_TEMPERATURE_C")
        )

    if override_value is not None:
        try:
            return float(override_value), str(
                config.get(
                    "outdoor_current_temperature_source",
                    config.get("current_temperature_source"),
                )
                or os.getenv("LG_WEATHER_OUTDOOR_CURRENT_TEMPERATURE_SOURCE")
                or os.getenv("LG_WEATHER_CURRENT_TEMPERATURE_SOURCE")
                or "external"
            )
        except (TypeError, ValueError):
            logger.warning("Neplatna hodnota outdoor_current_temperature_c: %s", override_value)

    url = (
        config.get("outdoor_current_temperature_url")
        or config.get("current_temperature_url")
        or os.getenv("LG_WEATHER_OUTDOOR_CURRENT_TEMPERATURE_URL")
        or os.getenv("LG_WEATHER_CURRENT_TEMPERATURE_URL")
    )
    if not url:
        return None, "forecast"

    source_label = str(
        config.get(
            "outdoor_current_temperature_source",
            config.get("current_temperature_source"),
        )
        or os.getenv("LG_WEATHER_OUTDOOR_CURRENT_TEMPERATURE_SOURCE")
        or os.getenv("LG_WEATHER_CURRENT_TEMPERATURE_SOURCE")
        or "external"
    ).strip() or "external"

    try:
        timeout = aiohttp.ClientTimeout(total=6)
        headers = {"Accept": "application/json, text/html;q=0.9, */*;q=0.8", "User-Agent": "Mozilla/5.0"}
        if session is None:
            async with aiohttp.ClientSession(timeout=timeout) as local_session:
                async with local_session.get(str(url), headers=headers) as response:
                    response.raise_for_status()
                    response_headers = getattr(response, "headers", {}) or {}
                    if hasattr(response_headers, "get"):
                        content_type = response_headers.get("Content-Type", "")
                    else:
                        content_type = ""
                    if "application/json" in str(content_type).lower():
                        payload = await response.json(content_type=None)
                        temperature_c = _extract_temperature_from_payload(payload)
                    else:
                        text = await response.text()
                        temperature_c = _extract_temperature_from_chmi_html(text)
        else:
            async with session.get(str(url), headers=headers) as response:
                response.raise_for_status()
                response_headers = getattr(response, "headers", {}) or {}
                if hasattr(response_headers, "get"):
                    content_type = response_headers.get("Content-Type", "")
                else:
                    content_type = ""
                if "application/json" in str(content_type).lower():
                    payload = await response.json(content_type=None)
                    temperature_c = _extract_temperature_from_payload(payload)
                else:
                    text = await response.text()
                    temperature_c = _extract_temperature_from_chmi_html(text)
    except Exception as exc:
        logger.warning("Nepodařilo se načíst externí teplotu z %s: %s", url, exc)
        return None, "forecast"

    if temperature_c is None:
        logger.warning("Externí zdroj teploty %s nevrátil platnou hodnotu", url)
        return None, "forecast"

    return round(float(temperature_c), 1), source_label


async def _resolve_current_temperature(
    config: dict,
    hourly: list[dict],
    session: aiohttp.ClientSession | None = None,
) -> tuple[float | None, str]:
    """Resolve current temperature from explicit override or fallback forecast.

    The application now supports an explicit current temperature value from an
    external source such as ESP32 or a weather station. If none is supplied,
    the first hourly forecast point is used as a safe fallback so the UI and
    automation still keep working.
    """
    external_temperature_c, external_source = await _fetch_external_current_temperature(config, session=session)
    if external_temperature_c is not None:
        return external_temperature_c, external_source

    if hourly:
        try:
            return float(hourly[0].get("temp_c", 0.0)), "forecast"
        except (TypeError, ValueError):
            return None, "forecast"

    return None, "forecast"


def save_weather_cache(data: dict) -> None:
    """
    Uloží předpověď do ``data/weather_cache.json`` (atomický zápis).

    Zapisuje se přes dočasný soubor a následný přejmenováním, aby při
    pádu během zápisu nezůstal poškozený JSON. Volá se po každém úspěšném
    stažení dat (background loop i HTTP endpoint).

    Args:
        data: Výsledek ``_fetch_weather_data`` (bez klíče ``error``).
    """
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_CACHE_FILE)
    except Exception as exc:
        logger.warning("Nepodařilo se uložit weather cache: %s", exc)


def load_weather_cache() -> tuple[dict | None, datetime | None]:
    """
    Načte poslední uloženou předpověď z ``data/weather_cache.json``.

    Returns:
        tuple: ``(data, fetched_at)`` – data předpovědi a čas jejich
               stažení (UTC). Při chybějícím/poškozeném souboru nebo bez
               platného ``fetched_at`` vrací ``(None, None)``.
    """
    if not _CACHE_FILE.exists():
        return None, None
    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Nepodařilo se načíst weather cache: %s", exc)
        return None, None

    fetched_raw = data.get("fetched_at") if isinstance(data, dict) else None
    fetched_at: datetime | None = None
    if fetched_raw:
        try:
            fetched_at = datetime.fromisoformat(str(fetched_raw).replace("Z", "+00:00"))
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        except ValueError:
            fetched_at = None
    return data, fetched_at



@router.get("/config", summary="Weather konfigurace")
async def get_weather_config() -> dict:
    """
    Vrátí weather sekci z automation_rules.json.

    Returns:
        dict: Konfigurace (provider, poi_id, location, horizon, offset …).
    """
    normalized = _normalize_weather_config_for_clients(_load_weather_config())

    if normalized.get("indoor_temperature_source") != "poer_api":
        return normalized

    poer_api_key = os.getenv("LG_POER_API_KEY", "").strip()
    if not poer_api_key:
        normalized["indoor_temperature_error"] = "POER: chybi LG_POER_API_KEY"
        return normalized

    poer_status = await fetch_poer_status_cached(
        api_key=poer_api_key,
        preferred_device_id=normalized.get("poer_device_id"),
    )
    poer_temp_c = poer_status.get("current_temperature_c")
    poer_target_temp_c = poer_status.get("target_temperature_c")
    poer_device_id = poer_status.get("device_id")
    poer_error = poer_status.get("error_text")
    if poer_device_id:
        normalized["poer_device_id"] = poer_device_id
    if poer_temp_c is not None:
        normalized["indoor_current_temperature_c"] = round(float(poer_temp_c), 1)
        normalized["poer_current_temperature_c"] = round(float(poer_temp_c), 1)
        normalized["indoor_temperature_is_estimated"] = False
    else:
        normalized["poer_current_temperature_c"] = None
    if poer_target_temp_c is not None:
        normalized["poer_target_temperature_c"] = round(float(poer_target_temp_c), 1)
    else:
        normalized["poer_target_temperature_c"] = None
    if poer_error:
        normalized["indoor_temperature_error"] = poer_error

    return normalized


async def _fetch_weather_data(config: dict) -> dict:
    """Stáhne a zparsuje hodinová meteogram data z ČHMÚ API.

    Provede HTTP GET na ČHMÚ meteogram endpoint a vrátí strukturovaný
    výsledek s hodinovými a denními daty. Nemodifikuje stav aplikace –
    zápisem do cache se stará volající (route nebo background task).

    Args:
        config: Sekce ``weather`` z automation_rules.json.

    Returns:
        dict: Výsledek s klíčem ``hourly`` a ``daily``. Při selhání
              obsahuje klíč ``error`` s popisem chyby.
    """
    poi_id = str(config.get("chmi_meteogram_poi_id", "510"))
    location = config.get("chmi_location_label", "")
    ac_indoor_proxy_offset = _read_ac_indoor_temperature_proxy_offset(config)
    horizon_h = int(config.get("forecast_horizon_hours", 24))
    url = f"{_METEOGRAM_BASE}/{poi_id}"
    now_utc = datetime.now(timezone.utc)
    horizon_cutoff = now_utc + timedelta(hours=horizon_h)

    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={"Accept": "application/json"}) as resp:
                resp.raise_for_status()
                payload = await resp.json(content_type=None)

        raw_points: list = payload.get("data", []) if isinstance(payload, dict) else []

        _CZECH_DAYS = ["Pondělí", "Úterý", "Středa", "Čtvrtek", "Pátek", "Sobota", "Neděle"]
        hourly: list[dict] = []
        _daily_map: dict[str, dict] = {}  # date_label -> akumulátor

        for row in raw_points:
            if not isinstance(row, dict):
                continue
            vt_raw = row.get("validityTime")
            t2m = row.get("t2m")
            if vt_raw is None or t2m is None:
                continue
            try:
                dt_utc = datetime.fromisoformat(str(vt_raw).replace("Z", "+00:00"))
                if dt_utc.tzinfo is None:
                    dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if dt_utc < now_utc or dt_utc > horizon_cutoff:
                continue

            local_dt = dt_utc.astimezone()
            date_key = local_dt.strftime("%d.%m.")
            point: dict = {
                "time_utc": dt_utc.isoformat(),
                "time_label": local_dt.strftime("%H:%M"),
                "date_label": date_key,
                "temp_c": round(float(t2m), 1),
                "temp_raw_c": round(float(t2m), 1),
            }

            # Volitelná číselná pole – mapování na skutečné klíče ČHMÚ
            # meteogram API (model ALADIN). Hodnoty jsou předpověď daného
            # modelu pro příslušnou hodinu.
            for src_key, dst_key in (
                ("cloudsTot", "cloudiness_pct"),    # celková oblačnost %
                ("prec", "precip_mm_h"),            # celkové srážky mm/h
                ("snow", "snow_mm_h"),              # sníh mm/h
                ("rh2m", "humidity_pct"),           # relativní vlhkost %
                ("windSpeed", "wind_ms"),           # rychlost větru m/s
                ("windGustSpeed", "wind_gust_ms"),  # nárazy větru m/s
                ("windDirection", "wind_dir_deg"),  # směr větru ve stupních
                ("mslp", "pressure_hpa"),           # tlak přepočtený na hladinu moře hPa
            ):
                val = row.get(src_key)
                if val is not None:
                    try:
                        point[dst_key] = round(float(val), 1)
                    except (TypeError, ValueError):
                        pass

            # Ikona počasí ČHMÚ (celé číslo) – ponecháváme bez zaokrouhlení
            icon_val = row.get("icon")
            if icon_val is not None:
                try:
                    point["icon"] = int(icon_val)
                except (TypeError, ValueError):
                    pass

            hourly.append(point)

            # Akumulace hodnot pro denní agregáty
            if date_key not in _daily_map:
                _daily_map[date_key] = {
                    "date_label": date_key,
                    "day_name": _CZECH_DAYS[local_dt.weekday()],
                    "temps": [],
                    "precips": [],
                    "cloudiness": [],
                }
            entry = _daily_map[date_key]
            entry["temps"].append(point["temp_c"])
            if "precip_mm_h" in point:
                entry["precips"].append(point["precip_mm_h"])
            if "cloudiness_pct" in point:
                entry["cloudiness"].append(point["cloudiness_pct"])

        # Denní sumáře – min/max teplota, celkové srážky, průměrná oblačnost
        daily: list[dict] = [
            {
                "date_label": d["date_label"],
                "day_name": d["day_name"],
                "min_temp_c": round(min(d["temps"]), 1),
                "max_temp_c": round(max(d["temps"]), 1),
                "total_precip_mm": round(sum(d["precips"]), 1) if d["precips"] else 0.0,
                "avg_cloudiness_pct": (
                    round(sum(d["cloudiness"]) / len(d["cloudiness"]))
                    if d["cloudiness"] else None
                ),
            }
            for d in _daily_map.values()
        ]

        current_temperature_c, current_temperature_source = await _resolve_current_temperature(
            config,
            hourly,
            session=session,
        )
        current_point = None
        if hourly:
            current_point = dict(hourly[0])
        elif current_temperature_c is not None:
            current_point = {
                "temp_c": round(float(current_temperature_c), 1),
                "time_label": "now",
                "date_label": datetime.now().astimezone().strftime("%d.%m."),
            }

        if current_point is not None and current_temperature_c is not None:
            current_point["temp_c"] = round(float(current_temperature_c), 1)
            current_point["current_temperature_c"] = round(float(current_temperature_c), 1)
            current_point["current_temperature_source"] = current_temperature_source

        return {
            "enabled": True,
            "location": location,
            "poi_id": poi_id,
            "ac_indoor_temperature_proxy_offset_c": ac_indoor_proxy_offset,
            "indoor_temperature_is_estimated": True,
            "indoor_temperature_source": "ac_builtin_sensor_proxy",
            "horizon_hours": horizon_h,
            "fetched_at": now_utc.isoformat(),
            "current": current_point,
            "current_temperature_c": current_temperature_c,
            "current_temperature_source": current_temperature_source,
            "outdoor_current_temperature_c": current_temperature_c,
            "outdoor_current_temperature_source": current_temperature_source,
            "forecast_3h": hourly[: min(3, len(hourly))],
            "hourly": hourly,
            "daily": daily,
        }

    except aiohttp.ClientError as exc:
        logger.warning("ČHMÚ meteogram fetch chyba: %s", exc)
        return {
            "enabled": True,
            "location": location,
            "poi_id": poi_id,
            "fetched_at": None,
            "error": f"Nepodařilo se stáhnout data: {exc}",
            "current": None,
            "current_temperature_c": None,
            "current_temperature_source": "forecast",
            "forecast_3h": [],
            "hourly": [],
        }
    except Exception:
        logger.exception("Neočekávaná chyba při získávání počasí")
        return {
            "enabled": True,
            "location": location,
            "poi_id": poi_id,
            "fetched_at": None,
            "error": "Interní chyba serveru",
            "current": None,
            "current_temperature_c": None,
            "current_temperature_source": "forecast",
            "forecast_3h": [],
            "hourly": [],
        }


@router.get("/forecast", summary="Hodinový forecast")
async def get_weather_forecast(request: Request) -> dict:
    """
    Vrátí hodinový forecast z ČHMÚ meteogram API.

    Cachuje výsledek v ``app.state.weather_cache`` po dobu
    ``refresh_interval_hours`` (výchozí 3 h). Každý bod obsahuje teplotu
    a volitelně oblačnost (``cloudiness_pct``), srážky (``precip_mm_h``)
    a vlhkost (``humidity_pct``).

    Args:
        request: HTTP požadavek – přístup k ``app.state``.

    Returns:
        dict: ``{enabled, location, fetched_at, horizon_hours,
                 hourly: [...]}``.
              Při chybě downloadu vrátí ``{..., error: str, hourly: []}``.
    """
    config = _load_weather_config()

    if not config.get("enabled", False):
        return {"enabled": False, "hourly": [], "location": None}

    now_utc = datetime.now(timezone.utc)
    refresh_hours = float(config.get("refresh_interval_hours", 3))

    # Zkontroluj platnost cache
    cache = getattr(request.app.state, "weather_cache", None)
    cache_time: datetime | None = getattr(request.app.state, "weather_cache_time", None)
    if cache is not None and cache_time is not None:
        age_hours = (now_utc - cache_time).total_seconds() / 3600
        if age_hours < refresh_hours:
            return cache

    result = await _fetch_weather_data(config)
    if "error" not in result:
        request.app.state.weather_cache = result
        request.app.state.weather_cache_time = now_utc
        save_weather_cache(result)
    return result
