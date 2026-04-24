"""Tests for the Glutz eAccess lock platform."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.components.lock import (
    DOMAIN as LOCK_DOMAIN,
    SERVICE_LOCK,
    SERVICE_OPEN,
    SERVICE_UNLOCK,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_LOCKED,
    STATE_UNAVAILABLE,
    STATE_UNLOCKED,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from pyglutz_eaccess import GlutzAuthError, GlutzConnectionError
from homeassistant.components.glutz_eaccess.const import DOMAIN
from homeassistant.components.glutz_eaccess.coordinator import SCAN_INTERVAL
from homeassistant.components.glutz_eaccess.lock import UNLOCK_DURATION

MAIN_DOOR = "lock.main_door"
FALLBACK_DOOR = "lock.door_ap_2"


async def _call_service(hass: HomeAssistant, service: str, entity_id: str) -> None:
    await hass.services.async_call(
        LOCK_DOMAIN, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )


async def test_setup_creates_entity_per_access_point(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """One lock entity is created for each access point returned by the API."""
    await setup_integration(hass, mock_config_entry, mock_api)

    assert hass.states.get(MAIN_DOOR) is not None
    assert hass.states.get(FALLBACK_DOOR) is not None


async def test_entity_name_falls_back_to_access_point_id(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Device name falls back to 'Door <id>' when no location is reported."""
    await setup_integration(hass, mock_config_entry, mock_api)

    assert hass.states.get(FALLBACK_DOOR).attributes["friendly_name"] == "Door ap-2"


