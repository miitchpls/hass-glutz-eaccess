"""Tests for the Glutz eAccess diagnostics."""
from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.glutz_eaccess.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_entry_diagnostics_redacts_password(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration,
) -> None:
    """Password must be redacted in diagnostics; other fields preserved."""
    await setup_integration(hass, mock_config_entry, mock_api)

    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diag[CONF_PASSWORD] == "**REDACTED**"
    assert diag[CONF_HOST] == "https://example.com"
    assert diag[CONF_USERNAME] == "user"
