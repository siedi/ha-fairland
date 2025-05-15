# Fairland Pool Heat Pump Integration for Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/siedi/ha-fairland.svg)](https://github.com/siedi/ha-fairland/releases)

This integration enables monitoring and control of Fairland pool heat pumps in Home Assistant, connecting directly to Fairland's cloud API rather than using Tuya.

## Features

* Monitor operational parameters of your heat pump
* Control settings directly from Home Assistant
* Support for multiple Fairland heat pump models
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

The integration creates various entities to monitor and control your Fairland heat pump:

### Climate Entity
* Heat pump control (on/off, mode, temperature)

### Sensors
* Current temperature
* Target temperature
* Operating mode
* Energy consumption
* Other operational parameters

### Switches/Controls
* Power switch
* Mode selection (Heating, Cooling, Auto)
* Additional operational controls, which shouldn't be touched unless you know what you're doing

## Energy Monitoring Setup for Fairland Integration

To monitor your Fairland heat pump's energy consumption in the Home Assistant Energy Dashboard, you need to create an integration sensor that converts power (kW) to energy (kWh). Follow these steps:

### Option: Configure via YAML

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

### Adding to Energy Dashboard

1. Go to **Settings > Dashboards > Energy**.
2. In the **Electricity grid** section, click **Add Consumption**.
3. Under **Individual devices**, select your `sensor.fairland_energy_kwh` sensor.
4. Click **Save**.

Now your Fairland heat pump's energy consumption will be tracked in the Energy Dashboard!

### Understanding the Configuration

* The `integration` sensor automatically converts power (kW) to energy (kWh) by integrating the power usage over time.
* `unit_prefix`: k ensures the values are displayed in kilowatt-hours (kWh) instead of watt-hours (Wh).
* The `utility_meter` entities provide daily and monthly consumption statistics.

### Troubleshooting

If you don't see data in the Energy Dashboard:

* Verify that your power sensor (`sensor.fairland_power`) is providing valid readings
* Check that the integration sensor (`sensor.fairland_energy_kwh`) is working correctly
* Make sure you've selected the correct sensor in the Energy Dashboard configuration

## Troubleshooting

If you experience issues with the integration, please check the Home Assistant logs for entries related to "fairland".

For detailed debugging:
1. Enable debug logging by adding the following to your `configuration.yaml`:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.fairland: debug
2. Restart Home Assistant
3. Check the logs for detailed information

## Development
This custom component is based on integration_blueprint template.

## License
This project is licensed under the MIT License - see the LICENSE file for details.