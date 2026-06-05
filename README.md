# Fairland (iGarden) Integration for Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/siedi/ha-fairland.svg)](https://github.com/siedi/ha-fairland/releases)

This integration enables monitoring and control of Fairland pool heat pumps and pool pumps (Inverflow Plus and OEM-rebadged variants such as Madimack) in Home Assistant, connecting directly to Fairland's iGarden cloud API rather than using Tuya.

## Compatibility

> **Important:** This integration only works with Fairland devices that use the **iGarden app** (and its corresponding firmware/cloud). It is **not compatible** with the Fairland SmartPool app, which is Tuya-based and uses a completely different API.
>
> If your device is paired with the SmartPool app, look into Tuya-based integrations instead (e.g. [LocalTuya](https://github.com/rospogriern/localtuya) or the built-in Tuya integration).

## Known Limitations

> **Single active session per account:** The iGarden cloud only allows one active session per account at a time. While the Home Assistant integration is connected, the iGarden mobile app will show your device as "offline" and cannot control it — and vice versa. This is enforced server-side; no header or client-fingerprint trick defeats it.
>
> **Recommended workaround:** Create a second iGarden account (different email) and use the iGarden app to *share* your device from the primary account to the second one. Then configure the Home Assistant integration with the second account's credentials. HA and your phone will use independent sessions and stop kicking each other out. See [#69](https://github.com/siedi/ha-fairland/issues/69) for the full context.

## Supported Devices

* Fairland pool heat pumps on the iGarden platform
* Fairland Inverflow Plus pool pumps on the iGarden platform
* OEM-rebadged variants of the above — Madimack pool pumps (e.g. Inverflow Plus 1.5hp) are Fairland OEM rebrands and run on the same iGarden cloud, so they are supported as well

## Features

* Monitor operational parameters of your Fairland device
* Control settings directly from Home Assistant
* Support for multiple Fairland heat pump and pool pump models
* Direct cloud API connection to Fairland (not using Tuya)

## Installation

### Option 1: HACS (recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. Go to HACS → Integrations.
3. Click the three dots in the top right corner and select "Custom repositories".
4. Add the URL `https://github.com/siedi/ha-fairland` with category "Integration".
5. Click "Add".
6. Search for "Fairland" and install the integration.
7. Restart Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=siedi&repository=ha-fairland&category=Integration)

### Option 2: Manual Installation

1. Download the contents of this repository.
2. Copy the `custom_components/fairland` directory into the `custom_components` directory of your Home Assistant installation.
3. Restart Home Assistant.

## Configuration

Add the integration through the Home Assistant UI:

1. Go to Settings → Devices & Services → Integrations
2. Click the "+ Add Integration" button
3. Search for "Fairland"
4. Follow the configuration steps

You will need your Fairland app account credentials to set up the integration.

## Supported Entities

The integration creates a range of entities depending on the type of device discovered on your iGarden account.

### For heat pumps

#### Climate Entity
* Heat pump control (on/off, mode, temperature)

#### Sensors
* Current temperature
* Target temperature
* Operating mode
* Energy consumption
* Other operational parameters

#### Switches/Controls
* Power switch
* Mode selection (Heating, Cooling, Auto)
* Additional operational controls, which shouldn't be touched unless you know what you're doing

### For pool pumps

* **Power switch** — turn the pump on/off
* **Speed Setpoint** (number, 30-100%, slider) — target pump speed in Manual Inverter mode
* **Backwash Duration** (number, 0-1440 minutes, configuration) — how long a backwash cycle should run
* **Mode** (select: Manual Inverter / Backwash) — selecting **Backwash** starts a real backwash cycle on the pump
* **Current Power** (sensor, W) — instantaneous power draw
* **Backwash Countdown** (sensor, minutes, diagnostic) — minutes remaining in the active backwash cycle
* **Energy Consumption** (sensor, kWh, `TOTAL_INCREASING`) — cumulative energy, works directly with the Energy Dashboard

## Energy Monitoring

> **Note:** Pool pumps expose `sensor.<device>_energy_consumption` natively (kWh, `TOTAL_INCREASING`) and can be added straight to the Energy Dashboard without the utility_meter / integration recipe below. The recipe in this section is only required for **heat pumps**, which expose instantaneous power (kW) but not cumulative energy.

### Heat pumps: deriving energy from power

To monitor your Fairland heat pump's energy consumption in the Home Assistant Energy Dashboard, you need to create an integration sensor that converts power (kW) to energy (kWh). Follow these steps:

#### Option: Configure via YAML

1. Add the following configuration to your `configuration.yaml`:

```yaml
# Energy monitoring for Fairland heat pump
utility_meter:
  fairland_energy_daily:
    source: sensor.fairland_energy_kwh
    cycle: daily
  fairland_energy_monthly:
    source: sensor.fairland_energy_kwh
    cycle: monthly

sensor:
  - platform: integration
    source: sensor.fairland_power
    name: fairland_energy_kwh
    unit_prefix: k
    round: 2
```
2. Adjust `sensor.fairland_power` to match your actual power sensor entity ID. If you're unsure, go to **Developer Tools > States** and search for "fairland" to find the correct entity ID.

3. Restart Home Assistant to apply the changes.

#### Adding to Energy Dashboard

1. Go to **Settings > Dashboards > Energy**.
2. In the **Electricity grid** section, click **Add Consumption**.
3. Under **Individual devices**, select your `sensor.fairland_energy_kwh` sensor (heat pumps) or `sensor.<device>_energy_consumption` (pool pumps).
4. Click **Save**.

Now your Fairland device's energy consumption will be tracked in the Energy Dashboard!

#### Understanding the Configuration

* The `integration` sensor automatically converts power (kW) to energy (kWh) by integrating the power usage over time.
* `unit_prefix`: k ensures the values are displayed in kilowatt-hours (kWh) instead of watt-hours (Wh).
* The `utility_meter` entities provide daily and monthly consumption statistics.

#### Troubleshooting

If you don't see data in the Energy Dashboard:

* Verify that your power sensor (`sensor.fairland_power`) is providing valid readings
* Check that the integration sensor (`sensor.fairland_energy_kwh`) is working correctly
* Make sure you've selected the correct sensor in the Energy Dashboard configuration

## Troubleshooting

If you experience issues with the integration, first check the Home Assistant logs for entries related to "fairland": **Settings → System → Logs**, then search for `fairland`.

### Login problems during setup

The iGarden cloud runs several regional servers (EU, US, HK, CN) and your account exists on exactly one of them — decided by the app when the account was registered, not necessarily matching your country. The integration tries all regions automatically during setup, so you don't need to configure anything.

If the setup dialog still fails with an authentication or unknown error, the log contains a line like:

```
Login failed: <code> <message>
```

(requires v0.3.3 or newer). Please include this line when opening an issue — the error code tells us exactly what the cloud rejected. Error `400000` on all regions means the credentials really don't match any iGarden account (note: SmartPool app accounts are a different system and not supported).

### Debug logging (integration already set up)

1. Go to **Settings → Devices & Services → Fairland (iGarden)**
2. Open the three-dot menu (⋮) in the top right corner and select **Enable debug logging**
3. Reproduce the problem, then disable debug logging the same way — Home Assistant offers the collected log as a download

> **Note:** The debug logging menu entry only appears if the `logger` integration is loaded. It is part of `default_config:`; if you maintain a manual `configuration.yaml` without `default_config:`, add a `logger:` line and restart.

### Debug logging (setup not possible yet)

The UI toggle requires a configured integration. If you can't get past the setup dialog, enable debug logging via `configuration.yaml` instead:

```yaml
logger:
  default: info
  logs:
    custom_components.fairland: debug
```

Then restart Home Assistant, retry the setup, and check the logs.

### Diagnostics download

For device-related issues (wrong values, missing entities), attach a diagnostics dump to your report: **Settings → Devices & Services → Fairland (iGarden) → three-dot menu (⋮) on the entry → Download diagnostics**. The dump contains your devices' raw data points; credentials, serial numbers, and location data are redacted automatically.

## Development
This custom component is based on integration_blueprint template.

## License
This project is licensed under the MIT License - see the LICENSE file for details.