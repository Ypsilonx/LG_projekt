"""
GUI aplikace pro ovládání LG klimatizace prostřednictvím ThinQ API.
Poskytuje moderní tmavé rozhraní s responzivními prvky a pokročilým plánováním.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import threading
import json
import logging
from datetime import datetime
from pathlib import Path
import sys

# Import modulů aplikace
sys.path.insert(0, str(Path(__file__).parent.parent))
from server_api import ThinQAPI
from klima_logic import create_control_payload
from gui.theme import setup_dark_theme
from gui.widgets import LEDIndicator
from gui.controls import ClimateControls, TimerControls, InfoPanel
from gui.scheduler import SchedulerWidget

# Nastavení logování
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEVICE_ID = "ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e"

class ClimateApp(tk.Tk):
    """Hlavní aplikace pro ovládání klimatizace"""
    
    def __init__(self):
        super().__init__()
        self.title("LG ThinQ Klimatizace – Ovládání & Plánování")
        self.geometry("650x800")
        self.resizable(True, True)
        self.minsize(500, 600)
        
        # Nastavení tmavého tématu
        setup_dark_theme(self)
        
        # Inicializace API a dat
        self.api = None
        self.device_profile = self.load_device_profile()
        self.last_device_status = None
        self.status_check_interval = 5000  # 5 sekund
        self.pending_update = False
        
        # Status variable pro globální stav
        self.status_var = tk.StringVar(value="Načítám stav zařízení...")
        
        # Inicializace event loop pro asynchronní operace
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        
        # Vytvoření GUI
        self.create_widgets()
        
        # Spuštění počáteční kontroly stavu
        self.after(100, self.initial_status_check)
        
        # Pravidelná kontrola stavu
        self.periodic_status_check()
        
    def load_device_profile(self):
        """Načtení profilu zařízení"""
        try:
            with open("data/device_profile.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Chyba při načítání profilu zařízení: {e}")
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
        
        # Plánovač (nová funkce)
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
        
        # Aktualizace scrollovatelné oblasti
        self.scrollable_frame.update_idletasks()
    
    def create_status_bar(self):
        """Vytvoření status baru"""
        status_frame = ttk.Frame(self.scrollable_frame)
        status_frame.pack(pady=10, padx=20, fill='x')
        
        # LED indikátor
        self.led_indicator = LEDIndicator(status_frame, size=16)
        self.led_indicator.pack(side=tk.LEFT, padx=(0, 10))
        
        # Status text
        status_label = ttk.Label(status_frame, textvariable=self.status_var, font=("Segoe UI", 10))
        status_label.pack(side=tk.LEFT, expand=True, anchor='w')
        
        # Tlačítko manuální aktualizace
        refresh_btn = ttk.Button(status_frame, text="🔄 Aktualizovat", command=self.manual_refresh)
        refresh_btn.pack(side=tk.RIGHT)
    
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
    
    def handle_device_command(self, command, *args):
        """Zpracování příkazů z GUI komponent"""
        logger.info(f"Příkaz zařízení: {command}, parametry: {args}")
        
        # Spuštění asynchronního příkazu
        future = asyncio.run_coroutine_threadsafe(
            self._execute_device_command(command, *args),
            self.loop
        )
        
        def handle_result():
            try:
                future.result(timeout=10)  # Čekání max 10 sekund
            except Exception as e:
                logger.error(f"Chyba při provádění příkazu {command}: {e}")
                error_msg = str(e)
                self.after(0, lambda msg=error_msg: messagebox.showerror("Chyba", f"Příkaz {command} selhal: {msg}"))
        
        threading.Thread(target=handle_result, daemon=True).start()
    
    async def _execute_device_command(self, command, *args):
        """Asynchronní provádění příkazů zařízení"""
        try:
            api = await self.initialize_api()
            
            if command == "toggle_power":
                # Nejprve získáme aktuální stav
                status = await api.get_device_status(DEVICE_ID)
                
                # Podle device_profile.json: operation.airConOperationMode pro power stav
                current_power = status.get("operation", {}).get("airConOperationMode", "POWER_OFF")
                
                # Pokud je vypnuté, zapneme. Pokud je zapnuté, vypneme
                if current_power == "POWER_OFF":
                    new_state = "POWER_ON"
                else:  # POWER_ON
                    new_state = "POWER_OFF"
                    
                payload = create_control_payload("power", new_state)
                logger.info(f"Toggle power: {current_power} -> {new_state}")
                
            elif command == "change_mode":
                mode = args[0]
                payload = create_control_payload("mode", mode)
                
            elif command == "set_temperature":
                temperature, mode = args[0], args[1] if len(args) > 1 else None
                payload = create_control_payload("temperature", temperature, mode)
                
            elif command == "set_wind_strength":
                wind_strength = args[0]
                payload = create_control_payload("wind_strength", wind_strength)
                
            elif command == "set_wind_direction":
                updown, leftright = args[0], args[1]
                payload = create_control_payload("wind_direction", updown, leftright)
                
            elif command == "set_power_save":
                enabled = args[0]
                payload = create_control_payload("power_save", enabled)
                
            elif command == "set_sleep_timer":
                hours, minutes = args[0], args[1]
                payload = create_control_payload("sleep_timer", hours, minutes)
                
            elif command == "cancel_all_timers":
                payload = create_control_payload("cancel_timers")
                
            else:
                logger.warning(f"Neznámý příkaz: {command}")
                return
            
            # Odeslání příkazu
            result = await api.send_device_command(DEVICE_ID, payload)
            logger.info(f"Příkaz {command} úspěšně odeslán: {result}")
            
            # Rychlá aktualizace stavu (po 1 sekundě)
            self.after(1000, lambda: asyncio.run_coroutine_threadsafe(
                self.update_device_status(), self.loop
            ))
            
        except Exception as e:
            logger.error(f"Chyba při provádění příkazu {command}: {e}")
            raise
    
    def execute_scheduled_command(self, schedule_entry):
        """Provádění naplánovaného příkazu"""
        logger.info(f"Provádím naplánovaný příkaz: {schedule_entry}")
        
        # Konverze schedule_entry na příkazy zařízení
        if schedule_entry.power_on:
            self.handle_device_command("toggle_power")
        
        if schedule_entry.mode:
            self.handle_device_command("change_mode", schedule_entry.mode)
        
        if schedule_entry.temperature:
            self.handle_device_command("set_temperature", schedule_entry.temperature, schedule_entry.mode)
        
        if schedule_entry.wind_strength:
            self.handle_device_command("set_wind_strength", schedule_entry.wind_strength)
        
        # Wind direction
        if hasattr(schedule_entry, 'wind_updown') or hasattr(schedule_entry, 'wind_leftright'):
            updown = getattr(schedule_entry, 'wind_updown', False)
            leftright = getattr(schedule_entry, 'wind_leftright', False)
            self.handle_device_command("set_wind_direction", updown, leftright)
    
    def on_schedule_change(self, schedule_entries):
        """Callback volaný při změně plánu"""
        logger.info(f"Plán aktualizován: {len(schedule_entries)} položek")
        # Zde můžeme implementovat logiku pro spuštění/zastavení plánovače
        # např. aktualizaci background task pro monitoring času
    
    async def update_device_status(self):
        """Aktualizace stavu zařízení"""
        try:
            api = await self.initialize_api()
            status = await api.get_device_status(DEVICE_ID)
            
            # Kontrola změn ve stavu
            if status != self.last_device_status:
                self.last_device_status = status
                
                # Aktualizace GUI v hlavním vlákně
                self.after(0, lambda: self._update_gui_status(status))
                
                logger.info("Stav zařízení aktualizován")
            
        except Exception as e:
            logger.error(f"Chyba při aktualizaci stavu: {e}")
            self.after(0, lambda: self.status_var.set(f"Chyba: {e}"))
            self.after(0, lambda: self.led_indicator.set_state("error"))
    
    def _update_gui_status(self, device_status):
        """Aktualizace GUI podle stavu zařízení (hlavní vlákno)"""
        try:
            # Aktualizace status baru - kombinace runState a operation
            run_state = device_status.get("runState", {}).get("currentState", "UNKNOWN")
            power_operation = device_status.get("operation", {}).get("airConOperationMode", "POWER_OFF")
            mode = device_status.get("airConJobMode", {}).get("currentJobMode", "N/A")
            temp = device_status.get("temperature", {}).get("currentTemperature", "?")
            
            # Kombinace stavů pro display
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
            
            status_text = f"Stav: {display_state}, Režim: {mode}, Teplota: {temp}°C"
            self.status_var.set(status_text)
            
            # LED indikátor
            logger.info(f"Aktualizuji LED: power={power_operation}, run={run_state} -> {led_state}")
            self.led_indicator.set_state(led_state)
            
            # Aktualizace všech komponent
            if hasattr(self, 'climate_controls'):
                self.climate_controls.update_status(device_status)
            
            if hasattr(self, 'timer_controls'):
                self.timer_controls.update_status(device_status)
            
            if hasattr(self, 'info_panel'):
                self.info_panel.update_status(device_status)
                
        except Exception as e:
            logger.error(f"Chyba při aktualizaci GUI: {e}")
            self.status_var.set(f"Chyba GUI: {e}")
    
    def initial_status_check(self):
        """Počáteční kontrola stavu"""
        asyncio.run_coroutine_threadsafe(self.update_device_status(), self.loop)
    
    def periodic_status_check(self):
        """Pravidelná kontrola stavu"""
        if not self.pending_update:
            self.pending_update = True
            asyncio.run_coroutine_threadsafe(self.update_device_status(), self.loop)
            self.after(500, lambda: setattr(self, 'pending_update', False))
        
        # Plánování další kontroly
        self.after(self.status_check_interval, self.periodic_status_check)
    
    def manual_refresh(self):
        """Manuální obnovení stavu"""
        self.status_var.set("Aktualizuji...")
        asyncio.run_coroutine_threadsafe(self.update_device_status(), self.loop)
    
    def on_closing(self):
        """Čištění při zavírání aplikace"""
        try:
            if self.api:
                asyncio.run_coroutine_threadsafe(self.api.close(), self.loop)
            self.loop.call_soon_threadsafe(self.loop.stop)
        except:
            pass
        finally:
            self.destroy()

def main():
    """Spuštění aplikace"""
    app = ClimateApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()

if __name__ == "__main__":
    main()
