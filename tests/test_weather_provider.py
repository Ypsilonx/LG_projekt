import asyncio
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from weather_provider import WeatherForecastInterval, WeatherForecastSnapshot, estimate_current_outdoor_temperature
from web.routes.weather import _fetch_weather_data, _resolve_current_temperature


class WeatherProviderTests(unittest.TestCase):
    def test_estimate_uses_explicit_current_temperature_when_present(self) -> None:
        snapshot = WeatherForecastSnapshot(
            fetched_at_utc=datetime.now(timezone.utc),
            reference_time_utc=datetime.now(timezone.utc),
            provider="TEST",
            region_code="TEST",
            location_label="Test",
            intervals=(
                WeatherForecastInterval(
                    start_time_utc=datetime.now(timezone.utc),
                    end_time_utc=datetime.now(timezone.utc) + timedelta(hours=1),
                    min_temp_c=8.0,
                    max_temp_c=10.0,
                    stream_id="test",
                    headline=None,
                ),
            ),
            source_files=("test",),
            current_temperature_c=12.5,
            current_temperature_source="external",
        )

        self.assertEqual(estimate_current_outdoor_temperature(snapshot, datetime.now()), 12.5)

    def test_external_temperature_source_is_used_before_forecast_fallback(self) -> None:
        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload
                self.headers = {"Content-Type": "application/json"}

            def raise_for_status(self) -> None:
                return None

            async def json(self, content_type=None):
                return self._payload

            async def text(self):
                return ""

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

        class FakeSession:
            def __init__(self, *args, **kwargs):
                self.calls = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return FakeResponse({"temperature_c": 11.3})

        async def run_test() -> tuple[float | None, str]:
            return await _resolve_current_temperature(
                {"current_temperature_url": "https://example.test/weather"},
                [{"temp_c": 5.0}],
                session=FakeSession(),
            )

        value, source = asyncio.run(run_test())
        self.assertEqual(value, 11.3)
        self.assertEqual(source, "external")

    def test_fetch_weather_data_keeps_outdoor_forecast_raw(self) -> None:
        future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self) -> None:
                return None

            async def json(self, content_type=None):
                return self._payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

        class FakeSession:
            def __init__(self, payload, *args, **kwargs):
                self._payload = payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            def get(self, url, **kwargs):
                return FakeResponse(self._payload)

        async def run_test() -> dict:
            payload = {
                "data": [
                    {
                        "validityTime": future_time,
                        "t2m": 17.4,
                    }
                ]
            }
            with patch(
                "web.routes.weather.aiohttp.ClientSession",
                return_value=FakeSession(payload),
            ):
                return await _fetch_weather_data(
                    {
                        "enabled": True,
                        "chmi_meteogram_poi_id": "510",
                        "forecast_horizon_hours": 24,
                        "ac_indoor_temperature_proxy_offset_c": -2.0,
                    }
                )

        result = asyncio.run(run_test())

        self.assertEqual(result["hourly"][0]["temp_c"], 17.4)
        self.assertEqual(result["hourly"][0]["temp_raw_c"], 17.4)
        self.assertEqual(result["ac_indoor_temperature_proxy_offset_c"], -2.0)


if __name__ == "__main__":
    unittest.main()
