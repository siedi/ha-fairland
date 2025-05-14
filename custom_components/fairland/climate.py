"""Climate platform for Fairland integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_WHOLE, UnitOfTemperature
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, LOGGER
from .entity import FairlandEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FairlandDataUpdateCoordinator
    from .data import FairlandConfigEntry

# Map Fairland HVAC modes to Home Assistant modes
HVAC_MODE_MAP = {
    0: HVACMode.AUTO,
    1: HVACMode.HEAT,
    2: HVACMode.COOL,
}

# Map Home Assistant modes to Fairland HVAC modes
HVAC_MODE_REVERSE_MAP = {
    HVACMode.AUTO: 0,
    HVACMode.HEAT: 1,
    HVACMode.COOL: 2,
    HVACMode.OFF: None,  # Handle separately when switching on/off
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FairlandConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fairland climate platform."""
    LOGGER.debug("Setting up Fairland climate platform")

    entities = []
    devices = entry.runtime_data.coordinator.data

    # Create climate entities for each device
    for device_info in devices:
        if device_info.get("categoryCode") == "heatPump":
            LOGGER.debug("Found heat pump device: %s", device_info["deviceName"])

            entities.append(
                FairlandClimate(
                    coordinator=entry.runtime_data.coordinator,
                    device_info=device_info,
                )
            )

    async_add_entities(entities, True)


