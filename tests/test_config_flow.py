"""Tests for the Glutz eAccess config flow."""
from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from pyglutz_eaccess import GlutzAuthError, GlutzConnectionError
from homeassistant.components.glutz_eaccess.config_flow import _is_valid_password
from homeassistant.components.glutz_eaccess.const import DOMAIN

CREDENTIALS_INPUT = {
    CONF_HOST: "https://example.com",
    CONF_USERNAME: "user",
    CONF_PASSWORD: "secret",
}

CONFIRM_INPUT = {
    CONF_HOST: "https://instance.example.com",
    CONF_USERNAME: "user@example.com",
    CONF_PASSWORD: "Secure1!",
}

REAUTH_INPUT = {
    CONF_HOST: "https://new.example.com",
    CONF_USERNAME: "new@example.com",
    CONF_PASSWORD: "new_password",
}

INVITE_URL = (
    "https://eaccess.ac.glutz.com/invite///cloud.eaccess.glutz.com/building-name"
    "?systemid=SYS123&email=user%40example.com&token=TOK123"
)


@contextlib.contextmanager
def _patch_api(api: AsyncMock):
    """Mock GlutzAPI at both import sites.

    `config_flow.py` and `__init__.py` each do `from pyglutz_eaccess import
    GlutzAPI`, so they hold independent references. After `CREATE_ENTRY`,
    `async_setup_entry` runs and uses `__init__.GlutzAPI`, so both must be
    mocked to avoid the real client being instantiated.
    """
    with (
        patch(
            "homeassistant.components.glutz_eaccess.config_flow.GlutzAPI", return_value=api
        ),
        patch("homeassistant.components.glutz_eaccess.GlutzAPI", return_value=api),
    ):
        yield


async def _start_flow(hass: HomeAssistant) -> dict:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def _start_step(hass: HomeAssistant, step: str) -> dict:
    menu = await _start_flow(hass)
    return await hass.config_entries.flow.async_configure(
        menu["flow_id"], {"next_step_id": step}
    )


async def _advance_to_invitation_confirm(hass: HomeAssistant) -> dict:
    result = await _start_step(hass, "invitation")
    with patch(
        "homeassistant.components.glutz_eaccess.config_flow.resolve_instance_host",
        return_value="instance.example.com",
    ):
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {"invite_url": INVITE_URL}
        )


class TestIsValidPassword:
    """Unit tests for the password policy helper."""

    def test_valid_password(self) -> None:
        assert _is_valid_password("Secure1!") is True

    def test_missing_uppercase(self) -> None:
        assert _is_valid_password("secure1!") is False

    def test_missing_lowercase(self) -> None:
        assert _is_valid_password("SECURE1!") is False

    def test_missing_digit(self) -> None:
        assert _is_valid_password("Secure!!") is False

    def test_missing_special(self) -> None:
        assert _is_valid_password("Secure123") is False

    def test_too_short(self) -> None:
        assert _is_valid_password("Sec1!") is False

    def test_unicode_special_char(self) -> None:
        assert _is_valid_password("Secure1€") is True

    def test_space_counts_as_special(self) -> None:
        assert _is_valid_password("Secure1 ") is True


async def test_user_step_shows_menu(hass: HomeAssistant) -> None:
    """The initial user step offers credentials or invitation entry points."""
    result = await _start_flow(hass)

    assert result["type"] == FlowResultType.MENU
    assert set(result["menu_options"]) == {"credentials", "invitation"}


# --- credentials step --------------------------------------------------------


async def test_credentials_step_shows_form(hass: HomeAssistant) -> None:
    """Selecting credentials presents the input form."""
    result = await _start_step(hass, "credentials")

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "credentials"


async def test_credentials_success_creates_entry(
    hass: HomeAssistant, mock_api: AsyncMock
) -> None:
    """Valid credentials and system info create the config entry."""
    result = await _start_step(hass, "credentials")
    mock_api.get_system_info = AsyncMock(
        return_value={"id": "SYS1", "name": "Palazzo Rossi"}
    )

    with _patch_api(mock_api):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENTIALS_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Palazzo Rossi"
    assert result["data"] == CREDENTIALS_INPUT
    assert result["result"].unique_id == "SYS1"


