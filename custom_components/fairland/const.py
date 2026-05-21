"""Constants for the Fairland integration."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "fairland"
DEFAULT_SCAN_INTERVAL = 30
ATTRIBUTION = "Data provided by Fairland IOT"

# iGarden cloud device category codes. The cloud returns these on every
# device in a courtyard; entity platforms dispatch on them so heat pumps and
# pool pumps (Inverflow Plus and OEM-rebadged variants) don't share dpId maps.
HEAT_PUMP_CATEGORY_CODE = "heatPump"
WATER_PUMP_CATEGORY_CODE = "waterPump"
