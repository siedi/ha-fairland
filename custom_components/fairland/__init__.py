"""Custom integration to integrate Fairland with Home Assistant.

For more details about this integration, please refer to
https://github.com/siedi/ha-fairland
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration

# from . import climate, sensor, switch
from .api import (
    FairlandApiClient,
    FairlandApiClientCommunicationError,
    FairlandApiClientError,
)
from .const import LOGGER
from .coordinator import FairlandDataUpdateCoordinator
from .data import FairlandData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import FairlandConfigEntry


PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: FairlandConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    coordinator = FairlandDataUpdateCoordinator(
        hass=hass,
        config_entry=config_entry,
    )

    apiClient = FairlandApiClient(
        username=config_entry.data[CONF_USERNAME],
        password=config_entry.data[CONF_PASSWORD],
        session=async_get_clientsession(hass),
        country_code=config_entry.data.get("countryCode", "DE"),
    )

    config_entry.runtime_data = FairlandData(
        client=apiClient,
        integration=async_get_loaded_integration(hass, config_entry.domain),
        coordinator=coordinator,
    )

    # Login
    try:
        await apiClient.login()
    except (FairlandApiClientCommunicationError, FairlandApiClientError) as ex:
        LOGGER.exception("Failed to login: %s", ex)
        return False

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()

    # Set up the platforms for this integration
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    config_entry.async_on_unload(config_entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: FairlandConfigEntry
) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    config_entry: FairlandConfigEntry,
) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, config_entry)
    await async_setup_entry(hass, config_entry)
