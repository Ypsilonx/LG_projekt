# -*- coding: utf-8 -*-
"""
Teplotní limity klimatizace odvozené z device_profile.json.

Modul čte ``data/device_profile.json`` a vrací minimální a maximální
povolenou teplotu pro každý pracovní režim zařízení. Při každém volání
čte soubor znovu, takže automaticky reflektuje případné aktualizace profilu
(např. po aktualizaci firmware přes ``scripts/fetch_device_profile.py``).

Pokud soubor nelze načíst nebo neobsahuje očekávané klíče, jsou vráceny
konzervativní výchozí hodnoty odvozené z API specifikace.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PROFILE_FILE = Path(__file__).parent.parent / "data" / "device_profile.json"

# Výchozí hodnoty při chybě čtení profilu – konzervativní, dle API specifikace
_FALLBACK: dict[str, int] = {"min": 18, "max": 30}
_FALLBACK_HEAT: dict[str, int] = {"min": 16, "max": 30}

# Mapování pracovního módu → klíč v sekci temperature device profilu
_MODE_TO_PROFILE_KEY: dict[str, str] = {
    "HEAT": "heatTargetTemperature",
    "COOL": "coolTargetTemperature",
    "AUTO": "autoTargetTemperature",
}


def _read_profile() -> dict:
    """
    Načte a vrátí obsah device_profile.json.

    Returns:
        dict: Obsah profilu nebo prázdný dict při chybě.
    """
    try:
        return json.loads(_PROFILE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("device_profile.json nenalezen: %s", _PROFILE_FILE)
    except Exception as exc:
        logger.warning("Chyba čtení device_profile.json: %s", exc)
    return {}


def get_temp_limits(job_mode: str) -> dict[str, int] | None:
    """
    Vrátí teplotní limity pro daný pracovní režim klimatizace.

    Pořadí hledání v profilu:
        1. Specifický klíč pro mód (``heatTargetTemperature`` apod.)
        2. Obecný ``targetTemperature`` (write range)
        3. Hardcoded fallback dle API specifikace

    Args:
        job_mode: Pracovní mód zařízení (COOL, HEAT, AUTO, AIR_DRY, FAN …)

    Returns:
        dict s klíči ``min`` a ``max`` (°C), nebo ``None`` pro FAN
        (teplota v režimu FAN není relevantní).
    """
    mode = (job_mode or "").upper()

    if mode == "FAN":
        return None

    profile = _read_profile()
    temp_section: dict = profile.get("property", {}).get("temperature", {})

    # Zkus specifický klíč pro mód
    profile_key = _MODE_TO_PROFILE_KEY.get(mode)
    if profile_key:
        w = temp_section.get(profile_key, {}).get("value", {}).get("w", {})
        if isinstance(w, dict) and w.get("min") is not None and w.get("max") is not None:
            return {"min": int(w["min"]), "max": int(w["max"])}

    # Fallback na obecný targetTemperature (write range) – platí pro AIR_DRY a neznámé módy
    w = temp_section.get("targetTemperature", {}).get("value", {}).get("w", {})
    if isinstance(w, dict) and w.get("min") is not None and w.get("max") is not None:
        return {"min": int(w["min"]), "max": int(w["max"])}

    # Hardcoded fallback dle API specifikace
    logger.debug("Teplotní limity pro mód %s: používám hardcoded fallback", mode)
    return _FALLBACK_HEAT.copy() if mode == "HEAT" else _FALLBACK.copy()


def get_all_temp_limits() -> dict[str, dict[str, int] | None]:
    """
    Vrátí slovník pracovní mód → teplotní limity pro všechny podporované módy.

    Určeno především pro API endpoint (frontend).

    Returns:
        dict: Klíče jsou názvy módů (COOL, HEAT, AUTO, AIR_DRY, FAN).
              Hodnota je ``{"min": int, "max": int}`` nebo ``None`` pro FAN.
    """
    modes = ["COOL", "HEAT", "AUTO", "AIR_DRY", "FAN"]
    return {m: get_temp_limits(m) for m in modes}
