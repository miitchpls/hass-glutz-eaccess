from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from glutz_eaccess import async_setup_entry, async_unload_entry
from glutz_eaccess.const import DOMAIN

ENTRY_ID = "test_entry_id"

ENTRY_DATA = {
    "host": "https://example.com",
    "username": "user",
    "password": "secret",
    "cert_pem": None,
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
            "https://example.com",
            "user",
            "secret",
            cert_pem=None,
            language="en",
        )

    async def test_forwards_platform_setup(self):
        hass = _make_hass()
        entry = _make_entry()
        mock_api = AsyncMock()

        with patch("glutz_eaccess.__init__.GlutzAPI", return_value=mock_api):
            await async_setup_entry(hass, entry)

        hass.config_entries.async_forward_entry_setups.assert_awaited_once()


class TestAsyncUnloadEntry:
    async def test_closes_api_on_unload(self):
        hass = _make_hass()
        entry = _make_entry()
        mock_api = AsyncMock()
        hass.data[DOMAIN] = {ENTRY_ID: mock_api}

        result = await async_unload_entry(hass, entry)

        assert result is True
        mock_api.close.assert_awaited_once()

    async def test_removes_api_from_hass_data(self):
        hass = _make_hass()
        entry = _make_entry()
        mock_api = AsyncMock()
        hass.data[DOMAIN] = {ENTRY_ID: mock_api}

        await async_unload_entry(hass, entry)

        assert ENTRY_ID not in hass.data[DOMAIN]

    async def test_does_not_close_api_if_unload_fails(self):
        hass = _make_hass()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
        entry = _make_entry()
        mock_api = AsyncMock()
        hass.data[DOMAIN] = {ENTRY_ID: mock_api}

        result = await async_unload_entry(hass, entry)

        assert result is False
        mock_api.close.assert_not_awaited()
