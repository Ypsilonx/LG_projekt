# -*- coding: utf-8 -*-
"""
GUI aplikace ThermoControl-LG-POER_app pro ovládání klimatizace a termostatu.
Poskytuje moderní tmavé rozhraní s responzivními prvky a pokročilým plánováním.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
import sys

# ============================================================================
# KONFIGURACE
# ============================================================================
# MQTT real-time stream je primární zdroj aktualizací stavu.
# HTTP polling je zachován pouze jako záloha (tlačítko Aktualizovat)
# a pro počáteční načtení stavu při spuštění.
SCHEDULE_CHECK_INTERVAL = 30000  # Kontrola spuštění plánovaných úkolů (ms) - 30s
# ============================================================================

# Import modulů aplikace
sys.path.insert(0, str(Path(__file__).parent.parent))
from server_api import ThinQAPI, get_ac_device_id
from thermal_controller import (
    ThermalControlPolicy,
    ThermalControlState,
)
from gui.theme import setup_dark_theme
from gui.widgets import LEDIndicator, EnergyPanel, WeatherForecastPanel
from gui.controls import ClimateControls, TimerControls, InfoPanel, POERStatusPanel
from gui.scheduler import SchedulerWidget
from gui.automation_energy_mixin import AutomationEnergyMixin
from gui.mode_scheduler_mixin import ModeSchedulerMixin
from gui.device_runtime_mixin import DeviceRuntimeMixin

# Nastavení logování
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ClimateApp(DeviceRuntimeMixin, ModeSchedulerMixin, AutomationEnergyMixin, tk.Tk):
    """Hlavní GUI aplikace pro ovládání klimatizace a termostatu."""
    
    def __init__(self):
        super().__init__()
        self.title("ThermoControl-LG-POER_app")
        self.geometry("820x860")
        self.resizable(True, True)
        self.minsize(680, 680)
        
        # Nastavení tmavého tématu
        setup_dark_theme(self)
        
        # Inicializace API a dat
        self.api = None
        try:
            self.device_id = get_ac_device_id()
        except Exception as e:
            logger.error(f"Nelze načíst Device ID: {e}")
            messagebox.showerror("Chyba konfigurace", str(e))
            self.destroy()
            return
        self.device_profile = self.load_device_profile()
        self.last_device_status = None
        self.pending_update = False
        self._mqtt_active = False  # True pokud MQTT stream běží
        self._status_refresh_after_id = None  # Sloučený fallback refresh přes HTTP
        self._command_execution_lock = None  # Lock je inicializován v asyncio vlákně
        
        # Status variable pro globální stav
        self.status_var = tk.StringVar(value="Načítám stav zařízení...")
        self.live_state_var = tk.StringVar(value="LG: načítám stav")
        self.poer_live_state_var = tk.StringVar(value="POER: načítám stav")
        self.auto_mode_var = tk.StringVar(value="🤖 AUTO mód: inicializace")
        self.automation_info_var = tk.StringVar(value="Načítám pravidla automatizace...")
        self.poer_summary_var = tk.StringVar(value="POER: načítám stav...")
        self._last_automation_note = None
        self.poer_indoor_temperature_c = None
        self.poer_current_humidity_pct = None
        self.poer_target_temperature_c = None
        self.poer_device_id = None
        self.poer_error = None
        self.poer_hvac_mode = None
        self.poer_preset_mode = None
        self.poer_action = None
        self.poer_min_temp_c = None
        self.poer_max_temp_c = None
        self.weather_snapshot = None
        self.weather_last_refresh_at = None
        self.weather_last_attempt_at = None
        self.weather_last_error = None
        self.weather_refresh_in_progress = False
        self.poer_refresh_in_progress = False
        self.thermal_policy = ThermalControlPolicy()
        self.thermal_state = ThermalControlState()
        self.last_thermal_action_at = None
        self.last_thermal_decision_signature = None

        # Stav režimů, plánovače a energy panelu
        self.schedule_check_active = True
        self.schedule_check_interval_ms = SCHEDULE_CHECK_INTERVAL
        self.last_executed_schedule = None
        self.hand_mode_active = False
        self.schedule_was_active_last_check = False
        self.blocked_schedule_entry = None
        self.blocked_schedule_reason = None
        self._info_panel_visible = False
        self._scheduler_visible = False
        self.energy_last_data = []
        self.energy_last_period = "DAILY"
        self.energy_last_view_key = "weekly"
        
        # Inicializace event loop pro asynchronní operace
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        # Načtení pravidel sezónní automatizace
        self._load_automation_rules()
        
        # Vytvoření GUI
        self.create_widgets()
        
        # Spuštění počáteční kontroly stavu + MQTT
        self.after(100, self.initial_status_check)
        
        # Pravidelná kontrola plánů
        self.periodic_schedule_check()
        
    def load_device_profile(self):
        """
        Načte profil zařízení – nejdříve zkusí stáhnout z API,
        při selhání použije lokální zálohu data/device_profile.json.

        Stažený profil se automaticky uloží jako záloha pro případ výpadku sítě.
        """
        profile_path = Path(__file__).parent.parent.parent / "data" / "device_profile.json"

        # Pokus o stažení z API (spustíme na nové event loop – main loop ještě neběží)
        try:
            from server_api import ThinQAPI as _ThinQAPI

            async def _fetch_profile():
                _api = _ThinQAPI()
                try:
                    return await _api.get_device_profile(self.device_id)
                finally:
                    await _api.close()

            profile = asyncio.run(_fetch_profile())
            if profile:
                # Uložit jako zálohu pro případ výpadku sítě při příštím spuštění
                try:
                    with open(profile_path, "w", encoding="utf-8") as f:
                        json.dump(profile, f, ensure_ascii=False, indent=2)
                    logger.info("💾 Profil zařízení uložen jako lokální záloha")
                except Exception as save_err:
                    logger.warning(f"Nelze uložit zálohu profilu: {save_err}")
                return profile
        except Exception as e:
            logger.warning(f"Nelze stáhnout profil z API: {e} – používám lokální zálohu")

        # Fallback: lokální záloha
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                logger.info("📂 Profil zařízení načten z lokální zálohy")
                return json.load(f)
        except Exception as e:
            logger.error(f"Nelze načíst zálohu profilu: {e}")
            messagebox.showerror("Chyba", f"Nelze načíst profil zařízení: {e}")
            return {}
    
    def create_widgets(self):
        """Vytvoření hlavního GUI"""
        # Hlavní scrollovatelný frame
        main_canvas = tk.Canvas(self, bg="#222222", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=main_canvas.yview)
        self.scrollable_frame = ttk.Frame(main_canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        main_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bindování mouse wheel pro scrollování
        self.bind_mousewheel(main_canvas)
        
        # Status bar s LED indikátorem
        self.create_status_bar()

        # Hlavní automatizační kontext má být vizuálně nahoře.
        self.create_weather_panel()
        self.create_device_tabs()
        self.create_automation_panel()

        # Plánovač (nová funkce)
        self.scheduler_widget = None
        if self.device_profile:
            modes = self.device_profile.get("property", {}).get("airConJobMode", {}).get("currentJobMode", {}).get("value", {}).get("w", ["AUTO", "COOL", "HEAT", "FAN"])
            wind_options = self.device_profile.get("property", {}).get("airFlow", {}).get("windStrength", {}).get("value", {}).get("w", ["AUTO", "LOW", "MID", "HIGH"])
            
            self.scheduler_widget = SchedulerWidget(
                self.scrollable_frame,
                modes=modes,
                wind_options=wind_options,
                on_schedule_change=self.on_schedule_change
            )
            self.scheduler_widget.pack(pady=10, padx=10, fill='x')
            self._scheduler_visible = True

        # Panel spotřeby energie
        self.energy_panel = EnergyPanel(
            self.scrollable_frame,
            on_refresh=self.refresh_energy_data,
            on_export=self.export_energy_data,
        )
        self.energy_panel.pack(pady=10, padx=10, fill='x')

        self._apply_mode_visibility()
        self._update_mode_buttons()
        self._refresh_automation_summary()
        self.after(400, lambda: self.refresh_energy_data("weekly"))
        
        # Aktualizace scrollovatelné oblasti
        self.scrollable_frame.update_idletasks()

    def create_device_tabs(self):
        """Vytvoří LG a POER tab pro hlavní ovládací prvky."""
        tabs_frame = ttk.LabelFrame(self.scrollable_frame, text="🎛 Ovládání zařízení", padding=8)
        tabs_frame.pack(pady=10, padx=10, fill='x')

        self.device_tabs = ttk.Notebook(tabs_frame)
        self.device_tabs.pack(fill='x')

        self.lg_tab = ttk.Frame(self.device_tabs)
        self.poer_tab = ttk.Frame(self.device_tabs)
        self.device_tabs.add(self.lg_tab, text="LG klimatizace")
        self.device_tabs.add(self.poer_tab, text="POER termostat")

        lg_stack = ttk.Frame(self.lg_tab)
        lg_stack.pack(fill='x')

        if self.device_profile:
            self.climate_controls = ClimateControls(
                lg_stack,
                self.device_profile,
                self.status_var,
                on_command=self.handle_device_command,
            )
            self.climate_controls.pack(pady=10, padx=10, fill='x')

        self.timer_controls = TimerControls(
            lg_stack,
            on_command=self.handle_device_command,
        )
        self.timer_controls.pack(pady=10, padx=10, fill='x')

        self.info_panel = InfoPanel(lg_stack)
        self.info_panel.pack(pady=10, padx=10, fill='x')
        self._info_panel_visible = True

        self.poer_panel = POERStatusPanel(
            self.poer_tab,
            on_refresh=self.refresh_poer_data,
            on_command=self.handle_poer_command,
        )
        self.poer_panel.pack(fill='x')
        self.device_tabs.select(self.lg_tab)
        self.after(250, self.refresh_poer_data)
    
    def create_status_bar(self):
        """Vytvoření status baru"""
        status_frame = ttk.LabelFrame(self.scrollable_frame, text="📌 Aktuální stav systému", padding=10)
        status_frame.pack(pady=10, padx=20, fill='x')

        # LG stav + LED
        lg_row = ttk.Frame(status_frame)
        lg_row.pack(fill='x')

        self.led_indicator = LEDIndicator(lg_row, size=16)
        self.led_indicator.pack(side=tk.LEFT, padx=(0, 10))

        self.live_state_label = ttk.Label(
            lg_row,
            textvariable=self.live_state_var,
            font=("Segoe UI", 10, "bold"),
            justify='left',
        )
        self.live_state_label.pack(side=tk.LEFT, anchor='w', fill='x', expand=True)
        lg_row.bind("<Configure>", self._on_top_row_resize)

        # POER stav + LED
        poer_row = ttk.Frame(status_frame)
        poer_row.pack(fill='x', pady=(4, 2))

        self.poer_led_indicator = LEDIndicator(poer_row, size=16)
        self.poer_led_indicator.pack(side=tk.LEFT, padx=(0, 10))

        self.poer_live_state_label = ttk.Label(
            poer_row,
            textvariable=self.poer_live_state_var,
            font=("Segoe UI", 10, "bold"),
            justify='left',
        )
        self.poer_live_state_label.pack(side=tk.LEFT, anchor='w', fill='x', expand=True)
        poer_row.bind("<Configure>", self._on_poer_row_resize)

        ttk.Label(
            status_frame,
            textvariable=self.auto_mode_var,
            font=("Segoe UI", 10, "bold"),
            justify='left',
        ).pack(anchor='w', fill='x', pady=(4, 6))

        status_row = ttk.Frame(status_frame)
        status_row.pack(fill='x')
        
        # Status text
        self.status_label = ttk.Label(
            status_row,
            textvariable=self.status_var,
            font=("Segoe UI", 10),
            justify='left',
        )
        self.status_label.pack(side=tk.LEFT, fill='x', expand=True, anchor='w')
        status_row.bind("<Configure>", self._on_status_row_resize)

        actions_row = ttk.Frame(status_frame)
        actions_row.pack(fill='x', pady=(6, 0))
        
        # Tlačítko manuální aktualizace
        refresh_btn = ttk.Button(actions_row, text="🔄 Aktualizovat", command=self.manual_refresh)
        refresh_btn.pack(side=tk.RIGHT, padx=(0, 2))
        
        # Přepínače režimů
        self.stop_schedule_btn = ttk.Button(
            actions_row,
            text="🖐️ HAND režim",
            command=self.stop_active_schedule,
            state='normal',
        )
        self.stop_schedule_btn.pack(side=tk.RIGHT, padx=(0, 2))

        self.resume_automation_btn = ttk.Button(
            actions_row,
            text="🤖 AUTO režim",
            command=self.resume_automatic_mode,
            state='normal',
        )
        self.resume_automation_btn.pack(side=tk.RIGHT, padx=(0, 2))

    def _on_top_row_resize(self, event):
        """Nastavi wraplength pro horni zivy stav podle aktualni sirky."""
        if hasattr(self, 'live_state_label') and self.live_state_label:
            self.live_state_label.configure(wraplength=max(320, int(event.width) - 70))

    def _on_poer_row_resize(self, event):
        """Nastavi wraplength pro POER radek v hornim stavu."""
        if hasattr(self, 'poer_live_state_label') and self.poer_live_state_label:
            self.poer_live_state_label.configure(wraplength=max(320, int(event.width) - 70))

    def _on_status_row_resize(self, event):
        """Nastavi wraplength pro stavovy text, aby se neschovaval za tlacitka."""
        if hasattr(self, 'status_label') and self.status_label:
            self.status_label.configure(wraplength=max(320, int(event.width) - 20))

    def _update_live_state_header(self, device_status):
        """Sestaví horní souhrn aktuálního stavu LG klimatizace.

        Args:
            device_status: Snapshot stavu zařízení.
        """

        if not isinstance(device_status, dict):
            self.live_state_var.set("LG: stav nedostupný")
            return

        power_mode = str(
            device_status.get("operation", {}).get("airConOperationMode", "POWER_OFF")
        ).upper()
        run_state = str(device_status.get("runState", {}).get("currentState", "UNKNOWN")).upper()
        mode = str(device_status.get("airConJobMode", {}).get("currentJobMode", "-")).upper()
        target_temp = device_status.get("temperature", {}).get("targetTemperature")

        raw_temp_c = None
        weather_cfg = self.automation_rules.weather
        thermostat_temp_c = weather_cfg.indoor_current_temperature_c
        poer_indoor_temp_c = getattr(self, "poer_indoor_temperature_c", None)
        poer_target_temp_c = getattr(self, "poer_target_temperature_c", None)
        try:
            raw_temp_c = float(device_status.get("temperature", {}).get("currentTemperature"))
        except (TypeError, ValueError):
            raw_temp_c = None

        estimated_indoor_temp_c = None
        if weather_cfg.indoor_current_temperature_source == "poer_api" and poer_indoor_temp_c is not None:
            estimated_indoor_temp_c = float(poer_indoor_temp_c)
            sensor_prefix = "teplota z termostatu POER"
        elif thermostat_temp_c is not None:
            estimated_indoor_temp_c = float(thermostat_temp_c)
            sensor_prefix = "teplota z termostatu"
        else:
            sensor_prefix = "odhad interieru z AC"
            if raw_temp_c is not None:
                estimated_indoor_temp_c = (
                    raw_temp_c
                    + float(weather_cfg.ac_indoor_temperature_proxy_offset_c)
                )

        if power_mode == "POWER_ON" and run_state == "NORMAL":
            state_text = "Zapnuto"
        elif power_mode == "POWER_OFF":
            state_text = "Vypnuto"
        else:
            state_text = f"{power_mode}/{run_state}"

        target_text = f"{target_temp}°C" if target_temp is not None else "?"
        poer_target_text = f"{poer_target_temp_c:.1f}°C" if poer_target_temp_c is not None else "?"
        ac_sensor_text = f"{raw_temp_c:.1f}°C" if raw_temp_c is not None else "?"
        if raw_temp_c is None:
            if estimated_indoor_temp_c is not None:
                sensor_text = f"{sensor_prefix}: {estimated_indoor_temp_c:.1f}°C"
            else:
                sensor_text = f"{sensor_prefix}: nedostupna"
        else:
            sensor_text = f"{sensor_prefix}: {estimated_indoor_temp_c:.1f}°C"

        self.live_state_var.set(
            f"LG: {state_text} | Režim: {mode} | AC čidlo: {ac_sensor_text} | "
            f"Cíl AC: {target_text} | {sensor_text} | Cíl POER: {poer_target_text}"
        )

    def _update_poer_live_state_header(self):
        """Sestavi horni zivy stav POER a aktualizuje POER LED indikator."""
        poer_error = getattr(self, "poer_error", None)
        poer_temp = getattr(self, "poer_indoor_temperature_c", None)
        poer_target = getattr(self, "poer_target_temperature_c", None)
        poer_humidity = getattr(self, "poer_current_humidity_pct", None)
        poer_mode = str(getattr(self, "poer_hvac_mode", "") or "").lower()

        poer_temp_text = f"{float(poer_temp):.1f}°C" if poer_temp is not None else "?"
        poer_target_text = f"{float(poer_target):.1f}°C" if poer_target is not None else "?"
        poer_humidity_text = f"{float(poer_humidity):.0f}%" if poer_humidity is not None else "?"

        if poer_error:
            self.poer_live_state_var.set(f"POER: chyba ({poer_error})")
            if hasattr(self, "poer_led_indicator"):
                self.poer_led_indicator.set_state("error")
            return

        if poer_mode == "off":
            poer_state = "Vypnuto"
            poer_led_state = "off"
        elif poer_temp is not None or poer_target is not None:
            poer_state = "Aktivní"
            poer_led_state = "on"
        else:
            poer_state = "Neznámý"
            poer_led_state = "error"

        self.poer_live_state_var.set(
            f"POER: {poer_state} | Režim: {str(poer_mode or '--').upper()} | "
            f"Aktuální: {poer_temp_text} | Cíl: {poer_target_text} | Vlhkost: {poer_humidity_text}"
        )
        if hasattr(self, "poer_led_indicator"):
            self.poer_led_indicator.set_state(poer_led_state)

    def create_automation_panel(self):
        """Vytvoří souhrnný panel LG, POER a automatizačního stavu."""
        summary_frame = ttk.LabelFrame(self.scrollable_frame, text="📊 Souhrn nastavení", padding=10)
        summary_frame.pack(pady=10, padx=10, fill='x')

        columns_frame = ttk.Frame(summary_frame)
        columns_frame.pack(fill='x')

        lg_summary_frame = ttk.LabelFrame(columns_frame, text="LG", padding=10)
        lg_summary_frame.pack(side=tk.LEFT, fill='both', expand=True, padx=(0, 6))

        poer_summary_frame = ttk.LabelFrame(columns_frame, text="POER", padding=10)
        poer_summary_frame.pack(side=tk.LEFT, fill='both', expand=True, padx=(6, 0))

        ttk.Label(
            lg_summary_frame,
            textvariable=self.status_var,
            justify='left',
            wraplength=320,
        ).pack(anchor='w', fill='x')

        ttk.Label(
            lg_summary_frame,
            textvariable=self.live_state_var,
            justify='left',
            wraplength=320,
        ).pack(anchor='w', fill='x', pady=(6, 0))

        ttk.Label(
            poer_summary_frame,
            textvariable=self.poer_summary_var,
            justify='left',
            wraplength=320,
        ).pack(anchor='w', fill='x')

        ttk.Label(
            summary_frame,
            textvariable=self.automation_info_var,
            justify='left',
            wraplength=680,
        ).pack(anchor='w', fill='x', pady=(10, 0))

        self._update_poer_summary()

    def _update_poer_summary(self):
        """Sestaví krátký souhrn stavu POER pro dashboard a tab."""
        poer_error = getattr(self, "poer_error", None)
        poer_temp = getattr(self, "poer_indoor_temperature_c", None)
        poer_humidity = getattr(self, "poer_current_humidity_pct", None)
        poer_target = getattr(self, "poer_target_temperature_c", None)
        poer_device_id = getattr(self, "poer_device_id", None)
        poer_mode = getattr(self, "poer_hvac_mode", None)
        poer_preset = getattr(self, "poer_preset_mode", None)
        poer_action = getattr(self, "poer_action", None)
        poer_min_temp = getattr(self, "poer_min_temp_c", None)
        poer_max_temp = getattr(self, "poer_max_temp_c", None)

        if poer_error:
            summary = f"POER: {poer_error}"
        else:
            temp_text = f"{float(poer_temp):.1f}°C" if poer_temp is not None else "nedostupná"
            target_text = f"{float(poer_target):.1f}°C" if poer_target is not None else "nedostupný"
            humidity_text = f"{float(poer_humidity):.1f}%" if poer_humidity is not None else "--"
            device_text = f"{poer_device_id[:8]}..." if poer_device_id else "nezjištěno"
            summary = (
                f"Aktuální teplota: {temp_text}\n"
                f"Cílová teplota: {target_text}\n"
                f"Vlhkost: {humidity_text}\n"
                f"Režim: {poer_mode or '--'} | Předvolba: {poer_preset or '--'} | Akce: {poer_action or '--'}\n"
                f"Rozsah: {poer_min_temp or '--'}-{poer_max_temp or '--'} °C\n"
                f"Zařízení: {device_text}"
            )

        self.poer_summary_var.set(summary)
        self._update_poer_live_state_header()

        if hasattr(self, "poer_panel"):
            self.poer_panel.update_status(
                current_temperature_c=poer_temp,
                current_humidity_pct=poer_humidity,
                target_temperature_c=poer_target,
                device_id=poer_device_id,
                mode=poer_mode,
                preset=poer_preset,
                action=poer_action,
                min_temp_c=poer_min_temp,
                max_temp_c=poer_max_temp,
                error_text=poer_error,
            )

    def create_weather_panel(self):
        """Vytvoří panel s vizualizací načtené předpovědi počasí."""
        self.weather_panel = WeatherForecastPanel(
            self.scrollable_frame,
            on_refresh=self._manual_weather_refresh,
        )
        self.weather_panel.pack(pady=10, padx=10, fill='x')
    
    def bind_mousewheel(self, canvas):
        """Bindování mouse wheel pro scrollování"""
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        def _bind_to_mousewheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        def _unbind_from_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        canvas.bind('<Enter>', _bind_to_mousewheel)
        canvas.bind('<Leave>', _unbind_from_mousewheel)
    
    async def initialize_api(self):
        """Inicializace API připojení"""
        if not self.api:
            self.api = ThinQAPI()
            await self.api.initialize()
        return self.api

    def on_closing(self):
        """Čištění při zavírání aplikace – čeká na uzavření MQTT a HTTP session."""
        self.schedule_check_active = False
        if self._status_refresh_after_id is not None:
            try:
                self.after_cancel(self._status_refresh_after_id)
            except Exception:
                pass
            self._status_refresh_after_id = None
        try:
            if self.api:
                # Zablokujeme hlavní vlákno max. 5s, aby close() stihl proběhnout
                # před zastavením event loopu (jinak vznikají „Task destroyed" chyby)
                future = asyncio.run_coroutine_threadsafe(self.api.close(), self.loop)
                future.result(timeout=5)
        except Exception as e:
            logger.warning(f"Chyba při zavírání API: {e}")
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.destroy()

def main():
    """Spuštění aplikace"""
    app = ClimateApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()

if __name__ == "__main__":
    main()
