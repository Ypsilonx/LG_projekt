# -*- coding: utf-8 -*-
"""
Router: Ovládání zařízení (POST /api/devices/{device_id}/command).

Přijme příkaz s volitelnými argumenty, sestaví bezpečný CommandPlan
přes command_policy a provede ho přes command_executor.

Endpoint záměrně nepřijímá surový ThinQ payload – veškerá validace
a sestavení probíhá na serveru přes command_policy.build_command_plan.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from command_executor import execute_plan
from command_policy import build_command_plan
from server_api import ThinQAPI
from web.routes.devices import _get_api

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/devices", tags=["Ovládání"])

# Povolené interní příkazy (whitelist – brání injekci libovolného příkazu)
ALLOWED_COMMANDS = {
    "power_on",
    "power_off",
    "toggle_power",
    "change_mode",
    "set_temperature",
    "set_wind_strength",
    "set_wind_direction",
    "set_power_save",
    "cancel_all_timers",
}


class CommandRequest(BaseModel):
    """
    Tělo POST požadavku pro odeslání příkazu klimatizaci.

    Args:
        command: Interní název příkazu (musí být v ALLOWED_COMMANDS)
        args:    Volitelné argumenty příkazu
                 - ``change_mode``     → ``["HEAT"]``
                 - ``set_temperature`` → ``[22.0]``
                 - ``set_wind_strength`` → ``["AUTO"]``
                 - ``set_wind_direction`` → ``[true, false]``
    """

    command: str
    args: list[Any] = []

    @field_validator("command")
    @classmethod
    def command_must_be_allowed(cls, v: str) -> str:
        """Zamítne příkazy mimo whitelist – chrání před nevalidovaným vstupem."""
        if v not in ALLOWED_COMMANDS:
            raise ValueError(
                f"Nepovolený příkaz '{v}'. "
                f"Povolené příkazy: {sorted(ALLOWED_COMMANDS)}"
            )
        return v


class CommandResponse(BaseModel):
    """
    Odpověď po provedení příkazu.

    Args:
        skipped:     True pokud byl příkaz přeskočen (precondition již splněna)
        skip_reason: Důvod přeskočení, jinak None
        steps:       Výsledky provedených kroků
    """

    skipped: bool
    skip_reason: str | None
    steps: list[dict]


@router.post(
    "/{device_id}/command",
    response_model=CommandResponse,
    summary="Odeslat příkaz zařízení",
    description=(
        "Sestaví bezpečný plán příkazů přes `command_policy` a provede ho. "
        "Automaticky přidá precondition kroky (např. power_on před change_mode). "
        "Pokud je požadovaný stav již aktivní, příkaz se přeskočí."
    ),
)
async def send_command(device_id: str, body: CommandRequest, request: Request):
    """
    Odešle příkaz klimatizaci.

    Postup:
        1. Načte aktuální stav zařízení.
        2. Sestaví CommandPlan přes build_command_plan.
        3. Pokud plan.should_skip, vrátí ``skipped=True`` bez volání API.
        4. Jinak provede všechny kroky přes execute_plan.

    Args:
        device_id: ThinQ Device ID
        body:      Příkaz a argumenty
        request:   FastAPI request (přístup k app.state.api)

    Returns:
        CommandResponse: Výsledek provedení příkazu

    Raises:
        HTTPException 422: Nepovolený příkaz (Pydantic validace)
        HTTPException 503: ThinQ API nedostupné
        HTTPException 400: Chyba při sestavení nebo provedení plánu
    """
    api = _get_api(request)

    try:
        status = await api.get_device_status(device_id)
    except Exception as exc:
        logger.warning(f"Nelze načíst stav pro command: {exc}")
        raise HTTPException(status_code=503, detail=f"Nelze načíst stav zařízení: {exc}")

    args = tuple(body.args)
    plan = build_command_plan(body.command, args, status)

    if plan.should_skip:
        logger.info(f"Příkaz '{body.command}' přeskočen: {plan.skip_reason}")
        return CommandResponse(skipped=True, skip_reason=plan.skip_reason, steps=[])

    try:
        results = await execute_plan(api, device_id, plan, status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Chyba při provádění příkazu '{body.command}': {exc}")
        raise HTTPException(status_code=503, detail=f"Chyba při odesílání příkazu: {exc}")

    return CommandResponse(skipped=False, skip_reason=None, steps=results)
