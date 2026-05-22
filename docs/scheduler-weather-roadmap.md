# Roadmap: Scheduler, Pocasi, Sezony a Modernizace GUI

Cil:
- Udelat z aplikace spolehlivy celorocni system pro automaticke rizeni klimatizace.
- Omezit riziko kolizi prikazu a serverovych odmitnuti.
- Zavest pravidla podle pocasi a rocnich obdobi.
- Zmodernizovat GUI tak, aby bylo prehledne, vysvetlitelne a prijemne na dlouhodobe pouzivani.

## 1. Aktualni stav a limity

Aktualne scheduler umi hlavne casove intervaly start-end s parametry mode, teplota, vitr.
Neni zde plnohodnotny system priorit, konfliktni resolver, ani weather-based rozhodovani.

Dalsi omezeni:
- Vykonavani planu je intervalove a jednoduche.
- Chybi strategicke rozhodovani podle sezony a venkovni teploty.
- Chybi simulace pravidel pred nasazenim.
- GUI je funkcni, ale nevede uzivatele procesem tvorby pravidel.

## 2. Pozadovane schopnosti

1. Rocni automatizace
- Profil zima, prechod, leto.
- Napriklad v zime zakazat rezim chlazeni.

2. Weather-aware rizeni
- Reagovat na aktualni venkovni teplotu a volitelne i kratkou predpoved.
- Menit cilovou teplotu podle venkovni situace.

3. Konfliktni resolver
- Jasna priorita rozhodnuti, aby se pravidla neprala.
- Stabilizace proti prepinani rezimu tam a zpet.

4. Vysvetlitelnost
- Kazde automaticke rozhodnuti musi mit odpoved na otazku Proc se to stalo.

5. Uzivatelska privetivost
- GUI musi vest uzivatele krok za krokem a minimalizovat chybne nastaveni.

## 3. Navrhovana architektura

1. Moduly
- scheduler_core: vyhodnoceni casovych planu.
- policy_engine: pravidla, sezony, priority, konflikty.
- weather_provider: adapter pro pocasi a cache.
- automation_orchestrator: centralni smycka, ktera sklada vystup do jednoho ciloveho prikazu.
- audit_log: zapis rozhodnuti a prikazu.

2. Priorita rozhodnuti
- Manual override ma nejvyssi prioritu.
- Bezpecnostni pravidla (napr. zimni zakaz COOL) jsou nad weather optimalizaci.
- Weather optimalizace je nad beznym casovym planem.
- Casovy plan je nad vychozim fallbackem.

3. Anti-flapping
- Minimalni doba mezi zmenami rezimu.
- Hystereze teploty, aby nedochazelo k cukanim.

## 4. Faze implementace

### Faze A: Model pravidel a sezony

Co pribude:
- Datovy model pravidel, sezon a priorit.
- Validace konfigurace pri ulozeni.
- Prvni pravidlo: zimni blokace COOL.

Vystup:
- Pravidla jsou ulozena v datech, cte je engine, umi je vysvetlit.

### Faze B: Weather provider

Co pribude:
- Adapter pro weather API.
- Cache a timeouty.
- Fallback kdyz weather API neni dostupne.

Vystup:
- System ma aktualni venkovni data bez zbytecneho spamu API.

### Faze C: Orchestrator a konfliktni resolver

Co pribude:
- Jedna centralni smycka vyhodnoceni.
- Jedna centralni fronta prikazu na zarizeni.
- Vysledny cilovy stav zarizeni je deterministicky.

Vystup:
- Predvidatelne a stabilni chovani i pri vice pravidlech.

### Faze D: Modernizace GUI / webovy dashboard

Stav: v implementaci (webova aplikace nahrazuje desktopove GUI).

Co je hotovo:
- FastAPI webovy server s MQTT real-time push pres WebSocket.
- REST API pro cteni stavu zarizeni a provedeni prikazu.
- Zakladni HTML sablony (Tailwind CDN + Alpine.js).
- Docker kontejnerizace (docker-compose + Cloudflare Tunnel).

Co jeste pribude:
- Dashboard s kartami a live stavy zarizeni.
- Ovladaci prvky v prohlizeci (moc, rezim, teplota, vitr).
- Panel pro zobrazeni a editaci automatizacnich pravidel.
- Panel pro spravу casovych planu.
- Panel pocasi (CHMU forecast).
- Builder pravidel (krokovy wizard) – nizka priorita.
- Test pravidla nanecisto nad historickym vzorkem pocasi – nizka priorita.

Vystup:
- Webova aplikace bude pristupna z domaci site i z internetu (Cloudflare Tunnel)
  bez nutnosti instalace klienta.

### Faze E: Telemetrie, testy, dokumentace

Co pribude:
- Telemetrie volani API, latence a kody chyb.
- Integrační testy rozhodovaci logiky.
- Uzivatelsky navod a provozni playbook.

Vystup:
- Dlouhodobe udrzitelny projekt s jasnym chovanim.

## 5. MVP rozsah pro nejblizsi iteraci

Doporucene minimum:
1. Zimni blokace COOL.
2. Zakladni weather adapter jen pro venkovni teplotu.
3. Jedno pravidlo pro cilovou teplotu podle venkovni teploty.
4. Conflict resolver s prioritami.
5. Jednoduchy panel v GUI pro prehled aktivnich pravidel.

## 6. Akceptacni kriteri

1. Pri aktivni zime nelze automatizaci prepnout do COOL.
2. Pri venkovni teplote pod definovanou hranici system navrhne HEAT nebo FAN podle pravidel.
3. Pri dostupnem MQTT se neprovadi zbytecne cteni stavu.
4. Pri neplatne konfiguraci se pravidla neaktivuji a GUI jasne ukaze chybu.
5. U kazde automaticke akce je dohledatelny duvod.

## 7. Rizika

1. Weather API nedostupnost.
- Mit cache, fallback a stale funkcni casovy plan.

2. Prilis mnoho pravidel.
- Mit priority a detekci konfliktu pred aktivaci.

3. Uzivatelska slozitost.
- Mit wizard, sablony a prehled Proc.

## 8. Co delat hned ted

1. Schvalit MVP rozsah pro prvni iteraci.
2. Implementovat Fazi A v malem kroku.
3. Po Fazi A provest prakticke testy a upravit pravidla dle realneho chovani.
4. Pokracovat Fazemi B a C.
5. GUI modernizovat az nad stabilni logikou.

