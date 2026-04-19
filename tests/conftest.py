from __future__ import annotations

import os
import sys
import types

import pytest
from unittest.mock import AsyncMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPONENT_ROOT = os.path.join(PROJECT_ROOT, "custom_components", "glutz_eaccess")

# Make the sibling `pyglutz_eaccess` package importable without installing it,
# so `.api` (a thin re-export) resolves during tests.
_PKG_SRC = os.path.join(PROJECT_ROOT, "packages", "pyglutz_eaccess", "src")
if _PKG_SRC not in sys.path:
    sys.path.insert(0, _PKG_SRC)

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

# homeassistant.exceptions
ha_exc = _stub_module("homeassistant.exceptions")
class _HomeAssistantError(Exception):
    pass
class _ConfigEntryAuthFailed(_HomeAssistantError):
    pass
class _ConfigEntryNotReady(_HomeAssistantError):
    pass
ha_exc.HomeAssistantError = _HomeAssistantError
ha_exc.ConfigEntryAuthFailed = _ConfigEntryAuthFailed
ha_exc.ConfigEntryNotReady = _ConfigEntryNotReady

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

    def async_abort(self, *, reason):
        return {"type": "abort", "reason": reason}

    def _async_current_entries(self):
        return []

    def _get_reauth_entry(self):
        return self._reauth_entry

    def async_update_reload_and_abort(self, entry, *, data_updates=None, data=None):
        return {
            "type": "abort",
            "reason": "reauth_successful",
            "entry": entry,
            "data_updates": data_updates,
            "data": data,
        }

ha_ce.ConfigEntry = _ConfigEntry
ha_ce.ConfigFlow = _ConfigFlow

# homeassistant.components.diagnostics
ha_diagnostics = _stub_module("homeassistant.components.diagnostics")
def _async_redact_data(data: dict, to_redact: set) -> dict:
    return {k: "**REDACTED**" if k in to_redact else v for k, v in data.items()}
ha_diagnostics.async_redact_data = _async_redact_data

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

# homeassistant.helpers.aiohttp_client
ha_aiohttp = _stub_module("homeassistant.helpers.aiohttp_client")
def _async_get_clientsession(hass):
    # Identity shim for tests: returns the hass mock itself so test assertions
    # can treat the "session" and "hass" as interchangeable when GlutzAPI /
    # resolve_instance_host / set_new_password are patched.
    return hass
ha_aiohttp.async_get_clientsession = _async_get_clientsession

# homeassistant.helpers.entity
ha_entity = _stub_module("homeassistant.helpers.entity")
class _DeviceInfo(dict):
    def __init__(self, **kwargs):
        super().__init__(kwargs)
ha_entity.DeviceInfo = _DeviceInfo

# homeassistant.helpers.update_coordinator
ha_uc = _stub_module("homeassistant.helpers.update_coordinator")

class _UpdateFailed(Exception):
    pass

class _DataUpdateCoordinator:
    def __init__(self, hass, logger, *, name, update_interval, config_entry=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.config_entry = config_entry
        self.data = None
        self.last_update_success = True

    async def async_config_entry_first_refresh(self) -> None:
        self.data = await self._async_update_data()

    async def _async_update_data(self):  # pragma: no cover - overridden
        raise NotImplementedError

    def __class_getitem__(cls, _item):
        return cls


class _CoordinatorEntity:
    _attr_available: bool = True

    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    def async_write_ha_state(self) -> None:
        pass

    def __class_getitem__(cls, _item):
        return cls


ha_uc.DataUpdateCoordinator = _DataUpdateCoordinator
ha_uc.CoordinatorEntity = _CoordinatorEntity
ha_uc.UpdateFailed = _UpdateFailed

# Top-level homeassistant
ha = _stub_module("homeassistant")
ha.config_entries = ha_ce

# ---------------------------------------------------------------------------
# Register the integration as the 'glutz_eaccess' package
# ---------------------------------------------------------------------------

if "glutz_eaccess" not in sys.modules:
    pkg = types.ModuleType("glutz_eaccess")
    pkg.__path__ = [COMPONENT_ROOT]
    pkg.__package__ = "glutz_eaccess"
    sys.modules["glutz_eaccess"] = pkg

# Force-load __init__.py into the package so top-level imports work
import importlib.util as _ilu

def _load_as(module_name: str, file_name: str) -> types.ModuleType:
    path = os.path.join(COMPONENT_ROOT, file_name)
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
_load_as("glutz_eaccess.coordinator", "coordinator.py")
_load_as("glutz_eaccess.config_flow", "config_flow.py")
_load_as("glutz_eaccess.lock", "lock.py")
_load_as("glutz_eaccess.diagnostics", "diagnostics.py")

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
    return api
