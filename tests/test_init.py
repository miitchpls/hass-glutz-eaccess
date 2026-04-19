from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from glutz_eaccess import async_setup_entry, async_unload_entry

ENTRY_ID = "test_entry_id"

ENTRY_DATA = {
    "host": "https://example.com",
    "username": "user",
    "password": "secret",
}


def _make_hass():
    hass = MagicMock()
    hass.config.language = "en"
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    return hass


def _make_entry():
    entry = MagicMock()
    entry.entry_id = ENTRY_ID
    entry.data = ENTRY_DATA
    entry.runtime_data = None
    return entry


class TestAsyncSetupEntry:
    async def test_stores_coordinator_in_runtime_data(self):
        hass = _make_hass()
        entry = _make_entry()
        mock_coordinator = AsyncMock()

        with patch("glutz_eaccess.__init__.GlutzAPI"), patch(
            "glutz_eaccess.__init__.GlutzCoordinator", return_value=mock_coordinator
        ):
            result = await async_setup_entry(hass, entry)

        assert result is True
        assert entry.runtime_data is mock_coordinator

    async def test_calls_first_refresh(self):
        hass = _make_hass()
        entry = _make_entry()
        mock_coordinator = AsyncMock()

        with patch("glutz_eaccess.__init__.GlutzAPI"), patch(
            "glutz_eaccess.__init__.GlutzCoordinator", return_value=mock_coordinator
        ):
            await async_setup_entry(hass, entry)

        mock_coordinator.async_config_entry_first_refresh.assert_awaited_once()

    async def test_forwards_platform_setup(self):
        hass = _make_hass()
        entry = _make_entry()

        with patch("glutz_eaccess.__init__.GlutzAPI"), patch(
            "glutz_eaccess.__init__.GlutzCoordinator", return_value=AsyncMock()
        ):
            await async_setup_entry(hass, entry)

        hass.config_entries.async_forward_entry_setups.assert_awaited_once()

    async def test_api_created_with_correct_args(self):
        hass = _make_hass()
        entry = _make_entry()

        with patch("glutz_eaccess.__init__.GlutzAPI") as mock_api_cls, patch(
            "glutz_eaccess.__init__.GlutzCoordinator", return_value=AsyncMock()
        ):
            await async_setup_entry(hass, entry)

        mock_api_cls.assert_called_once_with(
            hass,
            "https://example.com",
            "user",
            "secret",
            language="en",
        )

    async def test_first_refresh_failure_propagates(self):
        hass = _make_hass()
        entry = _make_entry()
        mock_coordinator = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh = AsyncMock(
            side_effect=RuntimeError("boom")
        )

        with patch("glutz_eaccess.__init__.GlutzAPI"), patch(
            "glutz_eaccess.__init__.GlutzCoordinator", return_value=mock_coordinator
        ):
            try:
                await async_setup_entry(hass, entry)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Expected RuntimeError")

        hass.config_entries.async_forward_entry_setups.assert_not_awaited()


class TestAsyncUnloadEntry:
    async def test_delegates_to_unload_platforms(self):
        hass = _make_hass()
        entry = _make_entry()

        result = await async_unload_entry(hass, entry)

        assert result is True
        hass.config_entries.async_unload_platforms.assert_awaited_once()

    async def test_returns_false_when_unload_fails(self):
        hass = _make_hass()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
        entry = _make_entry()

        result = await async_unload_entry(hass, entry)

        assert result is False
