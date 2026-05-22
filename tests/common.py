"""Shim that re-exports tests.common from pytest-homeassistant-custom-component."""

from pytest_homeassistant_custom_component.common import *  # noqa: F401, F403
from pytest_homeassistant_custom_component.common import (  # noqa: F401
    MockConfigEntry,
    async_fire_time_changed,
    load_json_array_fixture,
    load_json_object_fixture,
    snapshot_platform,
)
