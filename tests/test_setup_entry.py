"""setup_entry maps login failures to the proper HA exceptions."""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "fairland"


def _load_init() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "fairland.integration_init", PKG_DIR / "__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["fairland.integration_init"] = module
    spec.loader.exec_module(module)
    return module


integration = _load_init()
# Use the module objects the integration itself imported, not sys.modules
# lookups: conftest can be imported twice and re-register the stubs.
api = sys.modules[integration.FairlandApiClient.__module__]
exceptions = sys.modules["homeassistant.exceptions"]


class _Entries:
    def __init__(self) -> None:
        self.updated = None

    def async_update_entry(self, entry, data):
        self.updated = data


class _Hass:
    def __init__(self) -> None:
        self.config_entries = _Entries()


class _Entry:
    domain = "fairland"

    def __init__(self, data) -> None:
        self.data = data


def _run(monkeypatch, data, login_exc, detect_exc=None, detect_result="us"):
    async def login(self):
        raise login_exc

    async def detect_region(self):
        if detect_exc:
            raise detect_exc
        return detect_result

    monkeypatch.setattr(api.FairlandApiClient, "login", login)
    monkeypatch.setattr(api.FairlandApiClient, "detect_region", detect_region)
    monkeypatch.setattr(integration, "FairlandDataUpdateCoordinator", lambda **kw: None)
    hass = _Hass()
    entry = _Entry(data)
    with pytest.raises(Exception) as info:
        asyncio.run(integration.async_setup_entry(hass, entry))
    return info.value, hass


CREDS = {"username": "a@b.c", "password": "x"}


def test_auth_error_with_region_triggers_reauth(monkeypatch):
    exc, _ = _run(
        monkeypatch,
        {**CREDS, "api_region": "eu"},
        api.FairlandApiClientAuthenticationError("bad"),
    )
    assert isinstance(exc, exceptions.ConfigEntryAuthFailed)


def test_communication_error_is_not_ready(monkeypatch):
    exc, _ = _run(
        monkeypatch,
        {**CREDS, "api_region": "eu"},
        api.FairlandApiClientCommunicationError("down"),
    )
    assert isinstance(exc, exceptions.ConfigEntryNotReady)


def test_legacy_entry_no_region_accepts_credentials_is_authfailed(monkeypatch):
    exc, _ = _run(
        monkeypatch,
        CREDS,
        api.FairlandApiClientAuthenticationError("bad"),
        detect_exc=api.FairlandApiClientAuthenticationError("none"),
    )
    assert isinstance(exc, exceptions.ConfigEntryAuthFailed)


def test_legacy_entry_unreachable_region_is_not_ready(monkeypatch):
    exc, _ = _run(
        monkeypatch,
        CREDS,
        api.FairlandApiClientAuthenticationError("bad"),
        detect_exc=api.FairlandApiClientCommunicationError("down"),
    )
    assert isinstance(exc, exceptions.ConfigEntryNotReady)


class _MigEntry:
    def __init__(
        self,
        entry_id,
        courtyard_id,
        unique_id=None,
        version=1,
        minor=1,
        scan_interval=None,
        options=None,
    ):
        self.entry_id = entry_id
        self.title = f"Entry {entry_id}"
        self.data = {"courtyard_id": courtyard_id}
        if scan_interval is not None:
            self.data["scan_interval"] = scan_interval
        self.options = options or {}
        self.unique_id = unique_id
        self.version = version
        self.minor_version = minor


class _MigEntries:
    def __init__(self, entries) -> None:
        self._entries = entries
        self.calls = []

    def async_entries(self, domain):
        return list(self._entries)

    def async_update_entry(self, entry, **kwargs):
        self.calls.append((entry, kwargs))
        # Like HA: apply the update to the entry.
        for key, value in kwargs.items():
            setattr(entry, key, value)


def _migrate(entry, others=()):
    hass = _Hass()
    hass.config_entries = _MigEntries([entry, *others])
    result = asyncio.run(integration.async_migrate_entry(hass, entry))
    return result, hass.config_entries.calls


def test_migrate_1_1_ends_at_1_3_in_one_call():
    entry = _MigEntry("a", 12345, scan_interval=45)
    result, calls = _migrate(entry)
    assert result is True
    assert [kw for _, kw in calls] == [
        {"unique_id": "12345", "minor_version": 2},
        {
            "data": {"courtyard_id": 12345},
            "options": {"scan_interval": 45},
            "minor_version": 3,
        },
    ]
    assert entry.minor_version == 3
    assert entry.unique_id == "12345"
    assert "scan_interval" not in entry.data


def test_migrate_1_1_without_scan_interval_only_bumps_minor_version():
    entry = _MigEntry("a", 12345)
    result, calls = _migrate(entry)
    assert result is True
    assert calls[-1][1] == {"minor_version": 3}
    assert entry.options == {}


def test_migrate_duplicate_courtyard_still_reaches_1_3():
    entry = _MigEntry("b", 12345, scan_interval=60)
    other = _MigEntry("a", 12345, unique_id="12345", minor=3)
    result, calls = _migrate(entry, [other])
    assert result is True
    assert entry.unique_id is None
    assert entry.minor_version == 3
    assert entry.options == {"scan_interval": 60}


def test_migrate_1_2_moves_scan_interval_to_options():
    entry = _MigEntry(
        "a", 12345, unique_id="12345", minor=2, scan_interval=45, options={"x": 1}
    )
    result, calls = _migrate(entry)
    assert result is True
    assert calls == [
        (
            entry,
            {
                "data": {"courtyard_id": 12345},
                "options": {"x": 1, "scan_interval": 45},
                "minor_version": 3,
            },
        )
    ]


def test_migrate_1_2_without_scan_interval_only_bumps_minor_version():
    entry = _MigEntry("a", 12345, unique_id="12345", minor=2)
    result, calls = _migrate(entry)
    assert result is True
    assert calls == [(entry, {"minor_version": 3})]


def test_migrate_future_major_version_is_refused():
    entry = _MigEntry("a", 12345, version=2, minor=0)
    result, calls = _migrate(entry)
    assert result is False
    assert calls == []


def test_migrate_current_minor_version_is_untouched():
    entry = _MigEntry("a", 12345, unique_id="12345", minor=3)
    result, calls = _migrate(entry)
    assert result is True
    assert calls == []


def test_migrate_keeps_existing_unique_id():
    entry = _MigEntry("a", 12345, unique_id="custom")
    result, calls = _migrate(entry)
    assert result is True
    assert calls[0] == (entry, {"unique_id": "custom", "minor_version": 2})
    assert entry.minor_version == 3
