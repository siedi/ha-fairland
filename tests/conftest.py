"""Test harness for the Fairland integration platforms.

Home Assistant is not installed for the test run. Instead we stub the
``homeassistant.*`` modules (and ``aiohttp``) in ``sys.modules`` with the
minimal surface each platform touches, then load the integration's platform
files via importlib. Tests feed real (sanitized) device dicts from the
diagnostics fixtures and assert which entities are created and how their
values/units/scales come out. See CLAUDE.md ("Verifying Against Real
Devices") for the rationale.

Limitation: the stubs are intentionally permissive, so these tests verify dp
mapping (scale, units, polarity, category dispatch) but cannot catch misuse
of the real Home Assistant entity API.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = REPO_ROOT / "custom_components" / "fairland"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# --------------------------------------------------------------------------
# Stub homeassistant.* and aiohttp
# --------------------------------------------------------------------------
class _AttrStr:
    """Enum stand-in: attribute access returns the attribute name."""

    def __getattr__(self, name: str) -> str:
        return name


class _IntFlag:
    """Bit-flag stand-in: attribute access returns an int so ``|`` works."""

    def __getattr__(self, name: str) -> int:
        return 1


def _register(name: str, **attrs) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


class _CoordinatorEntity:
    """Minimal CoordinatorEntity: stores the coordinator, no-ops the rest."""

    hass = None

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator

    def __class_getitem__(cls, item):  # CoordinatorEntity[Coordinator]
        return cls

    def async_on_remove(self, *args, **kwargs) -> None:
        pass

    def async_write_ha_state(self) -> None:
        pass

    def schedule_update_ha_state(self, *args, **kwargs) -> None:
        pass


def _device_info(**kwargs) -> dict:
    return dict(kwargs)


def _slugify(value) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(value).lower()).strip("_")


def _install_stubs() -> None:
    _register("aiohttp", ClientSession=object, ClientError=Exception)
    _register("homeassistant")
    _register(
        "homeassistant.const",
        PERCENTAGE="%",
        UnitOfElectricCurrent=_AttrStr(),
        UnitOfElectricPotential=_AttrStr(),
        UnitOfEnergy=_AttrStr(),
        UnitOfPower=_AttrStr(),
        UnitOfTemperature=_AttrStr(),
        UnitOfTime=_AttrStr(),
        CONF_PASSWORD="password",
        CONF_USERNAME="username",
        Platform=_AttrStr(),
        ATTR_TEMPERATURE="temperature",
        PRECISION_WHOLE=1,
    )
    _register(
        "homeassistant.components.climate",
        ClimateEntity=type("ClimateEntity", (), {}),
    )
    _register(
        "homeassistant.components.climate.const",
        ClimateEntityFeature=_IntFlag(),
        HVACAction=_AttrStr(),
        HVACMode=_AttrStr(),
    )
    _register("homeassistant.core", HomeAssistant=object)
    _register("homeassistant.util", slugify=_slugify)
    _register(
        "homeassistant.components.sensor",
        SensorDeviceClass=_AttrStr(),
        SensorEntity=type("SensorEntity", (), {}),
        SensorStateClass=_AttrStr(),
    )
    _register(
        "homeassistant.components.switch",
        SwitchEntity=type("SwitchEntity", (), {}),
    )
    _register(
        "homeassistant.components.select",
        SelectEntity=type("SelectEntity", (), {}),
    )
    _register(
        "homeassistant.components.number",
        NumberDeviceClass=_AttrStr(),
        NumberEntity=type("NumberEntity", (), {}),
        NumberMode=_AttrStr(),
    )
    _register(
        "homeassistant.components.binary_sensor",
        BinarySensorDeviceClass=_AttrStr(),
        BinarySensorEntity=type("BinarySensorEntity", (), {}),
    )
    _register("homeassistant.helpers")
    _register(
        "homeassistant.helpers.entity",
        DeviceInfo=_device_info,
        EntityCategory=_AttrStr(),
    )
    _register("homeassistant.helpers.device_registry", DeviceInfo=_device_info)
    _register(
        "homeassistant.helpers.update_coordinator",
        CoordinatorEntity=_CoordinatorEntity,
        DataUpdateCoordinator=type("DataUpdateCoordinator", (), {}),
        UpdateFailed=type("UpdateFailed", (Exception,), {}),
    )
    _register(
        "homeassistant.helpers.event",
        async_call_later=lambda *a, **k: lambda: None,
    )
    _register("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    _register(
        "homeassistant.helpers.aiohttp_client",
        async_get_clientsession=lambda *a, **k: None,
    )
    _register("homeassistant.loader", async_get_loaded_integration=lambda *a, **k: None)


def _load_integration() -> dict[str, types.ModuleType]:
    package = types.ModuleType("fairland")
    package.__path__ = [str(PKG_DIR)]
    sys.modules["fairland"] = package

    def load(name: str) -> types.ModuleType:
        spec = importlib.util.spec_from_file_location(
            f"fairland.{name}", PKG_DIR / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"fairland.{name}"] = module
        spec.loader.exec_module(module)
        return module

    # Dependency order: leaves first.
    for name in ("const", "api", "data", "coordinator", "entity"):
        load(name)
    return {
        name: load(name)
        for name in (
            "sensor",
            "switch",
            "select",
            "number",
            "binary_sensor",
            "climate",
        )
    }


_install_stubs()
_PLATFORMS = _load_integration()


# --------------------------------------------------------------------------
# Fake coordinator / config entry plumbing
# --------------------------------------------------------------------------
class FakeClient:
    """Records set_device_status calls so write paths can be asserted."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def set_device_status(self, device_id, dp_id, value):
        self.calls.append((device_id, dp_id, value))


class _FakeConfigEntry:
    domain = "fairland"
    entry_id = "test_entry"


class _FakeRuntime:
    def __init__(self, coordinator, client) -> None:
        self.coordinator = coordinator
        self.client = client


class _FakeCoordinator:
    def __init__(self, devices, client) -> None:
        self.data = devices
        self.last_update_success = True
        self.config_entry = _FakeConfigEntry()
        self.config_entry.runtime_data = _FakeRuntime(self, client)

    def async_add_listener(self, *args, **kwargs):
        return lambda: None

    async def async_request_refresh(self) -> None:
        pass


class _FakeEntry:
    def __init__(self, coordinator, client) -> None:
        self.runtime_data = _FakeRuntime(coordinator, client)


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------
def load_fixture(name: str) -> list[dict]:
    """Return the device list from a fixture file as a single-device list."""
    data = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
    return data if isinstance(data, list) else [data]


@pytest.fixture
def platforms() -> dict[str, types.ModuleType]:
    return _PLATFORMS


@pytest.fixture
def setup_entities():
    """Return a helper: (platform_name, devices) -> (entities, client)."""

    def _run(platform_name: str, devices: list[dict]):
        client = FakeClient()
        coordinator = _FakeCoordinator(devices, client)
        entry = _FakeEntry(coordinator, client)
        collected: list = []

        def _add(entities, *args, **kwargs):
            collected.extend(entities)

        asyncio.run(_PLATFORMS[platform_name].async_setup_entry(None, entry, _add))
        return collected, client

    return _run
