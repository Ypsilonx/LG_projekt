# Ovládání klimatizace LG (RAC_056905_WW)

## Základní informace
- **Typ zařízení:** DEVICE_AIR_CONDITIONER
- **Model:** RAC_056905_WW
- **Název:** Klimatizace
- **ID:** ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e

## Možné akce a parametry

| Akce / Parametr                | Popis / Hodnoty (příklad)         |
|-------------------------------|-----------------------------------|
| Zapnout/Vypnout               | `set_current_job_mode('ON'/'OFF')`|
| Režim (chlazení, topení, auto)| `set_air_con_operation_mode('COOL'/'HEAT'/'AUTO')` |
| Cílová teplota (°C)           | `set_cool_target_temperature_c(22)`|
| Cílová teplota (°F)           | `set_cool_target_temperature_f(72)`|
| Úspora energie                | `set_power_save_enabled(True/False)`|
| Síla ventilátoru              | `set_wind_strength('LOW'/'MID'/'HIGH')`|
| Krok ventilátoru              | `set_wind_step(1/2/3/...)`        |
| Světlo displeje               | `set_display_light('ON'/'OFF')`   |
| Směr proudění (vert./horiz.)  | `set_wind_rotate_up_down(True/False)`<br>`set_wind_rotate_left_right(True/False)` |
| Časovač (relativní/absolutní) | `set_relative_time_to_start(hour, min)`<br>`set_absolute_time_to_stop(hour, min)` |

> **Poznámka:** Dostupné hodnoty závisí na konkrétním modelu. Nejprve si načtěte aktuální stav a profil zařízení.

## Ukázkový skript pro ovládání

```python
import asyncio
import aiohttp
from thinqconnect import ThinQApi
from thinqconnect.devices.air_conditioner import AirConditionerDevice

ACCESS_TOKEN = "..."
COUNTRY_CODE = "CZ"
CLIENT_ID = "..."
DEVICE_ID = "ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e"

async def main():
    async with aiohttp.ClientSession() as session:
        api = ThinQApi(
            access_token=ACCESS_TOKEN,
            country_code=COUNTRY_CODE,
            client_id=CLIENT_ID,
            session=session
        )
        # Získání objektu klimatizace
        ac = AirConditionerDevice(
            thinq_api=api,
            device_id=DEVICE_ID,
            device_type="DEVICE_AIR_CONDITIONER",
            model_name="RAC_056905_WW",
            alias="Klimatizace",
            reportable=True,
            profile={}  # Zde lze načíst profil, pokud je potřeba
        )
        # Příklad: nastavení režimu chlazení a teploty
        await ac.set_air_con_operation_mode("COOL")
        await ac.set_cool_target_temperature_c(22)
        await ac.set_wind_strength("HIGH")
        await ac.set_display_light("ON")
        print("Nastavení odesláno.")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Vizuální přehled

```
+---------------------+
|      KLIMATIZACE    |
+---------------------+
| Režim:   COOL/HEAT  |
| Teplota:   16-30°C  |
| Ventilátor: LOW-HIGH|
| Světlo:   ON/OFF    |
| Směr:     ↑ ↓ ← →   |
| Časovač:  ...       |
+---------------------+
```

- Pro detailní možnosti vždy nejprve načtěte profil zařízení a aktuální stav.
- Pokud potřebujete konkrétní hodnoty, použijte metody pro čtení stavu (viz dokumentace thinqconnect).
