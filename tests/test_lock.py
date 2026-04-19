from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from pyglutz_eaccess import GlutzAuthError, GlutzConnectionError
from glutz_eaccess.lock import GlutzLock, async_setup_entry

AP_WITH_LOCATION = {"accessPointId": "ap-1", "location": ["Building A", "Floor 1", "Main Door"]}
AP_NO_LOCATION = {"accessPointId": "ap-2", "location": []}
AP_MISSING_LOCATION = {"accessPointId": "ap-3"}


def _make_coordinator(api, access_points: list[dict] | None = None) -> MagicMock:
    coordinator = MagicMock()
    coordinator.api = api
    coordinator.last_update_success = True
    coordinator.data = {
        ap["accessPointId"]: ap for ap in (access_points or [AP_WITH_LOCATION])
    }
    entry = MagicMock()
    entry.async_start_reauth = MagicMock()
    coordinator.config_entry = entry
    return coordinator


def _make_lock(api, access_point: dict, coordinator: MagicMock | None = None) -> GlutzLock:
    coordinator = coordinator or _make_coordinator(api, [access_point])
    lock = GlutzLock(coordinator, access_point)
    lock.hass = MagicMock()
    lock.hass.async_create_task = lambda coro: asyncio.ensure_future(coro)
    lock.async_write_ha_state = MagicMock()
    return lock


class TestAsyncSetupEntry:
    async def test_creates_one_entity_per_access_point(self, mock_api, sample_access_points):
        coordinator = _make_coordinator(mock_api, sample_access_points)
        entry = MagicMock()
        entry.runtime_data = coordinator

        added: list[GlutzLock] = []
        async_add_entities = MagicMock(side_effect=lambda it: added.extend(it))

        await async_setup_entry(MagicMock(), entry, async_add_entities)

        assert len(added) == len(sample_access_points)
        assert all(isinstance(e, GlutzLock) for e in added)


class TestGlutzLockInit:
    def test_entity_name_is_none(self, mock_api):
        lock = GlutzLock(_make_coordinator(mock_api), AP_WITH_LOCATION)
        assert lock._attr_name is None

    def test_device_name_from_last_location_element(self, mock_api):
        lock = GlutzLock(_make_coordinator(mock_api), AP_WITH_LOCATION)
        assert lock._device_name == "Main Door"

    def test_device_name_fallback_when_no_location(self, mock_api):
        lock = GlutzLock(_make_coordinator(mock_api), AP_NO_LOCATION)
        assert lock._device_name == "Door ap-2"

    def test_device_name_fallback_when_location_missing(self, mock_api):
        lock = GlutzLock(_make_coordinator(mock_api), AP_MISSING_LOCATION)
        assert lock._device_name == "Door ap-3"

    def test_unique_id(self, mock_api):
        lock = GlutzLock(_make_coordinator(mock_api), AP_WITH_LOCATION)
        assert lock._attr_unique_id == "glutz_ap-1"

    def test_initial_state_is_locked(self, mock_api):
        lock = GlutzLock(_make_coordinator(mock_api), AP_WITH_LOCATION)
        assert lock._attr_is_locked is True

    def test_device_info(self, mock_api):
        lock = GlutzLock(_make_coordinator(mock_api), AP_WITH_LOCATION)
        info = lock.device_info
        assert ("glutz_eaccess", "ap-1") in info["identifiers"]
        assert info["name"] == "Main Door"
        assert info["manufacturer"] == "Glutz"


class TestAvailability:
    def test_available_when_coordinator_healthy_and_ap_present(self, mock_api):
        coordinator = _make_coordinator(mock_api, [AP_WITH_LOCATION])
        lock = GlutzLock(coordinator, AP_WITH_LOCATION)
        assert lock.available is True

    def test_unavailable_when_coordinator_failed(self, mock_api):
        coordinator = _make_coordinator(mock_api, [AP_WITH_LOCATION])
        coordinator.last_update_success = False
        lock = GlutzLock(coordinator, AP_WITH_LOCATION)
        assert lock.available is False

    def test_unavailable_when_access_point_disappears(self, mock_api):
        coordinator = _make_coordinator(mock_api, [AP_WITH_LOCATION])
        lock = GlutzLock(coordinator, AP_WITH_LOCATION)
        coordinator.data = {}  # access point no longer reported
        assert lock.available is False


