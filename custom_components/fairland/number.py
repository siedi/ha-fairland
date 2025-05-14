"""Number platform for Fairland integration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN, LOGGER
from .entity import FairlandEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FairlandDataUpdateCoordinator
    from .data import FairlandConfigEntry

# Define writable parameters
NUMBER_TYPES = {
    "116": {
        "name": "Set Water Pump Mode",
        "unit": None,
        "icon": "mdi:water-pump",
        "min": 0,
        "max": 2,
        "step": 1,
        "mode": NumberMode.SLIDER,
        "entity_category": EntityCategory.CONFIG,
    },
    "117": {
        "name": "Set Water Pump Time",
        "unit": "min",
        "icon": "mdi:timer",
        "min": 10,
        "max": 120,
        "step": 5,
        "mode": NumberMode.SLIDER,
        "entity_category": EntityCategory.CONFIG,
    },
    "118": {
        "name": "Set Defrosting Interval",
        "unit": "min",
        "icon": "mdi:snowflake-melt",
        "min": 30,
        "max": 90,
        "step": 1,
        "mode": NumberMode.BOX,
        "entity_category": EntityCategory.CONFIG,
    },
    "119": {
        "name": "Set Defrosting Start Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer-low",
        "min": -30,
        "max": 250,
        "step": 1,
        "mode": NumberMode.BOX,
        "entity_category": EntityCategory.CONFIG,
    },
    "120": {
        "name": "Set Defrosting Running Time",
        "unit": "min",
        "icon": "mdi:timer",
        "min": 1,
        "max": 12,
        "step": 1,
        "mode": NumberMode.BOX,
        "entity_category": EntityCategory.CONFIG,
    },
    "121": {
        "name": "Set Defrosting Quit Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
        "min": 8,
        "max": 100,
        "step": 1,
        "mode": NumberMode.BOX,
        "entity_category": EntityCategory.CONFIG,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FairlandConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fairland number controls."""
    LOGGER.debug("Setting up Fairland number controls")

    entities = []
    devices = entry.runtime_data.coordinator.data

    # Create number entities for each writable parameter
    for device_info in devices:
        if device_info.get("categoryCode") == "heatPump":
            if "dps" in device_info:
                dp_map = {item["dpId"]: item for item in device_info["dps"]}

                # Für jeden schreibbaren Parameter prüfen
                for dp_id, config in NUMBER_TYPES.items():
                    if dp_id in dp_map:
                        # Prüfen ob der Parameter schreibbar ist
                        if dp_map[dp_id].get("dpMode") == "rw":
                            # Werte spezifische Einstellungen aus dpProperty aus
                            if "dpProperty" in dp_map[dp_id]:
                                try:
                                    prop = json.loads(dp_map[dp_id]["dpProperty"])
                                    # Aktualisiere min/max/step basierend auf den tatsächlichen Geräteeigenschaften
                                    if "min" in prop:
                                        config = config.copy()
                                        config["min"] = float(prop["min"])
                                    if "max" in prop:
                                        config = config.copy()
                                        config["max"] = float(prop["max"])
                                    if "step" in prop:
                                        config = config.copy()
                                        config["step"] = float(prop["step"])
                                except Exception as ex:
                                    LOGGER.warning(
                                        "Failed to parse dpProperty for number entity: %s",
                                        ex,
                                    )

                            entities.append(
                                FairlandNumber(
                                    coordinator=entry.runtime_data.coordinator,
                                    device_info=device_info,
                                    dp_id=dp_id,
                                    config=config,
                                )
                            )

    async_add_entities(entities, True)


class FairlandNumber(FairlandEntity, NumberEntity):
    """Representation of a configurable Fairland parameter."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FairlandDataUpdateCoordinator,
        device_info: dict[str, Any],
        dp_id: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)

        self._device_info = device_info
        self._device_id = device_info["id"]
        self._dp_id = dp_id
        self._config = config

        # Set attributes based on config
        self._attr_name = config["name"]
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_{dp_id}_control"
        self._attr_native_unit_of_measurement = config.get("unit")
        self._attr_icon = config.get("icon")
        self._attr_entity_category = config.get("entity_category")
        self._attr_native_min_value = config["min"]
        self._attr_native_max_value = config["max"]
        self._attr_native_step = config["step"]
        self._attr_mode = config["mode"]

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_info["deviceName"],
            manufacturer="Fairland",
            model=device_info.get("deviceName", "Unknown"),
            sw_version=device_info.get("version", "Unknown"),
        )

        # Initialize current value
        self._update_value()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    def _update_value(self):
        """Update value from device data."""
        if "dps" in self._device_info:
            for dp in self._device_info["dps"]:
                if dp["dpId"] == self._dp_id:
                    self._attr_native_value = dp["dpValue"]
                    self._attr_available = True
                    return

            self._attr_available = False

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        try:
            # Runde den Wert basierend auf dem Step
            if self._attr_native_step.is_integer():
                rounded_value = int(round(value))
            else:
                rounded_value = round(value, 2)

            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                self._dp_id,
                rounded_value,
            )

            self._attr_native_value = rounded_value
            self.async_write_ha_state()

            # Aktualisiere, um den neuen Zustand zu erhalten
            await self.coordinator.async_request_refresh()
        except Exception as ex:
            LOGGER.error("Error setting value: %s", ex)

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
                self._update_value()
                self.async_write_ha_state()
                break

    async def async_update(self) -> None:
        """Update the entity."""
        # The coordinator handles the updates
        await self.coordinator.async_request_refresh()
