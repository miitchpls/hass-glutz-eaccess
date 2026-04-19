from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GlutzAPI, GlutzAuthError, GlutzConnectionError

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)

type GlutzConfigEntry = ConfigEntry["GlutzCoordinator"]


class GlutzCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls Glutz access points and exposes them keyed by accessPointId."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: GlutzAPI,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Glutz eAccess",
            update_interval=SCAN_INTERVAL,
            config_entry=entry,
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            access_points = await self.api.get_access_points()
        except GlutzAuthError as err:
            raise ConfigEntryAuthFailed("Invalid credentials") from err
        except GlutzConnectionError as err:
            raise UpdateFailed(str(err)) from err
        return {ap["accessPointId"]: ap for ap in access_points}
