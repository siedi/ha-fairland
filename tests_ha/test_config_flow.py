"""Config, reauth and options flow tests against a real Home Assistant."""

from __future__ import annotations


from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fairland.const import DOMAIN

from .conftest import (
    FairlandApiClientAuthenticationError,
    FairlandApiClientCommunicationError,
    FairlandApiClientError,
)

USER_INPUT = {"accountName": "me@example.com", "password": "secret"}

ERRORS = [
    (FairlandApiClientAuthenticationError("bad"), "invalid_auth"),
    (FairlandApiClientCommunicationError("down"), "cannot_connect"),
    (FairlandApiClientError("boom"), "unknown"),
]


def _entry(options=None, drop=(), **data) -> MockConfigEntry:
    entry_data = {
        "username": "me@example.com",
        "password": "old",
        "api_region": "eu",
        "courtyard_id": 111,
        "courtyard_name": "Garden",
        **data,
    }
    for key in drop:
        del entry_data[key]
    return MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=3,
        unique_id="111",
        title="Garden",
        data=entry_data,
        options=options or {},
    )


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_flow_creates_entry(hass, api, mock_setup_entry) -> None:
    """Credentials, then courtyard: entry with unique id and no scan_interval."""
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert "scan_interval" not in result["data_schema"].schema

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["step_id"] == "courtyard"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"courtyard": 111}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Garden"
    data = result["data"]
    assert data["username"] == "me@example.com"
    assert data["password"] == "secret"
    assert data["api_region"] == "eu"
    assert data["courtyard_id"] == 111
    assert data["courtyard_name"] == "Garden"
    assert "scan_interval" not in data
    assert data["devices"][0]["dps"] == [{"dpId": 101}]
    assert result["result"].unique_id == "111"
    assert result["result"].minor_version == 3
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(("exc", "error"), ERRORS)
@pytest.mark.parametrize("failing", ["detect_region", "get_courtyards"])
async def test_user_flow_errors_then_recovery(
    hass, api, mock_setup_entry, exc, error, failing
) -> None:
    """Each error is shown on the user form and the same flow then succeeds."""
    api[failing].side_effect = exc
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}

    api[failing].side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["step_id"] == "courtyard"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"courtyard": 111}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize("courtyards", [[], None])
async def test_no_courtyards_aborts(hass, api, courtyards) -> None:
    api["get_courtyards"].return_value = courtyards
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_courtyards"


@pytest.mark.parametrize(
    "failing", ["get_devices", "get_status"], ids=["devices", "status"]
)
@pytest.mark.parametrize(
    "exc",
    [FairlandApiClientCommunicationError("down"), FairlandApiClientError("boom")],
)
async def test_devices_error_then_recovery(
    hass, api, mock_setup_entry, failing, exc
) -> None:
    api[failing].side_effect = exc
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"courtyard": 111}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "courtyard"
    assert result["errors"] == {"base": "devices_error"}

    api[failing].side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"courtyard": 111}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_courtyard_aborts(hass, api, mock_setup_entry) -> None:
    _entry().add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"courtyard": 111}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_success(hass, api, mock_setup_entry) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new"
    api["login"].assert_awaited_once()
    api["detect_region"].assert_not_awaited()


@pytest.mark.parametrize(("exc", "error"), ERRORS)
async def test_reauth_errors_then_recovery(
    hass, api, mock_setup_entry, exc, error
) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    api["login"].side_effect = exc
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "new"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert entry.data["password"] == "old"

    api["login"].side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new"


async def test_reauth_legacy_entry_detects_and_stores_region(
    hass, api, mock_setup_entry
) -> None:
    entry = _entry(drop=("api_region",))
    entry.add_to_hass(hass)
    api["detect_region"].return_value = "us"

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "new"}
    )
    assert result["reason"] == "reauth_successful"
    assert entry.data["api_region"] == "us"
    assert entry.data["password"] == "new"
    api["login"].assert_not_awaited()


@pytest.mark.parametrize(
    ("options", "data", "expected_default"),
    [
        ({}, {}, 30),
        ({}, {"scan_interval": 45}, 45),
        ({"scan_interval": 90}, {"scan_interval": 45}, 90),
    ],
)
async def test_options_flow_changes_scan_interval(
    hass, api, mock_setup_entry, options, data, expected_default
) -> None:
    entry = _entry(options=options, **data)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    schema_key = next(iter(result["data_schema"].schema))
    assert schema_key.default() == expected_default

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 120}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"scan_interval": 120}
