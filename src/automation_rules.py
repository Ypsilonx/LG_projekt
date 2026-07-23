# -*- coding: utf-8 -*-
"""
Season-aware automation rules for scheduled climate control.

This module provides a validated configuration model and mode resolution
logic for the first automation phase:
- COOL mode is allowed only in configured seasons (default: SUMMER).
- Outside allowed seasons, mode can be blocked or replaced by fallback mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

SEASON_CODES = ("WINTER", "TRANSITION", "SUMMER")
SEASON_LABELS_CZ = {
    "WINTER": "zima",
    "TRANSITION": "jaro/podzim",
    "SUMMER": "leto",
}

DEFAULT_AUTOMATION_RULES: dict[str, Any] = {
    "season_months": {
        "WINTER": [11, 12, 1, 2, 3],
        "TRANSITION": [4, 5, 9, 10],
        "SUMMER": [6, 7, 8],
    },
    "cooling_allowed_seasons": ["SUMMER"],
    "cooling_block_fallback_mode": "HEAT",
    "manual_override_requires_resume_button": True,
    "strategy": "comfort_with_energy_saving",
    "weather": {
        "enabled": True,
        "sensor_offset_c": -2.0,
        "use_short_term_forecast": True,
        "provider": "CHMI_METEOGRAM",
        "chmi_region_code": "RPZL",
        "chmi_location_label": "Valašské Meziříčí",
        "chmi_meteogram_poi_id": "510",
        "chmi_meteogram_x": None,
        "chmi_meteogram_y": None,
        "forecast_horizon_hours": 24,
        "refresh_interval_hours": 3,
        "comfort_margin_c": 1.0,
        "prefer_aladin_model": True,
        "adjust_mode_by_forecast": True,
        "current_temperature_c": None,
        "current_temperature_source": "external",
        "current_temperature_url": None,
    },
}


class AutomationRulesError(ValueError):
    """Error raised when automation rules configuration is invalid."""


@dataclass(frozen=True)
class WeatherPlanningConfig:
    """Configuration for weather-related planning parameters.

    Args:
        enabled: Enables weather-based logic (future phases).
        sensor_offset_c: Sensor correction offset in degrees Celsius.
        use_short_term_forecast: Enables short-term forecast usage.
        provider: Weather provider identifier.
        chmi_region_code: CHMI regional forecast code.
        chmi_location_label: User-facing location label for UI.
        chmi_meteogram_poi_id: CHMI meteogram point identifier.
        chmi_meteogram_x: Optional longitude override for meteogram endpoint.
        chmi_meteogram_y: Optional latitude override for meteogram endpoint.
        forecast_horizon_hours: Forecast horizon used in planning.
        refresh_interval_hours: Weather refresh interval.
        comfort_margin_c: Temperature margin for comfort/economy decisions.
        prefer_aladin_model: User preference for ALADIN-backed CHMI data.
        adjust_mode_by_forecast: Enables weather-based mode relaxation.
    """

    enabled: bool
    sensor_offset_c: float
    use_short_term_forecast: bool
    provider: str
    chmi_region_code: str
    chmi_location_label: str
    chmi_meteogram_poi_id: str
    chmi_meteogram_x: float | None
    chmi_meteogram_y: float | None
    forecast_horizon_hours: int
    refresh_interval_hours: int
    comfort_margin_c: float
    prefer_aladin_model: bool
    adjust_mode_by_forecast: bool


@dataclass(frozen=True)
class AutomationRulesConfig:
    """Validated automation rules configuration.

    Args:
        season_months: Mapping of season code to tuple of month numbers.
        cooling_allowed_seasons: Seasons where COOL mode can be used.
        cooling_block_fallback_mode: Mode used when COOL is blocked.
        manual_override_requires_resume_button: Override behavior policy.
        strategy: High-level strategy label for future policy tuning.
        weather: Weather planning settings.
    """

    season_months: dict[str, tuple[int, ...]]
    cooling_allowed_seasons: tuple[str, ...]
    cooling_block_fallback_mode: str | None
    manual_override_requires_resume_button: bool
    strategy: str
    weather: WeatherPlanningConfig


@dataclass(frozen=True)
class ModeResolution:
    """Result of schedule mode validation against automation rules.

    Args:
        allowed: True if schedule execution can continue.
        requested_mode: Original requested mode from schedule.
        effective_mode: Mode that should be executed.
        season: Season code for evaluated timestamp.
        reason: Human-readable decision reason.
        adjusted: True if effective mode differs from requested mode.
    """

    allowed: bool
    requested_mode: str
    effective_mode: str | None
    season: str
    reason: str
    adjusted: bool = False


def default_automation_rules_payload() -> dict[str, Any]:
    """Return a deep copy of default automation rules payload.

    Returns:
        dict[str, Any]: Default JSON-serializable rule structure.
    """

    return json.loads(json.dumps(DEFAULT_AUTOMATION_RULES))


def _normalize_month_list(months: Any, field_name: str) -> tuple[int, ...]:
    """Normalize and validate month list.

    Args:
        months: Raw value expected to contain month numbers.
        field_name: Field name used in validation errors.

    Returns:
        tuple[int, ...]: Normalized month list.

    Raises:
        AutomationRulesError: If value is invalid.
    """

    if not isinstance(months, list) or not months:
        raise AutomationRulesError(f"{field_name} must be a non-empty list.")

    normalized: list[int] = []
    for item in months:
        try:
            month = int(item)
        except (TypeError, ValueError) as exc:
            raise AutomationRulesError(f"{field_name} contains invalid month value: {item}") from exc

        if month < 1 or month > 12:
            raise AutomationRulesError(f"{field_name} month {month} is out of range 1..12.")
        normalized.append(month)

    if len(set(normalized)) != len(normalized):
        raise AutomationRulesError(f"{field_name} contains duplicate months.")

    return tuple(normalized)


def _parse_season_months(raw: Any) -> dict[str, tuple[int, ...]]:
    """Parse and validate season to month mapping.

    Args:
        raw: Raw season_months object from JSON.

    Returns:
        dict[str, tuple[int, ...]]: Validated season mapping.

    Raises:
        AutomationRulesError: If structure or values are invalid.
    """

    if not isinstance(raw, dict):
        raise AutomationRulesError("season_months must be an object.")

    season_months: dict[str, tuple[int, ...]] = {}
    seen_months: set[int] = set()

    for season_code in SEASON_CODES:
        months = _normalize_month_list(raw.get(season_code), f"season_months.{season_code}")

        overlap = seen_months.intersection(months)
        if overlap:
            overlap_text = ", ".join(str(value) for value in sorted(overlap))
            raise AutomationRulesError(
                f"Months overlap between seasons. Duplicated months: {overlap_text}."
            )

        seen_months.update(months)
        season_months[season_code] = months

    expected_months = set(range(1, 13))
    if seen_months != expected_months:
        missing = sorted(expected_months.difference(seen_months))
        missing_text = ", ".join(str(value) for value in missing)
        raise AutomationRulesError(f"season_months must cover all months 1..12. Missing: {missing_text}.")

    return season_months


def _parse_cooling_allowed_seasons(
    raw: Any,
    season_months: dict[str, tuple[int, ...]],
) -> tuple[str, ...]:
    """Parse and validate seasons where cooling is allowed.

    Args:
        raw: Raw cooling_allowed_seasons JSON value.
        season_months: Validated season mapping.

    Returns:
        tuple[str, ...]: Normalized season codes.

    Raises:
        AutomationRulesError: If value is invalid.
    """

    if not isinstance(raw, list) or not raw:
        raise AutomationRulesError("cooling_allowed_seasons must be a non-empty list.")

    allowed: list[str] = []
    known_seasons = set(season_months.keys())

    for item in raw:
        season_code = str(item).upper().strip()
        if season_code not in known_seasons:
            raise AutomationRulesError(
                f"Unknown season in cooling_allowed_seasons: {item}."
            )
        if season_code not in allowed:
            allowed.append(season_code)

    return tuple(allowed)


def _parse_weather_settings(raw: Any) -> WeatherPlanningConfig:
    """Parse weather planning settings.

    Args:
        raw: Raw weather object from JSON.

    Returns:
        WeatherPlanningConfig: Validated weather settings.

    Raises:
        AutomationRulesError: If value types are invalid.
    """

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise AutomationRulesError("weather must be an object.")

    try:
        sensor_offset_c = float(raw.get("sensor_offset_c", 0.0))
    except (TypeError, ValueError) as exc:
        raise AutomationRulesError("weather.sensor_offset_c must be a number.") from exc

    provider = str(raw.get("provider", "CHMI_METEOGRAM")).upper().strip() or "CHMI_METEOGRAM"
    allowed_providers = {"CHMI", "CHMI_METEOGRAM"}
    if provider not in allowed_providers:
        known_providers = ", ".join(sorted(allowed_providers))
        raise AutomationRulesError(
            f"weather.provider must be one of: {known_providers}."
        )

    chmi_region_code = str(raw.get("chmi_region_code", "RPZL")).upper().strip() or "RPZL"
    chmi_location_label = str(
        raw.get("chmi_location_label", "Valašské Meziříčí")
    ).strip() or "Valašské Meziříčí"
    chmi_meteogram_poi_id = str(raw.get("chmi_meteogram_poi_id", "510")).strip() or "510"

    if not chmi_meteogram_poi_id.isdigit():
        raise AutomationRulesError("weather.chmi_meteogram_poi_id must be numeric.")

    def _parse_optional_coordinate(field_name: str) -> float | None:
        """Parse optional meteogram coordinate value from weather settings.

        Args:
            field_name: Name of weather JSON field.

        Returns:
            float | None: Parsed coordinate or None when value is not provided.

        Raises:
            AutomationRulesError: If provided value is not numeric.
        """

        raw_value = raw.get(field_name)
        if raw_value in (None, ""):
            return None

        try:
            return float(raw_value)
        except (TypeError, ValueError) as exc:
            raise AutomationRulesError(f"weather.{field_name} must be a number or null.") from exc

    chmi_meteogram_x = _parse_optional_coordinate("chmi_meteogram_x")
    chmi_meteogram_y = _parse_optional_coordinate("chmi_meteogram_y")

    try:
        forecast_horizon_hours = int(raw.get("forecast_horizon_hours", 24))
    except (TypeError, ValueError) as exc:
        raise AutomationRulesError("weather.forecast_horizon_hours must be an integer.") from exc

    if forecast_horizon_hours < 1 or forecast_horizon_hours > 72:
        raise AutomationRulesError("weather.forecast_horizon_hours must be in range 1..72.")

    try:
        refresh_interval_hours = int(raw.get("refresh_interval_hours", 3))
    except (TypeError, ValueError) as exc:
        raise AutomationRulesError("weather.refresh_interval_hours must be an integer.") from exc

    if refresh_interval_hours < 1 or refresh_interval_hours > 24:
        raise AutomationRulesError("weather.refresh_interval_hours must be in range 1..24.")

    try:
        comfort_margin_c = float(raw.get("comfort_margin_c", 1.0))
    except (TypeError, ValueError) as exc:
        raise AutomationRulesError("weather.comfort_margin_c must be a number.") from exc

    if comfort_margin_c < 0.0 or comfort_margin_c > 5.0:
        raise AutomationRulesError("weather.comfort_margin_c must be in range 0.0..5.0.")

    return WeatherPlanningConfig(
        enabled=bool(raw.get("enabled", True)),
        sensor_offset_c=sensor_offset_c,
        use_short_term_forecast=bool(raw.get("use_short_term_forecast", True)),
        provider=provider,
        chmi_region_code=chmi_region_code,
        chmi_location_label=chmi_location_label,
        chmi_meteogram_poi_id=chmi_meteogram_poi_id,
        chmi_meteogram_x=chmi_meteogram_x,
        chmi_meteogram_y=chmi_meteogram_y,
        forecast_horizon_hours=forecast_horizon_hours,
        refresh_interval_hours=refresh_interval_hours,
        comfort_margin_c=comfort_margin_c,
        prefer_aladin_model=bool(raw.get("prefer_aladin_model", True)),
        adjust_mode_by_forecast=bool(raw.get("adjust_mode_by_forecast", True)),
    )


def parse_automation_rules(raw: dict[str, Any]) -> AutomationRulesConfig:
    """Validate and normalize raw automation rules.

    Args:
        raw: Raw parsed JSON object.

    Returns:
        AutomationRulesConfig: Validated rules configuration.

    Raises:
        AutomationRulesError: If configuration is invalid.
    """

    if not isinstance(raw, dict):
        raise AutomationRulesError("Automation rules root must be a JSON object.")

    season_months = _parse_season_months(raw.get("season_months"))
    cooling_allowed_seasons = _parse_cooling_allowed_seasons(
        raw.get("cooling_allowed_seasons"),
        season_months,
    )

    fallback_raw = raw.get("cooling_block_fallback_mode")
    fallback_mode = str(fallback_raw).upper().strip() if fallback_raw else None
    if fallback_mode == "":
        fallback_mode = None

    return AutomationRulesConfig(
        season_months=season_months,
        cooling_allowed_seasons=cooling_allowed_seasons,
        cooling_block_fallback_mode=fallback_mode,
        manual_override_requires_resume_button=bool(
            raw.get("manual_override_requires_resume_button", True)
        ),
        strategy=str(raw.get("strategy", "comfort_with_energy_saving")),
        weather=_parse_weather_settings(raw.get("weather")),
    )


def _write_rules_payload(config_path: Path, payload: dict[str, Any]) -> None:
    """Write automation rules payload to disk.

    Args:
        config_path: Target JSON file path.
        payload: JSON-serializable configuration payload.
    """

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, ensure_ascii=False)


def load_automation_rules(config_path: Path) -> tuple[AutomationRulesConfig, str | None]:
    """Load automation rules with validation and safe fallback.

    Args:
        config_path: Path to automation rules JSON file.

    Returns:
        tuple[AutomationRulesConfig, str | None]:
            - validated rules configuration
            - optional warning string when fallback was used
    """

    warning_message: str | None = None

    if not config_path.exists():
        payload = default_automation_rules_payload()
        _write_rules_payload(config_path, payload)
        return parse_automation_rules(payload), None

    try:
        with open(config_path, "r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)
    except Exception as exc:
        payload = default_automation_rules_payload()
        warning_message = (
            f"Automation rules file could not be parsed ({exc}). Defaults were restored."
        )
        _write_rules_payload(config_path, payload)
        return parse_automation_rules(payload), warning_message

    try:
        return parse_automation_rules(payload), None
    except AutomationRulesError as exc:
        fallback_payload = default_automation_rules_payload()
        _write_rules_payload(config_path, fallback_payload)
        warning_message = (
            "Automation rules validation failed "
            f"({exc}). Defaults were restored."
        )
        return parse_automation_rules(fallback_payload), warning_message


def season_label_cz(season_code: str) -> str:
    """Return Czech label for season code.

    Args:
        season_code: Internal season code.

    Returns:
        str: Czech season label for UI/log output.
    """

    return SEASON_LABELS_CZ.get(season_code, season_code.lower())


def get_season_for_datetime(
    current_time: datetime,
    rules: AutomationRulesConfig,
) -> str:
    """Resolve active season for given timestamp.

    Args:
        current_time: Evaluated time.
        rules: Validated automation rules.

    Returns:
        str: Season code.
    """

    month = current_time.month
    for season_code, months in rules.season_months.items():
        if month in months:
            return season_code
    return "TRANSITION"


def resolve_scheduled_mode(
    requested_mode: str,
    current_time: datetime,
    rules: AutomationRulesConfig,
    available_modes: set[str] | None = None,
) -> ModeResolution:
    """Resolve scheduled mode according to season-aware automation rules.

    Args:
        requested_mode: Mode requested by schedule entry.
        current_time: Time for season evaluation.
        rules: Validated automation rules.
        available_modes: Optional set of modes supported by device profile.

    Returns:
        ModeResolution: Decision for mode execution.
    """

    normalized_mode = str(requested_mode or "").upper().strip()
    season_code = get_season_for_datetime(current_time, rules)
    season_text = season_label_cz(season_code)

    normalized_available: set[str] | None = None
    if available_modes is not None:
        normalized_available = {str(mode).upper().strip() for mode in available_modes}

    if not normalized_mode:
        return ModeResolution(
            allowed=False,
            requested_mode=normalized_mode,
            effective_mode=None,
            season=season_code,
            reason="Plan nema nastaveny rezim.",
            adjusted=False,
        )

    if normalized_available is not None and normalized_mode not in normalized_available:
        return ModeResolution(
            allowed=False,
            requested_mode=normalized_mode,
            effective_mode=None,
            season=season_code,
            reason=f"Rezim {normalized_mode} neni podporovan profilem zarizeni.",
            adjusted=False,
        )

    if normalized_mode == "COOL" and season_code not in rules.cooling_allowed_seasons:
        fallback_mode = rules.cooling_block_fallback_mode

        if fallback_mode:
            fallback_mode = fallback_mode.upper().strip()

            if normalized_available is not None and fallback_mode not in normalized_available:
                if "HEAT" in normalized_available:
                    fallback_mode = "HEAT"
                elif "FAN" in normalized_available:
                    fallback_mode = "FAN"
                else:
                    fallback_mode = None

        if fallback_mode:
            return ModeResolution(
                allowed=True,
                requested_mode=normalized_mode,
                effective_mode=fallback_mode,
                season=season_code,
                reason=(
                    f"V sezone {season_text} je COOL blokovan. "
                    f"Pouzivam fallback rezim {fallback_mode}."
                ),
                adjusted=True,
            )

        return ModeResolution(
            allowed=False,
            requested_mode=normalized_mode,
            effective_mode=None,
            season=season_code,
            reason=f"V sezone {season_text} je COOL blokovan a fallback neni dostupny.",
            adjusted=False,
        )

    return ModeResolution(
        allowed=True,
        requested_mode=normalized_mode,
        effective_mode=normalized_mode,
        season=season_code,
        reason=f"Rezim {normalized_mode} je v sezone {season_text} povolen.",
        adjusted=False,
    )


def build_automation_summary(
    rules: AutomationRulesConfig,
    current_time: datetime,
    manual_override_active: bool,
    last_note: str | None = None,
) -> str:
    """Build one-line human-readable automation summary.

    Args:
        rules: Validated automation rules.
        current_time: Time for season label.
        manual_override_active: Current manual override flag.
        last_note: Optional latest decision note.

    Returns:
        str: Summary text suitable for GUI label.
    """

    season_code = get_season_for_datetime(current_time, rules)
    season_name = season_label_cz(season_code)
    allowed = ", ".join(season_label_cz(item) for item in rules.cooling_allowed_seasons)
    override_text = "aktivni" if manual_override_active else "vypnuty"
    if rules.weather.enabled:
        weather_source = f"ČHMÚ region {rules.weather.chmi_region_code}"
        if rules.weather.provider == "CHMI_METEOGRAM":
            weather_source = (
                f"ČHMÚ Meteogram POI {rules.weather.chmi_meteogram_poi_id} "
                f"(fallback region {rules.weather.chmi_region_code})"
            )
            if rules.weather.chmi_meteogram_x is not None and rules.weather.chmi_meteogram_y is not None:
                weather_source = (
                    f"{weather_source}"
                    f" ({rules.weather.chmi_meteogram_x:.4f},{rules.weather.chmi_meteogram_y:.4f})"
                )

        weather_text = (
            f"Pocasi: {weather_source} "
            f"{rules.weather.forecast_horizon_hours}h "
            f"(refresh {rules.weather.refresh_interval_hours}h, "
            f"offset {rules.weather.sensor_offset_c:+.1f}C)"
        )
    else:
        weather_text = "Pocasi: vypnuto"

    base = (
        f"Sezona: {season_name} | COOL povolen: {allowed} | "
        f"Manual override: {override_text}\n"
        f"{weather_text}"
    )

    if last_note:
        return f"{base}\nPosledni rozhodnuti: {last_note}"
    return base
