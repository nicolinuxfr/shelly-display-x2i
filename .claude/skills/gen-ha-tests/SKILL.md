---
name: gen-ha-tests
description: Generate pytest test stubs for a module in the shelly_x2i integration
disable-model-invocation: true
---

Generate pytest tests for a given module in the shelly_x2i integration.

Arguments:
- `module`: The module to test (e.g. coordinator.py, client.py, switch.py)

Steps to follow:
1. Read the target module fully
2. Read `custom_components/shelly_x2i/const.py` for constants
3. Read `custom_components/shelly_x2i/client.py` to understand the RPC client interface

Then generate a test file at `tests/test_<module_name>.py` using:
- `pytest-homeassistant-custom-component` patterns
- `unittest.mock.AsyncMock` and `unittest.mock.patch` for mocking RPC calls and aiohttp
- `pytest.fixture` for common setup (mock coordinator, mock config entry, mock hass)
- Cover: happy path, error handling (aiohttp.ClientError), edge cases specific to the module

If `tests/` directory doesn't exist, create it with a `conftest.py` containing common fixtures:
- `mock_config_entry`: a ConfigEntry with test host/credentials
- `mock_coordinator`: a patched ShellyX2iCoordinator with fake data
- `mock_client`: a patched ShellyX2iClient returning canned RPC responses

Follow HA testing patterns: use `hass` fixture from pytest-homeassistant-custom-component, async tests with `@pytest.mark.asyncio`.
