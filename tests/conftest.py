"""Common fixtures for the Glutz eAccess tests."""
from __future__ import annotations

import os
from collections.abc import Callable, Coroutine, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import homeassistant.components as _hac
import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Extend homeassistant.components.__path__ so that the local
# homeassistant/components/glutz_eaccess package is importable as
# homeassistant.components.glutz_eaccess alongside the installed HA components.
_LOCAL_COMPONENTS = os.path.join(_PROJECT_ROOT, "homeassistant", "components")
if _LOCAL_COMPONENTS not in list(_hac.__path__):
    _hac.__path__.append(_LOCAL_COMPONENTS)

from homeassistant.components.glutz_eaccess.const import DOMAIN  # noqa: E402

MOCK_ENTRY_DATA = {
    CONF_HOST: "https://example.com",
    CONF_USERNAME: "user",
    CONF_PASSWORD: "secret",
}

MOCK_ACCESS_POINTS = [
    {"accessPointId": "ap-1", "location": ["Building A", "Floor 1", "Main Door"]},
    {"accessPointId": "ap-2", "location": []},
]


@pytest.fixture(autouse=True)
def stub_clientsession() -> Generator[None, None, None]:
    """Prevent the HA shared aiohttp session from being created for real.

    A real `aiohttp.ClientSession` eagerly spins up a `pycares` DNS resolver
    whose daemon shutdown thread outlives the test and trips the
    `verify_cleanup` "no lingering threads" assertion. Patching
    `_async_create_clientsession` (the factory used by
    `async_get_clientsession`) covers every caller regardless of how they
    imported the helper. `GlutzAPI` is mocked in every test so the session
    is never actually used. Shim only required under
    `pytest-homeassistant-custom-component`; HA core tests don't need it.
    """
    with patch(
        "homeassistant.helpers.aiohttp_client._async_create_clientsession",
        return_value=MagicMock(),
    ):
        yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a MockConfigEntry for the Glutz eAccess integration."""
    return MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_ENTRY_DATA,
        unique_id="SYS1",
    )


@pytest.fixture
def mock_api() -> AsyncMock:
    """Return a mocked `GlutzAPI` instance with sensible defaults."""
    api = AsyncMock()
    api.open_access_point = AsyncMock(return_value=True)
    api.hold_open_access_point = AsyncMock(return_value=True)
    api.close_access_point = AsyncMock(return_value=True)
    api.get_access_points = AsyncMock(return_value=list(MOCK_ACCESS_POINTS))
    api.get_system_info = AsyncMock(return_value={"id": "SYS1", "name": "Palazzo"})
    return api


@pytest.fixture
def setup_integration() -> Callable[
    [HomeAssistant, MockConfigEntry, AsyncMock], Coroutine[Any, Any, None]
]:
    """Return a callable that adds a config entry to `hass` and sets it up."""

    async def _setup(
        hass: HomeAssistant, entry: MockConfigEntry, api: AsyncMock
    ) -> None:
        entry.add_to_hass(hass)
        with patch("homeassistant.components.glutz_eaccess.GlutzAPI", return_value=api):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

    return _setup
