"""Tests for the Glutz eAccess integration."""

from homeassistant.components.homeassistant import DOMAIN as HA_DOMAIN
from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_load_integrations
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry


async def setup_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Set up the Glutz eAccess integration for testing."""
    # Preload translations for the core "homeassistant" integration so the
    # autouse check_translations fixture can resolve issues.config_entry_reauth.*
    # when ConfigEntryAuthFailed triggers HA's built-in reauth repair issue.
    await async_load_integrations(hass, {HA_DOMAIN})
    await async_setup_component(hass, LOCK_DOMAIN, {})
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
