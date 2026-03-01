"""Home Assistant integration for Shelly Wall Display X2i RPC controls."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .client import ShellyRPCClient
from .const import (
    ATTR_ENTRY_ID,
    ATTR_METHOD,
    ATTR_PARAMS,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SOURCE_DEVICE_ID,
    CONF_SOURCE_ENTITY_ID,
    DOMAIN,
    PLATFORMS,
    SERVICE_CALL_RPC,
    DEFAULT_SCAN_INTERVAL,
    build_update_interval,
)
from .coordinator import ShellyX2iRPCDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class ShellyX2iRPCRuntimeData:
    """Runtime data stored per config entry."""

    client: ShellyRPCClient
    coordinator: ShellyX2iRPCDataUpdateCoordinator
    device_info: dict[str, Any]


SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_METHOD): cv.string,
        vol.Optional(ATTR_PARAMS, default={}): dict,
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)


def _get_scan_interval_seconds(entry: ConfigEntry) -> int:
    """Return configured scan interval seconds with safe fallback."""
    raw_value = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return DEFAULT_SCAN_INTERVAL


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration services."""

    async def _async_handle_call_rpc(service: ServiceCall) -> None:
        method: str = service.data[ATTR_METHOD]
        params: dict[str, Any] = service.data.get(ATTR_PARAMS, {})
        entry_id: str | None = service.data.get(ATTR_ENTRY_ID)

        entries = hass.config_entries.async_entries(DOMAIN)
        if entry_id:
            entries = [entry for entry in entries if entry.entry_id == entry_id]

        if not entries:
            _LOGGER.warning("No config entry found for service call to method %s", method)
            return

        entry = entries[0]
        runtime: ShellyX2iRPCRuntimeData = entry.runtime_data
        await runtime.client.call(method, params)
        await runtime.coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_CALL_RPC):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CALL_RPC,
            _async_handle_call_rpc,
            schema=SERVICE_SCHEMA,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the config entry."""
    if not entry.data.get(CONF_SOURCE_DEVICE_ID):
        source_entity_id = entry.options.get(CONF_SOURCE_ENTITY_ID) or entry.data.get(
            CONF_SOURCE_ENTITY_ID
        )
        if source_entity_id:
            ent_reg = async_get_entity_registry(hass)
            source_entry = ent_reg.async_get(source_entity_id) if ent_reg is not None else None
            if source_entry is not None and source_entry.device_id:
                data = dict(entry.data)
                data[CONF_SOURCE_DEVICE_ID] = source_entry.device_id
                hass.config_entries.async_update_entry(entry, data=data)

    session = async_get_clientsession(hass)
    client = ShellyRPCClient(
        session=session,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data.get(CONF_USERNAME),
        password=entry.data.get(CONF_PASSWORD),
    )

    info = await client.call("Shelly.GetDeviceInfo")
    name = info.get("name") or "Shelly Wall Display X2i"
    mac = info.get("mac")
    model = info.get("model")
    sw = info.get("fw_id")
    device_id = info.get("id") or entry.entry_id

    device_info: dict[str, Any] = {
        "identifiers": {(DOMAIN, device_id)},
        "name": name,
        "manufacturer": "Shelly",
        "model": model or "Wall Display X2i",
        "sw_version": sw,
        "configuration_url": f"http://{entry.data[CONF_HOST]}",
    }
    if isinstance(mac, str) and mac:
        device_info["connections"] = {(dr.CONNECTION_NETWORK_MAC, mac)}

    update_interval = build_update_interval(_get_scan_interval_seconds(entry))
    coordinator = ShellyX2iRPCDataUpdateCoordinator(
        hass,
        client,
        str(name),
        update_interval,
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = ShellyX2iRPCRuntimeData(
        client=client,
        coordinator=coordinator,
        device_info=device_info,
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry."""
    result = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if result and not hass.config_entries.async_entries(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_CALL_RPC)
    return result
