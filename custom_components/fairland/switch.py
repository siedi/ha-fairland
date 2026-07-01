"""Switch platform for Fairland integration."""

from __future__ import annotations

import base64
import struct
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import DeviceInfo

from .api import FairlandApiClientCommunicationError, FairlandApiClientError
from .const import (
    DOMAIN,
    HEAT_PUMP_CATEGORY_CODE,
    LOGGER,
    POOL_SURFER_CATEGORY_CODE,
    SALT_MACHINE_CATEGORY_CODE,
    WATER_PUMP_CATEGORY_CODE,
)
from .entity import FairlandEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FairlandDataUpdateCoordinator
    from .data import FairlandConfigEntry

# Per-category switch maps. Each entry maps a dpId to its presentation.
# `is_power` marks the device's main power switch, which keeps the original
# `_switch` unique_id for backwards compatibility; every other switch gets a
# `_switch_<dpId>` suffix. `require_value` skips creation when the firmware
# never populates the dp (always null).
#
# Power dpId differs per category: heat pumps use dpId 101, water pumps use
# dpId 105 (dpId 105 is the "Running Percentage" sensor on heat pumps, so the
# maps must stay separate), salt chlorinators use dpId 103.
HEAT_PUMP_SWITCH_TYPES: dict[str, dict[str, Any]] = {
    "101": {"name": "Power", "icon": "mdi:power", "is_power": True},
}
WATER_PUMP_SWITCH_TYPES: dict[str, dict[str, Any]] = {
    "105": {"name": "Power", "icon": "mdi:power", "is_power": True},
}
SALT_MACHINE_SWITCH_TYPES: dict[str, dict[str, Any]] = {
    "103": {"name": "Power", "icon": "mdi:power", "is_power": True},
    "107": {"name": "Turbo", "icon": "mdi:rocket-launch"},
    "121": {"name": "Timer", "icon": "mdi:timer-cog"},
    "123": {"name": "Real-time Salinity Monitoring", "icon": "mdi:shaker-outline"},
    # Backwash: rw, but null on firmwares without it. Useful for automations
    # (pausing chlorine production during a backwash cycle).
    "153": {"name": "Backwash", "icon": "mdi:water-sync", "require_value": True},
}
# Swim jet (poolSurfer, #85). There is no boolean power dp; the on/off state
# lives in the dp 22 state machine. Powering on runs Free Mode P0 by default
# (confirmed by the user manual and the on/off diagnostics: dp 22 goes
# 0 = POWER_OFF -> 3 = FREE_MODE_RUNNING), so the Power switch writes those
# enum values instead of a bool. `enum_on_value`/`enum_off_value` opt into
# the enum write/read path; any non-POWER_OFF state reads as on.
POOL_SURFER_SWITCH_TYPES: dict[str, dict[str, Any]] = {
    "22": {
        "name": "Power",
        "icon": "mdi:power",
        "is_power": True,
        "enum_on_value": 3,
        "enum_off_value": 0,
    },
}

CATEGORY_SWITCH_TYPES = {
    HEAT_PUMP_CATEGORY_CODE: HEAT_PUMP_SWITCH_TYPES,
    WATER_PUMP_CATEGORY_CODE: WATER_PUMP_SWITCH_TYPES,
    SALT_MACHINE_CATEGORY_CODE: SALT_MACHINE_SWITCH_TYPES,
    POOL_SURFER_CATEGORY_CODE: POOL_SURFER_SWITCH_TYPES,
}

