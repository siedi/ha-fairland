"""Constants for the Fairland integration."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "fairland"
DEFAULT_SCAN_INTERVAL = 30
ATTRIBUTION = "Data provided by Fairland IOT"

# Regional iGarden cloud servers (extracted from the iGarden app, issue #74).
# An account lives on exactly ONE region, chosen by the app from the phone's
# location at signup — not by the user's country — so the integration finds
# the right server by trying each region at login instead of mapping
# countries to servers. A wrong region answers with code 400000
# ("Account does not exist or password is incorrect").
# Order = detection order. "hk" is last because it is currently (2026-06)
# a DNS alias for api-eu; it stays in the list in case Fairland splits it
# into a real region later.
API_REGIONS = {
    "eu": "https://api-eu.fairlandiot.com",
    "us": "https://api-us.fairlandiot.com",
    "cn": "https://api-cn.fairlandiot.com",
    "hk": "https://api-hk.fairlandiot.com",
}
DEFAULT_API_REGION = "eu"
CONF_API_REGION = "api_region"

# iGarden cloud device category codes. The cloud returns these on every
# device in a courtyard; entity platforms dispatch on them so heat pumps and
# pool pumps (Inverflow Plus and OEM-rebadged variants) don't share dpId maps.
HEAT_PUMP_CATEGORY_CODE = "heatPump"
WATER_PUMP_CATEGORY_CODE = "waterPump"
# Inverter salt chlorinator (Fairland i-Salt and OEM rebrands, issue #80).
# A wholly separate dpId namespace from heat/water pumps.
SALT_MACHINE_CATEGORY_CODE = "saltMachine"
# Multiport valve / sand-filter controller (MPV, issue #80/#81). Again its
# own dpId namespace.
SAND_CYLINDER_CATEGORY_CODE = "sandCylinder"
# Counter-current swim jet (Fairland/iGarden "Swim Jet", productCode
# iupstream1, issue #85). Yet another wholly separate dpId namespace.
POOL_SURFER_CATEGORY_CODE = "poolSurfer"

# Pool-pump flow values (dp 101/106/107/112) are reported in the unit the
# user selects via dp 110, so flow entities derive their unit from it rather
# than hardcoding one.
WATER_PUMP_FLOW_UNIT_DP = "110"
WATER_PUMP_FLOW_UNITS = {0: "m³/h", 1: "L/min", 2: "US gpm", 3: "IMP gpm"}
