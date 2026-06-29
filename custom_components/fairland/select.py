"""Select platform for Fairland integration.

Currently exposes the operating-mode enum on Fairland-platform water pumps
(dpId 103) as a writable select entity. The available modes differ per
firmware (e.g. 2-mode pumps report ``{"0": "MI", "1": "backwash"}`` while
3-mode pumps report ``{"0": "AI", "1": "MI", "2": "backwash"}``), so the
int-to-option mapping is parsed from the ``dpProperty`` the device itself
reports instead of being hardcoded (see issue #77).

NOTE: selecting ``Backwash`` will start a real backwash cycle on the pump
for the duration configured by the ``Backwash Duration`` number entity
(dpId 104). Treat this as a deliberate user action.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.util import slugify

from .api import FairlandApiClientCommunicationError, FairlandApiClientError
from .const import (
    DOMAIN,
    LOGGER,
    SALT_MACHINE_CATEGORY_CODE,
    SAND_CYLINDER_CATEGORY_CODE,
    WATER_PUMP_CATEGORY_CODE,
)
from .entity import FairlandEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FairlandDataUpdateCoordinator
    from .data import FairlandConfigEntry


WATER_PUMP_MODE_DP_ID = "103"
WATER_PUMP_MODE_TRANSLATION_KEY = "water_pump_mode"

# Pool-pump flow-unit selector (dp 110). Drives the unit shown by the flow
# sensors and the flow setpoint. Maps by integer key.
WATER_PUMP_FLOW_UNIT_DP_ID = "110"
WATER_PUMP_FLOW_UNIT_SELECT: dict[str, Any] = {
    "translation_key": "water_pump_flow_unit",
    "icon": "mdi:cup-water",
    "entity_category": EntityCategory.CONFIG,
    "int_to_option": {0: "m3h", 1: "l_min", 2: "us_gpm", 3: "imp_gpm"},
}

# Known firmware enum labels → translation-key option names. Option names
# are lowercase snake_case to match the translation file convention.
# Labels not listed here fall through to ``slugify(label)`` and are shown
# untranslated, so new firmware variants still produce a working entity.
WATER_PUMP_MODE_LABEL_TO_OPTION: dict[str, str] = {
    "AI": "auto_inverter",
    "MI": "manual_inverter",
    "backwash": "backwash",
}

# Used when a device reports no parseable dpProperty for dpId 103. Matches
# the 2-mode firmware the platform was originally developed against (#72).
WATER_PUMP_MODE_FALLBACK_INT_TO_OPTION: dict[int, str] = {
    0: "manual_inverter",
    1: "backwash",
}


# Inverter salt chlorinator (saltMachine) enum controls (issue #80). The
# int → option map is parsed from each dp's dpProperty; `label_to_option`
# gives firmware labels a translated option name, anything else falls through
# to slugify so unknown firmware variants still produce a working entity.
SALT_MACHINE_SELECT_TYPES: dict[str, dict[str, Any]] = {
    "132": {
        "translation_key": "salt_machine_mode",
        "icon": "mdi:tune",
        "label_to_option": {
            "inverter": "inverter",
            "auto_ph": "auto_ph",
            "manual": "manual",
        },
    },
    "122": {
        "translation_key": "salt_polarity_reversal",
        "icon": "mdi:swap-horizontal-bold",
        "label_to_option": {
            "2": "2_hours",
            "4": "4_hours",
            "6": "6_hours",
        },
    },
}


# Multiport valve / sand-filter controller (sandCylinder, #80/#81) enum
# controls. Their dpProperty labels are localized (Chinese on this firmware),
# so they map by the integer key via `int_to_option` rather than by label.
# Option names taken from the firmware's own en-US propNameLanguage.
SAND_CYLINDER_SELECT_TYPES: dict[str, dict[str, Any]] = {
    "106": {
        "translation_key": "sand_cylinder_mode",
        "icon": "mdi:valve",
        "int_to_option": {
            0: "no_movement",
            1: "one_touch_rinse",
            2: "recirc",
            3: "closed",
            4: "filter",
            5: "waste",
        },
    },
    "125": {
        "translation_key": "sand_cylinder_pump_control",
        "icon": "mdi:water-pump",
        "int_to_option": {0: "none", 1: "pump_on", 2: "pump_off"},
    },
    "118": {
        "translation_key": "sand_cylinder_pressure_unit",
        "icon": "mdi:gauge",
        "entity_category": EntityCategory.CONFIG,
        "int_to_option": {0: "mpa", 1: "kpa", 2: "psi", 3: "bar"},
    },
    "123": {
        "translation_key": "sand_cylinder_temp_detection",
        "icon": "mdi:thermometer",
        "entity_category": EntityCategory.CONFIG,
        "int_to_option": {0: "off", 1: "celsius", 2: "fahrenheit"},
    },
}


def _enum_int_keys(dp: dict[str, Any]) -> set[int]:
    """Return the set of integer enum keys advertised in a dp's dpProperty."""
    try:
        prop = json.loads(dp.get("dpProperty") or "")
    except (TypeError, ValueError):
        return set()
    if not isinstance(prop, dict):
        return set()
    keys: set[int] = set()
    for raw_value in prop:
        try:
            keys.add(int(raw_value))
        except (TypeError, ValueError):
            continue
    return keys


