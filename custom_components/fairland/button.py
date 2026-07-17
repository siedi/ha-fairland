"""Button platform for Fairland integration."""

from __future__ import annotations

import base64
import struct
from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo

from .api import FairlandApiClientCommunicationError, FairlandApiClientError
from .const import DOMAIN, LOGGER, POOL_SURFER_CATEGORY_CODE
from .entity import FairlandEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FairlandDataUpdateCoordinator
    from .data import FairlandConfigEntry

# Swim jet (poolSurfer, #96 follow-up to #85). The device does not model
# "Free" and "Timer" as two working modes: dp 21 value 0 is a single mode
# ("Frei- oder Timer-Modus") and the FREE-vs-TIMER distinction lives only in
# the dp 22 state machine (FREE_MODE_* 1-5 vs TIMING_MODE_* 6-10). So there is
# no persistent "timer" flag to bind a switch/select to — starting the native
# timer is a one-shot state-machine transition, which maps to a Button.
#
# Pressing the button writes the packed dp 20 "Mode + Status" field
# = <mode 0, status 8 TIMING_MODE_RUNNING>, base64-encoded ("AAAIAA=="). The
# firmware then runs its own countdown using the already-exposed Timer Mode
# Default Duration (dp 30) and Timer Mode Default Speed (dp 29) numbers; the
# existing Pause switch (dp 22 8<->9) and Power switch (any state -> 0) cover
# the rest of the timer lifecycle.
#
# NOTE: the <0, 8> pair is decoded from a real diagnostic (PR #88), but only
# ever *observed* while a timer was already running — that *writing* it starts
# the timer is not yet confirmed on-device (#96). Same caveat as the mode
# select writes when they were first added.
SWIM_JET_MODE_STATUS_DP = "20"
SWIM_JET_STATUS_DP = "22"
SWIM_JET_TIMER_MODE = 0
SWIM_JET_TIMER_STATUS = 8


def _pack_mode_status(mode: int, status: int) -> str:
    """Pack a swim-jet <mode, status> pair into the base64 dp 20 raw value."""
    return base64.b64encode(struct.pack("<HH", mode, status)).decode()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FairlandConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fairland button platform."""
    LOGGER.debug("Setting up Fairland button platform")

    entities = []
    for device_info in entry.runtime_data.coordinator.data:
        # Strictly poolSurfer-only: the packed dp 20 field and the dp 22 state
        # machine are unique to this category's dp namespace.
        if device_info.get("categoryCode") != POOL_SURFER_CATEGORY_CODE:
            continue

        dp_map = {dp.get("dpId"): dp for dp in device_info.get("dps", [])}
        if SWIM_JET_MODE_STATUS_DP in dp_map and SWIM_JET_STATUS_DP in dp_map:
            entities.append(
                FairlandSwimJetStartTimerButton(
                    coordinator=entry.runtime_data.coordinator,
                    device_info=device_info,
                )
            )
    async_add_entities(entities, True)


class FairlandSwimJetStartTimerButton(FairlandEntity, ButtonEntity):
    """Start the swim jet's native timer mode (#96).

    Writes the packed dp 20 "Mode + Status" field = <mode 0, status 8> so the
    device runs its own countdown with the configured Timer Mode Default
    Duration/Speed, instead of the indefinite Free Mode that the mode select's
    "Free or timed mode" option starts.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:timer-play"

    def __init__(
        self,
        coordinator: FairlandDataUpdateCoordinator,
        device_info: dict[str, Any],
    ) -> None:
        """Initialize the start-timer button."""
        super().__init__(coordinator)

        self._device_info = device_info
        self._device_id = device_info["id"]
        self._attr_name = "Start Timer"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_start_timer"

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

    async def async_press(self) -> None:
        """Start timer mode by writing <mode 0, status 8> to dp 20."""
        try:
            await self.coordinator.config_entry.runtime_data.client.set_device_status(
                self._device_id,
                SWIM_JET_MODE_STATUS_DP,
                _pack_mode_status(SWIM_JET_TIMER_MODE, SWIM_JET_TIMER_STATUS),
            )
            # Nudge a refresh so the Status sensor / Power switch reflect the
            # new running state once the cloud catches up (2-4 s, #77).
            self._schedule_write_refresh()
        except (FairlandApiClientCommunicationError, FairlandApiClientError) as ex:
            LOGGER.error("Error starting swim-jet timer: %s", ex)
