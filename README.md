
# LG ThinQ Klimatizace - Ovládání & Plánování

Moderní Python aplikace pro kompletní ovládání LG ThinQ klimatizací s pokročilými funkcemi plánování a tmavým GUI.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: UTF-8](https://img.shields.io/badge/code%20style-UTF--8-brightgreen.svg)](https://en.wikipedia.org/wiki/UTF-8)

## ✨ Hlavní funkce

- 🎨 **Moderní tmavé GUI** - responzivní rozhraní s hover efekty
- 🧭 **Jasné režimy AUTO/HAND** - viditelný stav řízení s přepínačem v horním panelu
- 🌡️ **Kompletní ovládání klimatizace** - zapnutí/vypnutí, režimy, teplota, větrání
- 📅 **Pokročilé plánování (HAND)** - časové harmonogramy dostupné v ručním režimu
- 🌦️ **Sezónní pravidla automatiky** - chlazení jen ve vybraných obdobích (výchozí: léto)
- 🌤️ **ČHMÚ weather planning** - hodinový meteogram (POI 510) + fallback region RPZL, horizont 24h, refresh 3h
- 📊 **Vizualizace počasí v GUI** - graf intervalů, tabulka min/max a stav korekce AC čidla
- 🌡️ **Teplota čidla s offsetem** - UI zobrazuje pouze výslednou korigovanou hodnotu
- ⚡ **Energy reporting** - den/týden/měsíc/rok + export CSV
- ⚡ **Optimalizované API** - smart caching, automatické retry při chybách
- 🔧 **CLI i GUI režim** - flexibilní použití
- 💨 **Pokročilé větrání** - směr proudění, síla větru, rotace
- ⏰ **Časovače** - sleep timer s rychlými tlačítky
- 💡 **LED indikátory** - vizuální zpětná vazba o stavu zařízení
- 🌍 **Multi-platform** - Windows, Linux, macOS

## 📸 Screenshot

![LG ThinQ GUI](docs/screenshot.png)

## 🚀 Rychlé spuštění

### Předpoklady

- Python 3.12 nebo novější
- LG ThinQ účet s registrovanými klimatizacemi
- **LG Developer API přístup** (viz níže)

## 📁 Architektura projektu

```
src/
├── main.py                    # Univerzální vstupní bod (CLI/GUI)
├── server_api.py             # ThinQ API komunikace s caching
├── klima_logic.py            # Payload generátor pro všechny příkazy
├── energy_analytics.py       # Rozsahy energy dotazů + export CSV
├── weather_provider.py        # ČHMÚ provider + weather-based mode adjustments
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
├── schedule.json             # Časové plány a harmonogramy
└── automation_rules.json     # Sezónní pravidla automatizace
```

### � Krok 1: Získání LG ThinQ API přístupových údajů

**DŮLEŽITÉ:** Tento projekt vyžaduje API přihlašovací údaje od LG.

1. **Navštivte LG Developer Portal:**
   ```
   https://developer.lgaccount.com/
   ```

2. **Zaregistrujte se a vytvořte aplikaci:**
   - Přihlaste se nebo vytvořte nový účet
   - V sekci "My Applications" klikněte na "Create Application"
   - Vyplňte informace o aplikaci
   - Získáte: `Client ID`

3. **Autorizujte své zařízení:**
   - Propojte svůj LG ThinQ účet s vývojářskou aplikací
   - Vytvořte osobní access token (PAT) pro ThinQ API
   - Získejte seznam vašich zařízení a jejich ID

4. **Poznamenejte si tyto údaje:**
   - ✅ Access Token (PAT)
   - ✅ Client ID
   - ✅ Device ID (ID vaší klimatizace)

> 💡 **Tip:** Podrobný návod naleznete v [LG ThinQ Connect API dokumentaci](https://developer.lgaccount.com/thinq-connect)

---

### 🔧 Krok 2: Instalace projektu

#### Klonování repozitáře
```bash
git clone https://github.com/your-username/lg-thinq-climate-control.git
cd lg-thinq-climate-control
```

#### Vytvoření virtuálního prostředí
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
```

#### Instalace závislostí
```bash
pip install -r requirements.txt
```

---

### ⚙️ Krok 3: Konfigurace

#### Automatická inicializace (doporučeno)
```bash
python setup.py
```

Tento script automaticky:
- ✅ Vytvoří konfigurační soubory z šablon
- ✅ Připraví adresářovou strukturu
- ✅ Zobrazí další kroky

#### Manuální konfigurace

1. **Zkopírujte šablony:**
   ```bash
   cp data/config.json.example data/config.json
   cp data/devices.json.example data/devices.json
   cp data/schedule.json.example data/schedule.json
   cp data/automation_rules.json.example data/automation_rules.json
   ```

2. **Upravte `data/config.json`:**
   ```json
   {
       "access_token": "váš_access_token_zde",
       "country_code": "CZ",
       "client_id": "váš_client_id_zde"
   }
   ```

3. **Upravte `data/devices.json`:**
   ```json
   [
     {
          "deviceId": "vaše_device_id_zde",
          "deviceInfo": {
             "deviceType": "DEVICE_AIR_CONDITIONER",
             "modelName": "LG AC Model",
             "alias": "Obývací pokoj",
             "reportable": true
          }
     }
   ]
   ```

4. **(Volitelné) Upravte `data/automation_rules.json`:**
    ```json
    {
       "season_months": {
          "WINTER": [11, 12, 1, 2, 3],
          "TRANSITION": [4, 5, 9, 10],
          "SUMMER": [6, 7, 8]
       },
       "cooling_allowed_seasons": ["SUMMER"],
       "cooling_block_fallback_mode": "HEAT",
       "weather": {
          "enabled": true,
          "provider": "CHMI_METEOGRAM",
          "chmi_region_code": "RPZL",
          "chmi_location_label": "Bynina (Valasske Mezirici)",
          "chmi_meteogram_poi_id": "510",
          "chmi_meteogram_x": null,
          "chmi_meteogram_y": null,
          "sensor_offset_c": -2.0,
          "forecast_horizon_hours": 24,
          "refresh_interval_hours": 3,
          "use_short_term_forecast": true
       }
    }
    ```

    Výchozí pravidlo: mimo léto je režim `COOL` blokovaný a automatika použije fallback `HEAT`.
   Pokud je weather planner aktivní, automatika navíc využívá ČHMÚ forecast pro úpravu režimu
    směrem k úspoře energie (např. `COOL/HEAT -> FAN/AUTO`, pokud forecast i korigovaný senzor
   nepotvrzují potřebu topení/chlazení). Výchozí provider je `CHMI_METEOGRAM` (POI 510), při
   chybě se aplikace automaticky přepne na regionální `CHMI` fallback (`chmi_region_code`).

> ⚠️ **BEZPEČNOST:** Nikdy nesdílejte soubory `config.json` a `devices.json`! Obsahují citlivé údaje.

---

### 🎯 Krok 4: Spuštění aplikace

**GUI režim (výchozí - doporučeno):**
```bash
python src/main.py
# nebo
python src/main.py --mode gui
```

**CLI režim:**
```bash
# Výpis zařízení a aliasů
python src/main.py --mode cli --list-devices

# Zobrazení stavu zařízení
python src/main.py --mode cli --status

# Zobrazení stavu podle aliasu zařízení
python src/main.py --mode cli --status --device-alias "Obývací pokoj"

# Provedení příkazu
python src/main.py --mode cli --command power_on
```

---

## 🔒 Bezpečnost

### Ochrana citlivých údajů

Všechny soubory obsahující tokeny, API klíče a ID zařízení jsou **automaticky ignorovány** v `.gitignore`:

```
✅ Bezpečné (commitovány):
- data/config.json.example      # Šablona
- data/devices.json.example     # Šablona
- data/schedule.json.example    # Šablona

❌ Ignorované (NECOMMITUJTE):
- data/config.json              # Obsahuje tokeny!
- data/devices.json             # Obsahuje device ID!
- data/schedule.json            # Osobní plány
```

### ⚠️ PŘED PUBLIKACÍ PROJEKTU:
1. ✅ Nikdy necommitujte soubory bez `.example` přípony
2. ✅ Zkontrolujte `.gitignore` před každým pushem
3. ✅ Používejte environment variables pro CI/CD
4. ✅ Rotujte API klíče pravidelně

---

## 🎯 Použití GUI aplikace

### Základní ovládání
- **🖐️ HAND / 🤖 AUTO** - přepnutí mezi ručním a automatickým řízením
- **⚡ Zapnutí/Vypnutí** - hlavní tlačítko power
- **🌡️ Režimy** - COOL, HEAT, FAN, AUTO, AIR_DRY
- **🌡️ Teplota** - přesné nastavení s slidérem
- **💨 Větrání (HAND)** - síla větru + směr proudění v rozbalitelné sekci ručního režimu
- **⚡ Úspora energie** - power save režim

### Časovače
- **⏰ Sleep Timer** - rychlé tlačítka 30min, 1h, 2h
- **📅 Plánování (HAND)** - pokročilé časové harmonogramy jen v HAND režimu

### Vizualizace počasí
- **🌤️ Panel Počasí (ČHMÚ)** - zobrazuje načtený provider, POI/region a čas poslední aktualizace
- **📉 Graf forecastu** - intervalové min/max teploty pro zvolený horizont (výchozí 24h)
- **🧮 Korekce AC čidla** - v UI se zobrazuje pouze výsledná teplota po aplikaci offsetu

### Spotřeba energie
- **⚡ Přehled spotřeby** - samostatné pohledy Den / Týden / Měsíc / Rok
- **📊 Graf hodnot** - sloupcová vizualizace spotřeby dle zvoleného období
- **⤓ CSV export** - stažení právě zobrazené datové sady pro další analýzu

Poznámka k realtime příkonu:
- ThinQ status payload ho nemusí poskytovat konzistentně u všech modelů.
- Pokud API aktuální příkon nevrátí, GUI to explicitně označí jako nedostupné.

### Pokročilé plánování
Vytvářejte komplexní plány jako:
- "8:00 - zapni FAN na AUTO na 2 hodiny"
- "12:00 - přepni na COOL, nastav 22°C"
- "22:00 - zapni sleep timer na 30 minut"

Režimové řízení:
- `🖐️ HAND režim` zapne ruční řízení (včetně plánovače a pokročilých prvků větrání).
- `🤖 AUTO režim` vrátí řízení na pravidla + PID regulaci.

## 🛠️ Technické detaily

### Provozní playbook

- Podrobné pořadí příkazů, preconditions a limit policy: `docs/command-order-playbook.md`
- Roadmap scheduleru, počasí a modernizace GUI: `docs/scheduler-weather-roadmap.md`

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

#### `FileNotFoundError: config.json not found`
**Řešení:** Spusťte `python setup.py` nebo vytvořte konfigurační soubory z šablon.

#### `401 Unauthorized` nebo `403 Forbidden`
**Řešení:** 
- Zkontrolujte API přihlašovací údaje v `data/config.json`
- Ověřte, že máte správně nastavené oprávnění v LG Developer portálu
- Vygenerujte nové API klíče

#### `503 Service Unavailable`
**Řešení:** 
- LG API servery jsou dočasně nedostupné
- Aplikace automaticky opakuje dotazy (3× s 2s pauzou)
- Počkejte 10-15 minut a zkuste znovu

#### `NOT_PROVIDED_FEATURE`
**Řešení:** Funkce není vaším zařízením podporována - zkontrolujte `device_profile.json`

#### `COMMAND_NOT_SUPPORTED_IN_POWER_OFF`
**Řešení:** Zařízení musí být zapnuté pro tento příkaz

#### Rozbité české znaky na Linuxu
**Řešení:**
```bash
export LANG=cs_CZ.UTF-8
export LC_ALL=cs_CZ.UTF-8
```

### Debug režim
```bash
# Windows
$env:PYTHONPATH="src"
python src/main.py

# Linux/macOS
export PYTHONPATH=src
python src/main.py
```

---

## � Dokumentace API

### Podporované příkazy

| Kategorie | Příkazy | Hodnoty |
|-----------|---------|---------|
| **Power** | `power_on`, `power_off`, `toggle_power` | - |
| **Režimy** | `change_mode` | `COOL`, `HEAT`, `FAN`, `AUTO`, `AIR_DRY` |
| **Teplota** | `set_temperature` | 16-30°C (podle režimu) |
| **Větrání** | `set_wind_strength` | `AUTO`, `LOW`, `MID`, `HIGH` |
| **Směr** | `set_wind_direction` | nahoru/dolů, vlevo/vpravo |
| **Timery** | `set_sleep_timer` | minuty |

### API Optimalizace
- ✅ **Smart caching** - ukládání posledního stavu
- ✅ **Change detection** - API volání jen při změně
- ✅ **Retry logic** - automatické opakování při 503 chybách
- ✅ **Error handling** - robustní zpracování chyb
- ✅ **Connection pooling** - efektivní síťové připojení

---

## 🤝 Přispívání

Contributions are welcome! 🎉

### Jak přispět:

1. **Fork** projektu
2. Vytvořte **feature branch**
   ```bash
   git checkout -b feature/AmazingFeature
   ```
3. **Commit** změny
   ```bash
   git commit -m 'Add some AmazingFeature'
   ```
4. **Push** do branch
   ```bash
   git push origin feature/AmazingFeature
   ```
5. Otevřete **Pull Request**

### Coding Standards:
- ✅ UTF-8 kódování ve všech souborech
- ✅ PEP 8 style guide
- ✅ Docstrings pro všechny funkce
- ✅ Type hints kde je to vhodné
- ✅ Testování před submitem

---

## 📄 Licence

Tento projekt je licencován pod **MIT License** - viz [LICENSE](LICENSE) soubor pro detaily.

## 👨‍💻 Autor & Poděkování

Vytvořeno s pomocí GitHub Copilot pro efektivní ovládání LG ThinQ zařízení.

### Použité knihovny:
- [thinqconnect](https://github.com/thinq-connect/pythinqconnect) - Oficiální LG ThinQ Python SDK
- [aiohttp](https://github.com/aio-libs/aiohttp) - Asynchronní HTTP klient
- [tkinter](https://docs.python.org/3/library/tkinter.html) - GUI framework

---

## 🔮 Roadmap

- [ ] Pokročilé energetické metriky a statistiky
- [ ] Push notifikace (desktop/mobile)
- [ ] Webové rozhraní (Flask/FastAPI)
- [ ] Mobile app (React Native/Flutter)
- [ ] Hlasové ovládání (Google Assistant/Alexa)
- [ ] Docker kontejnerizace
- [ ] Home Assistant integrace
- [ ] Multi-device management (více klimatizací najednou)

---

## ⭐ Podpořte projekt

Pokud se vám projekt líbí, dejte mu hvězdičku na GitHubu! ⭐

## 📧 Kontakt

Máte otázky? Otevřete [Issue](https://github.com/your-username/lg-thinq-climate-control/issues) nebo [Discussion](https://github.com/your-username/lg-thinq-climate-control/discussions).

---

**Made with ❤️ and ☕**
