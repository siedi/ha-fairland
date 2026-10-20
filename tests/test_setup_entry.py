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
