"""saltMachine (inverter salt chlorinator) entity creation tests, issue #80.

Fed by tests/fixtures/salt_machine.json — a sanitized capture of a real
device's data points from a user-attached diagnostics report.
"""

from __future__ import annotations

import asyncio

import pytest
from conftest import load_fixture


@pytest.fixture
def salt_devices() -> list[dict]:
    return load_fixture("salt_machine.json")


def _by_dp(entities: list) -> dict:
    return {e._dp_id: e for e in entities}


# --------------------------------------------------------------------------
# Sensors
# --------------------------------------------------------------------------
def test_sensor_dps_created(setup_entities, salt_devices):
    entities, _ = setup_entities("sensor", salt_devices)
    dps = _by_dp(entities)
    expected = {
        "101",
        "112",
        "111",
        "102",
        "133",
        "105",
        "113",
        "124",
        "106",
        "130",
        "145",
        "119",
        "127",
        "128",
    }
    assert set(dps) == expected


def test_sensor_ph_is_scaled(setup_entities, salt_devices):
    # dp 112 reports 69 with scale=1 → 6.9
    entities, _ = setup_entities("sensor", salt_devices)
    assert _by_dp(entities)["112"]._attr_native_value == pytest.approx(6.9)


def test_sensor_pool_temp_celsius_and_fahrenheit(setup_entities, salt_devices):
    dps = _by_dp(setup_entities("sensor", salt_devices)[0])
    # dp 102 = 150 (scale 1) → 15.0 °C ; dp 133 = 590 (scale 1) → 59.0 °F
    assert dps["102"]._attr_native_value == pytest.approx(15.0)
    assert dps["133"]._attr_native_value == pytest.approx(59.0)


def test_sensor_enum_maps_to_label(setup_entities, salt_devices):
    dps = _by_dp(setup_entities("sensor", salt_devices)[0])
    # dp 119 reports 0 → "WAIT" from its dpProperty enum.
    assert dps["119"]._attr_native_value == "WAIT"
    assert dps["119"]._attr_options == ["WAIT", "GOOD", "GREAT"]
    # dp 128 is a raw display string, shown verbatim.
    assert dps["128"]._attr_native_value == "AAAA"


# --------------------------------------------------------------------------
# Switches
# --------------------------------------------------------------------------
def test_switches_created_and_backwash_gated(setup_entities, salt_devices):
    entities, _ = setup_entities("switch", salt_devices)
    # dp 153 (backwash) is null on this firmware → skipped by require_value.
    assert set(_by_dp(entities)) == {"103", "107", "121", "123"}


def test_power_switch_keeps_legacy_unique_id(setup_entities, salt_devices):
    entities, _ = setup_entities("switch", salt_devices)
    power = _by_dp(entities)["103"]
    device_id = salt_devices[0]["id"]
    assert power._attr_unique_id == f"fairland_{device_id}_switch"


def test_switch_write_records_call(setup_entities, salt_devices):
    entities, client = setup_entities("switch", salt_devices)
    turbo = _by_dp(entities)["107"]
    asyncio.run(turbo.async_turn_on())
    assert client.calls == [(salt_devices[0]["id"], "107", True)]


# --------------------------------------------------------------------------
# Selects
# --------------------------------------------------------------------------
def test_selects_created(setup_entities, salt_devices):
    entities, _ = setup_entities("select", salt_devices)
    dps = _by_dp(entities)
    assert set(dps) == {"132", "122"}
    # dp 132 reports 0 → "inverter"; full option set parsed from dpProperty.
    assert dps["132"]._attr_current_option == "inverter"
    assert dps["132"]._attr_options == ["inverter", "auto_ph", "manual"]
    # dp 122 reports 1 → the "4 hours" option.
    assert dps["122"]._attr_current_option == "4_hours"


