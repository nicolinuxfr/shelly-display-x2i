"""Constants for the Shelly Wall Display X2i integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "shelly_x2i"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SOURCE_ENTITY_ID = "source_entity_id"
CONF_SOURCE_DEVICE_ID = "source_device_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ENABLE_NOTIFICATIONS = "enable_notifications"

DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_ENABLE_NOTIFICATIONS = True
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300
DEFAULT_NAME = "Shelly Wall Display X2i"

PLATFORMS = ["switch", "number", "button", "sensor", "binary_sensor"]

def build_update_interval(scan_interval_seconds: int) -> timedelta:
    """Build a safe update interval from user-provided seconds."""
    safe = max(MIN_SCAN_INTERVAL, min(MAX_SCAN_INTERVAL, int(scan_interval_seconds)))
    return timedelta(seconds=safe)

SERVICE_CALL_RPC = "call_rpc"
ATTR_ENTRY_ID = "entry_id"
ATTR_METHOD = "method"
ATTR_PARAMS = "params"
