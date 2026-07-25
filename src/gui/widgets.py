# -*- coding: utf-8 -*-
"""
Vlastní tkinter widgets pro LG ThinQ aplikaci.
Obsahuje LED indikátor, EnergyPanel, WeatherForecastPanel a další GUI komponenty.
"""
import tkinter as tk
from tkinter import ttk
from datetime import date

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
    Panel zobrazujici spotrebu energie klimatizace po vybranem obdobi.

    Data jsou načítána přes Energy API (GET /devices/energy/{deviceId}/usage).
    Zobrazuje sloupcovy graf vykresleny pomoci tk.Canvas a textove hodnoty
    v kWh. Hodnoty energyUsage z API jsou v jednotkach Wh.

    Args:
        parent: Rodičovský widget
        on_refresh: Callback volaný při stisku tlačítka Aktualizovat.
                    Musi mit signaturu on_refresh(view_key: str).
        on_export: Callback volany pri exportu CSV.
                   Musi mit signaturu on_export(view_key: str).
    """

    VIEW_OPTIONS = {
        "daily": "Den",
        "weekly": "Tyden",
        "monthly": "Mesic",
        "yearly": "Rok",
    }

    BAR_WIDTH = 28
    BAR_SPACING = 10
    CANVAS_HEIGHT = 160
    BAR_COLOR = "#4a9eff"
    BAR_COLOR_TODAY = "#00cc66"
    TEXT_COLOR = "#cccccc"
    BG_COLOR = "#2a2a2a"

    def __init__(self, parent, on_refresh=None, on_export=None, **kwargs):
        super().__init__(parent, text="⚡ Spotreba energie", padding=10, **kwargs)
        self.on_refresh = on_refresh
        self.on_export = on_export
        self._data: list[dict] = []
        self._view_key = "weekly"
        self._period = "DAILY"

        self._build_ui()

    def _build_ui(self):
        """Sestavi UI panel vcetne vyberu obdobi a exportu CSV."""
        top = ttk.Frame(self)
        top.pack(fill="x")

        self.total_label = ttk.Label(top, text="Celkem: –", font=("Segoe UI", 10, "bold"))
        self.total_label.pack(side=tk.LEFT)

        controls = ttk.Frame(top)
        controls.pack(side=tk.RIGHT)

        self.view_var = tk.StringVar(value=self.VIEW_OPTIONS[self._view_key])
        view_values = [self.VIEW_OPTIONS[key] for key in self.VIEW_OPTIONS]
        self.view_combo = ttk.Combobox(
            controls,
            textvariable=self.view_var,
            values=view_values,
            state="readonly",
            width=10,
        )
        self.view_combo.pack(side=tk.RIGHT, padx=(6, 0))
        self.view_combo.bind("<<ComboboxSelected>>", self._on_view_changed)

        export_btn = ttk.Button(controls, text="⤓ CSV", command=self._on_export_click)
        export_btn.pack(side=tk.RIGHT, padx=(6, 0))

        refresh_btn = ttk.Button(controls, text="🔄", width=3, command=self._on_refresh_click)
        refresh_btn.pack(side=tk.RIGHT)

        self.canvas = tk.Canvas(
            self, width=520, height=self.CANVAS_HEIGHT + 42,
            bg=self.BG_COLOR, highlightthickness=0
        )
        self.canvas.pack(pady=(6, 0), fill="x")

        self.current_power_var = tk.StringVar(value="Aktualni prikon: API nedostupny")
        ttk.Label(self, textvariable=self.current_power_var, foreground="#999999").pack(anchor="w", pady=(4, 0))

        self.status_label = ttk.Label(self, text="Kliknete na 🔄 pro nacteni dat", foreground="#888888")
        self.status_label.pack(anchor="w")

    def _selected_view_key(self):
        """Vrati interni klic aktualne zvoleneho pohledu."""
        selected_label = self.view_var.get()
        for key, label in self.VIEW_OPTIONS.items():
            if label == selected_label:
                return key
        return "weekly"

    def _on_view_changed(self, _event=None):
        """Reaguje na zmenu obdobi a okamzite spusti obnovu dat."""
        self._view_key = self._selected_view_key()
        self._on_refresh_click()

    def _on_refresh_click(self):
        """Zavola callback pro spusteni async aktualizace dat."""
        if self.on_refresh:
            self.on_refresh(self._selected_view_key())

    def _on_export_click(self):
        """Zavola callback pro export aktualni sady do CSV."""
        if self.on_export:
            self.on_export(self._selected_view_key())

    def update_data(self, data_list: list[dict], *, view_key="weekly", period="DAILY", current_power_w=None):
        """
        Aktualizuje panel novymi daty z Energy API.

        Args:
            data_list: Seznam zaznamu [{"usedDate": "20260511", "energyUsage": 508}, ...].
            view_key: Klic aktivniho pohledu.
            period: API perioda (`DAILY` nebo `MONTHLY`).
            current_power_w: Volitelny aktualni prikon ve wattech.
        """
        self._view_key = view_key if view_key in self.VIEW_OPTIONS else "weekly"
        self._period = period
        self.view_var.set(self.VIEW_OPTIONS[self._view_key])
        self._data = sorted(data_list, key=lambda x: x.get("usedDate", ""))

        if isinstance(current_power_w, (int, float)):
            self.current_power_var.set(f"Aktualni prikon: {float(current_power_w):.1f} W")
        else:
            self.current_power_var.set("Aktualni prikon: API nedostupny")

        self._draw()

    def _draw(self):
        """Prekresli sloupcovy graf dle aktualnich dat."""
        self.canvas.delete("all")

        plot_top = 18
        plot_bottom = self.CANVAS_HEIGHT
        plot_height = max(20, plot_bottom - plot_top)

        if not self._data:
            self.total_label.config(text="Celkem: 0.00 kWh")
            self.status_label.config(text="Zadna data pro zvolene obdobi")
            self.canvas.create_text(
                10, (plot_top + plot_bottom) // 2, anchor="w",
                text="Zadna data", fill=self.TEXT_COLOR
            )
            return

        max_wh = max((float(d.get("energyUsage", 0) or 0) for d in self._data), default=1) or 1
        today_str = date.today().strftime("%Y%m%d")
        total_kwh = sum(float(d.get("energyUsage", 0) or 0) for d in self._data) / 1000
        view_label = self.VIEW_OPTIONS.get(self._view_key, "Obdobi")

        bar_count = max(1, len(self._data))
        available_width = max(360, int(self.canvas.winfo_width() or 0))
        if available_width <= 1:
            available_width = 520

        spacing = self.BAR_SPACING if bar_count <= 14 else 6
        raw_bar_width = int((available_width - spacing * (bar_count + 1)) / bar_count)
        bar_width = max(8, min(self.BAR_WIDTH, raw_bar_width))

        if bar_width == 8 and bar_count > 20:
            spacing = 3

        self.canvas.configure(width=available_width)

        self.total_label.config(text=f"Celkem ({view_label}): {total_kwh:.2f} kWh")
        self.status_label.config(text="")

        show_value_labels = bar_count <= 16
        tick_step = 1 if bar_count <= 12 else (2 if bar_count <= 24 else 3)

        for i, entry in enumerate(self._data):
            wh = float(entry.get("energyUsage", 0) or 0)
            used_date = str(entry.get("usedDate", ""))
            bar_h = max(4, int((wh / max_wh) * plot_height))

            x0 = spacing + i * (bar_width + spacing)
            x1 = x0 + bar_width
            y0 = plot_bottom - bar_h
            y1 = plot_bottom

            color = self.BAR_COLOR_TODAY if used_date == today_str else self.BAR_COLOR
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

            # Popisek pod sloupcem podle periody
            if self._period == "MONTHLY" and len(used_date) == 6:
                day_label = f"{used_date[4:6]}/{used_date[2:4]}"
            elif len(used_date) == 8:
                day_label = f"{used_date[6:8]}.{used_date[4:6]}."
            else:
                day_label = "?"

            if i % tick_step == 0 or i == bar_count - 1:
                self.canvas.create_text(
                    (x0 + x1) // 2, plot_bottom + 12,
                    text=day_label, fill=self.TEXT_COLOR, font=("Segoe UI", 8)
                )

            # Hodnota nad sloupcem (kWh)
            kwh = wh / 1000
            if show_value_labels:
                self.canvas.create_text(
                    (x0 + x1) // 2, max(8, y0 - 9),
                    text=f"{kwh:.2f}", fill=self.TEXT_COLOR, font=("Segoe UI", 7)
                )

    def show_loading(self):
        """Zobrazi nacitaci zpravu."""
        self.status_label.config(text="Nacitam data...")

    def show_error(self, msg: str):
        """Zobrazi chybovou zpravu (zarizeni nemusi energy API podporovat)."""
        self.status_label.config(text=f"⚠️ {msg}")
        self.canvas.delete("all")


class WeatherForecastPanel(ttk.LabelFrame):
    """Panel s forecastem a docasnym odhadem interieru z AC cidla.

    Args:
        parent: Rodicovsky widget.
        on_refresh: Callback pro manualni obnoveni weather dat.
    """

    CANVAS_HEIGHT = 150
    CANVAS_BG = "#2a2a2a"
    CANVAS_FG = "#cccccc"
    LINE_COLOR = "#4a9eff"
    POINT_MIN_COLOR = "#66ccff"
    POINT_MAX_COLOR = "#ff9966"

    def __init__(self, parent, on_refresh=None, **kwargs):
        """Inicializace panelu forecast vizualizace.

        Args:
            parent: Rodicovsky widget.
            on_refresh: Callback pro manualni refresh.
            **kwargs: Dalsi argumenty pro ttk.LabelFrame.
        """

        super().__init__(parent, text="🌤️ Počasí (ČHMÚ Meteogram)", padding=10, **kwargs)
        self.on_refresh = on_refresh

        self.meta_var = tk.StringVar(value="Zdroj: ČHMÚ Meteogram | čekám na data")
        self.outdoor_var = tk.StringVar(value="Venkovní teplota: nedostupná")
        self.sensor_var = tk.StringVar(value="Odhad interieru z AC: nedostupna")
        self.summary_var = tk.StringVar(value="Forecast: čekám na první aktualizaci")
        self.status_var = tk.StringVar(value="")

        self._build_ui()

    def _build_ui(self):
        """Sestavi vizualni cast panelu."""
        header = ttk.Frame(self)
        header.pack(fill="x")

        ttk.Label(header, textvariable=self.meta_var, font=("Segoe UI", 10, "bold")).pack(
            side=tk.LEFT,
            anchor="w",
        )

        refresh_btn = ttk.Button(header, text="🔄", width=3, command=self._on_refresh_click)
        refresh_btn.pack(side=tk.RIGHT)

        ttk.Label(self, textvariable=self.outdoor_var, justify="left").pack(anchor="w", pady=(6, 0))
        ttk.Label(self, textvariable=self.sensor_var, justify="left").pack(anchor="w", pady=(6, 0))
        ttk.Label(self, textvariable=self.summary_var, justify="left").pack(anchor="w", pady=(2, 8))

        self.chart_canvas = tk.Canvas(
            self,
            height=self.CANVAS_HEIGHT,
            bg=self.CANVAS_BG,
            highlightthickness=0,
        )
        self.chart_canvas.pack(fill="x", pady=(0, 8))

        columns = ("interval", "tmin", "tmax", "tok")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=6)
        self.tree.heading("interval", text="Interval")
        self.tree.heading("tmin", text="Min °C")
        self.tree.heading("tmax", text="Max °C")
        self.tree.heading("tok", text="Zdroj")

        self.tree.column("interval", width=250, anchor="w")
        self.tree.column("tmin", width=80, anchor="center")
        self.tree.column("tmax", width=80, anchor="center")
        self.tree.column("tok", width=110, anchor="center")
        self.tree.pack(fill="x")

        ttk.Label(self, textvariable=self.status_var, foreground="#888888").pack(anchor="w", pady=(4, 0))

    def _on_refresh_click(self):
        """Spusti manualni obnoveni weather dat pres callback."""
        if self.on_refresh:
            self.on_refresh()

    def show_loading(self, message="Načítám forecast…"):
        """Zobrazi stav nacitani weather dat.

        Args:
            message: Text zobrazeny v paticce panelu.
        """

        self.status_var.set(message)

    def update_data(
        self,
        snapshot,
        now_local,
        horizon_hours,
        outdoor_now_c,
        sensor_raw_c,
        ac_indoor_temperature_proxy_offset_c,
        sensor_source,
        last_refresh_local,
        last_error,
    ):
        """Aktualizuje panel daty forecastu a stavem cidla.

        Args:
            snapshot: Objekt snapshotu forecastu, nebo None.
            now_local: Aktualni lokalni cas.
            horizon_hours: Delka forecast horizontu.
            outdoor_now_c: Odhad aktualni venkovni teploty.
            sensor_raw_c: Aktualni teplota z AC cidla.
            ac_indoor_temperature_proxy_offset_c: Docasny proxy offset pro
                odhad interierove teploty z AC cidla.
            sensor_source: Zdroj indoor teploty (externi termostat nebo AC cidlo).
            last_refresh_local: Cas posledni uspesne aktualizace.
            last_error: Posledni chyba refreshu.
        """

        if outdoor_now_c is None:
            self.outdoor_var.set("Venkovní teplota (online): nedostupná")
        else:
            self.outdoor_var.set(
                f"Venkovní teplota (online odhad): {outdoor_now_c:.1f}°C"
            )

        corrected_sensor_c = None
        if sensor_raw_c is not None:
            corrected_sensor_c = (
                sensor_raw_c + float(ac_indoor_temperature_proxy_offset_c)
            )

        if sensor_raw_c is None:
            self.sensor_var.set("Indoor teplota: nedostupna")
        else:
            if sensor_source == "external_thermostat":
                self.sensor_var.set(f"Indoor teplota (termostat): {sensor_raw_c:.1f}°C")
            else:
                self.sensor_var.set(f"Odhad interieru z AC: {corrected_sensor_c:.1f}°C")

        if snapshot is None:
            self.meta_var.set("Zdroj: ČHMÚ Meteogram (POI) | čekám na data")
            self.summary_var.set("Forecast: čekám na první aktualizaci")
            self._set_table_rows([])
            self._draw_chart([])
            if last_error:
                self.status_var.set(f"⚠️ {last_error}")
            else:
                self.status_var.set("")
            return

        refreshed = "?"
        if last_refresh_local is not None:
            refreshed = last_refresh_local.strftime("%H:%M")

        provider_label = snapshot.provider
        if provider_label.upper() == "CHMI":
            provider_label = "ČHMÚ regionální forecast"
        elif provider_label.upper() == "CHMI_METEOGRAM":
            provider_label = "ČHMÚ Meteogram"

        source_label = provider_label
        if snapshot.provider.upper() == "CHMI_METEOGRAM":
            poi_id = snapshot.region_code.replace("POI", "").strip()
            if poi_id:
                source_label = f"{provider_label} POI {poi_id}"
        elif snapshot.region_code:
            source_label = f"{provider_label} {snapshot.region_code}"

        self.meta_var.set(
            f"Zdroj: {source_label} | "
            f"Lokalita: {snapshot.location_label} | Aktualizace: {refreshed}"
        )

        intervals = list(snapshot.horizon_intervals(now_local, horizon_hours))
        intervals.sort(key=lambda item: item.start_time_utc)

        min_values = [item.min_temp_c for item in intervals if item.min_temp_c is not None]
        max_values = [item.max_temp_c for item in intervals if item.max_temp_c is not None]

        if min_values or max_values:
            min_text = f"{min(min_values):.1f}°C" if min_values else "?"
            max_text = f"{max(max_values):.1f}°C" if max_values else "?"
            self.summary_var.set(
                f"Forecast {horizon_hours}h: min {min_text} | max {max_text}"
            )
        else:
            self.summary_var.set(f"Forecast {horizon_hours}h: bez teplotních dat")

        rows = []
        for item in intervals:
            start_local = item.start_time_utc.astimezone().strftime("%d.%m %H:%M")
            end_local = item.end_time_utc.astimezone().strftime("%H:%M")
            stream_label = "-"
            if item.stream_id:
                if item.stream_id.startswith("graf.meteogram."):
                    stream_label = f"POI {item.stream_id.split('.')[-1]}"
                else:
                    stream_label = item.stream_id.split(".")[-1]

            row = (
                f"{start_local} - {end_local}",
                self._format_optional_temp(item.min_temp_c),
                self._format_optional_temp(item.max_temp_c),
                stream_label,
            )
            rows.append(row)

        self._set_table_rows(rows)
        self._draw_chart(intervals)

        if last_error:
            self.status_var.set(f"⚠️ Poslední chyba refresh: {last_error}")
        else:
            self.status_var.set(f"Intervalů v horizontu: {len(intervals)}")

    def _set_table_rows(self, rows):
        """Naplni tabulku radky forecastu.

        Args:
            rows: Kolekce radku pro Treeview.
        """

        for item_id in self.tree.get_children():
            self.tree.delete(item_id)

        for row in rows[:12]:
            self.tree.insert("", tk.END, values=row)

    def _draw_chart(self, intervals):
        """Vykresli jednoduchy graf min/max teplot forecast intervalu.

        Args:
            intervals: Seznam forecast intervalu.
        """

        canvas = self.chart_canvas
        canvas.delete("all")

        width = canvas.winfo_width()
        if width < 50:
            width = 560

        height = self.CANVAS_HEIGHT
        plot_top = 12
        plot_bottom = height - 24

        points = [
            item for item in intervals
            if item.min_temp_c is not None or item.max_temp_c is not None
        ]

        if not points:
            canvas.create_text(
                width // 2,
                height // 2,
                text="Bez dat pro vykreslení",
                fill=self.CANVAS_FG,
                font=("Segoe UI", 9),
            )
            return

        values = []
        for item in points:
            if item.min_temp_c is not None:
                values.append(item.min_temp_c)
            if item.max_temp_c is not None:
                values.append(item.max_temp_c)

        if not values:
            return

        min_v = min(values)
        max_v = max(values)
        if abs(max_v - min_v) < 0.3:
            min_v -= 1.0
            max_v += 1.0

        step_x = width / (len(points) + 1)

        def to_y(temp_c):
            ratio = (temp_c - min_v) / (max_v - min_v)
            return plot_bottom - ratio * (plot_bottom - plot_top)

        canvas.create_line(10, plot_bottom, width - 10, plot_bottom, fill="#555555")
        canvas.create_text(10, plot_top, text=f"{max_v:.1f}°C", anchor="w", fill=self.CANVAS_FG, font=("Segoe UI", 8))
        canvas.create_text(10, plot_bottom, text=f"{min_v:.1f}°C", anchor="sw", fill=self.CANVAS_FG, font=("Segoe UI", 8))

        for idx, item in enumerate(points, start=1):
            x = int(step_x * idx)
            low = item.min_temp_c if item.min_temp_c is not None else item.max_temp_c
            high = item.max_temp_c if item.max_temp_c is not None else item.min_temp_c
            y_low = to_y(low)
            y_high = to_y(high)

            canvas.create_line(x, y_low, x, y_high, fill=self.LINE_COLOR, width=3)
            canvas.create_oval(x - 3, y_low - 3, x + 3, y_low + 3, fill=self.POINT_MIN_COLOR, outline="")
            canvas.create_oval(x - 3, y_high - 3, x + 3, y_high + 3, fill=self.POINT_MAX_COLOR, outline="")

            tick = item.start_time_utc.astimezone().strftime("%H")
            canvas.create_text(x, plot_bottom + 12, text=tick, fill=self.CANVAS_FG, font=("Segoe UI", 8))

    def _format_optional_temp(self, value):
        """Vrati textovy format volitelne teploty.

        Args:
            value: Hodnota teploty nebo None.

        Returns:
            str: Naformatovana hodnota.
        """

        if value is None:
            return "-"
        return f"{value:.1f}"
