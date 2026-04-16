from __future__ import annotations

import asyncio
import logging

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import GlutzAPI, GlutzConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

UNLOCK_DURATION = 3


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a GlutzLock entity for each access point returned by the API."""
    api: GlutzAPI = hass.data[DOMAIN][entry.entry_id]
    access_points = await api.get_access_points()
    async_add_entities(GlutzLock(api, ap) for ap in access_points)


class GlutzLock(LockEntity):
    """Represents a Glutz access point as a Home Assistant lock entity.

    Since the door has no state feedback (it re-locks automatically after
    a few seconds), the state is simulated: unlocked for UNLOCK_DURATION
    seconds, then reverted to locked.
    """

    _attr_has_entity_name = True
    _attr_assumed_state = True

    def __init__(self, api: GlutzAPI, access_point: dict) -> None:
        self._api = api
        self._access_point_id: str = access_point["accessPointId"]
        self._default_action: int = access_point["defaultActions"]
        location: list[str] = access_point.get("location", [])
        self._attr_name = location[-1] if location else f"Door {self._access_point_id}"
        self._attr_unique_id = f"glutz_{self._access_point_id}"
        self._attr_is_locked = True

    async def async_unlock(self, **kwargs) -> None:
        """Unlock the door by calling the Glutz API, then revert state after UNLOCK_DURATION."""
        try:
            success = await self._api.open_access_point(
                self._access_point_id, self._default_action
            )
            if success:
                self._attr_is_locked = False
                self.async_write_ha_state()
                self.hass.async_create_task(self._relock())
            else:
                _LOGGER.error("Failed to open access point %s", self._access_point_id)
        except GlutzConnectionError as err:
            _LOGGER.error("Error opening access point %s: %s", self._access_point_id, err)

    async def _relock(self) -> None:
        await asyncio.sleep(UNLOCK_DURATION)
        self._attr_is_locked = True
        self.async_write_ha_state()
