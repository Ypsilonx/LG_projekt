"""
Modul pro základní ovládací prvky klimatizace.
Obsahuje widgety pro zapnutí/vypnutí, změnu módu, teploty, větru apod.
"""
import tkinter as tk
from tkinter import ttk
import asyncio
import threading
from typing import Callable, Optional, List

class ClimateControls(ttk.Frame):
    """Widget s osnovními ovládacími prvky klimatizace"""
    
    def __init__(self, parent, profile: dict, status_var: tk.StringVar, 
                 on_command: Callable = None):
        super().__init__(parent)
        self.profile = profile
        self.status_var = status_var
        self.on_command = on_command
        
        # Proměnné pro GUI
        self.mode_var = tk.StringVar()
        self.temp_var = tk.DoubleVar(value=22)
        self.wind_var = tk.StringVar()
        self.rotate_updown_var = tk.BooleanVar()
        self.rotate_leftright_var = tk.BooleanVar()
        self.powersave_var = tk.BooleanVar()
        
        # Data z profilu
        self.modes = self.profile["property"]["airConJobMode"]["currentJobMode"]["value"]["w"]
        self.wind_strengths = self.profile["property"]["airFlow"]["windStrength"]["value"]["w"]
        
        self.create_widgets()
        
    def create_widgets(self):
        """Vytvoření ovládacích prvků"""
        
        # Tlačítko zapnutí/vypnutí
        self.toggle_btn = ttk.Button(self, text="⚡ Zapnout/Vypnout", command=self.toggle_power)
        self.toggle_btn.pack(pady=10)

        # Výběr módu
        mode_frame = ttk.LabelFrame(self, text="🌡️ Režim klimatizace", padding=10)
        mode_frame.pack(pady=10, padx=20, fill='x')
        
        self.mode_combo = ttk.Combobox(mode_frame, values=self.modes, textvariable=self.mode_var, 
                                      state="readonly", width=15, font=("Segoe UI", 10))
        self.mode_combo.pack(side=tk.LEFT, padx=5)
        self.mode_combo.bind("<<ComboboxSelected>>", self.on_mode_change)
        
        self.mode_btn = ttk.Button(mode_frame, text="Změnit", command=self.change_mode)
        self.mode_btn.pack(side=tk.LEFT, padx=5)

        # Teplota (dynamicky zobrazovaná podle módu)
        self.temp_frame = ttk.LabelFrame(self, text="🌡️ Teplota", padding=10)
        self.temp_frame.pack(pady=10, padx=20, fill='x')
        
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
        # ttk.Scale nemá resolution, takže budeme zaokrouhlovat v callback
        self.temp_scale.pack(pady=5, fill='x')
        
        self.temp_btn = ttk.Button(self.target_temp_frame, text="Nastavit teplotu", command=self.set_temperature)
        self.temp_btn.pack(pady=5)

        # Síla větru s detailem
        wind_frame = ttk.LabelFrame(self, text="💨 Síla větru", padding=10)
        wind_frame.pack(pady=10, padx=20, fill='x')
        
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
        self.wind_direction_frame = ttk.LabelFrame(self, text="🌀 Směr větru", padding=10)
        self.wind_direction_frame.pack(pady=10, padx=20, fill='x')
        
        # Automatické otáčení
        auto_rotate_frame = ttk.Frame(self.wind_direction_frame)
        auto_rotate_frame.pack(fill='x', pady=5)
        
        ttk.Label(auto_rotate_frame, text="Automatické otáčení:", font=("Segoe UI", 9, "bold")).pack(anchor='w')
        
        checkbox_frame = ttk.Frame(auto_rotate_frame)
        checkbox_frame.pack(fill='x', pady=2)
        
        self.updown_check = ttk.Checkbutton(checkbox_frame, text="↕️ Nahoru/Dolů", 
                                           variable=self.rotate_updown_var, command=self.set_wind_direction)
        self.updown_check.pack(side=tk.LEFT, padx=10)
        
        self.leftright_check = ttk.Checkbutton(checkbox_frame, text="↔️ Vlevo/Vpravo", 
                                              variable=self.rotate_leftright_var, command=self.set_wind_direction)
        self.leftright_check.pack(side=tk.LEFT, padx=10)

        # Power Save režim
        self.powersave_frame = ttk.LabelFrame(self, text="⚡ Úspora energie", padding=10)
        self.powersave_frame.pack(pady=10, padx=20, fill='x')
        
        self.powersave_check = ttk.Checkbutton(self.powersave_frame, text="Zapnout úsporu energie", 
                                              variable=self.powersave_var, command=self.set_power_save)
        self.powersave_check.pack()
        
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
            
            # Upravíme rozsah teplot podle módu (podle device_profile.json)
            if current_mode == "COOL":
                # Chlazení: 18-30°C
                self.temp_scale.configure(from_=18, to=30)
                self.temp_frame.configure(text="🌡️ Chlazení (18-30°C)")
            elif current_mode == "HEAT":
                # Vytápění: 16-30°C (širší rozsah dolů)
                self.temp_scale.configure(from_=16, to=30)
                self.temp_frame.configure(text="🌡️ Vytápění (16-30°C)")
            elif current_mode == "AUTO":
                # Automatický: 18-30°C
                self.temp_scale.configure(from_=18, to=30)
                self.temp_frame.configure(text="🌡️ Automatický režim (18-30°C)")
            elif current_mode == "AIR_DRY":
                # Odvlhčování: 18-30°C
                self.temp_scale.configure(from_=18, to=30)
                self.temp_frame.configure(text="🌡️ Odvlhčování (18-30°C)")
        
        # Aktualizace velikosti okna
        self.update_idletasks()
        
    def update_temp_label(self, value):
        """Aktualizace zobrazení teploty při pohybu slideru"""
        # Zaokrouhlíme na celé stupně jako v oficiální LG aplikaci
        temp = round(float(value))
        # Nastavíme zaokrouhlenou hodnotu zpět do proměnné
        self.temp_var.set(temp)
        self.temp_label.config(text=f"Cíl: {temp}°C")
        
    def update_status(self, device_status: dict):
        """Aktualizace GUI podle stavu zařízení"""
        # Extrakce dat ze statusu
        current_temp = device_status.get("temperature", {}).get("currentTemperature", "?")
        target_temp = device_status.get("temperature", {}).get("targetTemperature", "?")
        mode = device_status.get("airConJobMode", {}).get("currentJobMode", "?")
        wind = device_status.get("airFlow", {}).get("windStrength", "?")
        wind_detail = device_status.get("airFlow", {}).get("windStrengthDetail", "Nedostupný")
        wind_updown = device_status.get("windDirection", {}).get("rotateUpDown", False)
        wind_leftright = device_status.get("windDirection", {}).get("rotateLeftRight", False)
        power_save = device_status.get("powerSave", {}).get("powerSaveEnabled", False)
        
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
        
        # Aktualizace detail labelu
        self.wind_detail_label.config(text=f"Detail: {wind_detail}")
    
    # Metody pro ovládání - delegují na callback
    def toggle_power(self):
        if self.on_command:
            self.on_command("toggle_power")
            
    def change_mode(self):
        if self.on_command:
            self.on_command("change_mode", self.mode_var.get())
            
    def set_temperature(self):
        if self.on_command:
            self.on_command("set_temperature", self.temp_var.get(), self.mode_var.get())
            
    def set_wind_strength(self):
        if self.on_command:
            self.on_command("set_wind_strength", self.wind_var.get())
            
    def set_wind_direction(self):
        if self.on_command:
            self.on_command("set_wind_direction", self.rotate_updown_var.get(), self.rotate_leftright_var.get())
            
    def set_power_save(self):
        if self.on_command:
            self.on_command("set_power_save", self.powersave_var.get())

