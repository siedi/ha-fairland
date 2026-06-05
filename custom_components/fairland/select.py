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
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import slugify

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
