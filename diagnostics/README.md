# Local diagnostics archive

Raw diagnostics JSONs that users attach to issues, kept here for reference
when investigating device behavior or adding support for new firmwares and
device categories.

**These files are gitignored and must never be committed** — they contain
account/device data and are large. Only this README is tracked (see the
`diagnostics/*` rule in `.gitignore`).

## Naming convention

```
issue-<NN>-<short-description>.json
```

e.g. `issue-80-salt-chlorinator.json`, `issue-77-pump-mode.json`.

## Reading a dump

Live device state is under the top-level `data.devices` key (coordinator
data). `data.entry_data` is config only. Each device has a `categoryCode`
(`heatPump` / `waterPump` / `saltMachine` / …) and a `dps` list; each dp
carries `dpId`, `dpValue`, `dpProperty` (scale/min/max/unit/enum labels —
the firmware-specific source of truth), `dpMode` (`ro`/`rw`/`wo`) and
`dpType`.

## Probe scripts

Standalone scripts that hit the iGarden cloud API directly (stdlib only, no
Home Assistant) also live here, gitignored like the dumps. They are the fastest
way to answer "what does the API actually return / accept?" without spinning up
HA. Credentials are prompted for, never stored. Two exist from the shared-device
work (#92):

- `fairland_probe_shared.py` — logs in (auto-detecting the region), then dumps
  the full `deviceAllGroupInfo` body per group, including `bindDeviceInfos`
  (owned) vs `shareDeviceInfos` (shared to you), and every device's dp schema.
- `fairland_probe_write.py` — a reversible write test: nudges a numeric dp on a
  shared device by one step, reads it back to confirm propagation, then restores
  it, comparing `set` with and without a shareId.

Use a second account when probing (single active session per account), and do
not poll with HA against the same account at the same time.

## Promoting a dump to a test fixture

When a dump informs a code change, turn it into a small committed fixture so
the behavior is regression-tested (see `tests/` and CLAUDE.md → "Verifying
Against Real Devices"):

1. Pick one representative device from `data.devices`.
2. Keep only `dpId`, `dpValue`, `dpProperty`, `dpMode`, `dpType` per dp.
3. Anonymize `id` and `deviceName`.
4. Write it to `tests/fixtures/<category>.json` and add a test.
