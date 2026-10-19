"""saltMachine VSP pump control (dp 146) tests, issue #107.

dp 146 "VSP device control" packs two bytes, base64-encoded: byte 0 = VSP
toggle, byte 1 = speed index (0 OFF, 1 SP1, 2 SP2, 3 SP3). Decoded from the
#107 diagnostics; tests/fixtures/salt_machine_tt_pure.json is the "on, SP2"
capture (``AQI=``), the #80 fixture reports ``AQE=`` (on, SP1).
"""

from __future__ import annotations

import asyncio
import copy

import pytest
from conftest import load_fixture


@pytest.fixture
def tt_pure_devices() -> list[dict]:
    return load_fixture("salt_machine_tt_pure.json")


def _vsp(entities: list):
    return next(e for e in entities if getattr(e, "_dp_id", None) == "146")


def _with_vsp(devices: list[dict], value) -> list[dict]:
    devices = copy.deepcopy(devices)
    for dp in devices[0]["dps"]:
        if dp["dpId"] == "146":
            dp["dpValue"] = value
    return devices


@pytest.mark.parametrize(
    ("raw", "is_on", "speed"),
    [
        ("AQI=", True, "sp2"),  # #107: toggle on, SP2
        ("AQA=", True, "off"),  # #107: toggle on, speed OFF
        ("AAA=", False, "off"),  # #107: toggle off
        ("AQE=", True, "sp1"),  # #80/#81 units
    ],
)
def test_vsp_decodes_both_bytes(setup_entities, tt_pure_devices, raw, is_on, speed):
    devices = _with_vsp(tt_pure_devices, raw)
    switch = _vsp(setup_entities("switch", devices)[0])
    select = _vsp(setup_entities("select", devices)[0])
    assert switch.is_on is is_on
    assert select.current_option == speed
    assert select._attr_options == ["off", "sp1", "sp2", "sp3"]


def test_vsp_names_and_unique_ids(setup_entities, tt_pure_devices):
    device_id = tt_pure_devices[0]["id"]
    switch = _vsp(setup_entities("switch", tt_pure_devices)[0])
    select = _vsp(setup_entities("select", tt_pure_devices)[0])
    assert switch._attr_name == "VSP Control"
    assert switch._attr_unique_id == f"fairland_{device_id}_switch_vsp"
    assert select._attr_translation_key == "salt_vsp_speed"
    assert select._attr_unique_id == f"fairland_{device_id}_select_vsp_speed"


@pytest.mark.parametrize("raw", [None, "", "AQ==", "AQID", "not base64!"])
def test_vsp_skipped_when_not_two_bytes(setup_entities, tt_pure_devices, raw):
    devices = _with_vsp(tt_pure_devices, raw)
    for platform in ("switch", "select"):
        entities, _ = setup_entities(platform, devices)
        assert all(getattr(e, "_dp_id", None) != "146" for e in entities)


def test_switch_off_keeps_speed(setup_entities, tt_pure_devices):
    entities, client = setup_entities("switch", tt_pure_devices)
    asyncio.run(_vsp(entities).async_turn_off())
    # [1, 2] -> [0, 2]
    assert client.calls == [(tt_pure_devices[0]["id"], "146", "AAI=")]


def test_select_speed_keeps_toggle(setup_entities, tt_pure_devices):
    entities, client = setup_entities("select", tt_pure_devices)
    asyncio.run(_vsp(entities).async_select_option("sp3"))
    # [1, 2] -> [1, 3]
    assert client.calls == [(tt_pure_devices[0]["id"], "146", "AQM=")]
    assert _vsp(entities).current_option == "sp3"


def test_select_unknown_option_not_written(setup_entities, tt_pure_devices):
    entities, client = setup_entities("select", tt_pure_devices)
    asyncio.run(_vsp(entities).async_select_option("sp9"))
    assert client.calls == []


def test_switch_and_select_share_pending_write(platforms, tt_pure_devices):
    # Toggle off, then set a speed before the cloud reports back: the select
    # must build on the pending [0, 2], not the stale polled [1, 2].
    from conftest import FakeClient, _FakeCoordinator, _FakeEntry

    client = FakeClient()
    coordinator = _FakeCoordinator(tt_pure_devices, client)
    entry = _FakeEntry(coordinator, client)
    collected: list = []
    for name in ("switch", "select"):
        asyncio.run(
            platforms[name].async_setup_entry(
                None, entry, lambda ents, *a, **k: collected.extend(ents)
            )
        )
    switch, select = (e for e in collected if getattr(e, "_dp_id", None) == "146")
    asyncio.run(switch.async_turn_off())
    asyncio.run(select.async_select_option("sp1"))
    device_id = tt_pure_devices[0]["id"]
    assert client.calls == [
        (device_id, "146", "AAI="),
        (device_id, "146", "AAE="),
    ]
    assert switch.is_on is False
    assert select.current_option == "sp1"
