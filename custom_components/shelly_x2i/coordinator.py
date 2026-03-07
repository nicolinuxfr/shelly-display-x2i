"""Data update coordinator for Shelly X2i RPC."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import logging
from datetime import timedelta
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ShellyRPCClient, ShellyRPCError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_POST_ACTION_REFRESH_DELAY = 3.0
_TRANSIENT_AVAILABILITY_GRACE = 15.0
_FULL_REFRESH_EVERY = 10


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
    """Clamp a firmware brightness level (0..100) to an integer percentage.

    The X2i firmware stores brightness as a percentage in both GetConfig/GetStatus
    and SetConfig, so no unit conversion is needed here.
    """
    if not isinstance(level, (int, float)):
        return None
    return int(round(max(0.0, min(100.0, float(level)))))


def _ui_config(config: dict[str, Any]) -> dict[str, Any] | None:
    """Return the UI config subtree when available."""
    ui_cfg = config.get("ui")
    return ui_cfg if isinstance(ui_cfg, dict) else None


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
        self._local_action_until: float = 0.0
        self._scheduled_refresh_task: asyncio.Task[None] | None = None
        self._methods_set: set[str] | None = None
        self._refresh_count = 0

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

    def mark_local_action(self, grace_seconds: float = _TRANSIENT_AVAILABILITY_GRACE) -> None:
        """Keep entities available while the device applies a local RPC action."""
        self._local_action_until = max(self._local_action_until, time.monotonic() + grace_seconds)

    @property
    def assume_available(self) -> bool:
        """Report transient availability when a recent local action may disrupt polling."""
        return bool(self.data) and time.monotonic() < self._local_action_until

    def schedule_refresh(self, delay: float = _POST_ACTION_REFRESH_DELAY) -> None:
        """Refresh after a short delay to let the display settle after RPC writes."""
        if self._scheduled_refresh_task is not None and not self._scheduled_refresh_task.done():
            self._scheduled_refresh_task.cancel()
        self._scheduled_refresh_task = self.hass.async_create_task(
            self._async_delayed_refresh(delay)
        )

    async def _async_delayed_refresh(self, delay: float) -> None:
        """Trigger a refresh after a delay and swallow transient cancellation."""
        try:
            await asyncio.sleep(delay)
            await self.async_request_refresh()
        except asyncio.CancelledError:
            raise
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.debug("Delayed Shelly refresh failed: %s", err)

    def _build_brightness_ui_config(self, level: int) -> dict[str, Any]:
        """Build a firmware-compatible Ui.SetConfig payload for brightness."""
        clamped_level = max(0, min(100, int(level)))

        config = self.data.get("config", {})
        ui_config = _ui_config(config) if isinstance(config, dict) else None
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

    async def async_set_screen_off_when_idle(self, enabled: bool) -> None:
        """Enable or disable screen power-off when idle."""
        await self.client.call("Ui.SetConfig", {"config": {"screen_off_when_idle": bool(enabled)}})

    async def async_set_screen_saver_enabled(self, enabled: bool) -> None:
        """Enable or disable the screen saver while preserving known options."""
        config = self.data.get("config", {})
        ui_config = _ui_config(config) if isinstance(config, dict) else None
        screen_saver_cfg = (
            deepcopy(ui_config.get("screen_saver")) if isinstance(ui_config.get("screen_saver"), dict) else {}
        ) if isinstance(ui_config, dict) else {}
        screen_saver_cfg["enable"] = bool(enabled)
        await self.client.call("Ui.SetConfig", {"config": {"screen_saver": screen_saver_cfg}})

    async def async_set_screen_saver_timeout(self, timeout_seconds: int) -> None:
        """Set the screen saver timeout while preserving other screen saver options."""
        config = self.data.get("config", {})
        ui_config = _ui_config(config) if isinstance(config, dict) else None
        screen_saver_cfg = (
            deepcopy(ui_config.get("screen_saver")) if isinstance(ui_config.get("screen_saver"), dict) else {}
        ) if isinstance(ui_config, dict) else {}
        screen_saver_cfg["timeout"] = max(0, int(timeout_seconds))
        await self.client.call("Ui.SetConfig", {"config": {"screen_saver": screen_saver_cfg}})

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest device data."""
        try:
            status = await self.client.call("Shelly.GetStatus")
        except ShellyRPCError as err:
            raise UpdateFailed(str(err)) from err

        previous = self.data if isinstance(self.data, dict) else {}
        refresh_index = self._refresh_count
        self._refresh_count += 1
        should_refresh_full = not previous or refresh_index % _FULL_REFRESH_EVERY == 0

        config = previous.get("config", {}) if isinstance(previous.get("config"), dict) else {}
        if should_refresh_full or not config:
            try:
                config = await self.client.call("Shelly.GetConfig")
            except ShellyRPCError as err:
                if not config:
                    raise UpdateFailed(str(err)) from err
                _LOGGER.debug("Shelly.GetConfig unavailable/failed, keeping cached config: %s", err)

        methods_set = self._methods_set
        if methods_set is None:
            try:
                methods_result = await self.client.call("Shelly.ListMethods")
                methods = methods_result.get("methods", [])
                if not isinstance(methods, list):
                    methods = []
                methods_set = set(m for m in methods if isinstance(m, str))
                self._methods_set = methods_set
            except ShellyRPCError as err:
                _LOGGER.debug("Shelly.ListMethods unavailable/failed: %s", err)
                methods_set = set()
        if methods_set is None:
            methods_set = set()

        sys_status: dict[str, Any] = (
            previous.get("sys_status", {}) if isinstance(previous.get("sys_status"), dict) else {}
        )
        if "Sys.GetStatus" in methods_set and (should_refresh_full or not sys_status):
            try:
                sys_status = await self.client.call("Sys.GetStatus")
            except ShellyRPCError as err:
                _LOGGER.debug("Sys.GetStatus unavailable/failed, keeping cached value: %s", err)
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
            "sys_status": sys_status,
            "methods": methods_set,
            "screen_on": screen_on,
            "brightness_status": brightness_status,
            "brightness_config": brightness_config,
            "brightness": brightness,
        }
        return parsed
