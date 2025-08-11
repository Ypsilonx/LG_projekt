import asyncio
import uuid
import aiohttp
from thinqconnect import ThinQApi

# ---------- ZDE VLOŽTE SVÉ ÚDAJE ----------
ACCESS_TOKEN = "thinqpat_72547fb563e6b9b202d9a45ca8d582e1bcac54da66c7b47e110e"
COUNTRY_CODE = "CZ"
# -------------------------------------------

# Každý klient musí mít unikátní ID, uuid4 je pro to ideální
CLIENT_ID = str(uuid.uuid4())

async def main():
    """Připojí se k LG API pomocí tokenu a vypíše zařízení."""
    
    async with aiohttp.ClientSession() as session:
        # Vytvoření API klienta s vaším tokenem a údaji
        api = ThinQApi(
            access_token=ACCESS_TOKEN,
            country_code=COUNTRY_CODE,
            client_id=CLIENT_ID,
            session=session
        )

        print("Načítám zařízení pomocí API tokenu...")
        
        try:
            devices = await api.async_get_device_list()
            import json
            print("\n>>> RAW odpověď ze serveru na /devices:")
            print(json.dumps(devices, indent=2, ensure_ascii=False))

            # Uložení RAW odpovědi do JSON souboru
            with open("devices.json", "w", encoding="utf-8") as f:
                json.dump(devices, f, indent=2, ensure_ascii=False)

            print("\n>>> Nalezená zařízení na tvém účtu:")
            if not devices:
                print("  Žádná zařízení nebyla nalezena.")
            for device in devices:
                info = device.get('deviceInfo', {})
                print(f"  - Typ:    {info.get('deviceType')}")
                print(f"    Model:  {info.get('modelName')}")
                print(f"    Název:  {info.get('alias')}")
                print(f"    ID:     {device.get('deviceId')}\n")
        except Exception as e:
            print(f"Došlo k chybě: {e}")

if __name__ == "__main__":
    asyncio.run(main())