class FairlandClimate(FairlandEntity, ClimateEntity):
    """Representation of a Fairland climate device."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_precision = PRECISION_WHOLE
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO]
    _attr_min_temp = 8
    _attr_max_temp = 40

    def __init__(
        self,
        coordinator: FairlandDataUpdateCoordinator,
        device_info: dict[str, Any],
    ) -> None:
        """Initialize the climate device."""

        super().__init__(coordinator)
        LOGGER.debug("Climate device info: %s", self._attr_device_info)

        self._device_info = device_info
        self._device_id = device_info["id"]
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}"
        self.coordinator = coordinator

        self._index_data = {}
        for dp in device_info["dps"]:
            self._index_data[dp["dpId"]] = dp

        # Setup preset modes dynamically if running mode is available
        self._preset_modes_map = {}
        self._preset_modes_reverse_map = {}
        self._setup_preset_modes()

        # Set preset_modes attribute based on available modes
        self._attr_preset_modes = (
            list(self._preset_modes_map.values()) if self._preset_modes_map else []
        )

        # Initialize preset mode
        self._attr_preset_mode = None

        # Setzen Sie die Standardwerte
        self._attr_current_temperature = None
        self._attr_target_temperature = None
        self._is_on = self._get_switch_state()
        self._attr_hvac_mode = self._get_current_mode()
        self._attr_hvac_action = HVACAction.IDLE

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_info["deviceName"],
            manufacturer="Fairland",
            model=device_info.get("deviceName", "Unknown"),
            sw_version=device_info.get("version", "Unknown"),
        )

    def _setup_preset_modes(self):
        """Set up preset modes from the device data."""
        running_mode_dp = self._index_data.get("102")
        if not running_mode_dp or "dpProperty" not in running_mode_dp:
            LOGGER.debug("No running mode data point found or dpProperty missing")
            return

        try:
            import json

            # Parse the dpProperty which contains the mode mapping
            mode_mapping = json.loads(running_mode_dp["dpProperty"])

            # Create the forward mapping (value -> name)
            for value, name in mode_mapping.items():
                self._preset_modes_map[int(value)] = name

            # Create the reverse mapping (name -> value)
            for value, name in mode_mapping.items():
                self._preset_modes_reverse_map[name] = int(value)

            LOGGER.debug(f"Set up preset modes: {self._preset_modes_map}")
        except Exception as ex:
            LOGGER.error(f"Error setting up preset modes: {ex}")

    def _get_switch_state(self):
        """Get the current switch state from the device data."""
        switch_dp = self._index_data.get("101")
        if switch_dp:
            return switch_dp["dpValue"]
        return False

    def _get_current_mode(self):
        """Get the current mode from the device data."""
        if not self._is_on:
            return HVACMode.OFF

        mode_dp = self._index_data.get("106")
        if mode_dp:
            mode_value = mode_dp["dpValue"]
            # Map zu Home Assistant-Modi
            return HVAC_MODE_MAP.get(mode_value, HVACMode.OFF)
        return HVACMode.OFF

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self) -> None:
        """Update entity state from the coordinator."""
        # Find our device in the coordinator data
        for device in self.coordinator.data:
            if device["id"] == self._device_id:
                # Aktualisiere device_info mit den neuesten Daten
                self._device_info = device
                device_status = device.get("dps", [])

                # Update our stored data based on the response
                for dp in device_status:
                    dp_id = dp["dpId"]
                    value = dp["dpValue"]

                    if dp_id == "101":  # Power switch
                        self._is_on = value
                        if not self._is_on:
                            self._attr_hvac_mode = HVACMode.OFF
                            self._attr_hvac_action = HVACAction.OFF

                    elif dp_id == "102":  # Running mode
                        mode_name = self._preset_modes_map.get(value)
                        if mode_name:
                            self._attr_preset_mode = mode_name

                    elif dp_id == "106":  # Operating mode
                        if self._is_on:
                            self._attr_hvac_mode = HVAC_MODE_MAP.get(
                                value, HVACMode.OFF
                            )

                    elif dp_id == "103":  # Current temperature
                        self._attr_current_temperature = value

                    elif dp_id == "107":  # Target temperature
                        self._attr_target_temperature = value

                    elif dp_id == "113":  # Operating status
                        # 0: standby, 1: operating
                        if value == 1 and self._is_on:
                            if self._attr_hvac_mode == HVACMode.HEAT:
                                self._attr_hvac_action = HVACAction.HEATING
                            elif self._attr_hvac_mode == HVACMode.COOL:
                                self._attr_hvac_action = HVACAction.COOLING
                            else:
                                self._attr_hvac_action = HVACAction.IDLE
                        else:
                            self._attr_hvac_action = HVACAction.IDLE

    async def async_set_preset_mode(self, preset_mode):
        """Set new preset mode."""
        try:
            mode_value = self._preset_modes_reverse_map.get(preset_mode)
            if mode_value is not None:
                await (
                    self.coordinator.config_entry.runtime_data.client.set_device_status(
                        self._device_id,
                        "102",  # Running mode data point
                        mode_value,
                    )
                )
                self._attr_preset_mode = preset_mode
            else:
                LOGGER.error(f"Unknown preset mode: {preset_mode}")
        except Exception as ex:
            LOGGER.error(f"Error setting preset mode: {ex}")

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        try:
            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                "103",  # Target temperature data point
                int(temperature),
            )
            self._attr_target_temperature = temperature
        except Exception as ex:
            LOGGER.error("Error setting temperature: %s", ex)

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return

        # If currently off, turn on first
        if not self._is_on:
            await self.async_turn_on()

        # Set the mode
        try:
            mode_value = HVAC_MODE_REVERSE_MAP.get(hvac_mode)
            if mode_value is not None:
                await (
                    self.coordinator.config_entry.runtime_data.client.set_device_status(
                        self._device_id,
                        "106",  # Operating mode data point
                        mode_value,
                    )
                )
                self._attr_hvac_mode = hvac_mode
        except Exception as ex:
            LOGGER.error("Error setting HVAC mode: %s", ex)

    async def async_turn_on(self):
        """Turn the entity on."""
        try:
            await self.coordinator.config_entry.runtime_data.client.set_device_statuss(
                self._device_id,
                "101",  # Power switch data point
                True,
            )
            self._is_on = True

            # Restore previous mode or set to AUTO
            last_mode = self._attr_hvac_mode
            if last_mode == HVACMode.OFF:
                self._attr_hvac_mode = HVACMode.AUTO
            else:
                self._attr_hvac_mode = last_mode
        except Exception as ex:
            LOGGER.error("Error turning on: %s", ex)

    async def async_turn_off(self):
        """Turn the entity off."""
        try:
            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                "101",  # Power switch data point
                False,
            )
            self._is_on = False
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_hvac_action = HVACAction.OFF
        except Exception as ex:
            LOGGER.error("Error turning off: %s", ex)
