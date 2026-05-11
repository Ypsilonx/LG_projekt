# -*- coding: utf-8 -*-
"""
Vlastní tkinter widgets pro LG ThinQ aplikaci.
Obsahuje LED indikátor, EnergyPanel a další GUI komponenty.
"""
import tkinter as tk
from tkinter import ttk
from datetime import date, timedelta

class LEDIndicator(ttk.Frame):
    """LED indikátor stavu zařízení"""
    
    def __init__(self, master, size=20, **kwargs):
        super().__init__(master, **kwargs)
        self.size = size
        self.canvas = tk.Canvas(self, width=size*2, height=size*2, bg="#222222", highlightthickness=0)
        self.led = self.canvas.create_oval(2, 2, size*2-2, size*2-2, fill="gray", outline="#444444")
        self.canvas.pack()
        
    def set_state(self, state):
        """Nastavení stavu LED (on, off, error)"""
        if state == "on" or state == "POWER_ON":
            color = "#00ff00"  # Zelená pro zapnuto
        elif state == "off" or state == "POWER_OFF":
            color = "#ff0000"  # Červená pro vypnuto
        elif state == "error":
            color = "#ff8800"  # Oranžová pro chybu
        else:
            color = "#666666"  # Šedá pro neznámý stav
            
        self.canvas.itemconfig(self.led, fill=color)

# Zpětná kompatibilita
class LedIndicator(LEDIndicator):
    """Zpětně kompatibilní alias pro LEDIndicator"""
    pass


class EnergyPanel(ttk.LabelFrame):
    """
    Panel zobrazující denní spotřebu energie klimatizace za posledních 7 dní.

    Data jsou načítána přes Energy API (GET /devices/energy/{deviceId}/usage).
    Zobrazuje jednoduchý sloupcový graf vykreslený pomocí tk.Canvas a textové
    hodnoty v kWh. Hodnoty energyUsage z API jsou v jednotkách Wh.

    Args:
        parent: Rodičovský widget
        on_refresh: Callback volaný při stisku tlačítka Aktualizovat.
                    Musí mít signaturu: on_refresh() – spouští async aktualizaci.
    """

    BAR_WIDTH = 28
    BAR_SPACING = 10
    CANVAS_HEIGHT = 100
    BAR_COLOR = "#4a9eff"
    BAR_COLOR_TODAY = "#00cc66"
    TEXT_COLOR = "#cccccc"
    BG_COLOR = "#2a2a2a"

    def __init__(self, parent, on_refresh=None, **kwargs):
        super().__init__(parent, text="⚡ Spotřeba energie (posledních 7 dní)", padding=10, **kwargs)
        self.on_refresh = on_refresh
        self._data: list[dict] = []

        self._build_ui()

    def _build_ui(self):
        """Sestaví UI panel – canvas pro graf a tlačítko aktualizace."""
        top = ttk.Frame(self)
        top.pack(fill="x")

        self.total_label = ttk.Label(top, text="Celkem 7 dní: –", font=("Segoe UI", 10, "bold"))
        self.total_label.pack(side=tk.LEFT)

        refresh_btn = ttk.Button(top, text="🔄", width=3, command=self._on_refresh_click)
        refresh_btn.pack(side=tk.RIGHT)

        canvas_width = 7 * (self.BAR_WIDTH + self.BAR_SPACING) + self.BAR_SPACING
        self.canvas = tk.Canvas(
            self, width=canvas_width, height=self.CANVAS_HEIGHT + 30,
            bg=self.BG_COLOR, highlightthickness=0
        )
        self.canvas.pack(pady=(6, 0), fill="x")

        self.status_label = ttk.Label(self, text="Klikněte na 🔄 pro načtení dat", foreground="#888888")
        self.status_label.pack()

    def _on_refresh_click(self):
        """Zavolá nadřazený callback pro spuštění async aktualizace."""
        if self.on_refresh:
            self.on_refresh()

    def update_data(self, data_list: list[dict]):
        """
        Aktualizuje panel novými daty z Energy API.

        Args:
            data_list: Seznam záznamů [{"usedDate": "20260511", "energyUsage": 508}, ...]
                       energyUsage je v jednotkách Wh.
        """
        # Seřadit dle data, vzít posledních 7 záznamů
        self._data = sorted(data_list, key=lambda x: x.get("usedDate", ""))[-7:]
        self._draw()

    def _draw(self):
        """Překreslí sloupcový graf dle aktuálních dat."""
        self.canvas.delete("all")
        if not self._data:
            self.canvas.create_text(
                10, self.CANVAS_HEIGHT // 2, anchor="w",
                text="Žádná data", fill=self.TEXT_COLOR
            )
            return

        max_wh = max((d.get("energyUsage", 0) for d in self._data), default=1) or 1
        today_str = date.today().strftime("%Y%m%d")
        total_kwh = sum(d.get("energyUsage", 0) for d in self._data) / 1000

        self.total_label.config(text=f"Celkem 7 dní: {total_kwh:.2f} kWh")
        self.status_label.config(text="")

        for i, entry in enumerate(self._data):
            wh = entry.get("energyUsage", 0)
            used_date = entry.get("usedDate", "")
            bar_h = max(4, int((wh / max_wh) * self.CANVAS_HEIGHT))

            x0 = self.BAR_SPACING + i * (self.BAR_WIDTH + self.BAR_SPACING)
            x1 = x0 + self.BAR_WIDTH
            y0 = self.CANVAS_HEIGHT - bar_h
            y1 = self.CANVAS_HEIGHT

            color = self.BAR_COLOR_TODAY if used_date == today_str else self.BAR_COLOR
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

            # Popisek pod sloupcem (den v měsíci)
            day_label = used_date[6:] if len(used_date) == 8 else "?"
            self.canvas.create_text(
                (x0 + x1) // 2, self.CANVAS_HEIGHT + 10,
                text=day_label, fill=self.TEXT_COLOR, font=("Segoe UI", 8)
            )

            # Hodnota nad sloupcem (kWh)
            kwh = wh / 1000
            self.canvas.create_text(
                (x0 + x1) // 2, y0 - 8,
                text=f"{kwh:.2f}", fill=self.TEXT_COLOR, font=("Segoe UI", 7)
            )

    def show_loading(self):
        """Zobrazí načítací zprávu."""
        self.status_label.config(text="Načítám data…")

    def show_error(self, msg: str):
        """Zobrazí chybovou zprávu (zařízení nemusí energy API podporovat)."""
        self.status_label.config(text=f"⚠️ {msg}")
        self.canvas.delete("all")
