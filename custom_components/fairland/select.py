"""Select platform for Fairland integration.

Currently exposes the operating-mode enum on Fairland-platform water pumps
(dpId 103) as a writable select entity. The cloud accepts native ``int``
values: ``0`` = Manual Inverter, ``1`` = Backwash.

NOTE: selecting ``Backwash`` will start a real backwash cycle on the pump
for the duration configured by the ``Backwash Duration`` number entity
(dpId 104). Treat this as a deliberate user action.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import DeviceInfo

from .api import FairlandApiClientCommunicationError, FairlandApiClientError
from .const import DOMAIN, LOGGER, WATER_PUMP_CATEGORY_CODE
from .entity import FairlandEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FairlandDataUpdateCoordinator
    from .data import FairlandConfigEntry


WATER_PUMP_MODE_DP_ID = "103"
WATER_PUMP_MODE_TRANSLATION_KEY = "water_pump_mode"

# Server-side enum int → translation-key option name. Option names are
# lowercase snake_case to match the translation file convention.
WATER_PUMP_MODE_INT_TO_OPTION: dict[int, str] = {
    0: "manual_inverter",
    1: "backwash",
}
WATER_PUMP_MODE_OPTION_TO_INT: dict[str, int] = {
    v: k for k, v in WATER_PUMP_MODE_INT_TO_OPTION.items()
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FairlandConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fairland select platform."""
    LOGGER.debug("Setting up Fairland select platform")

    entities = []
    for device_info in entry.runtime_data.coordinator.data:
        if device_info.get("categoryCode") != WATER_PUMP_CATEGORY_CODE:
            continue
        if "dps" not in device_info:
            continue
        if not any(
            dp.get("dpId") == WATER_PUMP_MODE_DP_ID for dp in device_info["dps"]
        ):
            continue
        entities.append(
            FairlandWaterPumpModeSelect(
                coordinator=entry.runtime_data.coordinator,
                device_info=device_info,
            )
        )
    async_add_entities(entities, True)


class FairlandWaterPumpModeSelect(FairlandEntity, SelectEntity):
    """Operating mode select for Fairland-platform water pumps (dpId 103)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:tune"
    _attr_translation_key = WATER_PUMP_MODE_TRANSLATION_KEY

    def __init__(
        self,
        coordinator: FairlandDataUpdateCoordinator,
        device_info: dict[str, Any],
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)

        self._device_info = device_info
        self._device_id = device_info["id"]

        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_mode"
        self._attr_options = list(WATER_PUMP_MODE_INT_TO_OPTION.values())

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_info["deviceName"],
            manufacturer="Fairland",
            model=device_info.get("deviceName", "Unknown"),
            sw_version=device_info.get("version", "Unknown"),
        )

        self._update_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    def _update_state(self) -> None:
        """Update current option from device data."""
        if "dps" not in self._device_info:
            return
        for dp in self._device_info["dps"]:
            if dp["dpId"] == WATER_PUMP_MODE_DP_ID:
                raw = dp.get("dpValue")
                try:
                    self._attr_current_option = WATER_PUMP_MODE_INT_TO_OPTION.get(
                        int(raw)
                    )
                except (TypeError, ValueError):
                    self._attr_current_option = None
                self._attr_available = self._attr_current_option is not None
                return
        self._attr_available = False

    async def async_select_option(self, option: str) -> None:
        """Write a new mode to the pump."""
        if option not in WATER_PUMP_MODE_OPTION_TO_INT:
            LOGGER.error("Refusing to set unknown mode option: %r", option)
            return
        target_int = WATER_PUMP_MODE_OPTION_TO_INT[option]
        try:
            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                WATER_PUMP_MODE_DP_ID,
                target_int,
            )
            self._attr_current_option = option
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        except (FairlandApiClientCommunicationError, FairlandApiClientError) as ex:
            LOGGER.error("Error setting mode: %s", ex)

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        for device in self.coordinator.data:
            if device["id"] == self._device_id:
                self._device_info = device
                self._update_state()
                self.async_write_ha_state()
                break

    async def async_update(self) -> None:
        """Update the entity."""
        await self.coordinator.async_request_refresh()
