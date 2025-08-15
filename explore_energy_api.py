import asyncio
import json
import sys
sys.path.append('src')
from server_api import get_api

DEVICE_ID = "ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e"

async def explore_api_endpoints():
    """Zkouší různé API endpointy pro získání dat o spotřebě energie"""
    api, session = await get_api()
    try:
        # Standardní device status (už známe)
        status = await get_device_status(api, DEVICE_ID)
        
        # Zkusíme další možné endpointy
        possible_endpoints = [
            "getDeviceEnergy",
            "getEnergyConsumption", 
            "getPowerUsage",
            "getDeviceStatistics",
            "getDeviceMonitoring",
            "getDeviceInfo",
            "getDeviceDetails"
        ]
        
        for endpoint in possible_endpoints:
            try:
                if hasattr(api, endpoint):
                    print(f"\n=== Trying {endpoint} ===")
                    result = await getattr(api, endpoint)(DEVICE_ID)
                    print(f"SUCCESS: {json.dumps(result, indent=2)}")
                else:
                    print(f"Endpoint {endpoint} not available")
            except Exception as e:
                print(f"Failed {endpoint}: {e}")
                
        # Zkusíme získat kompletní profile zařízení
        try:
            print(f"\n=== Device Profile ===")
            profile = await api.get_device_profile(DEVICE_ID)
            print(f"Profile: {json.dumps(profile, indent=2)}")
        except Exception as e:
            print(f"Profile failed: {e}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await session.close()

async def get_device_status(api, device_id):
    """Pomocná funkce"""
    return await api.get_device_status(device_id)

if __name__ == "__main__":
    asyncio.run(explore_api_endpoints())
