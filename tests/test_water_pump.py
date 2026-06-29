"""Water-pump regression tests.

The saltMachine work generalized the switch platform and refactored the
sensor/number value paths. These guard that existing water-pump entities —
especially the power switch's legacy unique_id — keep working.
"""

from __future__ import annotations

import pytest
from conftest import load_fixture


@pytest.fixture
def water_pump() -> list[dict]:
    return load_fixture("water_pump.json")


def _by_dp(entities: list) -> dict:
    return {e._dp_id: e for e in entities}


def test_power_switch_unique_id_unchanged(setup_entities, water_pump):
    entities, _ = setup_entities("switch", water_pump)
    # Exactly one switch (power, dp 105), and it must keep the bare `_switch`
    # unique_id so existing installs don't lose entity history.
    assert len(entities) == 1
    assert entities[0]._dp_id == "105"
    assert entities[0]._attr_unique_id == f"fairland_{water_pump[0]['id']}_switch"


def test_mode_select_still_created(setup_entities, water_pump):
    entities, _ = setup_entities("select", water_pump)
    # The water pump keeps its dedicated mode-select class (dp 103).
    assert len(entities) == 1
    select = entities[0]
    assert type(select).__name__ == "FairlandWaterPumpModeSelect"
    assert select._attr_unique_id == f"fairland_{water_pump[0]['id']}_mode"
    assert select._attr_current_option is not None


def test_speed_setpoint_number_created(setup_entities, water_pump):
    entities, _ = setup_entities("number", water_pump)
    assert "111" in _by_dp(entities)


def test_current_power_sensor_created(setup_entities, water_pump):
    entities, _ = setup_entities("sensor", water_pump)
    assert _by_dp(entities)["5"]._attr_native_value == 46


def test_no_binary_sensors_for_water_pump(setup_entities, water_pump):
    entities, _ = setup_entities("binary_sensor", water_pump)
    assert entities == []
