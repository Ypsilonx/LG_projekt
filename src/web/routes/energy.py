# -*- coding: utf-8 -*-
"""
Router: Energie – GET /api/energy/{device_id}?view=daily|weekly|monthly|yearly

Vrátí normalizovaná data spotřeby energie pro zvolený pohled.
Využívá energy_analytics.py pro výpočet časového rozsahu a formátování.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from energy_analytics import (
    format_used_date,
    normalize_energy_records,
    resolve_energy_query,
    total_energy_kwh,
)
from server_api import ThinQAPI

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/energy", tags=["Energie"])


def _get_api(request: Request) -> ThinQAPI:
    """
    Vrátí sdílenou instanci ThinQAPI z app.state.

    Args:
        request: FastAPI HTTP požadavek.

    Returns:
        ThinQAPI: Inicializovaná instance.

    Raises:
        HTTPException 503: Pokud API nebylo inicializováno.
    """
    api: ThinQAPI | None = request.app.state.api
    if api is None:
        detail = getattr(request.app.state, "api_error", "ThinQ API není k dispozici.")
        raise HTTPException(status_code=503, detail=detail)
    return api


@router.get(
    "/{device_id}",
    summary="Spotřeba energie zařízení",
    description=(
        "Vrátí normalizovaná data spotřeby energie pro zvolený pohled. "
        "Hodnoty energyUsage jsou v jednotkách Wh."
    ),
)
async def get_energy_usage(
    device_id: str,
    request: Request,
    view: str = Query("weekly", description="Pohled: daily | weekly | monthly | yearly"),
) -> dict:
    """
    Načte a normalizuje data spotřeby energie ze zařízení.

    Args:
        device_id: ThinQ ID zařízení.
        view:      Pohled – daily (dnes), weekly (7 dní), monthly (měsíc), yearly (12 měsíců).

    Returns:
        dict s klíči:
            view_key  – zvolený pohled
            period    – API perioda (DAILY / MONTHLY)
            total_kwh – celková spotřeba v kWh
            records   – seznam záznamů [usedDate, label, energyUsage (Wh)]

    Raises:
        HTTPException 503: API není k dispozici.
        HTTPException 502: Chyba komunikace s ThinQ.
    """
    api = _get_api(request)
    query = resolve_energy_query(view)

    try:
        raw = await api.get_energy_usage(
            device_id,
            query.period,
            query.start_date,
            query.end_date,
        )
    except Exception as exc:
        logger.error("Chyba načítání energy usage (%s): %s", device_id[:8], exc)
        raise HTTPException(
            status_code=502,
            detail=f"Chyba komunikace s ThinQ API: {exc}",
        ) from exc

    records = normalize_energy_records(raw or [])
    for rec in records:
        rec["label"] = format_used_date(rec["usedDate"], query.period)

    return {
        "view_key":  query.view_key,
        "period":    query.period,
        "total_kwh": round(total_energy_kwh(records), 3),
        "records":   records,
    }