class TimerControls(ttk.Frame):
    """Widget pro ovládání časovačů"""
    
    def __init__(self, parent, on_command: Callable = None):
        super().__init__(parent)
        self.on_command = on_command
        self.create_widgets()
        
    def create_widgets(self):
        """Vytvoření widgetů pro časovače"""
        # Timery - hlavní sekce
        timer_frame = ttk.LabelFrame(self, text="⏰ Časovače", padding=10)
        timer_frame.pack(pady=10, padx=20, fill='x')
        
        # Status timeru
        self.start_timer_label = ttk.Label(timer_frame, text="Časovač zapnutí: Nevystaven", font=("Segoe UI", 9))
        self.start_timer_label.pack(anchor='w', pady=1)
        
        self.stop_timer_label = ttk.Label(timer_frame, text="Časovač vypnutí: Nevystaven", font=("Segoe UI", 9))
        self.stop_timer_label.pack(anchor='w', pady=1)
        
        self.sleep_timer_label = ttk.Label(timer_frame, text="Sleep timer: Nevystaven", font=("Segoe UI", 9))
        self.sleep_timer_label.pack(anchor='w', pady=1)
        
        # Timer controls
        timer_control_frame = ttk.Frame(timer_frame)
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
        
    def update_status(self, device_status: dict):
        """Aktualizace zobrazení časovačů"""
        start_timer = device_status.get("timer", {}).get("relativeStartTimer", "UNSET")
        stop_timer = device_status.get("timer", {}).get("relativeStopTimer", "UNSET")  
        sleep_timer = device_status.get("sleepTimer", {}).get("relativeStopTimer", "UNSET")
        
        self.start_timer_label.config(text=f"Časovač zapnutí: {'Nastaven' if start_timer == 'SET' else 'Nevystaven'}")
        self.stop_timer_label.config(text=f"Časovač vypnutí: {'Nastaven' if stop_timer == 'SET' else 'Nevystaven'}")
        self.sleep_timer_label.config(text=f"Sleep timer: {'Nastaven' if sleep_timer == 'SET' else 'Nevystaven'}")
        
    def set_sleep_timer(self, hours, minutes):
        if self.on_command:
            self.on_command("set_sleep_timer", hours, minutes)
            
    def cancel_all_timers(self):
        if self.on_command:
            self.on_command("cancel_all_timers")

