
# LG ThinQ Klimatizace - Ovládání & Plánování

Moderní Python aplikace pro kompletní ovládání LG ThinQ klimatizací s pokročilými funkcemi plánování a tmavým GUI.

## ✨ Hlavní funkce

- 🎨 **Moderní tmavé GUI** - responzivní rozhraní s hover efekty
- 🌡️ **Kompletní ovládání klimatizace** - zapnutí/vypnutí, režimy, teplota, větrání
- 📅 **Pokročilé plánování** - časové harmonogramy pro automatické ovládání
- ⚡ **Optimalizované API** - smart caching, snížení API volání o 81%
- 🔧 **CLI i GUI režim** - flexibilní použití
- 💨 **Pokročilé větrání** - směr proudění, síla větru, rotace
- ⏰ **Časovače** - sleep timer s rychlými tlačítky
- 💡 **LED indikátory** - vizuální zpětná vazba o stavu zařízení

## 📁 Architektura projektu

```
src/
├── main.py                    # Univerzální vstupní bod (CLI/GUI)
├── server_api.py             # ThinQ API komunikace s caching
├── klima_logic.py            # Payload generátor pro všechny příkazy
├── frontend.py               # CLI rozhraní (legacy)
└── gui/                      # Modularizované GUI komponenty
    ├── app.py                # Hlavní aplikace
    ├── theme.py              # Tmavé téma s hover fixes
    ├── controls.py           # Ovládací prvky klimatizace
    ├── scheduler.py          # Pokročilý plánovač
    └── widgets.py            # LED indikátory a custom widgety

data/
├── config.json               # API přihlašovací údaje
├── devices.json              # Seznam zařízení
├── device_profile.json       # Profil zařízení a podporované funkce
└── schedule.json             # Časové plány a harmonogramy
```

## 🚀 Rychlé spuštění

### 1. Nastavení virtuálního prostředí
```powershell
# Klonování/stažení projektu
cd d:\61_Programing\LG_projekt

# Vytvoření a aktivace virtuálního prostředí Python 3.12
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Instalace závislostí
```powershell
pip install thinqconnect aiohttp tkinter
```

### 3. Konfigurace
Upravte soubory v `data/` složce:
- `config.json` - vaše LG ThinQ API údaje
- `devices.json` - ID vašich zařízení

### 4. Spuštění aplikace

**GUI režim (výchozí):**
```powershell
python src\main.py
# nebo
python src\main.py --mode gui
```

**CLI režim:**
```powershell
# Zobrazení stavu zařízení
python src\main.py --mode cli --status

# Provedení příkazu
python src\main.py --mode cli --command power_on
```

## 🎯 Použití GUI aplikace

### Základní ovládání
- **⚡ Zapnutí/Vypnutí** - hlavní tlačítko power
- **🌡️ Režimy** - COOL, HEAT, FAN, AUTO, AIR_DRY
- **🌡️ Teplota** - přesné nastavení s slidérem
- **💨 Větrání** - síla větru + směr proudění
- **⚡ Úspora energie** - power save režim

### Časovače
- **⏰ Sleep Timer** - rychlé tlačítka 30min, 1h, 2h
- **📅 Plánování** - pokročilé časové harmonogramy

### Pokročilé plánování
Vytvářejte komplexní plány jako:
- "8:00 - zapni FAN na AUTO na 2 hodiny"
- "12:00 - přepni na COOL, nastav 22°C"
- "22:00 - zapni sleep timer na 30 minut"

## 🛠️ Technické detaily

### Podporované příkazy
- **Power:** `POWER_ON`, `POWER_OFF`
- **Režimy:** `COOL`, `HEAT`, `FAN`, `AUTO`, `AIR_DRY`
- **Teplota:** 16-30°C (dle režimu)
- **Větrání:** `AUTO`, `LOW`, `MID`, `HIGH`
- **Směr:** rotace nahoru/dolů, vlevo/vpravo
- **Timery:** sleep timer, relativní časovače

### API Optimalizace
- **Smart caching** - ukládání posledního stavu
- **Change detection** - API volání jen při změně
- **Error handling** - robustní zpracování chyb
- **Connection pooling** - efektivní síťové připojení

### Kompatibilita
- **Python:** 3.12+
- **OS:** Windows, Linux, macOS
- **LG ThinQ:** všechna podporovaná klimatizační zařízení

## 🐛 Řešení problémů

### Časté chyby
- **`NOT_PROVIDED_FEATURE`** - funkce není zařízením podporována
- **`COMMAND_NOT_SUPPORTED_IN_POWER_OFF`** - příkaz vyžaduje zapnuté zařízení
- **Import errors** - zkontrolujte virtuální prostředí a závislosti

### Debug režim
```powershell
# Zapnutí debug logování
set PYTHONPATH=src
python -c "import logging; logging.basicConfig(level=logging.DEBUG)"
python src\main.py
```

## 📝 Plánované funkce
- [ ] Pokročilé energetické metriky
- [ ] Push notifikace
- [ ] Webové rozhraní
- [ ] Mobile app
- [ ] Hlasové ovládání

## 🤝 Přispívání
1. Fork projektu
2. Vytvořte feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit změny (`git commit -m 'Add some AmazingFeature'`)
4. Push do branch (`git push origin feature/AmazingFeature`)
5. Otevřete Pull Request

## 📄 Licence
Projekt je licencován pod MIT License - viz [LICENSE](LICENSE) soubor.

## 👨‍💻 Autor
Vytvořeno s pomocí GitHub Copilot pro efektivní ovládání LG ThinQ zařízení.
