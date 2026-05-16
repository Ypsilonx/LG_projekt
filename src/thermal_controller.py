# -*- coding: utf-8 -*-
"""Thermal automation controller with PID-like staged behavior.

The controller combines corrected indoor temperature, online outdoor estimate,
and simple hysteresis/watchdog rules to reduce frequent mode switching.
It is intentionally deterministic and lightweight so it can run in the GUI loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class ThermalControlPolicy:
    """Configuration for thermal control behavior.

    Args:
        target_temperature_c: Desired indoor comfort temperature.
        cooling_start_above_c: Cooling starts when indoor exceeds this value.
        heating_start_below_c: Heating starts when indoor goes below this value.
        outdoor_delta_trigger_c: Strong indoor/outdoor delta trigger.
        cooling_watchdog_threshold_c: Watchdog threshold for insufficient cooling.
        cooling_watchdog_minutes: Duration before watchdog can power off cooling.
        command_cooldown_minutes: Minimal delay between repeated equal actions.
        cooling_high_error_c: Error above target for high cooling fan.
        cooling_mid_error_c: Error above target for medium cooling fan.
        heating_high_error_c: Error below target for high heating fan.
        heating_mid_error_c: Error below target for medium heating fan.
    """

    target_temperature_c: float = 22.0
    cooling_start_above_c: float = 23.0
    heating_start_below_c: float = 20.0
    outdoor_delta_trigger_c: float = 10.0
    cooling_watchdog_threshold_c: float = 23.0
    cooling_watchdog_minutes: int = 30
    command_cooldown_minutes: int = 5
    cooling_high_error_c: float = 2.0
    cooling_mid_error_c: float = 1.0
    heating_high_error_c: float = 2.0
    heating_mid_error_c: float = 1.0


@dataclass(frozen=True)
class ThermalControlState:
    """Runtime state required for thermal watchdog logic.

    Args:
        cooling_watch_started_at: Start time of cooling watchdog window.
        cooling_watch_min_temp_c: Lowest indoor temperature seen in watchdog window.
    """

    cooling_watch_started_at: datetime | None = None
    cooling_watch_min_temp_c: float | None = None


@dataclass(frozen=True)
class ThermalControlDecision:
    """Controller decision to be executed by GUI command layer.

    Args:
        action: Decision action, one of keep, run, power_off.
        mode: Mode to run when action is run.
        target_temperature_c: Target temperature for action run.
        wind_strength: Fan strength for action run.
        reason: Human-readable reason for diagnostics.
    """

    action: str
    mode: str | None
    target_temperature_c: float | None
    wind_strength: str | None
    reason: str


def _wind_by_error(error_c: float, high_error_c: float, mid_error_c: float) -> str:
    """Map absolute temperature error to fan strength.

    Args:
        error_c: Absolute control error in Celsius.
        high_error_c: Threshold for high fan.
        mid_error_c: Threshold for medium fan.

    Returns:
        str: One of HIGH, MID, LOW.
    """

    if error_c >= high_error_c:
        return "HIGH"
    if error_c >= mid_error_c:
        return "MID"
    return "LOW"


def derive_policy_for_target(
    policy: ThermalControlPolicy,
    target_temperature_c: float,
) -> ThermalControlPolicy:
    """Return thermal policy with thresholds shifted to a new target temperature.

    The original policy values are treated as baseline deltas around the baseline
    target. When target is changed (for example user sets 20C), cooling/heating
    start thresholds and watchdog threshold are shifted by the same delta.

    Args:
        policy: Baseline thermal policy.
        target_temperature_c: New target temperature in Celsius.

    Returns:
        ThermalControlPolicy: Policy adapted to the new target value.
    """

    target_c = float(target_temperature_c)
    base_target_c = float(policy.target_temperature_c)

    cooling_start_delta_c = float(policy.cooling_start_above_c) - base_target_c
    heating_start_delta_c = float(policy.heating_start_below_c) - base_target_c
    cooling_watchdog_delta_c = float(policy.cooling_watchdog_threshold_c) - base_target_c

    return ThermalControlPolicy(
        target_temperature_c=target_c,
        cooling_start_above_c=target_c + cooling_start_delta_c,
        heating_start_below_c=target_c + heating_start_delta_c,
        outdoor_delta_trigger_c=float(policy.outdoor_delta_trigger_c),
        cooling_watchdog_threshold_c=target_c + cooling_watchdog_delta_c,
        cooling_watchdog_minutes=int(policy.cooling_watchdog_minutes),
        command_cooldown_minutes=int(policy.command_cooldown_minutes),
        cooling_high_error_c=float(policy.cooling_high_error_c),
        cooling_mid_error_c=float(policy.cooling_mid_error_c),
        heating_high_error_c=float(policy.heating_high_error_c),
        heating_mid_error_c=float(policy.heating_mid_error_c),
    )


def decide_thermal_control(
    indoor_corrected_c: float | None,
    outdoor_online_c: float | None,
    current_mode: str | None,
    power_on: bool,
    now_local: datetime,
    state: ThermalControlState,
    policy: ThermalControlPolicy,
) -> tuple[ThermalControlDecision, ThermalControlState]:
    """Return staged thermal control decision and updated watchdog state.

    Args:
        indoor_corrected_c: Corrected indoor temperature from AC sensor.
        outdoor_online_c: Online outdoor temperature estimate.
        current_mode: Current AC mode.
        power_on: Current AC power status.
        now_local: Current local time.
        state: Current thermal controller state.
        policy: Thermal controller thresholds and timings.

    Returns:
        tuple[ThermalControlDecision, ThermalControlState]: Decision and new state.
    """

    if indoor_corrected_c is None:
        return (
            ThermalControlDecision(
                action="keep",
                mode=None,
                target_temperature_c=None,
                wind_strength=None,
                reason="PID: chybi indoor teplota, regulace beze zmeny.",
            ),
            ThermalControlState(),
        )

    normalized_mode = str(current_mode or "").upper().strip()
    is_cooling_active = power_on and normalized_mode == "COOL"

    next_state = state
    if is_cooling_active and indoor_corrected_c > policy.cooling_watchdog_threshold_c:
        if state.cooling_watch_started_at is None:
            next_state = ThermalControlState(
                cooling_watch_started_at=now_local,
                cooling_watch_min_temp_c=indoor_corrected_c,
            )
        else:
            previous_min = state.cooling_watch_min_temp_c
            observed_min = indoor_corrected_c if previous_min is None else min(previous_min, indoor_corrected_c)
            next_state = ThermalControlState(
                cooling_watch_started_at=state.cooling_watch_started_at,
                cooling_watch_min_temp_c=observed_min,
            )

            elapsed = now_local - state.cooling_watch_started_at
            watchdog_delta = timedelta(minutes=max(1, policy.cooling_watchdog_minutes))
            if elapsed >= watchdog_delta and observed_min > policy.cooling_watchdog_threshold_c:
                return (
                    ThermalControlDecision(
                        action="power_off",
                        mode=None,
                        target_temperature_c=None,
                        wind_strength=None,
                        reason=(
                            "PID: watchdog - po 30 min indoor nekleslo pod "
                            f"{policy.cooling_watchdog_threshold_c:.1f}C, vypinam klimatizaci."
                        ),
                    ),
                    ThermalControlState(),
                )
    else:
        next_state = ThermalControlState()

    target_c = float(policy.target_temperature_c)
    delta_to_target = indoor_corrected_c - target_c

    outdoor_delta_c = None
    if outdoor_online_c is not None:
        outdoor_delta_c = abs(indoor_corrected_c - outdoor_online_c)

    strong_outdoor_delta = (
        outdoor_delta_c is not None
        and outdoor_delta_c >= float(policy.outdoor_delta_trigger_c)
    )

    need_heating = indoor_corrected_c < float(policy.heating_start_below_c)
    if not need_heating and strong_outdoor_delta and outdoor_online_c is not None:
        need_heating = outdoor_online_c <= (target_c - 5.0) and indoor_corrected_c < (target_c + 0.6)

    need_cooling = indoor_corrected_c > float(policy.cooling_start_above_c)
    if not need_cooling and strong_outdoor_delta and outdoor_online_c is not None:
        need_cooling = outdoor_online_c >= (target_c + 5.0) and indoor_corrected_c > (target_c - 0.6)

    if need_heating:
        error_c = max(target_c - indoor_corrected_c, 0.0)
        wind = _wind_by_error(error_c, policy.heating_high_error_c, policy.heating_mid_error_c)
        return (
            ThermalControlDecision(
                action="run",
                mode="HEAT",
                target_temperature_c=target_c,
                wind_strength=wind,
                reason=(
                    f"PID: indoor {indoor_corrected_c:.1f}C pod prahem {policy.heating_start_below_c:.1f}C, "
                    f"zapinam HEAT ({wind})."
                ),
            ),
            next_state,
        )

    if need_cooling:
        error_c = max(indoor_corrected_c - target_c, 0.0)
        wind = _wind_by_error(error_c, policy.cooling_high_error_c, policy.cooling_mid_error_c)
        reason = (
            f"PID: indoor {indoor_corrected_c:.1f}C nad prahem {policy.cooling_start_above_c:.1f}C, "
            f"zapinam COOL ({wind})."
        )
        if strong_outdoor_delta and outdoor_online_c is not None:
            reason += (
                f" Rozdil indoor/outdoor {outdoor_delta_c:.1f}C je >= "
                f"{policy.outdoor_delta_trigger_c:.1f}C."
            )
        return (
            ThermalControlDecision(
                action="run",
                mode="COOL",
                target_temperature_c=target_c,
                wind_strength=wind,
                reason=reason,
            ),
            next_state,
        )

    if abs(delta_to_target) <= 0.6:
        if power_on and normalized_mode in {"COOL", "HEAT"}:
            return (
                ThermalControlDecision(
                    action="run",
                    mode="FAN",
                    target_temperature_c=None,
                    wind_strength="LOW",
                    reason=(
                        f"PID: indoor {indoor_corrected_c:.1f}C je blizko cile {target_c:.1f}C, "
                        "prepinam na FAN LOW."
                    ),
                ),
                next_state,
            )
        return (
            ThermalControlDecision(
                action="keep",
                mode=None,
                target_temperature_c=None,
                wind_strength=None,
                reason=f"PID: indoor {indoor_corrected_c:.1f}C je v pasmu komfortu.",
            ),
            next_state,
        )

    if delta_to_target > 0.0:
        error_c = abs(delta_to_target)
        wind = _wind_by_error(error_c, policy.cooling_high_error_c, policy.cooling_mid_error_c)
        return (
            ThermalControlDecision(
                action="run",
                mode="COOL",
                target_temperature_c=target_c,
                wind_strength=wind,
                reason=(
                    f"PID: indoor {indoor_corrected_c:.1f}C je nad cilem {target_c:.1f}C, "
                    f"udrzuji COOL ({wind})."
                ),
            ),
            next_state,
        )

    error_c = abs(delta_to_target)
    wind = _wind_by_error(error_c, policy.heating_high_error_c, policy.heating_mid_error_c)
    return (
        ThermalControlDecision(
            action="run",
            mode="HEAT",
            target_temperature_c=target_c,
            wind_strength=wind,
            reason=(
                f"PID: indoor {indoor_corrected_c:.1f}C je pod cilem {target_c:.1f}C, "
                f"udrzuji HEAT ({wind})."
            ),
        ),
        next_state,
    )
