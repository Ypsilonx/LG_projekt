# -*- coding: utf-8 -*-
"""
Interaktivní CLI rozhraní pro ovládání LG ThinQ klimatizace.
Legacy modul – pro nové použití preferujte main.py s --mode cli.
"""
import asyncio
from server_api import ThinQAPI, get_ac_device_id
from klima_logic import get_power_payload

DEVICE_ID = get_ac_device_id()

async def main():
    """Interaktivní CLI: zobrazí stav klimatizace a umožní zapnutí/vypnutí."""
    api = ThinQAPI()
    try:
        status = await api.get_device_status(DEVICE_ID)
        print("Aktuální stav klimatizace:", status)
        power_state = status.get("operation", {}).get("airConOperationMode")
        print(f"Stav zařízení: {power_state}")
        power_on = input("Zapnout klimatizaci? (a/n): ").lower() == "a"
        if not power_on and power_state == "POWER_OFF":
            print("Zařízení je již vypnuté. Nebyl odeslán žádný příkaz.")
            return
        if power_on and power_state == "POWER_ON":
            print("Zařízení je již zapnuté. Nebyl odeslán žádný příkaz.")
            return
        payload = get_power_payload("POWER_ON" if power_on else "POWER_OFF")
        result = await api.send_device_command(DEVICE_ID, payload)
        print("Výsledek příkazu:", result)
    except Exception as e:
        print(f"Chyba: {e}")
    finally:
        await api.close()

if __name__ == "__main__":
    asyncio.run(main())
