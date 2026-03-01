"""Constants for the Shelly Wall Display X2i RPC integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "shelly_x2i_rpc"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SOURCE_ENTITY_ID = "source_entity_id"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_NAME = "Shelly Wall Display X2i RPC"

PLATFORMS = ["switch", "number", "button"]

UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

SERVICE_CALL_RPC = "call_rpc"
ATTR_ENTRY_ID = "entry_id"
ATTR_METHOD = "method"
ATTR_PARAMS = "params"
