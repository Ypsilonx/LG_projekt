# -*- coding: utf-8 -*-
"""Pomocne utility pro praci se spotrebou energie v GUI."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


# Ceske nazvy mesicu v nominativu (index 1..12) pro popisky obdobi.
_CZECH_MONTHS = (
    "",
    "leden", "únor", "březen", "duben", "květen", "červen",
    "červenec", "srpen", "září", "říjen", "listopad", "prosinec",
)


@dataclass(frozen=True)
class EnergyQuery:
    """Parametry dotazu na ThinQ energy endpoint.

    Attributes:
        view_key: Interni klic pohledu (daily/weekly/monthly/yearly).
        period: API perioda (DAILY nebo MONTHLY).
        start_date: Datum od ve formatu dle periody.
        end_date: Datum do ve formatu dle periody.
        label: Lokalizovany nazev pohledu pro GUI.
        offset: Posun do historie v poctu obdobi (0 = aktualni, kladne = zpet).
        range_label: Citelny popisek konkretniho obdobi (napr. "květen 2026").
    """

    view_key: str
    period: str
    start_date: str
    end_date: str
    label: str
    offset: int = 0
    range_label: str = ""


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


def _last_day_of_month(any_day: date) -> date:
    """Vrati posledni den mesice, do nehoz dane datum spada.

    Args:
        any_day: Libovolny den v mesici.

    Returns:
        date: Posledni kalendarni den daneho mesice.
    """

    first_next = _shift_month(any_day, 1)
    return first_next - timedelta(days=1)


def _fmt_day(day: date) -> str:
    """Naformatuje datum jako `D. M. RRRR` (ceska konvence bez nul navic).

    Args:
        day: Datum k naformatovani.

    Returns:
        str: Citelne datum, napr. `1. 6. 2026`.
    """

    return f"{day.day}. {day.month}. {day.year}"


def resolve_energy_query(
    view_key: str,
    today: date | None = None,
    offset: int = 0,
) -> EnergyQuery:
    """Vypocita rozsah dat pro vybrany pohled spotreby.

    Args:
        view_key: Klic pohledu (`daily`, `weekly`, `monthly`, `yearly`).
        today: Volitelne referencni datum, primarne pro testy.
        offset: Posun do historie v poctu obdobi (0 = aktualni, kladne = zpet).
            Den -> dny, tyden -> tydny, mesic -> mesice, rok -> roky.

    Returns:
        EnergyQuery: Parametry pro volani `get_energy_usage`.
    """

    now_day = today or date.today()
    normalized = (view_key or "weekly").strip().lower()
    steps = max(0, int(offset or 0))

    if normalized == "daily":
        target = now_day - timedelta(days=steps)
        day = target.strftime("%Y%m%d")
        return EnergyQuery(
            view_key="daily",
            period="DAILY",
            start_date=day,
            end_date=day,
            label="Den",
            offset=steps,
            range_label=_fmt_day(target),
        )

    if normalized == "monthly":
        month_first = _shift_month(now_day.replace(day=1), -steps)
        # U aktualniho mesice koncime dneskem, u historickych poslednim dnem mesice.
        if steps == 0:
            month_end = now_day
        else:
            month_end = _last_day_of_month(month_first)
        return EnergyQuery(
            view_key="monthly",
            period="DAILY",
            start_date=month_first.strftime("%Y%m%d"),
            end_date=month_end.strftime("%Y%m%d"),
            label="Mesic",
            offset=steps,
            range_label=f"{_CZECH_MONTHS[month_first.month]} {month_first.year}",
        )

    if normalized == "yearly":
        end_month_first = _shift_month(now_day.replace(day=1), -12 * steps)
        start_month_first = _shift_month(end_month_first, -11)
        return EnergyQuery(
            view_key="yearly",
            period="MONTHLY",
            start_date=start_month_first.strftime("%Y%m"),
            end_date=end_month_first.strftime("%Y%m"),
            label="Rok",
            offset=steps,
            range_label=(
                f"{start_month_first.month:02d}/{start_month_first.year} – "
                f"{end_month_first.month:02d}/{end_month_first.year}"
            ),
        )

    # weekly (vychozi): 7denni okno posunute o `steps` tydnu.
    week_end = now_day - timedelta(days=7 * steps)
    week_start = week_end - timedelta(days=6)
    return EnergyQuery(
        view_key="weekly",
        period="DAILY",
        start_date=week_start.strftime("%Y%m%d"),
        end_date=week_end.strftime("%Y%m%d"),
        label="Tyden",
        offset=steps,
        range_label=f"{_fmt_day(week_start)} – {_fmt_day(week_end)}",
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


def _is_number(value: Any) -> bool:
    """Overi, zda lze hodnotu prevest na float.

    Args:
        value: Libovolna hodnota z API zaznamu.

    Returns:
        bool: True pokud je hodnota cislo, jinak False.
    """

    try:
        float(value if value is not None else 0)
        return True
    except (TypeError, ValueError):
        return False


def _iso_used_date(used_date: str, period: str) -> str:
    """Prevede API datum na ISO tvar pro snadne zpracovani v tabulkach.

    Args:
        used_date: Datum z API (`YYYYMMDD` nebo `YYYYMM`).
        period: API perioda (`DAILY`/`MONTHLY`).

    Returns:
        str: ISO datum (`RRRR-MM-DD` nebo `RRRR-MM`), nebo puvodni hodnota.
    """

    if period == "MONTHLY" and len(used_date) == 6:
        return f"{used_date[0:4]}-{used_date[4:6]}"

    if len(used_date) == 8:
        return f"{used_date[0:4]}-{used_date[4:6]}-{used_date[6:8]}"

    return used_date


def build_energy_csv_text(
    records: list[dict[str, Any]],
    *,
    period: str,
    view_label: str,
    range_label: str = "",
) -> str:
    """Sestavi podrobny CSV obsah spotreby jako text.

    Sloupce jsou voleny pro maximalni vyuzitelnost v tabulkovem procesoru:
    pohled, obdobi, perioda, raw i ISO datum, popisek, spotreba ve Wh i kWh
    a procentni podil na celkove spotrebe obdobi.

    Args:
        records: Normalizovane zaznamy spotreby.
        period: API perioda (`DAILY`/`MONTHLY`).
        view_label: Lokalizovany nazev pohledu (napr. `Tyden`).
        range_label: Citelny popisek konkretniho obdobi (napr. `květen 2026`).

    Returns:
        str: CSV obsah (oddelovac `;`), bez BOM.
    """

    total_wh = sum(
        float(entry.get("energyUsage", 0) or 0)
        for entry in (records or [])
        if _is_number(entry.get("energyUsage"))
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "view",
            "range",
            "period",
            "usedDate",
            "isoDate",
            "label",
            "energyUsageWh",
            "energyUsageKWh",
            "sharePct",
        ]
    )

    for entry in records or []:
        used_date = str(entry.get("usedDate", ""))
        try:
            usage_wh = float(entry.get("energyUsage", 0) or 0)
        except (TypeError, ValueError):
            usage_wh = 0.0

        share_pct = (usage_wh / total_wh * 100.0) if total_wh > 0 else 0.0

        writer.writerow(
            [
                view_label,
                range_label,
                period,
                used_date,
                _iso_used_date(used_date, period),
                format_used_date(used_date, period),
                f"{usage_wh:.2f}",
                f"{usage_wh / 1000.0:.4f}",
                f"{share_pct:.1f}",
            ]
        )

    return buffer.getvalue()


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
