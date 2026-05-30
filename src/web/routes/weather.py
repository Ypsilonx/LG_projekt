# -*- coding: utf-8 -*-
"""
Router: Počasí – GET /api/weather/forecast + GET /api/weather/config.

Stahuje hodinová meteorologická data z ČHMÚ meteogram API a vrací
strukturovaný forecast s teplotou, oblačností a srážkami.

Výsledek je cachován v ``app.state.weather_cache`` po dobu nastavenou
v ``automation_rules.json`` (výchozí: 3 hodiny).
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/weather", tags=["Počasí"])

_DATA_DIR = Path("data")
_METEOGRAM_BASE = "https://data-provider.chmi.cz/api/graphs/graf.meteogram"


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


@router.get("/config", summary="Weather konfigurace")
async def get_weather_config() -> dict:
    """
    Vrátí weather sekci z automation_rules.json.

    Returns:
        dict: Konfigurace (provider, poi_id, location, horizon, offset …).
    """
    return _load_weather_config()


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
    sensor_offset = float(config.get("sensor_offset_c", 0.0))
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
                "temp_c": round(float(t2m) + sensor_offset, 1),
                "temp_raw_c": round(float(t2m), 1),
            }

            # Volitelná pole – přítomnost závisí na verzi API
            for src_key, dst_key in (
                ("n", "cloudiness_pct"),
                ("rr1h", "precip_mm_h"),
                ("rh2m", "humidity_pct"),
                ("ff10m", "wind_ms"),
                ("dd", "wind_dir_deg"),   # směr větru ve stupních
            ):
                val = row.get(src_key)
                if val is not None:
                    try:
                        point[dst_key] = round(float(val), 1)
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

        return {
            "enabled": True,
            "location": location,
            "poi_id": poi_id,
            "sensor_offset_c": sensor_offset,
            "horizon_hours": horizon_h,
            "fetched_at": now_utc.isoformat(),
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
                 sensor_offset_c, hourly: [...]}``.
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
    return result
