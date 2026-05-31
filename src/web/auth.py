# -*- coding: utf-8 -*-
"""
Ověřování přístupu přes Cloudflare Access (Zero Trust).

Architektura ochrany:
    Internet → Cloudflare Access (přihlášení e-mailem/IdP) → Cloudflare Tunnel
             → tato aplikace

Cloudflare Access provede autentizaci na své edge síti a do každého
povoleného požadavku vloží podepsaný JWT (hlavička
``Cf-Access-Jwt-Assertion`` nebo cookie ``CF_Authorization``). Tento
modul ten token ověřuje jako **pojistku** (defense in depth) – aplikace
tak odmítne jakýkoli požadavek, který by Cloudflare Access obešel.

Token je podepsán privátním klíčem Cloudflare; veřejné klíče (JWKS) se
stahují z ``{team_domain}/cdn-cgi/access/certs`` a krátkodobě cachují.

Pokud je ``LG_AUTH_MODE`` jiný než ``cloudflare``, ověřování je vypnuté
(vhodné pro lokální vývoj) a middleware propouští vše.
"""

import asyncio
import logging
from typing import Any

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from web.settings import Settings, get_settings

logger = logging.getLogger(__name__)

# Hlavička a cookie, do nichž Cloudflare Access vkládá podepsaný JWT.
_CF_HEADER = "Cf-Access-Jwt-Assertion"
_CF_COOKIE = "CF_Authorization"

# Cesty nevyžadující autentizaci.
# /health musí být veřejné pro Docker HEALTHCHECK a externí monitoring.
# /static obsahuje pouze veřejné CSS/JS bez citlivého obsahu.
_EXEMPT_PREFIXES = ("/health", "/static")


class CloudflareAccessError(Exception):
    """Vyhozeno při neplatném nebo chybějícím Cloudflare Access tokenu."""


class CloudflareAccessVerifier:
    """
    Ověřovač Cloudflare Access JWT tokenů.

    Stahuje a cachuje veřejné klíče (JWKS) z Cloudflare a validuje jimi
    podpis, vydavatele (issuer) a publikum (audience) tokenu.

    Args:
        team_domain: URL Cloudflare Access týmu, např.
                     ``https://muj-tym.cloudflareaccess.com``.
        audience:    Application Audience (AUD) tag konkrétní aplikace
                     z Cloudflare Access (Zero Trust → Access → Applications).
    """

    def __init__(self, team_domain: str, audience: str) -> None:
        self._issuer = team_domain.rstrip("/")
        self._audience = audience
        certs_url = f"{self._issuer}/cdn-cgi/access/certs"
        # PyJWKClient si sám cachuje stažené klíče a obnovuje je dle potřeby.
        self._jwk_client = jwt.PyJWKClient(certs_url, cache_keys=True)

    async def verify(self, token: str) -> dict[str, Any]:
        """
        Ověří JWT token a vrátí jeho claims.

        Stažení JWKS i samotná validace běží v thread poolu, aby
        neblokovaly asyncio event loop.

        Args:
            token: Hodnota JWT z hlavičky nebo cookie.

        Returns:
            dict[str, Any]: Dekódované claims (např. ``email``, ``sub``).

        Raises:
            CloudflareAccessError: Pokud je token neplatný, prošlý,
                má špatný podpis, vydavatele nebo publikum.
        """
        try:
            return await asyncio.to_thread(self._verify_sync, token)
        except CloudflareAccessError:
            raise
        except Exception as exc:  # pragma: no cover - obrana proti neznámým chybám
            raise CloudflareAccessError(f"Ověření tokenu selhalo: {exc}") from exc

    def _verify_sync(self, token: str) -> dict[str, Any]:
        """
        Synchronní jádro ověření (běží v thread poolu).

        Args:
            token: JWT k ověření.

        Returns:
            dict[str, Any]: Dekódované claims.

        Raises:
            CloudflareAccessError: Při jakékoli chybě validace.
        """
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
            )
        except jwt.PyJWTError as exc:
            raise CloudflareAccessError(str(exc)) from exc


def _extract_token(request: Request) -> str | None:
    """
    Vytáhne Cloudflare Access JWT z požadavku.

    Preferuje hlavičku ``Cf-Access-Jwt-Assertion``; pokud chybí, zkusí
    cookie ``CF_Authorization`` (používá ji prohlížeč při navigaci).

    Args:
        request: Příchozí HTTP požadavek.

    Returns:
        str | None: Token, nebo None pokud není přítomen.
    """
    header_token = request.headers.get(_CF_HEADER)
    if header_token:
        return header_token
    return request.cookies.get(_CF_COOKIE)


class CloudflareAccessMiddleware(BaseHTTPMiddleware):
    """
    Middleware vynucující platný Cloudflare Access token na všech cestách
    kromě veřejných (viz ``_EXEMPT_PREFIXES``).

    Při ``auth_mode != "cloudflare"`` je middleware no-op a propouští vše.
    """

    def __init__(self, app, settings: Settings | None = None) -> None:
        super().__init__(app)
        self._settings = settings or get_settings()
        self._verifier: CloudflareAccessVerifier | None = None
        if self._settings.auth_is_cloudflare:
            if not self._settings.cf_team_domain or not self._settings.cf_aud:
                raise RuntimeError(
                    "LG_AUTH_MODE=cloudflare vyžaduje nastavení "
                    "LG_CF_TEAM_DOMAIN a LG_CF_AUD."
                )
            self._verifier = CloudflareAccessVerifier(
                self._settings.cf_team_domain,
                self._settings.cf_aud,
            )

    async def dispatch(self, request: Request, call_next):
        """
        Ověří token a buď propustí požadavek dál, nebo vrátí 403.

        Args:
            request:   Příchozí HTTP požadavek.
            call_next: Navazující ASGI handler.

        Returns:
            Response: Odpověď aplikace, nebo 403 při selhání ověření.
        """
        if self._verifier is None:
            return await call_next(request)

        path = request.url.path
        if path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        token = _extract_token(request)
        if not token:
            return JSONResponse(
                status_code=403,
                content={"detail": "Chybí Cloudflare Access token."},
            )

        try:
            claims = await self._verifier.verify(token)
        except CloudflareAccessError as exc:
            logger.warning("Odmítnut neplatný Cloudflare Access token: %s", exc)
            return JSONResponse(
                status_code=403,
                content={"detail": "Neplatný Cloudflare Access token."},
            )

        # Identitu zpřístupníme handlerům (např. pro audit log).
        request.state.user_email = claims.get("email")
        return await call_next(request)
