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

DEVICE_ID = "ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e"

# ...další importy a utility...

def get_profile():
    with open("data/device_profile.json", encoding="utf-8") as f:
        return json.load(f)

# ...další utility pro získání parametrů...

class KlimaApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("LG Klimatizace – Ovládání")
        self.geometry("500x600")  # Větší výchozí velikost
        self.resizable(True, True)  # Povolení resize
        self.minsize(400, 500)  # Minimální velikost
        
        # Nastavení tmavého tématu
        set_dark_theme(self)
        
        # Inicializace proměnných
        self.status_var = tk.StringVar(value="Načítám stav...")
        self.last_device_status = None  # Cache posledního stavu
        self.status_check_interval = 5000  # Interval kontroly (5 sekund)
        self.pending_update = False  # Flag pro čekající aktualizaci
        
        # Inicializace event loop pro asynchronní operace
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        
        # Vytvoření GUI
        self.create_widgets()
        
        # Spuštění počáteční kontroly stavu a pak periodické kontroly
        self.after(100, self.initial_status_check)
        
    def create_widgets(self):
        # Hlavní scrollovatelný frame pro responzivitu
        main_canvas = tk.Canvas(self, bg="#222222", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=main_canvas.yview)
        self.scrollable_frame = ttk.Frame(main_canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        main_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        # Packing hlavních elementů
        main_canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y")
        
        # Widget pro centrování obsahu
        content_frame = ttk.Frame(self.scrollable_frame)
        content_frame.pack(expand=True, fill="both")
        
        # LED indikátor stavu
        self.led_indicator = LedIndicator(content_frame)
        self.led_indicator.pack(pady=15)

        # Stav zařízení
        self.status_label = ttk.Label(content_frame, textvariable=self.status_var, font=("Segoe UI", 12, "bold"))
        self.status_label.pack(pady=10)

        # Separator
        separator1 = ttk.Frame(content_frame, height=2)
        separator1.pack(fill='x', padx=20, pady=10)

        # Tlačítko zapnutí/vypnutí
        self.toggle_btn = ttk.Button(content_frame, text="⚡ Zapnout/Vypnout", command=self.toggle_power)
        self.toggle_btn.pack(pady=10)

        # Výběr módu
        self.profile = get_profile()
        self.modes = self.profile["property"]["airConJobMode"]["currentJobMode"]["value"]["w"]
        self.mode_var = tk.StringVar(value=self.modes[0])
        
        mode_frame = ttk.LabelFrame(content_frame, text="🌡️ Režim klimatizace", padding=10)
        mode_frame.pack(pady=10, padx=20, fill='x')
        
        self.mode_combo = ttk.Combobox(mode_frame, values=self.modes, textvariable=self.mode_var, 
                                      state="readonly", width=15, font=("Segoe UI", 10))
        self.mode_combo.pack(side=tk.LEFT, padx=5)
        self.mode_combo.bind("<<ComboboxSelected>>", self.on_mode_change)
        
        self.mode_btn = ttk.Button(mode_frame, text="Změnit", command=self.change_mode)
        self.mode_btn.pack(side=tk.LEFT, padx=5)

        # Teplota (dynamicky zobrazovaná podle módu)
        self.temp_frame = ttk.LabelFrame(content_frame, text="🌡️ Teplota", padding=10)
        self.temp_frame.pack(pady=10, padx=20, fill='x')
        
        self.temp_var = tk.DoubleVar(value=22)
        
        # Aktuální teplota (vždy zobrazená)
        self.current_temp_label = ttk.Label(self.temp_frame, text="Aktuální: --°C", font=("Segoe UI", 10, "bold"))
        self.current_temp_label.pack(pady=5)
        
        # Cílová teplota (skrytá v módu FAN)
        self.target_temp_frame = ttk.Frame(self.temp_frame)
        self.target_temp_frame.pack(fill='x', pady=5)
        
        self.temp_label = ttk.Label(self.target_temp_frame, text="Cíl: 22°C", font=("Segoe UI", 10))
        self.temp_label.pack(pady=5)
        
        self.temp_scale = ttk.Scale(self.target_temp_frame, from_=16, to=30, variable=self.temp_var, 
                                   orient=tk.HORIZONTAL, length=250, command=self.update_temp_label)
        self.temp_scale.pack(pady=5, fill='x')
        
        self.temp_btn = ttk.Button(self.target_temp_frame, text="Nastavit teplotu", command=self.set_temperature)
        self.temp_btn.pack(pady=5)

        # Síla větru s detailem
        wind_frame = ttk.LabelFrame(content_frame, text="💨 Síla větru", padding=10)
        wind_frame.pack(pady=10, padx=20, fill='x')
        
        self.wind_strengths = self.profile["property"]["airFlow"]["windStrength"]["value"]["w"]
        self.wind_var = tk.StringVar(value=self.wind_strengths[0])
        
        # Detail síly větru (read-only info)
        self.wind_detail_label = ttk.Label(wind_frame, text="Detail: --", font=("Segoe UI", 9))
        self.wind_detail_label.pack(pady=2)
        
        wind_control_frame = ttk.Frame(wind_frame)
        wind_control_frame.pack(fill='x')
        
        self.wind_combo = ttk.Combobox(wind_control_frame, values=self.wind_strengths, textvariable=self.wind_var, 
                                      state="readonly", width=15, font=("Segoe UI", 10))
        self.wind_combo.pack(side=tk.LEFT, padx=5)
        self.wind_btn = ttk.Button(wind_control_frame, text="Nastavit", command=self.set_wind_strength)
        self.wind_btn.pack(side=tk.LEFT, padx=5)

        # Směr větru s rozšířenými možnostmi
        self.wind_direction_frame = ttk.LabelFrame(content_frame, text="🌀 Směr větru", padding=10)
        self.wind_direction_frame.pack(pady=10, padx=20, fill='x')
        
        # Automatické otáčení
        auto_rotate_frame = ttk.Frame(self.wind_direction_frame)
        auto_rotate_frame.pack(fill='x', pady=5)
        
        ttk.Label(auto_rotate_frame, text="Automatické otáčení:", font=("Segoe UI", 9, "bold")).pack(anchor='w')
        
        self.rotate_updown_var = tk.BooleanVar()
        self.rotate_leftright_var = tk.BooleanVar()
        
        checkbox_frame = ttk.Frame(auto_rotate_frame)
        checkbox_frame.pack(fill='x', pady=2)
        
        self.updown_check = ttk.Checkbutton(checkbox_frame, text="↕️ Nahoru/Dolů", 
                                           variable=self.rotate_updown_var, command=self.set_wind_direction)
        self.updown_check.pack(side=tk.LEFT, padx=10)
        
        self.leftright_check = ttk.Checkbutton(checkbox_frame, text="↔️ Vlevo/Vpravo", 
                                              variable=self.rotate_leftright_var, command=self.set_wind_direction)
        self.leftright_check.pack(side=tk.LEFT, padx=10)

        # Power Save režim
        self.powersave_frame = ttk.LabelFrame(content_frame, text="⚡ Úspora energie", padding=10)
        self.powersave_frame.pack(pady=10, padx=20, fill='x')
        
        self.powersave_var = tk.BooleanVar()
        self.powersave_check = ttk.Checkbutton(self.powersave_frame, text="Zapnout úsporu energie", 
                                              variable=self.powersave_var, command=self.set_power_save)
        self.powersave_check.pack()
        
        # Dodatečné informace a statistiky
        self.info_frame = ttk.LabelFrame(content_frame, text="📊 Informace o zařízení", padding=10)
        self.info_frame.pack(pady=10, padx=20, fill='x')
        
        # Energie/spotřeba (pokud bude dostupná)
        self.energy_label = ttk.Label(self.info_frame, text="Spotřeba: Nedostupná", font=("Segoe UI", 9))
        self.energy_label.pack(anchor='w', pady=1)
        
        # Stav běhu
        self.run_state_label = ttk.Label(self.info_frame, text="Stav systému: --", font=("Segoe UI", 9))
        self.run_state_label.pack(anchor='w', pady=1)
        
        # Detail větrání
        self.wind_detail_info = ttk.Label(self.info_frame, text="Detail proudění: --", font=("Segoe UI", 9))
        self.wind_detail_info.pack(anchor='w', pady=1)
        
        # Jednotka teploty
        self.temp_unit_label = ttk.Label(self.info_frame, text="Jednotka: °C", font=("Segoe UI", 9))
        self.temp_unit_label.pack(anchor='w', pady=1)
        
        # Timery - nová sekce
        self.timer_frame = ttk.LabelFrame(content_frame, text="⏰ Časovače", padding=10)
        self.timer_frame.pack(pady=10, padx=20, fill='x')
        
        # Start timer info
        self.start_timer_label = ttk.Label(self.timer_frame, text="Časovač zapnutí: Nevystaven", font=("Segoe UI", 9))
        self.start_timer_label.pack(anchor='w', pady=1)
        
        # Stop timer info  
        self.stop_timer_label = ttk.Label(self.timer_frame, text="Časovač vypnutí: Nevystaven", font=("Segoe UI", 9))
        self.stop_timer_label.pack(anchor='w', pady=1)
        
        # Sleep timer info
        self.sleep_timer_label = ttk.Label(self.timer_frame, text="Sleep timer: Nevystaven", font=("Segoe UI", 9))
        self.sleep_timer_label.pack(anchor='w', pady=1)
        
        # Timer controls
        timer_control_frame = ttk.Frame(self.timer_frame)
        timer_control_frame.pack(fill='x', pady=5)
        
        # Quick sleep timer buttons
        ttk.Label(timer_control_frame, text="Rychlý Sleep Timer:", font=("Segoe UI", 9, "bold")).pack(anchor='w')
        sleep_buttons_frame = ttk.Frame(timer_control_frame)
        sleep_buttons_frame.pack(fill='x', pady=2)
        
        self.sleep_30min_btn = ttk.Button(sleep_buttons_frame, text="30 min", command=lambda: self.set_sleep_timer(0, 30))
        self.sleep_30min_btn.pack(side=tk.LEFT, padx=2)
        
        self.sleep_1h_btn = ttk.Button(sleep_buttons_frame, text="1 hod", command=lambda: self.set_sleep_timer(1, 0))
        self.sleep_1h_btn.pack(side=tk.LEFT, padx=2)
        
        self.sleep_2h_btn = ttk.Button(sleep_buttons_frame, text="2 hod", command=lambda: self.set_sleep_timer(2, 0))
        self.sleep_2h_btn.pack(side=tk.LEFT, padx=2)
        
        self.cancel_timers_btn = ttk.Button(sleep_buttons_frame, text="❌ Zrušit timery", command=self.cancel_all_timers)
        self.cancel_timers_btn.pack(side=tk.LEFT, padx=5)
        
        # Bind pro mousewheel scrolling
        self.bind_mousewheel(main_canvas)
        
    def bind_mousewheel(self, canvas):
        """Bind mousewheel scrolling to canvas"""
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        def _bind_to_mousewheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        def _unbind_from_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        canvas.bind('<Enter>', _bind_to_mousewheel)
        canvas.bind('<Leave>', _unbind_from_mousewheel)
        
    def on_mode_change(self, event=None):
        """Reakce na změnu módu - skrytí/zobrazení příslušných widgetů"""
        current_mode = self.mode_var.get()
        
        if current_mode == "FAN":
            # V módu FAN skryjeme nastavení cílové teploty
            self.target_temp_frame.pack_forget()
            self.temp_frame.configure(text="🌡️ Aktuální teplota")
        else:
            # V ostatních módech zobrazíme nastavení cílové teploty
            self.target_temp_frame.pack(fill='x', pady=5, after=self.current_temp_label)
            self.temp_frame.configure(text="🌡️ Teplota")
            
            # Upravíme rozsah teplot podle módu
            if current_mode == "COOL":
                self.temp_scale.configure(from_=18, to=30)
                self.temp_frame.configure(text="🌡️ Chlazení")
            elif current_mode == "HEAT":
                self.temp_scale.configure(from_=16, to=30)
                self.temp_frame.configure(text="🌡️ Vytápění")
            elif current_mode == "AUTO":
                self.temp_scale.configure(from_=18, to=30)
                self.temp_frame.configure(text="🌡️ Automatický režim")
            elif current_mode == "AIR_DRY":
                self.temp_scale.configure(from_=18, to=30)
                self.temp_frame.configure(text="🌡️ Odvlhčování")
        
        # Aktualizace velikosti okna
        self.update_idletasks()
        
    def update_temp_label(self, value):
        """Aktualizace zobrazení teploty při pohybu slideru"""
        temp = round(float(value))
        self.temp_label.config(text=f"Cíl: {temp}°C")

    def toggle_power(self):
        def send():
            asyncio.run_coroutine_threadsafe(self.async_toggle_power(), self.loop)
        threading.Thread(target=send, daemon=True).start()

    async def async_toggle_power(self):
        api, session = await get_api()
        try:
            status = await get_device_status(api, DEVICE_ID)
            power_state = status.get("operation", {}).get("airConOperationMode", "?")
            new_state = power_state != "POWER_ON"
            payload = get_power_payload(new_state)
            result = await send_device_command(api, DEVICE_ID, payload)
            self.status_var.set(f"Výsledek: {result}")
            # Vyžádání aktualizace stavu po změně
            self.after(1000, self.request_status_update)  # Počkání na aplikaci změny
        except Exception as e:
            import traceback
            print("[ERROR]", e)
            traceback.print_exc()
            self.status_var.set(f"Chyba: {e}")
        finally:
            await session.close()

    def change_mode(self):
        selected_mode = self.mode_var.get()
        def send():
            asyncio.run_coroutine_threadsafe(self.async_change_mode(selected_mode), self.loop)
        threading.Thread(target=send, daemon=True).start()

    async def async_change_mode(self, mode):
        api, session = await get_api()
        try:
            payload = {"airConJobMode": {"currentJobMode": mode}}
            result = await send_device_command(api, DEVICE_ID, payload)
            self.status_var.set(f"Mód změněn: {result}")
            # Vyžádání aktualizace stavu po změně
            self.after(1000, self.request_status_update)
        except Exception as e:
            import traceback
            print("[ERROR]", e)
            traceback.print_exc()
            self.status_var.set(f"Chyba: {e}")
        finally:
            await session.close()

    def set_temperature(self):
        temp = self.temp_var.get()
        mode = self.mode_var.get()
        def send():
            asyncio.run_coroutine_threadsafe(self.async_set_temperature(temp, mode), self.loop)
        threading.Thread(target=send, daemon=True).start()

    async def async_set_temperature(self, temp, mode):
        api, session = await get_api()
        try:
            key = None
            if mode == "COOL":
                key = "coolTargetTemperature"
            elif mode == "HEAT":
                key = "heatTargetTemperature"
            elif mode == "AUTO":
                key = "autoTargetTemperature"
            else:
                key = "targetTemperature"
            payload = {"temperature": {key: temp}}
            result = await send_device_command(api, DEVICE_ID, payload)
            self.status_var.set(f"Teplota nastavena: {result}")
            # Vyžádání aktualizace stavu po změně
            self.after(1000, self.request_status_update)
        except Exception as e:
            import traceback
            print("[ERROR]", e)
            traceback.print_exc()
            self.status_var.set(f"Chyba: {e}")
        finally:
            await session.close()

    def set_wind_strength(self):
        wind = self.wind_var.get()
        def send():
            asyncio.run_coroutine_threadsafe(self.async_set_wind_strength(wind), self.loop)
        threading.Thread(target=send, daemon=True).start()

    async def async_set_wind_strength(self, wind):
        api, session = await get_api()
        try:
            payload = {"airFlow": {"windStrength": wind}}
            result = await send_device_command(api, DEVICE_ID, payload)
            self.status_var.set(f"Síla větru nastavena: {result}")
            # Vyžádání aktualizace stavu po změně
            self.after(1000, self.request_status_update)
        except Exception as e:
            import traceback
            print("[ERROR]", e)
            traceback.print_exc()
            self.status_var.set(f"Chyba: {e}")
        finally:
            await session.close()
            
    def set_wind_direction(self):
        """Nastavení směru větru"""
        updown = self.rotate_updown_var.get()
        leftright = self.rotate_leftright_var.get()
        def send():
            asyncio.run_coroutine_threadsafe(self.async_set_wind_direction(updown, leftright), self.loop)
        threading.Thread(target=send, daemon=True).start()

    async def async_set_wind_direction(self, updown, leftright):
        api, session = await get_api()
        try:
            payload = {"windDirection": {"rotateUpDown": updown, "rotateLeftRight": leftright}}
            result = await send_device_command(api, DEVICE_ID, payload)
            self.status_var.set(f"Směr větru nastaven: {result}")
            # Vyžádání aktualizace stavu po změně
            self.after(1000, self.request_status_update)
        except Exception as e:
            import traceback
            print("[ERROR]", e)
            traceback.print_exc()
            self.status_var.set(f"Chyba: {e}")
        finally:
            await session.close()
            
    def set_power_save(self):
        """Nastavení power save režimu"""
        enabled = self.powersave_var.get()
        def send():
            asyncio.run_coroutine_threadsafe(self.async_set_power_save(enabled), self.loop)
        threading.Thread(target=send, daemon=True).start()

    async def async_set_power_save(self, enabled):
        api, session = await get_api()
        try:
            payload = {"powerSave": {"powerSaveEnabled": enabled}}
            result = await send_device_command(api, DEVICE_ID, payload)
            self.status_var.set(f"Power Save {'zapnut' if enabled else 'vypnut'}: {result}")
            # Vyžádání aktualizace stavu po změně
            self.after(1000, self.request_status_update)
        except Exception as e:
            import traceback
            print("[ERROR]", e)
            traceback.print_exc()
            self.status_var.set(f"Chyba: {e}")
        finally:
            await session.close()
            
    def set_sleep_timer(self, hours, minutes):
        """Nastavení sleep timer"""
        def send():
            asyncio.run_coroutine_threadsafe(self.async_set_sleep_timer(hours, minutes), self.loop)
        threading.Thread(target=send, daemon=True).start()

    async def async_set_sleep_timer(self, hours, minutes):
        api, session = await get_api()
        try:
            payload = {
                "sleepTimer": {
                    "relativeHourToStop": hours,
                    "relativeMinuteToStop": minutes,
                    "relativeStopTimer": "SET" if hours > 0 or minutes > 0 else "UNSET"
                }
            }
            result = await send_device_command(api, DEVICE_ID, payload)
            if hours > 0 or minutes > 0:
                self.status_var.set(f"Sleep timer nastaven na {hours}h {minutes}min: {result}")
            else:
                self.status_var.set(f"Sleep timer zrušen: {result}")
            # Vyžádání aktualizace stavu po změně
            self.after(1000, self.request_status_update)
        except Exception as e:
            import traceback
            print("[ERROR]", e)
            traceback.print_exc()
            self.status_var.set(f"Chyba: {e}")
        finally:
            await session.close()
            
    def cancel_all_timers(self):
        """Zrušení všech časovačů"""
        def send():
            asyncio.run_coroutine_threadsafe(self.async_cancel_all_timers(), self.loop)
        threading.Thread(target=send, daemon=True).start()

    async def async_cancel_all_timers(self):
        api, session = await get_api()
        try:
            payload = {
                "timer": {
                    "relativeStartTimer": "UNSET",
                    "relativeStopTimer": "UNSET"
                },
                "sleepTimer": {
                    "relativeStopTimer": "UNSET"
                }
            }
            result = await send_device_command(api, DEVICE_ID, payload)
            self.status_var.set(f"Všechny časovače zrušeny: {result}")
            # Vyžádání aktualizace stavu po změně
            self.after(1000, self.request_status_update)
        except Exception as e:
            import traceback
            print("[ERROR]", e)
            traceback.print_exc()
            self.status_var.set(f"Chyba: {e}")
        finally:
            await session.close()

    def initial_status_check(self):
        """Počáteční načtení stavu při spuštění"""
        def fetch():
            asyncio.run_coroutine_threadsafe(self.async_update_status(), self.loop)
        threading.Thread(target=fetch, daemon=True).start()
        # Spustí periodické kontroly
        self.after(self.status_check_interval, self.periodic_status_check)
        
    def periodic_status_check(self):
        """Periodická kontrola stavu pouze pokud není čekající aktualizace"""
        if not self.pending_update:
            def fetch():
                asyncio.run_coroutine_threadsafe(self.async_update_status(), self.loop)
            threading.Thread(target=fetch, daemon=True).start()
        # Naplánuje další kontrolu
        self.after(self.status_check_interval, self.periodic_status_check)
        
    def request_status_update(self):
        """Vyžádá okamžitou aktualizaci stavu po provedení změny"""
        self.pending_update = True
        self.status_var.set("Aktualizuji stav...")
        def fetch():
            asyncio.run_coroutine_threadsafe(self.async_update_status(), self.loop)
        threading.Thread(target=fetch, daemon=True).start()

    async def async_update_status(self):
        api, session = await get_api()
        try:
            status = await get_device_status(api, DEVICE_ID)
            
            # Porovnání se zachovaným stavem - aktualizace pouze při změně
            if self.last_device_status != status:
                print("[DEBUG] Device status changed:", status)
                self.last_device_status = status.copy()
                
                # Extrakce dat ze statusu
                power_state = status.get("operation", {}).get("airConOperationMode", "?")
                current_temp = status.get("temperature", {}).get("currentTemperature", "?")
                target_temp = status.get("temperature", {}).get("targetTemperature", "?")
                temp_unit = status.get("temperature", {}).get("unit", "C")
                mode = status.get("airConJobMode", {}).get("currentJobMode", "?")
                wind = status.get("airFlow", {}).get("windStrength", "?")
                wind_detail = status.get("airFlow", {}).get("windStrengthDetail", "Nedostupný")
                wind_updown = status.get("windDirection", {}).get("rotateUpDown", False)
                wind_leftright = status.get("windDirection", {}).get("rotateLeftRight", False)
                power_save = status.get("powerSave", {}).get("powerSaveEnabled", False)
                run_state = status.get("runState", {}).get("currentState", "Neznámý")
                
                # Timer informace
                start_timer = status.get("timer", {}).get("relativeStartTimer", "UNSET")
                stop_timer = status.get("timer", {}).get("relativeStopTimer", "UNSET")  
                sleep_timer = status.get("sleepTimer", {}).get("relativeStopTimer", "UNSET")
                
                # Pokus o získání informací o spotřebě (experimentální)
                energy_info = "Nedostupná"
                if "energy" in status:
                    energy_data = status["energy"]
                    if isinstance(energy_data, dict):
                        consumption = energy_data.get("consumption", energy_data.get("power", energy_data.get("watt", "N/A")))
                        if consumption != "N/A":
                            energy_info = f"{consumption} W"
                elif "power" in status:
                    power_data = status["power"]
                    if isinstance(power_data, (int, float)):
                        energy_info = f"{power_data} W"
                    elif isinstance(power_data, dict):
                        consumption = power_data.get("consumption", power_data.get("current", "N/A"))
                        if consumption != "N/A":
                            energy_info = f"{consumption} W"
                
                # Aktualizace stavového textu
                power_text = "Zapnuto" if power_state == "POWER_ON" else "Vypnuto" if power_state == "POWER_OFF" else "Neznámý"
                self.status_var.set(f"Stav: {power_text} | {current_temp}°C → {target_temp}°C | {mode}")
                
                # Aktualizace LED indikátoru
                self.led_indicator.set_state(power_state)
                
                # Aktualizace aktuální teploty
                self.current_temp_label.config(text=f"Aktuální: {current_temp}°C")
                
                # Aktualizace hodnot v GUI (bez triggeru událostí)
                if mode in self.modes:
                    self.mode_var.set(mode)
                    self.on_mode_change()  # Aplikuje logiku skrytí/zobrazení
                    
                if isinstance(target_temp, (int, float)) and mode != "FAN":
                    self.temp_var.set(target_temp)
                    self.temp_label.config(text=f"Cíl: {target_temp}°C")
                    
                if wind in self.wind_strengths:
                    self.wind_var.set(wind)
                    
                # Aktualizace směru větru
                self.rotate_updown_var.set(wind_updown)
                self.rotate_leftright_var.set(wind_leftright)
                
                # Aktualizace power save
                self.powersave_var.set(power_save)
                
                # Aktualizace informačních labelů
                self.energy_label.config(text=f"Spotřeba: {energy_info}")
                self.run_state_label.config(text=f"Stav systému: {run_state}")
                self.wind_detail_info.config(text=f"Detail proudění: {wind_detail}")
                self.temp_unit_label.config(text=f"Jednotka: °{temp_unit}")
                self.wind_detail_label.config(text=f"Detail: {wind_detail}")
                
                # Aktualizace timer labelů
                self.start_timer_label.config(text=f"Časovač zapnutí: {'Nastaven' if start_timer == 'SET' else 'Nevystaven'}")
                self.stop_timer_label.config(text=f"Časovač vypnutí: {'Nastaven' if stop_timer == 'SET' else 'Nevystaven'}")
                self.sleep_timer_label.config(text=f"Sleep timer: {'Nastaven' if sleep_timer == 'SET' else 'Nevystaven'}")
                
            else:
                print("[DEBUG] Device status unchanged, skipping update")
                
        except Exception as e:
            import traceback
            print("[ERROR]", e)
            traceback.print_exc()
            self.status_var.set(f"Chyba: {e}")
            self.led_indicator.set_state(None)
        finally:
            await session.close()
            self.pending_update = False  # Reset flagu

    # ...další metody pro logiku a aktualizaci GUI...

if __name__ == "__main__":
    app = KlimaApp()
    app.mainloop()
