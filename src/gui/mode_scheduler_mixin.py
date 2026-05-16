# -*- coding: utf-8 -*-
"""Mixiny pro HAND/AUTO režim a běh plánovače v GUI aplikaci."""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ModeSchedulerMixin:
    """Mnozina metod pro prepinani rezimu a scheduler runtime."""

    def _update_mode_buttons(self):
        """Synchronizuje stavy tlacitek AUTO/HAND s aktualnim rezimem."""
        if self.hand_mode_active:
            self.stop_schedule_btn.config(state='disabled')
            self.resume_automation_btn.config(state='normal')
        else:
            self.stop_schedule_btn.config(state='normal')
            self.resume_automation_btn.config(state='disabled')

    def _apply_mode_visibility(self):
        """Aplikuje viditelnost HAND-only panelu a planovace."""
        if hasattr(self, 'climate_controls') and self.climate_controls:
            self.climate_controls.set_hand_mode(self.hand_mode_active)

        if hasattr(self, 'info_panel') and self.info_panel:
            self.info_panel.set_hand_mode(self.hand_mode_active)
            if self.hand_mode_active and not self._info_panel_visible:
                self.info_panel.pack(pady=10, padx=10, fill='x', before=self.energy_panel)
                self._info_panel_visible = True
            elif (not self.hand_mode_active) and self._info_panel_visible:
                self.info_panel.pack_forget()
                self._info_panel_visible = False

        if hasattr(self, 'scheduler_widget') and self.scheduler_widget:
            if self.hand_mode_active and not self._scheduler_visible:
                self.scheduler_widget.pack(pady=10, padx=10, fill='x')
                self._scheduler_visible = True
            elif (not self.hand_mode_active) and self._scheduler_visible:
                self.scheduler_widget.pack_forget()
                self._scheduler_visible = False

    def _set_hand_mode(self, enabled, note=None):
        """Nastavi aplikaci do HAND nebo AUTO rezimu.

        Args:
            enabled: True pro HAND, False pro AUTO.
            note: Volitelna textova poznamka do automatizacniho panelu.
        """
        self.hand_mode_active = bool(enabled)

        # Pri prepnuti rezimu vynulujeme scheduler stav, aby nedoslo k navazani
        # na stary aktivni plan po zmene rezimu.
        self.last_executed_schedule = None
        self.schedule_was_active_last_check = False
        self.blocked_schedule_entry = None
        self.blocked_schedule_reason = None

        self._apply_mode_visibility()
        self._update_mode_buttons()
        self._refresh_automation_summary(note=note)

    def _update_automation_mode_banner(self, active_schedule=None):
        """Aktualizuje horni indikaci stavu AUTO/HAND rezimu.

        Args:
            active_schedule: Aktivní plán, pokud je k dispozici.
        """
        if self.hand_mode_active:
            if active_schedule is not None:
                self.auto_mode_var.set(f"🖐️ HAND mód: aktivní plán '{active_schedule.name}'")
            else:
                self.auto_mode_var.set("🖐️ HAND mód: ruční řízení")
            return

        self.auto_mode_var.set("🤖 AUTO mód: PID regulace + pravidla")

    def stop_active_schedule(self):
        """Prepne aplikaci do HAND rezimu (rucni rizeni)."""
        try:
            self._set_hand_mode(True, note="HAND rezim aktivovan uzivatelem.")
            self.status_var.set("HAND rezim aktivni - planovac a rucne prvky jsou zapnuty")
        except Exception as e:
            logger.error(f"Chyba pri aktivaci HAND rezimu: {e}")
            self.status_var.set(f"Chyba: {e}")

    def resume_automatic_mode(self):
        """Prepne aplikaci do AUTO rezimu (automaticka regulace)."""
        self._set_hand_mode(False, note="AUTO rezim aktivovan uzivatelem.")
        self.status_var.set("AUTO rezim aktivni - rizeni prevzala automatika")

    def execute_scheduled_command(self, schedule_entry):
        """Provádí naplánovaný příkaz se zachováním postupných prodlev.

        Args:
            schedule_entry: Aktivní položka plánovače.

        Returns:
            None
        """
        logger.info(f"🎯 Provádím naplánovaný příkaz: {schedule_entry.name}")

        try:
            if schedule_entry.power_on:
                logger.info("  ↳ Kontroluji stav a zapínám zařízení pokud je vypnuto")
                self.handle_device_command("power_on")
                self.after(3000, lambda entry=schedule_entry: self._execute_schedule_after_power_on(entry))
                return

            if schedule_entry.mode:
                logger.info(f"  ↳ Nastavuji režim: {schedule_entry.mode}")
                self.handle_device_command("change_mode", schedule_entry.mode)

            if schedule_entry.mode and (schedule_entry.temperature or schedule_entry.wind):
                self.after(
                    3000,
                    lambda entry=schedule_entry: self._execute_schedule_remaining_params(
                        entry,
                        update_status=False,
                    ),
                )
            elif not schedule_entry.mode:
                self._execute_schedule_remaining_params(schedule_entry, update_status=False)
            else:
                self._finish_schedule_execution(schedule_entry, update_status=False)

        except Exception as e:
            logger.error(f"❌ Chyba při provádění plánu '{schedule_entry.name}': {e}")
            self.status_var.set(f"Chyba při provádění plánu: {e}")

    def _execute_schedule_after_power_on(self, schedule_entry):
        """Pokračuje zpracováním plánu po zapnutí zařízení.

        Args:
            schedule_entry: Aktivní položka plánovače.

        Returns:
            None
        """
        try:
            if schedule_entry.mode:
                logger.info(f"  ↳ Nastavuji režim: {schedule_entry.mode}")
                self.handle_device_command("change_mode", schedule_entry.mode)

            self.after(
                3000,
                lambda entry=schedule_entry: self._execute_schedule_remaining_params(
                    entry,
                    update_status=True,
                ),
            )
        except Exception as e:
            logger.error(f"❌ Chyba při nastavování režimu plánu '{schedule_entry.name}': {e}")
            self.status_var.set(f"Chyba při nastavování režimu: {e}")

    def _execute_schedule_remaining_params(self, schedule_entry, update_status):
        """Zpracuje teplotu a připraví případný krok pro větrák.

        Args:
            schedule_entry: Aktivní položka plánovače.
            update_status: Zda po dokončení nastavit text stavu.

        Returns:
            None
        """
        try:
            if schedule_entry.temperature and schedule_entry.mode != "FAN":
                logger.info(f"  ↳ Nastavuji teplotu: {schedule_entry.temperature}°C")
                self.handle_device_command("set_temperature", schedule_entry.temperature)

            if schedule_entry.wind:
                self.after(
                    2000,
                    lambda entry=schedule_entry, should_update=update_status: self._execute_schedule_wind_step(
                        entry,
                        should_update,
                    ),
                )
            else:
                self._finish_schedule_execution(schedule_entry, update_status)
        except Exception as e:
            logger.error(f"❌ Chyba při nastavování parametrů plánu '{schedule_entry.name}': {e}")
            self.status_var.set(f"Chyba při nastavování: {e}")

    def _execute_schedule_wind_step(self, schedule_entry, update_status):
        """Aplikuje krok síly větráku a dokončí plán.

        Args:
            schedule_entry: Aktivní položka plánovače.
            update_status: Zda po dokončení nastavit text stavu.

        Returns:
            None
        """
        try:
            if schedule_entry.wind:
                logger.info(f"  ↳ Nastavuji sílu větráku: {schedule_entry.wind}")
                self.handle_device_command("set_wind_strength", schedule_entry.wind)

            self._finish_schedule_execution(schedule_entry, update_status)
        except Exception as e:
            logger.error(f"❌ Chyba při nastavování větráku plánu '{schedule_entry.name}': {e}")
            self.status_var.set(f"Chyba při nastavování větráku: {e}")

    def _finish_schedule_execution(self, schedule_entry, update_status):
        """Uzavře běh plánu logem a volitelně i stavovým textem.

        Args:
            schedule_entry: Aktivní položka plánovače.
            update_status: Zda do status baru propsat dokončení plánu.

        Returns:
            None
        """
        logger.info(f"✅ Plán '{schedule_entry.name}' byl úspěšně proveden")
        if update_status:
            self.status_var.set(f"Plán '{schedule_entry.name}' dokončen")

    def on_schedule_change(self, schedule_entries):
        """Callback volaný při změně plánu."""
        logger.info(f"Plán aktualizován: {len(schedule_entries)} položek")

    def periodic_schedule_check(self):
        """Pravidelná kontrola plánů pro automatické spouštění."""
        if not self.schedule_check_active:
            return

        try:
            current_time = datetime.now()
            active_schedule = None
            self._trigger_weather_refresh_if_due(current_time)

            # Planovac je aktivni pouze v HAND modu.
            if self.hand_mode_active and hasattr(self, 'scheduler_widget') and self.scheduler_widget:
                active_schedule = self.scheduler_widget.get_active_schedule_for_time(current_time)

                if active_schedule:
                    self.schedule_was_active_last_check = True

                    if active_schedule != self.last_executed_schedule:
                        current_minute = current_time.strftime("%H:%M")
                        schedule_start = active_schedule.start_time

                        if (
                            current_minute == schedule_start
                            or (self.last_executed_schedule is None and active_schedule.enabled)
                        ):
                            schedule_to_run, resolution = self._apply_automation_rules_to_schedule(
                                active_schedule,
                                current_time,
                            )

                            if schedule_to_run is None:
                                logger.warning(
                                    f"⛔ Plan '{active_schedule.name}' byl blokovan pravidly: {resolution.reason}"
                                )
                                self.blocked_schedule_entry = active_schedule
                                self.blocked_schedule_reason = resolution.reason
                                self.after(0, lambda m=resolution.reason: self.status_var.set(f"⛔ {m}"))
                            else:
                                self.blocked_schedule_entry = None
                                self.blocked_schedule_reason = None
                                if schedule_to_run.mode != active_schedule.mode:
                                    logger.info(
                                        f"🔁 Plan '{active_schedule.name}' upraven pravidly: "
                                        f"{active_schedule.mode} -> {schedule_to_run.mode}"
                                    )

                                logger.info(
                                    f"🕒 Spoustim naplanovany prikaz: {active_schedule.name} v {schedule_start}"
                                )
                                self.execute_scheduled_command(schedule_to_run)

                            self.last_executed_schedule = active_schedule

                    if active_schedule == self.blocked_schedule_entry:
                        reason = self.blocked_schedule_reason or "Plan je blokovan pravidly."
                        self.after(0, lambda m=reason: self.status_var.set(f"⛔ {m}"))
                    else:
                        remaining_time = self._calculate_remaining_time(active_schedule, current_time)
                        if remaining_time:
                            self.after(0, lambda: self.status_var.set(
                                f"🏃 Aktivni: {active_schedule.name} (zbyva {remaining_time})"
                            ))
                else:
                    if self.schedule_was_active_last_check and self.last_executed_schedule:
                        if getattr(self.last_executed_schedule, 'power_off_at_end', True):
                            logger.info(f"🔚 Plan '{self.last_executed_schedule.name}' skoncil - vypinam zarizeni")
                            self.handle_device_command("power_off")
                            self.status_var.set(f"Plan '{self.last_executed_schedule.name}' dokoncen - zarizeni vypnuto")
                        else:
                            logger.info(f"🔚 Plan '{self.last_executed_schedule.name}' skoncil - zarizeni zustava zapnute")
                            self.status_var.set(f"Plan '{self.last_executed_schedule.name}' dokoncen - zarizeni bezi")

                    self.schedule_was_active_last_check = False
                    self.last_executed_schedule = None
                    self.blocked_schedule_entry = None
                    self.blocked_schedule_reason = None

                    next_schedule, time_to_next = self._find_next_schedule(current_time)
                    if next_schedule and time_to_next:
                        current_status = self.status_var.get()
                        if not current_status.startswith("🏃") and not current_status.startswith("Chyba"):
                            self.after(0, lambda: self.status_var.set(
                                f"⏰ Dalsi: {next_schedule.name} za {time_to_next}"
                            ))
            else:
                self.schedule_was_active_last_check = False
                self.last_executed_schedule = None
                self.blocked_schedule_entry = None
                self.blocked_schedule_reason = None

            self._run_thermal_regulation(current_time=current_time, active_schedule=active_schedule)
            self._refresh_automation_summary(current_time=current_time, active_schedule=active_schedule)
            self._update_mode_buttons()

        except Exception as e:
            logger.error(f"Chyba při kontrole plánů: {e}")

        # Naplánuj další kontrolu
        if self.schedule_check_active:
            interval_ms = getattr(self, "schedule_check_interval_ms", 30000)
            self.after(interval_ms, self.periodic_schedule_check)

    def _calculate_remaining_time(self, schedule_entry, current_time):
        """Výpočet zbývajícího času aktivního plánu."""
        try:
            end_time = datetime.strptime(schedule_entry.end_time, "%H:%M").time()
            current_time_only = current_time.time()

            # Převod na minuty
            end_minutes = end_time.hour * 60 + end_time.minute
            current_minutes = current_time_only.hour * 60 + current_time_only.minute

            if end_minutes < current_minutes:  # Přes půlnoc
                end_minutes += 24 * 60

            remaining_minutes = end_minutes - current_minutes
            if remaining_minutes > 0:
                hours = remaining_minutes // 60
                minutes = remaining_minutes % 60
                if hours > 0:
                    return f"{hours}h {minutes}min"
                return f"{minutes}min"
        except Exception:
            pass
        return None

    def _find_next_schedule(self, current_time):
        """Najde nejbližší nadcházející plán."""
        try:
            if not hasattr(self, 'scheduler_widget') or not self.scheduler_widget:
                return None, None

            current_time_only = current_time.time()
            current_minutes = current_time_only.hour * 60 + current_time_only.minute

            closest_schedule = None
            closest_minutes = float('inf')

            for entry in self.scheduler_widget.schedule_entries:
                if not entry.enabled:
                    continue

                try:
                    start_time = datetime.strptime(entry.start_time, "%H:%M").time()
                    start_minutes = start_time.hour * 60 + start_time.minute

                    # Pokud je start_time dnes později
                    if start_minutes > current_minutes:
                        minutes_diff = start_minutes - current_minutes
                        if minutes_diff < closest_minutes:
                            closest_minutes = minutes_diff
                            closest_schedule = entry
                    else:
                        # Zítra
                        minutes_diff = (24 * 60) - current_minutes + start_minutes
                        if minutes_diff < closest_minutes:
                            closest_minutes = minutes_diff
                            closest_schedule = entry

                except Exception:
                    continue

            if closest_schedule and closest_minutes < float('inf'):
                hours = closest_minutes // 60
                minutes = closest_minutes % 60
                if hours > 24:
                    return closest_schedule, f"{hours//24}d {hours%24}h"
                if hours > 0:
                    return closest_schedule, f"{hours}h {minutes}min"
                return closest_schedule, f"{minutes}min"

        except Exception as e:
            logger.error(f"Chyba při hledání nejbližšího plánu: {e}")

        return None, None
