"""Presentation helpers for device alarm records (issue #102).

Shared by the Latest Alarm sensor and the Alarm event entity. Records come
from FairlandApiClient.get_device_alarms, already stripped and sorted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def alarm_text(value: Any) -> str | None:
    """Pick the English text out of an alarm record's language dict."""
    if not isinstance(value, dict):
        return value if isinstance(value, str) and value else None
    if value.get("en-US"):
        return value["en-US"]
    return next((text for text in value.values() if text), None)


def alarm_time(epoch_ms: Any) -> str | None:
    """Convert an alarm record's epoch-milliseconds timestamp to ISO 8601."""
    try:
        return datetime.fromtimestamp(int(epoch_ms) / 1000, tz=UTC).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def alarm_summary(record: dict[str, Any]) -> dict[str, Any]:
    """Condense an alarm record to the fields shown in HA."""
    clear_status = record.get("clearStatus")
    return {
        "code": record.get("code") or record.get("showInfo"),
        # Heat pumps leave the name empty and put the meaning into reason
        # (E3 = "No water protection"); chlorinators fill both (#102).
        "description": alarm_text(record.get("name"))
        or alarm_text(record.get("reason")),
        "created": alarm_time(record.get("createTime")),
        "cleared": None if clear_status is None else clear_status == 1,
        "cleared_at": alarm_time(record.get("clearTime")),
    }


def alarm_details(record: dict[str, Any]) -> dict[str, Any]:
    """Return the full set of fields shown for one alarm."""
    return {
        **alarm_summary(record),
        "level": record.get("level"),
        "reason": alarm_text(record.get("reason")),
        "solution": alarm_text(record.get("solution")),
    }


def alarm_key(record: dict[str, Any]) -> tuple[Any, Any]:
    """Identify an alarm record (the stripped records carry no id)."""
    return (record.get("createTime"), record.get("code"))
