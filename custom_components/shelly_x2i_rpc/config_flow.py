"""Config flow for Shelly Wall Display X2i RPC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import ShellyRPCClient, ShellyRPCError
from .const import CONF_SOURCE_ENTITY_ID, DEFAULT_PORT, DOMAIN

CONF_DISCOVERED_DEVICE = "discovered_device"
_DISCOVERY_MANUAL = "__manual__"


@dataclass(slots=True)
class _DiscoveryCandidate:
    """Candidate found from Home Assistant registries."""

    key: str
    label: str
    host: str
    port: int
    source_entity_id: str | None


class ShellyX2iRPCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Shelly Wall Display X2i RPC."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow state."""
        self._candidates: list[_DiscoveryCandidate] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        self._candidates = await self._async_discover_candidates()
        if self._candidates:
            return await self.async_step_discovery()
        return await self.async_step_manual()

    async def async_step_discovery(self, user_input: dict[str, Any] | None = None):
        """Select one discovered device or switch to manual setup."""
        if user_input is not None:
            selected_key = user_input[CONF_DISCOVERED_DEVICE]
            if selected_key == _DISCOVERY_MANUAL:
                return await self.async_step_manual()

            candidate = next((item for item in self._candidates if item.key == selected_key), None)
            if candidate is None:
                return self._async_show_discovery_form(
                    errors={"base": "unknown_device"},
                    selected_key=self._candidates[0].key,
                    username=user_input.get(CONF_USERNAME, ""),
                    password=user_input.get(CONF_PASSWORD, ""),
                )

            return await self._async_validate_and_create(
                {
                    CONF_HOST: candidate.host,
                    CONF_PORT: candidate.port,
                    CONF_USERNAME: user_input.get(CONF_USERNAME) or None,
                    CONF_PASSWORD: user_input.get(CONF_PASSWORD) or None,
                    CONF_SOURCE_ENTITY_ID: candidate.source_entity_id,
                },
                source_step="discovery",
                selected_key=selected_key,
            )

        return self._async_show_discovery_form()

    async def async_step_manual(self, user_input: dict[str, Any] | None = None):
        """Manual setup fallback."""
        if user_input is not None:
            return await self._async_validate_and_create(
                {
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PORT: user_input[CONF_PORT],
                    CONF_USERNAME: user_input.get(CONF_USERNAME) or None,
                    CONF_PASSWORD: user_input.get(CONF_PASSWORD) or None,
                    CONF_SOURCE_ENTITY_ID: user_input.get(CONF_SOURCE_ENTITY_ID) or None,
                },
                source_step="manual",
            )

        return self._async_show_manual_form()

    async def _async_validate_and_create(
        self,
        data: dict[str, Any],
        source_step: str,
        selected_key: str | None = None,
    ):
        """Validate RPC endpoint and create config entry."""
        client = ShellyRPCClient(
            async_get_clientsession(self.hass),
            host=data[CONF_HOST],
            port=data[CONF_PORT],
            username=data.get(CONF_USERNAME),
            password=data.get(CONF_PASSWORD),
        )

        try:
            info = await client.call("Shelly.GetDeviceInfo")
        except ShellyRPCError:
            if source_step == "discovery":
                return self._async_show_discovery_form(
                    errors={"base": "cannot_connect"},
                    selected_key=selected_key or self._candidates[0].key,
                    username=data.get(CONF_USERNAME) or "",
                    password=data.get(CONF_PASSWORD) or "",
                )
            return self._async_show_manual_form(
                errors={"base": "cannot_connect"},
                host=data[CONF_HOST],
                port=data[CONF_PORT],
                username=data.get(CONF_USERNAME) or "",
                password=data.get(CONF_PASSWORD) or "",
                source_entity_id=data.get(CONF_SOURCE_ENTITY_ID) or "",
            )

        unique = str(info.get("id") or data[CONF_HOST])
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured()

        title = info.get("name") or f"Wall Display X2i ({data[CONF_HOST]})"
        return self.async_create_entry(title=title, data=data)

    def _async_show_discovery_form(
        self,
        errors: dict[str, str] | None = None,
        selected_key: str | None = None,
        username: str = "",
        password: str = "",
    ):
        """Render discovery form with defaults."""
        options = {candidate.key: candidate.label for candidate in self._candidates}
        options[_DISCOVERY_MANUAL] = "Manual setup"

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DISCOVERED_DEVICE,
                    default=selected_key or self._candidates[0].key,
                ): vol.In(options),
                vol.Optional(CONF_USERNAME, default=username): str,
                vol.Optional(CONF_PASSWORD, default=password): str,
            }
        )
        return self.async_show_form(step_id="discovery", data_schema=schema, errors=errors or {})

    def _async_show_manual_form(
        self,
        errors: dict[str, str] | None = None,
        host: str = "",
        port: int = DEFAULT_PORT,
        username: str = "",
        password: str = "",
        source_entity_id: str = "",
    ):
        """Render manual form with defaults."""
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=host): str,
                vol.Required(CONF_PORT, default=port): int,
                vol.Optional(CONF_USERNAME, default=username): str,
                vol.Optional(CONF_PASSWORD, default=password): str,
                vol.Optional(CONF_SOURCE_ENTITY_ID, default=source_entity_id): str,
            }
        )
        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors or {})

    async def _async_discover_candidates(self) -> list[_DiscoveryCandidate]:
        """Discover likely Shelly Wall Display devices from HA registries."""
        dev_reg = dr.async_get(self.hass)
        ent_reg = er.async_get(self.hass)

        candidates: list[_DiscoveryCandidate] = []

        for device in dev_reg.devices.values():
            manufacturer = (device.manufacturer or "").lower()
            model = (device.model or "").lower()
            name = (device.name or "").lower()

            if "shelly" not in manufacturer:
                continue
            if "x2i" not in model and "x2i" not in name and "wall display" not in model:
                continue

            entities = er.async_entries_for_device(ent_reg, device.id)
            host, port = self._host_from_device(device, entities)
            if host is None:
                continue
            source_entity_id = entities[0].entity_id if entities else None

            label_name = device.name_by_user or device.name or "Shelly Wall Display X2i"
            label = f"{label_name} ({host}:{port})"
            candidates.append(
                _DiscoveryCandidate(
                    key=device.id,
                    label=label,
                    host=host,
                    port=port,
                    source_entity_id=source_entity_id,
                )
            )

        candidates.sort(key=lambda item: item.label.lower())
        return candidates

    @staticmethod
    def _parse_host_port(value: str | None) -> tuple[str | None, int]:
        """Parse host/port from URL or raw host string."""
        if not value:
            return None, DEFAULT_PORT

        raw = value.strip()
        if not raw:
            return None, DEFAULT_PORT
        if "://" not in raw:
            raw = f"http://{raw}"

        parsed = urlparse(raw)
        if not parsed.hostname:
            return None, DEFAULT_PORT

        return parsed.hostname, parsed.port or DEFAULT_PORT

    def _host_from_device(
        self,
        device: dr.DeviceEntry,
        entities: list[er.RegistryEntry],
    ) -> tuple[str | None, int]:
        """Extract host/port from available HA metadata for this device."""
        host, port = self._parse_host_port(device.configuration_url)
        if host is not None:
            return host, port

        # Try linked config entries (official Shelly integration usually stores host there).
        for entry_id in device.config_entries:
            config_entry = self.hass.config_entries.async_get_entry(entry_id)
            if config_entry is None:
                continue
            for source in (config_entry.data, config_entry.options):
                for key in (CONF_HOST, "host", "ip", "ip_address", "address", "device_ip"):
                    value = source.get(key)
                    if isinstance(value, str):
                        host, port = self._parse_host_port(value)
                        if host is not None:
                            return host, port

        # Last fallback: inspect runtime state attributes from linked entities.
        for entity in entities:
            state = self.hass.states.get(entity.entity_id)
            if state is None:
                continue
            for key in ("ip", "ip_address", "host", "address"):
                value = state.attributes.get(key)
                if isinstance(value, str):
                    host, port = self._parse_host_port(value)
                    if host is not None:
                        return host, port

        return None, DEFAULT_PORT

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow."""
        return ShellyX2iRPCOptionsFlow(config_entry)


class ShellyX2iRPCOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SOURCE_ENTITY_ID,
                    default=self._config_entry.options.get(
                        CONF_SOURCE_ENTITY_ID,
                        self._config_entry.data.get(CONF_SOURCE_ENTITY_ID, ""),
                    ),
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
