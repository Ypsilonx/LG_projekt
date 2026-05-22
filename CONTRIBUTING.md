# Contributing to LG ThinQ Climate Control

Děkujeme za váš zájem přispět do projektu! 🎉

## 📋 Jak přispět

### 1. Nahlášení chyb (Bug Reports)

Pokud najdete chybu:
1. Zkontrolujte [Issues](https://github.com/your-username/lg-thinq-climate-control/issues), zda již není nahlášená
2. Vytvořte nový Issue s těmito informacemi:
   - **Popis problému** - co se stalo a co jste očekávali
   - **Kroky k reprodukci** - jak chybu vyvolat
   - **Prostředí** - OS, Python verze, verze závislostí
   - **Logy** - relevantní error messages

### 2. Návrhy funkcí (Feature Requests)

Máte nápad na novou funkci?
1. Otevřete Issue s tagem `enhancement`
2. Popište:
   - **Jakou funkci navrhujete**
   - **Proč by byla užitečná**
   - **Jak by mohla fungovat**

### 3. Pull Requests

#### Před vytvořením PR:

1. **Fork** repozitář
2. **Clone** váš fork
   ```bash
   git clone https://github.com/your-username/lg-thinq-climate-control.git
   ```
3. Vytvořte **novou branch**
   ```bash
   git checkout -b feature/my-amazing-feature
   ```

#### Během vývoje:

- ✅ Používejte **UTF-8 kódování** (`# -*- coding: utf-8 -*-`)
- ✅ Dodržujte **PEP 8** style guide
- ✅ Přidejte **docstrings** k funkcím
- ✅ **Testujte** své změny před commitem
- ✅ **Commitujte logicky** - jedna změna = jeden commit
- ✅ Pište **smysluplné commit messages**

#### Commit message formát:

```
Typ: Stručný popis (max 50 znaků)

Detailnější vysvětlení změny, pokud je potřeba.
Může být víceřádkové.

- Seznam konkrétních změn
- Co bylo opraveno/přidáno
```

**Typy:**
- `FEAT:` - nová funkce
- `FIX:` - oprava chyby
- `DOCS:` - změny v dokumentaci
- `STYLE:` - formátování, whitespace
- `REFACTOR:` - refactoring kódu
- `TEST:` - přidání testů
- `CHORE:` - údržba projektu

#### Po dokončení:

1. **Push** změn
   ```bash
   git push origin feature/my-amazing-feature
   ```
2. Otevřete **Pull Request** na GitHubu
3. Popište co PR dělá a proč
4. Odkažte související Issues (`Fixes #123`)

## 🎨 Coding Standards

### Python Style Guide

- Dodržujte **PEP 8**
- Maximální délka řádku: **100 znaků**
- Indentace: **4 mezery** (ne taby)
- UTF-8 encoding v hlavičce všech souborů

### Dokumentace

```python
def my_function(param1: str, param2: int) -> bool:
    """
    Stručný popis funkce na jednom řádku.
    
    Detailnější popis může být víceřádkový.
    Vysvětluje co funkce dělá a proč.
    
    Args:
        param1: Popis prvního parametru
        param2: Popis druhého parametru
    
    Returns:
        Popis návratové hodnoty
    
    Raises:
        ValueError: Kdy může nastat tato chyba
    """
    pass
```

### Struktura souborů

```python
# -*- coding: utf-8 -*-
"""
Modul docstring - popis modulu.
"""

# Standard library imports
import os
import sys

# Third party imports
import aiohttp
from thinqconnect import ThinQApi

# Local imports
from .utils import helper_function

# Constants
DEFAULT_TIMEOUT = 30

# Classes and functions
...
```

## 🧪 Testování

Před odesláním PR:
1. ✅ Aplikace se spustí bez chyb
2. ✅ Všechny funkce fungují správně
3. ✅ Nerozbíjíte existující funkce
4. ✅ Testováno na vašem OS (ideálně i jiných)

## 🔒 Bezpečnost

- ❌ **NIKDY** necommitujte API tokeny, klíče, nebo device ID
- ❌ **NIKDY** necommitujte `config.json`, `devices.json`
- ✅ **VŽDY** používejte `.example` soubory jako šablony
- ✅ **VŽDY** zkontrolujte `.gitignore` před commitem

## 📝 Checklist před PR

- [ ] Kód dodržuje PEP 8
- [ ] Přidány docstrings
- [ ] UTF-8 encoding v nových souborech
- [ ] Žádné citlivé údaje v commitu
- [ ] Aplikace se spustí bez chyb
- [ ] Otestováno na skutečném zařízení nebo přes web UI (pokud možno)
- [ ] Aktualizována dokumentace (pokud potřeba)
- [ ] Commit messages jsou srozumitelné

## 💬 Komunikace

- **Issues** - pro chyby a návrhy
- **Discussions** - pro obecné dotazy a diskuze
- **PR comments** - pro review a feedback

## 📜 Code of Conduct

- Buďte **respektující** k ostatním přispěvatelům
- **Konstruktivní** kritika je vítána
- **Diskriminace** jakéhokoli druhu není tolerována
- **Pamatujte** - všichni jsme zde dobrovolně

## 🎓 První PR?

Nebojte se! Každý někde začínal. Pokud máte otázky:
1. Podívejte se na existující PRs
2. Ptejte se v Discussions
3. Začněte s malými změnami (oprava překlepy, dokumentace)

## 🙏 Děkujeme!

Každý příspěvek, ať už malý nebo velký, je vítán a oceňován! 💖
