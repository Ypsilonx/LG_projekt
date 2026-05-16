# -*- coding: utf-8 -*-
"""
Hlavní vstupní bod pro LG ThinQ klimatizační aplikaci.
Podporuje jak CLI, tak GUI režim s pokročilými funkcemi včetně plánování.
"""
import sys
import argparse
import asyncio
from pathlib import Path
from typing import Any

# Zajistíme, že Python najde naše moduly
sys.path.insert(0, str(Path(__file__).parent))
from server_api import get_ac_device_id, get_device_id_by_alias, list_devices
from command_policy import build_command_plan

def main():
    """Hlavní funkce aplikace"""
    parser = argparse.ArgumentParser(description="LG ThinQ Klimatizace - Ovládání & Plánování")
    parser.add_argument("--mode", choices=["gui", "cli"], default="gui", 
                       help="Režim spuštění: gui (výchozí) nebo cli")
    parser.add_argument("--list-devices", action="store_true",
                       help="Vypíše dostupná zařízení z devices.json (CLI)")
    parser.add_argument("--device-id", type=str,
                       help="ID zařízení (pro CLI režim)")
    parser.add_argument("--device-alias", type=str,
                       help="Alias zařízení z devices.json (pro CLI režim)")
    parser.add_argument("--command", type=str,
                       help="Příkaz pro zařízení (pro CLI režim)")
    parser.add_argument("--status", action="store_true",
                       help="Zobrazit stav zařízení (CLI)")
    
    args = parser.parse_args()
    
    if args.mode == "gui":
        run_gui()
    elif args.mode == "cli":
        # CLI režim
        print("LG ThinQ Klimatizace - CLI režim")
        
        if args.list_devices:
            cli_list_devices()
        elif args.status:
            # Zobrazení stavu zařízení
            asyncio.run(cli_show_status(args.device_id, args.device_alias))
        elif args.command:
            # Provedení příkazu
            asyncio.run(cli_execute_command(args.device_id, args.command, args.device_alias))
        else:
            print("Pro CLI režim zadejte --status, --command nebo --list-devices")
            parser.print_help()

def run_cli():
    """Spuštění interaktivního CLI režimu (zpětná kompatibilita)."""
    import frontend
    asyncio.run(frontend.main())

def run_gui():
    """Spuštění GUI režimu"""
    try:
        from gui.app import main as gui_main
        gui_main()
    except ImportError as e:
        print(f"Chyba při importu GUI modulů: {e}")
        print("Zkuste nainstalovat potřebné závislosti: pip install tkinter")
        sys.exit(1)

def resolve_device_id(device_id: str | None = None, device_alias: str | None = None) -> str:
    """
    Vyhodnotí cílové zařízení z argumentů CLI.

    Args:
        device_id: Explicitní Device ID
        device_alias: Alias zařízení z devices.json

    Returns:
        str: Výsledné Device ID

    Raises:
        ValueError: Pokud je zadán neplatný alias nebo kombinace argumentů
    """
    if device_id:
        return device_id
    if device_alias:
        return get_device_id_by_alias(device_alias)
    return get_ac_device_id()


def cli_list_devices():
    """Vypíše seznam zařízení načtených z devices.json."""
    try:
        devices = list_devices()
        if not devices:
            print("V devices.json nebyla nalezena žádná zařízení.")
            return

        print("\nDostupná zařízení:")
        print("-" * 72)
        print(f"{'Alias':<20} {'Typ':<28} {'ID (zkráceně)':<20}")
        print("-" * 72)

        for device in devices:
            alias = device.get("alias") or "(bez aliasu)"
            dev_type = device.get("device_type") or "(neznámý typ)"
            dev_id = device.get("device_id") or "(bez ID)"
            short_id = f"{dev_id[:8]}..." if len(dev_id) > 8 else dev_id
            print(f"{alias:<20} {dev_type:<28} {short_id:<20}")

    except Exception as e:
        print(f"Chyba při načítání zařízení: {e}")


async def cli_show_status(device_id=None, device_alias=None):
    """CLI funkce pro zobrazení stavu zařízení"""
    try:
        from server_api import ThinQAPI
        
        api = ThinQAPI()
        await api.initialize()
        
        # Použití zvoleného zařízení (ID, alias, nebo výchozí klimatizace)
        device_id = resolve_device_id(device_id, device_alias)
            
        status = await api.get_device_status(device_id)
        
        # Podle device_profile.json: kombinace runState a operation
        run_state = status.get("runState", {}).get("currentState", "N/A")
        power_operation = status.get("operation", {}).get("airConOperationMode", "N/A")
        
        print(f"\n=== Stav klimatizace (ID: {device_id[:8]}...) ===")
        print(f"Napájení: {power_operation} (Běh: {run_state})")
        print(f"Režim: {status.get('airConJobMode', {}).get('currentJobMode', 'N/A')}")
        print(f"Aktuální teplota: {status.get('temperature', {}).get('currentTemperature', 'N/A')}°C")
        print(f"Cílová teplota: {status.get('temperature', {}).get('targetTemperature', 'N/A')}°C")
        print(f"Síla větru: {status.get('airFlow', {}).get('windStrength', 'N/A')}")
        print(f"Úspora energie: {status.get('powerSave', {}).get('powerSaveEnabled', False)}")
        
        await api.close()
        
    except Exception as e:
        print(f"Chyba při získávání stavu: {e}")

