# -*- coding: utf-8 -*-
"""
API routery – budou registrovány v app.py v dalších krocích.

Struktura:
    devices.py   – GET stav a seznam zařízení
    control.py   – POST příkazy (power, mode, teplota, ...)
    automation.py – pravidla, sezóny, thermal controller
    weather.py   – aktuální počasí a předpověď
    ws.py        – WebSocket endpoint (MQTT → browser push)
"""
