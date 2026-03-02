"""Websocket notification listener for Shelly RPC."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp

from .coordinator import ShellyX2iRPCDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
_NOTIFY_METHODS = {"NotifyStatus", "NotifyEvent"}
_REFRESH_MIN_INTERVAL = 1.0


class ShellyNotificationListener:
    """Maintain an RPC websocket connection and trigger refresh on notifications."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        ws_url: str,
        ws_headers: dict[str, str],
        coordinator: ShellyX2iRPCDataUpdateCoordinator,
    ) -> None:
        self._session = session
        self._ws_url = ws_url
        self._ws_headers = ws_headers
        self._coordinator = coordinator
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._last_refresh = 0.0

    def start(self) -> None:
        """Start background listener task."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="shelly_x2i_notifications")

    async def stop(self) -> None:
        """Stop background listener task."""
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        """Reconnect loop."""
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                await self._listen_once()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as err:  # pragma: no cover - defensive reconnect loop
                _LOGGER.debug("Shelly notification listener disconnected: %s", err)
            if self._stop_event.is_set():
                return
            await asyncio.sleep(backoff)
            backoff = min(30.0, backoff * 2.0)

    async def _listen_once(self) -> None:
        """Connect and process websocket frames."""
        async with self._session.ws_connect(
            self._ws_url,
            headers=self._ws_headers or None,
            heartbeat=30,
            timeout=aiohttp.ClientTimeout(total=None),
        ) as ws:
            _LOGGER.debug("Shelly notification websocket connected: %s", self._ws_url)
            while not self._stop_event.is_set():
                message = await ws.receive()
                if message.type == aiohttp.WSMsgType.TEXT:
                    self._handle_text_message(message.data)
                    continue
                if message.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.ERROR,
                ):
                    return

    def _handle_text_message(self, payload: str) -> None:
        """Process websocket message and refresh coordinator on notifications."""
        try:
            body: Any = json.loads(payload)
        except ValueError:
            return
        if not isinstance(body, dict):
            return

        method = body.get("method")
        if method not in _NOTIFY_METHODS:
            return

        now = time.monotonic()
        if (now - self._last_refresh) < _REFRESH_MIN_INTERVAL:
            return
        self._last_refresh = now
        asyncio.create_task(self._coordinator.async_request_refresh())