class TestAsyncUnlock:
    async def test_sets_unlocked_on_success(self, mock_api):
        lock = _make_lock(mock_api, AP_WITH_LOCATION)
        await lock.async_unlock()
        assert lock._attr_is_locked is False

    async def test_creates_relock_task(self, mock_api):
        lock = _make_lock(mock_api, AP_WITH_LOCATION)
        await lock.async_unlock()
        assert lock._relock_task is not None
        lock._relock_task.cancel()

    async def test_cancels_existing_relock_task_on_second_unlock(self, mock_api):
        lock = _make_lock(mock_api, AP_WITH_LOCATION)
        await lock.async_unlock()
        first_task = lock._relock_task
        await lock.async_unlock()
        await asyncio.sleep(0)
        assert first_task.cancelled()
        if lock._relock_task:
            lock._relock_task.cancel()

    async def test_connection_error_raises_without_mutating_available(self, mock_api):
        mock_api.open_access_point = AsyncMock(side_effect=GlutzConnectionError)
        lock = _make_lock(mock_api, AP_WITH_LOCATION)
        with pytest.raises(HomeAssistantError):
            await lock.async_unlock()
        # availability is now coordinator-driven; entity's _attr_available stays default
        assert lock._attr_is_locked is True

    async def test_raises_when_api_returns_false(self, mock_api):
        mock_api.open_access_point = AsyncMock(return_value=False)
        lock = _make_lock(mock_api, AP_WITH_LOCATION)
        with pytest.raises(HomeAssistantError):
            await lock.async_unlock()
        assert lock._attr_is_locked is True


class TestAsyncLock:
    async def test_sets_locked_on_success(self, mock_api):
        lock = _make_lock(mock_api, AP_WITH_LOCATION)
        lock._attr_is_locked = False
        await lock.async_lock()
        assert lock._attr_is_locked is True

    async def test_cancels_pending_relock_task(self, mock_api):
        lock = _make_lock(mock_api, AP_WITH_LOCATION)
        await lock.async_unlock()
        assert lock._relock_task is not None
        await lock.async_lock()
        assert lock._relock_task is None

    async def test_connection_error_raises(self, mock_api):
        mock_api.close_access_point = AsyncMock(side_effect=GlutzConnectionError)
        lock = _make_lock(mock_api, AP_WITH_LOCATION)
        with pytest.raises(HomeAssistantError):
            await lock.async_lock()

    async def test_raises_when_api_returns_false(self, mock_api):
        mock_api.close_access_point = AsyncMock(return_value=False)
        lock = _make_lock(mock_api, AP_WITH_LOCATION)
        lock._attr_is_locked = False
        with pytest.raises(HomeAssistantError):
            await lock.async_lock()
        assert lock._attr_is_locked is False


class TestRelock:
    async def test_relock_sets_locked_after_duration(self, mock_api):
        lock = _make_lock(mock_api, AP_WITH_LOCATION)

        with patch("glutz_eaccess.lock.asyncio.sleep", new_callable=AsyncMock):
            await lock.async_unlock()
            task = lock._relock_task
            if task:
                await task

        assert lock._attr_is_locked is True

    async def test_relock_clears_task_reference(self, mock_api):
        lock = _make_lock(mock_api, AP_WITH_LOCATION)

        with patch("glutz_eaccess.lock.asyncio.sleep", new_callable=AsyncMock):
            await lock.async_unlock()
            task = lock._relock_task
            if task:
                await task

        assert lock._relock_task is None


class TestAuthErrorTriggersReauth:
    async def test_unlock_auth_error_starts_reauth(self, mock_api):
        mock_api.open_access_point = AsyncMock(side_effect=GlutzAuthError)
        coordinator = _make_coordinator(mock_api, [AP_WITH_LOCATION])
        lock = _make_lock(mock_api, AP_WITH_LOCATION, coordinator=coordinator)

        with pytest.raises(HomeAssistantError):
            await lock.async_unlock()

        coordinator.config_entry.async_start_reauth.assert_called_once_with(lock.hass)

    async def test_lock_auth_error_starts_reauth(self, mock_api):
        mock_api.close_access_point = AsyncMock(side_effect=GlutzAuthError)
        coordinator = _make_coordinator(mock_api, [AP_WITH_LOCATION])
        lock = _make_lock(mock_api, AP_WITH_LOCATION, coordinator=coordinator)

        with pytest.raises(HomeAssistantError):
            await lock.async_lock()

        coordinator.config_entry.async_start_reauth.assert_called_once_with(lock.hass)

    async def test_unlock_connection_error_does_not_start_reauth(self, mock_api):
        mock_api.open_access_point = AsyncMock(side_effect=GlutzConnectionError)
        coordinator = _make_coordinator(mock_api, [AP_WITH_LOCATION])
        lock = _make_lock(mock_api, AP_WITH_LOCATION, coordinator=coordinator)

        with pytest.raises(HomeAssistantError):
            await lock.async_unlock()

        coordinator.config_entry.async_start_reauth.assert_not_called()
