"""Shim that re-exports tests.common from pytest-homeassistant-custom-component."""

from pytest_homeassistant_custom_component.common import *  # noqa: F401, F403
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    snapshot_platform,
)
