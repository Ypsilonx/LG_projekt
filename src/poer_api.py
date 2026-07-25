# -*- coding: utf-8 -*-
"""Lehky klient pro POER cloud API bez zavislosti na Home Assistantu.

Modul slouzi pro ziskani aktualniho stavu termostatu POER a pro zapisove
ovladani zakladnich pointu: cilova teplota, hvac mode a preset.
Autentizace pouziva API key z mobilni POER aplikace.
"""

from __future__ import annotations

from typing import Any

import aiohttp

_POER_CN_URL = "https://open2.poersmart.com"
_POER_EU_URL = "https://open.poersmart.com"


def _resolve_poer_endpoint_and_token(api_key: str) -> tuple[str, str] | None:
    """Rozhodne endpoint a token podle prefixu API klice."""

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


def _build_poer_headers(token: str) -> dict[str, str]:
    """Vytvori standardni hlavičky pro POER requesty."""

    return {
        "Authorization": f"beer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def fetch_poer_indoor_temperature(
    api_key: str,
    preferred_device_id: str | None = None,
    session: aiohttp.ClientSession | None = None,
) -> tuple[float | None, str | None, str | None]:
    """Nacte aktualni indoor teplotu z POER cloud API."""

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
) -> dict[str, Any]:
    """Nacte aktualni stav termostatu z POER cloud API."""

    resolved = _resolve_poer_endpoint_and_token(api_key)
    if resolved is None:
        return {
            "current_temperature_c": None,
            "current_humidity_pct": None,
            "target_temperature_c": None,
            "device_id": None,
            "mode": None,
            "preset": None,
            "action": None,
            "min_temp_c": None,
            "max_temp_c": None,
            "error_text": "Neplatny POER API key (chybi prefix cn/eu nebo token).",
        }

    api_url, token = resolved
    url = f"{api_url.rstrip('/')}/speaker/ha/v1.0"
    headers = _build_poer_headers(token)

    own_session = session is None
    client = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12))

    try:
        sync_payload = {"requestId": "111", "inputs": [{"intent": "action.devices.SYNC"}]}
        async with client.post(url, json=sync_payload, headers=headers) as response:
            if response.status != 200:
                text = await response.text()
                return {
                    "current_temperature_c": None,
                    "current_humidity_pct": None,
                    "target_temperature_c": None,
                    "device_id": None,
                    "mode": None,
                    "preset": None,
                    "action": None,
                    "min_temp_c": None,
                    "max_temp_c": None,
                    "error_text": f"POER SYNC selhal: {response.status} {text}",
                }
            sync_data = await response.json(content_type=None)

        devices = sync_data.get("payload", {}).get("devices", [])
        if not isinstance(devices, list) or not devices:
            return {
                "current_temperature_c": None,
                "current_humidity_pct": None,
                "target_temperature_c": None,
                "device_id": None,
                "mode": None,
                "preset": None,
                "action": None,
                "min_temp_c": None,
                "max_temp_c": None,
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
                "current_humidity_pct": None,
                "target_temperature_c": None,
                "device_id": None,
                "mode": None,
                "preset": None,
                "action": None,
                "min_temp_c": None,
                "max_temp_c": None,
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
                    "current_humidity_pct": None,
                    "target_temperature_c": None,
                    "device_id": device_id,
                    "mode": None,
                    "preset": None,
                    "action": None,
                    "min_temp_c": None,
                    "max_temp_c": None,
                    "error_text": f"POER QUERY selhal: {response.status} {text}",
                }
            status_data = await response.json(content_type=None)

        devices_payload = status_data.get("payload", {}).get("devices", {})
        device_payload = devices_payload.get(device_id, {}) if isinstance(devices_payload, dict) else {}
        device_meta = next((item for item in devices if str(item.get("id")) == str(device_id)), {})

        def _to_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        current_temperature_c = _to_float(device_payload.get("thermostatTemperatureAmbient"))
        current_humidity_pct = _to_float(device_payload.get("thermostatHumidityAmbient"))
        target_temperature_c = _to_float(device_payload.get("thermostatTemperatureSetpoint"))

        current_mode = str(device_payload.get("thermostatMode") or "").strip() or None
        current_action = str(device_payload.get("thermostatAction") or "").strip() or None
        preset = "home"
        mode = current_mode
        if current_mode == "eco":
            preset = "away"
            mode = "heat"

        attributes = device_meta.get("attributes", {}) if isinstance(device_meta, dict) else {}
        temp_range = attributes.get("thermostatTemperatureRange", {}) if isinstance(attributes, dict) else {}
        min_temp_c = _to_float(temp_range.get("minThresholdCelsius"))
        max_temp_c = _to_float(temp_range.get("maxThresholdCelsius"))

        return {
            "current_temperature_c": current_temperature_c,
            "current_humidity_pct": current_humidity_pct,
            "target_temperature_c": target_temperature_c,
            "device_id": device_id,
            "mode": mode,
            "preset": preset,
            "action": current_action,
            "min_temp_c": min_temp_c,
            "max_temp_c": max_temp_c,
            "error_text": None if current_temperature_c is not None else "POER nevratil thermostatTemperatureAmbient.",
        }

    except aiohttp.ClientError as exc:
        return {
            "current_temperature_c": None,
            "current_humidity_pct": None,
            "target_temperature_c": None,
            "device_id": None,
            "mode": None,
            "preset": None,
            "action": None,
            "min_temp_c": None,
            "max_temp_c": None,
            "error_text": f"POER sitova chyba: {exc}",
        }
    except Exception as exc:
        return {
            "current_temperature_c": None,
            "current_humidity_pct": None,
            "target_temperature_c": None,
            "device_id": None,
            "mode": None,
            "preset": None,
            "action": None,
            "min_temp_c": None,
            "max_temp_c": None,
            "error_text": f"POER neocekavana chyba: {exc}",
        }
    finally:
        if own_session:
            await client.close()


