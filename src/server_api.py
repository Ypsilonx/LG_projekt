# -*- coding: utf-8 -*-
"""
API modul pro komunikaci s LG ThinQ službou.
Poskytuje HTTP přístup ke stavu a ovládání zařízení a real-time
MQTT stream pro okamžité notifikace o změnách stavu bez pollingu.
"""
import json
import logging
import asyncio
import aiohttp
from pathlib import Path
from typing import Callable, Optional
from thinqconnect import ThinQApi, ThinQMQTTClient

logger = logging.getLogger(__name__)


class ThinQAPI:
    """
    Wrapper nad ThinQ API s podporou HTTP příkazů i real-time MQTT streamu.

    Životní cyklus:
        1. initialize()      – vytvoří HTTP session a ThinQApi objekt
        2. connect_mqtt()    – připojí MQTT pro real-time notifikace (volitelné)
        3. get_device_status() / send_device_command() – HTTP operace
        4. close()           – čistě odpojí MQTT i HTTP session
    """

    def __init__(self):
        self._api: Optional[ThinQApi] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._mqtt: Optional[ThinQMQTTClient] = None
        self.config = self._load_config()

    # ------------------------------------------------------------------
    # Konfigurace
    # ------------------------------------------------------------------

    def _load_config(self) -> dict:
        """
        Načte konfiguraci z data/config.json.

        Returns:
            dict: Konfigurační data (access_token, country_code, client_id)

        Raises:
            FileNotFoundError: Pokud config.json neexistuje
            KeyError: Pokud chybí povinný klíč
        """
        config_path = Path(__file__).parent.parent / "data" / "config.json"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Konfigurační soubor {config_path} nenalezen. "
                "Zkopírujte data/config.json.example a vyplňte přihlašovací údaje."
            )

        for key in ("access_token", "country_code", "client_id"):
            if not config.get(key) or config[key].startswith("YOUR_"):
                raise ValueError(
                    f"Chybí nebo nevyplněná hodnota '{key}' v config.json."
                )
        return config

    # ------------------------------------------------------------------
    # HTTP inicializace
    # ------------------------------------------------------------------

    async def initialize(self) -> ThinQApi:
        """
        Inicializuje HTTP session a ThinQApi objekt (idempotentní).

        Returns:
            ThinQApi: Inicializovaný API objekt
        """
        if self._api is None:
            self._session = aiohttp.ClientSession()
            # Správné pořadí parametrů: session, access_token, country_code, client_id
            self._api = ThinQApi(
                session=self._session,
                access_token=self.config["access_token"],
                country_code=self.config["country_code"],
                client_id=self.config["client_id"],
            )
        return self._api

    # ------------------------------------------------------------------
    # MQTT real-time stream
    # ------------------------------------------------------------------

    async def connect_mqtt(self, on_message: Callable) -> bool:
        """
        Připojí MQTT klienta pro real-time notifikace o změnách stavu.

        Postup dle ThinQ API specifikace:
            1. GET /route              – zjistí adresu MQTT brokeru
            2. POST /client            – registrace klienta
            3. POST /client/certificate – vydání AWS IoT certifikátu
            4. Připojení na MQTT broker přes mTLS

        Po úspěšném připojení je `on_message` voláno při každé změně
        stavu zařízení – bez jakéhokoliv pollingu.

        Args:
            on_message: Callback volaný při příchodu MQTT zprávy.
                        Signatura: on_message(topic: str, payload: dict, dup: bool,
                                              qos: int, retain: bool, **kwargs)

        Returns:
            bool: True pokud se připojení zdařilo, False jinak
        """
        api = await self.initialize()

        try:
            self._mqtt = ThinQMQTTClient(
                thinq_api=api,
                client_id=self.config["client_id"],
                on_message_received=on_message,
                on_connection_interrupted=self._on_mqtt_interrupted,
                on_connection_success=self._on_mqtt_connected,
                on_connection_failure=self._on_mqtt_failure,
                on_connection_closed=self._on_mqtt_closed,
            )

            # Krok 1: zjistit adresu MQTT serveru přes GET /route
            await self._mqtt.async_init()

            # Krok 2+3: registrace klienta + získání AWS IoT certifikátu
            prepared = await self._mqtt.async_prepare_mqtt()
            if not prepared:
                logger.error("❌ MQTT příprava selhala (certifikát nebo registrace)")
                return False

            # Krok 4: připojení na MQTT broker
            await self._mqtt.async_connect_mqtt()

            if self._mqtt.is_connected:
                logger.info("✅ MQTT připojeno – real-time notifikace aktivní")
                return True
            else:
                logger.error("❌ MQTT připojení neproběhlo")
                return False

        except Exception as e:
            logger.error(f"❌ Chyba při MQTT inicializaci: {e}")
            return False

    def _on_mqtt_connected(self, connection, callback_data, **kwargs):
        """Callback: MQTT úspěšně připojeno.

        AWS CRT SDK předává (connection, callback_data) kde callback_data
        obsahuje atributy return_code a session_present.
        """
        session_present = getattr(callback_data, "session_present", False)
        logger.info(f"📡 MQTT spojení navázáno (session_present={session_present})")

    def _on_mqtt_interrupted(self, connection, error, **kwargs):
        """Callback: MQTT spojení přerušeno – AWS SDK se automaticky pokusí znovu."""
        logger.warning(f"⚠️ MQTT přerušeno: {error} – pokus o reconnect...")

    def _on_mqtt_failure(self, connection, callback_data, **kwargs):
        """Callback: MQTT připojení selhalo."""
        logger.error(f"❌ MQTT selhalo: {callback_data}")

    def _on_mqtt_closed(self, **kwargs):
        """Callback: MQTT spojení ukončeno."""
        logger.info("🔌 MQTT odpojeno")

    @property
    def mqtt_connected(self) -> bool:
        """Vrací True pokud je MQTT aktivní."""
        return self._mqtt is not None and self._mqtt.is_connected

    # ------------------------------------------------------------------
    # HTTP operace se zařízeními
    # ------------------------------------------------------------------

    async def get_device_status(self, device_id: str) -> dict:
        """
        Získá aktuální stav zařízení přes HTTP GET /devices/{deviceId}/state.

        Používá se pro počáteční načtení stavu a po odeslání příkazu.
        Za normálního provozu jsou aktualizace doručovány přes MQTT.

        Args:
            device_id: ID zařízení

        Returns:
            dict: Aktuální stav zařízení

        Raises:
            Exception: Při chybě komunikace s API
        """
        api = await self.initialize()
        try:
            status = await api.async_get_device_status(device_id)
            logger.debug(f"📋 Stav načten pro {device_id[:8]}...")
            return status
        except Exception as e:
            logger.error(f"❌ Chyba při načítání stavu: {e}")
            raise

    async def send_device_command(self, device_id: str, payload: dict) -> dict:
        """
        Odešle řídicí příkaz zařízení přes HTTP POST /devices/{deviceId}/control.

        Args:
            device_id: ID zařízení
            payload: Řídicí příkaz (viz klima_logic.py)

        Returns:
            dict: Odpověď API

        Raises:
            Exception: Při chybě komunikace nebo odmítnutí příkazu
        """
        api = await self.initialize()
        try:
            logger.info(f"📤 Příkaz → {device_id[:8]}...: {json.dumps(payload, ensure_ascii=False)}")
            result = await api.async_post_device_control(device_id, payload)
            logger.info(f"📥 Odpověď: {result}")
            return result
        except Exception as e:
            logger.error(f"❌ Chyba při odesílání příkazu: {e}")
            raise

    async def get_devices(self) -> list:
        """
        Načte seznam všech registrovaných zařízení přes GET /devices.

        Returns:
            list: Seznam zařízení
        """
        api = await self.initialize()
        try:
            return await api.async_get_device_list()
        except Exception as e:
            logger.error(f"❌ Chyba při načítání seznamu zařízení: {e}")
            raise

    # ------------------------------------------------------------------
    # Čistý shutdown
    # ------------------------------------------------------------------

    async def close(self):
        """
        Čistě odpojí MQTT a uzavře HTTP session.

        Volat při vypnutí aplikace pro uvolnění serverových zdrojů
        (zruší registraci klienta přes DELETE /client).
        """
        if self._mqtt and self._mqtt.is_connected:
            try:
                await self._mqtt.async_disconnect()
                logger.info("MQTT odpojeno")
            except Exception as e:
                logger.warning(f"Chyba při odpojení MQTT: {e}")
        self._mqtt = None

        if self._session:
            await self._session.close()
            self._session = None
        self._api = None
        logger.info("API session uzavřena")


