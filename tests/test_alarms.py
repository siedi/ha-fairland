"""Device alarm tests (issue #102): alarmStatus flag + cloud alarm history.

Records are modeled on real deviceAlarmPage responses: the heat-pump E3 on
the maintainer's own heat pump (name empty, meaning in reason) and the
chlorinator A3/E3 sequence from #102 (name filled, returned out of order).
"""

from __future__ import annotations

import asyncio
import copy
import sys

import pytest
from conftest import load_fixture

api = sys.modules["fairland.api"]
coordinator_mod = sys.modules["fairland.coordinator"]

DEVICE_ID = "device-1"
NO_NAME = {"de": None, "en-US": None, "zh-CN": None}

HEAT_PUMP_E3 = {
    "id": "r1",
    "deviceId": DEVICE_ID,
    "sn": "SECRET-SN",
    "picture": "https://example.invalid/pic.png",
    "code": "E3",
    "level": "WARN",
    "name": NO_NAME,
    "showInfo": "E3",
    "reason": {"de": "Wassermangelschutz", "en-US": "No water protection"},
    "solution": {"en-US": "Check whether water flow is normal."},
    "clearStatus": 1,
    "createTime": 1791120361000,
    "clearTime": 1791120363000,
}


def _chlorinator_record(code, name, created_ms, cleared_ms, device_id=DEVICE_ID):
    return {
        "deviceId": device_id,
        "code": code,
        "level": "WARN",
        "name": {"en-US": name, "zh-CN": "x"},
        "reason": {"en-US": f"{name} reason"},
        "solution": {"en-US": f"{name} solution"},
        "clearStatus": 1,
        "createTime": created_ms,
        "clearTime": cleared_ms,
    }


# #102: E3 listed before the newer A3.
CHLORINATOR_PAGE = {
    "records": [
        _chlorinator_record("A3", "Air in cell", 1000, 2000),
        _chlorinator_record("E3", "Air in cell Protection", 5000, 9000),
        _chlorinator_record("A3", "Air in cell", 9500, 9800),
        _chlorinator_record("A3", "Air in cell", 3000, 4000),
        _chlorinator_record("Z9", "Other device", 99999, 99999, device_id="other"),
    ],
    "total": "5",
    "size": "10",
    "current": "1",
}


# --------------------------------------------------------------------------
# Parsing the deviceAlarmPage response
# --------------------------------------------------------------------------
def test_records_sorted_newest_first_and_filtered_by_device():
    records = api._alarms_from_page_response(CHLORINATOR_PAGE, DEVICE_ID)
    assert [r["createTime"] for r in records] == [9500, 5000, 3000, 1000]


def test_records_drop_pii_fields():
    (record,) = api._alarms_from_page_response({"records": [HEAT_PUMP_E3]}, DEVICE_ID)
    assert "sn" not in record
    assert "picture" not in record
    assert record["code"] == "E3"


def test_empty_history_is_an_empty_list():
    assert api._alarms_from_page_response({"records": []}, DEVICE_ID) == []


@pytest.mark.parametrize("data", [None, [], "x", {}, {"records": None}])
def test_unusable_response_is_none(data):
    assert api._alarms_from_page_response(data, DEVICE_ID) is None


# --------------------------------------------------------------------------
# Alarm binary sensor (alarmStatus)
# --------------------------------------------------------------------------
def _device(**extra):
    device = copy.deepcopy(load_fixture("heat_pump.json")[0])
    device["id"] = DEVICE_ID
    device.update(extra)
    return device


def _alarm_entity(entities, cls_name):
    matches = [e for e in entities if type(e).__name__ == cls_name]
    assert len(matches) <= 1
    return matches[0] if matches else None


def test_alarm_binary_sensor_not_created_without_flag(setup_entities):
    entities, _ = setup_entities("binary_sensor", [_device()])
    assert _alarm_entity(entities, "FairlandAlarmBinarySensor") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0, False), (1, True), ("1", True), ("0", False), (None, None), (7, None)],
)
def test_alarm_binary_sensor_state(setup_entities, raw, expected):
    entities, _ = setup_entities("binary_sensor", [_device(alarmStatus=raw)])
    sensor = _alarm_entity(entities, "FairlandAlarmBinarySensor")
    assert sensor._attr_name == "Alarm"
    assert sensor._attr_device_class == "PROBLEM"
    assert sensor.is_on is expected


