import asyncio
import uuid
import aiohttp
from thinqconnect import ThinQApi

ACCESS_TOKEN = "thinqpat_72547fb563e6b9b202d9a45ca8d582e1bcac54da66c7b47e110e"  # váš token
COUNTRY_CODE = "CZ"
CLIENT_ID = str(uuid.uuid4())    # např. uuid.uuid4()
DEVICE_ID = "ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e"

async def main():
    async with aiohttp.ClientSession() as session:
        api = ThinQApi(
            access_token=ACCESS_TOKEN,
            country_code=COUNTRY_CODE,
            client_id=CLIENT_ID,
            session=session
        )
        # Získání profilu zařízení
        profile = await api.async_get_device_profile(DEVICE_ID)
        import json
        # Ulož profil do souboru
        with open("device_profile.json", "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
        print("Profil zařízení byl uložen do device_profile.json")

if __name__ == "__main__":
    asyncio.run(main())