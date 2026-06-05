"""Diagnostics support for Fairland."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import FairlandConfigEntry

TO_REDACT = {
    "username",
    "password",
    "accountName",
    "phone",
    "email",
    "userId",
    "token",
    "authorization",
    "sn",
    "deviceSn",
    "mac",
    "ip",
    "ssid",
    "wifiName",
    "lat",
    "lon",
    "latitude",
    "longitude",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    entry: FairlandConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator

    # The config flow stores a snapshot of the device list (including dps)
    # in entry.data at setup time. Nothing reads it afterwards and it never
    # updates, so dumping it here is misleading: it looks like live device
    # state but is frozen at setup (see issue #77, where three diagnostics
    # taken in different pump modes all showed identical stale values).
    # Only the coordinator data under "devices" reflects current state.
    entry_data = {k: v for k, v in entry.data.items() if k != "devices"}

    return {
        "entry_data": async_redact_data(entry_data, TO_REDACT),
        "devices": async_redact_data(coordinator.data, TO_REDACT)
        if coordinator.data
        else None,
    }
