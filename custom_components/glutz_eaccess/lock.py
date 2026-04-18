from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import GlutzAPI, GlutzAuthError, GlutzConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Duration in seconds to show the lock as unlocked before reverting to locked.
# Matches the physical door's automatic re-lock time.
UNLOCK_DURATION = 3


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a GlutzLock entity for each access point returned by the API."""
    api: GlutzAPI = hass.data[DOMAIN][entry.entry_id]
    access_points = await api.get_access_points()
    async_add_entities(GlutzLock(api, entry, ap) for ap in access_points)


class GlutzLock(LockEntity):
    """Represents a Glutz access point as a Home Assistant lock entity.

    Since the door has no state feedback (it re-locks automatically after
    a few seconds), the state is simulated: unlocked for UNLOCK_DURATION
    seconds, then reverted to locked.
    """

    _attr_has_entity_name = True
    _attr_assumed_state = True

    _attr_name = None

    def __init__(
        self,
        api: GlutzAPI,
        entry: ConfigEntry,
        access_point: dict[str, Any],
    ) -> None:
        self._api = api
        self._entry = entry
        self._access_point_id: str = access_point["accessPointId"]
        location: list[str] = access_point.get("location", [])
        self._device_name = (
            location[-1] if location else f"Door {self._access_point_id}"
        )
        self._attr_unique_id = f"glutz_{self._access_point_id}"
        self._attr_is_locked = True
        self._attr_available = True
        self._relock_task: asyncio.Task[None] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._access_point_id)},
            name=self._device_name,
            manufacturer="Glutz",
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the door by calling the Glutz API, then revert state after UNLOCK_DURATION."""
        try:
            success = await self._api.open_access_point(self._access_point_id)
        except GlutzAuthError as err:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                f"Authentication failed for access point {self._access_point_id}"
            ) from err
        except GlutzConnectionError as err:
            self._attr_available = False
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Error opening access point {self._access_point_id}: {err}"
            ) from err

        if not self._attr_available:
            self._attr_available = True
            self.async_write_ha_state()
        if not success:
            raise HomeAssistantError(
                f"Failed to open access point {self._access_point_id}"
            )
        self._attr_is_locked = False
        self.async_write_ha_state()
        if self._relock_task:
            self._relock_task.cancel()
        self._relock_task = self.hass.async_create_task(self._relock())

    async def async_lock(self, **kwargs: Any) -> None:
        """Force-lock the door via the API and cancel any pending auto-relock."""
        try:
            success = await self._api.close_access_point(self._access_point_id)
        except GlutzAuthError as err:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                f"Authentication failed for access point {self._access_point_id}"
            ) from err
        except GlutzConnectionError as err:
            self._attr_available = False
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Error locking access point {self._access_point_id}: {err}"
            ) from err

        if not self._attr_available:
            self._attr_available = True
        if not success:
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Failed to lock access point {self._access_point_id}"
            )
        if self._relock_task:
            self._relock_task.cancel()
            self._relock_task = None
        self._attr_is_locked = True
        self.async_write_ha_state()

    async def _relock(self) -> None:
        await asyncio.sleep(UNLOCK_DURATION)
        self._relock_task = None
        self._attr_is_locked = True
        self.async_write_ha_state()
