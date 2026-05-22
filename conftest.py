"""Root conftest: inject local integration and HA core test shims into sys.modules."""

import sys
from pathlib import Path
from types import ModuleType

import homeassistant.components
import pytest_homeassistant_custom_component.common as _phcc_common
import pytest_homeassistant_custom_component.typing as _phcc_typing

# ---------------------------------------------------------------------------
# Make the local integration visible as homeassistant.components.glutz_eaccess
# ---------------------------------------------------------------------------
homeassistant.components.__path__.append(
    str(Path(__file__).parent / "homeassistant" / "components")
)

# ---------------------------------------------------------------------------
# tests.common  →  pytest_homeassistant_custom_component.common
# ---------------------------------------------------------------------------
_tests_common = ModuleType("tests.common")
_tests_common.__dict__.update(
    {k: v for k, v in vars(_phcc_common).items() if not k.startswith("__")}
)
sys.modules.setdefault("tests", ModuleType("tests"))
sys.modules["tests.common"] = _tests_common

# ---------------------------------------------------------------------------
# tests.typing  →  pytest_homeassistant_custom_component.typing
# ---------------------------------------------------------------------------
_tests_typing = ModuleType("tests.typing")
_tests_typing.__dict__.update(
    {k: v for k, v in vars(_phcc_typing).items() if not k.startswith("__")}
)
sys.modules["tests.typing"] = _tests_typing

# ---------------------------------------------------------------------------
# tests.components.diagnostics  →  minimal implementation
# ---------------------------------------------------------------------------
_tests_components = ModuleType("tests.components")
sys.modules["tests.components"] = _tests_components


async def _get_diagnostics_for_config_entry(hass, hass_client, config_entry):
    client = await hass_client()
    response = await client.get(
        f"/api/diagnostics/config_entry/{config_entry.entry_id}"
    )
    return await response.json()


_tests_diag = ModuleType("tests.components.diagnostics")
_tests_diag.get_diagnostics_for_config_entry = _get_diagnostics_for_config_entry
sys.modules["tests.components.diagnostics"] = _tests_diag
