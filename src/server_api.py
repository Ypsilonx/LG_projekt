# -*- coding: utf-8 -*-
"""
API modul pro komunikaci s LG ThinQ službou.
Optimalizovaná verze s caching a error handling.
"""
import json
import logging
import asyncio
import aiohttp
from pathlib import Path
from thinqconnect import ThinQApi

# Nastavení logování
logger = logging.getLogger(__name__)

class ThinQAPI:
    """ThinQ API wrapper s caching a error handling"""
    
    def __init__(self):
        self.api = None
        self.session = None
        self.config = self.load_config()
        self.device_cache = {}
        
    def load_config(self):
        """Načtení konfigurace z config.json"""
        try:
            config_path = Path(__file__).parent.parent / "data" / "config.json"
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Chyba při načítání konfigurace: {e}")
            raise
    
    async def initialize(self):
        """Inicializace API připojení"""
        if not self.api:
            self.session = aiohttp.ClientSession()
            self.api = ThinQApi(
                access_token=self.config["access_token"],
                country_code=self.config["country_code"],
                client_id=self.config["client_id"],
                session=self.session
            )
        return self.api
    
    async def get_device_status(self, device_id: str):
        """Získání stavu zařízení s caching (bez agresivního retry)"""
        try:
            api = await self.initialize()
            
            # V synchronní verzi thinqconnect používáme get_device_status
            if hasattr(api, 'async_get_device_status'):
                status = await api.async_get_device_status(device_id)
            else:
                # Fallback pro synchronní verzi
                status = api.get_device_status(device_id)
            
            # Cache pro porovnání změn
            if device_id in self.device_cache:
                if status == self.device_cache[device_id]:
                    logger.debug(f"Stav zařízení {device_id[:8]}... nezměněn")
                else:
                    logger.info(f"📋 Stav zařízení aktualizován")
            else:
                logger.info(f"📋 První načtení stavu zařízení")
            
            self.device_cache[device_id] = status
            return status
            
        except Exception as e:
            # Při jakékoliv chybě (včetně 503) to prostě selže
            # Periodická kontrola to zkusí znovu za 5 minut (STATUS_CHECK_INTERVAL)
            logger.error(f"❌ Chyba API: {e} - další pokus za 5 minut (automatická kontrola)")
            raise
    
    async def send_device_command(self, device_id: str, payload: dict):
        """Odeslání příkazu zařízení"""
        try:
            api = await self.initialize()
            
            logger.info(f"📤 API příkaz: {json.dumps(payload, ensure_ascii=False)}")
            
            if hasattr(api, 'async_post_device_control'):
                result = await api.async_post_device_control(device_id, payload)
            else:
                # Fallback pro synchronní verzi
                result = api.post_device_control(device_id, payload)
            
            logger.info(f"📥 API odpověď: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Chyba při odesílání příkazu: {e}")
            raise
    
    async def get_devices(self):
        """Získání seznamu zařízení"""
        try:
            api = await self.initialize()
            
            if hasattr(api, 'async_get_devices'):
                devices = await api.async_get_devices()
            else:
                devices = api.get_devices()
            
            return devices
            
        except Exception as e:
            logger.error(f"Chyba při získávání seznamu zařízení: {e}")
            raise
    
    async def close(self):
        """Uzavření API připojení"""
        if self.session:
            await self.session.close()
            self.session = None
        self.api = None
        logger.info("API připojení uzavřeno")

# Zpětná kompatibilita s původním API
async def get_api():
    """Zpětně kompatibilní funkce pro získání API instance"""
    api_instance = ThinQAPI()
    await api_instance.initialize()
    return api_instance.api, None

async def get_device_status(api, device_id):
    """Zpětně kompatibilní funkce pro získání stavu zařízení"""
    if hasattr(api, 'async_get_device_status'):
        return await api.async_get_device_status(device_id)
    else:
        return api.get_device_status(device_id)

async def send_device_command(api, device_id, payload):
    """Zpětně kompatibilní funkce pro odeslání příkazu"""
    if hasattr(api, 'async_post_device_control'):
        return await api.async_post_device_control(device_id, payload)
    else:
        return api.post_device_control(device_id, payload)
