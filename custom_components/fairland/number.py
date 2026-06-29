"""Number platform for Fairland integration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .api import FairlandApiClientCommunicationError, FairlandApiClientError
from .const import (
    DOMAIN,
    HEAT_PUMP_CATEGORY_CODE,
    LOGGER,
    SALT_MACHINE_CATEGORY_CODE,
    WATER_PUMP_CATEGORY_CODE,
)
from .entity import FairlandEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FairlandDataUpdateCoordinator
    from .data import FairlandConfigEntry

# Heat-pump writable parameters.
HEAT_PUMP_NUMBER_TYPES = {
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


# Water-pump writable parameters. The Inverflow Plus pump (and OEM rebadges
# like Madimack) drives a real motor, so default ranges are deliberately
# conservative. The dpProperty min/max/step override below means we always
# clamp to whatever the firmware reports.
WATER_PUMP_NUMBER_TYPES = {
    "111": {
        "name": "Speed Setpoint",
        "unit": PERCENTAGE,
        "icon": "mdi:speedometer",
        "min": 30,
        "max": 100,
        "step": 1,
        "mode": NumberMode.SLIDER,
    },
    "104": {
        "name": "Backwash Duration",
        "unit": UnitOfTime.MINUTES,
        "icon": "mdi:timer-sand",
        "min": 0,
        "max": 1440,
        "step": 1,
        "mode": NumberMode.BOX,
        "entity_category": EntityCategory.CONFIG,
    },
}

# Inverter salt chlorinator (saltMachine) writable setpoints (issue #80).
# min/max/step are overridden from each device's dpProperty below, so the
# defaults here are only fallbacks. pH (dp 110) arrives as an integer × 10,
# so it opts into dpProperty scaling (`scale_from_property`) to read and
# write in real pH units.
SALT_MACHINE_NUMBER_TYPES = {
    "110": {
        "name": "pH Setpoint",
        "unit": None,
        "icon": "mdi:ph",
        "device_class": NumberDeviceClass.PH,
        "min": 6.5,
        "max": 8.5,
        "step": 0.1,
        "mode": NumberMode.BOX,
        "scale_from_property": True,
    },
    "108": {
        "name": "ORP Setpoint",
        "unit": UnitOfElectricPotential.MILLIVOLT,
        "icon": "mdi:test-tube",
        "min": 200,
        "max": 850,
        "step": 10,
        "mode": NumberMode.SLIDER,
    },
    "125": {
        "name": "Target Chlorine Output",
        "unit": PERCENTAGE,
        "icon": "mdi:gauge",
        "min": 0,
        "max": 130,
        "step": 5,
        "mode": NumberMode.SLIDER,
    },
    "109": {
        "name": "Pool Volume",
        "unit": "m³",
        "icon": "mdi:pool",
        "min": 5,
        "max": 100,
        "step": 5,
        "mode": NumberMode.BOX,
        "entity_category": EntityCategory.CONFIG,
    },
    "126": {
        "name": "Acid Dosing Rate",
        "unit": "ml/day",
        "icon": "mdi:eyedropper",
        "min": 0,
        "max": 9990,
        "step": 10,
        "mode": NumberMode.BOX,
        "entity_category": EntityCategory.CONFIG,
    },
}


# Firmware-reported time units (dpProperty "unit") we trust to override a
# default time unit: the backwash duration comes in seconds on some pumps
# (e.g. InverFlow(L), issue #77) and minutes on others.
DP_PROPERTY_TIME_UNITS = {
    "s": UnitOfTime.SECONDS,
    "min": UnitOfTime.MINUTES,
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

    for device_info in devices:
        category = device_info.get("categoryCode")
        if category == HEAT_PUMP_CATEGORY_CODE:
            number_types = HEAT_PUMP_NUMBER_TYPES
        elif category == WATER_PUMP_CATEGORY_CODE:
            number_types = WATER_PUMP_NUMBER_TYPES
        elif category == SALT_MACHINE_CATEGORY_CODE:
            number_types = SALT_MACHINE_NUMBER_TYPES
        else:
            continue

        if "dps" not in device_info:
            continue

        dp_map = {item["dpId"]: item for item in device_info["dps"]}

        # Für jeden schreibbaren Parameter prüfen
        for dp_id, config in number_types.items():
            if dp_id not in dp_map:
                continue
            # Prüfen ob der Parameter schreibbar ist
            if dp_map[dp_id].get("dpMode") != "rw":
                continue

            # Werte spezifische Einstellungen aus dpProperty aus
            if "dpProperty" in dp_map[dp_id]:
                try:
                    prop = json.loads(dp_map[dp_id]["dpProperty"])
                    # Manche Werte kommen als Integer × 10^scale (z.B. der
                    # pH-Sollwert mit scale=1). dpProperty min/max/step liegen
                    # dann ebenfalls im rohen Raum, also alle herunterskalieren.
                    factor = 1.0
                    if config.get("scale_from_property") and int(prop.get("scale", 0)):
                        scale = int(prop["scale"])
                        factor = 10**scale
                        config = config.copy()
                        config["scale"] = scale
                    # Aktualisiere min/max/step basierend auf den tatsächlichen Geräteeigenschaften
                    if "min" in prop:
                        config = config.copy()
                        config["min"] = float(prop["min"]) / factor
                    if "max" in prop:
                        config = config.copy()
                        config["max"] = float(prop["max"]) / factor
                    if "step" in prop:
                        config = config.copy()
                        config["step"] = float(prop["step"]) / factor
                    # Zeit-Einheit aus der Firmware übernehmen: manche Pumpen
                    # melden die Backwash-Dauer in Sekunden statt Minuten (#77).
                    if (
                        config.get("unit") in (UnitOfTime.MINUTES, UnitOfTime.SECONDS)
                        and prop.get("unit") in DP_PROPERTY_TIME_UNITS
                    ):
                        config = config.copy()
                        config["unit"] = DP_PROPERTY_TIME_UNITS[prop["unit"]]
                except (json.JSONDecodeError, KeyError, ValueError) as ex:
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
        # Firmware reports/accepts the raw integer value × 10^scale (e.g. pH
        # as 74 for 7.4); 0 means the value is already in display units.
        self._scale = config.get("scale", 0)

        # Set attributes based on config
        self._attr_name = config["name"]
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_{dp_id}_control"
        self._attr_native_unit_of_measurement = config.get("unit")
        self._attr_icon = config.get("icon")
        self._attr_device_class = config.get("device_class")
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
                    value = self._effective_dp_value(self._dp_id, dp["dpValue"])
                    if self._scale > 0 and value is not None:
                        value = value / (10**self._scale)
                    self._attr_native_value = value
                    self._attr_available = True
                    return

            self._attr_available = False

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        try:
            # Scaled values (e.g. pH 7.4) go to the firmware as the raw
            # integer (74); unscaled values round to the step granularity.
            if self._scale > 0:
                raw_value = int(round(value * (10**self._scale)))
            elif self._attr_native_step.is_integer():
                raw_value = int(round(value))
            else:
                raw_value = round(value, 2)

            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                self._dp_id,
                raw_value,
            )

            # Optimistisch setzen; die Cloud meldet den neuen Wert erst nach
            # 2-4 s zurück, ein sofortiger Refresh würde den alten Wert lesen
            # und die UI zurückspringen lassen (#77). Pending-Vergleich läuft
            # über den rohen Wert, die Anzeige über den skalierten.
            self._note_pending_write(self._dp_id, raw_value)
            self._attr_native_value = (
                raw_value / (10**self._scale) if self._scale > 0 else raw_value
            )
            self.async_write_ha_state()
            self._schedule_write_refresh()
        except (FairlandApiClientCommunicationError, FairlandApiClientError) as ex:
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
