# -*- coding: utf-8 -*-
"""Mixiny pro automatizaci, weather orchestrace a energy reporting v GUI."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog

import aiohttp

from automation_rules import build_automation_summary, load_automation_rules, resolve_scheduled_mode
from energy_analytics import export_energy_records_csv, normalize_energy_records, resolve_energy_query
from gui.scheduler import ScheduleEntry
from thermal_controller import decide_thermal_control, derive_policy_for_target
from weather_provider import (
    decide_mode_by_weather,
    estimate_current_outdoor_temperature,
    fetch_chmi_meteogram_forecast,
    fetch_chmi_region_forecast,
)

logger = logging.getLogger(__name__)


class AutomationEnergyMixin:
    """Mnozina metod pro weather automatizaci, termoregulaci a energy data."""

    def _load_automation_rules(self):
        """Nacte a validuje sezonni pravidla automatizace z data souboru."""
        rules_path = Path(__file__).resolve().parents[2] / "data" / "automation_rules.json"
        self.automation_rules, warning = load_automation_rules(rules_path)

        if warning:
            logger.warning(warning)
            self._last_automation_note = warning

    def _refresh_automation_summary(self, current_time=None, note=None, active_schedule=None):
        """Aktualizuje textovy prehled aktivnich automatizacnich pravidel v GUI.

        Args:
            current_time: Referencni cas pro vykresleni summary.
            note: Volitelna textova poznamka do souhrnu.
            active_schedule: Aktivni plan pro spravne zobrazeni banneru.
        """
        if current_time is None:
            current_time = datetime.now()

        if note is not None:
            self._last_automation_note = note

        summary = build_automation_summary(
            rules=self.automation_rules,
            current_time=current_time,
            manual_override_active=self.hand_mode_active,
            last_note=self._last_automation_note,
        )

        self.automation_info_var.set(summary)
        self._update_automation_mode_banner(active_schedule=active_schedule)
        self._refresh_weather_visualization(current_time)

    def _refresh_weather_visualization(self, current_time=None):
        """Aktualizuje weather panel dle posledniho snapshotu a stavu cidla."""
        if current_time is None:
            current_time = datetime.now()

        if not hasattr(self, "weather_panel"):
            return

        weather_cfg = self.automation_rules.weather
        snapshot = self.weather_snapshot
        if not weather_cfg.enabled or not weather_cfg.use_short_term_forecast:
            snapshot = None

        outdoor_now_c = estimate_current_outdoor_temperature(snapshot, current_time)

        self.weather_panel.update_data(
            snapshot=snapshot,
            now_local=current_time,
            horizon_hours=weather_cfg.forecast_horizon_hours,
            outdoor_now_c=outdoor_now_c,
            sensor_raw_c=self._extract_current_temperature(),
            sensor_offset_c=weather_cfg.sensor_offset_c,
            last_refresh_local=self.weather_last_refresh_at,
            last_error=self.weather_last_error,
        )

    def _manual_weather_refresh(self):
        """Spusti rucni obnovu weather dat z panelu pocasi."""
        if self.weather_refresh_in_progress:
            return

        self._start_weather_refresh(force=True)

    def _start_weather_refresh(self, force=False):
        """Spusti asynchronni refresh weather cache podle intervalu nebo na vyzadani.

        Args:
            force: Pokud True, ignoruje interval aktualizace.

        Returns:
            bool: True pokud byl refresh spusten.
        """
        weather_cfg = self.automation_rules.weather
        if not weather_cfg.enabled or not weather_cfg.use_short_term_forecast:
            return False

        if self.weather_refresh_in_progress:
            return False

        if not force:
            refresh_delta = timedelta(hours=max(1, weather_cfg.refresh_interval_hours))
            last_reference = self.weather_last_refresh_at or self.weather_last_attempt_at
            if last_reference is not None and (datetime.now() - last_reference) < refresh_delta:
                return False

        if hasattr(self, "weather_panel"):
            self.weather_panel.show_loading()

        # Omezime frekvenci pokusu i pri opakovanych chybach, aby nedochazelo
        # k nechtenemu zatizeni CHMI endpointu.
        self.weather_last_attempt_at = datetime.now()
        self.weather_refresh_in_progress = True
        future = asyncio.run_coroutine_threadsafe(self._refresh_weather_snapshot_async(), self.loop)
        future.add_done_callback(self._on_weather_refresh_finished)
        return True

    def _apply_automation_rules_to_schedule(self, schedule_entry, current_time):
        """Vyhodnoti sezonni pravidla nad planem a vrati finalni zaznam ke spusteni."""
        available_modes = None
        if hasattr(self, 'scheduler_widget') and self.scheduler_widget:
            available_modes = {str(mode).upper() for mode in self.scheduler_widget.modes}

        resolution = resolve_scheduled_mode(
            requested_mode=schedule_entry.mode,
            current_time=current_time,
            rules=self.automation_rules,
            available_modes=available_modes,
        )

        if not resolution.allowed:
            self._refresh_automation_summary(current_time=current_time, note=resolution.reason)
            return None, resolution

        combined_reason = resolution.reason
        effective_entry = schedule_entry

        if resolution.adjusted and resolution.effective_mode:
            effective_entry = ScheduleEntry(
                name=schedule_entry.name,
                start_time=schedule_entry.start_time,
                end_time=schedule_entry.end_time,
                mode=resolution.effective_mode,
                temperature=schedule_entry.temperature,
                wind=schedule_entry.wind,
                power_on=schedule_entry.power_on,
                power_off_at_end=getattr(schedule_entry, 'power_off_at_end', True),
            )
            effective_entry.enabled = schedule_entry.enabled

        weather_cfg = self.automation_rules.weather
        if (
            weather_cfg.enabled
            and weather_cfg.use_short_term_forecast
            and weather_cfg.adjust_mode_by_forecast
        ):
            current_temp_c = self._extract_current_temperature()
            weather_adjustment = decide_mode_by_weather(
                requested_mode=effective_entry.mode,
                requested_temperature_c=effective_entry.temperature,
                device_current_temperature_c=current_temp_c,
                sensor_offset_c=weather_cfg.sensor_offset_c,
                snapshot=self.weather_snapshot,
                horizon_hours=weather_cfg.forecast_horizon_hours,
                comfort_margin_c=weather_cfg.comfort_margin_c,
                available_modes=available_modes,
                now_local=current_time,
            )

            combined_reason = f"{combined_reason} | {weather_adjustment.reason}"

            if weather_adjustment.adjusted and weather_adjustment.effective_mode:
                weather_adjusted_entry = ScheduleEntry(
                    name=effective_entry.name,
                    start_time=effective_entry.start_time,
                    end_time=effective_entry.end_time,
                    mode=weather_adjustment.effective_mode,
                    temperature=effective_entry.temperature,
                    wind=effective_entry.wind,
                    power_on=effective_entry.power_on,
                    power_off_at_end=getattr(effective_entry, 'power_off_at_end', True),
                )
                weather_adjusted_entry.enabled = effective_entry.enabled
                effective_entry = weather_adjusted_entry

        self._refresh_automation_summary(current_time=current_time, note=combined_reason)

        if resolution.adjusted and resolution.effective_mode:
            return effective_entry, resolution

        if effective_entry is not schedule_entry:
            return effective_entry, resolution

        return schedule_entry, resolution

    def _extract_current_temperature(self):
        """Vrati aktualni namerenou teplotu ze stavu zarizeni."""
        if not isinstance(self.last_device_status, dict):
            return None

        temp_node = self.last_device_status.get("temperature", {})
        if not isinstance(temp_node, dict):
            return None

        value = temp_node.get("currentTemperature")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _extract_current_target_temperature(self):
        """Vrati aktualne nastavenou cilovou teplotu ze stavu zarizeni.

        Returns:
            float | None: Aktualni target temperature v C nebo None.
        """
        if not isinstance(self.last_device_status, dict):
            return None

        temp_node = self.last_device_status.get("temperature", {})
        if not isinstance(temp_node, dict):
            return None

        value = temp_node.get("targetTemperature")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _extract_current_power_w(self):
        """Vrati aktualni prikon ve wattech, pokud ho API vystavi.

        Returns:
            float | None: Aktualni prikon ve W nebo None, pokud neni dostupny.
        """
        if not isinstance(self.last_device_status, dict):
            return None

        status = self.last_device_status

        energy_data = status.get("energy")
        if isinstance(energy_data, dict):
            for key in ("consumption", "power", "watt", "current"):
                try:
                    value = energy_data.get(key)
                    if value is not None:
                        return float(value)
                except (TypeError, ValueError):
                    continue

        power_data = status.get("power")
        if isinstance(power_data, (int, float)):
            return float(power_data)

        if isinstance(power_data, dict):
            for key in ("consumption", "current", "watt", "power"):
                try:
                    value = power_data.get(key)
                    if value is not None:
                        return float(value)
                except (TypeError, ValueError):
                    continue

        return None

    def _build_thermal_signature(self, action, mode, target_temperature_c, wind_strength):
        """Vytvori podpis rozhodnuti pro potlaceni opakovanych prikazu.

        Args:
            action: Typ akce (run/power_off).
            mode: Rezim akce.
            target_temperature_c: Cilova teplota akce.
            wind_strength: Sila vetraku akce.

        Returns:
            tuple: Normalizovany podpis rozhodnuti.
        """
        target_value = None
        if target_temperature_c is not None:
            target_value = int(round(float(target_temperature_c)))

        return (
            str(action or "").lower().strip(),
            str(mode or "").upper().strip(),
            target_value,
            str(wind_strength or "").upper().strip(),
        )

    def _run_thermal_regulation(self, current_time, active_schedule):
        """Spusti PID-like regulaci mimo aktivni scheduler a HAND rezim.

        Args:
            current_time: Aktualni cas rozhodovani.
            active_schedule: Aktivni schedule, pokud existuje.
        """
        if self.hand_mode_active:
            return

        if active_schedule is not None:
            return

        if not isinstance(self.last_device_status, dict):
            return

        weather_cfg = self.automation_rules.weather
        if not weather_cfg.enabled:
            return

        indoor_raw_c = self._extract_current_temperature()
        if indoor_raw_c is None:
            return

        indoor_corrected_c = indoor_raw_c + float(weather_cfg.sensor_offset_c)
        outdoor_online_c = estimate_current_outdoor_temperature(self.weather_snapshot, current_time)

        power_mode = str(
            self.last_device_status.get("operation", {}).get("airConOperationMode", "POWER_OFF")
        ).upper()
        current_mode = str(
            self.last_device_status.get("airConJobMode", {}).get("currentJobMode", "")
        ).upper()
        power_on = power_mode == "POWER_ON"

        effective_policy = self.thermal_policy
        current_target_c = self._extract_current_target_temperature()
        if current_target_c is not None:
            effective_policy = derive_policy_for_target(
                policy=self.thermal_policy,
                target_temperature_c=current_target_c,
            )

        decision, next_state = decide_thermal_control(
            indoor_corrected_c=indoor_corrected_c,
            outdoor_online_c=outdoor_online_c,
            current_mode=current_mode,
            power_on=power_on,
            now_local=current_time,
            state=self.thermal_state,
            policy=effective_policy,
        )
        self.thermal_state = next_state

        if decision.action == "keep":
            return

        signature = self._build_thermal_signature(
            decision.action,
            decision.mode,
            decision.target_temperature_c,
            decision.wind_strength,
        )
        cooldown_delta = timedelta(minutes=max(1, effective_policy.command_cooldown_minutes))
        if (
            self.last_thermal_decision_signature == signature
            and self.last_thermal_action_at is not None
            and (current_time - self.last_thermal_action_at) < cooldown_delta
        ):
            return

        if decision.action == "power_off":
            self.handle_device_command("power_off")
        elif decision.action == "run" and decision.mode:
            target_temp = decision.target_temperature_c
            if target_temp is None:
                target_temp = effective_policy.target_temperature_c

            auto_entry = ScheduleEntry(
                name="PID auto regulace",
                start_time=current_time.strftime("%H:%M"),
                end_time=current_time.strftime("%H:%M"),
                mode=decision.mode,
                temperature=int(round(float(target_temp))),
                wind=decision.wind_strength or "AUTO",
                power_on=True,
                power_off_at_end=False,
            )
            auto_entry.enabled = True
            self.execute_scheduled_command(auto_entry)
        else:
            return

        self.last_thermal_decision_signature = signature
        self.last_thermal_action_at = current_time
        self.status_var.set(decision.reason)
        self._refresh_automation_summary(current_time=current_time, note=decision.reason)

    async def _refresh_weather_snapshot_async(self):
        """Stahne aktualni weather snapshot podle aktivniho provideru."""
        weather_cfg = self.automation_rules.weather
        timeout = aiohttp.ClientTimeout(total=25)
        session_headers = {
            "Accept": "application/json",
            "User-Agent": "LG-Projekt-WeatherClient/1.0 (+local-app)",
        }

        async with aiohttp.ClientSession(timeout=timeout, headers=session_headers) as session:
            if weather_cfg.provider == "CHMI":
                return await fetch_chmi_region_forecast(
                    session=session,
                    region_code=weather_cfg.chmi_region_code,
                    location_label=weather_cfg.chmi_location_label,
                )

            if weather_cfg.provider == "CHMI_METEOGRAM":
                try:
                    return await fetch_chmi_meteogram_forecast(
                        session=session,
                        poi_id=weather_cfg.chmi_meteogram_poi_id,
                        location_label=weather_cfg.chmi_location_label,
                        x=weather_cfg.chmi_meteogram_x,
                        y=weather_cfg.chmi_meteogram_y,
                    )
                except Exception as exc:
                    logger.warning(
                        "⚠️ Meteogram refresh selhal, prepinam na regionalni CHMI fallback: "
                        f"{exc}"
                    )
                    return await fetch_chmi_region_forecast(
                        session=session,
                        region_code=weather_cfg.chmi_region_code,
                        location_label=weather_cfg.chmi_location_label,
                    )

        raise RuntimeError(f"Nepodporovany weather provider: {weather_cfg.provider}")

    def _on_weather_refresh_finished(self, future):
        """Dokonci weather refresh ve vlakne GUI po async stazeni."""
        try:
            snapshot = future.result()
            error_text = None
        except Exception as exc:
            snapshot = None
            error_text = str(exc)

        self.after(0, lambda s=snapshot, e=error_text: self._complete_weather_refresh(s, e))

    def _complete_weather_refresh(self, snapshot, error_text):
        """Aplikuje vysledek weather refresh a obnovi automation panel."""
        self.weather_refresh_in_progress = False

        if error_text:
            self.weather_last_error = error_text
            logger.warning(f"⚠️ CHMI refresh selhal: {error_text}")
        else:
            self.weather_snapshot = snapshot
            self.weather_last_refresh_at = datetime.now()
            self.weather_last_error = None

            if snapshot is not None:
                logger.info(
                    "✅ CHMI refresh uspesny "
                    f"({snapshot.region_code}, {len(snapshot.intervals)} intervalu)"
                )

        self._refresh_automation_summary(current_time=datetime.now())

    def _trigger_weather_refresh_if_due(self, current_time):
        """Spusti obnoveni weather cache podle nastaveneho intervalu."""
        self._start_weather_refresh(force=False)

    def refresh_energy_data(self, view_key="weekly"):
        """Nacte spotrebu energie pro vybrane obdobi a aktualizuje EnergyPanel.

        Args:
            view_key: Pohled `daily`, `weekly`, `monthly` nebo `yearly`.
        """
        query = resolve_energy_query(view_key)
        self.energy_panel.show_loading()

        async def _fetch():
            api = await self.initialize_api()
            return await api.get_energy_usage(
                self.device_id,
                period=query.period,
                start_date=query.start_date,
                end_date=query.end_date,
            )

        def _done(future):
            try:
                raw_data = future.result()
                data_list = normalize_energy_records(raw_data)
                self.energy_last_data = data_list
                self.energy_last_period = query.period
                self.energy_last_view_key = query.view_key

                current_power_w = self._extract_current_power_w()
                self.after(
                    0,
                    lambda: self.energy_panel.update_data(
                        data_list,
                        view_key=query.view_key,
                        period=query.period,
                        current_power_w=current_power_w,
                    ),
                )
            except Exception as e:
                logger.error(f"❌ Chyba pri nacitani energy dat: {e}")
                self.after(0, lambda: self.energy_panel.show_error(str(e)))

        future = asyncio.run_coroutine_threadsafe(_fetch(), self.loop)
        future.add_done_callback(_done)

    def export_energy_data(self, view_key="weekly"):
        """Exportuje posledni nactenou datovou sadu spotreby do CSV.

        Args:
            view_key: Pozadovany pohled z energy panelu.
        """
        if view_key != self.energy_last_view_key:
            self.status_var.set("Nejdriv nacti data pro zvolene obdobi a pak spust export")
            return

        if not self.energy_last_data:
            self.status_var.set("Pro export nejsou k dispozici zadna data")
            return

        query = resolve_energy_query(view_key)
        default_name = f"spotreba_{query.view_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path = filedialog.asksaveasfilename(
            title="Ulozit spotrebu energie",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV", "*.csv"), ("Vsechny soubory", "*.*")],
        )

        if not file_path:
            return

        try:
            export_energy_records_csv(
                file_path=file_path,
                records=self.energy_last_data,
                period=self.energy_last_period,
                view_label=query.label,
            )
            self.status_var.set(f"Spotreba exportovana do: {file_path}")
        except Exception as e:
            logger.error(f"❌ Chyba pri exportu energy dat: {e}")
            self.status_var.set(f"Export selhal: {e}")
