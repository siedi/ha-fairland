"""Tests for the deviceAllGroupInfo device-list parsing (shared devices, #92).

The cloud returns a courtyard's devices in two lists: ``bindDeviceInfos``
(owned) and ``shareDeviceInfos`` (shared to this account). The integration must
surface both, otherwise an account that only has a device shared to it sees no
devices and no entities.
"""

from __future__ import annotations

import sys

# api.py is loaded as ``fairland.api`` by conftest's _load_integration().
api = sys.modules["fairland.api"]
merge = api._devices_from_group_response


def test_owned_only():
    data = {"bindDeviceInfos": [{"id": "a"}], "shareDeviceInfos": []}
    assert merge(data) == [{"id": "a"}]


def test_shared_only():
    # This is the #92 case: nothing owned, one device shared in.
    data = {
        "bindDeviceInfos": [],
        "shareDeviceInfos": [{"id": "s", "categoryCode": "heatPump"}],
    }
    assert merge(data) == [{"id": "s", "categoryCode": "heatPump"}]


def test_owned_and_shared_are_combined():
    data = {
        "bindDeviceInfos": [{"id": "a"}],
        "shareDeviceInfos": [{"id": "s"}],
    }
    assert merge(data) == [{"id": "a"}, {"id": "s"}]


def test_missing_or_null_keys_are_tolerated():
    # A firmware/account may omit a key or return null instead of [].
    assert merge({}) == []
    assert merge({"bindDeviceInfos": None, "shareDeviceInfos": None}) == []
    assert merge({"bindDeviceInfos": [{"id": "a"}]}) == [{"id": "a"}]
