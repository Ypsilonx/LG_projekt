"""
Logika pro vytváření příkazů a payloadů pro LG ThinQ klimatizaci.
Obsahuje všechny typy kontrolních příkazů.
"""
import logging

logger = logging.getLogger(__name__)

def create_control_payload(command_type: str, *args, **kwargs):
    """
    Univerzální funkce pro vytváření payloadů pro různé typy příkazů.
    
    Args:
        command_type: Typ příkazu (power, mode, temperature, wind_strength, atd.)
        *args: Poziční argumenty specifické pro typ příkazu
        **kwargs: Klíčové argumenty specifické pro typ příkazu
    
    Returns:
        dict: Payload pro ThinQ API
    """
    try:
        if command_type == "power":
            state = args[0] if args else "POWER_ON"
            # Pro LG ThinQ používáme operation.airConOperationMode podle device_profile.json
            return {"operation": {"airConOperationMode": state}}
        
        elif command_type == "mode":
            mode = args[0] if args else "AUTO"
            return {"airConJobMode": {"currentJobMode": mode}}
        
        elif command_type == "temperature":
            temperature = args[0] if args else 22
            mode = args[1] if len(args) > 1 else kwargs.get("mode")
            
            # Pouze celé stupně jako v oficiální LG mobilní aplikaci
            temp_rounded = round(float(temperature))  # Zaokrouhlení na celé číslo
            
            # Podle módu použijeme správné pole a rozsah podle device_profile.json
            if mode == "COOL":
                # Pro chlazení: rozsah 18-30°C
                temp_clamped = max(18, min(30, temp_rounded))
                temp_field = "coolTargetTemperature"
            elif mode == "HEAT":
                # Pro vytápění: rozsah 16-30°C  
                temp_clamped = max(16, min(30, temp_rounded))
                temp_field = "heatTargetTemperature"
            elif mode == "AUTO":
                # Pro automatický režim: rozsah 18-30°C
                temp_clamped = max(18, min(30, temp_rounded))
                temp_field = "autoTargetTemperature"
            else:
                # Fallback pro ostatní módy nebo když mód není specifikován
                temp_clamped = max(18, min(30, temp_rounded))
                temp_field = "targetTemperature"
            
            logger.info(f"Teplota: {temperature} -> zaokrouhleno: {temp_rounded} -> omezeno: {temp_clamped} (mód: {mode}, pole: {temp_field})")
            
            payload = {"temperature": {temp_field: temp_clamped}}
            # Pokud je specifikován mód, přidáme jej také
            if mode:
                payload["airConJobMode"] = {"currentJobMode": mode}
            return payload
        
        elif command_type == "wind_strength":
            strength = args[0] if args else "AUTO"
            return {"airFlow": {"windStrength": strength}}
        
        elif command_type == "wind_direction":
            updown = args[0] if args else False
            leftright = args[1] if len(args) > 1 else False
            return {
                "windDirection": {
                    "rotateUpDown": updown,
                    "rotateLeftRight": leftright
                }
            }
        
        elif command_type == "power_save":
            enabled = args[0] if args else False
            return {"powerSave": {"powerSaveEnabled": enabled}}
        
        elif command_type == "sleep_timer":
            hours = args[0] if args else 0
            minutes = args[1] if len(args) > 1 else 0
            total_minutes = hours * 60 + minutes
            return {
                "sleepTimer": {
                    "relativeStopTimer": "SET",
                    "relativeStopTimerTimeMinutes": total_minutes
                }
            }
        
        elif command_type == "cancel_timers":
            return {
                "timer": {
                    "relativeStartTimer": "UNSET",
                    "relativeStopTimer": "UNSET"
                },
                "sleepTimer": {
                    "relativeStopTimer": "UNSET"
                }
            }
        
        else:
            logger.warning(f"Neznámý typ příkazu: {command_type}")
            return {}
            
    except Exception as e:
        logger.error(f"Chyba při vytváření payloadu pro {command_type}: {e}")
        return {}

# Zpětná kompatibilita s původními funkcemi
def get_power_payload(power_state: str):
    """Zpětně kompatibilní funkce pro power payload"""
    return create_control_payload("power", power_state)

def get_mode_payload(mode: str):
    """Zpětně kompatibilní funkce pro mode payload"""
    return create_control_payload("mode", mode)

def get_temperature_payload(temperature: float, mode: str = None):
    """Vytvoření payloadu pro nastavení teploty"""
    return create_control_payload("temperature", temperature, mode)

def get_wind_payload(strength: str):
    """Vytvoření payloadu pro nastavení síly větru"""
    return create_control_payload("wind_strength", strength)

def get_wind_direction_payload(updown: bool = False, leftright: bool = False):
    """Vytvoření payloadu pro směr větru"""
    return create_control_payload("wind_direction", updown, leftright)

def get_power_save_payload(enabled: bool):
    """Vytvoření payloadu pro power save režim"""
    return create_control_payload("power_save", enabled)

def get_sleep_timer_payload(hours: int, minutes: int = 0):
    """Vytvoření payloadu pro sleep timer"""
    return create_control_payload("sleep_timer", hours, minutes)

def get_cancel_timers_payload():
    """Vytvoření payloadu pro zrušení všech timerů"""
    return create_control_payload("cancel_timers")
