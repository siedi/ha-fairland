"""Custom integration to integrate Fairland with Home Assistant.

For more details about this integration, please refer to
https://github.com/siedi/ha-fairland
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration

# from . import climate, sensor, switch
from .api import (
    FairlandApiClient,
    FairlandApiClientAuthenticationError,
    FairlandApiClientError,
)
from .const import CONF_API_REGION, DEFAULT_API_REGION, DOMAIN, LOGGER
from .coordinator import FairlandDataUpdateCoordinator
from .data import FairlandData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import FairlandConfigEntry


PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SELECT,
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
        region=config_entry.data.get(CONF_API_REGION, DEFAULT_API_REGION),
    )

    config_entry.runtime_data = FairlandData(
        client=apiClient,
        integration=async_get_loaded_integration(hass, config_entry.domain),
        coordinator=coordinator,
    )

    # Login. Entries created before the regional servers were known have no
    # stored region; if their account is rejected, detect the region once
    # and persist it.
    try:
        await apiClient.login()
    except FairlandApiClientAuthenticationError as ex:
        if CONF_API_REGION in config_entry.data:
            msg = "Login rejected, please re-authenticate"
            raise ConfigEntryAuthFailed(msg) from ex
        try:
            region = await apiClient.detect_region()
        except FairlandApiClientAuthenticationError as ex2:
            msg = "No regional server accepts these credentials"
            raise ConfigEntryAuthFailed(msg) from ex2
        except FairlandApiClientError as ex2:
            msg = f"Could not detect the account region: {ex2}"
            raise ConfigEntryNotReady(msg) from ex2
        LOGGER.info("Account found on regional server '%s', saving it", region)
        hass.config_entries.async_update_entry(
            config_entry,
            data={**config_entry.data, CONF_API_REGION: region},
        )
    except FairlandApiClientError as ex:
        # Includes communication errors
        msg = f"Could not log in to the Fairland cloud: {ex}"
        raise ConfigEntryNotReady(msg) from ex

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()

    # Set up the platforms for this integration
    # No update listener: the reauth flow reloads the entry itself and the
    # options flow is an OptionsFlowWithReload.
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: FairlandConfigEntry
) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: FairlandConfigEntry
) -> bool:
    """Migrate old entries.

    1.1 -> 1.2 adds the courtyard id as unique ID, 1.2 -> 1.3 moves the scan
    interval from data to options.
    """
    if config_entry.version > 1:
        # Created by a newer version of the integration, can't downgrade.
        return False

    if config_entry.version == 1 and config_entry.minor_version < 2:
        unique_id = config_entry.unique_id
        if unique_id is None:
            unique_id = str(config_entry.data["courtyard_id"])
            duplicate = next(
                (
                    other
                    for other in hass.config_entries.async_entries(DOMAIN)
                    if other.entry_id != config_entry.entry_id
                    and other.unique_id == unique_id
                ),
                None,
            )
            if duplicate is not None:
                LOGGER.warning(
                    "Config entry '%s' is a duplicate courtyard of '%s', "
                    "remove one of the entries",
                    config_entry.title,
                    duplicate.title,
                )
                unique_id = None
        if unique_id is None:
            hass.config_entries.async_update_entry(config_entry, minor_version=2)
        else:
            hass.config_entries.async_update_entry(
                config_entry, unique_id=unique_id, minor_version=2
            )
        LOGGER.debug(
            "Migrated config entry '%s' to 1.2 (unique_id=%s)",
            config_entry.title,
            unique_id,
        )

    if config_entry.version == 1 and config_entry.minor_version < 3:
        data = dict(config_entry.data)
        if "scan_interval" in data:
            options = {
                **config_entry.options,
                "scan_interval": data.pop("scan_interval"),
            }
            hass.config_entries.async_update_entry(
                config_entry, data=data, options=options, minor_version=3
            )
        else:
            hass.config_entries.async_update_entry(config_entry, minor_version=3)
        LOGGER.debug("Migrated config entry '%s' to 1.3", config_entry.title)

    return True