# Swim-jet pause control (#85). The dp 22 state machine has a suspend state
# per mode family (the manual's Mode-button pause). Pausing/resuming writes
# the packed dp 20 "Mode + Status" field (like the mode select), keeping the
# current mode and toggling only the run state between running and suspend:
#   free    running 3 <-> suspend 4
#   timer   running 8 <-> suspend 9
#   training/surf/custom running 13 <-> suspend 14
# Only the training/surf suspend (14) is observed in a diagnostic; free/timer
# follow the same running+1 pattern.
SWIM_JET_MODE_STATUS_DP = "20"
SWIM_JET_STATUS_DP = "22"
SWIM_JET_MODE_DP = "21"
SWIM_JET_SUSPEND_FOR_RUNNING = {3: 4, 8: 9, 13: 14}
SWIM_JET_RESUME_FOR_SUSPEND = {4: 3, 9: 8, 14: 13}
SWIM_JET_SUSPEND_STATES = frozenset(SWIM_JET_RESUME_FOR_SUSPEND)


def _pack_mode_status(mode: int, status: int) -> str:
    """Pack a swim-jet <mode, status> pair into the base64 dp 20 raw value."""
    return base64.b64encode(struct.pack("<HH", mode, status)).decode()


def _coerce_bool(raw: Any) -> bool:
    """Coerce a dpValue (bool / 0|1 / "0"|"1"|"on") to a switch state."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "on", "yes")
    return bool(raw)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FairlandConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fairland switch platform."""
    LOGGER.debug("Setting up Fairland switch platform")

    entities = []
    for device_info in entry.runtime_data.coordinator.data:
        switch_types = CATEGORY_SWITCH_TYPES.get(device_info.get("categoryCode"))
        if switch_types is None:
            continue

        dp_map = {dp.get("dpId"): dp for dp in device_info.get("dps", [])}
        for dp_id, config in switch_types.items():
            if dp_id not in dp_map:
                continue
            if config.get("require_value") and dp_map[dp_id].get("dpValue") is None:
                LOGGER.debug(
                    "Skipping switch dp %s: firmware does not populate it", dp_id
                )
                continue
            entities.append(
                FairlandSwitch(
                    coordinator=entry.runtime_data.coordinator,
                    device_info=device_info,
                    dp_id=dp_id,
                    config=config,
                )
            )

        # Swim jet: add a Pause switch alongside the Power switch when the
        # state machine (dp 22) and the mode/status write field (dp 20) exist.
        if (
            device_info.get("categoryCode") == POOL_SURFER_CATEGORY_CODE
            and SWIM_JET_STATUS_DP in dp_map
            and SWIM_JET_MODE_STATUS_DP in dp_map
        ):
            entities.append(
                FairlandSwimJetPauseSwitch(
                    coordinator=entry.runtime_data.coordinator,
                    device_info=device_info,
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
        dp_id: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize the switch class."""
        super().__init__(coordinator)

        self._device_info = device_info
        self._device_id = device_info["id"]
        self._dp_id = dp_id

        # Preserve the original unique_id for the main power switch so
        # existing installs keep their entity history.
        suffix = "switch" if config.get("is_power") else f"switch_{dp_id}"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_{suffix}"
        self._attr_name = config["name"]
        self._attr_icon = config.get("icon", "mdi:power")
        # Enum-backed switches (e.g. the swim jet's dp 22 state machine) write
        # integer states instead of a bool; on = any value other than "off".
        self._enum_on = config.get("enum_on_value")
        self._enum_off = config.get("enum_off_value")
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

    def _coerce_on(self, raw: Any) -> bool:
        """Map a raw dpValue to on/off, honoring an enum on/off mapping."""
        if self._enum_on is None:
            return _coerce_bool(raw)
        if raw is None:
            return False
        try:
            return int(raw) != int(self._enum_off)
        except (TypeError, ValueError):
            return False

    def _update_state(self):
        """Update state from device data."""
        if "dps" in self._device_info:
            for dp in self._device_info["dps"]:
                if dp["dpId"] == self._dp_id:
                    self._is_on = self._coerce_on(
                        self._effective_dp_value(self._dp_id, dp["dpValue"])
                    )
                    self._attr_available = True
                    return

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return if entity is available."""
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

    async def _async_write(self, value: bool) -> None:
        """Write a new on/off state, holding it optimistically (#77)."""
        # Enum-backed switches send the mapped integer state (e.g. the swim
        # jet's dp 22: 3 = FREE_MODE_RUNNING, 0 = POWER_OFF) rather than a bool.
        write_value: Any = value
        if self._enum_on is not None:
            write_value = self._enum_on if value else self._enum_off
        try:
            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                self._dp_id,
                write_value,
            )
            # Optimistisch setzen; die Cloud meldet den neuen Wert erst nach
            # 2-4 s zurück, ein sofortiger Refresh würde den alten Wert lesen
            # und die UI zurückspringen lassen (#77).
            self._note_pending_write(self._dp_id, write_value)
            self._is_on = value
            self.async_write_ha_state()
            self._schedule_write_refresh()
        except (FairlandApiClientCommunicationError, FairlandApiClientError) as ex:
            LOGGER.error("Error setting switch %s: %s", self._dp_id, ex)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self._async_write(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        await self._async_write(False)


class FairlandSwimJetPauseSwitch(FairlandEntity, SwitchEntity):
    """Pause/resume switch for the swim jet (#85).

    On = the jet is suspended (paused). Toggling writes the packed dp 20
    "Mode + Status" field, keeping the current mode and switching only the run
    state between running and suspend. It is a no-op when the jet is off or
    already in the requested state.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:pause"

    def __init__(
        self,
        coordinator: FairlandDataUpdateCoordinator,
        device_info: dict[str, Any],
    ) -> None:
        """Initialize the pause switch."""
        super().__init__(coordinator)

        self._device_info = device_info
        self._device_id = device_info["id"]
        self._attr_name = "Pause"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_pause"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_info["deviceName"],
            manufacturer="Fairland",
            model=device_info.get("deviceName", "Unknown"),
            sw_version=device_info.get("version", "Unknown"),
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    def _read_int(self, dp_id: str) -> int | None:
        """Return a dp's current integer value, honoring pending writes."""
        for dp in self._device_info.get("dps", []):
            if dp["dpId"] == dp_id:
                raw = self._effective_dp_value(dp_id, dp.get("dpValue"))
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return None
        return None

    @property
    def is_on(self) -> bool:
        """Return true if the jet is currently suspended (paused)."""
        return self._read_int(SWIM_JET_STATUS_DP) in SWIM_JET_SUSPEND_STATES

    async def _write_status(self, status: int) -> None:
        """Write <current mode, status> to the packed dp 20 field."""
        mode = self._read_int(SWIM_JET_MODE_DP) or 0
        try:
            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                SWIM_JET_MODE_STATUS_DP,
                _pack_mode_status(mode, status),
            )
            # Hold the new run state optimistically until the cloud catches up
            # (#77); is_on reads dp 22, so the pending write is noted there.
            self._note_pending_write(SWIM_JET_STATUS_DP, status)
            self.async_write_ha_state()
            self._schedule_write_refresh()
        except (FairlandApiClientCommunicationError, FairlandApiClientError) as ex:
            LOGGER.error("Error setting swim-jet pause state: %s", ex)

    async def async_turn_on(self, **kwargs) -> None:
        """Pause: suspend the currently running mode."""
        status = self._read_int(SWIM_JET_STATUS_DP)
        target = SWIM_JET_SUSPEND_FOR_RUNNING.get(status)
        if target is None:
            LOGGER.debug("Pause ignored: swim jet not running (status=%s)", status)
            return
        await self._write_status(target)

    async def async_turn_off(self, **kwargs) -> None:
        """Resume: return the suspended mode to running."""
        status = self._read_int(SWIM_JET_STATUS_DP)
        target = SWIM_JET_RESUME_FOR_SUSPEND.get(status)
        if target is None:
            LOGGER.debug("Resume ignored: swim jet not paused (status=%s)", status)
            return
        await self._write_status(target)

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
                self.async_write_ha_state()
                break