# ------------------------------------------------------------------
# Pomocné funkce
# ------------------------------------------------------------------

def get_ac_device_id() -> str:
    """
    Načte Device ID klimatizace z data/devices.json.
    Hledá první zařízení typu DEVICE_AIR_CONDITIONER.

    Returns:
        str: Device ID klimatizace

    Raises:
        ValueError: Pokud klimatizace v souboru nebyla nalezena
        FileNotFoundError: Pokud soubor devices.json neexistuje
    """
    devices_path = Path(__file__).parent.parent / "data" / "devices.json"
    try:
        with open(devices_path, "r", encoding="utf-8") as f:
            devices = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Soubor {devices_path} nenalezen. "
            "Zkopírujte data/devices.json.example a vyplňte Device ID."
        )

    for device in devices:
        if device.get("deviceInfo", {}).get("deviceType") == "DEVICE_AIR_CONDITIONER":
            return device["deviceId"]

    raise ValueError(
        "Klimatizace (DEVICE_AIR_CONDITIONER) nebyla nalezena v devices.json."
    )


# ------------------------------------------------------------------
# Zpětná kompatibilita (frontend.py)
# ------------------------------------------------------------------

async def get_api():
    """
    Zpětně kompatibilní funkce – vrací (ThinQApi, None).

    Deprecated: Používejte přímo třídu ThinQAPI.
    """
    instance = ThinQAPI()
    api = await instance.initialize()
    return api, None


async def get_device_status(api: ThinQApi, device_id: str) -> dict:
    """
    Zpětně kompatibilní funkce pro získání stavu zařízení.

    Deprecated: Používejte ThinQAPI.get_device_status().
    """
    return await api.async_get_device_status(device_id)


async def send_device_command(api: ThinQApi, device_id: str, payload: dict) -> dict:
    """
    Zpětně kompatibilní funkce pro odeslání příkazu.

    Deprecated: Používejte ThinQAPI.send_device_command().
    """
    return await api.async_post_device_control(device_id, payload)