def test_alarm_binary_sensor_follows_coordinator(setup_entities):
    # 0 → 1 → 1 → 0 cycle from the #102 captures.
    device = _device(alarmStatus=0)
    entities, _ = setup_entities("binary_sensor", [device])
    sensor = _alarm_entity(entities, "FairlandAlarmBinarySensor")
    states = []
    for raw in (0, 1, 1, 0):
        device["alarmStatus"] = raw
        states.append(sensor.is_on)
    assert states == [False, True, True, False]


def test_alarm_binary_sensor_unavailable_on_update_failure(setup_entities):
    entities, _ = setup_entities("binary_sensor", [_device(alarmStatus=1)])
    sensor = _alarm_entity(entities, "FairlandAlarmBinarySensor")
    sensor.coordinator.last_update_success = False
    assert sensor.available is False


# --------------------------------------------------------------------------
# Latest Alarm sensor (history)
# --------------------------------------------------------------------------
def _latest(setup_entities, alarms):
    entities, _ = setup_entities("sensor", [_device(alarms=alarms)])
    return _alarm_entity(entities, "FairlandLatestAlarmSensor")


def test_latest_alarm_not_created_without_history_key(setup_entities):
    entities, _ = setup_entities("sensor", [_device()])
    assert _alarm_entity(entities, "FairlandLatestAlarmSensor") is None


def test_latest_alarm_unavailable_when_history_failed(setup_entities):
    sensor = _latest(setup_entities, None)
    assert sensor is not None
    assert sensor.available is False


def test_latest_alarm_empty_history(setup_entities):
    sensor = _latest(setup_entities, [])
    assert sensor.available is True
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


def test_latest_alarm_heat_pump_uses_reason_when_name_empty(setup_entities):
    records = api._alarms_from_page_response({"records": [HEAT_PUMP_E3]}, DEVICE_ID)
    sensor = _latest(setup_entities, records)
    attrs = sensor.extra_state_attributes
    assert sensor.native_value == "E3"
    assert attrs["description"] == "No water protection"
    assert attrs["solution"] == "Check whether water flow is normal."
    assert attrs["cleared"] is True
    assert attrs["created"] == "2026-10-04T13:26:01+00:00"
    assert attrs["cleared_at"] == "2026-10-04T13:26:03+00:00"


def test_latest_alarm_chlorinator_newest_first(setup_entities):
    records = api._alarms_from_page_response(CHLORINATOR_PAGE, DEVICE_ID)
    sensor = _latest(setup_entities, records)
    attrs = sensor.extra_state_attributes
    # Newest is the cleared A3 after the E3, not the E3 listed first.
    assert sensor.native_value == "A3"
    assert attrs["description"] == "Air in cell"
    assert [h["code"] for h in attrs["history"]] == ["A3", "E3", "A3", "A3"]
    assert attrs["history"][1]["description"] == "Air in cell Protection"


# --------------------------------------------------------------------------
# Coordinator: a failing alarm endpoint must not drop telemetry
# --------------------------------------------------------------------------
class _Client:
    def __init__(self, alarm_error=None):
        self.alarm_error = alarm_error

    async def get_all_devices_in_courtyard(self, courtyard_id):
        return [{"id": DEVICE_ID, "alarmStatus": 0}]

    async def get_device_status(self, device_id):
        return [{"dpId": "103", "dpValue": 25}]

    async def get_device_alarms(self, device_id):
        if self.alarm_error:
            raise self.alarm_error
        return []


def _run_coordinator(client):
    coordinator = coordinator_mod.FairlandDataUpdateCoordinator.__new__(
        coordinator_mod.FairlandDataUpdateCoordinator
    )

    class _Entry:
        data = {"courtyard_id": "c1"}

        class runtime_data:  # noqa: N801
            pass

    _Entry.runtime_data.client = client
    coordinator.config_entry = _Entry
    return asyncio.run(coordinator._async_update_data())


def test_coordinator_attaches_alarm_history():
    (device,) = _run_coordinator(_Client())
    assert device["alarms"] == []
    assert device["dps"] == [{"dpId": "103", "dpValue": 25}]


def test_coordinator_alarm_failure_keeps_telemetry():
    error = api.FairlandApiClientCommunicationError("boom")
    (device,) = _run_coordinator(_Client(alarm_error=error))
    assert device["alarms"] is None
    assert device["dps"] == [{"dpId": "103", "dpValue": 25}]
