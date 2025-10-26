
# LG ThinQ Klimatizace - Ovládání & Plánování

Moderní Python aplikace pro kompletní ovládání LG ThinQ klimatizací s pokročilými funkcemi plánování a tmavým GUI.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: UTF-8](https://img.shields.io/badge/code%20style-UTF--8-brightgreen.svg)](https://en.wikipedia.org/wiki/UTF-8)

## ✨ Hlavní funkce

- 🎨 **Moderní tmavé GUI** - responzivní rozhraní s hover efekty
- 🌡️ **Kompletní ovládání klimatizace** - zapnutí/vypnutí, režimy, teplota, větrání
- 📅 **Pokročilé plánování** - časové harmonogramy pro automatické ovládání
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
   - Získáte: `Client ID`, `Client Secret`, `API Key`

3. **Autorizujte své zařízení:**
   - Propojte svůj LG ThinQ účet s vývojářskou aplikací
   - Získejte seznam vašich zařízení a jejich ID

4. **Poznamenejte si tyto údaje:**
   - ✅ Client ID
   - ✅ Client Secret  
   - ✅ API Key
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
   ```

2. **Upravte `data/config.json`:**
   ```json
   {
     "client_id": "váš_client_id_zde",
     "client_secret": "váš_client_secret_zde",
     "api_key": "váš_api_key_zde",
     "country_code": "CZ",
     "language_code": "cs-CZ"
   }
   ```

3. **Upravte `data/devices.json`:**
   ```json
   [
     {
       "device_id": "vaše_device_id_zde",
       "alias": "Obývací pokoj",
       "type": "AIR_CONDITIONER",
       "model_name": "LG AC Model"
     }
   ]
   ```

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
# Zobrazení stavu zařízení
python src/main.py --mode cli --status

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
