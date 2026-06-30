"""poolSurfer (counter-current swim jet) tests, issue #85.

Fed by tests/fixtures/pool_surfer.json — a sanitized capture of a real
Swim Jet (productCode iupstream1). The device was idle at capture time, so
most live values are 0; voltage (dp 10), the model/status enums and the
operating-mode select carry real non-zero state, which is what the scaling
and enum assertions below lean on. Entity names come from the firmware's own
nameLanguage (en-US), as with the sandCylinder category.
"""

from __future__ import annotations

import asyncio

import pytest
from conftest import load_fixture


@pytest.fixture
def swim_jet_devices() -> list[dict]:
    return load_fixture("pool_surfer.json")


def _by_dp(entities: list) -> dict:
    return {e._dp_id: e for e in entities}


# --------------------------------------------------------------------------
# Sensors
# --------------------------------------------------------------------------
def test_sensor_dps_created(setup_entities, swim_jet_devices):
    entities, _ = setup_entities("sensor", swim_jet_devices)
    assert set(_by_dp(entities)) == {
        "2",
        "22",
        "42",
        "40",
        "41",
        "12",
        "9",
        "11",
        "10",
        "13",
        "8",
        "6",
        "7",
        "50",
        "51",
        "52",
    }


def test_voltage_scaled(setup_entities, swim_jet_devices):
    # dp 10 = 243 (scale 1) → 24.3 V.
    dps = _by_dp(setup_entities("sensor", swim_jet_devices)[0])
    assert dps["10"]._attr_native_value == pytest.approx(24.3)
    assert dps["10"]._attr_native_unit_of_measurement == "VOLT"


def test_internal_temperatures_scaled(setup_entities, swim_jet_devices):
    # dp 6/50 are scale 1: 347 → 34.7 °C, 345 → 34.5 °C.
    dps = _by_dp(setup_entities("sensor", swim_jet_devices)[0])
    assert dps["6"]._attr_native_value == pytest.approx(34.7)
    assert dps["50"]._attr_native_value == pytest.approx(34.5)
    assert dps["6"]._attr_entity_category == "DIAGNOSTIC"


def test_distance_unit_and_scale(setup_entities, swim_jet_devices):
    # dp 42 carries the firmware unit "(米)" (meters) with scale 2; the unit
    # comes from our config (METERS), not the Chinese firmware string.
    dps = _by_dp(setup_entities("sensor", swim_jet_devices)[0])
    assert dps["42"]._attr_native_unit_of_measurement == "METERS"
    assert dps["42"]._attr_native_value == pytest.approx(0.0)


def test_model_enum_label(setup_entities, swim_jet_devices):
    # dp 2 = 1 → "SJ200 (1700r)" from the dpProperty enum labels.
    dps = _by_dp(setup_entities("sensor", swim_jet_devices)[0])
    assert dps["2"]._attr_native_value == "SJ200 (1700r)"


def test_status_enum_label(setup_entities, swim_jet_devices):
    # dp 22 = 0 → "POWER_OFF_STATUS" (idle). The enum sensor shows the raw
    # dpProperty labels (the firmware's localized names live separately).
    dps = _by_dp(setup_entities("sensor", swim_jet_devices)[0])
    assert dps["22"]._attr_native_value == "POWER_OFF_STATUS"


# --------------------------------------------------------------------------
# Numbers (speed control + per-mode defaults)
# --------------------------------------------------------------------------
def test_numbers_created(setup_entities, swim_jet_devices):
    entities, _ = setup_entities("number", swim_jet_devices)
    assert set(_by_dp(entities)) == {"23", "28", "29", "30"}


def test_speed_range_from_property(setup_entities, swim_jet_devices):
    # dp 23 = 0 %, range 0 .. 100 from its dpProperty.
    num = _by_dp(setup_entities("number", swim_jet_devices)[0])["23"]
    assert num._attr_native_value == pytest.approx(0)
    assert num._attr_native_min_value == pytest.approx(0)
    assert num._attr_native_max_value == pytest.approx(100)
    assert num._attr_native_unit_of_measurement == "%"


def test_defaults_marked_config(setup_entities, swim_jet_devices):
    dps = _by_dp(setup_entities("number", swim_jet_devices)[0])
    assert dps["28"]._attr_entity_category == "CONFIG"
    assert dps["30"]._attr_entity_category == "CONFIG"
    # The live speed control is a primary entity (no category).
    assert dps["23"]._attr_entity_category is None


def test_speed_write_sends_int(setup_entities, swim_jet_devices):
    entities, client = setup_entities("number", swim_jet_devices)
    asyncio.run(_by_dp(entities)["23"].async_set_native_value(40))
    assert client.calls == [(swim_jet_devices[0]["id"], "23", 40)]


# --------------------------------------------------------------------------
# Select (working mode)
# --------------------------------------------------------------------------
def test_selects_created(setup_entities, swim_jet_devices):
    entities, _ = setup_entities("select", swim_jet_devices)
    assert set(_by_dp(entities)) == {"21"}


def test_mode_options_by_int_key(setup_entities, swim_jet_devices):
    # dp 21's raw dpProperty labels (TRAINING_MODE_P*) are stale, so options
    # come from the int-key map (correct labels live in the translations).
    mode = _by_dp(setup_entities("select", swim_jet_devices)[0])["21"]
    assert mode._attr_options == [
        "free_or_timed",
        "training_1",
        "training_2",
        "training_3",
        "training_4",
        "surf",
        "custom",
    ]
    # Device reports 0 → free/timed mode.
    assert mode._attr_current_option == "free_or_timed"


def test_mode_write_sends_int(setup_entities, swim_jet_devices):
    entities, client = setup_entities("select", swim_jet_devices)
    asyncio.run(_by_dp(entities)["21"].async_select_option("surf"))
    # "surf" maps to firmware int 5.
    assert client.calls == [(swim_jet_devices[0]["id"], "21", 5)]


# --------------------------------------------------------------------------
# Binary sensor (driver board fault)
# --------------------------------------------------------------------------
def test_driver_board_fault_created(setup_entities, swim_jet_devices):
    entities, _ = setup_entities("binary_sensor", swim_jet_devices)
    bs = _by_dp(entities)
    assert set(bs) == {"4"}
    # dp 4 = 0 → no fault, and it is not inverted.
    assert bs["4"].is_on is False


# --------------------------------------------------------------------------
# No switches / climate for this category
# --------------------------------------------------------------------------
def test_no_switches(setup_entities, swim_jet_devices):
    entities, _ = setup_entities("switch", swim_jet_devices)
    assert entities == []
