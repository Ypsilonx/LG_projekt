# -*- coding: utf-8 -*-
"""
WebSocket endpoint a správa připojených klientů.

Architektura real-time toku:
    MQTT broker (AWS IoT)
        → ThinQAPI.connect_mqtt(on_message)   # C++ vlákno AWS CRT SDK
        → asyncio.run_coroutine_threadsafe     # přechod do asyncio smyčky
        → ConnectionManager.broadcast()        # odeslání všem WS klientům
        → prohlížeče                           # live aktualizace UI

Endpoint: GET /ws  (WebSocket upgrade)

Formát zprávy odesílané klientům:
    {
        "type": "device_status" | "connection" | "mqtt_status",
        "data": { ... },
        "timestamp": "<ISO 8601 UTC>"
    }
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Real-time"])


class ConnectionManager:
    """
    Správce aktivních WebSocket připojení.

    Singleton instance ``manager`` je importována v ``app.py`` pro
    registraci MQTT bridge callbacku a v route handleru pro accept/disconnect.

    Thread-safety:
        ``broadcast`` je volán výhradně z asyncio smyčky (přes
        ``run_coroutine_threadsafe`` z MQTT callbacku). ``_connections``
        list je modifikován pouze v asyncio kontextu, proto je přístup
        bezpečný bez explicitního zámku.
    """

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        """
        Přijme nové WebSocket připojení.

        Args:
            ws: FastAPI WebSocket objekt
        """
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"📲 WS klient připojen  (aktivní: {len(self._connections)})")

    def disconnect(self, ws: WebSocket) -> None:
        """
        Odstraní WebSocket z aktivního seznamu.

        Args:
            ws: Odpojena instance WebSocket
        """
        try:
            self._connections.remove(ws)
        except ValueError:
            pass
        logger.info(f"🔌 WS klient odpojen   (aktivní: {len(self._connections)})")

    async def broadcast(self, message: dict) -> None:
        """
        Odešle zprávu všem připojeným klientům.

        Nefunkční spojení jsou tiše odstraněna ze seznamu.

        Args:
            message: Slovník serializovatelný jako JSON
        """
        if not self._connections:
            return
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def client_count(self) -> int:
        """Počet aktuálně připojených WebSocket klientů."""
        return len(self._connections)


# Singleton sdílený mezi app.py (MQTT bridge) a route handlerem
manager = ConnectionManager()


def _now_iso() -> str:
    """Vrátí aktuální čas UTC ve formátu ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket endpoint pro real-time push stavu zařízení.

    Klient se připojí na ``ws://host:8000/ws`` a dostává JSON zprávy
    bez nutnosti pollování REST API.

    Po připojení klient obdrží potvrzovací zprávu ``type=connection``.
    Každá MQTT notifikace ze zařízení je následně odeslána jako
    ``type=device_status``.

    Klient může posílat libovolný text (např. „ping") – server ho ignoruje
    a slouží jen pro udržení spojení naživu.
    """
    await manager.connect(ws)
    try:
        # Potvrzení připojení
        await ws.send_json({
            "type": "connection",
            "data": {"status": "connected", "active_clients": manager.client_count},
            "timestamp": _now_iso(),
        })
        # Čekáme na zprávy od klienta (heartbeat ping) – držíme spojení otevřené
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as exc:
        logger.warning(f"WS chyba: {exc}")
        manager.disconnect(ws)