async def test_initial_state_is_locked(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """A newly-created entity starts in the locked state."""
    await setup_integration(hass, mock_config_entry, mock_api)

    assert hass.states.get(MAIN_DOOR).state == STATE_LOCKED


async def test_unlock_calls_api_and_updates_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """The unlock service calls the API and flips the state to unlocked."""
    await setup_integration(hass, mock_config_entry, mock_api)

    await _call_service(hass, SERVICE_UNLOCK, MAIN_DOOR)

    mock_api.open_access_point.assert_awaited_once_with("ap-1")
    assert hass.states.get(MAIN_DOOR).state == STATE_UNLOCKED


async def test_auto_relock_returns_state_to_locked(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
    freezer,
) -> None:
    """After UNLOCK_DURATION the entity reverts to locked automatically."""
    await setup_integration(hass, mock_config_entry, mock_api)

    await _call_service(hass, SERVICE_UNLOCK, MAIN_DOOR)
    assert hass.states.get(MAIN_DOOR).state == STATE_UNLOCKED

    freezer.tick(UNLOCK_DURATION + 1)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(MAIN_DOOR).state == STATE_LOCKED


async def test_lock_cancels_pending_auto_relock(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Calling lock while an auto-relock is pending cancels it cleanly."""
    await setup_integration(hass, mock_config_entry, mock_api)

    await _call_service(hass, SERVICE_UNLOCK, MAIN_DOOR)
    await _call_service(hass, SERVICE_LOCK, MAIN_DOOR)

    mock_api.close_access_point.assert_awaited_once_with("ap-1")
    assert hass.states.get(MAIN_DOOR).state == STATE_LOCKED


async def test_unlock_connection_error_raises_and_preserves_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Transient connection errors surface as HomeAssistantError; state stays locked."""
    await setup_integration(hass, mock_config_entry, mock_api)
    mock_api.open_access_point = AsyncMock(side_effect=GlutzConnectionError("boom"))

    with pytest.raises(HomeAssistantError):
        await _call_service(hass, SERVICE_UNLOCK, MAIN_DOOR)

    assert hass.states.get(MAIN_DOOR).state == STATE_LOCKED


async def test_unlock_api_returns_false_raises(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """When the API reports failure we raise without flipping state."""
    await setup_integration(hass, mock_config_entry, mock_api)
    mock_api.open_access_point = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError):
        await _call_service(hass, SERVICE_UNLOCK, MAIN_DOOR)

    assert hass.states.get(MAIN_DOOR).state == STATE_LOCKED


async def test_lock_api_returns_false_raises(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """When close_access_point returns False we raise and state stays unlocked."""
    await setup_integration(hass, mock_config_entry, mock_api)
    await _call_service(hass, SERVICE_UNLOCK, MAIN_DOOR)
    mock_api.close_access_point = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError):
        await _call_service(hass, SERVICE_LOCK, MAIN_DOOR)

    assert hass.states.get(MAIN_DOOR).state == STATE_UNLOCKED


async def test_open_calls_api_and_updates_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """The open service calls hold_open and flips the state to unlocked without scheduling a relock."""
    await setup_integration(hass, mock_config_entry, mock_api)

    await _call_service(hass, SERVICE_OPEN, MAIN_DOOR)

    mock_api.hold_open_access_point.assert_awaited_once_with("ap-1")
    assert hass.states.get(MAIN_DOOR).state == STATE_UNLOCKED


async def test_open_does_not_auto_relock(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
    freezer,
) -> None:
    """After open, the door stays unlocked even past UNLOCK_DURATION."""
    await setup_integration(hass, mock_config_entry, mock_api)

    await _call_service(hass, SERVICE_OPEN, MAIN_DOOR)

    freezer.tick(UNLOCK_DURATION + 1)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(MAIN_DOOR).state == STATE_UNLOCKED


async def test_open_cancels_pending_auto_relock(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
    freezer,
) -> None:
    """Open while a relock is pending cancels it."""
    await setup_integration(hass, mock_config_entry, mock_api)

    await _call_service(hass, SERVICE_UNLOCK, MAIN_DOOR)
    await _call_service(hass, SERVICE_OPEN, MAIN_DOOR)

    freezer.tick(UNLOCK_DURATION + 1)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(MAIN_DOOR).state == STATE_UNLOCKED


async def test_open_connection_error_raises_and_preserves_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Transient connection error on open surfaces as HomeAssistantError; state stays locked."""
    await setup_integration(hass, mock_config_entry, mock_api)
    mock_api.hold_open_access_point = AsyncMock(side_effect=GlutzConnectionError("boom"))

    with pytest.raises(HomeAssistantError):
        await _call_service(hass, SERVICE_OPEN, MAIN_DOOR)

    assert hass.states.get(MAIN_DOOR).state == STATE_LOCKED


async def test_open_api_returns_false_raises(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """When hold_open_access_point returns False we raise without flipping state."""
    await setup_integration(hass, mock_config_entry, mock_api)
    mock_api.hold_open_access_point = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError):
        await _call_service(hass, SERVICE_OPEN, MAIN_DOOR)

    assert hass.states.get(MAIN_DOOR).state == STATE_LOCKED


@pytest.mark.parametrize("service", [SERVICE_UNLOCK, SERVICE_LOCK])
async def test_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
    service: str,
) -> None:
    """Auth failure on either lock or unlock triggers a reauth flow."""
    await setup_integration(hass, mock_config_entry, mock_api)
    method = "open_access_point" if service == SERVICE_UNLOCK else "close_access_point"
    setattr(mock_api, method, AsyncMock(side_effect=GlutzAuthError("nope")))

    with pytest.raises(HomeAssistantError):
        await _call_service(hass, service, MAIN_DOOR)

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"].get("source") == "reauth" for f in flows)


async def test_open_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Auth failure on open triggers a reauth flow."""
    await setup_integration(hass, mock_config_entry, mock_api)
    mock_api.hold_open_access_point = AsyncMock(side_effect=GlutzAuthError("nope"))

    with pytest.raises(HomeAssistantError):
        await _call_service(hass, SERVICE_OPEN, MAIN_DOOR)

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"].get("source") == "reauth" for f in flows)


async def test_entity_unavailable_when_coordinator_fails(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
    freezer,
) -> None:
    """Coordinator update failure propagates to entity availability."""
    await setup_integration(hass, mock_config_entry, mock_api)

    mock_api.get_access_points = AsyncMock(side_effect=GlutzConnectionError("down"))
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(MAIN_DOOR).state == STATE_UNAVAILABLE


async def test_entity_unavailable_when_access_point_disappears(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
    freezer,
) -> None:
    """An entity becomes unavailable if its access point vanishes from the API."""
    await setup_integration(hass, mock_config_entry, mock_api)

    mock_api.get_access_points = AsyncMock(
        return_value=[{"accessPointId": "ap-2", "location": []}]
    )
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(MAIN_DOOR).state == STATE_UNAVAILABLE
    assert hass.states.get(FALLBACK_DOOR).state == STATE_LOCKED
