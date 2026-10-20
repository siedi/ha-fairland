"""Config flow for Fairland integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import homeassistant.helpers.config_validation as cv

from .api import (
    FairlandApiClient,
    FairlandApiClientAuthenticationError,
    FairlandApiClientCommunicationError,
    FairlandApiClientError,
)
from .const import (
    CONF_API_REGION,
    DEFAULT_API_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("accountName"): cv.string,
        vol.Required("password"): cv.string,
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required("password"): cv.string})


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fairland."""

    VERSION = 1
    MINOR_VERSION = 3

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> FairlandOptionsFlow:
        """Return the options flow (scan interval)."""
        return FairlandOptionsFlow()

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.apiClient = None
        self.username = None
        self.password = None
        self.api_region = None
        self.courtyards = None
        self.selected_courtyard = None
        self.devices = None

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        _errors = {}

        if user_input is not None:
            self.username = user_input["accountName"]
            self.password = user_input["password"]

            try:
                self.apiClient = FairlandApiClient(
                    username=self.username,
                    password=self.password,
                    session=async_create_clientsession(self.hass),
                )
                # Accounts live on one of several regional servers; try
                # them all instead of asking the user (see const.API_REGIONS).
                self.api_region = await self.apiClient.detect_region()

                self.courtyards = await self.apiClient.get_courtyards()

            except FairlandApiClientAuthenticationError as exception:
                LOGGER.warning(exception)
                _errors["base"] = "invalid_auth"
            except FairlandApiClientCommunicationError as exception:
                LOGGER.error(exception)
                _errors["base"] = "cannot_connect"
            except FairlandApiClientError as exception:
                LOGGER.exception(exception)
                _errors["base"] = "unknown"
            else:
                # If successful, move to the next step
                return await self.async_step_courtyard()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=_errors
        )

    async def async_step_courtyard(
        self,
        user_input=None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the courtyard selection step."""
        _errors = {}

        # Fehlerbehandlung für den Fall, dass courtyards None ist
        if self.courtyards is None or len(self.courtyards) == 0:
            LOGGER.error("No courtyards found or courtyards is None")
            _errors["base"] = "no_courtyards"
            # Zurück zum Benutzer-Schritt, um es erneut zu versuchen
            return self.async_abort(reason="no_courtyards")

        if user_input is not None:
            # Get selected courtyard
            selected_courtyard_id = user_input["courtyard"]
            selected_courtyard = next(
                c for c in self.courtyards if c["id"] == selected_courtyard_id
            )

            # The courtyard id is server-assigned and stable; one entry per
            # courtyard (the e-mail is user-changeable, so not used here).
            await self.async_set_unique_id(str(selected_courtyard_id))
            self._abort_if_unique_id_configured()

            # Store the selected courtyard
            self.selected_courtyard = selected_courtyard

            # Get all devices in the courtyard
            try:
                devices = await self.apiClient.get_all_devices_in_courtyard(
                    selected_courtyard_id
                )
                # Store the devices data for use during entry creation
                for device in devices:
                    dps = await self.apiClient.get_device_status(device["id"])
                    device["dps"] = dps

                self.devices = devices

                # Save the data for the entry
                return self.async_create_entry(
                    title=selected_courtyard["name"],
                    data={
                        "username": self.username,
                        "password": self.password,
                        CONF_API_REGION: self.api_region,
                        "courtyard_id": selected_courtyard_id,
                        "courtyard_name": selected_courtyard["name"],
                        "devices": self.devices,
                    },
                )
            except (FairlandApiClientCommunicationError, FairlandApiClientError) as ex:
                LOGGER.exception("Failed to get devices: %s", ex)
                _errors["base"] = "devices_error"

        # Zeige das Formular nur an, wenn courtyards gültig ist
        return self.async_show_form(
            step_id="courtyard",
            data_schema=vol.Schema(
                {
                    vol.Required("courtyard"): vol.In(
                        {c["id"]: c["name"] for c in self.courtyards}
                    ),
                }
            ),
            errors=_errors,
            description_placeholders={"username": self.username},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Start reauthentication after the stored credentials were rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask for the new password and validate it."""
        _errors = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            client = FairlandApiClient(
                username=entry.data["username"],
                password=user_input["password"],
                session=async_create_clientsession(self.hass),
                region=entry.data.get(CONF_API_REGION, DEFAULT_API_REGION),
            )
            data_updates = {"password": user_input["password"]}
            try:
                if CONF_API_REGION in entry.data:
                    await client.login()
                else:
                    data_updates[CONF_API_REGION] = await client.detect_region()
            except FairlandApiClientAuthenticationError as exception:
                LOGGER.warning(exception)
                _errors["base"] = "invalid_auth"
            except FairlandApiClientCommunicationError as exception:
                LOGGER.error(exception)
                _errors["base"] = "cannot_connect"
            except FairlandApiClientError as exception:
                LOGGER.exception(exception)
                _errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates=data_updates
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            errors=_errors,
            description_placeholders={"username": entry.data["username"]},
        )


class FairlandOptionsFlow(config_entries.OptionsFlowWithReload):
    """Options: polling interval. The entry is reloaded when they change."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            "scan_interval",
            self.config_entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required("scan_interval", default=current): cv.positive_int}
            ),
        )
