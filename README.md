# LG ThinQ – Modulární projekt pro ovládání klimatizace

Tento projekt je rozdělen do přehledných modulů pro snadné rozšiřování a údržbu:

## Struktura projektu

- `data/config.json` – Konfigurační soubor s klíči/tokeny pro přihlášení (odděleně od zařízení).
- `data/devices.json`, `data/device_profile.json` – Data o zařízeních a profilech (cache, neukládejte do veřejného repozitáře).
- `src/server_api.py` – Modul pro komunikaci se serverem (autentizace, získání dat, odesílání příkazů).
- `src/klima_logic.py` – Modul s logikou pro ovládání klimatizace (generování payloadů, validace).
- `src/frontend.py` – Frontend aplikace (CLI/GUI), pouze interakce s uživatelem.
- `src/main.py` – Vstupní bod projektu, propojuje moduly (lze rozšiřovat).
- Další skripty (např. `klima_gui.py`, `KLIMATIZACE_OVLADANI.md`) lze přidávat dle potřeby.

## Požadavky

- Python 3.12
- Virtuální prostředí (`.venv`)
- Knihovny: `thinqconnect`, `aiohttp`, `tkinter` (součástí standardní knihovny)

## Rychlý start

1. Vytvořte a aktivujte virtuální prostředí:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
2. Nainstalujte závislosti:
   ```powershell
   pip install thinqconnect aiohttp
   ```
3. Zadejte své klíče do `data/config.json`.
4. Spusťte frontend:
   ```powershell
   python src/frontend.py
   ```

## Bezpečnost a rozšiřitelnost

- Nikdy nesdílejte své tokeny, `devices.json` ani `device_profile.json` veřejně.
- `.gitignore` chrání citlivé údaje a dočasné soubory.
- Každý modul je samostatný, lze snadno přidávat nové funkce (např. další zařízení, GUI, automatizace).

## Ovládání klimatizace – příklad

Pro zapnutí/vypnutí klimatizace použijte funkci:
```python
from src.klima_logic import get_power_payload
payload = get_power_payload(True)  # Zapnout
payload = get_power_payload(False) # Vypnout
```
a odešlete ji pomocí:
```python
from src.server_api import send_device_command
await send_device_command(api, DEVICE_ID, payload)
```

Správné klíče a hodnoty najdete vždy v `device_profile.json`.

- Pro detailní možnosti ovládání klimatizace viz `KLIMATIZACE_OVLADANI.md`.
