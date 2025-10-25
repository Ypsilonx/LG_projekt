# -*- coding: utf-8 -*-
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
from server_api import ThinQAPI, send_device_command
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
        
        # Pravidelná kontrola plánů (každou minutu)
        self.schedule_check_active = True
        self.last_executed_schedule = None
        self.manual_schedule_override = False  # Příznak pro manuální přerušení plánu
        self.schedule_was_active_last_check = False  # Pro detekci konce plánu
        self.periodic_schedule_check()
        
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
        refresh_btn.pack(side=tk.RIGHT, padx=(0, 2))
        
        # Tlačítko pro přerušení aktivního plánu
        self.stop_schedule_btn = ttk.Button(status_frame, text="⏹️ Stop plán", 
                                          command=self.stop_active_schedule, state='disabled')
        self.stop_schedule_btn.pack(side=tk.RIGHT)
    
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
            
            elif command == "power_on":
                # NOVÝ: Vždy zajistit zapnutí (nemusíme kontrolovat stav)
                payload = create_control_payload("power", "POWER_ON")
                logger.info(f"Power ON příkaz")
            
            elif command == "power_off":
                # NOVÝ: Vždy zajistit vypnutí
                payload = create_control_payload("power", "POWER_OFF")
                logger.info(f"Power OFF příkaz")
                
            elif command == "change_mode":
                mode = args[0]
                payload = create_control_payload("mode", mode)
                
            elif command == "set_temperature":
                temperature = args[0]
                # OPRAVA: Pouze teplota bez režimu (fungující řešení)
                payload = create_control_payload("temperature", temperature)
                
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
            
            # Pro nastavení teploty čekáme delší dobu na aktualizaci
            if command == "set_temperature":
                self.after(3000, lambda: asyncio.run_coroutine_threadsafe(
                    self.update_device_status(), self.loop
                ))
                logger.info("Naplánována aktualizace stavu za 3 sekundy pro temperature")
            else:
                # Rychlá aktualizace stavu (po 1 sekundě)
                self.after(1000, lambda: asyncio.run_coroutine_threadsafe(
                    self.update_device_status(), self.loop
                ))
            
        except Exception as e:
            logger.error(f"Chyba při provádění příkazu {command}: {e}")
            raise

    def stop_active_schedule(self):
        """Zastavení aktivního plánu"""
        try:
            if self.last_executed_schedule:
                logger.info(f"🛑 Uživatel přerušil aktivní plán: {self.last_executed_schedule.name}")
                self.manual_schedule_override = True
                self.schedule_was_active_last_check = False  # Reset tracking
                self.last_executed_schedule = None
                self.status_var.set("Aktivní plán byl přerušen")
                self.stop_schedule_btn.config(state='disabled')
                
                # Resetuj override za 30 sekund
                self.after(30000, lambda: setattr(self, 'manual_schedule_override', False))
            else:
                self.status_var.set("Žádný aktivní plán k přerušení")
                
        except Exception as e:
            logger.error(f"Chyba při zastavování plánu: {e}")
            self.status_var.set(f"Chyba: {e}")

    def execute_scheduled_command(self, schedule_entry):
        """Provádění naplánovaného příkazu"""
        logger.info(f"🎯 Provádím naplánovaný příkaz: {schedule_entry.name}")
        
        try:
            # Nejdříve zapnout zařízení (pokud je potřeba)
            if schedule_entry.power_on:
                logger.info("  ↳ Kontroluji stav a zapínám zařízení pokud je vypnuto")
                # OPRAVA: Místo toggle_power použijeme power_on pro zajištění zapnutí
                self.handle_device_command("power_on")
                
                # Počkat 3 sekundy, aby se zařízení zapnulo
                def continue_after_power_on():
                    try:
                        # Pak nastavit ostatní parametry
                        if schedule_entry.mode:
                            logger.info(f"  ↳ Nastavuji režim: {schedule_entry.mode}")
                            self.handle_device_command("change_mode", schedule_entry.mode)
                        
                        # Další pauza před dalšími příkazy
                        def set_remaining_params():
                            try:
                                if schedule_entry.temperature and schedule_entry.mode != "FAN":
                                    logger.info(f"  ↳ Nastavuji teplotu: {schedule_entry.temperature}°C")
                                    # OPRAVA: Odesíláme pouze teplotu bez režimu (fungující řešení)
                                    self.handle_device_command("set_temperature", schedule_entry.temperature)
                                
                                # Další pauza před větrákem
                                def set_wind_after_temp():
                                    if schedule_entry.wind:
                                        logger.info(f"  ↳ Nastavuji sílu větráku: {schedule_entry.wind}")
                                        self.handle_device_command("set_wind_strength", schedule_entry.wind)
                                    
                                    logger.info(f"✅ Plán '{schedule_entry.name}' byl úspěšně proveden")
                                    self.status_var.set(f"Plán '{schedule_entry.name}' dokončen")
                                
                                # Počkat 2 sekundy mezi teplotou a větrem
                                if schedule_entry.wind:
                                    self.after(2000, set_wind_after_temp)
                                else:
                                    logger.info(f"✅ Plán '{schedule_entry.name}' byl úspěšně proveden")
                                    self.status_var.set(f"Plán '{schedule_entry.name}' dokončen")
                                
                            except Exception as e:
                                logger.error(f"❌ Chyba při nastavování parametrů plánu '{schedule_entry.name}': {e}")
                                self.status_var.set(f"Chyba při nastavování: {e}")
                        
                        # Počkat dalších 3 sekund před nastavením teploty (místo 2)
                        self.after(3000, set_remaining_params)
                        
                    except Exception as e:
                        logger.error(f"❌ Chyba při nastavování režimu plánu '{schedule_entry.name}': {e}")
                        self.status_var.set(f"Chyba při nastavování režimu: {e}")
                
                # Počkat 3 sekundy po zapnutí
                self.after(3000, continue_after_power_on)
                
            else:
                # Pokud se nezapíná, nastavit parametry postupně s pauzami
                if schedule_entry.mode:
                    logger.info(f"  ↳ Nastavuji režim: {schedule_entry.mode}")
                    self.handle_device_command("change_mode", schedule_entry.mode)
                
                def set_temp_after_mode():
                    if schedule_entry.temperature and schedule_entry.mode != "FAN":
                        logger.info(f"  ↳ Nastavuji teplotu: {schedule_entry.temperature}°C")
                        # OPRAVA: Odesíláme pouze teplotu bez režimu (fungující řešení)
                        self.handle_device_command("set_temperature", schedule_entry.temperature)
                    
                    def set_wind_after_temp():
                        if schedule_entry.wind:
                            logger.info(f"  ↳ Nastavuji sílu větráku: {schedule_entry.wind}")
                            self.handle_device_command("set_wind_strength", schedule_entry.wind)
                        
                        logger.info(f"✅ Plán '{schedule_entry.name}' byl úspěšně proveden")
                    
                    # Pauza před větrákem
                    if schedule_entry.wind:
                        self.after(2000, set_wind_after_temp)
                    else:
                        logger.info(f"✅ Plán '{schedule_entry.name}' byl úspěšně proveden")
                
                # Pauza po změně režimu před teplotou
                if schedule_entry.mode and (schedule_entry.temperature or schedule_entry.wind):
                    self.after(3000, set_temp_after_mode)
                elif not schedule_entry.mode:
                    # Pokud se nemění režim, spustíme hned
                    set_temp_after_mode()
                else:
                    logger.info(f"✅ Plán '{schedule_entry.name}' byl úspěšně proveden")
            
        except Exception as e:
            logger.error(f"❌ Chyba při provádění plánu '{schedule_entry.name}': {e}")
            self.status_var.set(f"Chyba při provádění plánu: {e}")
    
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

    async def manual_update_device_status(self):
        """Speciální verze update_device_status pro manual refresh - vždycky aktualizuje GUI"""
        try:
            api = await self.initialize_api()
            status = await api.get_device_status(DEVICE_ID)
            
            # Při manual refresh VŽDYCKY aktualizujeme GUI, i když se stav nezměnil
            self.last_device_status = status
            
            # Aktualizace GUI v hlavním vlákně
            self.after(0, lambda: self._update_gui_status(status))
            
            logger.info("Manual refresh: Stav zařízení aktualizován")
            
        except Exception as e:
            logger.error(f"Chyba při manual refresh: {e}")
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

    def periodic_schedule_check(self):
        """Pravidelná kontrola plánů pro automatické spouštění"""
        if not self.schedule_check_active:
            return
            
        try:
            from datetime import datetime
            current_time = datetime.now()
            
            # Zkontroluj, jestli existuje aktivní plán pro aktuální čas
            if hasattr(self, 'scheduler_widget') and self.scheduler_widget:
                active_schedule = self.scheduler_widget.get_active_schedule_for_time(current_time)
                
                if active_schedule and not self.manual_schedule_override:
                    # AKTIVNÍ PLÁN
                    self.schedule_was_active_last_check = True
                    
                    # Aktualizace tlačítka Stop plán - povolit
                    self.after(0, lambda: self.stop_schedule_btn.config(state='normal'))
                    
                    if active_schedule != self.last_executed_schedule:
                        # Nový plán k provedení
                        current_minute = current_time.strftime("%H:%M")
                        schedule_start = active_schedule.start_time
                        
                        # Spustit jen pokud jsme přesně na začátku plánovaného času (±1 minuta)
                        # NEBO pokud je plán aktivní a ještě nebyl spuštěn (restart aplikace během plánu)
                        if (current_minute == schedule_start or 
                            (self.last_executed_schedule is None and active_schedule.enabled)):
                            
                            logger.info(f"🕒 Spouštím naplánovaný příkaz: {active_schedule.name} v {schedule_start}")
                            self.execute_scheduled_command(active_schedule)
                            self.last_executed_schedule = active_schedule
                            
                    # Aktualizace status baru s aktivním plánem
                    remaining_time = self._calculate_remaining_time(active_schedule, current_time)
                    if remaining_time:
                        self.after(0, lambda: self.status_var.set(
                            f"🏃 Aktivní: {active_schedule.name} (zbývá {remaining_time})"
                        ))
                        
                else:
                    # ŽÁDNÝ AKTIVNÍ PLÁN
                    self.after(0, lambda: self.stop_schedule_btn.config(state='disabled'))
                    
                    # Detekce konce plánu - pokud předtím byl aktivní a teď není
                    if self.schedule_was_active_last_check and self.last_executed_schedule and not self.manual_schedule_override:
                        # Zkontroluj, jestli má plán vypnout zařízení na konci
                        if getattr(self.last_executed_schedule, 'power_off_at_end', True):
                            logger.info(f"🔚 Plán '{self.last_executed_schedule.name}' skončil - vypínám zařízení")
                            self.handle_device_command("power_off")  # OPRAVA: Použít power_off místo toggle
                            self.status_var.set(f"Plán '{self.last_executed_schedule.name}' dokončen - zařízení vypnuto")
                        else:
                            logger.info(f"🔚 Plán '{self.last_executed_schedule.name}' skončil - zařízení zůstává zapnuté")
                            self.status_var.set(f"Plán '{self.last_executed_schedule.name}' dokončen - zařízení běží")
                    
                    self.schedule_was_active_last_check = False
                    
                    if not active_schedule:
                        self.last_executed_schedule = None
                        
                    # Najdi nejbližší plán
                    next_schedule, time_to_next = self._find_next_schedule(current_time)
                    if next_schedule and time_to_next:
                        # Updatej status pouze pokud není jiný text
                        current_status = self.status_var.get()
                        if (not current_status.startswith("🏃") and not current_status.startswith("Chyba") 
                            and not current_status.startswith("Aktivní plán byl přerušen")
                            and not current_status.startswith("Plán ") and "dokončen" not in current_status):
                            self.after(0, lambda: self.status_var.set(
                                f"⏰ Další: {next_schedule.name} za {time_to_next}"
                            ))
                    
        except Exception as e:
            logger.error(f"Chyba při kontrole plánů: {e}")
        
        # Naplánuj další kontrolu za 30 sekund
        if self.schedule_check_active:
            self.after(30000, self.periodic_schedule_check)  # 30 sekund
    
    def _calculate_remaining_time(self, schedule_entry, current_time):
        """Výpočet zbývajícího času aktivního plánu"""
        try:
            from datetime import datetime, time
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
                else:
                    return f"{minutes}min"
        except:
            pass
        return None
    
    def _find_next_schedule(self, current_time):
        """Najde nejbližší nadcházející plán"""
        try:
            if not hasattr(self, 'scheduler_widget') or not self.scheduler_widget:
                return None, None
                
            from datetime import datetime, timedelta
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
                            
                except:
                    continue
            
            if closest_schedule and closest_minutes < float('inf'):
                hours = closest_minutes // 60
                minutes = closest_minutes % 60
                if hours > 24:
                    return closest_schedule, f"{hours//24}d {hours%24}h"
                elif hours > 0:
                    return closest_schedule, f"{hours}h {minutes}min"
                else:
                    return closest_schedule, f"{minutes}min"
                    
        except Exception as e:
            logger.error(f"Chyba při hledání nejbližšího plánu: {e}")
            
        return None, None
    
    def manual_refresh(self):
        """Manuální obnovení stavu"""
        try:
            logger.info("🔄 Manuální refresh - START")
            self.status_var.set("Aktualizuji...")
            self.led_indicator.set_state("error")  # Oranžová při načítání
            
            # Spustíme async update a čekáme na výsledek
            future = asyncio.run_coroutine_threadsafe(self.manual_update_device_status(), self.loop)
            
            # Počkáme chvilku a zkontrolujeme stav
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
                            # Nebudeme nastavovat success, necháme LED odrážet skutečný stav zařízení
                            # LED se aktualizuje automaticky v _update_gui_status
                    else:
                        # Pokud ještě nedoběhl, zkusíme znovu za 500ms
                        self.after(500, check_result)
                except Exception as e:
                    logger.error(f"❌ Check result error: {e}")
                    self.status_var.set(f"Chyba: {e}")
                    self.led_indicator.set_state("error")
            
            # Zkontrolujeme výsledek za 1s
            self.after(1000, check_result)
            
            logger.info("Manuální refresh spuštěn")
        except Exception as e:
            logger.error(f"Chyba při manuálním refresh: {e}")
            self.status_var.set(f"Chyba refresh: {e}")
            self.led_indicator.set_state("error")
    
    def on_closing(self):
        """Čištění při zavírání aplikace"""
        try:
            # Zastavíme kontrolu plánů
            self.schedule_check_active = False
            
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