async def send_poer_command(
    api_key: str,
    endpoint: str,
    data: dict[str, Any],
    preferred_device_id: str | None = None,
    session: aiohttp.ClientSession | None = None,
) -> dict[str, Any]:
    """Odešle write příkaz do POER cloudu."""

    resolved = _resolve_poer_endpoint_and_token(api_key)
    if resolved is None:
        return {
            "success": False,
            "device_id": None,
            "error_text": "Neplatny POER API key (chybi prefix cn/eu nebo token).",
        }

    api_url, token = resolved
    state = await fetch_poer_status(
        api_key=api_key,
        preferred_device_id=preferred_device_id,
        session=session,
    )
    device_id = state.get("device_id")
    if not device_id:
        return {
            "success": False,
            "device_id": None,
            "error_text": state.get("error_text") or "POER zarizeni neni dostupne.",
        }

    if endpoint == "set_temp":
        execution = [
            {
                "command": "action.devices.commands.ThermostatTemperatureSetpoint",
                "params": {"thermostatTemperatureSetpoint": data["temperature"]},
            }
        ]
    elif endpoint == "set_mode":
        mode = str(data.get("mode") or "auto").lower()
        preset = str(data.get("preset") or "home").lower()
        if preset == "away":
            mode = "eco"
        execution = [
            {
                "command": "action.devices.commands.ThermostatSetMode",
                "params": {"thermostatMode": mode},
            }
        ]
    else:
        return {
            "success": False,
            "device_id": device_id,
            "error_text": f"Nepodporovany POER prikaz: {endpoint}",
        }

    payload = {
        "requestId": "113",
        "inputs": [
            {
                "intent": "action.devices.EXECUTE",
                "payload": {
                    "commands": [
                        {
                            "devices": [{"id": device_id}],
                            "execution": execution,
                        }
                    ]
                },
            }
        ],
    }

    url = f"{api_url.rstrip('/')}/speaker/ha/v1.0"
    headers = _build_poer_headers(token)

    own_session = session is None
    client = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12))

    try:
        async with client.post(url, json=payload, headers=headers) as response:
            if response.status == 200:
                return {"success": True, "device_id": device_id, "error_text": None}

            text = await response.text()
            return {
                "success": False,
                "device_id": device_id,
                "error_text": f"POER command selhal: {response.status} {text}",
            }
    except aiohttp.ClientError as exc:
        return {
            "success": False,
            "device_id": device_id,
            "error_text": f"POER sitova chyba: {exc}",
        }
    except Exception as exc:
        return {
            "success": False,
            "device_id": device_id,
            "error_text": f"POER neocekavana chyba: {exc}",
        }
    finally:
        if own_session:
            await client.close()
