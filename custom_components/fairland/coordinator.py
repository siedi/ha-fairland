"""Data update coordinator for Fairland integration."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FairlandApiClientCommunicationError, FairlandApiClientError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import FairlandConfigEntry


from .const import DOMAIN, LOGGER


class FairlandDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Fairland data."""

    config_entry: FairlandConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: FairlandConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.device_ids = {}
        scan_interval = config_entry.data.get("scan_interval", 30)
        super().__init__(
            hass,
            logger=LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self):
        """Fetch data from API."""
        LOGGER.debug("Fetching data from Fairland API")
        LOGGER.debug(
            "Selected courtyard ID: %s", self.config_entry.data["courtyard_id"]
        )
        try:
            devices = await self.config_entry.runtime_data.client.get_all_devices_in_courtyard(
                self.config_entry.data["courtyard_id"]
            )
            # Get updated device data
            updated_devices = []

            for device in devices:
                try:
                    # Get updated device status
                    device_status = (
                        await self.config_entry.runtime_data.client.get_device_status(
                            device["id"],
                        )
                    )
                    # Update the device data
                    updated_device = device.copy()
                    updated_device["dps"] = device_status
                    updated_devices.append(updated_device)
                except (FairlandApiClientCommunicationError, FairlandApiClientError):
                    # Keep the old data
                    updated_devices.append(device)

        except (FairlandApiClientCommunicationError, FairlandApiClientError) as ex:
            raise UpdateFailed(f"Error updating data: {ex}") from ex
        else:
            return updated_devices
