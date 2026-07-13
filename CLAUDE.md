# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for Fairland pool heat pumps and pool pumps (Inverflow Plus and OEM rebrands such as Madimack). It connects directly to Fairland's iGarden cloud API (not Tuya) to monitor and control devices.

## Development Commands

```bash
# Install dependencies
scripts/setup

# Run linting (ruff format + ruff check with auto-fix)
scripts/lint

# Run the test suite (no HA install needed; see "Verifying Against Real Devices")
pip install -r requirements-test.txt && pytest tests/
# or, without setup: uvx --python 3.13 pytest tests/

# Run local Home Assistant instance for testing
scripts/develop
```

`scripts/lint` needs `ruff` on PATH; if it is missing, `uvx ruff format custom_components/ && uvx ruff check --fix custom_components/` works without setup. Note CI lints the whole repo (`ruff check .`), so `tests/` must lint clean too.

The `scripts/develop` command creates a `config/` directory and starts Home Assistant with debug logging enabled. The custom component is added to PYTHONPATH automatically.

## Architecture

### Data Flow

1. **FairlandApiClient** (`api.py`) - HTTP client for the iGarden cloud
   - Four regional servers (`API_REGIONS` in `const.py`); an account exists on exactly ONE region, auto-detected by trying each at login (#74)
   - Handles authentication (login with password, token management)
   - Fetches courtyards (device groups) and devices
   - Gets/sets device data points (dps)
   - The cloud allows only one active session per account (server-side, #69)

2. **FairlandDataUpdateCoordinator** (`coordinator.py`) - Polls API at configurable interval (default 30s)
   - Fetches all devices in selected courtyard
   - Updates device status data points for each device

3. **FairlandData** (`data.py`) - Runtime data container attached to config entry
   - Holds client, coordinator, and integration references

4. **Entity Platforms** - Binary Sensor, Climate, Sensor, Switch, Number, Select entities created per device, dispatched on `categoryCode` (`heatPump`, `waterPump`, `saltMachine`, `sandCylinder`).

### Device Data Points (dps)

Devices expose functionality through numbered data points. **The dpId namespace is per `categoryCode`** — e.g. heat-pump dp 108 = Lower Temperature Limit, water-pump dp 108 = Backwash Countdown. Never share dp maps across categories.

Heat pump (`heatPump`): `101` power switch, `102` running/preset mode, `103` current temperature, `106` HVAC mode (0=Auto, 1=Heat, 2=Cool), `107` target temperature, `113` operating status, `138` remote-switch status (enum 0=on/1=off — exposed as an enum sensor, not a bool, so a 0 value isn't read as "off").

Water pump (`waterPump`): `5` current power, `102` running rate, `103` mode enum, `104` backwash duration, `105` power switch, `108` backwash countdown, `109` energy, `111` speed setpoint.

Salt chlorinator (`saltMachine`, #80): `101` salt ppm, `103` power, `108` ORP setpoint, `110` pH setpoint (scale 1), `111`/`112` ORP/pH measured, `102`/`105`/`133` temps (102=pool °C, 133=pool °F, 105=controller), `119` water-quality enum, `122` polarity-reversal interval, `125`/`113` chlorine output target/actual, `132` mode enum, `114`/`115`/`117`/`118`/`154` binary status/alarms. Binary alarm polarity is derived from the dpProperty true/false labels, not guessed.

Multiport valve (`sandCylinder`, #80/#81): `101` water temp (scale 1), `102` pressure (MPa, scale 3 — HA has no MPa unit so it rides as a plain unit string), `105` backwash-trigger pressure (MPa setpoint), `106` mode-switch command enum, `107` current valve position enum, `108`/`109`/`111`/`112`/`113` backwash/protection setpoints, `115`/`116` countdown sensors, `118`/`123`/`125` config/pump selects. Entity names and enum option names are taken verbatim from the firmware's own `nameLanguage`/`propNameLanguage` (en-US) in the diagnostics. Enum labels here are localized (Chinese), so `sandCylinder` selects map by the integer key (`int_to_option`) instead of by label.

Swim jet (`poolSurfer`, productCode `iupstream1`, #85): counter-current swimming machine. Every dp carries a full `nameLanguage`/`dpPropertyNameLanguage` (en-US + de/fr/es/cs) — these (NOT the `dpProperty` raw labels, which are stale here) are the naming source, like `sandCylinder`. `23` speed setpoint (%, rw — "Current rotational speed"), `28`/`29`/`30` per-mode default speed/speed/duration (rw config), `21` "Working mode" select (0=free/timed, 1-4=training 1-4, 5=surf, 6=custom; raw dpProperty labels say "TRAINING_MODE_P*" and are wrong, so it maps by `int_to_option`). The mode is READ from dp21 but writing dp21 alone does nothing — the change must go through the packed raw field `20` "Mode + Status" (two LE uint16s: mode=dp21, status=dp22), so the select writes dp20 = `<mode, running-status>` base64-encoded (running-status 3=free, 13=training/surf/custom; also `AAAIAA==` = timer's status 8). A **Pause** switch also writes dp20, holding the current mode and toggling only the run state between running and suspend (free 3↔4, timer 8↔9, training/surf/custom 13↔14; only the 14 suspend is observed, the rest follow the running+1 pattern). The Power switch on `22`, the Pause switch, and the mode select all write via dp20; `22` "System state machine" — exposed both as a read-only status enum sensor (raw dpProperty labels POWER_OFF_STATUS/FREE_MODE_*) and as the **Power switch** (there is no boolean power dp; the manual + on/off diagnostics confirm power-on runs Free Mode P0, i.e. dp22 0=POWER_OFF ↔ 3=FREE_MODE_RUNNING — the switch writes those enum ints via `enum_on_value`/`enum_off_value`), `2` model enum (SJ230/200/160/100), `4` driver-board fault — exposed both as a binary PROBLEM sensor and as a raw numeric "Fault Code" sensor (it is a 0-65535 code register, 0=OK, not a bool), `42`/`40`/`41` session distance(m,scale2)/duration(s)/intensity(%), `12` motor power (W), `9`/`11` actual/commanded motor speed (rpm), `10` bus voltage (scale1), `8`/`13` motor/bus current (scale2), `6`/`7`/`50`/`51`/`52` internal temps (scale1). Deliberately omitted: firmware-debug dps (RTOS stack sizes `58`-`65`, RCC flags `55`/`56`, ota size `15`, commissioning timers `16`-`18`, device log `57`, wifi level `53`, device clock `24`) and the raw training-program blobs (`20`/`27`/`31`-`38`).

Battery swim jet (`interjetlithium`, productCode `lithiumjetx30p30`, #94): the X-series lithium counter-current jets (X35-P30 … X20-P10, dp `1` model enum) — a wholly separate dp namespace from `poolSurfer`. Full 26-language `nameLanguage` is the naming source, but the `dpProperty` unit strings are Chinese (摄氏度/伏特V/安培A), so units are set in the dp maps. `3` battery %, `10` charging bool, `18`/`19`/`20` battery cell temp (s1)/voltage (s2)/current (s2), `23`/`24` battery fw version/cycle count, `14` actual speed (0-2000, no firmware unit — none applied), `15`/`16`/`17` driver temp/bus voltage/bus current (all s1), `21`/`22` hard/soft boot counters (max 255, kept MEASUREMENT so a wrap can't corrupt statistics). Writable: `4` "Mode Settings" — **no value labels in dpProperty**, so it is a select mapping by int key with labels from the official Swim Jet X user manual (app mode dial: 0/1/2/3/4/E/F): 0=P0 standby, 1-4=P1-P4 flow speeds, 5=PE turbo (5 min), 6=PF surf. PE/PF exceed the dpProperty max of 4 (suspected stale, like the poolSurfer enums) and the whole mapping — plus whether writing dp 4 starts the jet remotely (power is a hardware button; the app has a separate "End") — is **unverified on-device**, tracked in #94. Manual archived at `diagnostics/issue-94-swim-jet-x-manual.pdf`; fault codes are just E0 motor / B0 battery. `7` "Timer Settings" (no firmware unit; seconds confirmed by the hardware timer's 15-90 min options = 0-5400 step 900). There is **no power dp, no running-state dp and no readable fault code** (only the write-only `9` clear-fault); write-only momentary dps (`9`, `13`) and the raw usage report `11` (big-endian uint16 <mode, minutes> pairs — note poolSurfer's dp 20 raw is little-endian) are not exposed.

Swim-jet fault codes (from the user manual §10.2; surfaced on dp `4`). We show dp4's raw integer only — the firmware's encoding is **unverified** (suspected `group<<8 | index`, e.g. E2 02 → 514) and we have no faulted capture, so no code→text map is applied. Add a decoded enum sensor once a faulted diagnostic confirms the encoding. Table for reference: `E0 01` bus voltage abnormal, `E0 02` output overcurrent, `E0 03` output current imbalance, `E0 04` output short-circuit, `E0 05` output phase loss, `E0 06` motor stall, `E0 07` motor dry-run (not submerged), `E1 01` MOSFET over-temp, `E1 02` enclosure over-temp, `E2 01` temp-sensor fault, `E2 02` motor-drive fault, `E2 03` driver-board comms fault (>30s). Non-shutdown throttling states shown on the display as `A1` (MOSFET temp), `A2` (enclosure temp), `A3` (output current).

**dpProperty is the source of truth and firmware-specific** — never hardcode what it provides:
- `scale` (value = raw / 10^scale) differs per device for the same dpId
- enum options differ (e.g. dp 103 mode: 2 modes on some pumps, 3 on others, #77)
- `min`/`max`/`step` and even the `unit` differ (backwash times: seconds on some firmwares, minutes on others)
- Some dps exist in the cloud schema but are never populated by a given firmware (always null) — gate entity creation on `dpValue is not None` where that matters (`require_value` pattern in `sensor.py`, `switch.py`, `binary_sensor.py`)

### Config Flow

User provides iGarden app credentials. Integration fetches available courtyards, user selects one, and all devices in that courtyard become available. Note: the flow stores a device-list snapshot in `entry.data["devices"]` that nothing reads afterwards (excluded from diagnostics).

## Verifying Against Real Devices

The maintainer owns a heat pump but no water pump (and no salt chlorinator) — those changes are verified with diagnostics JSONs that users attach to issues. In those files, live device state is under the top-level `devices` key (coordinator data); `entry_data` is config only.

**Test suite (`tests/`)** runs without an HA install: `tests/conftest.py` stubs `homeassistant.*` in `sys.modules` and loads each platform (including `climate`) via `importlib`, then feeds real device dicts. One fixture per category (`heat_pump`, `water_pump`, `salt_machine`, `sand_cylinder`). Tests assert which entities are created and how values/units/scales/polarity come out — the exact bug classes that have bitten this project. The stubs are intentionally permissive, so they verify dp mapping but cannot catch misuse of the real HA entity API. Sanitized, anonymized fixtures live in `tests/fixtures/*.json` (one device per category). When a new firmware or category shows up, add a sanitized fixture and a test.

**Local diagnostics archive (`diagnostics/`)** holds the raw user-attached JSONs for reference when investigating. It is gitignored (PII + size) and never committed — only its `README.md` and the naming convention are. To turn a raw dump into a committed fixture, strip it to one device with just the per-dp `dpId`/`dpValue`/`dpProperty`/`dpMode`/`dpType` fields and anonymize `id`/`deviceName`.

## Release Process

1. Land the change commits, make sure CI (Lint + Validate) is green
2. Bump `manifest.json` version in its own `chore: bump version to X.Y.Z` commit, push, wait for CI
3. `gh release create vX.Y.Z --target main --title vX.Y.Z --notes ...` — notes style: short prose intro explaining the problem, bolded `**Fixed:**`/`**New:**` bullets, thanks to the reporting user, `Full Changelog` compare link
4. Changes outside `custom_components/` (workflows, docs, dev tooling) don't need a release

## Code Style

Uses `ruff` for formatting and linting. Run `scripts/lint` before commits.
