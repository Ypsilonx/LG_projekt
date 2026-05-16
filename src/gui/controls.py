# -*- coding: utf-8 -*-
"""
Modul pro základní ovládací prvky klimatizace.
Obsahuje widgety pro zapnutí/vypnutí, změnu módu, teploty, větru apod.
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable

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
        self.hand_mode_enabled = False
        self.advanced_controls_expanded = False
        self._last_mode_layout = None
        
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
        
        # Cílová teplota (layout je stale stejny, v rezimu FAN se jen vypne)
        self.target_temp_frame = ttk.Frame(self.temp_frame)
        self.target_temp_frame.pack(fill='x', pady=5)
        
        self.temp_label = ttk.Label(self.target_temp_frame, text="Cíl: 22°C", font=("Segoe UI", 10))
        self.temp_label.pack(pady=5)
        
        self.temp_scale = ttk.Scale(self.target_temp_frame, from_=16, to=30, variable=self.temp_var, 
                                   orient=tk.HORIZONTAL, length=250, command=self.update_temp_label)
        # ttk.Scale nemá resolution, takže budeme zaokrouhlovat na půlstupně v callback
        self.temp_scale.pack(pady=5, fill='x')
        
        self.temp_btn = ttk.Button(self.target_temp_frame, text="Nastavit teplotu", command=self.set_temperature)
        self.temp_btn.pack(pady=5)

        self.temp_mode_hint = ttk.Label(
            self.target_temp_frame,
            text="",
            font=("Segoe UI", 9),
            foreground="#999999",
        )
        self.temp_mode_hint.pack(anchor='w', pady=(2, 0))

        self.advanced_toggle_btn = ttk.Button(
            self,
            text="▶ Pokrocile rucni ovladani",
            command=self._toggle_advanced_controls,
        )
        self.advanced_toggle_btn.pack(pady=(0, 6), padx=20, fill='x')

        self.advanced_controls_container = ttk.Frame(self)
        self.advanced_controls_container.pack(fill='x')

        # Síla větru s detailem (pouze HAND mód)
        self.wind_frame = ttk.LabelFrame(self.advanced_controls_container, text="💨 Síla větru", padding=10)
        self.wind_frame.pack(pady=10, padx=20, fill='x')
        
        # Detail síly větru (read-only info)
        self.wind_detail_label = ttk.Label(self.wind_frame, text="Detail: --", font=("Segoe UI", 9))
        self.wind_detail_label.pack(pady=2)
        
        wind_control_frame = ttk.Frame(self.wind_frame)
        wind_control_frame.pack(fill='x')
        
        self.wind_combo = ttk.Combobox(wind_control_frame, values=self.wind_strengths, textvariable=self.wind_var, 
                                      state="readonly", width=15, font=("Segoe UI", 10))
        self.wind_combo.pack(side=tk.LEFT, padx=5)
        self.wind_btn = ttk.Button(wind_control_frame, text="Nastavit", command=self.set_wind_strength)
        self.wind_btn.pack(side=tk.LEFT, padx=5)

        # Směr větru s rozšířenými možnostmi
        self.wind_direction_frame = ttk.LabelFrame(self.advanced_controls_container, text="🌀 Směr větru", padding=10)
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
        self.powersave_frame = ttk.LabelFrame(self.advanced_controls_container, text="⚡ Úspora energie", padding=10)
        self.powersave_frame.pack(pady=10, padx=20, fill='x')
        
        self.powersave_check = ttk.Checkbutton(self.powersave_frame, text="Zapnout úsporu energie", 
                                              variable=self.powersave_var, command=self.set_power_save)
        self.powersave_check.pack()

        if self.modes:
            self.mode_var.set(self.modes[0])
        self.on_mode_change()
        self.set_hand_mode(False)

    def set_hand_mode(self, enabled: bool):
        """Nastavi viditelnost HAND-only pokrocileho ovladani.

        Args:
            enabled: True pokud ma byt aktivni HAND mod.
        """
        self.hand_mode_enabled = bool(enabled)
        if not self.hand_mode_enabled:
            self.advanced_controls_expanded = False

        self._apply_advanced_controls_visibility()

    def _toggle_advanced_controls(self):
        """Prepinac rozbaleni pokrocilych rucnich prvku."""
        if not self.hand_mode_enabled:
            return

        self.advanced_controls_expanded = not self.advanced_controls_expanded
        self._apply_advanced_controls_visibility()

    def _apply_advanced_controls_visibility(self):
        """Aplikuje aktualni viditelnost HAND-only panelu."""
        if self.hand_mode_enabled:
            if not self.advanced_toggle_btn.winfo_manager():
                self.advanced_toggle_btn.pack(pady=(0, 6), padx=20, fill='x')

            if self.advanced_controls_expanded:
                if not self.advanced_controls_container.winfo_manager():
                    self.advanced_controls_container.pack(fill='x')
            elif self.advanced_controls_container.winfo_manager():
                self.advanced_controls_container.pack_forget()
        else:
            if self.advanced_controls_container.winfo_manager():
                self.advanced_controls_container.pack_forget()
            if self.advanced_toggle_btn.winfo_manager():
                self.advanced_toggle_btn.pack_forget()

        self._update_advanced_toggle_text()

    def _update_advanced_toggle_text(self):
        """Aktualizuje text tlacitka dle stavu rozbaleni."""
        if not self.hand_mode_enabled:
            return

        icon = "▼" if self.advanced_controls_expanded else "▶"
        self.advanced_toggle_btn.configure(text=f"{icon} Pokrocile rucni ovladani")
        
    def on_mode_change(self, event=None):
        """Reakce na změnu modu bez skakani layoutu pri prepnuti."""
        current_mode = self.mode_var.get()

        if current_mode == self._last_mode_layout:
            return

        supports_target_temp = current_mode != "FAN"

        if current_mode == "FAN":
            self.temp_scale.configure(state='disabled')
            self.temp_btn.configure(state='disabled')
            self.temp_mode_hint.configure(text="V rezimu FAN se cilova teplota nenastavuje")
            self.temp_frame.configure(text="🌡️ Aktuální teplota")
        else:
            self.temp_scale.configure(state='normal')
            self.temp_btn.configure(state='normal')
            self.temp_mode_hint.configure(text="")
            self.temp_frame.configure(text="🌡️ Teplota")
            
            # Upravíme rozsah teplot podle módu (pouze celá čísla)
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

        if supports_target_temp and self.temp_mode_hint.cget("text"):
            self.temp_mode_hint.configure(text="")

        self._last_mode_layout = current_mode
        
        # Aktualizace velikosti okna po zmene obsahu
        self.update_idletasks()
        
    def update_temp_label(self, value):
        """Aktualizace zobrazení teploty při pohybu slideru"""
        # Pouze celá čísla (žádné půlstupně)
        temp = int(round(float(value)))
        # Nastavíme zaokrouhlenou hodnotu zpět do proměnné
        self.temp_var.set(temp)
        self.temp_label.config(text=f"Cíl: {temp}°C")
        
    def update_status(self, device_status: dict, sensor_offset_c: float = 0.0):
        """Aktualizace GUI podle stavu zařízení.

        Args:
            device_status: Snapshot stavu klimatizace.
            sensor_offset_c: Korekce cidla v C, aplikovana na aktualni teplotu.
        """
        # Extrakce dat ze statusu
        current_temp = device_status.get("temperature", {}).get("currentTemperature", "?")
        target_temp = device_status.get("temperature", {}).get("targetTemperature", "?")
        mode = device_status.get("airConJobMode", {}).get("currentJobMode", "?")
        wind = device_status.get("airFlow", {}).get("windStrength", "?")
        wind_detail = device_status.get("airFlow", {}).get("windStrengthDetail", "Nedostupný")
        wind_updown = device_status.get("windDirection", {}).get("rotateUpDown", False)
        wind_leftright = device_status.get("windDirection", {}).get("rotateLeftRight", False)
        power_save = device_status.get("powerSave", {}).get("powerSaveEnabled", False)
        
        # Aktualizace aktuální teploty (zobrazeni s offsetem)
        try:
            corrected_current_temp = float(current_temp) + float(sensor_offset_c)
            self.current_temp_label.config(text=f"Aktualni (s offsetem): {corrected_current_temp:.1f}°C")
        except (TypeError, ValueError):
            self.current_temp_label.config(text="Aktualni (s offsetem): --°C")
        
        # Aktualizace hodnot v GUI (bez triggeru událostí)
        if mode in self.modes:
            if self.mode_var.get() != mode:
                self.mode_var.set(mode)
                self.on_mode_change()
            
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
            # Pošleme pouze teplotu bez režimu (nechá aktuální režim)
            self.on_command("set_temperature", self.temp_var.get())
            
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
        self.hand_mode_enabled = False
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

        self.set_hand_mode(False)

    def set_hand_mode(self, enabled: bool):
        """Nastavi viditelnost HAND-only informaci o proudění.

        Args:
            enabled: True pokud je aktivni HAND rezim.
        """
        self.hand_mode_enabled = bool(enabled)
        if self.hand_mode_enabled:
            if not self.wind_detail_info.winfo_manager():
                self.wind_detail_info.pack(anchor='w', pady=1, before=self.temp_unit_label)
        elif self.wind_detail_info.winfo_manager():
            self.wind_detail_info.pack_forget()
        
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
