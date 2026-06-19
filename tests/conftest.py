from __future__ import annotations

import pytest

PROVIDER_TEST_ENV = {
    "JAMBASE_LIVE_CALLS_ENABLED": "false",
    "CALENDAR_INGEST_JAMBASE_LIVE_CALLS_ENABLED": "false",
    "JAMBASE_API_KEY": "",
    "CALENDAR_INGEST_JAMBASE_API_KEY": "",
    "CITYSPARK_LIVE_CALLS_ENABLED": "false",
    "CALENDAR_INGEST_CITYSPARK_LIVE_CALLS_ENABLED": "false",
    "CITYSPARK_API_KEY": "",
    "CALENDAR_INGEST_CITYSPARK_API_KEY": "",
    "CITYSPARK_PORTAL_SCRIPT_ID": "",
    "CALENDAR_INGEST_CITYSPARK_PORTAL_SCRIPT_ID": "",
}


@pytest.fixture(autouse=True)
def isolate_live_provider_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from using locally exported live provider credentials."""

    for key, value in PROVIDER_TEST_ENV.items():
        monkeypatch.setenv(key, value)