class InfoPanel(ttk.Frame):
    """Widget pro zobrazení dodatečných informací"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.create_widgets()
        
    def create_widgets(self):
        """Vytvoření informačního panelu"""
        # Dodatečné informace a statistiky
        info_frame = ttk.LabelFrame(self, text="📊 Informace o zařízení", padding=10)
        info_frame.pack(pady=10, padx=20, fill='x')
        
        # Energie/spotřeba (pokud bude dostupná)
        self.energy_label = ttk.Label(info_frame, text="Spotřeba: Nedostupná", font=("Segoe UI", 9))
        self.energy_label.pack(anchor='w', pady=1)
        
        # Stav běhu
        self.run_state_label = ttk.Label(info_frame, text="Stav systému: --", font=("Segoe UI", 9))
        self.run_state_label.pack(anchor='w', pady=1)
        
        # Detail větrání
        self.wind_detail_info = ttk.Label(info_frame, text="Detail proudění: --", font=("Segoe UI", 9))
        self.wind_detail_info.pack(anchor='w', pady=1)
        
        # Jednotka teploty
        self.temp_unit_label = ttk.Label(info_frame, text="Jednotka: °C", font=("Segoe UI", 9))
        self.temp_unit_label.pack(anchor='w', pady=1)
        
    def update_status(self, device_status: dict):
        """Aktualizace informačního panelu"""
        run_state = device_status.get("runState", {}).get("currentState", "Neznámý")
        wind_detail = device_status.get("airFlow", {}).get("windStrengthDetail", "Nedostupný")
        temp_unit = device_status.get("temperature", {}).get("unit", "C")
        
        # Pokus o získání informací o spotřebě (experimentální)
        energy_info = "Nedostupná"
        if "energy" in device_status:
            energy_data = device_status["energy"]
            if isinstance(energy_data, dict):
                consumption = energy_data.get("consumption", energy_data.get("power", energy_data.get("watt", "N/A")))
                if consumption != "N/A":
                    energy_info = f"{consumption} W"
        elif "power" in device_status:
            power_data = device_status["power"]
            if isinstance(power_data, (int, float)):
                energy_info = f"{power_data} W"
            elif isinstance(power_data, dict):
                consumption = power_data.get("consumption", power_data.get("current", "N/A"))
                if consumption != "N/A":
                    energy_info = f"{consumption} W"
                    
        self.energy_label.config(text=f"Spotřeba: {energy_info}")
        self.run_state_label.config(text=f"Stav systému: {run_state}")
        self.wind_detail_info.config(text=f"Detail proudění: {wind_detail}")
        self.temp_unit_label.config(text=f"Jednotka: °{temp_unit}")
