"""Tests for the Glutz eAccess coordinator."""
from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from pyglutz_eaccess import GlutzAuthError, GlutzConnectionError
from custom_components.glutz_eaccess.const import DOMAIN
from custom_components.glutz_eaccess.coordinator import SCAN_INTERVAL


async def test_initial_refresh_populates_data_keyed_by_access_point_id(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """First refresh exposes access points as a dict keyed by accessPointId."""
    await setup_integration(hass, mock_config_entry, mock_api)

    data = mock_config_entry.runtime_data.data
    assert set(data.keys()) == {"ap-1", "ap-2"}
    assert data["ap-1"]["location"] == ["Building A", "Floor 1", "Main Door"]


async def test_connection_error_keeps_entry_in_setup_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Transient connection error during first refresh leads to SETUP_RETRY."""
    mock_api.get_access_points = AsyncMock(side_effect=GlutzConnectionError("boom"))

    await setup_integration(hass, mock_config_entry, mock_api)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_auth_error_triggers_reauth_flow(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Auth failure during first refresh starts a reauth flow."""
    mock_api.get_access_points = AsyncMock(side_effect=GlutzAuthError("bad creds"))

    await setup_integration(hass, mock_config_entry, mock_api)

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"].get("source") == "reauth" for f in flows)


async def test_scheduled_update_reflects_latest_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
    freezer,
) -> None:
    """A scheduled refresh picks up the updated access point list."""
    await setup_integration(hass, mock_config_entry, mock_api)

    mock_api.get_access_points = AsyncMock(
        return_value=[{"accessPointId": "ap-9", "location": ["New"]}]
    )
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert set(mock_config_entry.runtime_data.data.keys()) == {"ap-9"}


async def test_connection_error_during_update_marks_unsuccessful(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
    freezer,
) -> None:
    """A connection failure on a scheduled update flips last_update_success to False."""
    await setup_integration(hass, mock_config_entry, mock_api)
    coordinator = mock_config_entry.runtime_data

    mock_api.get_access_points = AsyncMock(side_effect=GlutzConnectionError("down"))
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False
