from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import CONF_CERT_PEM

_TO_REDACT = {CONF_PASSWORD, CONF_CERT_PEM}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    return async_redact_data(dict(entry.data), _TO_REDACT)
