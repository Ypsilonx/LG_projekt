# LG Projekt

Tento projekt slouží k ovládání a monitorování zařízení LG ThinQ (např. klimatizace) pomocí Pythonu.

## Složky a soubory
- `find_device.py` – Skript pro načtení a výpis zařízení z LG API (ollo69/wideq).
- `thinq_connection.py` – Skript pro získání dat ze zařízení pomocí knihovny thinqconnect.
- `klima_skript.py` – Skript pro stažení a uložení profilu zařízení.
- `klima_gui.py` – GUI aplikace pro zobrazení stavu klimatizace (Tkinter).
- `device_profile.json`, `devices.json` – Uložená data o zařízeních a profilech.
- `KLIMATIZACE_OVLADANI.md` – Dokumentace k ovládání klimatizace.
- `.gitignore` – Ignorované soubory a složky (např. .venv, citlivá data).

## Požadavky
- Python 3.12
- Virtuální prostředí (`.venv`)
- Knihovny: thinqconnect, aiohttp, tkinter

## První spuštění
1. Vytvořte a aktivujte virtuální prostředí:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
2. Nainstalujte závislosti:
   ```powershell
   pip install thinqconnect aiohttp
   ```
3. Spusťte skripty dle potřeby (viz výše).

## Poznámky
- Pro správné fungování je nutné mít vygenerované tokeny a profily zařízení.
- Pokud chcete rozšířit GUI o ovládání klimatizace, kontaktujte autora nebo přidejte vlastní funkce.
