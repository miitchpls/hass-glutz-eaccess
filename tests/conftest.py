from __future__ import annotations

import os
import sys
import types

import pytest
from unittest.mock import AsyncMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Minimal HomeAssistant stubs — avoids installing the full HA package
# ---------------------------------------------------------------------------

def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# homeassistant.const
ha_const = _stub_module("homeassistant.const")
ha_const.CONF_HOST = "host"
ha_const.CONF_USERNAME = "username"
ha_const.CONF_PASSWORD = "password"

class _Platform:
    LOCK = "lock"

ha_const.Platform = _Platform

# homeassistant.core
ha_core = _stub_module("homeassistant.core")
ha_core.HomeAssistant = object

# homeassistant.config_entries
ha_ce = _stub_module("homeassistant.config_entries")

class _ConfigEntry:
    pass

class _ConfigFlow:
    VERSION = 1

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    def async_show_form(self, *, step_id, data_schema=None, errors=None):
        return {"type": "form", "step_id": step_id, "errors": errors or {}}

    def async_create_entry(self, *, title, data):
        return {"type": "create_entry", "title": title, "data": data}

ha_ce.ConfigEntry = _ConfigEntry
ha_ce.ConfigFlow = _ConfigFlow

# homeassistant.components.lock
ha_components = _stub_module("homeassistant.components")
ha_lock = _stub_module("homeassistant.components.lock")

class _LockEntity:
    _attr_is_locked: bool | None = None
    _attr_available: bool = True
    _attr_assumed_state: bool = False
    _attr_has_entity_name: bool = False
    hass = None

    def async_write_ha_state(self) -> None:
        pass

ha_lock.LockEntity = _LockEntity

# homeassistant.helpers.entity_platform
ha_helpers = _stub_module("homeassistant.helpers")
ha_ep = _stub_module("homeassistant.helpers.entity_platform")
ha_ep.AddEntitiesCallback = object

# homeassistant.helpers.entity
ha_entity = _stub_module("homeassistant.helpers.entity")
class _DeviceInfo(dict):
    def __init__(self, **kwargs):
        super().__init__(kwargs)
ha_entity.DeviceInfo = _DeviceInfo

# Top-level homeassistant
ha = _stub_module("homeassistant")
ha.config_entries = ha_ce

# ---------------------------------------------------------------------------
# Register the integration as the 'glutz_eaccess' package
# ---------------------------------------------------------------------------

if "glutz_eaccess" not in sys.modules:
    pkg = types.ModuleType("glutz_eaccess")
    pkg.__path__ = [PROJECT_ROOT]
    pkg.__package__ = "glutz_eaccess"
    sys.modules["glutz_eaccess"] = pkg

# Force-load __init__.py into the package so top-level imports work
import importlib.util as _ilu

def _load_as(module_name: str, file_name: str) -> types.ModuleType:
    path = os.path.join(PROJECT_ROOT, file_name)
    spec = _ilu.spec_from_file_location(
        module_name, path,
        submodule_search_locations=[] if file_name == "__init__.py" else None,
    )
    mod = _ilu.module_from_spec(spec)
    mod.__package__ = "glutz_eaccess"
    mod.__name__ = module_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load in dependency order (api first, no relative imports)
_load_as("glutz_eaccess.const", "const.py")
_load_as("glutz_eaccess.api", "api.py")
_load_as("glutz_eaccess.config_flow", "config_flow.py")
_load_as("glutz_eaccess.lock", "lock.py")

# Load __init__.py and expose its exports on the package
_init = _load_as("glutz_eaccess.__init__", "__init__.py")
_pkg = sys.modules["glutz_eaccess"]
_pkg.async_setup_entry = _init.async_setup_entry
_pkg.async_unload_entry = _init.async_unload_entry

# Prevent pytest from re-importing the project root's __init__.py when it
# initialises the root directory as a package (it would fail without context).
sys.modules.setdefault("__init__", _init)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_ACCESS_POINTS = [
    {"accessPointId": "ap-1", "location": ["Building A", "Floor 1", "Main Door"]},
    {"accessPointId": "ap-2", "location": []},
]


@pytest.fixture
def sample_access_points():
    return list(SAMPLE_ACCESS_POINTS)


@pytest.fixture
def mock_api():
    api = AsyncMock()
    api.open_access_point = AsyncMock(return_value=True)
    api.close_access_point = AsyncMock(return_value=True)
    api.get_access_points = AsyncMock(return_value=list(SAMPLE_ACCESS_POINTS))
    api.close = AsyncMock()
    return api
