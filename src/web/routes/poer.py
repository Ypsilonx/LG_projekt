# -*- coding: utf-8 -*-
"""Router: POER termostat (stav + základní ovládání).

Endpointy jsou oddělené od LG command pipeline, protože POER používá
vlastní cloud API a vlastní sadu příkazů.
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from poer_api import fetch_poer_status_cached, send_poer_command
from web.routes.weather import _load_weather_config

router = APIRouter(prefix="/api/poer", tags=["POER"])


class PoerModeRequest(BaseModel):
    """Tělo požadavku pro nastavení režimu POER.

    Args:
        mode: HVAC režim (`auto`, `heat`, `off`).
        preset: Předvolba (`home`, `away`).
    """

    mode: Literal["auto", "heat", "off"]
    preset: Literal["home", "away"] = "home"


class PoerTemperatureRequest(BaseModel):
    """Tělo požadavku pro nastavení cílové teploty POER.

    Args:
        temperature: Cílová teplota ve °C.
    """

    temperature: float = Field(..., ge=5.0, le=35.0)


def _resolve_preferred_device_id() -> str | None:
    """Vrátí preferované POER device ID z konfigurace weather."""

    weather_cfg = _load_weather_config()
    raw_device_id = weather_cfg.get("poer_device_id") if isinstance(weather_cfg, dict) else None
    if raw_device_id in (None, ""):
        return None
    return str(raw_device_id)


def _require_poer_api_key() -> str:
    """Načte POER API key z prostředí nebo vyhodí HTTP 400."""

    api_key = os.getenv("LG_POER_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="Chybí LG_POER_API_KEY v prostředí.")
    return api_key


@router.get("/status", summary="Aktuální stav POER termostatu")
async def get_poer_status() -> dict:
    """Vrátí aktuální stav POER termostatu z cloud API (krátce cachováno)."""

    api_key = _require_poer_api_key()
    status = await fetch_poer_status_cached(
        api_key=api_key,
        preferred_device_id=_resolve_preferred_device_id(),
    )
    return status


@router.post("/command/set-temperature", summary="Nastaví cílovou teplotu POER")
async def set_poer_temperature(body: PoerTemperatureRequest) -> dict:
    """Nastaví cílovou teplotu POER termostatu."""

    api_key = _require_poer_api_key()
    result = await send_poer_command(
        api_key=api_key,
        endpoint="set_temp",
        data={"temperature": body.temperature},
        preferred_device_id=_resolve_preferred_device_id(),
    )
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("error_text") or "POER command selhal")
    return result


@router.post("/command/set-mode", summary="Nastaví režim a předvolbu POER")
async def set_poer_mode(body: PoerModeRequest) -> dict:
    """Nastaví režim a předvolbu POER termostatu."""

    api_key = _require_poer_api_key()
    result = await send_poer_command(
        api_key=api_key,
        endpoint="set_mode",
        data={"mode": body.mode, "preset": body.preset},
        preferred_device_id=_resolve_preferred_device_id(),
    )
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("error_text") or "POER command selhal")
    return result
