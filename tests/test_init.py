"""Tests for the Glutz eAccess integration setup/unload."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from pyglutz_eaccess import GlutzAuthError, GlutzConnectionError

from homeassistant.components.glutz_eaccess import async_remove_config_entry_device
from homeassistant.components.glutz_eaccess.const import DOMAIN


async def test_setup_entry_loads(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Entry reaches LOADED state when the API responds normally."""
    await setup_integration(hass, mock_config_entry, mock_api)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data is not None


async def test_setup_entry_connection_error_triggers_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Connection error during first refresh lands in SETUP_RETRY."""
    mock_api.get_access_points = AsyncMock(side_effect=GlutzConnectionError("boom"))

    await setup_integration(hass, mock_config_entry, mock_api)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_auth_error_triggers_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Auth error during first refresh lands in SETUP_ERROR and starts reauth."""
    mock_api.get_access_points = AsyncMock(side_effect=GlutzAuthError("bad"))

    await setup_integration(hass, mock_config_entry, mock_api)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"].get("source") == "reauth" for f in flows)


async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Unloading a loaded entry transitions it to NOT_LOADED."""
    await setup_integration(hass, mock_config_entry, mock_api)

    with patch("homeassistant.components.glutz_eaccess.GlutzAPI", return_value=mock_api):
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_remove_config_entry_device_returns_false_for_active_access_point(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Active access point blocks device removal."""
    await setup_integration(hass, mock_config_entry, mock_api)

    device_reg = dr.async_get(hass)
    device_entry = device_reg.async_get_device(identifiers={(DOMAIN, "ap-1")})

    assert not await async_remove_config_entry_device(hass, mock_config_entry, device_entry)


async def test_remove_config_entry_device_returns_true_for_stale_access_point(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Stale access point (absent from coordinator data) allows device removal."""
    await setup_integration(hass, mock_config_entry, mock_api)

    mock_config_entry.runtime_data.data = {}

    device_reg = dr.async_get(hass)
    device_entry = device_reg.async_get_device(identifiers={(DOMAIN, "ap-1")})

    assert await async_remove_config_entry_device(hass, mock_config_entry, device_entry)
