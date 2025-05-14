"""API client for Fairland."""

from __future__ import annotations

import socket
from typing import Any

import aiohttp
import async_timeout

from .const import LOGGER


class FairlandApiClientError(Exception):
    """Exception to indicate a general API error."""


class FairlandApiClientCommunicationError(
    FairlandApiClientError,
):
    """Exception to indicate a communication error."""


class FairlandApiClientAuthenticationError(
    FairlandApiClientError,
):
    """Exception to indicate an authentication error."""


def _verify_response_or_raise(response: aiohttp.ClientResponse) -> None:
    """Verify that the response is valid."""
    if response.status in (401, 403):
        msg = "Invalid credentials"
        LOGGER.error(msg)
        raise FairlandApiClientAuthenticationError(
            msg,
        )
    response.raise_for_status()


class FairlandApiClient:
    """Fairland API client."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        country_code: str = "DE",
        phone_code: str = "49",
    ) -> None:
        """Initialize the API client."""
        self.username = username
        self.password = password
        self.country_code = country_code
        self.phone_code = phone_code
        self.token = None
        self.user_id = None
        self._session = session

    def _get_headers(self):
        """Get headers for API requests."""
        if not self.token:
            raise Exception("Not logged in")

        return {
            "Content-Type": "application/json",
            "terminal": "2",
            "Authorization": self.token,
            "User-Agent": "Dart/3.5 (dart:io)",
            "Accept": "application/json;charset=UTF-8",
        }

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        payload: dict | None = None,
        headers: dict | None = None,
    ) -> Any:
        """Get information from the API."""
        if headers is None:
            headers = self._get_headers()

        try:
            async with async_timeout.timeout(10):
                response = await self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=payload,
                )
                _verify_response_or_raise(response)
                data = await response.json()
                return data["data"]

        except FairlandApiClientAuthenticationError:
            LOGGER.info("Maybe the token expired. Logging in again")
            await self.login()  # Get a new token
            headers = self._get_headers()  # Get headers with new token
            response = await self._session.request(
                method=method,
                url=url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = await response.json()
            return data["data"]

        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            LOGGER.error(msg)
            raise FairlandApiClientCommunicationError(
                msg,
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            LOGGER.error(msg)
            raise FairlandApiClientCommunicationError(
                msg,
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            msg = f"Something really wrong happened! - {exception}"
            LOGGER.error(msg)
            raise FairlandApiClientError(
                msg,
            ) from exception

    async def login(self) -> Any:
        """Login to the Fairland API."""
        url = "https://api-eu.fairlandiot.com/fyld-user-api/user/loginByPassword"
        payload = {
            "phoneCode": "49",
            "accountName": self.username,
            "password": self.password,
            "countryCode": "DE",
            "randStr": "",
            "ticket": "",
        }
        headers = {
            "Content-Type": "application/json",
            "terminal": "2",
            "User-Agent": "Dart/3.5 (dart:io)",
            "Accept": "application/json;charset=UTF-8",
        }

        try:
            async with async_timeout.timeout(10):
                response = await self._session.request(
                    method="post",
                    url=url,
                    headers=headers,
                    json=payload,
                )
                if response.status != 200:
                    raise Exception(
                        f"Failed to login: {response.status_code} {response.text}"
                    )

                data = await response.json()

                if data["code"] != 200000:
                    raise Exception(f"Login failed: {data['code']} {data['msg']}")

                self.token = data["data"]["authorization"]
                self.user_id = data["data"]["userId"]

                return data["data"]

        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            LOGGER.error(msg)
            raise FairlandApiClientCommunicationError(
                msg,
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            LOGGER.error(msg)
            raise FairlandApiClientCommunicationError(
                msg,
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            msg = f"Something really wrong happened! - {exception}"
            LOGGER.error(msg)
            raise FairlandApiClientError(
                msg,
            ) from exception

    async def get_courtyards(self) -> Any:
        """Get courtyards."""
        return await self._api_wrapper(
            method="post",
            url="https://api-eu.fairlandiot.com/fyld-device-api/deviceGroupApi/allGroupInfo",
            payload={
                "needDeviceCount": True,
            },
        )

    async def get_all_devices_in_courtyard(self, courtyard_id: str) -> Any:
        """Get all devices in a courtyard."""
        data = await self._api_wrapper(
            method="post",
            url="https://api-eu.fairlandiot.com/fyld-device-api/deviceApi/deviceAllGroupInfo",
            payload={
                "deviceGroupId": courtyard_id,
                "shareId": None,
            },
        )
        return data["bindDeviceInfos"]  # Geräteliste zurückgeben

    async def get_device_status(self, device_id: str) -> Any:
        """Get device status."""
        return await self._api_wrapper(
            method="post",
            url="https://api-eu.fairlandiot.com/fyld-device-api/deviceDataPointApi/deviceDataPointInfo",
            payload={
                "deviceId": device_id,
            },
        )

    async def set_device_status(self, device_id: str, dp_id: str, value: str) -> Any:
        """Set device status."""
        return await self._api_wrapper(
            method="post",
            url="https://api-eu.fairlandiot.com/fyld-device-api/devicePropertySetApi/set",
            payload={
                "deviceId": device_id,
                "dpIdValues": [{"type": "", "dpId": dp_id, "value": value}],
            },
        )
