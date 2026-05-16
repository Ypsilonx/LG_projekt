# -*- coding: utf-8 -*-
"""Pomocne utility pro praci se spotrebou energie v GUI."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EnergyQuery:
    """Parametry dotazu na ThinQ energy endpoint.

    Attributes:
        view_key: Interni klic pohledu (daily/weekly/monthly/yearly).
        period: API perioda (DAILY nebo MONTHLY).
        start_date: Datum od ve formatu dle periody.
        end_date: Datum do ve formatu dle periody.
        label: Lokalizovany nazev pohledu pro GUI.
    """

    view_key: str
    period: str
    start_date: str
    end_date: str
    label: str


def _shift_month(reference_date: date, offset_months: int) -> date:
    """Posune datum o zadany pocet mesicu a vrati prvni den vysledneho mesice.

    Args:
        reference_date: Vychozi datum.
        offset_months: Posun v mesicich (muze byt i zaporny).

    Returns:
        date: Prvni den ciloveho mesice.
    """

    month_index = reference_date.year * 12 + (reference_date.month - 1) + offset_months
    target_year = month_index // 12
    target_month = (month_index % 12) + 1
    return date(target_year, target_month, 1)


def resolve_energy_query(view_key: str, today: date | None = None) -> EnergyQuery:
    """Vypocita rozsah dat pro vybrany pohled spotreby.

    Args:
        view_key: Klic pohledu (`daily`, `weekly`, `monthly`, `yearly`).
        today: Volitelne referencni datum, primarne pro testy.

    Returns:
        EnergyQuery: Parametry pro volani `get_energy_usage`.
    """

    now_day = today or date.today()
    normalized = (view_key or "weekly").strip().lower()

    if normalized == "daily":
        day = now_day.strftime("%Y%m%d")
        return EnergyQuery(
            view_key="daily",
            period="DAILY",
            start_date=day,
            end_date=day,
            label="Den",
        )

    if normalized == "monthly":
        start_of_month = now_day.replace(day=1).strftime("%Y%m%d")
        return EnergyQuery(
            view_key="monthly",
            period="DAILY",
            start_date=start_of_month,
            end_date=now_day.strftime("%Y%m%d"),
            label="Mesic",
        )

    if normalized == "yearly":
        start_month = _shift_month(now_day.replace(day=1), -11).strftime("%Y%m")
        end_month = now_day.strftime("%Y%m")
        return EnergyQuery(
            view_key="yearly",
            period="MONTHLY",
            start_date=start_month,
            end_date=end_month,
            label="Rok",
        )

    start_of_week = (now_day - timedelta(days=6)).strftime("%Y%m%d")
    return EnergyQuery(
        view_key="weekly",
        period="DAILY",
        start_date=start_of_week,
        end_date=now_day.strftime("%Y%m%d"),
        label="Tyden",
    )


def normalize_energy_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalizuje surova API data do stabilniho tvaru pro GUI.

    Args:
        records: Surovy seznam zaznamu z ThinQ API.

    Returns:
        list[dict[str, Any]]: Serazene zaznamy s poli `usedDate` a `energyUsage` (Wh).
    """

    normalized: list[dict[str, Any]] = []
    for entry in records or []:
        used_date = str(entry.get("usedDate", "")).strip()
        if not used_date:
            continue

        try:
            usage_wh = float(entry.get("energyUsage", 0) or 0)
        except (TypeError, ValueError):
            usage_wh = 0.0

        normalized.append({"usedDate": used_date, "energyUsage": usage_wh})

    normalized.sort(key=lambda item: item.get("usedDate", ""))
    return normalized


def format_used_date(used_date: str, period: str) -> str:
    """Vrati kratky popisek osy X podle periody.

    Args:
        used_date: Datum z API (`YYYYMMDD` nebo `YYYYMM`).
        period: Typ periody (`DAILY` nebo `MONTHLY`).

    Returns:
        str: Uzivatelsky citelny popisek sloupce.
    """

    if period == "MONTHLY" and len(used_date) == 6:
        return f"{used_date[4:6]}/{used_date[0:4]}"

    if len(used_date) == 8:
        return f"{used_date[6:8]}.{used_date[4:6]}."

    return used_date or "-"


def total_energy_kwh(records: list[dict[str, Any]]) -> float:
    """Spocita celkovou spotrebu v kWh.

    Args:
        records: Normalizovane zaznamy spotreby.

    Returns:
        float: Celkova spotreba v kWh.
    """

    total_wh = 0.0
    for entry in records or []:
        try:
            total_wh += float(entry.get("energyUsage", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total_wh / 1000.0


def export_energy_records_csv(
    file_path: str | Path,
    records: list[dict[str, Any]],
    *,
    period: str,
    view_label: str,
) -> None:
    """Exportuje aktualni datovou sadu spotreby do CSV.

    Args:
        file_path: Cilova cesta vystupniho CSV.
        records: Normalizovane zaznamy spotreby.
        period: API perioda (`DAILY`/`MONTHLY`).
        view_label: Lokalizovany nazev pohledu pro hlavicku.
    """

    path = Path(file_path)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file, delimiter=";")
        writer.writerow(["view", "period", "usedDate", "label", "energyUsageWh", "energyUsageKWh"])

        for entry in records or []:
            used_date = str(entry.get("usedDate", ""))
            try:
                usage_wh = float(entry.get("energyUsage", 0) or 0)
            except (TypeError, ValueError):
                usage_wh = 0.0

            writer.writerow(
                [
                    view_label,
                    period,
                    used_date,
                    format_used_date(used_date, period),
                    f"{usage_wh:.2f}",
                    f"{usage_wh / 1000.0:.4f}",
                ]
            )
