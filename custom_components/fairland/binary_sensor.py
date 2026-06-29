"""Binary sensor platform for Fairland integration.

Provides protection/alarm and status indicators for inverter salt
chlorinators (saltMachine, issue #80). These data points come back as
``null`` on firmwares that don't implement them, so creation is gated on
``require_value`` where appropriate.

Polarity is derived from the firmware's own dpProperty true/false labels
rather than guessed: e.g. dp 114 reports ``true`` = 有水流 (flow present),
so as a PROBLEM sensor it is inverted (the problem is *no* flow), while
dp 117 reports ``true`` = 加盐 (salt needs topping up), which is already
the problem state and is not inverted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import (
    DOMAIN,
    LOGGER,
    SALT_MACHINE_CATEGORY_CODE,
)
from .entity import FairlandEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import FairlandDataUpdateCoordinator
    from .data import FairlandConfigEntry


# Salt-chlorinator binary sensors. `invert` flips the firmware value so the
# displayed state matches the device class (e.g. PROBLEM = on when faulted).
# `require_value` skips creation when the firmware never populates the dp.
SALT_MACHINE_BINARY_SENSOR_TYPES: dict[str, dict[str, Any]] = {
    # dp 114 true = 有水流 (flow present); the fault is the absence of flow.
    "114": {
        "name": "Water Flow Fault",
        "icon": "mdi:water-alert",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "invert": True,
        "require_value": True,
    },
    # dp 115 true = 加酸 (acid dosing active) — a running indicator, not a fault.
    "115": {
        "name": "Acid Dosing",
        "icon": "mdi:eyedropper",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "require_value": True,
    },
    # dp 117 true = 加盐 (salt needs topping up) — already the problem state.
    "117": {
        "name": "Salt Low",
        "icon": "mdi:shaker-outline",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "require_value": True,
    },
    # dp 118 true = 更换探头 (replace probe) — already the problem state.
    "118": {
        "name": "Replace Probe",
        "icon": "mdi:test-tube",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "require_value": True,
    },
    # dp 116 true = 校准 ("Calibration required" per firmware nameLanguage) —
    # a status/alarm like salt-low and replace-probe, not inverted.
    "116": {
        "name": "Calibration Required",
        "icon": "mdi:tune-vertical",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "require_value": True,
    },
    # dp 154 true = 泳池盖盖上 (pool cover closed). Informational, not a fault.
    "154": {
        "name": "Pool Cover Closed",
        "icon": "mdi:window-shutter",
        "device_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
}

CATEGORY_BINARY_SENSOR_TYPES = {
    SALT_MACHINE_CATEGORY_CODE: SALT_MACHINE_BINARY_SENSOR_TYPES,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FairlandConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fairland binary sensor platform."""
    LOGGER.debug("Setting up Fairland binary sensor platform")

    entities: list[BinarySensorEntity] = []
    for device_info in entry.runtime_data.coordinator.data:
        sensor_types = CATEGORY_BINARY_SENSOR_TYPES.get(device_info.get("categoryCode"))
        if sensor_types is None:
            continue

        dp_map = {dp.get("dpId"): dp for dp in device_info.get("dps", [])}
        for dp_id, config in sensor_types.items():
            if dp_id not in dp_map:
                continue
            if config.get("require_value") and dp_map[dp_id].get("dpValue") is None:
                LOGGER.debug(
                    "Skipping binary sensor dp %s: firmware does not populate it",
                    dp_id,
                )
                continue
            entities.append(
                FairlandBinarySensor(
                    coordinator=entry.runtime_data.coordinator,
                    device_info=device_info,
                    dp_id=dp_id,
                    config=config,
                )
            )

    if entities:
        LOGGER.debug("Adding %d Fairland binary sensors", len(entities))
    async_add_entities(entities, True)


class FairlandBinarySensor(FairlandEntity, BinarySensorEntity):
    """Representation of a Fairland binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FairlandDataUpdateCoordinator,
        device_info: dict[str, Any],
        dp_id: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)

        self._device_info = device_info
        self._device_id = device_info["id"]
        self._dp_id = dp_id
        self._invert = bool(config.get("invert", False))

        self._attr_name = config["name"]
        self._attr_icon = config.get("icon")
        self._attr_device_class = config.get("device_class")
        self._attr_entity_category = config.get("entity_category")
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_bs_{dp_id}"

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

    @property
    def is_on(self) -> bool | None:
        """Return whether the sensor is on (None if not yet reported)."""
        for device in self.coordinator.data:
            if device.get("id") != self._device_id:
                continue
            for dp in device.get("dps", []):
                if dp.get("dpId") != self._dp_id:
                    continue
                raw = dp.get("dpValue")
                if raw is None:
                    return None
                val = _coerce_bool(raw)
                return (not val) if self._invert else val
        return None


def _coerce_bool(raw: Any) -> bool:
    """Coerce a dpValue (bool / 0|1 / "0"|"1"|"on") to a boolean state."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "on", "yes")
    return bool(raw)
