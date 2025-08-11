import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import uuid
import aiohttp
import json
from thinqconnect import ThinQApi, AirConditionerDevice

# Uživatelské údaje
ACCESS_TOKEN = "thinqpat_72547fb563e6b9b202d9a45ca8d582e1bcac54da66c7b47e110e"
COUNTRY_CODE = "CZ"
CLIENT_ID = str(uuid.uuid4())
DEVICE_ID = "ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e"

# Načti informace o zařízení a profil ze souborů
with open("devices.json", encoding="utf-8") as f:
    devices = json.load(f)
device_info = next(d for d in devices if d["deviceId"] == DEVICE_ID)["deviceInfo"]

with open("device_profile.json", encoding="utf-8") as f:
    device_profile = json.load(f)

def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

async def get_ac_state():
    async with aiohttp.ClientSession() as session:
        api = ThinQApi(
            access_token=ACCESS_TOKEN,
            country_code=COUNTRY_CODE,
            client_id=CLIENT_ID,
            session=session
        )
        status = await api.async_get_device_status(DEVICE_ID)
        print("Status z API:", status)
        return status

class KlimaSimpleApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LG Klimatizace - Jednoduché ovládání")
        self.geometry("500x400")
        self.create_widgets()

    def create_widgets(self):
        self.state_text = tk.Text(self, height=18, width=60, state="disabled")
        self.state_text.pack(pady=10)

        self.load_btn = ttk.Button(self, text="Načti stav klimatizace", command=self.load_state)
        self.load_btn.pack(pady=5)

        self.refresh_btn = ttk.Button(self, text="Refresh stavu klimatizace", command=self.load_state)
        self.refresh_btn.pack(pady=5)

    def load_state(self):
        self.state_text.config(state="normal")
        self.state_text.delete(1.0, tk.END)
        try:
            status = run_async(get_ac_state())
            if not status:
                self.state_text.insert(tk.END, "Status není dostupný.\n")
            else:
                for prop, value in status.items():
                    if isinstance(value, dict):
                        for k, v in value.items():
                            self.state_text.insert(tk.END, f"{prop}.{k}: {v}\n")
                    elif isinstance(value, list):
                        self.state_text.insert(tk.END, f"{prop}: {value}\n")
                    else:
                        self.state_text.insert(tk.END, f"{prop}: {value}\n")
        except Exception as e:
            self.state_text.insert(tk.END, f"Chyba při načítání stavu: {e}\n")
        self.state_text.config(state="disabled")

if __name__ == "__main__":
    app = KlimaSimpleApp()
    app.mainloop()