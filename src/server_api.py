import json
import aiohttp
from thinqconnect import ThinQApi

# Načtení konfiguračních údajů
with open("data/config.json", encoding="utf-8") as f:
    config = json.load(f)

ACCESS_TOKEN = config["access_token"]
COUNTRY_CODE = config["country_code"]
CLIENT_ID = config["client_id"]

async def get_api():
    session = aiohttp.ClientSession()
    api = ThinQApi(
        access_token=ACCESS_TOKEN,
        country_code=COUNTRY_CODE,
        client_id=CLIENT_ID,
        session=session
    )
    return api, session

async def get_device_status(api, device_id):
    return await api.async_get_device_status(device_id)

async def send_device_command(api, device_id, payload):
    return await api.async_post_device_control(device_id, payload)

# Další funkce pro komunikaci se serverem lze přidávat sem
