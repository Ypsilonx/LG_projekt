import asyncio
import json
import sys
sys.path.append('src')
from server_api import get_api, get_device_status

DEVICE_ID = "ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e"

async def test():
    api, session = await get_api()
    try:
        status = await get_device_status(api, DEVICE_ID)
        print('=== FULL DEVICE STATUS ===')
        print(json.dumps(status, indent=2))
        print('\n=== AVAILABLE KEYS ===')
        for key in status.keys():
            print(f"- {key}: {type(status[key])}")
            if isinstance(status[key], dict):
                for subkey in status[key].keys():
                    print(f"  - {key}.{subkey}")
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(test())
