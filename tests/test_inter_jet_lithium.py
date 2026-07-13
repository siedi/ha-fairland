"""interjetlithium (battery swim jet X-series) tests, issue #94.

Fed by tests/fixtures/inter_jet_lithium.json — a sanitized capture of a real
Swim Jet X30-P30 (productCode lithiumjetx30p30). The device was idle at
capture time (speed 0, mode 0, not charging), so the scaling assertions lean
on the battery/temperature telemetry, which carries real non-zero state.
Entity names come from the firmware's own nameLanguage (en-US); its
dpProperty unit strings are Chinese, so units are set in the dp maps.

The firmware exposes no power dp, no running-state dp and no labels for the
dp 4 mode values, so the only controls are the two plain numbers asserted
below (see #94 for the pending mode/power semantics).
"""

from __future__ import annotations

import asyncio

import pytest
from conftest import load_fixture


@pytest.fixture
def jet_devices() -> list[dict]:
    return load_fixture("inter_jet_lithium.json")


def _by_dp(entities: list) -> dict:
    return {e._dp_id: e for e in entities if hasattr(e, "_dp_id")}


# --------------------------------------------------------------------------
# Sensors
# --------------------------------------------------------------------------
def test_sensor_dps_created(setup_entities, jet_devices):
    entities, _ = setup_entities("sensor", jet_devices)
    assert set(_by_dp(entities)) == {
        "1",
        "3",
        "14",
        "15",
        "16",
        "17",
        "18",
        "19",
        "20",
        "21",
        "22",
        "23",
        "24",
    }


def test_battery_level(setup_entities, jet_devices):
    # dp 3 = 33 (scale 0) → 33 %, the primary reading.
    dps = _by_dp(setup_entities("sensor", jet_devices)[0])
    assert dps["3"]._attr_native_value == 33
    assert dps["3"]._attr_native_unit_of_measurement == "%"
    assert dps["3"]._attr_entity_category is None


def test_model_enum_label(setup_entities, jet_devices):
    # dp 1 = 1 → "X30-P30" from the dpProperty enum labels.
    dps = _by_dp(setup_entities("sensor", jet_devices)[0])
    assert dps["1"]._attr_native_value == "X30-P30"


def test_battery_voltage_scaled(setup_entities, jet_devices):
    # dp 19 = 2504 (scale 2) → 25.04 V.
    dps = _by_dp(setup_entities("sensor", jet_devices)[0])
    assert dps["19"]._attr_native_value == pytest.approx(25.04)
    assert dps["19"]._attr_native_unit_of_measurement == "VOLT"


def test_cell_temperature_scaled(setup_entities, jet_devices):
    # dp 18 = 381 (scale 1) → 38.1 °C; dp 15 = 279 → 27.9 °C.
    dps = _by_dp(setup_entities("sensor", jet_devices)[0])
    assert dps["18"]._attr_native_value == pytest.approx(38.1)
    assert dps["15"]._attr_native_value == pytest.approx(27.9)
    assert dps["18"]._attr_entity_category == "DIAGNOSTIC"


def test_string_typed_scale_property(setup_entities, jet_devices):
    # dp 23/24 carry scale as the string "0" in dpProperty on this firmware;
    # the values must come through unscaled.
    dps = _by_dp(setup_entities("sensor", jet_devices)[0])
    assert dps["23"]._attr_native_value == 34
    assert dps["24"]._attr_native_value == 2


def test_actual_speed_has_no_unit(setup_entities, jet_devices):
    # dp 14 carries no firmware unit, so none is invented.
    dps = _by_dp(setup_entities("sensor", jet_devices)[0])
    assert dps["14"]._attr_native_unit_of_measurement is None
    assert dps["14"]._attr_native_value == 0


# --------------------------------------------------------------------------
# Binary sensor (charging)
# --------------------------------------------------------------------------
def test_charging_created(setup_entities, jet_devices):
    entities, _ = setup_entities("binary_sensor", jet_devices)
    bs = _by_dp(entities)
    assert set(bs) == {"10"}
    # Captured while not charging; a firmware bool, not inverted.
    assert bs["10"].is_on is False


# --------------------------------------------------------------------------
# Number (timer, the only other writable dp)
# --------------------------------------------------------------------------
def test_numbers_created(setup_entities, jet_devices):
    entities, _ = setup_entities("number", jet_devices)
    assert set(_by_dp(entities)) == {"7"}


def test_timer_range_from_property(setup_entities, jet_devices):
    # dp 7: 0 .. 5400 in 900 steps — matching the hardware timer button's
    # 15-90 min options, which is what pins the unit to seconds.
    num = _by_dp(setup_entities("number", jet_devices)[0])["7"]
    assert num._attr_native_min_value == pytest.approx(0)
    assert num._attr_native_max_value == pytest.approx(5400)
    assert num._attr_native_step == pytest.approx(900)
    assert num._attr_native_unit_of_measurement == "SECONDS"


# --------------------------------------------------------------------------
# Select (mode)
# --------------------------------------------------------------------------
def test_selects_created(setup_entities, jet_devices):
    entities, _ = setup_entities("select", jet_devices)
    assert set(_by_dp(entities)) == {"4"}


def test_mode_options_by_int_key(setup_entities, jet_devices):
    # dp 4's dpProperty carries no value labels, so options come from the
    # int-key map (P0-P4/PE/PF per the user manual, unverified — #94). The
    # value-type dpProperty (min/max/step keys) must not filter them out.
    mode = _by_dp(setup_entities("select", jet_devices)[0])["4"]
    assert mode._attr_options == [
        "p0_standby",
        "p1",
        "p2",
        "p3",
        "p4",
        "pe_turbo",
        "pf_surf",
    ]
    # Captured idle → 0 → P0 standby.
    assert mode._attr_current_option == "p0_standby"


def test_mode_write_sends_int(setup_entities, jet_devices):
    # Unlike the poolSurfer mode (packed dp 20), this mode writes its integer
    # straight to dp 4.
    entities, client = setup_entities("select", jet_devices)
    asyncio.run(_by_dp(entities)["4"].async_select_option("p2"))
    assert client.calls == [(jet_devices[0]["id"], "4", 2)]
