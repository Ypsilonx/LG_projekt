# -*- coding: utf-8 -*-
"""
Router: Plánování – GET/POST/PUT/DELETE/PATCH /api/schedule/.

Čte a zapisuje ``data/schedule.json`` a vrací normalizovanou strukturu
``{schedules: [...], settings: {...}}``.

Každá položka plánu má tvar::

    {
      "id": "UUID",
      "name": "Ranní chlazení",
      "enabled": true,
      "days": ["mon","tue","wed","thu","fri"],  // prázdné = každý den
      "time_on": "08:00",
      "time_off": "09:00",                        // null = bez automatického vypnutí
      "action": {
        "mode": "COOL",                           // null = neměnit
        "temperature": 22.0,                     // null = neměnit
        "wind_strength": "MID"                   // null = neměnit
      }
    }
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/schedule", tags=["Plánování"])

_DATA_DIR = Path("data")

# Serializuje read-modify-write cyklus napříč souběžnými requesty (např. dva
# otevřené tab v prohlížeči), aby si dva zápisy navzájem nepřepsaly změny.
_write_lock = asyncio.Lock()


def _read_schedule() -> dict:
    """
    Načte a parsuje data/schedule.json.

    Podporuje dva formáty:
    - Nový: ``{"schedules": [...], "settings": {...}}``
    - Starý: přímý seznam plánů (převede na nový formát).

    Returns:
        dict: Normalizovaná struktura ``{schedules, settings}``.

    Raises:
        FileNotFoundError: Soubor neexistuje.
        json.JSONDecodeError: Soubor není validní JSON.
    """
    path = _DATA_DIR / "schedule.json"
    if not path.exists():
        return {"schedules": [], "settings": {"enable_scheduler": False}}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return {"schedules": raw, "settings": {"enable_scheduler": True}}
    return raw


@router.get("/", summary="Seznam naplánovaných akcí")
async def get_schedule() -> dict:
    """
    Vrátí obsah schedule.json jako ``{schedules, settings}``.

    Returns:
        dict: ``{"schedules": [...], "settings": {...}}``.

    Raises:
        HTTPException 500: JSON je poškozený nebo nečitelný.
    """
    try:
        return _read_schedule()
    except json.JSONDecodeError as exc:
        logger.error("schedule.json není validní JSON: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"schedule.json je poškozený: {exc}"
        ) from exc
    except Exception as exc:
        logger.exception("Chyba při načítání schedule.json")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Write helpers
# ─────────────────────────────────────────────────────────────────────────────

_VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_VALID_MODES = {"COOL", "HEAT", "FAN", "AUTO", "AIR_DRY"}
_VALID_FANS = {"AUTO", "LOW", "MID", "HIGH"}


def _write_schedule(data: dict) -> None:
    """Atomicky zapíše data/schedule.json (UTF-8, odsazení 2 mezery).

    Zapisuje se přes dočasný soubor a `replace`, aby pád procesu uprostřed
    zápisu (výpadek napájení, OOM kill v Dockeru) nezanechal poškozený JSON,
    který by shodil `_scheduler_loop` i tento router při dalším startu.

    Args:
        data: Normalizovaná struktura ``{schedules, settings}``.
    """
    path = _DATA_DIR / "schedule.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _validate_entry(entry: dict[str, Any]) -> None:
    """Ověří povinná pole a povolené hodnoty záznamu plánu.

    Args:
        entry: Surový slovník z požadavku.

    Raises:
        HTTPException 422: Validační chyba.
    """
    time_on = entry.get("time_on", "").strip()
    if not time_on:
        raise HTTPException(status_code=422, detail="Pole 'time_on' je povinné (formát HH:MM).")

    for tf in ("time_on", "time_off"):
        val = entry.get(tf)
        if val and val.strip():
            parts = val.strip().split(":")
            if len(parts) != 2 or not all(p.isdigit() for p in parts):
                raise HTTPException(status_code=422, detail=f"Pole '{tf}' musí být ve formátu HH:MM.")

    days = entry.get("days", [])
    if not isinstance(days, list):
        raise HTTPException(status_code=422, detail="Pole 'days' musí být seznam.")
    invalid_days = set(days) - _VALID_DAYS
    if invalid_days:
        raise HTTPException(status_code=422, detail=f"Neplatné hodnoty 'days': {invalid_days}.")

    action = entry.get("action", {})
    if not isinstance(action, dict):
        raise HTTPException(status_code=422, detail="Pole 'action' musí být objekt.")

    mode = action.get("mode")
    if mode is not None and mode not in _VALID_MODES:
        raise HTTPException(status_code=422, detail=f"Neplatný mód '{mode}'.")

    temp = action.get("temperature")
    if temp is not None:
        try:
            t = float(temp)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Teplota musí být číslo.")
        if not (16 <= t <= 30):
            raise HTTPException(status_code=422, detail="Teplota musí být v rozsahu 16–30 °C.")

    fan = action.get("wind_strength")
    if fan is not None and fan not in _VALID_FANS:
        raise HTTPException(status_code=422, detail=f"Neplatná intenzita ventilátoru '{fan}'.")


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Normalizuje záznam plánu do kanonického formátu.

    Args:
        entry: Surový slovník.

    Returns:
        dict: Normalizovaný záznam s validovanými hodnotami.
    """
    action = entry.get("action") or {}
    temp = action.get("temperature")
    return {
        "id": entry.get("id") or str(uuid.uuid4()),
        "name": str(entry.get("name") or "").strip(),
        "enabled": bool(entry.get("enabled", True)),
        "days": list(entry.get("days") or []),
        "time_on": (entry.get("time_on") or "").strip(),
        "time_off": (entry.get("time_off") or "").strip() or None,
        "action": {
            "mode": action.get("mode") or None,
            "temperature": round(float(temp), 1) if temp is not None else None,
            "wind_strength": action.get("wind_strength") or None,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# CRUD endpointy
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/entries", summary="Přidat plán", status_code=201)
async def create_schedule_entry(entry: dict[str, Any]) -> dict:
    """Přidá nový záznam do schedule.json a vrátí ho s přiřazeným ``id``.

    Args:
        entry: Slovník s poli name, time_on, time_off, days, action, enabled.

    Returns:
        dict: Uložený záznam včetně vygenerovaného UUID.

    Raises:
        HTTPException 422: Validační chyba vstupních dat.
        HTTPException 500: Chyba zápisu souboru.
    """
    _validate_entry(entry)
    entry.pop("id", None)           # id se vždy generuje serverem
    normalized = _normalize_entry(entry)
    try:
        async with _write_lock:
            data = _read_schedule()
            data["schedules"].append(normalized)
            _write_schedule(data)
    except Exception as exc:
        logger.exception("Chyba při vytváření plánu")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return normalized


@router.put("/entries/{entry_id}", summary="Upravit plán")
async def update_schedule_entry(entry_id: str, entry: dict[str, Any]) -> dict:
    """Aktualizuje existující záznam plánu.

    Args:
        entry_id: UUID záznamu.
        entry: Aktualizovaná data záznamu.

    Returns:
        dict: Aktualizovaný záznam.

    Raises:
        HTTPException 404: Záznam nenalezen.
        HTTPException 422: Validační chyba.
        HTTPException 500: Chyba zápisu souboru.
    """
    _validate_entry(entry)
    entry["id"] = entry_id
    normalized = _normalize_entry(entry)
    try:
        async with _write_lock:
            data = _read_schedule()
            for i, s in enumerate(data["schedules"]):
                if s.get("id") == entry_id:
                    data["schedules"][i] = normalized
                    _write_schedule(data)
                    return normalized
    except Exception as exc:
        logger.exception("Chyba při aktualizaci plánu %s", entry_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail=f"Plán '{entry_id}' nenalezen.")


@router.delete("/entries/{entry_id}", summary="Smazat plán")
async def delete_schedule_entry(entry_id: str) -> dict:
    """Smaže záznam plánu z schedule.json.

    Args:
        entry_id: UUID záznamu.

    Returns:
        dict: ``{"deleted": entry_id}``

    Raises:
        HTTPException 404: Záznam nenalezen.
        HTTPException 500: Chyba zápisu souboru.
    """
    try:
        async with _write_lock:
            data = _read_schedule()
            original = len(data["schedules"])
            data["schedules"] = [s for s in data["schedules"] if s.get("id") != entry_id]
            if len(data["schedules"]) == original:
                raise HTTPException(status_code=404, detail=f"Plán '{entry_id}' nenalezen.")
            _write_schedule(data)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Chyba při mazání plánu %s", entry_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"deleted": entry_id}


@router.patch("/entries/{entry_id}/toggle", summary="Přepnout aktivaci plánu")
async def toggle_schedule_entry(entry_id: str) -> dict:
    """Přepne stav enabled/disabled záznamu plánu.

    Args:
        entry_id: UUID záznamu.

    Returns:
        dict: Aktualizovaný záznam.

    Raises:
        HTTPException 404: Záznam nenalezen.
        HTTPException 500: Chyba zápisu souboru.
    """
    try:
        async with _write_lock:
            data = _read_schedule()
            for s in data["schedules"]:
                if s.get("id") == entry_id:
                    s["enabled"] = not s.get("enabled", True)
                    _write_schedule(data)
                    return s
    except Exception as exc:
        logger.exception("Chyba při přepínání plánu %s", entry_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail=f"Plán '{entry_id}' nenalezen.")


@router.patch("/settings", summary="Aktualizovat nastavení plánovače")
async def patch_schedule_settings(body: dict[str, Any]) -> dict:
    """Přepíše vybraná pole v ``settings`` části schedule.json.

    Podporovaná pole: ``enable_scheduler`` (bool), ``auto_execute`` (bool).
    Ostatní klíče jsou ignorovány.

    Args:
        body: Slovník s novými hodnotami, např. ``{"enable_scheduler": true}``.

    Returns:
        dict: Aktualizovaná ``settings`` sekce.

    Raises:
        HTTPException 500: Chyba zápisu souboru.
    """
    allowed = {"enable_scheduler", "auto_execute"}
    update = {k: bool(v) for k, v in body.items() if k in allowed}
    try:
        async with _write_lock:
            data = _read_schedule()
            data.setdefault("settings", {}).update(update)
            _write_schedule(data)
            return data["settings"]
    except Exception as exc:
        logger.exception("Chyba při aktualizaci nastavení plánovače")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
