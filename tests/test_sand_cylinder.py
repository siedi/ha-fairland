"""sandCylinder (multiport valve / sand-filter controller) tests, #80/#81.

Fed by tests/fixtures/sand_cylinder.json — a sanitized capture of a real
MPV device's data points.
"""

from __future__ import annotations

import asyncio

import pytest
from conftest import load_fixture


@pytest.fixture
def mpv_devices() -> list[dict]:
    return load_fixture("sand_cylinder.json")


def _by_dp(entities: list) -> dict:
    return {e._dp_id: e for e in entities}


# --------------------------------------------------------------------------
# Sensors
# --------------------------------------------------------------------------
def test_sensor_dps_created(setup_entities, mpv_devices):
    entities, _ = setup_entities("sensor", mpv_devices)
    assert set(_by_dp(entities)) == {"101", "102", "107", "115", "116"}


def test_water_temperature_scaled(setup_entities, mpv_devices):
    # dp 101 = 141 (scale 1) → 14.1 °C
    dps = _by_dp(setup_entities("sensor", mpv_devices)[0])
    assert dps["101"]._attr_native_value == pytest.approx(14.1)


def test_pressure_scaled_to_mpa(setup_entities, mpv_devices):
    # dp 102 = 17 (scale 3) → 0.017 MPa, reported with a plain MPa unit.
    dps = _by_dp(setup_entities("sensor", mpv_devices)[0])
    assert dps["102"]._attr_native_value == pytest.approx(0.017)
    assert dps["102"]._attr_native_unit_of_measurement == "MPa"


def test_valve_position_enum_label(setup_entities, mpv_devices):
    # dp 107 = 6 → "FILTER" (English labels live in the dpProperty).
    dps = _by_dp(setup_entities("sensor", mpv_devices)[0])
    assert dps["107"]._attr_native_value == "FILTER"
    assert {"Backwash", "FILTER", "CLOSED"} <= set(dps["107"]._attr_options)


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------
def test_numbers_created(setup_entities, mpv_devices):
    entities, _ = setup_entities("number", mpv_devices)
    assert set(_by_dp(entities)) == {"105", "108", "109", "111", "112", "113"}


def test_trigger_pressure_scaled(setup_entities, mpv_devices):
    # dp 105 = 200 (scale 3) → 0.200 MPa; range 0 .. 2.5.
    num = _by_dp(setup_entities("number", mpv_devices)[0])["105"]
    assert num._attr_native_value == pytest.approx(0.200)
    assert num._attr_native_min_value == pytest.approx(0)
    assert num._attr_native_max_value == pytest.approx(2.5)


def test_trigger_pressure_write_scales_back(setup_entities, mpv_devices):
    entities, client = setup_entities("number", mpv_devices)
    asyncio.run(_by_dp(entities)["105"].async_set_native_value(0.250))
    # 0.250 MPa must reach the firmware as raw 250.
    assert client.calls == [(mpv_devices[0]["id"], "105", 250)]


# --------------------------------------------------------------------------
# Selects
# --------------------------------------------------------------------------
def test_selects_created(setup_entities, mpv_devices):
    entities, _ = setup_entities("select", mpv_devices)
    assert set(_by_dp(entities)) == {"106", "125", "118", "123"}


def test_mode_switch_options_by_int_key(setup_entities, mpv_devices):
    # dp 106 labels are localized; options come from the int-key map.
    mode = _by_dp(setup_entities("select", mpv_devices)[0])["106"]
    assert mode._attr_options == [
        "no_movement",
        "one_touch_rinse",
        "recirc",
        "closed",
        "filter",
        "waste",
    ]
    # Device reports 0 → "no movement".
    assert mode._attr_current_option == "no_movement"


def test_mode_switch_write_sends_int(setup_entities, mpv_devices):
    entities, client = setup_entities("select", mpv_devices)
    asyncio.run(_by_dp(entities)["106"].async_select_option("filter"))
    # "filter" maps to firmware int 4.
    assert client.calls == [(mpv_devices[0]["id"], "106", 4)]


def test_config_selects_marked_diagnostic_config(setup_entities, mpv_devices):
    dps = _by_dp(setup_entities("select", mpv_devices)[0])
    assert dps["118"]._attr_entity_category == "CONFIG"
    assert dps["123"]._attr_entity_category == "CONFIG"
    # The main mode control is a primary entity (no category).
    assert dps["106"]._attr_entity_category is None


# --------------------------------------------------------------------------
# No binary sensors / switches for this category
# --------------------------------------------------------------------------
def test_no_binary_sensors(setup_entities, mpv_devices):
    entities, _ = setup_entities("binary_sensor", mpv_devices)
    assert entities == []


def test_no_switches(setup_entities, mpv_devices):
    entities, _ = setup_entities("switch", mpv_devices)
    assert entities == []
