"""Data update coordinator for Shelly X2i RPC."""

from __future__ import annotations

from copy import deepcopy
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ShellyRPCClient, ShellyRPCError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_SHELLY_BRIGHTNESS_READ_MAX = 255


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
    """Backward-compatible parsed brightness value."""
    status_level = _parse_brightness_status(status)
    if isinstance(status_level, int):
        return status_level
    return _parse_brightness_config(config)


def _parse_brightness_status(status: dict[str, Any]) -> int | None:
    """Parse live brightness from status payload."""
    ui_status = status.get("ui")
    if isinstance(ui_status, dict):
        brightness = ui_status.get("brightness")
        if isinstance(brightness, dict):
            level = brightness.get("level")
            if isinstance(level, (int, float)):
                return int(round(level))
    return None


def _parse_brightness_config(config: dict[str, Any]) -> int | None:
    """Parse configured brightness from config payload."""
    ui_cfg = config.get("ui")
    if isinstance(ui_cfg, dict):
        brightness = ui_cfg.get("brightness")
        if isinstance(brightness, dict):
            level = brightness.get("level")
            if isinstance(level, (int, float)):
                return int(round(level))
    return None


def _normalize_to_percent(level: int | float | None) -> int | None:
    """Normalize firmware brightness readings to integer percentage."""
    if not isinstance(level, (int, float)):
        return None
    value = int(round(float(level)))
    if value <= 100:
        return max(0, value)
    return int(round((max(0, min(_SHELLY_BRIGHTNESS_READ_MAX, value)) / _SHELLY_BRIGHTNESS_READ_MAX) * 100))


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
        self._pending_brightness_level = max(0, min(100, int(level)))

    def clear_pending_brightness_level(self) -> None:
        """Drop pending brightness level."""
        self._pending_brightness_level = None

    def _build_brightness_ui_config(self, level: int) -> dict[str, Any]:
        """Build a firmware-compatible Ui.SetConfig payload for brightness."""
        clamped_level = max(0, min(100, int(level)))

        config = self.data.get("config", {})
        ui_config = config.get("ui") if isinstance(config, dict) else None
        brightness_cfg = ui_config.get("brightness") if isinstance(ui_config, dict) else None

        if isinstance(brightness_cfg, dict):
            payload_cfg = deepcopy(brightness_cfg)
            payload_cfg["level"] = clamped_level
            if "brightness" in payload_cfg and isinstance(payload_cfg["brightness"], (int, float)):
                payload_cfg["brightness"] = clamped_level
            if isinstance(payload_cfg.get("auto"), bool):
                payload_cfg["auto"] = False
            if isinstance(payload_cfg.get("auto_brightness"), bool):
                payload_cfg["auto_brightness"] = False
            if isinstance(payload_cfg.get("enabled"), bool):
                payload_cfg["enabled"] = True
            if isinstance(payload_cfg.get("mode"), str):
                payload_cfg["mode"] = "manual"
            return {"config": {"brightness": payload_cfg}}

        if isinstance(brightness_cfg, (int, float)):
            return {"config": {"brightness": clamped_level}}

        return {"config": {"brightness": {"level": clamped_level, "auto": False}}}

    async def async_set_brightness_level(self, level: int) -> None:
        """Set screen brightness using Ui.SetConfig."""
        await self.client.call("Ui.SetConfig", self._build_brightness_ui_config(level))

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
        brightness_status = _parse_brightness_status(status)
        brightness_config = _parse_brightness_config(config)
        brightness = brightness_status if brightness_status is not None else brightness_config
        if isinstance(screen_on, bool):
            self._expected_screen_on = screen_on
        _LOGGER.debug(
            "RPC state: screen_on=%s expected=%s brightness_status=%s brightness_config=%s pending=%s",
            screen_on,
            self._expected_screen_on,
            brightness_status,
            brightness_config,
            self._pending_brightness_level,
        )

        # If brightness was set while the screen was off, apply it as soon as the
        # screen is back on, including when wake-up was triggered directly on device.
        effective_screen_on = screen_on if isinstance(screen_on, bool) else self._expected_screen_on
        if effective_screen_on is True and isinstance(self._pending_brightness_level, int):
            pending_level = self._pending_brightness_level
            brightness_config_percent = _normalize_to_percent(brightness_config)
            if pending_level <= 0:
                self._pending_brightness_level = None
            elif brightness_config_percent != pending_level:
                try:
                    await self.async_set_brightness_level(pending_level)
                    _LOGGER.debug("Sent pending brightness level=%s", pending_level)
                except ShellyRPCError as err:
                    _LOGGER.warning("Failed applying pending brightness level %s: %s", pending_level, err)

        for level in (brightness_status, brightness_config):
            if isinstance(level, int) and level > 0:
                self._last_nonzero_brightness_level = level
        if (
            isinstance(self._pending_brightness_level, int)
            and _normalize_to_percent(brightness_config) == self._pending_brightness_level
        ):
            self._pending_brightness_level = None
        elif (
            isinstance(self._pending_brightness_level, int)
            and _normalize_to_percent(brightness_status) == self._pending_brightness_level
        ):
            self._pending_brightness_level = None

        parsed: dict[str, Any] = {
            "status": status,
            "config": config,
            "methods": set(m for m in methods if isinstance(m, str)),
            "screen_on": screen_on,
            "brightness_status": brightness_status,
            "brightness_config": brightness_config,
            "brightness": brightness,
        }
        return parsed
