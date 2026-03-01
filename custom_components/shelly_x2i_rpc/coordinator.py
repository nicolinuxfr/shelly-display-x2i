"""Data update coordinator for Shelly X2i RPC."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ShellyRPCClient, ShellyRPCError
from .const import DOMAIN

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
    """Parse brightness, preferring live status over potentially stale config."""
    ui_status = status.get("ui")
    if isinstance(ui_status, dict):
        brightness = ui_status.get("brightness")
        if isinstance(brightness, dict):
            level = brightness.get("level")
            if isinstance(level, (int, float)):
                return int(round(level))

    ui_cfg = config.get("ui")
    if isinstance(ui_cfg, dict):
        brightness = ui_cfg.get("brightness")
        if isinstance(brightness, dict):
            level = brightness.get("level")
            if isinstance(level, (int, float)):
                return int(round(level))
    return None


class ShellyX2iRPCDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and cache Shelly X2i RPC data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ShellyRPCClient,
        name: str,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_{name}",
            update_interval=update_interval,
        )
        self.client = client
        self._pending_brightness_level: int | None = None
        self._last_nonzero_brightness_level: int | None = None
        self._expected_screen_on: bool | None = None

    @property
    def pending_brightness_level(self) -> int | None:
        """Brightness level to apply on next screen wake-up."""
        return self._pending_brightness_level

    @property
    def last_nonzero_brightness_level(self) -> int | None:
        """Most recent non-zero brightness reported by the device."""
        return self._last_nonzero_brightness_level

    @property
    def expected_screen_on(self) -> bool | None:
        """Best-known power state when firmware does not expose screen_on."""
        return self._expected_screen_on

    def set_expected_screen_on(self, state: bool | None) -> None:
        """Set expected power state from user actions or observed telemetry."""
        self._expected_screen_on = state

    def set_pending_brightness_level(self, level: int) -> None:
        """Remember brightness level for later application."""
        self._pending_brightness_level = max(0, min(250, int(level)))

    def clear_pending_brightness_level(self) -> None:
        """Drop pending brightness level."""
        self._pending_brightness_level = None

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
        screen_on = _parse_screen_on(status)
        brightness = _parse_brightness(config, status)
        if isinstance(screen_on, bool):
            self._expected_screen_on = screen_on
        elif isinstance(brightness, int) and brightness > 0:
            # On firmware variants where screen_on is never reported, non-zero
            # brightness is the best signal that the panel is currently on.
            self._expected_screen_on = True
        _LOGGER.debug(
            "RPC state: screen_on=%s expected=%s brightness=%s pending=%s",
            screen_on,
            self._expected_screen_on,
            brightness,
            self._pending_brightness_level,
        )

        # If brightness was set while the screen was off, apply it as soon as the
        # screen is back on, including when wake-up was triggered directly on device.
        effective_screen_on = screen_on if isinstance(screen_on, bool) else self._expected_screen_on
        if effective_screen_on is True and isinstance(self._pending_brightness_level, int):
            pending_level = self._pending_brightness_level
            if pending_level <= 0:
                self._pending_brightness_level = None
            elif brightness != pending_level:
                try:
                    await self.client.call(
                        "Ui.SetConfig",
                        {
                            "config": {
                                "brightness": {
                                    "level": pending_level,
                                    "auto": False,
                                }
                            }
                        },
                    )
                    brightness = pending_level
                    _LOGGER.debug("Applied pending brightness level=%s after wake-up", pending_level)
                except ShellyRPCError as err:
                    _LOGGER.warning("Failed applying pending brightness level %s: %s", pending_level, err)
            if brightness == pending_level:
                self._pending_brightness_level = None

        if isinstance(brightness, int):
            if brightness > 0:
                self._last_nonzero_brightness_level = brightness
            if self._pending_brightness_level == brightness:
                self._pending_brightness_level = None

        parsed: dict[str, Any] = {
            "status": status,
            "config": config,
            "methods": set(m for m in methods if isinstance(m, str)),
            "screen_on": screen_on,
            "brightness": brightness,
        }
        return parsed
