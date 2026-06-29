"""Sensor platform for Fairland integration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import (
    DOMAIN,
    HEAT_PUMP_CATEGORY_CODE,
    LOGGER,
    SALT_MACHINE_CATEGORY_CODE,
    SAND_CYLINDER_CATEGORY_CODE,
    WATER_PUMP_CATEGORY_CODE,
    WATER_PUMP_FLOW_UNIT_DP,
    WATER_PUMP_FLOW_UNITS,
)
from .entity import FairlandEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FairlandDataUpdateCoordinator
    from .data import FairlandConfigEntry


# Heat-pump sensor types. dpId namespace is *not* shared with water pumps:
# e.g. heat-pump dpId 108 = Lower Temperature Limit, water-pump dpId 108 =
# Backwash Countdown. Dispatch in async_setup_entry guards against the
# collision.
HEAT_PUMP_SENSOR_TYPES = {
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


# Firmware-reported time units (dpProperty "unit") we trust to override a
# default time unit: backwash duration/countdown come in seconds on some
# pumps (e.g. InverFlow(L), issue #77) and minutes on others.
DP_PROPERTY_TIME_UNITS = {
    "s": UnitOfTime.SECONDS,
    "min": UnitOfTime.MINUTES,
}


def _resolve_flow_unit(dp_map: dict[str, Any]) -> str | None:
    """Resolve a pool pump's flow unit from its dp 110 selection."""
    dp = dp_map.get(WATER_PUMP_FLOW_UNIT_DP)
    if dp is None:
        return None
    try:
        return WATER_PUMP_FLOW_UNITS.get(int(dp.get("dpValue")))
    except (TypeError, ValueError):
        return None


