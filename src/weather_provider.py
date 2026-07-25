# -*- coding: utf-8 -*-
"""Utilities for CHMI weather forecast retrieval and mode adjustments.

This module provides a lightweight weather provider that consumes
CHMI regional text forecast JSON files and extracts temperature ranges.
The extracted values are used as a planning signal for comfort and
energy-saving mode adjustments.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any
from urllib.parse import urlencode, urljoin

import aiohttp

CHMI_FORECAST_NOW_INDEX_URL = "https://opendata.chmi.cz/meteorology/weather/forecast/now/"
CHMI_METEOGRAM_GRAPH_URL = "https://data-provider.chmi.cz/api/graphs/graf.meteogram"


class WeatherProviderError(RuntimeError):
    """Raised when weather data cannot be fetched or parsed."""


@dataclass(frozen=True)
class WeatherForecastInterval:
    """One forecast interval with optional temperature extremes.

    Args:
        start_time_utc: Interval start in UTC.
        end_time_utc: Interval end in UTC.
        min_temp_c: Minimum expected temperature for interval.
        max_temp_c: Maximum expected temperature for interval.
        stream_id: CHMI stream identifier.
        headline: Optional interval headline.
    """

    start_time_utc: datetime
    end_time_utc: datetime
    min_temp_c: float | None
    max_temp_c: float | None
    stream_id: str
    headline: str | None


@dataclass(frozen=True)
class WeatherForecastSnapshot:
    """Weather forecast snapshot from CHMI.

    Args:
        fetched_at_utc: Time when snapshot was downloaded.
        reference_time_utc: Source reference time.
        provider: Provider identifier.
        region_code: CHMI region code.
        location_label: User-facing location label.
        intervals: Parsed forecast intervals.
        source_files: Source JSON filenames used for this snapshot.
        current_temperature_c: Optional explicit current outdoor temperature.
        current_temperature_source: Optional source label for current outdoor temperature.
    """

    fetched_at_utc: datetime
    reference_time_utc: datetime | None
    provider: str
    region_code: str
    location_label: str
    intervals: tuple[WeatherForecastInterval, ...]
    source_files: tuple[str, ...]
    current_temperature_c: float | None = None
    current_temperature_source: str | None = None

    def horizon_intervals(self, now_local: datetime, horizon_hours: int) -> tuple[WeatherForecastInterval, ...]:
        """Return forecast intervals that overlap requested horizon.

        Args:
            now_local: Current local time.
            horizon_hours: Horizon length in hours.

        Returns:
            tuple[WeatherForecastInterval, ...]: Overlapping intervals.
        """

        now_utc = _to_utc(now_local)
        safe_horizon = max(int(horizon_hours), 1)
        horizon_end_utc = now_utc + timedelta(hours=safe_horizon)
        return tuple(
            interval
            for interval in self.intervals
            if interval.end_time_utc > now_utc and interval.start_time_utc < horizon_end_utc
        )

    def horizon_extremes(self, now_local: datetime, horizon_hours: int) -> tuple[float | None, float | None]:
        """Return min/max temperatures for intervals in requested horizon.

        Args:
            now_local: Current local time.
            horizon_hours: Horizon length in hours.

        Returns:
            tuple[float | None, float | None]: (minimum, maximum)
        """

        return compute_horizon_temperature_extremes(self, now_local, horizon_hours)


@dataclass(frozen=True)
class WeatherModeAdjustment:
    """Mode adjustment recommendation based on weather context.

    Args:
        effective_mode: Mode to execute.
        adjusted: True if mode changed.
        reason: Human-readable reason for decision.
    """

    effective_mode: str
    adjusted: bool
    reason: str


def _to_utc(value: datetime) -> datetime:
    """Convert datetime to UTC.

    Naive datetimes are interpreted in local timezone.

    Args:
        value: Datetime to convert.

    Returns:
        datetime: Time in UTC.
    """

    if value.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        value = value.replace(tzinfo=local_tz)
    return value.astimezone(timezone.utc)


def _parse_iso_datetime(value: Any) -> datetime | None:
    """Parse ISO datetime string into UTC datetime.

    Args:
        value: Raw datetime value.

    Returns:
        datetime | None: Parsed UTC datetime or None.
    """

    if not value:
        return None
    if not isinstance(value, str):
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_temperature_numbers(display_text: str) -> list[float]:
    """Extract temperature numbers from forecast text.

    Args:
        display_text: CHMI display text field.

    Returns:
        list[float]: Parsed temperatures in Celsius.
    """

    normalized = display_text.replace("\xa0", " ").replace("−", "-")
    matches = re.findall(r"-?\d+(?:[\.,]\d+)?", normalized)
    numbers: list[float] = []

    for item in matches:
        try:
            numbers.append(float(item.replace(",", ".")))
        except ValueError:
            continue

    return numbers


def _extract_latest_region_files(index_html: str, region_code: str) -> dict[str, str]:
    """Extract newest CHMI region forecast files from directory index HTML.

    Args:
        index_html: HTML directory listing.
        region_code: CHMI region code.

    Returns:
        dict[str, str]: Mapping prefix -> relative JSON filename.
    """

    normalized_region = region_code.upper().strip()
    pattern = re.compile(
        rf"href=[\"'](?P<filename>web_(?P<prefix>pCK[0-4]tx)_{re.escape(normalized_region)}_(?P<stamp>\d{{6}})\.json)[\"']",
        re.IGNORECASE,
    )

    latest_by_prefix: dict[str, tuple[str, str]] = {}
    for match in pattern.finditer(index_html):
        prefix = match.group("prefix").upper()
        stamp = match.group("stamp")
        filename = match.group("filename")

        previous = latest_by_prefix.get(prefix)
        if previous is None or stamp > previous[0]:
            latest_by_prefix[prefix] = (stamp, filename)

    return {
        prefix: value[1]
        for prefix, value in latest_by_prefix.items()
    }


def _parse_temperature_intervals(payload: dict[str, Any]) -> list[WeatherForecastInterval]:
    """Parse temperature intervals from one CHMI payload.

    Args:
        payload: CHMI JSON payload.

    Returns:
        list[WeatherForecastInterval]: Parsed intervals.
    """

    data_root = payload.get("data")
    if not isinstance(data_root, dict):
        return []

    features = data_root.get("features")
    if not isinstance(features, list) or not features:
        return []

    feature = features[0]
    if not isinstance(feature, dict):
        return []

    properties = feature.get("properties")
    if not isinstance(properties, dict):
        return []

    blocks = properties.get("data")
    if not isinstance(blocks, list):
        return []

    stream_id = str(payload.get("datovyTokID", "")).strip()
    interval_map: dict[tuple[datetime, datetime], dict[str, Any]] = {}

    for block in blocks:
        if not isinstance(block, dict):
            continue

        name = str(block.get("name", "")).strip()
        if name not in {"textMinimumTemperature", "textMaximumTemperature"}:
            continue

        start_utc = _parse_iso_datetime(block.get("startTime"))
        end_utc = _parse_iso_datetime(block.get("endTime"))
        if start_utc is None or end_utc is None:
            continue

        numbers = _extract_temperature_numbers(str(block.get("displayText", "")))
        if not numbers:
            continue

        key = (start_utc, end_utc)
        current = interval_map.setdefault(
            key,
            {
                "min_temp_c": None,
                "max_temp_c": None,
                "headline": block.get("headline"),
            },
        )

        if name == "textMinimumTemperature":
            min_value = min(numbers)
            previous_min = current["min_temp_c"]
            current["min_temp_c"] = min_value if previous_min is None else min(previous_min, min_value)
        elif name == "textMaximumTemperature":
            max_value = max(numbers)
            previous_max = current["max_temp_c"]
            current["max_temp_c"] = max_value if previous_max is None else max(previous_max, max_value)

    intervals: list[WeatherForecastInterval] = []
    for (start_utc, end_utc), values in interval_map.items():
        intervals.append(
            WeatherForecastInterval(
                start_time_utc=start_utc,
                end_time_utc=end_utc,
                min_temp_c=values["min_temp_c"],
                max_temp_c=values["max_temp_c"],
                stream_id=stream_id,
                headline=str(values["headline"]) if values["headline"] else None,
            )
        )

    return intervals


def _parse_meteogram_temperature_intervals(
    payload: dict[str, Any],
    poi_id: str,
) -> list[WeatherForecastInterval]:
    """Parse hourly meteogram points into forecast intervals.

    Args:
        payload: Meteogram JSON payload.
        poi_id: Meteogram point identifier.

    Returns:
        list[WeatherForecastInterval]: Parsed hourly intervals.

    Raises:
        WeatherProviderError: If payload does not contain usable hourly temperature points.
    """

    raw_points = payload.get("data")
    if not isinstance(raw_points, list):
        raise WeatherProviderError("Meteogram payload does not contain list 'data'.")

    points: list[tuple[datetime, float]] = []
    for row in raw_points:
        if not isinstance(row, dict):
            continue

        validity_time = _parse_iso_datetime(row.get("validityTime"))
        temp_c = _safe_float(row.get("t2m"))
        if validity_time is None or temp_c is None:
            continue

        points.append((validity_time, temp_c))

    if not points:
        raise WeatherProviderError(
            "Meteogram payload does not contain hourly 't2m' temperature points."
        )

    points.sort(key=lambda item: item[0])

    stream_id = f"graf.meteogram.{poi_id}"
    intervals: list[WeatherForecastInterval] = []

    for index, (start_time_utc, temp_c) in enumerate(points):
        if index + 1 < len(points):
            end_time_utc = points[index + 1][0]
        else:
            end_time_utc = start_time_utc + timedelta(hours=1)

        if end_time_utc <= start_time_utc:
            end_time_utc = start_time_utc + timedelta(hours=1)

        intervals.append(
            WeatherForecastInterval(
                start_time_utc=start_time_utc,
                end_time_utc=end_time_utc,
                min_temp_c=temp_c,
                max_temp_c=temp_c,
                stream_id=stream_id,
                headline=None,
            )
        )

    return intervals


async def _download_json(session: aiohttp.ClientSession, url: str) -> dict[str, Any]:
    """Download and decode JSON payload.

    Args:
        session: Existing aiohttp session.
        url: Target URL.

    Returns:
        dict[str, Any]: Parsed JSON object.

    Raises:
        WeatherProviderError: On HTTP or JSON decode error.
    """

    try:
        async with session.get(url) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
    except Exception as exc:
        raise WeatherProviderError(f"CHMI fetch failed for {url}: {exc}") from exc

    if not isinstance(payload, dict):
        raise WeatherProviderError(f"CHMI payload from {url} is not a JSON object.")

    return payload


async def fetch_chmi_region_forecast(
    session: aiohttp.ClientSession,
    region_code: str,
    location_label: str,
) -> WeatherForecastSnapshot:
    """Fetch CHMI regional forecast and extract temperature intervals.

    Args:
        session: Existing aiohttp session.
        region_code: CHMI region code (for example RPZL).
        location_label: User-facing location label.

    Returns:
        WeatherForecastSnapshot: Parsed weather snapshot.

    Raises:
        WeatherProviderError: On missing files or parse failures.
    """

    normalized_region = region_code.upper().strip()
    if not normalized_region:
        raise WeatherProviderError("Region code must not be empty.")

    try:
        async with session.get(CHMI_FORECAST_NOW_INDEX_URL) as response:
            response.raise_for_status()
            index_html = await response.text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise WeatherProviderError(f"Failed to load CHMI index: {exc}") from exc

    files_by_prefix = _extract_latest_region_files(index_html, normalized_region)
    if not files_by_prefix:
        raise WeatherProviderError(
            f"No CHMI forecast files found for region {normalized_region}."
        )

    source_files = tuple(files_by_prefix[prefix] for prefix in sorted(files_by_prefix.keys()))
    urls = [urljoin(CHMI_FORECAST_NOW_INDEX_URL, file_name) for file_name in source_files]

    results = await asyncio.gather(
        *[_download_json(session, url) for url in urls],
        return_exceptions=True,
    )

    payloads: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        payloads.append(result)

    if not payloads:
        raise WeatherProviderError("All CHMI forecast file downloads failed.")

    intervals: list[WeatherForecastInterval] = []
    reference_time_utc: datetime | None = None

    for payload in payloads:
        intervals.extend(_parse_temperature_intervals(payload))

        data_root = payload.get("data")
        if isinstance(data_root, dict):
            features = data_root.get("features")
            if isinstance(features, list) and features:
                feature = features[0]
                if isinstance(feature, dict):
                    properties = feature.get("properties")
                    if isinstance(properties, dict):
                        current_reference = _parse_iso_datetime(properties.get("referenceTime"))
                        if current_reference is not None:
                            if reference_time_utc is None or current_reference > reference_time_utc:
                                reference_time_utc = current_reference

    intervals.sort(key=lambda item: (item.start_time_utc, item.end_time_utc, item.stream_id))

    if not intervals:
        raise WeatherProviderError(
            f"No temperature intervals parsed for region {normalized_region}."
        )

    return WeatherForecastSnapshot(
        fetched_at_utc=datetime.now(timezone.utc),
        reference_time_utc=reference_time_utc,
        provider="CHMI",
        region_code=normalized_region,
        location_label=location_label,
        intervals=tuple(intervals),
        source_files=source_files,
    )


async def fetch_chmi_meteogram_forecast(
    session: aiohttp.ClientSession,
    poi_id: str | int,
    location_label: str,
    x: float | None = None,
    y: float | None = None,
) -> WeatherForecastSnapshot:
    """Fetch CHMI meteogram forecast and convert it into hourly intervals.

    Args:
        session: Existing aiohttp session.
        poi_id: Meteogram point identifier (for example 510).
        location_label: User-facing location label.
        x: Optional longitude override used by CHMI endpoint.
        y: Optional latitude override used by CHMI endpoint.

    Returns:
        WeatherForecastSnapshot: Parsed meteogram snapshot.

    Raises:
        WeatherProviderError: On validation, HTTP, decode, or parsing failures.
    """

    normalized_poi_id = str(poi_id).strip()
    if not normalized_poi_id or not normalized_poi_id.isdigit():
        raise WeatherProviderError("Meteogram poi_id must be a numeric value.")

    params: dict[str, str] = {}
    if x is not None:
        params["x"] = f"{float(x):.6f}"
    if y is not None:
        params["y"] = f"{float(y):.6f}"

    endpoint = f"{CHMI_METEOGRAM_GRAPH_URL}/{normalized_poi_id}"

    try:
        async with session.get(endpoint, params=params) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
    except Exception as exc:
        raise WeatherProviderError(f"CHMI meteogram fetch failed for {endpoint}: {exc}") from exc

    if not isinstance(payload, dict):
        raise WeatherProviderError(f"CHMI meteogram payload from {endpoint} is not a JSON object.")

    intervals = _parse_meteogram_temperature_intervals(payload, normalized_poi_id)

    source_url = endpoint
    if params:
        source_url = f"{endpoint}?{urlencode(params)}"

    normalized_label = str(location_label).strip() or f"Meteogram POI {normalized_poi_id}"
    reference_time_utc = intervals[0].start_time_utc if intervals else None

    return WeatherForecastSnapshot(
        fetched_at_utc=datetime.now(timezone.utc),
        reference_time_utc=reference_time_utc,
        provider="CHMI_METEOGRAM",
        region_code=f"POI{normalized_poi_id}",
        location_label=normalized_label,
        intervals=tuple(intervals),
        source_files=(source_url,),
    )


def compute_horizon_temperature_extremes(
    snapshot: WeatherForecastSnapshot,
    now_local: datetime,
    horizon_hours: int,
) -> tuple[float | None, float | None]:
    """Compute min/max temperatures inside forecast horizon.

    Args:
        snapshot: Weather forecast snapshot.
        now_local: Current local time.
        horizon_hours: Forecast horizon in hours.

    Returns:
        tuple[float | None, float | None]: (minimum, maximum)
    """

    horizon_intervals = snapshot.horizon_intervals(now_local, horizon_hours)
    mins = [item.min_temp_c for item in horizon_intervals if item.min_temp_c is not None]
    maxs = [item.max_temp_c for item in horizon_intervals if item.max_temp_c is not None]

    min_temp = min(mins) if mins else None
    max_temp = max(maxs) if maxs else None
    return min_temp, max_temp


def _estimate_current_temperature_from_intervals(
    intervals: tuple[WeatherForecastInterval, ...] | list[WeatherForecastInterval],
    now_local: datetime,
) -> float | None:
    """Estimate current outdoor temperature from forecast intervals.

    The value is derived from the interval overlapping current time.
    If no interval overlaps "now", the nearest interval in time is used.

    Args:
        intervals: Forecast intervals to inspect.
        now_local: Current local time.

    Returns:
        float | None: Estimated outdoor temperature in Celsius.
    """

    if not intervals:
        return None

    now_utc = _to_utc(now_local)

    overlapping = [
        interval
        for interval in intervals
        if interval.start_time_utc <= now_utc < interval.end_time_utc
    ]

    if overlapping:
        candidates = overlapping
    else:
        def _midpoint_utc(interval: WeatherForecastInterval) -> datetime:
            return interval.start_time_utc + ((interval.end_time_utc - interval.start_time_utc) / 2)

        candidates = sorted(
            intervals,
            key=lambda interval: abs((_midpoint_utc(interval) - now_utc).total_seconds()),
        )

    for interval in candidates:
        if interval.min_temp_c is not None and interval.max_temp_c is not None:
            return float((interval.min_temp_c + interval.max_temp_c) / 2.0)
        if interval.max_temp_c is not None:
            return float(interval.max_temp_c)
        if interval.min_temp_c is not None:
            return float(interval.min_temp_c)

    return None


def estimate_current_outdoor_temperature(
    snapshot: WeatherForecastSnapshot | None,
    now_local: datetime,
) -> float | None:
    """Estimate current outdoor temperature from the best available source.

    Explicit values (for example from an external sensor or a future ESP32 feed)
    take precedence. If no explicit value exists, the function falls back to the
    forecast interval overlapping current time.

    Args:
        snapshot: Latest weather snapshot.
        now_local: Current local time.

    Returns:
        float | None: Estimated or measured outdoor temperature in Celsius.
    """

    if snapshot is None:
        return None

    if snapshot.current_temperature_c is not None:
        return float(snapshot.current_temperature_c)

    if not snapshot.intervals:
        return None

    return _estimate_current_temperature_from_intervals(snapshot.intervals, now_local)


def _select_weather_fallback_mode(available_modes: set[str] | None) -> str | None:
    """Choose fallback mode for weather-driven relaxation.

    Args:
        available_modes: Optional set of supported mode names.

    Returns:
        str | None: Fallback mode or None when no safe option exists.
    """

    if available_modes is None:
        return "FAN"

    normalized = {str(mode).upper().strip() for mode in available_modes}
    if "FAN" in normalized:
        return "FAN"
    if "AUTO" in normalized:
        return "AUTO"
    return None


def _safe_float(value: Any) -> float | None:
    """Convert value to float, returning None on failure.

    Args:
        value: Raw numeric value.

    Returns:
        float | None: Parsed float.
    """

    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_temp(value: float | None) -> str:
    """Format optional temperature for log and UI reasons.

    Args:
        value: Temperature in Celsius.

    Returns:
        str: Human-readable value.
    """

    if value is None:
        return "?"
    return f"{value:.1f}C"


def decide_mode_by_weather(
    requested_mode: str,
    requested_temperature_c: float | int | None,
    device_current_temperature_c: float | int | None,
    ac_indoor_temperature_proxy_offset_c: float,
    snapshot: WeatherForecastSnapshot | None,
    horizon_hours: int,
    comfort_margin_c: float,
    available_modes: set[str] | None = None,
    now_local: datetime | None = None,
) -> WeatherModeAdjustment:
    """Decide whether scheduled mode should be relaxed by weather context.

    The mode is adjusted only for COOL and HEAT.
    COOL is relaxed when neither forecast nor adjusted sensor indicates heat pressure.
    HEAT is relaxed when neither forecast nor adjusted sensor indicates cold pressure.

    Args:
        requested_mode: Original scheduled mode.
        requested_temperature_c: Scheduled target temperature.
        device_current_temperature_c: Current temperature reported by the AC.
        ac_indoor_temperature_proxy_offset_c: Temporary proxy offset applied
            only until a real indoor thermostat or sensor is wired in.
        snapshot: Weather forecast snapshot.
        horizon_hours: Forecast horizon for decision.
        comfort_margin_c: Comfort hysteresis around target temperature.
        available_modes: Supported mode names.
        now_local: Current local time override.

    Returns:
        WeatherModeAdjustment: Final mode and explanation.
    """

    normalized_mode = str(requested_mode or "").upper().strip()
    if normalized_mode not in {"COOL", "HEAT"}:
        return WeatherModeAdjustment(
            effective_mode=normalized_mode,
            adjusted=False,
            reason="Pocasi: uprava se aplikuje pouze na COOL/HEAT.",
        )

    target_temp_c = _safe_float(requested_temperature_c)
    if target_temp_c is None:
        return WeatherModeAdjustment(
            effective_mode=normalized_mode,
            adjusted=False,
            reason="Pocasi: plan nema cilovou teplotu, rezim nechavam beze zmeny.",
        )

    if snapshot is None:
        return WeatherModeAdjustment(
            effective_mode=normalized_mode,
            adjusted=False,
            reason="Pocasi: CHMI data nejsou dostupna, rezim nechavam beze zmeny.",
        )

    effective_now = now_local or datetime.now()
    horizon_min_c, horizon_max_c = snapshot.horizon_extremes(effective_now, horizon_hours)

    if horizon_min_c is None and horizon_max_c is None:
        return WeatherModeAdjustment(
            effective_mode=normalized_mode,
            adjusted=False,
            reason="Pocasi: v horizontu nejsou teplotni data, rezim nechavam beze zmeny.",
        )

    fallback_mode = _select_weather_fallback_mode(available_modes)
    if not fallback_mode or fallback_mode == normalized_mode:
        return WeatherModeAdjustment(
            effective_mode=normalized_mode,
            adjusted=False,
            reason="Pocasi: fallback rezim neni dostupny, rezim nechavam beze zmeny.",
        )

    current_temp_c = _safe_float(device_current_temperature_c)
    adjusted_sensor_c = (
        current_temp_c + float(ac_indoor_temperature_proxy_offset_c)
        if current_temp_c is not None
        else None
    )

    margin_c = max(float(comfort_margin_c), 0.0)
    sensor_text = _fmt_temp(adjusted_sensor_c)
    forecast_text = f"{_fmt_temp(horizon_min_c)}..{_fmt_temp(horizon_max_c)}"

    if normalized_mode == "COOL":
        forecast_requires_cooling = (
            horizon_max_c is not None and horizon_max_c > (target_temp_c + margin_c)
        )
        sensor_requires_cooling = (
            adjusted_sensor_c is not None and adjusted_sensor_c > (target_temp_c + margin_c)
        )

        if not forecast_requires_cooling and not sensor_requires_cooling:
            return WeatherModeAdjustment(
                effective_mode=fallback_mode,
                adjusted=True,
                reason=(
                    "Pocasi: ochlazeni neni v horizontu nutne "
                    f"(forecast {forecast_text}, senzor {sensor_text}), "
                    f"prepina na {fallback_mode}."
                ),
            )

        return WeatherModeAdjustment(
            effective_mode=normalized_mode,
            adjusted=False,
            reason=(
                "Pocasi: ochlazeni potvrzeno "
                f"(forecast {forecast_text}, senzor {sensor_text}), "
                "rezim COOL zachovan."
            ),
        )

    forecast_requires_heating = (
        horizon_min_c is not None and horizon_min_c < (target_temp_c - margin_c)
    )
    sensor_requires_heating = (
        adjusted_sensor_c is not None and adjusted_sensor_c < (target_temp_c - margin_c)
    )

    if not forecast_requires_heating and not sensor_requires_heating:
        return WeatherModeAdjustment(
            effective_mode=fallback_mode,
            adjusted=True,
            reason=(
                "Pocasi: pritapeni neni v horizontu nutne "
                f"(forecast {forecast_text}, senzor {sensor_text}), "
                f"prepina na {fallback_mode}."
            ),
        )

    return WeatherModeAdjustment(
        effective_mode=normalized_mode,
        adjusted=False,
        reason=(
            "Pocasi: pritapeni potvrzeno "
            f"(forecast {forecast_text}, senzor {sensor_text}), "
            "rezim HEAT zachovan."
        ),
    )


def format_weather_snapshot_line(
    snapshot: WeatherForecastSnapshot | None,
    now_local: datetime,
    horizon_hours: int,
    last_refresh_local: datetime | None = None,
    last_error: str | None = None,
) -> str:
    """Create one-line weather status for automation panel.

    Args:
        snapshot: Latest weather snapshot.
        now_local: Current local time.
        horizon_hours: Forecast horizon in hours.
        last_refresh_local: Last successful refresh time in local timezone.
        last_error: Last weather refresh error.

    Returns:
        str: Human-readable weather summary line.
    """

    if snapshot is None:
        if last_error:
            return f"Pocasi: data nejsou dostupna ({last_error})."
        return "Pocasi: ceka se na prvni data CHMI."

    min_temp_c, max_temp_c = snapshot.horizon_extremes(now_local, horizon_hours)
    if last_refresh_local is None:
        refreshed_text = "?"
    else:
        refreshed_text = last_refresh_local.strftime("%H:%M")

    return (
        f"Pocasi {snapshot.provider} {snapshot.region_code} {snapshot.location_label}: "
        f"{_fmt_temp(min_temp_c)}..{_fmt_temp(max_temp_c)} / {horizon_hours}h, "
        f"aktualizace {refreshed_text}."
    )
