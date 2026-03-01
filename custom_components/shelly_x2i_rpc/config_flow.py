"""Config flow for Shelly Wall Display X2i RPC."""

from __future__ import annotations

from dataclasses import dataclass
import logging
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
_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _DiscoveryCandidate:
    """Candidate found from Home Assistant registries."""

    key: str
    label: str
    host: str
    port: int
    source_entity_id: str | None
    expected_model: str | None = None
    expected_unique_id: str | None = None
    expected_mac: str | None = None
    likely_x2i: bool = False


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

        if not self._is_wall_display_info(info):
            if source_step == "discovery":
                return self._async_show_discovery_form(
                    errors={"base": "not_wall_display"},
                    selected_key=selected_key or self._candidates[0].key,
                    username=data.get(CONF_USERNAME) or "",
                    password=data.get(CONF_PASSWORD) or "",
                )
            return self._async_show_manual_form(
                errors={"base": "not_wall_display"},
                host=data[CONF_HOST],
                port=data[CONF_PORT],
                username=data.get(CONF_USERNAME) or "",
                password=data.get(CONF_PASSWORD) or "",
                source_entity_id=data.get(CONF_SOURCE_ENTITY_ID) or "",
            )

        if source_step == "discovery" and selected_key is not None:
            candidate = next((item for item in self._candidates if item.key == selected_key), None)
            if candidate is not None and not self._candidate_matches_info(candidate, info):
                return self._async_show_discovery_form(
                    errors={"base": "wrong_device"},
                    selected_key=selected_key,
                    username=data.get(CONF_USERNAME) or "",
                    password=data.get(CONF_PASSWORD) or "",
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
        """Discover Shelly devices from HA registries and config entries."""
        dev_reg = dr.async_get(self.hass)
        ent_reg = er.async_get(self.hass)

        candidates: dict[str, _DiscoveryCandidate] = {}
        seen_host_ports: set[tuple[str, int]] = set()

        for device in dev_reg.devices.values():
            manufacturer = (device.manufacturer or "").lower()
            model = (device.model or "").lower()
            name = (device.name or "").lower()
            user_name = (device.name_by_user or "").lower()

            linked_entries = [
                self.hass.config_entries.async_get_entry(entry_id)
                for entry_id in device.config_entries
            ]
            has_shelly_entry = any(entry and entry.domain == "shelly" for entry in linked_entries)

            if "shelly" not in manufacturer and not has_shelly_entry:
                continue

            entities = er.async_entries_for_device(ent_reg, device.id)
            host, port = self._host_from_device(device, entities, linked_entries)
            if host is None:
                continue
            source_entity_id = self._select_source_entity(entities)
            likely_x2i = self._is_likely_x2i(model=model, name=name, user_name=user_name)
            expected_unique_id = next(
                (
                    entry.unique_id
                    for entry in linked_entries
                    if entry is not None and entry.domain == "shelly" and entry.unique_id
                ),
                None,
            )
            expected_mac = next(
                (
                    str(connection[1])
                    for connection in device.connections
                    if connection[0] == dr.CONNECTION_NETWORK_MAC
                ),
                None,
            )

            label_name = device.name_by_user or device.name or "Shelly device"
            model_label = f" - {device.model}" if device.model else ""
            label = f"{label_name}{model_label} ({host}:{port})"
            candidates[device.id] = (
                _DiscoveryCandidate(
                    key=device.id,
                    label=label,
                    host=host,
                    port=port,
                    source_entity_id=source_entity_id,
                    expected_model=device.model,
                    expected_unique_id=expected_unique_id,
                    expected_mac=expected_mac,
                    likely_x2i=likely_x2i,
                )
            )
            seen_host_ports.add((host, port))

        # Fallback: official Shelly config entries not linked to device registry.
        for entry in self.hass.config_entries.async_entries("shelly"):
            host, port = self._host_from_sources(entry.data, entry.options)
            if host is None or (host, port) in seen_host_ports:
                continue

            entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
            source_entity_id = self._select_source_entity(entities)
            model = str(entry.data.get("model") or entry.options.get("model") or "").lower()
            title = entry.title or "Shelly device"
            candidates[f"ce::{entry.entry_id}"] = _DiscoveryCandidate(
                key=f"ce::{entry.entry_id}",
                label=f"{title} ({host}:{port})",
                host=host,
                port=port,
                source_entity_id=source_entity_id,
                expected_model=entry.data.get("model") or entry.options.get("model"),
                expected_unique_id=entry.unique_id,
                likely_x2i=self._is_likely_x2i(model=model, name=title.lower(), user_name=""),
            )

        ordered = sorted(candidates.values(), key=lambda item: (not item.likely_x2i, item.label.lower()))
        _LOGGER.debug("Shelly candidate discovery found %s devices", len(ordered))
        return ordered

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
        linked_entries: list[config_entries.ConfigEntry | None],
    ) -> tuple[str | None, int]:
        """Extract host/port from available HA metadata for this device."""
        host, port = self._parse_host_port(device.configuration_url)
        if host is not None:
            return host, port

        # Try linked config entries (official Shelly integration usually stores host there).
        host, port = self._host_from_sources(
            *[
                source
                for entry in linked_entries
                if entry is not None
                for source in (entry.data, entry.options)
            ]
        )
        if host is not None:
            return host, port

        # Last fallback: inspect runtime state attributes from linked entities.
        for entity in entities:
            state = self.hass.states.get(entity.entity_id)
            if state is None:
                continue
            host, port = self._host_from_sources(state.attributes)
            if host is not None:
                return host, port

        return None, DEFAULT_PORT

    @classmethod
    def _host_from_sources(cls, *sources: dict[str, Any]) -> tuple[str | None, int]:
        """Extract host/port from several dictionaries."""
        for source in sources:
            for key in (CONF_HOST, "host", "ip", "ip_address", "address", "device_ip"):
                value = source.get(key)
                if isinstance(value, str):
                    host, port = cls._parse_host_port(value)
                    if host is not None:
                        return host, port
        return None, DEFAULT_PORT

    @staticmethod
    def _select_source_entity(entities: list[er.RegistryEntry]) -> str | None:
        """Choose the best source entity to link our entities to an existing device."""
        if not entities:
            return None
        for entity in entities:
            if "shelly" in entity.entity_id:
                return entity.entity_id
        return entities[0].entity_id

    @staticmethod
    def _is_likely_x2i(model: str, name: str, user_name: str) -> bool:
        """Tell whether this candidate likely targets Wall Display X2i."""
        text = f"{model} {name} {user_name}"
        return (
            "x2i" in text
            or "wall display" in text
            or "walldisplay" in text
            or "sawd" in text
        )

    @classmethod
    def _is_wall_display_info(cls, info: dict[str, Any]) -> bool:
        """Check whether Shelly.GetDeviceInfo payload looks like Wall Display."""
        model = str(info.get("model") or "").lower()
        name = str(info.get("name") or info.get("id") or "").lower()
        return cls._is_likely_x2i(model=model, name=name, user_name="")

    @classmethod
    def _candidate_matches_info(cls, candidate: _DiscoveryCandidate, info: dict[str, Any]) -> bool:
        """Verify selected candidate matches actual RPC endpoint identity."""
        info_id = cls._normalize_token(str(info.get("id") or ""))
        info_model = str(info.get("model") or "").lower()
        info_mac = cls._normalize_token(str(info.get("mac") or ""))

        expected_model = str(candidate.expected_model or "").lower()
        if expected_model and info_model and expected_model != info_model:
            return False

        expected_unique = cls._normalize_token(candidate.expected_unique_id)
        if expected_unique and info_id and expected_unique not in info_id:
            return False

        expected_mac = cls._normalize_token(candidate.expected_mac)
        if expected_mac:
            if info_mac and expected_mac != info_mac:
                return False
            if info_id and expected_mac not in info_id:
                return False

        return True

    @staticmethod
    def _normalize_token(value: str | None) -> str:
        """Normalize identifiers/MAC for resilient comparison."""
        if not value:
            return ""
        return "".join(ch for ch in value.upper() if ch.isalnum())

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
