"""Water-pump tests.

Cover both the pre-existing entities (regression: the power switch's legacy
unique_id must not change) and the flow gap-filling entities added later
(dp 101/106/107/110/112/114), fed by tests/fixtures/water_pump.json.
"""

from __future__ import annotations

import asyncio

import pytest
from conftest import load_fixture


@pytest.fixture
def water_pump() -> list[dict]:
    return load_fixture("water_pump.json")


def _by_dp(entities: list) -> dict:
    return {e._dp_id: e for e in entities}


# --------------------------------------------------------------------------
# Regression: pre-existing entities
# --------------------------------------------------------------------------
def test_power_switch_unique_id_unchanged(setup_entities, water_pump):
    entities, _ = setup_entities("switch", water_pump)
    # Exactly one switch (power, dp 105), and it must keep the bare `_switch`
    # unique_id so existing installs don't lose entity history.
    assert len(entities) == 1
    assert entities[0]._dp_id == "105"
    assert entities[0]._attr_unique_id == f"fairland_{water_pump[0]['id']}_switch"


def test_mode_select_still_created(setup_entities, water_pump):
    entities, _ = setup_entities("select", water_pump)
    mode = next(
        e for e in entities if type(e).__name__ == "FairlandWaterPumpModeSelect"
    )
    assert mode._attr_unique_id == f"fairland_{water_pump[0]['id']}_mode"
    assert mode._attr_current_option is not None


def test_speed_setpoint_number_created(setup_entities, water_pump):
    entities, _ = setup_entities("number", water_pump)
    assert "111" in _by_dp(entities)


def test_current_power_sensor_created(setup_entities, water_pump):
    entities, _ = setup_entities("sensor", water_pump)
    assert _by_dp(entities)["5"]._attr_native_value == 46


# --------------------------------------------------------------------------
# Flow gap-filling entities
# --------------------------------------------------------------------------
def test_flow_sensors_created(setup_entities, water_pump):
    dps = _by_dp(setup_entities("sensor", water_pump)[0])
    assert {"112", "101", "107"} <= set(dps)
    assert dps["112"]._attr_native_value == 3


def test_flow_sensor_unit_follows_dp110(setup_entities, water_pump):
    # dp 110 = 0 → m³/h.
    dps = _by_dp(setup_entities("sensor", water_pump)[0])
    assert dps["112"]._attr_native_unit_of_measurement == "m³/h"


def test_flow_sensor_unit_switches_with_dp110(setup_entities, water_pump):
    # Flip dp 110 to 1 (L/min) and the flow unit must follow.
    dev = water_pump[0]
    for dp in dev["dps"]:
        if dp["dpId"] == "110":
            dp["dpValue"] = 1
    dps = _by_dp(setup_entities("sensor", [dev])[0])
    assert dps["112"]._attr_native_unit_of_measurement == "L/min"


def test_flow_setpoint_number(setup_entities, water_pump):
    num = _by_dp(setup_entities("number", water_pump)[0])["106"]
    assert num._attr_native_value == 5
    assert num._attr_native_unit_of_measurement == "m³/h"


def test_flow_unit_select(setup_entities, water_pump):
    sel = next(
        e
        for e in setup_entities("select", water_pump)[0]
        if getattr(e, "_dp_id", None) == "110"
    )
    assert sel._attr_options == ["m3h", "l_min", "us_gpm", "imp_gpm"]
    assert sel._attr_current_option == "m3h"
    assert sel._attr_entity_category == "CONFIG"


def test_flow_unit_select_write(setup_entities, water_pump):
    entities, client = setup_entities("select", water_pump)
    sel = next(e for e in entities if getattr(e, "_dp_id", None) == "110")
    asyncio.run(sel.async_select_option("us_gpm"))
    assert client.calls == [(water_pump[0]["id"], "110", 2)]


def test_pressure_alarm_binary_sensor(setup_entities, water_pump):
    # dp 114 = False → Normal → not a problem.
    entities, _ = setup_entities("binary_sensor", water_pump)
    alarm = _by_dp(entities)["114"]
    assert alarm._attr_name == "Pressure Alarm"
    assert alarm.is_on is False
