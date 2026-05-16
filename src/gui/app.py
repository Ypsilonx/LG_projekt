# -*- coding: utf-8 -*-
"""
GUI aplikace pro ovládání LG klimatizace prostřednictvím ThinQ API.
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
from gui.controls import ClimateControls, TimerControls, InfoPanel
from gui.scheduler import SchedulerWidget
from gui.automation_energy_mixin import AutomationEnergyMixin
from gui.mode_scheduler_mixin import ModeSchedulerMixin
from gui.device_runtime_mixin import DeviceRuntimeMixin

# Nastavení logování
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ClimateApp(DeviceRuntimeMixin, ModeSchedulerMixin, AutomationEnergyMixin, tk.Tk):
    """Hlavní aplikace pro ovládání klimatizace"""
    
    def __init__(self):
        super().__init__()
        self.title("LG ThinQ Klimatizace – Ovládání & Plánování")
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
        self.live_state_var = tk.StringVar(value="Klimatizace: načítám stav")
        self.auto_mode_var = tk.StringVar(value="🤖 AUTO mód: inicializace")
        self.automation_info_var = tk.StringVar(value="Načítám pravidla automatizace...")
        self._last_automation_note = None
        self.weather_snapshot = None
        self.weather_last_refresh_at = None
        self.weather_last_attempt_at = None
        self.weather_last_error = None
        self.weather_refresh_in_progress = False
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
        self.create_automation_panel()
        
        # Hlavní ovládací prvky klimatizace
        if self.device_profile:
            self.climate_controls = ClimateControls(
                self.scrollable_frame, 
                self.device_profile, 
                self.status_var,
                on_command=self.handle_device_command
            )
            self.climate_controls.pack(pady=10, padx=10, fill='x')
        
        # Časovače
        self.timer_controls = TimerControls(
            self.scrollable_frame,
            on_command=self.handle_device_command
        )
        self.timer_controls.pack(pady=10, padx=10, fill='x')
        
        # Informační panel
        self.info_panel = InfoPanel(self.scrollable_frame)
        self.info_panel.pack(pady=10, padx=10, fill='x')
        self._info_panel_visible = True

        # Panel spotřeby energie
        self.energy_panel = EnergyPanel(
            self.scrollable_frame,
            on_refresh=self.refresh_energy_data,
            on_export=self.export_energy_data,
        )
        self.energy_panel.pack(pady=10, padx=10, fill='x')

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

        self._apply_mode_visibility()
        self._update_mode_buttons()
        self._refresh_automation_summary()
        self.after(400, lambda: self.refresh_energy_data("weekly"))
        
        # Aktualizace scrollovatelné oblasti
        self.scrollable_frame.update_idletasks()
    
    def create_status_bar(self):
        """Vytvoření status baru"""
        status_frame = ttk.LabelFrame(self.scrollable_frame, text="📌 Aktuální stav", padding=10)
        status_frame.pack(pady=10, padx=20, fill='x')
        
        # LED indikátor
        top_row = ttk.Frame(status_frame)
        top_row.pack(fill='x')

        self.led_indicator = LEDIndicator(top_row, size=16)
        self.led_indicator.pack(side=tk.LEFT, padx=(0, 10))

        self.live_state_label = ttk.Label(
            top_row,
            textvariable=self.live_state_var,
            font=("Segoe UI", 10, "bold"),
            justify='left',
        )
        self.live_state_label.pack(side=tk.LEFT, anchor='w', fill='x', expand=True)
        top_row.bind("<Configure>", self._on_top_row_resize)

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

    def _on_status_row_resize(self, event):
        """Nastavi wraplength pro stavovy text, aby se neschovaval za tlacitka."""
        if hasattr(self, 'status_label') and self.status_label:
            self.status_label.configure(wraplength=max(320, int(event.width) - 20))

    def _update_live_state_header(self, device_status):
        """Sestaví horní souhrn aktuálního stavu klimatizace.

        Args:
            device_status: Snapshot stavu zařízení.
        """

        if not isinstance(device_status, dict):
            self.live_state_var.set("Klimatizace: stav nedostupný")
            return

        power_mode = str(
            device_status.get("operation", {}).get("airConOperationMode", "POWER_OFF")
        ).upper()
        run_state = str(device_status.get("runState", {}).get("currentState", "UNKNOWN")).upper()
        mode = str(device_status.get("airConJobMode", {}).get("currentJobMode", "-")).upper()
        target_temp = device_status.get("temperature", {}).get("targetTemperature")

        raw_temp_c = None
        try:
            raw_temp_c = float(device_status.get("temperature", {}).get("currentTemperature"))
        except (TypeError, ValueError):
            raw_temp_c = None
        corrected_temp_c = None
        if raw_temp_c is not None:
            corrected_temp_c = raw_temp_c + float(self.automation_rules.weather.sensor_offset_c)

        if power_mode == "POWER_ON" and run_state == "NORMAL":
            state_text = "Zapnuto"
        elif power_mode == "POWER_OFF":
            state_text = "Vypnuto"
        else:
            state_text = f"{power_mode}/{run_state}"

        target_text = f"{target_temp}°C" if target_temp is not None else "?"
        if raw_temp_c is None:
            sensor_text = "teplota s offsetem: nedostupna"
        else:
            sensor_text = f"teplota s offsetem: {corrected_temp_c:.1f}°C"

        self.live_state_var.set(
            f"Klimatizace: {state_text} | Režim: {mode} | Cíl: {target_text} | {sensor_text}"
        )

    def create_automation_panel(self):
        """Vytvoreni panelu pro prehled sezonnich pravidel a stavu AUTO/HAND."""
        automation_frame = ttk.LabelFrame(self.scrollable_frame, text="🤖 Automatizace", padding=10)
        automation_frame.pack(pady=10, padx=10, fill='x')

        ttk.Label(
            automation_frame,
            textvariable=self.automation_info_var,
            justify='left',
            wraplength=580,
        ).pack(anchor='w', fill='x')

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