async def cli_execute_command(device_id, command, device_alias=None):
    """CLI funkce pro provedení příkazu"""
    try:
        from server_api import ThinQAPI
        from klima_logic import create_control_payload
        
        api = ThinQAPI()
        await api.initialize()
        
        device_id = resolve_device_id(device_id, device_alias)

        internal_command, internal_args = parse_cli_command(command)

        status = await api.get_device_status(device_id)
        plan = build_command_plan(internal_command, internal_args, status)
        if plan.should_skip:
            print(f"Příkaz přeskočen: {plan.skip_reason}")
            await api.close()
            return

        for idx, step in enumerate(plan.steps):
            payload = create_payload_for_internal_command(
                step.command,
                step.args,
                status,
                create_control_payload,
            )

            if payload is None:
                print(f"Neznámý krok plánu: {step.command}")
                continue

            result = await api.send_device_command(device_id, payload)
            print(f"Příkaz '{step.command}' úspěšně odeslán: {result}")

            status = apply_status_hint(status, step.command, step.args)

            is_last = idx == len(plan.steps) - 1
            if not is_last and step.delay_after_seconds > 0:
                await asyncio.sleep(step.delay_after_seconds)
        
        await api.close()
        
    except Exception as e:
        print(f"Chyba při provádění příkazu: {e}")


def parse_cli_command(command: str) -> tuple[str, tuple[Any, ...]]:
    """
    Přeloží textový CLI příkaz na interní příkaz a argumenty.

    Args:
        command: Hodnota z argumentu --command

    Returns:
        tuple[str, tuple[Any, ...]]: Interní příkaz a jeho argumenty

    Raises:
        ValueError: Pokud příkaz není podporován
    """
    command_lower = command.lower()

    if command_lower == "power_on":
        return "power_on", ()
    if command_lower == "power_off":
        return "power_off", ()
    if command_lower.startswith("mode_"):
        mode = command.replace("mode_", "").upper()
        return "change_mode", (mode,)
    if command_lower.startswith("temp_"):
        temp = float(command.replace("temp_", ""))
        return "set_temperature", (temp,)

    raise ValueError(
        "Neznámý příkaz. Dostupné: power_on, power_off, mode_cool, mode_heat, "
        "mode_fan, mode_auto, temp_22, atd."
    )


def create_payload_for_internal_command(
    command: str,
    args: tuple[Any, ...],
    status: dict,
    create_control_payload,
) -> dict | None:
    """
    Vytvoří payload pro interní krok příkazu.

    Args:
        command: Interní název příkazu
        args: Argumenty kroku
        status: Aktuální snapshot stavu
        create_control_payload: Tovární funkce payloadů

    Returns:
        dict | None: Payload pro API, nebo None při neznámém příkazu
    """
    if command == "power_on":
        return create_control_payload("power", "POWER_ON")
    if command == "power_off":
        return create_control_payload("power", "POWER_OFF")
    if command == "toggle_power":
        current_power = status.get("operation", {}).get("airConOperationMode", "POWER_OFF")
        target = "POWER_ON" if current_power == "POWER_OFF" else "POWER_OFF"
        return create_control_payload("power", target)
    if command == "change_mode":
        return create_control_payload("mode", args[0])
    if command == "set_temperature":
        return create_control_payload("temperature", args[0])
    if command == "set_wind_strength":
        return create_control_payload("wind_strength", args[0])
    if command == "set_wind_direction":
        return create_control_payload("wind_direction", args[0], args[1])
    if command == "set_power_save":
        return create_control_payload("power_save", args[0])
    if command == "set_sleep_timer":
        return create_control_payload("sleep_timer", args[0], args[1])
    if command == "cancel_all_timers":
        return create_control_payload("cancel_timers")
    return None


def apply_status_hint(status: dict, command: str, args: tuple[Any, ...]) -> dict:
    """
    Aplikuje odhad lokální změny stavu po úspěšném příkazu v CLI.

    Args:
        status: Aktuální snapshot stavu
        command: Provedený interní příkaz
        args: Argumenty příkazu

    Returns:
        dict: Aktualizovaný snapshot stavu
    """
    if command == "power_on":
        status.setdefault("operation", {})["airConOperationMode"] = "POWER_ON"
    elif command == "power_off":
        status.setdefault("operation", {})["airConOperationMode"] = "POWER_OFF"
    elif command == "change_mode":
        status.setdefault("airConJobMode", {})["currentJobMode"] = args[0]
    elif command == "set_temperature":
        status.setdefault("temperature", {})["targetTemperature"] = args[0]
    elif command == "set_wind_strength":
        status.setdefault("airFlow", {})["windStrength"] = args[0]
    elif command == "set_wind_direction":
        wind = status.setdefault("windDirection", {})
        wind["rotateUpDown"] = bool(args[0])
        wind["rotateLeftRight"] = bool(args[1])
    elif command == "set_power_save":
        status.setdefault("powerSave", {})["powerSaveEnabled"] = bool(args[0])

    return status

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Nový režim s argumenty
        main()
    else:
        # Zpětná kompatibilita - spustí GUI jako výchozí
        run_gui()
