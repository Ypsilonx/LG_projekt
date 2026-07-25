# -*- coding: utf-8 -*-
"""
Pravidla pro bezpečné pořadí příkazů klimatizace.

Modul převádí požadovaný příkaz na plán kroků, který respektuje
základní preconditions zařízení (zejména napájení) a minimalizuje
kolize při rychlém sekvenčním ovládání.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from profile_limits import get_temp_limits


@dataclass(frozen=True)
class CommandStep:
    """
    Jeden krok plánovaného ovládání zařízení.

    Args:
        command: Název interního příkazu (např. "power_on", "change_mode")
        args: Argumenty příkazu
        delay_after_seconds: Pauza po dokončení kroku (kvůli konzistenci zařízení)
        reason: Textový důvod, proč je krok vložen
    """

    command: str
    args: tuple[Any, ...] = ()
    delay_after_seconds: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class CommandPlan:
    """
    Kompletní plán příkazů pro bezpečné provedení požadavku.

    Args:
        steps: Kroky, které se mají postupně provést
        skip_reason: Důvod přeskočení, pokud není vhodné příkaz odeslat
    """

    steps: list[CommandStep]
    skip_reason: str | None = None

    @property
    def should_skip(self) -> bool:
        """
        Indikuje, zda se příkaz nemá provést.

        Returns:
            bool: True pokud má být požadavek přeskočen
        """

        return self.skip_reason is not None or not self.steps


REQUIRES_POWER_ON = {
    "change_mode",
    "set_temperature",
    "set_wind_strength",
    "set_wind_direction",
    "set_power_save",
    "set_sleep_timer",
}

_AUTOMATION_RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "automation_rules.json"


def _load_setpoint_correction_c() -> float:
    """Load room-to-AC setpoint correction from automation rules.

    The correction is derived from existing AC indoor proxy offset:
    room = ac + proxy_offset  =>  ac_target = room_target - proxy_offset.

    Returns:
        float: Correction added to user room target before sending to AC.
    """

    try:
        payload = json.loads(_AUTOMATION_RULES_PATH.read_text(encoding="utf-8"))
        weather = payload.get("weather", {}) if isinstance(payload, dict) else {}
        proxy_offset = weather.get(
            "ac_indoor_temperature_proxy_offset_c",
            weather.get("sensor_offset_c", 0.0),
        )
        return -float(proxy_offset)
    except Exception:
        return 0.0


def _apply_setpoint_correction(temp_c: float) -> float:
    """Convert room target temperature to AC target temperature.

    Args:
        temp_c: Requested room target in Celsius.

    Returns:
        float: Corrected AC target in Celsius.
    """

    correction_c = _load_setpoint_correction_c()
    return round(float(temp_c) + correction_c, 1)


def _get_power_mode(device_status: dict[str, Any]) -> str:
    """
    Načte aktuální napájecí režim zařízení.

    Args:
        device_status: Status zařízení

    Returns:
        str: Hodnota POWER_ON/POWER_OFF nebo výchozí POWER_OFF
    """

    return (
        device_status.get("operation", {})
        .get("airConOperationMode", "POWER_OFF")
    )


def _get_job_mode(device_status: dict[str, Any]) -> str:
    """
    Načte aktuální pracovní režim klimatizace.

    Args:
        device_status: Status zařízení

    Returns:
        str: Hodnota režimu (např. COOL/FAN/HEAT)
    """

    return (
        device_status.get("airConJobMode", {})
        .get("currentJobMode", "UNKNOWN")
    )


def _append_power_precondition(
    steps: list[CommandStep],
    command: str,
    device_status: dict[str, Any],
) -> None:
    """
    Doplní precondition krok pro zapnutí zařízení, pokud je potřeba.

    Args:
        steps: Sestavovaný seznam kroků
        command: Cílový příkaz
        device_status: Status zařízení
    """

    if command not in REQUIRES_POWER_ON:
        return

    if _get_power_mode(device_status) != "POWER_ON":
        steps.append(
            CommandStep(
                command="power_on",
                delay_after_seconds=2.5,
                reason="Precondition: zařízení musí být zapnuté",
            )
        )


def build_command_plan(
    command: str,
    args: tuple[Any, ...],
    device_status: dict[str, Any],
) -> CommandPlan:
    """
    Sestaví bezpečný plán kroků pro požadovaný příkaz.

    Args:
        command: Interní název příkazu
        args: Argumenty příkazu
        device_status: Poslední známý stav zařízení

    Returns:
        CommandPlan: Plán kroků nebo důvod přeskočení
    """

    command = command.strip()
    steps: list[CommandStep] = []
    power_mode = _get_power_mode(device_status)
    job_mode = _get_job_mode(device_status)

    if command == "power_on":
        if power_mode == "POWER_ON":
            return CommandPlan(steps=[], skip_reason="Zařízení je již zapnuté.")
        return CommandPlan(steps=[CommandStep("power_on")])

    if command == "power_off":
        if power_mode == "POWER_OFF":
            return CommandPlan(steps=[], skip_reason="Zařízení je již vypnuté.")
        return CommandPlan(steps=[CommandStep("power_off")])

    if command == "toggle_power":
        return CommandPlan(steps=[CommandStep("toggle_power")])

    _append_power_precondition(steps, command, device_status)

    if command == "change_mode":
        target_mode = str(args[0]).upper() if args else ""
        if target_mode and target_mode == str(job_mode).upper():
            return CommandPlan(steps=[], skip_reason=f"Režim {target_mode} je již nastaven.")
        steps.append(CommandStep("change_mode", args, delay_after_seconds=2.0))
        return CommandPlan(steps=steps)

    if command == "set_temperature":
        if str(job_mode).upper() == "FAN":
            return CommandPlan(
                steps=[],
                skip_reason="Teplotu nelze měnit v režimu FAN. Nejprve změňte režim.",
            )
        effective_args = args
        if args:
            try:
                requested_temp_val = float(args[0])
                temp_val = _apply_setpoint_correction(requested_temp_val)
                limits = get_temp_limits(job_mode)
                if limits and not (limits["min"] <= temp_val <= limits["max"]):
                    return CommandPlan(
                        steps=[],
                        skip_reason=(
                            f"Po korekci cíle ({requested_temp_val}°C -> {temp_val}°C) je "
                            "výsledek mimo povolený rozsah "
                            f"{limits['min']}–{limits['max']}°C pro režim {job_mode or 'neznámý'}."
                        ),
                    )
                effective_args = (temp_val, *args[1:])
            except (TypeError, ValueError):
                pass
        steps.append(CommandStep("set_temperature", effective_args, delay_after_seconds=1.5))
        return CommandPlan(steps=steps)

    if command == "set_wind_strength":
        target_strength = args[0] if args else None
        air = device_status.get("airFlow", {})
        if target_strength == "NATURE":
            # NATURE mód se ukládá do windStrengthDetail, ne windStrength
            if air.get("windStrengthDetail") == "NATURE":
                return CommandPlan(steps=[], skip_reason="Ventilátor je již v režimu Přírodní.")
        else:
            if target_strength and target_strength == air.get("windStrength"):
                return CommandPlan(steps=[], skip_reason="Síla větru je již nastavena.")
        steps.append(CommandStep("set_wind_strength", args, delay_after_seconds=0.8))
        return CommandPlan(steps=steps)

    if command == "set_wind_direction":
        target_updown = bool(args[0]) if len(args) > 0 else False
        target_leftright = bool(args[1]) if len(args) > 1 else False
        current_dir = device_status.get("windDirection", {})
        current_updown = bool(current_dir.get("rotateUpDown", False))
        current_leftright = bool(current_dir.get("rotateLeftRight", False))
        if (target_updown, target_leftright) == (current_updown, current_leftright):
            return CommandPlan(steps=[], skip_reason="Směr větru je již nastaven.")
        steps.append(CommandStep("set_wind_direction", args, delay_after_seconds=0.8))
        return CommandPlan(steps=steps)

    if command == "set_rotate_updown":
        target = bool(args[0]) if args else False
        current = bool(device_status.get("windDirection", {}).get("rotateUpDown", False))
        if target == current:
            return CommandPlan(steps=[], skip_reason="Vertikální kývání je již v tomto stavu.")
        steps.append(CommandStep("set_rotate_updown", args, delay_after_seconds=0.8))
        return CommandPlan(steps=steps)

    if command == "set_rotate_leftright":
        target = bool(args[0]) if args else False
        current = bool(device_status.get("windDirection", {}).get("rotateLeftRight", False))
        if target == current:
            return CommandPlan(steps=[], skip_reason="Horizontální kývání je již v tomto stavu.")
        steps.append(CommandStep("set_rotate_leftright", args, delay_after_seconds=0.8))
        return CommandPlan(steps=steps)

    if command == "set_power_save":
        target_enabled = bool(args[0]) if args else False
        current_enabled = bool(device_status.get("powerSave", {}).get("powerSaveEnabled", False))
        if target_enabled == current_enabled:
            return CommandPlan(steps=[], skip_reason="Power Save je již ve stejném stavu.")
        steps.append(CommandStep("set_power_save", args, delay_after_seconds=0.8))
        return CommandPlan(steps=steps)

    if command == "set_sleep_timer":
        steps.append(CommandStep("set_sleep_timer", args, delay_after_seconds=0.8))
        return CommandPlan(steps=steps)

    if command == "cancel_all_timers":
        steps.append(CommandStep("cancel_all_timers", args, delay_after_seconds=0.8))
        return CommandPlan(steps=steps)

    return CommandPlan(steps=[], skip_reason=f"Neznámý příkaz: {command}")