async def test_credentials_missing_system_name_uses_default_title(
    hass: HomeAssistant, mock_api: AsyncMock
) -> None:
    """A system without a `name` field falls back to the default title."""
    result = await _start_step(hass, "credentials")
    mock_api.get_system_info = AsyncMock(return_value={"id": "SYS1"})

    with _patch_api(mock_api):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENTIALS_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Glutz eAccess"


async def test_credentials_missing_system_id_errors_cannot_connect(
    hass: HomeAssistant, mock_api: AsyncMock
) -> None:
    """Without a system id we can't uniquely identify the installation."""
    result = await _start_step(hass, "credentials")
    mock_api.get_system_info = AsyncMock(return_value={"name": "Palazzo"})

    with patch(
        "homeassistant.components.glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENTIALS_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (GlutzAuthError, "invalid_auth"),
        (GlutzConnectionError, "cannot_connect"),
    ],
)
async def test_credentials_api_errors_map_to_form_errors(
    hass: HomeAssistant, mock_api: AsyncMock, error, expected
) -> None:
    """API-level failures surface as recoverable form errors."""
    result = await _start_step(hass, "credentials")
    mock_api.get_access_points = AsyncMock(side_effect=error)

    with patch(
        "homeassistant.components.glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENTIALS_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_credentials_aborts_when_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
) -> None:
    """A second entry for the same system aborts with already_configured."""
    mock_config_entry.add_to_hass(hass)
    result = await _start_step(hass, "credentials")

    with patch(
        "homeassistant.components.glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENTIALS_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# --- invitation step ---------------------------------------------------------


async def test_invitation_step_shows_form(hass: HomeAssistant) -> None:
    """Selecting invitation presents the URL input form."""
    result = await _start_step(hass, "invitation")

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "invitation"


async def test_invitation_invalid_url_errors(hass: HomeAssistant) -> None:
    """A malformed invitation URL produces an invitation-specific error."""
    result = await _start_step(hass, "invitation")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"invite_url": "not a valid url"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_invitation"}


async def test_invitation_resolve_failure_errors_cannot_connect(
    hass: HomeAssistant,
) -> None:
    """Instance host resolution failure maps to cannot_connect."""
    result = await _start_step(hass, "invitation")

    with patch(
        "homeassistant.components.glutz_eaccess.config_flow.resolve_instance_host",
        side_effect=GlutzConnectionError,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"invite_url": INVITE_URL}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_invitation_success_advances_to_confirm(hass: HomeAssistant) -> None:
    """Successful resolution advances to the password-set confirmation step."""
    result = await _advance_to_invitation_confirm(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "invitation_confirm"


# --- invitation confirm step -------------------------------------------------


async def test_invitation_confirm_weak_password_errors(hass: HomeAssistant) -> None:
    """A password that doesn't match the policy shows an invalid_password error."""
    result = await _advance_to_invitation_confirm(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CONFIRM_INPUT, CONF_PASSWORD: "weak"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_password"}


async def test_invitation_confirm_success_creates_entry(
    hass: HomeAssistant, mock_api: AsyncMock
) -> None:
    """Setting the password and fetching system info creates the entry."""
    result = await _advance_to_invitation_confirm(hass)
    mock_api.get_system_info = AsyncMock(
        return_value={"id": "SYS-API", "name": "Palazzo Rossi"}
    )

    with (
        _patch_api(mock_api),
        patch(
            "homeassistant.components.glutz_eaccess.config_flow.set_new_password",
            new=AsyncMock(),
        ) as mock_setpw,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CONFIRM_INPUT
        )
        await hass.async_block_till_done()

    mock_setpw.assert_awaited_once()
    _, host, token, password = mock_setpw.await_args.args
    assert host == "instance.example.com"
    assert token == "TOK123"
    assert password == "Secure1!"
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Palazzo Rossi"
    assert result["data"] == CONFIRM_INPUT
    assert result["result"].unique_id == "SYS-API"


async def test_invitation_confirm_falls_back_to_invitation_system_id(
    hass: HomeAssistant, mock_api: AsyncMock
) -> None:
    """If get_system_info fails we still create the entry using the invitation's id."""
    result = await _advance_to_invitation_confirm(hass)
    mock_api.get_system_info = AsyncMock(side_effect=GlutzConnectionError)

    with (
        _patch_api(mock_api),
        patch(
            "homeassistant.components.glutz_eaccess.config_flow.set_new_password",
            new=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CONFIRM_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Glutz eAccess"
    assert result["result"].unique_id == "SYS123"


async def test_invitation_confirm_no_system_id_errors_cannot_connect(
    hass: HomeAssistant, mock_api: AsyncMock
) -> None:
    """No system id (invitation lacks it and API fails) blocks entry creation."""
    invite_no_sys = INVITE_URL.replace("systemid=SYS123&", "")
    result = await _start_step(hass, "invitation")
    with patch(
        "homeassistant.components.glutz_eaccess.config_flow.resolve_instance_host",
        return_value="instance.example.com",
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"invite_url": invite_no_sys}
        )

    mock_api.get_system_info = AsyncMock(return_value={"name": "Palazzo"})
    with (
        patch(
            "homeassistant.components.glutz_eaccess.config_flow.set_new_password",
            new=AsyncMock(),
        ),
        patch(
            "homeassistant.components.glutz_eaccess.config_flow.GlutzAPI",
            return_value=mock_api,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CONFIRM_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (GlutzAuthError, "invalid_auth"),
        (GlutzConnectionError, "cannot_connect"),
    ],
)
async def test_invitation_confirm_set_password_errors_map_to_form_errors(
    hass: HomeAssistant, error, expected
) -> None:
    """Errors while setting the new password surface as form errors."""
    result = await _advance_to_invitation_confirm(hass)

    with patch(
        "homeassistant.components.glutz_eaccess.config_flow.set_new_password",
        side_effect=error,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CONFIRM_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": expected}


# --- reauth ------------------------------------------------------------------


@pytest.fixture
def reauth_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a configured entry to drive reauth tests from."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="SYS1",
        data={
            CONF_HOST: "https://example.com",
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "old_password",
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_reauth_shows_confirm_form(
    hass: HomeAssistant, reauth_entry: MockConfigEntry
) -> None:
    """Entry point for reauth surfaces the confirm form."""
    result = await reauth_entry.start_reauth_flow(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_success_updates_and_aborts(
    hass: HomeAssistant, reauth_entry: MockConfigEntry, mock_api: AsyncMock
) -> None:
    """A successful reauth updates the entry data and aborts with reauth_successful."""
    result = await reauth_entry.start_reauth_flow(hass)
    mock_api.get_system_info = AsyncMock(return_value={"id": "SYS1"})

    with _patch_api(mock_api):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], REAUTH_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert reauth_entry.data == REAUTH_INPUT


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (GlutzAuthError, "invalid_auth"),
        (GlutzConnectionError, "cannot_connect"),
    ],
)
async def test_reauth_api_errors_map_to_form_errors(
    hass: HomeAssistant,
    reauth_entry: MockConfigEntry,
    mock_api: AsyncMock,
    error,
    expected,
) -> None:
    """API errors on reauth stay on the form with a recoverable error."""
    result = await reauth_entry.start_reauth_flow(hass)
    mock_api.get_access_points = AsyncMock(side_effect=error)

    with patch(
        "homeassistant.components.glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], REAUTH_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_reauth_missing_system_id_errors_cannot_connect(
    hass: HomeAssistant, reauth_entry: MockConfigEntry, mock_api: AsyncMock
) -> None:
    """Reauth cannot succeed without a system id — show cannot_connect."""
    result = await reauth_entry.start_reauth_flow(hass)
    mock_api.get_system_info = AsyncMock(return_value={"name": "Palazzo"})

    with patch(
        "homeassistant.components.glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], REAUTH_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_wrong_account_aborts(
    hass: HomeAssistant, reauth_entry: MockConfigEntry, mock_api: AsyncMock
) -> None:
    """Logging in against a different system id aborts with wrong_account."""
    result = await reauth_entry.start_reauth_flow(hass)
    mock_api.get_system_info = AsyncMock(return_value={"id": "DIFFERENT_SYSTEM"})

    with patch(
        "homeassistant.components.glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], REAUTH_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "wrong_account"


async def test_reauth_confirm_form_prefills_host_and_username(
    hass: HomeAssistant, reauth_entry: MockConfigEntry
) -> None:
    """Reauth form prefills host and username from the existing entry."""
    result = await reauth_entry.start_reauth_flow(hass)

    defaults = {
        str(key): key.default()
        for key in result["data_schema"].schema
        if key.default is not vol.UNDEFINED
    }
    assert defaults[CONF_HOST] == "https://example.com"
    assert defaults[CONF_USERNAME] == "user@example.com"
