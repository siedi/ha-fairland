"""Data update coordinator for Fairland integration."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FairlandApiClientCommunicationError, FairlandApiClientError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import FairlandConfigEntry


from .const import DOMAIN, LOGGER, SCAN_INTERVAL


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
        super().__init__(
            hass,
            logger=LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
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

    async def _update_device_registry(self, device):
        """Check for new devices and update existing ones."""
        device_registry = dr.async_get(self.hass)

        if device["id"] not in self.device_ids:
            # Neues Gerät gefunden - registrieren
            device = device_registry.async_get_or_create(
                config_entry_id=self.config_entry.entry_id,
                identifiers={(DOMAIN, device["id"])},
                name=device["deviceName"],
                manufacturer="Fairland",
                model=device.get("categoryCode", "Unknown"),
                sw_version=device.get("version", "Unknown"),
                serial_number=device.get("sn", "Unknown"),
            )
            self.device_ids[device["id"]] = device["id"]
        else:
            # Gerät existiert bereits - aktualisieren falls nötig
            device = device_registry.async_get_device({(DOMAIN, device["id"])})
            if device:
                # Prüfe, ob sich gerätespezifische Informationen geändert haben
                updated_values = {}

                if device.name != device.get("deviceName"):
                    updated_values["name"] = device.get("deviceName")

                if device.model != device.get("categoryCode"):
                    updated_values["model"] = device.get("categoryCode")

                if device.sw_version != device.get("version"):
                    updated_values["sw_version"] = device.get("version")

                # Wenn Aktualisierungen notwendig sind
                if updated_values:
                    device_registry.async_update_device(device["id"], **updated_values)
