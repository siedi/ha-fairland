"""Heat-pump tests, fed by tests/fixtures/heat_pump.json (a sanitized
capture of the maintainer's own device — the integration's primary target,
previously without any test coverage)."""

from __future__ import annotations

import pytest
from conftest import load_fixture


@pytest.fixture
def heat_pump() -> list[dict]:
    return load_fixture("heat_pump.json")


def _by_dp(entities: list) -> dict:
    return {e._dp_id: e for e in entities}


# --------------------------------------------------------------------------
# Climate (the headline entity)
# --------------------------------------------------------------------------
def test_single_climate_entity(setup_entities, heat_pump):
    entities, _ = setup_entities("climate", heat_pump)
    assert len(entities) == 1


def test_climate_reads_temperatures_and_mode(setup_entities, heat_pump):
    climate = setup_entities("climate", heat_pump)[0][0]
    # dp 103 inlet temp = 28, dp 107 setting temp = 28, dp 106 = 1 (Heating),
    # power (dp 101) on, dp 102 = 2 (Turbo preset).
    assert climate._attr_current_temperature == 28
    assert climate._attr_target_temperature == 28
    assert climate._attr_hvac_mode == "HEAT"
    assert climate._attr_preset_mode == "Turbo"


# --------------------------------------------------------------------------
# Switch / sensors / numbers
# --------------------------------------------------------------------------
def test_power_switch(setup_entities, heat_pump):
    entities, _ = setup_entities("switch", heat_pump)
    assert len(entities) == 1
    assert entities[0]._dp_id == "101"
    assert entities[0]._attr_unique_id == f"fairland_{heat_pump[0]['id']}_switch"
    assert entities[0].is_on is True


def test_temperature_sensors(setup_entities, heat_pump):
    dps = _by_dp(setup_entities("sensor", heat_pump)[0])
    # dp 129 outlet water temp = 28, dp 130 ambient = 24.
    assert dps["129"]._attr_native_value == 28
    assert dps["130"]._attr_native_value == 24


def test_power_sensor_scaled_to_kw(setup_entities, heat_pump):
    # dp 112 = 281 with scale 3 → 0.281 kW.
    dps = _by_dp(setup_entities("sensor", heat_pump)[0])
    assert dps["112"]._attr_native_value == pytest.approx(0.281)


def test_remote_switch_enum_sensor(setup_entities, heat_pump):
    # dp 138 enum 0=on / 1=off; value 0 → "on" (must NOT coerce to a bool).
    dps = _by_dp(setup_entities("sensor", heat_pump)[0])
    assert dps["138"]._attr_native_value == "on"
    assert dps["138"]._attr_options == ["on", "off"]


def test_writable_numbers_created(setup_entities, heat_pump):
    entities, _ = setup_entities("number", heat_pump)
    assert set(_by_dp(entities)) == {"116", "117", "118", "119", "120", "121"}


# --------------------------------------------------------------------------
# Categories that should produce nothing for a heat pump
# --------------------------------------------------------------------------
def test_no_selects_or_binary_sensors(setup_entities, heat_pump):
    assert setup_entities("select", heat_pump)[0] == []
    assert setup_entities("binary_sensor", heat_pump)[0] == []
