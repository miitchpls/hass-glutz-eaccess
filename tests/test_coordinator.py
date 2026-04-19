from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from pyglutz_eaccess import GlutzAuthError, GlutzConnectionError
from glutz_eaccess.coordinator import SCAN_INTERVAL, GlutzCoordinator


def _make_coordinator(api) -> GlutzCoordinator:
    return GlutzCoordinator(MagicMock(), api, MagicMock())


class TestGlutzCoordinator:
    def test_stores_api(self):
        api = MagicMock()
        coordinator = _make_coordinator(api)
        assert coordinator.api is api

    def test_update_interval_matches_scan_interval(self):
        coordinator = _make_coordinator(MagicMock())
        assert coordinator.update_interval == SCAN_INTERVAL

    def test_config_entry_is_linked(self):
        entry = MagicMock()
        coordinator = GlutzCoordinator(MagicMock(), MagicMock(), entry)
        assert coordinator.config_entry is entry

    async def test_returns_dict_keyed_by_access_point_id(self):
        api = MagicMock()
        api.get_access_points = AsyncMock(
            return_value=[
                {"accessPointId": "ap-1", "location": ["A"]},
                {"accessPointId": "ap-2", "location": ["B"]},
            ]
        )
        coordinator = _make_coordinator(api)

        data = await coordinator._async_update_data()

        assert set(data.keys()) == {"ap-1", "ap-2"}
        assert data["ap-1"]["location"] == ["A"]

    async def test_auth_error_raises_config_entry_auth_failed(self):
        api = MagicMock()
        api.get_access_points = AsyncMock(side_effect=GlutzAuthError("bad creds"))
        coordinator = _make_coordinator(api)

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

    async def test_connection_error_raises_update_failed(self):
        api = MagicMock()
        api.get_access_points = AsyncMock(side_effect=GlutzConnectionError("down"))
        coordinator = _make_coordinator(api)

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    async def test_first_refresh_populates_data(self):
        api = MagicMock()
        api.get_access_points = AsyncMock(
            return_value=[{"accessPointId": "ap-1"}]
        )
        coordinator = _make_coordinator(api)

        await coordinator.async_config_entry_first_refresh()

        assert coordinator.data == {"ap-1": {"accessPointId": "ap-1"}}
