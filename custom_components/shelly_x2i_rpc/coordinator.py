"""Data update coordinator for Shelly X2i RPC."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ShellyRPCClient, ShellyRPCError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


def _parse_screen_on(status: dict[str, Any]) -> bool | None:
    """Try common fields used by Shelly UI status for display power."""
    ui = status.get("ui")
    if not isinstance(ui, dict):
        return None

    if isinstance(ui.get("screen_on"), bool):
        return ui["screen_on"]

    screen = ui.get("screen")
    if isinstance(screen, dict) and isinstance(screen.get("on"), bool):
        return screen["on"]

    return None


def _parse_brightness(config: dict[str, Any], status: dict[str, Any]) -> int | None:
    """Try common fields used by Shelly UI brightness config."""
    ui_cfg = config.get("ui")
    if isinstance(ui_cfg, dict):
        brightness = ui_cfg.get("brightness")
        if isinstance(brightness, dict):
            level = brightness.get("level")
            if isinstance(level, int):
                return level

    ui_status = status.get("ui")
    if isinstance(ui_status, dict):
        brightness = ui_status.get("brightness")
        if isinstance(brightness, dict):
            level = brightness.get("level")
            if isinstance(level, int):
                return level
    return None


class ShellyX2iRPCDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and cache Shelly X2i RPC data."""

    def __init__(self, hass: HomeAssistant, client: ShellyRPCClient, name: str) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_{name}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest device data."""
        try:
            status = await self.client.call("Shelly.GetStatus")
            config = await self.client.call("Shelly.GetConfig")
            methods_result = await self.client.call("Shelly.ListMethods")
        except ShellyRPCError as err:
            raise UpdateFailed(str(err)) from err

        methods = methods_result.get("methods", [])
        if not isinstance(methods, list):
            methods = []

        parsed: dict[str, Any] = {
            "status": status,
            "config": config,
            "methods": set(m for m in methods if isinstance(m, str)),
            "screen_on": _parse_screen_on(status),
            "brightness": _parse_brightness(config, status),
        }
        return parsed
