"""Event platform for Fairland integration.

One Alarm event entity per device (issue #102). It fires once for every new
record in the device's cloud alarm history, so automations (e.g. a push
notification) see each alarm, including repeats of the same code. The
Latest Alarm sensor cannot do that: its state is the code, so a second E3
after an E3 is no state change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.event import EventEntity
from homeassistant.helpers.entity import DeviceInfo

from .alarms import alarm_details, alarm_key
from .const import DOMAIN, LOGGER
from .entity import FairlandEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FairlandDataUpdateCoordinator
    from .data import FairlandConfigEntry

ALARM_EVENT_TYPE = "alarm"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FairlandConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fairland event platform."""
    LOGGER.debug("Setting up Fairland event platform")

    coordinator = entry.runtime_data.coordinator
    # The key is present (None) even if the history fetch failed.
    async_add_entities(
        FairlandAlarmEvent(coordinator=coordinator, device_info=device_info)
        for device_info in coordinator.data
        if "alarms" in device_info
    )


class FairlandAlarmEvent(FairlandEntity, EventEntity):
    """Fires for each new entry in a device's cloud alarm history.

    Records already in the history when the entity starts are taken as
    known and never fired, so a restart doesn't replay old alarms. Alarms
    raised while Home Assistant was down are skipped the same way.
    """

    _attr_has_entity_name = True
    _attr_name = "Alarm"
    _attr_icon = "mdi:alert-octagram"
    _attr_event_types = [ALARM_EVENT_TYPE]

    def __init__(
        self,
        coordinator: FairlandDataUpdateCoordinator,
        device_info: dict[str, Any],
    ) -> None:
        """Initialize the event entity."""
        super().__init__(coordinator)

        self._device_id = device_info["id"]
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_alarm_event"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_info["deviceName"],
            manufacturer="Fairland",
            model=device_info.get("deviceName", "Unknown"),
            sw_version=device_info.get("version", "Unknown"),
        )
        # Keys of the records seen so far; None until a history was read.
        self._seen: set[tuple[Any, Any]] | None = None
        self._newest = 0
        self._take_new_alarms(device_info.get("alarms"))

    def _alarms(self) -> list[dict[str, Any]] | None:
        for device in self.coordinator.data:
            if device.get("id") == self._device_id:
                return device.get("alarms")
        return None

    def _take_new_alarms(
        self, alarms: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        """Return alarms not seen before, oldest first, and mark them seen.

        The first readable history only sets the baseline. A record counts as
        new if it was never seen and is not older than the newest one seen,
        so a record that drops off the page and back can't fire twice.
        """
        if alarms is None:
            return []
        keys = {alarm_key(record) for record in alarms}
        if self._seen is None:
            self._seen = keys
            self._newest = max((key[0] or 0 for key in keys), default=0)
            return []
        new = [
            record
            for record in alarms
            if alarm_key(record) not in self._seen
            and (record.get("createTime") or 0) >= self._newest
        ]
        self._seen = keys
        self._newest = max([self._newest, *(key[0] or 0 for key in keys)])
        return sorted(new, key=lambda record: record.get("createTime") or 0)

    @property
    def available(self) -> bool:
        """Unavailable while the alarm history can't be fetched."""
        return self.coordinator.last_update_success and self._alarms() is not None

    def _handle_coordinator_update(self) -> None:
        """Fire one event per new alarm record."""
        new_alarms = self._take_new_alarms(self._alarms())
        if not new_alarms:
            self.async_write_ha_state()
            return
        for record in new_alarms:
            self._trigger_event(ALARM_EVENT_TYPE, alarm_details(record))
            self.async_write_ha_state()
