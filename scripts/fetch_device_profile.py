# -*- coding: utf-8 -*-
"""
Jednorázový utility skript – stáhne aktuální profil zařízení z LG ThinQ API
a uloží jej do data/device_profile.json.

Použití (z kořene projektu, s aktivovaným venv):
    python scripts/fetch_device_profile.py

Skript automaticky vybere klimatizaci (DEVICE_AIR_CONDITIONER) ze souboru
data/devices.json. Pokud chcete jiný device_id, předejte ho jako argument:
    python scripts/fetch_device_profile.py <device_id>
"""

import asyncio
import json
import sys
from pathlib import Path

# Přidáme src/ do path aby fungovaly importy
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from server_api import ThinQAPI  # noqa: E402


def _find_ac_device_id() -> str | None:
    """Načte device_id klimatizace z data/devices.json."""
    devices_file = ROOT / "data" / "devices.json"
    if not devices_file.exists():
        return None
    try:
        devs = json.loads(devices_file.read_text(encoding="utf-8"))
        for d in devs:
            if d.get("deviceInfo", {}).get("deviceType") == "DEVICE_AIR_CONDITIONER":
                return d.get("deviceId")
    except Exception as exc:
        print(f"Chyba při čtení devices.json: {exc}")
    return None


async def main() -> None:
    # Zjistit device_id
    if len(sys.argv) > 1:
        device_id = sys.argv[1]
        print(f"Používám device_id z argumentu: {device_id[:12]}...")
    else:
        device_id = _find_ac_device_id()
        if not device_id:
            print("❌ Nepodařilo se najít klimatizaci v data/devices.json")
            sys.exit(1)
        print(f"Nalezena klimatizace: {device_id[:12]}...")

    # Stáhnout profil
    api = ThinQAPI()
    print("Inicializuji ThinQAPI...")
    await api.initialize()

    print("Stahuji profil zařízení z API...")
    profile = await api.get_device_profile(device_id)

    # Uložit
    out_file = ROOT / "data" / "device_profile.json"
    out_file.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ Profil uložen do: {out_file.relative_to(ROOT)}")
    print(f"   Počet vlastností (top-level): {len(profile)}")

    await api.close()


if __name__ == "__main__":
    asyncio.run(main())
