# -*- coding: utf-8 -*-
"""Lehky klient pro POER cloud API bez zavislosti na Home Assistantu.

Modul slouzi pro ziskani aktualniho stavu termostatu POER, zejmena
aktualni indoor teploty a nastavene cilove teploty.
Autentizace pouziva API key z mobilni POER aplikace.
"""

from __future__ import annotations

import aiohttp

_POER_CN_URL = "https://open2.poersmart.com"
_POER_EU_URL = "https://open.poersmart.com"


def _resolve_poer_endpoint_and_token(api_key: str) -> tuple[str, str] | None:
    """Rozhodne endpoint a token podle prefixu API klice.

    API key z POER aplikace obsahuje prefix oblasti:
    - ``cn`` -> CN endpoint
    - ``eu`` -> EU endpoint

    Args:
        api_key: Hodnota API klice z POER aplikace.

    Returns:
        tuple[str, str] | None: ``(api_url, token)`` nebo ``None`` pri
            neplatnem formatu.
    """

    key = str(api_key or "").strip()
    if len(key) < 3:
        return None

    prefix = key[:2].lower()
    token = key[2:]
    if not token:
        return None

    if prefix == "cn":
        return _POER_CN_URL, token
    if prefix == "eu":
        return _POER_EU_URL, token
    return None


async def fetch_poer_indoor_temperature(
    api_key: str,
    preferred_device_id: str | None = None,
    session: aiohttp.ClientSession | None = None,
) -> tuple[float | None, str | None, str | None]:
    """Nacte aktualni indoor teplotu z POER cloud API.

    Wrapper nad ``fetch_poer_status`` pro mista, ktera zatim potrebuji jen
    ambientni indoor teplotu.

    Args:
        api_key: API key z POER aplikace (vcetne prefixu ``cn``/``eu``).
        preferred_device_id: Volitelne preferovane ID termostatu.
        session: Volitelna sdilena ``aiohttp`` session.

    Returns:
        tuple[float | None, str | None, str | None]:
            ``(temperature_c, device_id, error_text)``.
    """

    status = await fetch_poer_status(
        api_key=api_key,
        preferred_device_id=preferred_device_id,
        session=session,
    )
    return status["current_temperature_c"], status["device_id"], status["error_text"]


async def fetch_poer_status(
    api_key: str,
    preferred_device_id: str | None = None,
    session: aiohttp.ClientSession | None = None,
) -> dict[str, float | str | None]:
    """Nacte aktualni stav termostatu z POER cloud API.

    Funkce provadi stejnou sekvenci jako integrace pro Home Assistant:
    1. ``action.devices.SYNC`` kvuli seznamu zarizeni.
    2. ``action.devices.QUERY`` pro vybrane zarizeni.

    Args:
        api_key: API key z POER aplikace (vcetne prefixu ``cn``/``eu``).
        preferred_device_id: Volitelne preferovane ID termostatu.
        session: Volitelna sdilena ``aiohttp`` session.

    Returns:
        dict[str, float | str | None]: Slovnik s klici ``current_temperature_c``,
            ``target_temperature_c``, ``device_id`` a ``error_text``.
    """

    resolved = _resolve_poer_endpoint_and_token(api_key)
    if resolved is None:
        return {
            "current_temperature_c": None,
            "target_temperature_c": None,
            "device_id": None,
            "error_text": "Neplatny POER API key (chybi prefix cn/eu nebo token).",
        }

    api_url, token = resolved
    url = f"{api_url.rstrip('/')}/speaker/ha/v1.0"
    headers = {
        "Authorization": f"beer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    own_session = session is None
    client_timeout = aiohttp.ClientTimeout(total=12)
    client = session
    if own_session:
        client = aiohttp.ClientSession(timeout=client_timeout)

    assert client is not None

    try:
        sync_payload = {
            "requestId": "111",
            "inputs": [{"intent": "action.devices.SYNC"}],
        }
        async with client.post(url, json=sync_payload, headers=headers) as response:
            if response.status != 200:
                text = await response.text()
                return {
                    "current_temperature_c": None,
                    "target_temperature_c": None,
                    "device_id": None,
                    "error_text": f"POER SYNC selhal: {response.status} {text}",
                }
            sync_data = await response.json(content_type=None)

        devices = sync_data.get("payload", {}).get("devices", [])
        if not isinstance(devices, list) or not devices:
            return {
                "current_temperature_c": None,
                "target_temperature_c": None,
                "device_id": None,
                "error_text": "POER nevratil zadna zarizeni.",
            }

        device_id = None
        if preferred_device_id:
            for item in devices:
                if str(item.get("id")) == str(preferred_device_id):
                    device_id = str(item.get("id"))
                    break

        if device_id is None:
            device_id = str(devices[0].get("id", "")).strip() or None

        if not device_id:
            return {
                "current_temperature_c": None,
                "target_temperature_c": None,
                "device_id": None,
                "error_text": "POER zarizeni nema platne device_id.",
            }

        query_payload = {
            "requestId": "112",
            "inputs": [
                {
                    "intent": "action.devices.QUERY",
                    "payload": {"devices": [{"id": device_id}]},
                }
            ],
        }

        async with client.post(url, json=query_payload, headers=headers) as response:
            if response.status != 200:
                text = await response.text()
                return {
                    "current_temperature_c": None,
                    "target_temperature_c": None,
                    "device_id": device_id,
                    "error_text": f"POER QUERY selhal: {response.status} {text}",
                }
            status_data = await response.json(content_type=None)

        devices_payload = status_data.get("payload", {}).get("devices", {})
        device_payload = devices_payload.get(device_id, {}) if isinstance(devices_payload, dict) else {}
        raw_temp = device_payload.get("thermostatTemperatureAmbient")

        try:
            current_temperature_c = float(raw_temp)
        except (TypeError, ValueError):
            current_temperature_c = None

        raw_target_temp = device_payload.get("thermostatTemperatureSetpoint")
        try:
            target_temperature_c = float(raw_target_temp)
        except (TypeError, ValueError):
            target_temperature_c = None

        if current_temperature_c is None:
            return {
                "current_temperature_c": None,
                "target_temperature_c": target_temperature_c,
                "device_id": device_id,
                "error_text": "POER nevratil thermostatTemperatureAmbient.",
            }

        return {
            "current_temperature_c": current_temperature_c,
            "target_temperature_c": target_temperature_c,
            "device_id": device_id,
            "error_text": None,
        }

    except aiohttp.ClientError as exc:
        return {
            "current_temperature_c": None,
            "target_temperature_c": None,
            "device_id": None,
            "error_text": f"POER sitova chyba: {exc}",
        }
    except Exception as exc:
        return {
            "current_temperature_c": None,
            "target_temperature_c": None,
            "device_id": None,
            "error_text": f"POER neocekavana chyba: {exc}",
        }
    finally:
        if own_session:
            await client.close()
