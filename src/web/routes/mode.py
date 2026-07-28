# -*- coding: utf-8 -*-
"""
Router: Režim řízení – GET /api/mode/ + POST /api/mode/.

Spravuje přepínač HAND/AUTO uložený v ``app.state.control_mode``.
Přepnutí je okamžitě broadcastováno všem WebSocket klientům.

Stav je in-memory – při restartu serveru se resetuje na výchozí ``"AUTO"``.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from web.routes.ws import manager as ws_manager

logger = logging.getLogger(__name__)

# Soubor pro perzistenci control_mode mezi restarty serveru
_STATE_FILE = Path(__file__).resolve().parents[3] / "data" / "state.json"


def _save_control_mode(mode: str) -> None:
    """
    Uloží control_mode do data/state.json (atomicky přes tmp soubor + replace).

    Args:
        mode: "AUTO" nebo "HAND" – hodnota k uložení.
    """
    try:
        tmp = _STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"control_mode": mode}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(_STATE_FILE)
    except Exception as exc:
        logger.warning("Nelze uložit control_mode do state.json: %s", exc)

router = APIRouter(prefix="/api/mode", tags=["Režim řízení"])

_VALID_MODES = frozenset({"HAND", "AUTO"})


class ModeRequest(BaseModel):
    """Tělo požadavku pro nastavení režimu."""

    mode: str


@router.get("/", summary="Aktuální režim")
async def get_mode(request: Request) -> dict:
    """
    Vrátí aktuální režim řízení.

    Args:
        request: HTTP požadavek – přístup k ``app.state``.

    Returns:
        dict: ``{"mode": "AUTO" | "HAND"}``.
    """
    mode: str = getattr(request.app.state, "control_mode", "AUTO")
    return {"mode": mode}


@router.post("/", summary="Nastavit režim")
async def set_mode(body: ModeRequest, request: Request) -> dict:
    """
    Nastaví nový režim řízení a broadcastuje změnu přes WebSocket.

    Args:
        body: ``{"mode": "AUTO"}`` nebo ``{"mode": "HAND"}``.
        request: HTTP požadavek – přístup k ``app.state``.

    Returns:
        dict: ``{"mode": "HAND", "changed": True}``.

    Raises:
        HTTPException 422: Neplatná hodnota mode.
    """
    mode = body.mode.strip().upper()
    if mode not in _VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Neplatný režim '{mode}'. "
                f"Povolené hodnoty: {', '.join(sorted(_VALID_MODES))}"
            ),
        )

    old_mode: str = getattr(request.app.state, "control_mode", "AUTO")
    request.app.state.control_mode = mode
    _save_control_mode(mode)

    if mode != old_mode:
        await ws_manager.broadcast(
            {
                "type": "mode_change",
                "data": {"mode": mode, "previous": old_mode},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        logger.info("Režim přepnut: %s → %s", old_mode, mode)

    return {"mode": mode, "changed": mode != old_mode}
