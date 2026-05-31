# -*- coding: utf-8 -*-
"""
Jednoduchý in-memory rate limiter pro příkazové endpointy.

Chrání zápisové operace (odesílání příkazů klimatizaci) před záplavou
požadavků – ať už náhodnou (chyba v UI) nebo zlomyslnou. Implementace
využívá pouze standardní knihovnu (sliding-window v paměti procesu).

Omezení: stav je per-proces. Při škálování na více instancí by bylo
potřeba sdílené úložiště (Redis). Pro domácí nasazení s jednou instancí
je in-memory řešení dostatečné a bez externích závislostí.
"""

import logging
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from web.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class _SlidingWindow:
    """
    Sliding-window počitadlo požadavků na klienta.

    Pro každý klíč (IP) udržuje frontu časových razítek a odstraňuje ta,
    která vypadla z okna. Tím přesně počítá požadavky za posledních
    ``window_s`` sekund.

    Args:
        max_requests: Maximální počet požadavků v okně.
        window_s:     Délka okna v sekundách.
    """

    def __init__(self, max_requests: int, window_s: int) -> None:
        self._max = max_requests
        self._window = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str) -> bool:
        """
        Zjistí, zda klient smí provést další požadavek, a zaznamená jej.

        Args:
            key: Identifikátor klienta (zpravidla IP adresa).

        Returns:
            bool: True pokud je požadavek v limitu, jinak False.
        """
        now = time.monotonic()
        cutoff = now - self._window
        hits = self._hits[key]

        # Odstraň razítka mimo aktuální okno.
        while hits and hits[0] < cutoff:
            hits.popleft()

        if len(hits) >= self._max:
            return False

        hits.append(now)
        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware aplikující rate limit na zápisové (POST/PUT/PATCH/DELETE)
    požadavky pod prefixem ``/api/``.

    Čtecí operace (GET) nejsou omezeny. Klient se identifikuje IP adresou
    z ``request.client`` – díky ``proxy_headers`` uvicornu jde o skutečnou
    IP klienta i za reverzní proxy.
    """

    _WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app, settings: Settings | None = None) -> None:
        super().__init__(app)
        cfg = settings or get_settings()
        self._enabled = cfg.rate_limit_enabled
        self._window = _SlidingWindow(cfg.rate_limit_max, cfg.rate_limit_window_s)

    async def dispatch(self, request: Request, call_next):
        """
        Zkontroluje limit a buď požadavek propustí, nebo vrátí 429.

        Args:
            request:   Příchozí HTTP požadavek.
            call_next: Navazující ASGI handler.

        Returns:
            Response: Odpověď aplikace, nebo 429 při překročení limitu.
        """
        if not self._enabled:
            return await call_next(request)

        if request.method not in self._WRITE_METHODS:
            return await call_next(request)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        if not self._window.is_allowed(client_ip):
            logger.warning("Rate limit překročen pro %s", client_ip)
            return JSONResponse(
                status_code=429,
                content={"detail": "Příliš mnoho požadavků. Zkuste to za chvíli."},
            )

        return await call_next(request)
