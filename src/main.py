
"""
Hlavní vstupní bod pro LG ThinQ klimatizační aplikaci.
Podporuje jak CLI, tak GUI režim s pokročilými funkcemi včetně plánování.
"""
import sys
import argparse
import asyncio
from pathlib import Path

# Zajistíme, že Python najde naše moduly
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Hlavní funkce aplikace"""
    parser = argparse.ArgumentParser(description="LG ThinQ Klimatizace - Ovládání & Plánování")
    parser.add_argument("--mode", choices=["gui", "cli"], default="gui", 
                       help="Režim spuštění: gui (výchozí) nebo cli")
    parser.add_argument("--device-id", type=str,
                       help="ID zařízení (pro CLI režim)")
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
        
        if args.status:
            # Zobrazení stavu zařízení
            asyncio.run(cli_show_status(args.device_id))
        elif args.command:
            # Provedení příkazu
            asyncio.run(cli_execute_command(args.device_id, args.command))
        else:
            print("Pro CLI režim zadejte --status nebo --command")
            parser.print_help()

def run_cli():
    """Spuštění CLI režimu (zpětná kompatibilita)"""
    import frontend

def run_gui():
    """Spuštění GUI režimu"""
    try:
        from gui.app import main as gui_main
        gui_main()
    except ImportError as e:
        print(f"Chyba při importu GUI modulů: {e}")
        print("Zkuste nainstalovat potřebné závislosti: pip install tkinter")
        sys.exit(1)

async def cli_show_status(device_id=None):
    """CLI funkce pro zobrazení stavu zařízení"""
    try:
        from server_api import ThinQAPI
        
        api = ThinQAPI()
        await api.initialize()
        
        # Použití výchozího device_id, pokud není zadáno
        if not device_id:
            device_id = "ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e"
            
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

async def cli_execute_command(device_id, command):
    """CLI funkce pro provedení příkazu"""
    try:
        from server_api import ThinQAPI
        from klima_logic import create_control_payload
        
        api = ThinQAPI()
        await api.initialize()
        
        if not device_id:
            device_id = "ef279add7b418795378e9d20631cd85d86aa5e356a7e4599584434c4ead89c4e"
        
        # Parsing příkazů
        if command.lower() == "power_on":
            payload = create_control_payload("power", "POWER_ON")
        elif command.lower() == "power_off":
            payload = create_control_payload("power", "POWER_OFF")
        elif command.lower().startswith("mode_"):
            mode = command.replace("mode_", "").upper()
            payload = create_control_payload("mode", mode)
        elif command.lower().startswith("temp_"):
            temp = float(command.replace("temp_", ""))
            payload = create_control_payload("temperature", temp)
        else:
            print(f"Neznámý příkaz: {command}")
            print("Dostupné příkazy: power_on, power_off, mode_cool, mode_heat, mode_fan, mode_auto, temp_22, atd.")
            return
        
        result = await api.send_device_command(device_id, payload)
        print(f"Příkaz '{command}' úspěšně odeslán: {result}")
        
        await api.close()
        
    except Exception as e:
        print(f"Chyba při provádění příkazu: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Nový režim s argumenty
        main()
    else:
        # Zpětná kompatibilita - spustí GUI jako výchozí
        run_gui()
