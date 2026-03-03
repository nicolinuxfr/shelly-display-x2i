---
name: add-entity-platform
description: Add a new Home Assistant entity platform to the shelly_x2i integration following existing patterns
disable-model-invocation: true
---

Add a new entity platform to the shelly_x2i integration.

Arguments (passed by the user after the skill name):
- `platform_type`: One of sensor, binary_sensor, switch, number, button
- `rpc_key`: The Shelly RPC key to expose (e.g. BLE.GetStatus)
- `entity_name`: Human-readable name for the entity

Steps to follow:
1. Read `custom_components/shelly_x2i/entity.py` to understand the base entity classes
2. Read `custom_components/shelly_x2i/const.py` to understand existing constants
3. Read the closest existing platform file (e.g. `sensor.py` for sensor platforms) as template
4. Read `custom_components/shelly_x2i/strings.json` to understand translation structure
5. Read `custom_components/shelly_x2i/__init__.py` to understand platform registration

Then:
- Add necessary constants to `const.py`
- Create or update the platform file following the existing patterns exactly (use ShellyX2iEntity base, define EntityDescription, implement async_update or coordinator-based state)
- Add translation keys to `strings.json`
- Register the platform in `__init__.py` if it's a new platform type

Follow the existing code style: type hints, async/await, DataUpdateCoordinator pattern, no direct polling in entity.
