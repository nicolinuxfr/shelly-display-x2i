"""Switch entities for Shelly X2i RPC."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import ShellyX2iRPCRuntimeData
from .entity import ShellyX2iBaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up switch entities."""
    runtime: ShellyX2iRPCRuntimeData = entry.runtime_data
    async_add_entities(
        [ShellyScreenPowerSwitch(entry, runtime.coordinator, runtime.device_info)],
        True,
    )


class ShellyScreenPowerSwitch(ShellyX2iBaseEntity, SwitchEntity, RestoreEntity):
    """Power state of the X2i display."""

    _attr_translation_key = "screen_power"
    _attr_icon = "mdi:monitor"

    def __init__(self, entry, coordinator, fallback_device_info) -> None:
        super().__init__(
            entry=entry,
            coordinator=coordinator,
            fallback_device_info=fallback_device_info,
            key="screen_power",
            name="Screen",
        )
        self._optimistic_state: bool | None = None

    async def async_added_to_hass(self) -> None:
        """Restore last known state."""
        await super().async_added_to_hass()
        restored = await self.async_get_last_state()
        if restored is not None:
            self._optimistic_state = restored.state == "on"

    @property
    def is_on(self) -> bool | None:
        """Return current power status."""
        state = self.coordinator.data.get("screen_on")
        if isinstance(state, bool):
            return state
        return self._optimistic_state

    @property
    def assumed_state(self) -> bool:
        """Expose assumed state when firmware does not provide real status."""
        return self.coordinator.data.get("screen_on") is None

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the screen on."""
        await self.coordinator.client.call("Ui.Screen.Set", {"on": True})
        self._optimistic_state = True
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the screen off."""
        await self.coordinator.client.call("Ui.Screen.Set", {"on": False})
        self._optimistic_state = False
        await self.coordinator.async_request_refresh()