def _parse_enum_options(
    dp: dict[str, Any], label_to_option: dict[str, str]
) -> dict[int, str]:
    """Build an enum int → option-name map from a dp's dpProperty."""
    try:
        prop = json.loads(dp.get("dpProperty") or "")
    except (TypeError, ValueError):
        prop = None
    if not isinstance(prop, dict):
        return {}

    options: dict[int, str] = {}
    for raw_value, label in prop.items():
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        options[value] = label_to_option.get(str(label), slugify(str(label)))
    return options


def _parse_mode_options(dp: dict[str, Any]) -> dict[int, str]:
    """Build the enum int → option-name map from the dp's dpProperty."""
    try:
        prop = json.loads(dp.get("dpProperty") or "")
    except (TypeError, ValueError):
        prop = None
    if not isinstance(prop, dict):
        LOGGER.debug(
            "No parseable dpProperty for mode dp, using fallback options: %r",
            dp.get("dpProperty"),
        )
        return dict(WATER_PUMP_MODE_FALLBACK_INT_TO_OPTION)

    options: dict[int, str] = {}
    for raw_value, label in prop.items():
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        options[value] = WATER_PUMP_MODE_LABEL_TO_OPTION.get(
            str(label), slugify(str(label))
        )
    return options or dict(WATER_PUMP_MODE_FALLBACK_INT_TO_OPTION)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FairlandConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fairland select platform."""
    LOGGER.debug("Setting up Fairland select platform")

    entities = []
    for device_info in entry.runtime_data.coordinator.data:
        if "dps" not in device_info:
            continue
        category = device_info.get("categoryCode")

        if category == WATER_PUMP_CATEGORY_CODE:
            dp_ids = {dp.get("dpId") for dp in device_info["dps"]}
            if WATER_PUMP_MODE_DP_ID in dp_ids:
                entities.append(
                    FairlandWaterPumpModeSelect(
                        coordinator=entry.runtime_data.coordinator,
                        device_info=device_info,
                    )
                )
            if WATER_PUMP_FLOW_UNIT_DP_ID in dp_ids:
                entities.append(
                    FairlandDpSelect(
                        coordinator=entry.runtime_data.coordinator,
                        device_info=device_info,
                        dp_id=WATER_PUMP_FLOW_UNIT_DP_ID,
                        config=WATER_PUMP_FLOW_UNIT_SELECT,
                    )
                )
        elif category in (SALT_MACHINE_CATEGORY_CODE, SAND_CYLINDER_CATEGORY_CODE):
            select_types = (
                SALT_MACHINE_SELECT_TYPES
                if category == SALT_MACHINE_CATEGORY_CODE
                else SAND_CYLINDER_SELECT_TYPES
            )
            dp_ids = {dp.get("dpId") for dp in device_info["dps"]}
            for dp_id, config in select_types.items():
                if dp_id not in dp_ids:
                    continue
                entities.append(
                    FairlandDpSelect(
                        coordinator=entry.runtime_data.coordinator,
                        device_info=device_info,
                        dp_id=dp_id,
                        config=config,
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
        self._int_to_option: dict[int, str] = {}
        self._option_to_int: dict[str, int] = {}

        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_mode"

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
        """Update options and current option from device data."""
        if "dps" not in self._device_info:
            return
        for dp in self._device_info["dps"]:
            if dp["dpId"] == WATER_PUMP_MODE_DP_ID:
                self._int_to_option = _parse_mode_options(dp)
                self._option_to_int = {v: k for k, v in self._int_to_option.items()}
                self._attr_options = list(self._int_to_option.values())
                raw = self._effective_dp_value(WATER_PUMP_MODE_DP_ID, dp.get("dpValue"))
                try:
                    self._attr_current_option = self._int_to_option.get(int(raw))
                except (TypeError, ValueError):
                    self._attr_current_option = None
                self._attr_available = self._attr_current_option is not None
                return
        self._attr_available = False

    async def async_select_option(self, option: str) -> None:
        """Write a new mode to the pump."""
        if option not in self._option_to_int:
            LOGGER.error("Refusing to set unknown mode option: %r", option)
            return
        target_int = self._option_to_int[option]
        try:
            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                WATER_PUMP_MODE_DP_ID,
                target_int,
            )
            # Optimistisch setzen; die Cloud meldet den neuen Wert erst nach
            # 2-4 s zurück, ein sofortiger Refresh würde den alten Wert lesen
            # und die UI zurückspringen lassen (#77).
            self._note_pending_write(WATER_PUMP_MODE_DP_ID, target_int)
            self._attr_current_option = option
            self.async_write_ha_state()
            self._schedule_write_refresh()
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


class FairlandDpSelect(FairlandEntity, SelectEntity):
    """Generic dpProperty-driven enum select (saltMachine controls, #80)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FairlandDataUpdateCoordinator,
        device_info: dict[str, Any],
        dp_id: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)

        self._device_info = device_info
        self._device_id = device_info["id"]
        self._dp_id = dp_id
        self._label_to_option = config.get("label_to_option", {})
        # When given, the enum is mapped by its integer key (firmware labels
        # may be localized); otherwise it is parsed from the dpProperty labels.
        self._int_to_option_override = config.get("int_to_option")
        self._int_to_option: dict[int, str] = {}
        self._option_to_int: dict[str, int] = {}

        self._attr_icon = config.get("icon")
        self._attr_translation_key = config.get("translation_key")
        self._attr_entity_category = config.get("entity_category")
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_select_{dp_id}"

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
        """Update options and current option from device data."""
        if "dps" not in self._device_info:
            return
        for dp in self._device_info["dps"]:
            if dp["dpId"] == self._dp_id:
                if self._int_to_option_override is not None:
                    valid = _enum_int_keys(dp)
                    self._int_to_option = {
                        i: opt
                        for i, opt in self._int_to_option_override.items()
                        if not valid or i in valid
                    }
                else:
                    self._int_to_option = _parse_enum_options(dp, self._label_to_option)
                self._option_to_int = {v: k for k, v in self._int_to_option.items()}
                self._attr_options = list(self._int_to_option.values())
                raw = self._effective_dp_value(self._dp_id, dp.get("dpValue"))
                try:
                    self._attr_current_option = self._int_to_option.get(int(raw))
                except (TypeError, ValueError):
                    self._attr_current_option = None
                self._attr_available = self._attr_current_option is not None
                return
        self._attr_available = False

    async def async_select_option(self, option: str) -> None:
        """Write a new option to the device."""
        if option not in self._option_to_int:
            LOGGER.error(
                "Refusing to set unknown option %r on dp %s", option, self._dp_id
            )
            return
        target_int = self._option_to_int[option]
        try:
            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                self._dp_id,
                target_int,
            )
            # Optimistisch setzen; die Cloud meldet den neuen Wert erst nach
            # 2-4 s zurück (#77).
            self._note_pending_write(self._dp_id, target_int)
            self._attr_current_option = option
            self.async_write_ha_state()
            self._schedule_write_refresh()
        except (FairlandApiClientCommunicationError, FairlandApiClientError) as ex:
            LOGGER.error("Error setting option on dp %s: %s", self._dp_id, ex)

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
