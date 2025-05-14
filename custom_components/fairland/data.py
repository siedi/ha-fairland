"""Custom types for fairland."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import FairlandApiClient
    from .coordinator import FairlandDataUpdateCoordinator


type FairlandConfigEntry = ConfigEntry[FairlandData]


@dataclass
class FairlandData:
    """Data for the Fairland integration."""

    client: FairlandApiClient
    coordinator: FairlandDataUpdateCoordinator
    integration: Integration
