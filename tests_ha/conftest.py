"""Fixtures for the real-Home-Assistant tests (see requirements-test-ha.txt).

Kept apart from tests/, whose conftest stubs homeassistant.* in sys.modules.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

import pytest

# Make custom_components/ importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from custom_components.fairland.api import (  # noqa: E402
    FairlandApiClientAuthenticationError,
    FairlandApiClientCommunicationError,
    FairlandApiClientError,
)

__all__ = [
    "FairlandApiClientAuthenticationError",
    "FairlandApiClientCommunicationError",
    "FairlandApiClientError",
]

CLIENT = "custom_components.fairland.config_flow.FairlandApiClient"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let HA load custom_components/fairland."""


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip the real setup so no platform or network code runs."""
    with patch(
        "custom_components.fairland.async_setup_entry", return_value=True
    ) as mock:
        yield mock


@pytest.fixture
def api() -> Generator[dict[str, AsyncMock]]:
    """Patch the API client methods used by the config flow."""
    with (
        patch(f"{CLIENT}.detect_region", return_value="eu") as detect_region,
        patch(f"{CLIENT}.login", return_value=None) as login,
        patch(
            f"{CLIENT}.get_courtyards",
            return_value=[{"id": 111, "name": "Garden"}],
        ) as get_courtyards,
        patch(
            f"{CLIENT}.get_all_devices_in_courtyard",
            return_value=[{"id": "dev1", "deviceName": "Pump"}],
        ) as get_devices,
        patch(
            f"{CLIENT}.get_device_status", return_value=[{"dpId": 101}]
        ) as get_status,
    ):
        yield {
            "detect_region": detect_region,
            "login": login,
            "get_courtyards": get_courtyards,
            "get_devices": get_devices,
            "get_status": get_status,
        }
