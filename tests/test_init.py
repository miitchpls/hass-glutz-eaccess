from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from glutz_eaccess import async_setup_entry, async_unload_entry
from glutz_eaccess.api import GlutzAuthError, GlutzConnectionError
from glutz_eaccess.const import DOMAIN

ENTRY_ID = "test_entry_id"

ENTRY_DATA = {
    "host": "https://example.com",
    "username": "user",
    "password": "secret",
}


def _make_hass():
    hass = MagicMock()
    hass.data = {}
    hass.config.language = "en"
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    return hass


def _make_entry():
    entry = MagicMock()
    entry.entry_id = ENTRY_ID
    entry.data = ENTRY_DATA
    return entry


class TestAsyncSetupEntry:
    async def test_creates_api_and_stores_in_hass_data(self):
        hass = _make_hass()
        entry = _make_entry()
        mock_api = AsyncMock()

        with patch("glutz_eaccess.__init__.GlutzAPI", return_value=mock_api):
            result = await async_setup_entry(hass, entry)

        assert result is True
        assert hass.data[DOMAIN][ENTRY_ID] is mock_api

    async def test_api_created_with_correct_args(self):
        hass = _make_hass()
        entry = _make_entry()
        mock_api = AsyncMock()

        with patch("glutz_eaccess.__init__.GlutzAPI", return_value=mock_api) as mock_cls:
            await async_setup_entry(hass, entry)

        mock_cls.assert_called_once_with(
            hass,
            "https://example.com",
            "user",
            "secret",
            language="en",
        )

    async def test_forwards_platform_setup(self):
        hass = _make_hass()
        entry = _make_entry()
        mock_api = AsyncMock()

        with patch("glutz_eaccess.__init__.GlutzAPI", return_value=mock_api):
            await async_setup_entry(hass, entry)

        hass.config_entries.async_forward_entry_setups.assert_awaited_once()

    async def test_raises_auth_failed_on_invalid_credentials(self):
        hass = _make_hass()
        entry = _make_entry()
        mock_api = AsyncMock()
        mock_api.get_system_info = AsyncMock(side_effect=GlutzAuthError)

        with patch("glutz_eaccess.__init__.GlutzAPI", return_value=mock_api):
            with pytest.raises(ConfigEntryAuthFailed):
                await async_setup_entry(hass, entry)

        assert DOMAIN not in hass.data or ENTRY_ID not in hass.data.get(DOMAIN, {})
        hass.config_entries.async_forward_entry_setups.assert_not_awaited()

    async def test_raises_not_ready_on_connection_error(self):
        hass = _make_hass()
        entry = _make_entry()
        mock_api = AsyncMock()
        mock_api.get_system_info = AsyncMock(side_effect=GlutzConnectionError("boom"))

        with patch("glutz_eaccess.__init__.GlutzAPI", return_value=mock_api):
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, entry)

        hass.config_entries.async_forward_entry_setups.assert_not_awaited()


class TestAsyncUnloadEntry:
    async def test_removes_api_from_hass_data(self):
        hass = _make_hass()
        entry = _make_entry()
        mock_api = AsyncMock()
        hass.data[DOMAIN] = {ENTRY_ID: mock_api}

        result = await async_unload_entry(hass, entry)

        assert result is True
        assert ENTRY_ID not in hass.data[DOMAIN]

    async def test_keeps_api_when_unload_fails(self):
        hass = _make_hass()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
        entry = _make_entry()
        mock_api = AsyncMock()
        hass.data[DOMAIN] = {ENTRY_ID: mock_api}

        result = await async_unload_entry(hass, entry)

        assert result is False
        assert hass.data[DOMAIN][ENTRY_ID] is mock_api
