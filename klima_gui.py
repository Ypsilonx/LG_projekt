import json
import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import aiohttp
from thinqconnect import ThinQApi, AirConditionerDevice

# --- Uživatelské údaje ---
ACCESS_TOKEN = "thinqpat_72547fb563e6b9b202d9a45ca8d582e1bcac54da66c7b47e110e"
COUNTRY_CODE = "CZ"
CLIENT_ID = "klima-gui-demo"
DEVICE_ID = "ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e"

# Vysvětlivky k parametrům
EXPLAIN = {
    "runState": "Stav zařízení (NORMAL, ERROR)",
    "airConJobMode": "Režim klimatizace (HEAT, AUTO, COOL, AIR_DRY, FAN)",
    "operation": "Zapnutí/vypnutí (POWER_ON, POWER_OFF)",
    "powerSave": "Úspora energie (True/False)",
    "temperature": "Nastavení teploty (C/F, min/max, krok)",
    "airFlow": "Síla ventilátoru (HIGH, MID, LOW, AUTO)",
    "windDirection": "Směr proudění (vertikální/horizontální)",
    "timer": "Časovač (relativní start/stop)",
    "sleepTimer": "Sleep timer (relativní stop)",
}

# --- Asynchronní funkce pro získání aktuálního stavu a nastavení ---
async def get_ac_device():
    async with aiohttp.ClientSession() as session:
        api = ThinQApi(
            access_token=ACCESS_TOKEN,
            country_code=COUNTRY_CODE,
            client_id=CLIENT_ID,
            session=session
        )
        device = AirConditionerDevice(api, DEVICE_ID)
        await device.async_update()
        return device

def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

# --- GUI aplikace ---
class KlimaApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LG Klimatizace - Ovládání")
        self.geometry("520x650")
        self.device = None
        self.create_widgets()
        self.refresh_state()

    def create_widgets(self):
        self.state_frame = ttk.LabelFrame(self, text="Aktuální stav klimatizace")
        self.state_frame.pack(fill="x", padx=10, pady=5)
        self.state_text = tk.Text(self.state_frame, height=12, width=60, state="disabled")
        self.state_text.pack()

        self.control_frame = ttk.LabelFrame(self, text="Ovládání")
        self.control_frame.pack(fill="x", padx=10, pady=5)

        # Režim
        ttk.Label(self.control_frame, text="Režim:").grid(row=0, column=0, sticky="w")
        self.mode_var = tk.StringVar()
        self.mode_combo = ttk.Combobox(self.control_frame, textvariable=self.mode_var, state="readonly")
        self.mode_combo["values"] = ["AUTO", "COOL", "HEAT", "AIR_DRY", "FAN"]
        self.mode_combo.grid(row=0, column=1, padx=5, pady=2)

        # Teplota
        ttk.Label(self.control_frame, text="Cílová teplota [°C]:").grid(row=1, column=0, sticky="w")
        self.temp_var = tk.IntVar()
        self.temp_spin = ttk.Spinbox(self.control_frame, from_=16, to=30, textvariable=self.temp_var, width=5)
        self.temp_spin.grid(row=1, column=1, padx=5, pady=2)

        # Síla ventilátoru
        ttk.Label(self.control_frame, text="Síla ventilátoru:").grid(row=2, column=0, sticky="w")
        self.fan_var = tk.StringVar()
        self.fan_combo = ttk.Combobox(self.control_frame, textvariable=self.fan_var, state="readonly")
        self.fan_combo["values"] = ["AUTO", "LOW", "MID", "HIGH"]
        self.fan_combo.grid(row=2, column=1, padx=5, pady=2)

        # Směr proudění
        ttk.Label(self.control_frame, text="Směr proudění:").grid(row=3, column=0, sticky="w")
        self.dir_var = tk.StringVar()
        self.dir_combo = ttk.Combobox(self.control_frame, textvariable=self.dir_var, state="readonly")
        self.dir_combo["values"] = ["AUTO", "UP", "DOWN", "LEFT", "RIGHT"]
        self.dir_combo.grid(row=3, column=1, padx=5, pady=2)

        # Zapnout/vypnout
        self.power_btn = ttk.Button(self.control_frame, text="Zapnout", command=self.toggle_power)
        self.power_btn.grid(row=4, column=0, padx=5, pady=10, sticky="ew")

        # Nastavit parametry
        self.set_btn = ttk.Button(self.control_frame, text="Nastavit parametry", command=self.set_params)
        self.set_btn.grid(row=4, column=1, padx=5, pady=10, sticky="ew")

        # Obnovit stav
        self.refresh_btn = ttk.Button(self, text="Obnovit stav", command=self.refresh_state)
        self.refresh_btn.pack(pady=5)

    def refresh_state(self):
        self.state_text.config(state="normal")
        self.state_text.delete(1.0, tk.END)
        try:
            self.device = run_async(get_ac_device())
            state = self.device.state
            # Výpis stavu
            for k, v in state.items():
                self.state_text.insert(tk.END, f"{k}: {v}\n")
            self.state_text.config(state="disabled")
            # Předvyplnit hodnoty do ovládání
            self.mode_var.set(state.get("airConJobMode", "AUTO"))
            self.temp_var.set(int(state.get("targetTemperature", 22)))
            self.fan_var.set(state.get("windStrength", "AUTO"))
            self.dir_var.set("AUTO")  # Směr proudění není vždy dostupný, lze rozšířit
            self.power_btn.config(text="Vypnout" if state.get("operation") == "POWER_ON" else "Zapnout")
        except Exception as e:
            self.state_text.insert(tk.END, f"Chyba při načítání stavu: {e}\n")
            self.state_text.config(state="disabled")

    def toggle_power(self):
        if not self.device:
            return
        try:
            power_on = self.device.state.get("operation") != "POWER_ON"
            run_async(self.device.async_set_operation("POWER_ON" if power_on else "POWER_OFF"))
            self.refresh_state()
        except Exception as e:
            messagebox.showerror("Chyba", f"Nelze změnit stav: {e}")

    def set_params(self):
        if not self.device:
            return
        try:
            # Nastavení režimu
            run_async(self.device.async_set_current_job_mode(self.mode_var.get()))
            # Nastavení teploty
            run_async(self.device.async_set_target_temperature_c(self.temp_var.get()))
            # Nastavení síly ventilátoru
            run_async(self.device.async_set_wind_strength(self.fan_var.get()))
            # Směr proudění – pouze pokud je podporováno
            # run_async(self.device.async_set_wind_rotate_up_down(self.dir_var.get()))
            self.refresh_state()
        except Exception as e:
            messagebox.showerror("Chyba", f"Nelze nastavit parametry: {e}")

if __name__ == "__main__":
    app = KlimaApp()
    app.mainloop()