def test_select_write_records_int(setup_entities, salt_devices):
    entities, client = setup_entities("select", salt_devices)
    asyncio.run(_by_dp(entities)["132"].async_select_option("manual"))
    # "manual" maps to firmware int 3.
    assert client.calls == [(salt_devices[0]["id"], "132", 3)]


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------
def test_numbers_created(setup_entities, salt_devices):
    entities, _ = setup_entities("number", salt_devices)
    assert set(_by_dp(entities)) == {"110", "108", "125", "109", "126"}


def test_ph_setpoint_scaled_range_and_value(setup_entities, salt_devices):
    ph = _by_dp(setup_entities("number", salt_devices)[0])["110"]
    # dpProperty min/max/step (65/85/1, scale 1) → 6.5/8.5/0.1 ; value 74 → 7.4
    assert ph._attr_native_min_value == pytest.approx(6.5)
    assert ph._attr_native_max_value == pytest.approx(8.5)
    assert ph._attr_native_step == pytest.approx(0.1)
    assert ph._attr_native_value == pytest.approx(7.4)


def test_ph_setpoint_write_scales_back_to_raw(setup_entities, salt_devices):
    entities, client = setup_entities("number", salt_devices)
    asyncio.run(_by_dp(entities)["110"].async_set_native_value(7.6))
    # Displayed pH 7.6 must reach the firmware as the raw integer 76.
    assert client.calls == [(salt_devices[0]["id"], "110", 76)]


def test_orp_setpoint_unscaled(setup_entities, salt_devices):
    orp = _by_dp(setup_entities("number", salt_devices)[0])["108"]
    assert orp._attr_native_min_value == pytest.approx(200)
    assert orp._attr_native_max_value == pytest.approx(850)
    assert orp._attr_native_value == pytest.approx(650)


# --------------------------------------------------------------------------
# Binary sensors
# --------------------------------------------------------------------------
def test_binary_sensors_gate_null_dps(setup_entities, salt_devices):
    # On this firmware only the pool cover (154) is populated; the four
    # alarm dps are null → require_value skips them.
    entities, _ = setup_entities("binary_sensor", salt_devices)
    assert set(_by_dp(entities)) == {"154"}
    assert _by_dp(entities)["154"].is_on is False


def _salt_with_dp(dp_id: str, value) -> list[dict]:
    return [
        {
            "id": "1000000000000000009",
            "deviceName": "Synthetic",
            "categoryCode": "saltMachine",
            "version": None,
            "dps": [{"dpId": dp_id, "dpValue": value, "dpType": "bool"}],
        }
    ]


@pytest.mark.parametrize(
    ("flow_value", "expected_problem"),
    # dp 114 true = 有水流 (flow present): the PROBLEM is the *absence* of flow,
    # so the sensor is inverted.
    [(True, False), (False, True)],
)
def test_water_flow_polarity_is_inverted(setup_entities, flow_value, expected_problem):
    entities, _ = setup_entities("binary_sensor", _salt_with_dp("114", flow_value))
    assert entities[0].is_on is expected_problem


@pytest.mark.parametrize(
    ("salt_value", "expected_problem"),
    # dp 117 true = 加盐 (needs salt) — already the problem state, not inverted.
    [(True, True), (False, False)],
)
def test_salt_low_polarity_not_inverted(setup_entities, salt_value, expected_problem):
    entities, _ = setup_entities("binary_sensor", _salt_with_dp("117", salt_value))
    assert entities[0].is_on is expected_problem


@pytest.mark.parametrize(
    ("calibration_value", "expected_problem"),
    # dp 116 true = "Calibration required" — a status, not inverted.
    [(True, True), (False, False)],
)
def test_calibration_required_polarity(
    setup_entities, calibration_value, expected_problem
):
    entities, _ = setup_entities(
        "binary_sensor", _salt_with_dp("116", calibration_value)
    )
    assert entities[0]._attr_name == "Calibration Required"
    assert entities[0].is_on is expected_problem
