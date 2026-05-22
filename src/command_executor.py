# -*- coding: utf-8 -*-
"""
Sdílená logika pro sestavení a provedení příkazů klimatizace.

Tento modul byl extrahován z main.py, aby mohl být sdílen
mezi CLI (main.py) a webovým rozhraním (web/routes/control.py).

Odpovídá za:
- Překlad interního názvu příkazu na payload (create_payload_for_step)
- Optimistický lokální update stavového snapshotu (apply_status_hint)
- Vykonání celého CommandPlan na zařízení (execute_plan)
"""

import asyncio
import logging
from typing import Any

from klima_logic import create_control_payload
from command_policy import CommandPlan, build_command_plan
from server_api import ThinQAPI

logger = logging.getLogger(__name__)


def create_payload_for_step(command: str, args: tuple[Any, ...], status: dict) -> dict | None:
    """
    Přeloží interní název příkazu a jeho argumenty na payload pro ThinQ API.

    Args:
        command: Interní název příkazu (např. ``"change_mode"``, ``"power_on"``)
        args:    Argumenty příkazu (např. ``("COOL",)`` pro change_mode)
        status:  Aktuální snapshot stavu zařízení (potřebný pro toggle_power)

    Returns:
        dict | None: Payload připravený pro ``ThinQAPI.send_device_command``,
                     nebo ``None`` pokud příkaz není znám.
    """
    if command == "power_on":
        return create_control_payload("power", "POWER_ON")
    if command == "power_off":
        return create_control_payload("power", "POWER_OFF")
    if command == "toggle_power":
        current = status.get("operation", {}).get("airConOperationMode", "POWER_OFF")
        target = "POWER_ON" if current == "POWER_OFF" else "POWER_OFF"
        return create_control_payload("power", target)
    if command == "change_mode":
        return create_control_payload("mode", args[0])
    if command == "set_temperature":
        return create_control_payload("temperature", args[0])
    if command == "set_wind_strength":
        return create_control_payload("wind_strength", args[0])
    if command == "set_wind_direction":
        return create_control_payload("wind_direction", args[0], args[1])
    if command == "set_power_save":
        return create_control_payload("power_save", args[0])
    if command == "set_sleep_timer":
        return create_control_payload("sleep_timer", args[0], args[1])
    if command == "cancel_all_timers":
        return create_control_payload("cancel_timers")
    return None


def apply_status_hint(status: dict, command: str, args: tuple[Any, ...]) -> dict:
    """
    Aplikuje optimistický odhad lokální změny stavu po úspěšném příkazu.

    Nenahrazuje čtení ze zařízení – slouží jako dočasný mezistav
    pro CLI výpis a mezistavové výpočty v rámci vícekrokového plánu.

    Args:
        status:  Aktuální snapshot stavu (bude mutován in-place a vrácen)
        command: Provedený interní příkaz
        args:    Argumenty příkazu

    Returns:
        dict: Aktualizovaný snapshot stavu
    """
    if command == "power_on":
        status.setdefault("operation", {})["airConOperationMode"] = "POWER_ON"
    elif command == "power_off":
        status.setdefault("operation", {})["airConOperationMode"] = "POWER_OFF"
    elif command == "change_mode":
        status.setdefault("airConJobMode", {})["currentJobMode"] = args[0]
    elif command == "set_temperature":
        status.setdefault("temperature", {})["targetTemperature"] = args[0]
    elif command == "set_wind_strength":
        status.setdefault("airFlow", {})["windStrength"] = args[0]
    elif command == "set_wind_direction":
        wind = status.setdefault("windDirection", {})
        wind["rotateUpDown"] = bool(args[0])
        wind["rotateLeftRight"] = bool(args[1])
    elif command == "set_power_save":
        status.setdefault("powerSave", {})["powerSaveEnabled"] = bool(args[0])
    return status


async def execute_plan(
    api: ThinQAPI,
    device_id: str,
    plan: CommandPlan,
    status: dict,
) -> list[dict]:
    """
    Provede všechny kroky ``CommandPlan`` na zařízení.

    Po každém kroku aplikuje ``apply_status_hint`` jako optimistický
    mezistav pro správné vyhodnocení dalších kroků (např. precondition
    power_on před change_mode).

    Args:
        api:       Inicializovaná instance ``ThinQAPI``
        device_id: ThinQ Device ID cílového zařízení
        plan:      Plán kroků sestavený přes ``build_command_plan``
        status:    Aktuální snapshot stavu zařízení

    Returns:
        list[dict]: Výsledky jednotlivých kroků
                    ``[{"step": "power_on", "result": {...}}, ...]``

    Raises:
        ValueError:  Pokud krok obsahuje neznámý příkaz
        Exception:   Chyby z ``ThinQAPI.send_device_command`` (retry je uvnitř API)
    """
    results = []
    for idx, step in enumerate(plan.steps):
        payload = create_payload_for_step(step.command, step.args, status)
        if payload is None:
            raise ValueError(f"Neznámý příkaz v plánu: '{step.command}'")

        result = await api.send_device_command(device_id, payload)
        results.append({"step": step.command, "result": result})
        logger.info(f"✅ Krok {idx + 1}/{len(plan.steps)}: '{step.command}' OK")

        # Optimistický update mezistavového snapshotu
        status = apply_status_hint(status, step.command, step.args)

        # Pauza mezi kroky (ne po posledním)
        is_last = idx == len(plan.steps) - 1
        if not is_last and step.delay_after_seconds > 0:
            await asyncio.sleep(step.delay_after_seconds)

    return results
