"""Config flow for Fairland integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import homeassistant.helpers.config_validation as cv

from .api import (
    FairlandApiClient,
    FairlandApiClientAuthenticationError,
    FairlandApiClientCommunicationError,
    FairlandApiClientError,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, LOGGER

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("accountName"): cv.string,
        vol.Required("password"): cv.string,
        vol.Required("countryCode", default="DE"): cv.string,
        vol.Required("scan_interval", default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
    }
)

STEP_RECONFIGURE_SCHEMA = vol.Schema(
    {
        vol.Required("scan_interval", default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fairland."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.apiClient = None
        self.username = None
        self.password = None
        self.country_code = None
        self.scan_interval = None
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
            self.country_code = user_input["countryCode"]
            self.scan_interval = user_input["scan_interval"]

            try:
                self.apiClient = FairlandApiClient(
                    username=self.username,
                    password=self.password,
                    country_code=self.country_code,
                    session=async_create_clientsession(self.hass),
                )
                await self.apiClient.login()

                self.courtyards = await self.apiClient.get_courtyards()

            except FairlandApiClientAuthenticationError as exception:
                LOGGER.warning(exception)
                _errors["base"] = "auth"
            except FairlandApiClientCommunicationError as exception:
                LOGGER.error(exception)
                _errors["base"] = "connection"
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
                        "countryCode": self.country_code,
                        "scan_interval": self.scan_interval,
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

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle reconfiguration by the user."""
        _errors = {}

        # Get the entry using the standard method
        entry = self._get_reconfigure_entry()

        # Abort if the unique ID doesn't match
        self._abort_if_unique_id_configured()

        if user_input is not None:
            # Update scan interval
            new_data = {
                **entry.data,
                "scan_interval": user_input["scan_interval"],
            }

            # Update the config entry and reload the integration
            return self.async_update_reload_and_abort(
                entry, data=new_data, reason="reconfigure_successful"
            )

        # Prepare schema with current values
        current_scan_interval = entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)

        # Show form with current values as defaults
        schema = vol.Schema(
            {
                vol.Required(
                    "scan_interval", default=current_scan_interval
                ): cv.positive_int,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=_errors,
            description_placeholders={"device_name": entry.title},
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class CannotGetCourtyards(HomeAssistantError):
    """Error to indicate we cannot get the courtyards."""
