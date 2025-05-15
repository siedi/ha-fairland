"""Switch platform for Fairland integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.helpers.entity import DeviceInfo

from .api import FairlandApiClientCommunicationError, FairlandApiClientError
from .const import DOMAIN, LOGGER
from .entity import FairlandEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FairlandDataUpdateCoordinator
    from .data import FairlandConfigEntry

ENTITY_DESCRIPTIONS = (
    SwitchEntityDescription(
        key="Fairland",
        name="Power",
        icon="mdi:power",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FairlandConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fairland switch platform."""
    LOGGER.debug("Setting up Fairland switch platform")

    entities = []
    devices = entry.runtime_data.coordinator.data

    # Create switch entities for each device
    for device_info in devices:
        # Prüfe, ob es sich um eine Wärmepumpe handelt
        if device_info.get("categoryCode") == "heatPump":
            LOGGER.debug("Found heat pump device: %s", device_info["deviceName"])
            entities.append(
                FairlandSwitch(
                    coordinator=entry.runtime_data.coordinator,
                    device_info=device_info,
                    entity_description=ENTITY_DESCRIPTIONS,
                )
            )
    async_add_entities(entities, True)


class FairlandSwitch(FairlandEntity, SwitchEntity):
    """Representation of a Fairland switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FairlandDataUpdateCoordinator,
        device_info: dict[str, Any],
        entity_description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch class."""
        super().__init__(coordinator)
        LOGGER.debug("Switch device info: %s", self._attr_device_info)
        # self.entity_description = entity_description

        self._device_info = device_info
        self._device_id = device_info["id"]

        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_switch"
        self._attr_name = "Power"
        self._attr_icon = "mdi:power"
        self._is_on = False

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_info["deviceName"],
            manufacturer="Fairland",
            model=device_info.get("deviceName", "Unknown"),
            sw_version=device_info.get("version", "Unknown"),
        )

        # Initialize the state from device info
        self._update_state()

    def _update_state(self):
        """Update state from device data."""
        if "dps" in self._device_info:
            for dp in self._device_info["dps"]:
                if dp["dpId"] == "101":  # Power switch
                    self._is_on = dp["dpValue"]
                    self._attr_available = True
                    return

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        LOGGER.debug("Switch available: %s", self.coordinator.last_update_success)
        return self.coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Find our device in the coordinator data
        for device in self.coordinator.data:
            if device["id"] == self._device_id:
                self._device_info = device
                self._update_state()
                self.async_write_ha_state()
                break

    async def async_update(self) -> None:
        """Update the entity."""
        # The coordinator handles the updates
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        try:
            # await self.hass.async_add_executor_job(
            #    self._api.set_device_status,
            #    self._device_id,
            #    "101",  # Power switch data point
            #    True,
            # )
            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                "101",  # Power switch data point
                True,
            )
            self._is_on = True
            self.async_write_ha_state()

            # Request a refresh to get the updated state
            await self.coordinator.async_request_refresh()
        except (FairlandApiClientCommunicationError, FairlandApiClientError) as ex:
            LOGGER.error("Error turning on switch: %s", ex)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        try:
            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                "101",  # Power switch data point
                False,
            )
            self._is_on = False
            self.async_write_ha_state()

            # Request a refresh to get the updated state
            await self.coordinator.async_request_refresh()
        except (FairlandApiClientCommunicationError, FairlandApiClientError) as ex:
            LOGGER.error("Error turning off switch: %s", ex)
