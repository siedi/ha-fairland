"""Salt chlorinator VSP pump control (saltMachine dp 146, issue #107).

The iGarden app's "External control button" drives a variable-speed pump
from the chlorinator: a VSP on/off toggle plus a speed of OFF/SP1/SP2/SP3.
The firmware stores both in one raw dp, 146 "VSP device control", as two
bytes sent base64-encoded: byte 0 = toggle (1 on, 0 off), byte 1 = speed
index. Decoded from the #107 diagnostics: on+SP2 = ``AQI=`` [1, 2],
on+OFF = ``AQA=`` [1, 0], toggle off = ``AAA=`` [0, 0]. SP1 = 1 and SP3 = 3
follow the index pattern (#80/#81 units report [1, 1]).

The toggle is a switch and the speed a select. Each changes only its own
byte and keeps the other, so both read the dp through the coordinator-wide
shared pending store: an automation that turns VSP on and sets a speed
right after must not write the stale toggle byte back.
"""

from __future__ import annotations

import base64
import binascii
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.entity import DeviceInfo

from .api import FairlandApiClientCommunicationError, FairlandApiClientError
from .const import DOMAIN, LOGGER
from .entity import FairlandEntity

if TYPE_CHECKING:
    from .coordinator import FairlandDataUpdateCoordinator

VSP_DP_ID = "146"
VSP_SPEED_OPTIONS: dict[int, str] = {0: "off", 1: "sp1", 2: "sp2", 3: "sp3"}


def decode_vsp(raw: Any) -> tuple[int, int] | None:
    """Return (toggle, speed) from the base64 dp 146 value, None if unparseable."""
    if not isinstance(raw, str):
        return None
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(data) != 2:
        return None
    return data[0], data[1]


def encode_vsp(toggle: int, speed: int) -> str:
    """Pack (toggle, speed) into the base64 dp 146 raw value."""
    return base64.b64encode(bytes((toggle, speed))).decode()


def has_vsp(device_info: dict[str, Any]) -> bool:
    """Return True when the device reports a decodable dp 146."""
    for dp in device_info.get("dps", []):
        if dp.get("dpId") == VSP_DP_ID:
            return decode_vsp(dp.get("dpValue")) is not None
    return False


class FairlandVspEntity(FairlandEntity):
    """Shared dp 146 read-modify-write for the VSP switch and select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FairlandDataUpdateCoordinator,
        device_info: dict[str, Any],
    ) -> None:
        """Initialize the VSP entity."""
        super().__init__(coordinator)

        self._device_info = device_info
        self._device_id = device_info["id"]
        self._dp_id = VSP_DP_ID

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
        return self.coordinator.last_update_success and self._vsp() is not None

    def _vsp(self) -> tuple[int, int] | None:
        """Return the current (toggle, speed), honoring pending writes."""
        for dp in self._device_info.get("dps", []):
            if dp.get("dpId") == VSP_DP_ID:
                return decode_vsp(
                    self._effective_shared_dp_value(
                        self._device_id, VSP_DP_ID, dp.get("dpValue")
                    )
                )
        return None

    async def _async_write_vsp(
        self, toggle: int | None = None, speed: int | None = None
    ) -> None:
        """Write a new toggle and/or speed, keeping the other byte."""
        current = self._vsp()
        if current is None:
            LOGGER.error("VSP write skipped: dp %s unreadable", VSP_DP_ID)
            return
        value = encode_vsp(
            current[0] if toggle is None else toggle,
            current[1] if speed is None else speed,
        )
        try:
            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                VSP_DP_ID,
                value,
            )
            # Optimistisch setzen; die Cloud meldet den neuen Wert erst nach
            # 2-4 s zurück (#77). Shared, damit Switch und Select ihn sehen.
            self._note_shared_pending_write(self._device_id, VSP_DP_ID, value)
            self.async_write_ha_state()
            self._schedule_write_refresh()
        except (FairlandApiClientCommunicationError, FairlandApiClientError) as ex:
            LOGGER.error("Error setting VSP control: %s", ex)

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
