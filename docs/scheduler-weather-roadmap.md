# Implementované fáze: Scheduler, Počasí, Automatika, Web

Přehled toho, co bylo postupně implementováno. Všechny fáze jsou dokončeny.

## Fáze A – Model pravidel a sezóny  ✅

Modul: `src/automation_rules.py`

- Datový model pravidel a sezón (JSON), validace při načtení.
- Sezóny: WINTER [11,12,1,2,3], TRANSITION [4,5,9,10], SUMMER [6,7,8].
- Blokace COOL mimo léto; fallback mód konfigurovatelný (výchozí HEAT).
- Konfigurace v `data/automation_rules.json`.

## Fáze B – Weather provider  ✅

Modul: `src/weather_provider.py`, route: `src/web/routes/weather.py`

- ČHMÚ meteogram API (POI 510, výchozí horizont 24 h, cache 3 h).
- Parsovaná pole: `t2m` (teplota), `n` (oblačnost), `rr1h` (srážky), `rh2m` (vlhkost), `ff10m` (vítr), `dd` (směr větru → `wind_dir_deg`).
- Fallback na regionální forecast (`chmi_region_code`).
- Sensor offset pro korekci vnitřního čidla AC.
- Endpoint `/api/weather/forecast` vrací:
  - `hourly[]` – hodinové body (teplota, oblačnost, srážky, vlhkost, vítr, směr)
  - `daily[]` – denní agregace: `min_temp_c`, `max_temp_c`, `total_precip_mm`, `avg_cloudiness_pct`, `day_name`

## Fáze C – PID regulace a orchestrace  ✅

Modul: `src/thermal_controller.py`

- Staged PID-like regulace: prahy relativní k aktuální `targetTemperature` ze stavu zařízení.
- Watchdog 30 min pro chlazení.
- Delta indoor/outdoor ≥ 10 °C jako podmínka spuštění chlazení.
- Priorita rozhodnutí: manuální override > bezpečnostní pravidla > weather optimalizace > časový plán > fallback.

## Fáze D – Webový dashboard  ✅

Moduly: `src/web/`

- FastAPI server (`--mode web`), port 8000, Swagger na `/docs`.
- Real-time MQTT → WebSocket push (indikátor "Push"/"Offline").
- Single-page dashboard: Tailwind CSS (Play CDN) + Alpine.js v3, tmavý motiv.
- REST API:
  - `GET/POST /api/mode/` – přepínání AUTO ↔ HAND
  - `GET /api/devices/`, `GET /api/devices/{id}/status`
  - `POST /api/devices/{id}/command`
  - `GET /api/weather/forecast`, `/api/weather/config`
  - `GET /api/schedule/`, `POST/PUT/DELETE/PATCH /api/schedule/entries`
  - `GET /api/energy/{id}?view=daily|weekly|monthly|yearly`
- HAND scheduler: CRUD plánů s validací, UUID, persist do `data/schedule.json`.
- **Počasí widget**: gradient hlavička s aktuální teplotou a ikonou, tři záložky:
  - *Aktuální stav* – 4 kartičky (vítr + směr, vlhkost, srážky, oblačnost)
  - *Předpověď* – denní řádky (min/max teplota, celkové srážky, ikona)
  - *Hodinová* – původní scroll kartičky
- **Teplota**: slider (1°C krok) + tlačítka ±1, debounce 1 s (příkaz se odesle až po klidu); optim. aktualizace UI před potvrzením.
- **Lamely**: ThinQ Connect API nepodporuje nastavení polohy lamel – pouze boolean kývání (`set_rotate_updown`, `set_rotate_leftright`); každá osa se posílá jako samostatný příkaz. Sekce v UI je zedavě deaktivována s informací o omezení.
- Tab sync: při startu aplikace se `bottomTab` synchronizuje s načteným `controlMode`.
- Docker nasazení: `docker-compose up`, non-root uid 1000, volitelný Cloudflare Tunnel.

## Fáze E – Telemetrie, testy, dokumentace  ⏳

Zatím neimplementováno:

- Telemetrie API volání (latence, počty, chybové kódy) s persistencí.
- Integrační testy rozhodovací logiky proti mock API.
- Scheduler executor – background runner, který skutečně spouští naplánované HAND akce.
- MQTT watchdog s automatickým fallback pollingem při výpadku.
