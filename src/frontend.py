import asyncio
from src.server_api import get_api, get_device_status, send_device_command
from src.klima_logic import get_power_payload

DEVICE_ID = "ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e"  # upravte dle potřeby

async def main():
    api, session = await get_api()
    status = await get_device_status(api, DEVICE_ID)
    print("Aktuální stav klimatizace:", status)
    power_on = input("Zapnout klimatizaci? (a/n): ").lower() == "a"
    payload = get_power_payload(power_on)
    result = await send_device_command(api, DEVICE_ID, payload)
    print("Výsledek příkazu:", result)
    await session.close()

if __name__ == "__main__":
    asyncio.run(main())
