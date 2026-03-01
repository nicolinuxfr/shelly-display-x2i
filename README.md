# Shelly Wall Display X2i RPC (Home Assistant custom integration)

Custom integration to add RPC-only entities for a Shelly Wall Display X2i.

This integration is intended to complement the official Shelly integration:
- keep official Shelly entities
- add extra controls exposed through RPC (screen power, brightness, reboot, raw RPC service)
- optionally attach these entities to the same Home Assistant device by providing an existing Shelly entity ID in setup

## Features

- Auto-discovery of Shelly Wall Display X2i devices already known by Home Assistant (pre-fills host/port/source entity)
- Manual config flow fallback with IP/host, port, optional credentials
- `switch`:
  - Screen power (`Ui.Screen.Set`)
- `number`:
  - Screen brightness (`Ui.SetConfig`)
- `button`:
  - Refresh
  - Reboot
- Service:
  - `shelly_x2i_rpc.call_rpc` to execute any RPC method

## Install with HACS

1. HACS -> Integrations -> Custom repositories
2. Add this repository URL as category `Integration`
3. Install `Shelly Wall Display X2i RPC`
4. Restart Home Assistant

## Configure

1. Settings -> Devices & Services -> Add Integration
2. Search for `Shelly Wall Display X2i RPC`
3. If HA already knows compatible Shelly displays, pick one from the discovery list and validate.
4. Otherwise use manual setup and fill:
   - Host/IP (for example `192.168.1.50`)
   - Port (default `80`)
   - Optional credentials
   - Optional `source_entity_id` from the official Shelly device to group entities under the same HA device card

## Notes

- The integration is intentionally scoped to one X2i device per config entry.
- Availability and exact values depend on firmware RPC payload shape.
- If an RPC method is unavailable on your firmware, use `call_rpc` service to test capabilities (for example with `Shelly.ListMethods`).
