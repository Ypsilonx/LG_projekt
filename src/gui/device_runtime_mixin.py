# -*- coding: utf-8 -*-
"""Mixiny pro runtime zařízení: command pipeline, status refresh a MQTT update flow."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime
from tkinter import messagebox

from command_policy import build_command_plan
from klima_logic import create_control_payload

logger = logging.getLogger(__name__)


class DeviceRuntimeMixin:
    """Mnozina metod pro odesilani prikazu a zpracovani stavu zarizeni."""

    def _schedule_status_refresh(self, delay_ms: int, reason: str = ""):
        """Naplanuje sloucenou HTTP aktualizaci stavu.

        Pokud je MQTT pripojene, refresh slouzi jen jako pojistka a pouziva
        delsi interval. Opakovane planovani v kratkem case se slouci do jednoho
        pozadavku, aby se snizilo zatizeni API.

        Args:
            delay_ms: Pozadovane zpozdeni v milisekundach.
            reason: Duvod pro logovani.
        """
        mqtt_online = bool(self._mqtt_active and self.api and self.api.mqtt_connected)
        effective_delay_ms = max(delay_ms, 6000) if mqtt_online else delay_ms

        if self._status_refresh_after_id is not None:
            try:
                self.after_cancel(self._status_refresh_after_id)
            except Exception:
                # Pokud callback mezitim dobehl, nemusime ruseni resit.
                pass
            self._status_refresh_after_id = None

        self._status_refresh_after_id = self.after(effective_delay_ms, self._run_scheduled_status_refresh)

        suffix = " (MQTT fallback)" if mqtt_online else ""
        if reason:
            logger.info(
                f"Naplánována aktualizace stavu za {effective_delay_ms/1000:.1f}s{suffix} [{reason}]"
            )

    def _run_scheduled_status_refresh(self):
        """Spusti naplanovanou sloucenou HTTP aktualizaci stavu."""
        self._status_refresh_after_id = None
        asyncio.run_coroutine_threadsafe(self.update_device_status(), self.loop)

    def _build_payload_for_command(self, command, *args, device_status=None):
        """Vytvori ThinQ payload pro interni prikaz.

        Args:
            command: Interni nazev prikazu.
            args: Argumenty prikazu.
            device_status: Volitelny snapshot stavu zarizeni (pro toggle).

        Returns:
            dict | None: Payload pro API, nebo None pri neznamem prikazu.
        """
        if command == "toggle_power":
            current_power = (
                (device_status or {}).get("operation", {}).get("airConOperationMode", "POWER_OFF")
            )
            new_state = "POWER_ON" if current_power == "POWER_OFF" else "POWER_OFF"
            logger.info(f"Toggle power: {current_power} -> {new_state}")
            return create_control_payload("power", new_state)

        if command == "power_on":
            return create_control_payload("power", "POWER_ON")

        if command == "power_off":
            return create_control_payload("power", "POWER_OFF")

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

    def _apply_status_hint(self, status_snapshot, command, args):
        """Aplikuje lokalni odhad zmeny stavu po uspesnem prikazu.

        Odhad snizuje riziko kolizi mezi kroky v ramci jedne sekvence,
        nez dorazi potvrzeny stav pres MQTT/HTTP refresh.

        Args:
            status_snapshot: Aktualni snapshot stavu.
            command: Provedeny interni prikaz.
            args: Argumenty prikazu.

        Returns:
            dict: Aktualizovany snapshot stavu.
        """
        if not isinstance(status_snapshot, dict):
            status_snapshot = {}

        if command == "power_on":
            status_snapshot.setdefault("operation", {})["airConOperationMode"] = "POWER_ON"
        elif command == "power_off":
            status_snapshot.setdefault("operation", {})["airConOperationMode"] = "POWER_OFF"
        elif command == "change_mode":
            status_snapshot.setdefault("airConJobMode", {})["currentJobMode"] = args[0]
        elif command == "set_temperature":
            status_snapshot.setdefault("temperature", {})["targetTemperature"] = args[0]
        elif command == "set_wind_strength":
            status_snapshot.setdefault("airFlow", {})["windStrength"] = args[0]
        elif command == "set_wind_direction":
            wind = status_snapshot.setdefault("windDirection", {})
            wind["rotateUpDown"] = bool(args[0])
            wind["rotateLeftRight"] = bool(args[1])
        elif command == "set_power_save":
            status_snapshot.setdefault("powerSave", {})["powerSaveEnabled"] = bool(args[0])

        return status_snapshot

    def handle_device_command(self, command, *args):
        """Zpracovani prikazu z GUI komponent."""
        logger.info(f"Příkaz zařízení: {command}, parametry: {args}")

        # Spusteni asynchronniho prikazu
        future = asyncio.run_coroutine_threadsafe(
            self._execute_device_command(command, *args),
            self.loop,
        )

        def handle_result():
            try:
                future.result(timeout=10)  # Cekani max 10 sekund
            except Exception as e:
                logger.error(f"Chyba při provádění příkazu {command}: {e}")
                error_msg = str(e)
                self.after(0, lambda msg=error_msg: messagebox.showerror("Chyba", f"Příkaz {command} selhal: {msg}"))

        threading.Thread(target=handle_result, daemon=True).start()

    async def _execute_device_command(self, command, *args):
        """Asynchronni provadeni prikazu zarizeni."""
        try:
            if self._command_execution_lock is None:
                self._command_execution_lock = asyncio.Lock()

            async with self._command_execution_lock:
                api = await self.initialize_api()

                # Preferujeme posledni znamy stav (MQTT/refresh), aby se zbytecne
                # nevytvarely dalsi HTTP dotazy pri kazdem kliknuti.
                status_snapshot = self.last_device_status if isinstance(self.last_device_status, dict) else None
                if not status_snapshot:
                    status_snapshot = await api.get_device_status(self.device_id)

                plan = build_command_plan(command, tuple(args), status_snapshot)
                if plan.should_skip:
                    message = plan.skip_reason or "Příkaz přeskočen"
                    logger.info(f"Příkaz {command} přeskočen: {message}")
                    self.after(0, lambda m=message: self.status_var.set(m))
                    return

                for idx, step in enumerate(plan.steps):
                    payload = self._build_payload_for_command(
                        step.command,
                        *step.args,
                        device_status=status_snapshot,
                    )

                    if payload is None:
                        logger.warning(f"Neznámý krok v plánu: {step.command}")
                        continue

                    result = await api.send_device_command(self.device_id, payload)
                    logger.info(f"Příkaz {step.command} úspěšně odeslán: {result}")

                    status_snapshot = self._apply_status_hint(status_snapshot, step.command, step.args)

                    is_last_step = idx == len(plan.steps) - 1
                    if not is_last_step and step.delay_after_seconds > 0:
                        await asyncio.sleep(step.delay_after_seconds)

                # Pro nastaveni teploty cekame delsi dobu na aktualizaci
                if command == "set_temperature":
                    self._schedule_status_refresh(3000, reason="set_temperature")
                else:
                    # Rychla aktualizace stavu (po 1 sekunde)
                    self._schedule_status_refresh(1000, reason=command)

        except Exception as e:
            logger.error(f"Chyba při provádění příkazu {command}: {e}")
            raise

    async def update_device_status(self):
        """Aktualizace stavu zarizeni."""
        try:
            api = await self.initialize_api()
            status = await api.get_device_status(self.device_id)

            # Kontrola zmen ve stavu
            if status != self.last_device_status:
                self.last_device_status = status

                # Aktualizace GUI v hlavnim vlakne
                self.after(0, lambda: self._update_gui_status(status))

                logger.info("Stav zařízení aktualizován")

        except Exception as e:
            logger.error(f"Chyba při aktualizaci stavu: {e}")
            error_msg = str(e)
            self.after(0, lambda: self.status_var.set(f"Chyba: {error_msg}"))
            self.after(0, lambda: self.led_indicator.set_state("error"))

    async def manual_update_device_status(self):
        """Specialni verze update_device_status pro manual refresh - vzdy aktualizuje GUI."""
        try:
            api = await self.initialize_api()
            status = await api.get_device_status(self.device_id)

            # Pri manual refresh vzdy aktualizujeme GUI, i kdyz se stav nezmenil
            self.last_device_status = status

            # Aktualizace GUI v hlavnim vlakne
            self.after(0, lambda: self._update_gui_status(status))

            logger.info("Manual refresh: Stav zařízení aktualizován")

        except Exception as e:
            logger.error(f"Chyba při manual refresh: {e}")
            error_msg = str(e)
            self.after(0, lambda: self.status_var.set(f"Chyba: {error_msg}"))
            self.after(0, lambda: self.led_indicator.set_state("error"))

    def _update_gui_status(self, device_status):
        """Aktualizace GUI podle stavu zarizeni (hlavni vlakno)."""
        try:
            # Aktualizace status baru - kombinace runState a operation
            run_state = device_status.get("runState", {}).get("currentState", "UNKNOWN")
            power_operation = device_status.get("operation", {}).get("airConOperationMode", "POWER_OFF")
            mode = device_status.get("airConJobMode", {}).get("currentJobMode", "N/A")
            temp = device_status.get("temperature", {}).get("currentTemperature", "?")
            ac_target_temp = device_status.get("temperature", {}).get("targetTemperature")
            weather_cfg = self.automation_rules.weather
            ac_indoor_temperature_proxy_offset_c = float(
                weather_cfg.ac_indoor_temperature_proxy_offset_c
            )
            estimated_indoor_temp = None
            poer_indoor_temp = getattr(self, "poer_indoor_temperature_c", None)
            poer_target_temp = getattr(self, "poer_target_temperature_c", None)
            ac_sensor_temp = None
            try:
                ac_sensor_temp = float(temp)
            except (TypeError, ValueError):
                ac_sensor_temp = None
            if weather_cfg.indoor_current_temperature_source == "poer_api" and poer_indoor_temp is not None:
                estimated_indoor_temp = float(poer_indoor_temp)
                indoor_source_label = "teplota z termostatu POER"
            elif weather_cfg.indoor_current_temperature_c is not None:
                estimated_indoor_temp = float(weather_cfg.indoor_current_temperature_c)
                indoor_source_label = "teplota z termostatu"
            else:
                indoor_source_label = "odhad interieru z AC"
                try:
                    estimated_indoor_temp = (
                        float(temp) + ac_indoor_temperature_proxy_offset_c
                    )
                except (TypeError, ValueError):
                    estimated_indoor_temp = None

            # Kombinace stavu pro display
            if power_operation == "POWER_ON" and run_state == "NORMAL":
                display_state = "Zapnuto"
                led_state = "on"
            elif power_operation == "POWER_OFF":
                display_state = "Vypnuto"
                led_state = "off"
            elif run_state == "ERROR":
                display_state = "Chyba"
                led_state = "error"
            else:
                display_state = f"{power_operation}/{run_state}"
                led_state = "error"

            if estimated_indoor_temp is None:
                temp_text = "nedostupna"
            else:
                temp_text = f"{estimated_indoor_temp:.1f}°C"

            ac_sensor_text = "nedostupna" if ac_sensor_temp is None else f"{ac_sensor_temp:.1f}°C"
            ac_target_text = (
                f"{float(ac_target_temp):.1f}°C"
                if isinstance(ac_target_temp, (int, float))
                else "nedostupna"
            )
            poer_target_text = (
                f"{float(poer_target_temp):.1f}°C"
                if isinstance(poer_target_temp, (int, float))
                else "nedostupna"
            )

            status_text = (
                f"Stav: {display_state}, Rezim: {mode}, "
                f"{indoor_source_label}: {temp_text}, AC čidlo: {ac_sensor_text}, "
                f"Cíl AC: {ac_target_text}, Cíl POER: {poer_target_text}"
            )
            self.status_var.set(status_text)
            self._update_live_state_header(device_status)

            # LED indikator
            logger.info(f"Aktualizuji LED: power={power_operation}, run={run_state} -> {led_state}")
            self.led_indicator.set_state(led_state)

            # Aktualizace vsech komponent
            if hasattr(self, 'climate_controls'):
                displayed_indoor_temp = weather_cfg.indoor_current_temperature_c
                displayed_indoor_source = "ac_builtin_sensor"
                if weather_cfg.indoor_current_temperature_source == "poer_api" and poer_indoor_temp is not None:
                    displayed_indoor_temp = float(poer_indoor_temp)
                    displayed_indoor_source = "external_thermostat"
                elif weather_cfg.indoor_current_temperature_c is not None:
                    displayed_indoor_source = "external_thermostat"

                self.climate_controls.update_status(
                    device_status,
                    ac_indoor_temperature_proxy_offset_c=(
                        ac_indoor_temperature_proxy_offset_c
                    ),
                    indoor_temperature_c=displayed_indoor_temp,
                    indoor_temperature_source=displayed_indoor_source,
                    poer_target_temperature_c=poer_target_temp,
                )

            if hasattr(self, 'timer_controls'):
                self.timer_controls.update_status(device_status)

            if hasattr(self, 'info_panel'):
                self.info_panel.update_status(device_status)

            self._refresh_weather_visualization(datetime.now())

        except Exception as e:
            logger.error(f"Chyba při aktualizaci GUI: {e}")
            self.status_var.set(f"Chyba GUI: {e}")

    def initial_status_check(self):
        """Pocatecni nacteni stavu a spusteni MQTT streamu."""
        asyncio.run_coroutine_threadsafe(self._initial_connect(), self.loop)

    async def _initial_connect(self):
        """Inicializuje API, nacte pocatecni stav zarizeni a pokusi se pripojit MQTT."""
        # Krok 1: jednorazove nacteni stavu pres HTTP
        await self.update_device_status()

        # Krok 2: spusteni MQTT real-time streamu
        api = await self.initialize_api()
        self.after(0, lambda: self.status_var.set(
            self.status_var.get() + " | Připojuji MQTT..."
        ))
        success = await api.connect_mqtt(on_message=self._on_mqtt_message)
        self._mqtt_active = success

        if success:
            logger.info("✅ MQTT stream aktivní – polling deaktivován")
            self.after(0, self._update_mqtt_status_indicator)
        else:
            logger.warning("⚠️ MQTT nepřipojeno – záloha: ruční aktualizace tlačítkem")
            self.after(0, lambda: self.status_var.set(
                self.status_var.get().replace(" | Připojuji MQTT...", "") +
                " | MQTT nedostupné"
            ))

    def _on_mqtt_message(self, topic, payload, dup, qos, retain, **kwargs):
        """Callback volany pri kazde MQTT zprave ze zarizeni."""
        logger.debug(f"📡 MQTT zpráva: topic={topic}")
        try:
            # MQTT payload muze byt bytes nebo dict
            if isinstance(payload, (bytes, bytearray)):
                data = json.loads(payload.decode("utf-8"))
            else:
                data = payload

            # Extrahovat stav zarizeni z event obalky
            device_status = data.get("event", {}).get("push", data)

            if device_status:
                self.last_device_status = device_status
                # GUI aktualizace musi probehnout v hlavnim vlakne
                self.after(0, lambda s=device_status: self._update_gui_status(s))
                logger.info("📡 MQTT: GUI aktualizováno ze real-time zprávy")
        except Exception as e:
            logger.error(f"Chyba při zpracování MQTT zprávy: {e}")

    def _update_mqtt_status_indicator(self):
        """Aktualizuje status bar aby zobrazoval MQTT stav."""
        current = self.status_var.get().replace(" | Připojuji MQTT...", "")
        self.status_var.set(current)

    def manual_refresh(self):
        """Manualni obnoveni stavu."""
        try:
            logger.info("🔄 Manuální refresh - START")
            self.status_var.set("Aktualizuji...")
            self.led_indicator.set_state("error")  # Oranzova pri nactani

            # Spustime async update a cekame na vysledek
            future = asyncio.run_coroutine_threadsafe(self.manual_update_device_status(), self.loop)

            # Pockame chvilku a zkontrolujeme stav
            def check_result():
                try:
                    if future.done():
                        if future.exception():
                            error = future.exception()
                            logger.error(f"❌ Manual refresh failed: {error}")
                            self.status_var.set(f"Chyba refresh: {error}")
                            self.led_indicator.set_state("error")
                        else:
                            logger.info("✅ Manual refresh - SUCCESS")
                            # Nebudeme nastavovat success, nechame LED odrazet skutecny stav zarizeni
                    else:
                        # Pokud jeste nedobehl, zkusime znovu za 500ms
                        self.after(500, check_result)
                except Exception as e:
                    logger.error(f"❌ Check result error: {e}")
                    self.status_var.set(f"Chyba: {e}")
                    self.led_indicator.set_state("error")

            # Zkontrolujeme vysledek za 1s
            self.after(1000, check_result)

            logger.info("Manuální refresh spuštěn")
        except Exception as e:
            logger.error(f"Chyba při manuálním refresh: {e}")
            self.status_var.set(f"Chyba refresh: {e}")
            self.led_indicator.set_state("error")