# Read-only data points exposed by Fairland-platform water pumps (e.g.
# Inverflow Plus and OEM-rebadged variants such as Madimack). Energy is
# reported as an integer with a dpProperty scale (typically scale=2), so it
# rides the same scaling path as heat-pump temperature/power values.
WATER_PUMP_SENSOR_TYPES = {
    "5": {
        "name": "Current Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # dpId 102 ("real-time running rate") is defined in the cloud schema for
    # every pump, but some firmwares never populate it (always null) while
    # others report live motor speed. Only created when the device actually
    # reports a value (see "require_value" handling in async_setup_entry).
    "102": {
        "name": "Running Rate",
        "unit": PERCENTAGE,
        "icon": "mdi:speedometer",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "require_value": True,
    },
    "108": {
        "name": "Backwash Countdown",
        "unit": UnitOfTime.MINUTES,
        "icon": "mdi:timer-sand",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "109": {
        "name": "Energy Consumption",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:lightning-bolt",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
    },
    # Flow values are expressed in the unit selected on dp 110, so they carry
    # no static unit; `flow_unit` resolves it live (see _present_value path).
    # The firmware's dpProperty unit field is a junk multi-unit string here.
    "112": {
        "name": "Water Flow",
        "unit": None,
        "icon": "mdi:waves-arrow-right",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "flow_unit": True,
    },
    "101": {
        "name": "Maximum Flow Setting",
        "unit": None,
        "icon": "mdi:arrow-collapse-up",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "flow_unit": True,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "107": {
        "name": "Minimum Flow Setting",
        "unit": None,
        "icon": "mdi:arrow-collapse-down",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "flow_unit": True,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
}


# Inverter salt chlorinator (saltMachine) read-only data points (issue #80).
# dpProperty is the source of truth for scale, so the scale-from-property
# path in async_setup_entry fills it in (pH and several electrical values
# arrive as integers × 10). Enum points (`is_enum`) map their integer value
# to the firmware-reported labels; the raw display point (128) is shown
# verbatim as text.
SALT_MACHINE_SENSOR_TYPES = {
    "101": {
        "name": "Salt Concentration",
        "unit": "ppm",
        "icon": "mdi:shaker-outline",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "112": {
        "name": "pH",
        "unit": None,
        "icon": "mdi:ph",
        "device_class": SensorDeviceClass.PH,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "111": {
        "name": "ORP",
        "unit": UnitOfElectricPotential.MILLIVOLT,
        "icon": "mdi:test-tube",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # dp 102 = pool water temperature (°C); dp 133 mirrors it in °F. dp 105 is
    # the controller's internal/housing temperature.
    "102": {
        "name": "Pool Water Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:pool-thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "133": {
        "name": "Pool Water Temperature (°F)",
        "unit": UnitOfTemperature.FAHRENHEIT,
        "icon": "mdi:pool-thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "105": {
        "name": "Controller Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "113": {
        "name": "Chlorine Output",
        "unit": PERCENTAGE,
        "icon": "mdi:gauge",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "124": {
        "name": "Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "106": {
        "name": "Voltage",
        "unit": UnitOfElectricPotential.VOLT,
        "icon": "mdi:sine-wave",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "130": {
        "name": "Current",
        "unit": UnitOfElectricCurrent.AMPERE,
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "145": {
        "name": "Runtime",
        "unit": UnitOfTime.HOURS,
        "icon": "mdi:timer-outline",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "119": {
        "name": "Water Quality",
        "unit": None,
        "icon": "mdi:water-check",
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "is_enum": True,
    },
    "127": {
        "name": "Active Profile",
        "unit": None,
        "icon": "mdi:cog-outline",
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "is_enum": True,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "128": {
        "name": "Display",
        "unit": None,
        "icon": "mdi:dock-window",
        "device_class": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
}


# Multiport valve / sand-filter controller (sandCylinder, #80/#81). Names are
# taken verbatim from the firmware's own nameLanguage (en-US). Pressures are
# reported in MPa; HA has no MPa pressure unit, so they ride as a plain unit
# string without a device_class. dp 107 carries English enum labels in its
# dpProperty, so it maps via the generic is_enum path.
SAND_CYLINDER_SENSOR_TYPES = {
    "101": {
        "name": "Water Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer-water",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "102": {
        "name": "Pressure",
        "unit": "MPa",
        "icon": "mdi:gauge",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "107": {
        "name": "Valve Position",
        "unit": None,
        "icon": "mdi:pipe-valve",
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "is_enum": True,
    },
    "115": {
        "name": "Timed Backwash Remaining",
        "unit": UnitOfTime.DAYS,
        "icon": "mdi:calendar-clock",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "116": {
        "name": "Rinse Countdown",
        "unit": UnitOfTime.SECONDS,
        "icon": "mdi:timer-sand",
        "device_class": SensorDeviceClass.DURATION,
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

    for device_info in devices:
        if "dps" not in device_info:
            continue

        category = device_info.get("categoryCode")
        if category == HEAT_PUMP_CATEGORY_CODE:
            sensor_types = HEAT_PUMP_SENSOR_TYPES
        elif category == WATER_PUMP_CATEGORY_CODE:
            sensor_types = WATER_PUMP_SENSOR_TYPES
        elif category == SALT_MACHINE_CATEGORY_CODE:
            sensor_types = SALT_MACHINE_SENSOR_TYPES
        elif category == SAND_CYLINDER_CATEGORY_CODE:
            sensor_types = SAND_CYLINDER_SENSOR_TYPES
        else:
            continue

        dp_map = {item["dpId"]: item for item in device_info["dps"]}

        # Für jeden Sensortyp prüfen, ob er verfügbar ist
        for dp_id, sensor_config in sensor_types.items():
            if dp_id not in dp_map:
                continue

            # Datenpunkte, die nur im Cloud-Schema existieren, aber von der
            # Firmware nie befüllt werden, gar nicht erst anlegen.
            if (
                sensor_config.get("require_value")
                and dp_map[dp_id].get("dpValue") is None
            ):
                LOGGER.debug("Skipping dp %s: firmware does not populate it", dp_id)
                continue

            # scale aus dpProperty übernehmen, falls vorhanden.
            # Firmware liefert Temperaturen teils als Integer × 10 (scale=1).
            if "dpProperty" in dp_map[dp_id]:
                try:
                    prop = json.loads(dp_map[dp_id]["dpProperty"])
                    if "scale" in prop:
                        sensor_config = sensor_config.copy()
                        sensor_config["scale"] = int(prop["scale"])
                    # Zeit-Einheit aus der Firmware übernehmen: manche Pumpen
                    # melden Backwash-Dauern in Sekunden statt Minuten (#77).
                    if (
                        sensor_config.get("unit")
                        in (UnitOfTime.MINUTES, UnitOfTime.SECONDS)
                        and prop.get("unit") in DP_PROPERTY_TIME_UNITS
                    ):
                        sensor_config = sensor_config.copy()
                        sensor_config["unit"] = DP_PROPERTY_TIME_UNITS[prop["unit"]]
                    # Enum-Sensoren: die Firmware liefert die Wert→Label-Map
                    # direkt in dpProperty (z.B. {"0": "WAIT", "1": "GOOD"}).
                    if sensor_config.get("is_enum"):
                        enum_map = {
                            str(k): str(v)
                            for k, v in prop.items()
                            if str(k).lstrip("-").isdigit()
                        }
                        if enum_map:
                            sensor_config = sensor_config.copy()
                            sensor_config["enum_map"] = enum_map
                            sensor_config["options"] = list(enum_map.values())
                except (json.JSONDecodeError, KeyError, ValueError) as ex:
                    LOGGER.warning(
                        "Failed to parse dpProperty for dp %s: %s", dp_id, ex
                    )

            entities.append(
                FairlandSensor(
                    coordinator=entry.runtime_data.coordinator,
                    device_info=device_info,
                    dp_id=dp_id,
                    sensor_config=sensor_config,
                )
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
        # Enum sensors map the raw integer value to a firmware label
        # ({"0": "WAIT", ...}); when set, scaling is skipped.
        self._enum_map = sensor_config.get("enum_map")
        # Flow sensors take their unit from dp 110 (m³/h, L/min, ...).
        self._flow_unit = sensor_config.get("flow_unit", False)

        # Set attributes based on sensor_config
        self._attr_name = sensor_config["name"]
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_{dp_id}"
        self._attr_native_unit_of_measurement = sensor_config.get("unit")
        self._attr_icon = sensor_config.get("icon")
        self._attr_device_class = sensor_config.get("device_class")
        self._attr_state_class = sensor_config.get("state_class")
        self._attr_entity_category = sensor_config.get("entity_category")
        if "options" in sensor_config:
            self._attr_options = sensor_config["options"]

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

    def _present_value(self, value: Any) -> Any:
        """Map a raw dpValue to its presented value (enum label or scaled)."""
        if value is None:
            return None
        if self._enum_map is not None:
            return self._enum_map.get(str(value), value)
        if self._scale > 0:
            return value / (10**self._scale)
        return value

    def _update_state(self):
        """Update state from device data."""
        if "dps" in self._device_info:
            # Erstelle ein Dictionary mit dpId als Schlüssel für einfachen Zugriff
            dp_map = {item["dpId"]: item for item in self._device_info["dps"]}

            if self._dp_id in dp_map:
                self._attr_native_value = self._present_value(
                    dp_map[self._dp_id]["dpValue"]
                )
                if self._flow_unit:
                    self._attr_native_unit_of_measurement = _resolve_flow_unit(dp_map)
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
