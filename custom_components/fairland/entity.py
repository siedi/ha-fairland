"""FairlandEntity class."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION
from .coordinator import FairlandDataUpdateCoordinator

# The cloud confirms a write back into the readable dp state only after the
# device has reported in via MQTT — measured 2-4 s on a real heat pump.
# Refreshing immediately after a write therefore always reads the OLD value
# and makes the UI flicker (issue #77). Instead we refresh after a short
# delay and keep the optimistically written value until the cloud confirms
# it or the grace period expires.
WRITE_REFRESH_DELAY = 5.0
# How long to trust an unconfirmed optimistic value before falling back to
# whatever the cloud reports. One default poll cycle: if the device really
# rejected the write (e.g. a pump refusing a mode change while priming,
# issue #78), the UI honestly snaps back after this period.
PENDING_WRITE_TIMEOUT = 30.0


class FairlandEntity(CoordinatorEntity[FairlandDataUpdateCoordinator]):
    """FairlandEntity class."""

    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: FairlandDataUpdateCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        # dpId -> (written raw value, monotonic expiry)
        self._pending_writes: dict[str, tuple[Any, float]] = {}
        self._cancel_write_refresh = None
        # self._attr_unique_id = coordinator.config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={
                (
                    coordinator.config_entry.domain,
                    coordinator.config_entry.entry_id,
                ),
            },
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any scheduled post-write refresh."""
        if self._cancel_write_refresh is not None:
            self._cancel_write_refresh()
            self._cancel_write_refresh = None
        await super().async_will_remove_from_hass()

    def _note_pending_write(self, dp_id: str, value: Any) -> None:
        """Record an optimistic write so stale polls don't revert it."""
        self._pending_writes[str(dp_id)] = (
            value,
            time.monotonic() + PENDING_WRITE_TIMEOUT,
        )

    def _effective_dp_value(self, dp_id: str, polled_value: Any) -> Any:
        """Return the value to display for a dp, honoring pending writes.

        While a write is pending, the polled cloud value lags behind for a
        few seconds; keep showing the written value until the cloud confirms
        it or the grace period runs out.
        """
        pending = self._pending_writes.get(str(dp_id))
        if pending is None:
            return polled_value
        value, expires = pending
        if self._dp_values_match(polled_value, value) or time.monotonic() >= expires:
            del self._pending_writes[str(dp_id)]
            return polled_value
        return value

    @staticmethod
    def _dp_values_match(a: Any, b: Any) -> bool:
        """Compare dp values across types (bool/int/str from the cloud)."""
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return str(a) == str(b)

    def _schedule_write_refresh(self) -> None:
        """Request a coordinator refresh once the cloud has caught up."""
        if self._cancel_write_refresh is not None:
            self._cancel_write_refresh()

        async def _refresh(_now) -> None:
            self._cancel_write_refresh = None
            await self.coordinator.async_request_refresh()

        self._cancel_write_refresh = async_call_later(
            self.hass, WRITE_REFRESH_DELAY, _refresh
        )
