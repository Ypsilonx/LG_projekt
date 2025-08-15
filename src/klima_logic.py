# Logika pro ovládání klimatizace

def get_power_payload(power_on: bool):
    """Vrací payload pro zapnutí/vypnutí klimatizace."""
    return {"operation": {"airConOperationMode": "POWER_ON" if power_on else "POWER_OFF"}}

# Další logiku (např. nastavení teploty, režimu) lze přidávat sem

def get_mode_payload(mode: str):
    return {"airConJobMode": {"currentJobMode": mode}}

# Validace, transformace, příprava payloadů atd.
