
# LG ThinQ – Ovládání klimatizace v Pythonu

Tento projekt umožňuje číst stav a ovládat klimatizaci LG ThinQ pomocí Pythonu a knihovny `thinqconnect`. Součástí je i jednoduché GUI pro pohodlné ovládání.

## Soubory a jejich účel

- `thinq_connection.py` – Získání a výpis všech zařízení na účtu LG, uložení do `devices.json`.
- `klima_skript.py` – Stažení a uložení profilu konkrétního zařízení do `device_profile.json`.
- `klima_gui.py` – Hlavní GUI aplikace pro čtení i ovládání klimatizace (Tkinter, async).
- `gui_klima_stav.py` – Jednodušší GUI pouze pro čtení stavu klimatizace.
- `devices.json`, `device_profile.json` – Uložená data o zařízeních a jejich profilech (cache, neukládejte do veřejného repozitáře).
- `KLIMATIZACE_OVLADANI.md` – Přehled možností ovládání klimatizace, příklady volání API.
- `.gitignore` – Nastavení ignorovaných souborů (včetně citlivých dat a prostředí).

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
3. Získejte a nastavte přístupové tokeny (viz dokumentace thinqconnect).
4. Získejte seznam zařízení:
   ```powershell
   python thinq_connection.py
   ```
5. Stáhněte profil klimatizace:
   ```powershell
   python klima_skript.py
   ```
6. Spusťte GUI:
   ```powershell
   python klima_gui.py
   ```

## Bezpečnost a soukromí

- Nikdy nesdílejte své tokeny, `devices.json` ani `device_profile.json` veřejně.
- `.gitignore` je nastaven tak, aby chránil citlivé údaje a dočasné soubory.

## Další informace

- Pro detailní možnosti ovládání klimatizace viz `KLIMATIZACE_OVLADANI.md`.
- Pokud chcete rozšířit GUI o další funkce, upravte `klima_gui.py` dle potřeby.
