"""Sensor platform for Fairland integration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTemperature
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN, LOGGER
from .entity import FairlandEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FairlandDataUpdateCoordinator
    from .data import FairlandConfigEntry


# Define sensor types with the new detailed data points
SENSOR_TYPES = {
    # Temperaturen
    "103": {
        "name": "Inlet Water Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer-water",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "129": {
        "name": "Outlet Water Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer-water",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "130": {
        "name": "Ambient Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "131": {
        "name": "Exhaust Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer-high",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "132": {
        "name": "Outer Coil Pipe Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:pipe",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "133": {
        "name": "Gas Return Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:gas-cylinder",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "134": {
        "name": "Inner Coil Pipe Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:pipe",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "135": {
        "name": "Cooling Plate Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:coolant-temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # Leistung und Performance
    "105": {
        "name": "Running Percentage",
        "unit": PERCENTAGE,
        "icon": "mdi:percent",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "112": {
        "name": "Power",
        "unit": UnitOfPower.KILO_WATT,
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "scale": 3,  # Teile durch 1000 für kW
    },
    "137": {
        "name": "DC Fan Speed",
        "unit": "r/min",
        "icon": "mdi:fan",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "136": {
        "name": "Electronic Expansion Valve Opening",
        "unit": None,
        "icon": "mdi:valve",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # Additional debugging sensors
    "108": {
        "name": "Lower Temperature Limit",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer-low",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "109": {
        "name": "Upper Temperature Limit",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer-high",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "113": {
        "name": "Power Display Status",
        "unit": None,
        "icon": "mdi:power-settings",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "114": {
        "name": "Refrigeration Function",
        "unit": None,
        "icon": "mdi:snowflake",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "115": {
        "name": "Overclocking Function",
        "unit": None,
        "icon": "mdi:speedometer",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "116": {
        "name": "Water Pump Running Mode",
        "unit": None,
        "icon": "mdi:water-pump",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "117": {
        "name": "Water Pump Running Time",
        "unit": "min",
        "icon": "mdi:timer",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "118": {
        "name": "Defrosting Interval",
        "unit": "min",
        "icon": "mdi:snowflake-melt",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "119": {
        "name": "Defrosting Start Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer-low",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "120": {
        "name": "Defrosting Running Time",
        "unit": "min",
        "icon": "mdi:timer",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "121": {
        "name": "Defrosting Quit Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "122": {
        "name": "Compressor Speed Control",
        "unit": None,
        "icon": "mdi:engine",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "123": {
        "name": "EEV Superheat Heating",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:valve",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "124": {
        "name": "EEV Superheat Cooling",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:valve",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "125": {
        "name": "EEV Control Mode",
        "unit": None,
        "icon": "mdi:valve",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "126": {
        "name": "EEV Manual Opening Heating",
        "unit": None,
        "icon": "mdi:valve",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "127": {
        "name": "EEV Manual Opening Cooling",
        "unit": None,
        "icon": "mdi:valve",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "128": {
        "name": "Power-off Memory Function",
        "unit": None,
        "icon": "mdi:memory",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FairlandConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fairland sensors."""
    LOGGER.debug("Setting up Fairland sensors")

    entities = []
    devices = entry.runtime_data.coordinator.data

    entities = []
    devices = entry.runtime_data.coordinator.data

    # Create climate entities for each device
    for device_info in devices:
        if "dps" in device_info:
            dp_map = {item["dpId"]: item for item in device_info["dps"]}

            # Für jeden Sensortyp prüfen, ob er verfügbar ist
            for dp_id, sensor_config in SENSOR_TYPES.items():
                if dp_id in dp_map:
                    # Werte spezifische Einstellungen aus dpProperty aus
                    if dp_id == "112" and "dpProperty" in dp_map[dp_id]:
                        try:
                            prop = json.loads(dp_map[dp_id]["dpProperty"])
                            if "scale" in prop:
                                sensor_config = sensor_config.copy()
                                sensor_config["scale"] = int(prop["scale"])
                        except (json.JSONDecodeError, KeyError, ValueError) as ex:
                            LOGGER.warning(
                                "Failed to parse dpProperty for power sensor: %s", ex
                            )

                    entities.append(
                        FairlandSensor(
                            coordinator=entry.runtime_data.coordinator,
                            device_info=device_info,
                            dp_id=dp_id,
                            sensor_config=sensor_config,
                        )
                        # dp_id,
                        # sensor_config,
                    )

    async_add_entities(entities, True)


class FairlandSensor(FairlandEntity, SensorEntity):
    """Representation of a Fairland sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FairlandDataUpdateCoordinator,
        device_info: dict[str, Any],
        dp_id: str,
        sensor_config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""

        super().__init__(coordinator)
        LOGGER.debug("Sensor device info: %s", self._attr_device_info)

        self._device_info = device_info
        self._device_id = device_info["id"]
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}"
        self.coordinator = coordinator

        self._dp_id = dp_id
        self._sensor_config = sensor_config
        self._scale = sensor_config.get("scale", 0)

        # Set attributes based on sensor_config
        self._attr_name = sensor_config["name"]
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_{dp_id}"
        self._attr_native_unit_of_measurement = sensor_config.get("unit")
        self._attr_icon = sensor_config.get("icon")
        self._attr_device_class = sensor_config.get("device_class")
        self._attr_state_class = sensor_config.get("state_class")
        self._attr_entity_category = sensor_config.get("entity_category")

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_info["deviceName"],
            manufacturer="Fairland",
            model=device_info.get("deviceName", "Unknown"),
            sw_version=device_info.get("version", "Unknown"),
        )

        # Initialize the value
        self._update_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "dp_id": self._dp_id,
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    def _update_state(self):
        """Update state from device data."""
        if "dps" in self._device_info:
            # Erstelle ein Dictionary mit dpId als Schlüssel für einfachen Zugriff
            dp_map = {item["dpId"]: item for item in self._device_info["dps"]}

            if self._dp_id in dp_map:
                value = dp_map[self._dp_id]["dpValue"]

                # Skalierung anwenden (z.B. für Leistung)
                if self._scale > 0 and value is not None:
                    value = value / (10**self._scale)

                self._attr_native_value = value
                self._attr_available = True
                return

            for dp in self._device_info["dps"]:
                if dp["dpId"] == self._dp_id:
                    value = dp["dpValue"]

                    # Skalierung anwenden
                    if self._scale > 0 and value is not None:
                        value = value / (10**self._scale)

                    self._attr_native_value = value
                    self._attr_available = True
                    return

            # Wenn wir den Datenpunkt nicht gefunden haben
            LOGGER.warning(
                "Data point %s not found in device status for device %s",
                self._dp_id,
                self._device_id,
            )
            self._attr_available = False

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
