"""RPC client for Shelly Gen2 devices."""

from __future__ import annotations

import base64
from typing import Any

import aiohttp


class ShellyRPCError(Exception):
    """Raised when a Shelly RPC call fails."""


class ShellyRPCClient:
    """Small JSON-RPC client over HTTP for Shelly Gen2."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int = 80,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password or ""
        self._session = session
        self._url = f"http://{host}:{port}/rpc"
        self._auth = aiohttp.BasicAuth(username, password or "") if username else None
        self._request_id = 0

    @property
    def ws_url(self) -> str:
        """Return websocket RPC endpoint URL."""
        return f"ws://{self._host}:{self._port}/rpc"

    def ws_headers(self) -> dict[str, str]:
        """Build websocket headers with basic auth when configured."""
        if not self._username:
            return {}
        token = base64.b64encode(f"{self._username}:{self._password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call a Shelly RPC method."""
        self._request_id += 1
        payload: dict[str, Any] = {"id": self._request_id, "method": method}
        if params is not None:
            payload["params"] = params

        try:
            async with self._session.post(
                self._url,
                json=payload,
                auth=self._auth,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                body = await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise ShellyRPCError(f"RPC HTTP error for {method}: {err}") from err

        if "error" in body:
            raise ShellyRPCError(f"RPC error for {method}: {body['error']}")

        result = body.get("result")
        if result is None:
            return {}

        if isinstance(result, dict):
            return result

        return {"value": result}
