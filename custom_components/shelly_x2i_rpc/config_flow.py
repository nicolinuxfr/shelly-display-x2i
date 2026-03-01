"""Config flow for Shelly Wall Display X2i RPC."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import ShellyRPCClient, ShellyRPCError
from .const import CONF_SOURCE_ENTITY_ID, DEFAULT_PORT, DOMAIN


class ShellyX2iRPCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Shelly Wall Display X2i RPC."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            username = user_input.get(CONF_USERNAME) or None
            password = user_input.get(CONF_PASSWORD) or None

            client = ShellyRPCClient(
                async_get_clientsession(self.hass),
                host=host,
                port=port,
                username=username,
                password=password,
            )

            try:
                info = await client.call("Shelly.GetDeviceInfo")
            except ShellyRPCError:
                errors["base"] = "cannot_connect"
            else:
                unique = str(info.get("id") or host)
                await self.async_set_unique_id(unique)
                self._abort_if_unique_id_configured()

                title = info.get("name") or f"Wall Display X2i ({host})"
                data = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                    CONF_SOURCE_ENTITY_ID: user_input.get(CONF_SOURCE_ENTITY_ID) or None,
                }
                return self.async_create_entry(title=title, data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_USERNAME, default=""): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
                vol.Optional(CONF_SOURCE_ENTITY_ID, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

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
