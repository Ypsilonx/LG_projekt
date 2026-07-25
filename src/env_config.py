# -*- coding: utf-8 -*-
"""Pomocnik pro nacteni .env konfigurace pri lokalnim behu.

Docker Compose nahrava `.env` automaticky, ale pri prime spousteni
`python/uv run` je potreba hodnoty nacist manualne.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_LOADED = False


def load_local_env() -> bool:
    """Nacte lokalni `.env` do `os.environ`, pokud je dostupny.

    Hodnoty se nastavují pouze pokud proměnná ještě není v prostředí,
    aby prioritu měl shell, CI nebo Docker secrets.

    Returns:
        bool: True pokud se `.env` soubor nasel a byl zpracovan.
    """

    global _ENV_LOADED
    if _ENV_LOADED:
        return True

    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return False

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue

            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)

        _ENV_LOADED = True
        return True
    except OSError:
        return False
