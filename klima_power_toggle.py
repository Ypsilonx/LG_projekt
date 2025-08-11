import os
import asyncio
import uuid
import aiohttp
import traceback
import json
from thinqconnect import ThinQApi
from aiohttp import ClientTimeout

# Oprava bugů s timeoutem v proměnných prostředí
for key in list(os.environ.keys()):
    if "TIMEOUT" in key.upper():
        val = os.environ[key]
        try:
            os.environ[key] = str(int(float(val)))
        except Exception:
            del os.environ[key]

ACCESS_TOKEN = "thinqpat_72547fb563e6b9b202d9a45ca8d582e1bcac54da66c7b47e110e"
COUNTRY_CODE = "CZ"
CLIENT_ID = str(uuid.uuid4())
DEVICE_ID = "ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e"

def find_power_state(status):
    # Zkusíme různé varianty, vypíšeme vše pro ladění
    print("\n--- RAW STATUS ---")
    print(json.dumps(status, indent=2, ensure_ascii=False))
    print("--- END RAW STATUS ---\n")
    # Nejčastější varianty
    if isinstance(status, dict):
        if "operation" in status:
            op = status["operation"]
            if isinstance(op, dict) and "airConOperationMode" in op:
                return op["airConOperationMode"]
            if isinstance(op, str):
                return op
        if "airConOperationMode" in status:
            return status["airConOperationMode"]
    return None

async def main():
    try:
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=None)) as session:
            api = ThinQApi(
                access_token=ACCESS_TOKEN,
                country_code=COUNTRY_CODE,
                client_id=CLIENT_ID,
                session=session
            )
            status = await api.async_get_device_status(DEVICE_ID)
            current = find_power_state(status)
            print(f"Aktuální stav: {current}")
            if current == "POWER_ON":
                print("Vypínám klimatizaci...")
                await api.async_post_device_control(DEVICE_ID, {"operation": {"airConOperationMode": "POWER_OFF"}})
            else:
                print("Zapínám klimatizaci...")
                await api.async_post_device_control(DEVICE_ID, {"operation": {"airConOperationMode": "POWER_ON"}})
            new_status = await api.async_get_device_status(DEVICE_ID)
            print(f"Nový stav: {find_power_state(new_status)}")
    except Exception as e:
        print("Chyba:", e)
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
