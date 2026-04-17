from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from glutz_eaccess.api import GlutzAuthError, GlutzConnectionError
from glutz_eaccess.config_flow import GlutzConfigFlow, _is_valid_password

USER_INPUT = {
    "host": "https://example.com",
    "username": "user",
    "password": "secret",
}

INVITE_URL = (
    "https://eaccess.ac.glutz.com/invite///cloud.eaccess.glutz.com/building-name"
    "?systemid=SYS123&email=user%40example.com&token=TOK123"
)


def _make_flow() -> GlutzConfigFlow:
    flow = GlutzConfigFlow()
    flow.hass = MagicMock()
    flow.async_show_form = MagicMock(return_value={"type": "form"})
    flow.async_show_menu = MagicMock(return_value={"type": "menu"})
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    return flow


class TestIsValidPassword:
    def test_valid_password(self):
        assert _is_valid_password("Secure1!") is True

    def test_missing_uppercase(self):
        assert _is_valid_password("secure1!") is False

    def test_missing_lowercase(self):
        assert _is_valid_password("SECURE1!") is False

    def test_missing_digit(self):
        assert _is_valid_password("Secure!!") is False

    def test_missing_special(self):
        assert _is_valid_password("Secure123") is False

    def test_empty_string(self):
        assert _is_valid_password("") is False

    def test_too_short(self):
        assert _is_valid_password("Sec1!") is False

    def test_unicode_special_char(self):
        assert _is_valid_password("Secure1€") is True

    def test_space_counts_as_special(self):
        assert _is_valid_password("Secure1 ") is True


class TestAsyncStepUser:
    async def test_shows_menu(self):
        flow = _make_flow()
        result = await flow.async_step_user(None)
        flow.async_show_menu.assert_called_once()
        kwargs = flow.async_show_menu.call_args[1]
        assert kwargs["step_id"] == "user"
        assert set(kwargs["menu_options"]) == {"credentials", "invitation"}
        assert result == {"type": "menu"}


class TestAsyncStepCredentials:
    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        result = await flow.async_step_credentials(None)
        flow.async_show_form.assert_called_once()
        assert result == {"type": "form"}

    async def test_success_creates_entry(self):
        flow = _make_flow()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(return_value=[])

        with patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_credentials(USER_INPUT)

        flow.async_create_entry.assert_called_once()
        call_kwargs = flow.async_create_entry.call_args[1]
        assert call_kwargs["data"] == USER_INPUT

    async def test_auth_error_sets_invalid_auth(self):
        flow = _make_flow()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(side_effect=GlutzAuthError)

        with patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_credentials(USER_INPUT)

        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "invalid_auth"

    async def test_connection_error_sets_cannot_connect(self):
        flow = _make_flow()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(side_effect=GlutzConnectionError)

        with patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_credentials(USER_INPUT)

        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "cannot_connect"

    async def test_aborts_when_same_host_and_username_already_configured(self):
        flow = _make_flow()
        existing = MagicMock()
        existing.data = {"host": USER_INPUT["host"], "username": USER_INPUT["username"]}
        flow._async_current_entries = MagicMock(return_value=[existing])
        flow.async_abort = MagicMock(return_value={"type": "abort"})

        result = await flow.async_step_credentials(USER_INPUT)

        flow.async_abort.assert_called_once_with(reason="already_configured")
        assert result == {"type": "abort"}

    async def test_allows_same_host_different_username(self):
        flow = _make_flow()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(return_value=[])
        existing = MagicMock()
        existing.data = {"host": USER_INPUT["host"], "username": "other_user"}
        flow._async_current_entries = MagicMock(return_value=[existing])

        with patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_credentials(USER_INPUT)

        flow.async_create_entry.assert_called_once()


class TestAsyncStepInvitation:
    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        result = await flow.async_step_invitation(None)
        flow.async_show_form.assert_called_once()
        assert result == {"type": "form"}

    async def test_invalid_url_sets_error(self):
        flow = _make_flow()
        await flow.async_step_invitation({"invite_url": "not a valid url"})
        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "invalid_invitation"

    async def test_resolve_failure_sets_cannot_connect(self):
        flow = _make_flow()
        with patch(
            "glutz_eaccess.config_flow.resolve_instance_host",
            side_effect=GlutzConnectionError,
        ):
            await flow.async_step_invitation({"invite_url": INVITE_URL})
        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "cannot_connect"

    async def test_success_advances_to_confirm(self):
        flow = _make_flow()
        with patch(
            "glutz_eaccess.config_flow.resolve_instance_host",
            return_value="instance.example.com",
        ):
            await flow.async_step_invitation({"invite_url": INVITE_URL})
        assert flow._invitation == {
            "host": "instance.example.com",
            "email": "user@example.com",
            "token": "TOK123",
        }
        assert flow.async_show_form.call_args[1]["step_id"] == "invitation_confirm"


class TestAsyncStepInvitationConfirm:
    def _flow_with_invitation(self) -> GlutzConfigFlow:
        flow = _make_flow()
        flow._invitation = {
            "host": "instance.example.com",
            "email": "user@example.com",
            "token": "TOK123",
        }
        return flow

    async def test_shows_form_when_no_input(self):
        flow = self._flow_with_invitation()
        await flow.async_step_invitation_confirm(None)
        flow.async_show_form.assert_called_once()
        assert flow.async_show_form.call_args[1]["step_id"] == "invitation_confirm"

    def _submit(self, password: str = "Secure1!") -> dict:
        return {
            "host": "https://instance.example.com",
            "username": "user@example.com",
            "password": password,
        }

    async def test_weak_password_sets_error(self):
        flow = self._flow_with_invitation()
        await flow.async_step_invitation_confirm(self._submit(password="weak"))
        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "invalid_password"

    async def test_success_creates_entry(self):
        flow = self._flow_with_invitation()
        with patch(
            "glutz_eaccess.config_flow.set_new_password", new=AsyncMock()
        ) as mock_setpw:
            await flow.async_step_invitation_confirm(self._submit())
        mock_setpw.assert_awaited_once_with(
            flow.hass, "instance.example.com", "TOK123", "Secure1!"
        )
        call_kwargs = flow.async_create_entry.call_args[1]
        assert call_kwargs["data"] == {
            "host": "https://instance.example.com",
            "username": "user@example.com",
            "password": "Secure1!",
        }

    async def test_auth_error_sets_invalid_auth(self):
        flow = self._flow_with_invitation()
        with patch(
            "glutz_eaccess.config_flow.set_new_password",
            side_effect=GlutzAuthError,
        ):
            await flow.async_step_invitation_confirm(self._submit())
        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "invalid_auth"

    async def test_connection_error_sets_cannot_connect(self):
        flow = self._flow_with_invitation()
        with patch(
            "glutz_eaccess.config_flow.set_new_password",
            side_effect=GlutzConnectionError,
        ):
            await flow.async_step_invitation_confirm(self._submit())
        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "cannot_connect"

    async def test_duplicate_host_and_email_aborts(self):
        flow = self._flow_with_invitation()
        existing = MagicMock()
        existing.data = {
            "host": "https://instance.example.com",
            "username": "user@example.com",
        }
        flow._async_current_entries = MagicMock(return_value=[existing])
        flow.async_abort = MagicMock(return_value={"type": "abort"})

        result = await flow.async_step_invitation_confirm(self._submit())

        flow.async_abort.assert_called_once_with(reason="already_configured")
        assert result == {"type": "abort"}
