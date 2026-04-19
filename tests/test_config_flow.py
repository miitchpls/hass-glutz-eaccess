from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import voluptuous as vol

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
    flow.async_set_unique_id = AsyncMock(return_value=None)
    flow._abort_if_unique_id_configured = MagicMock()
    flow._abort_if_unique_id_mismatch = MagicMock()
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
        mock_api.get_system_info = AsyncMock(
            return_value={"id": "SYS1", "name": "Palazzo Rossi"}
        )

        with patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_credentials(USER_INPUT)

        flow.async_set_unique_id.assert_awaited_once_with("SYS1")
        flow._abort_if_unique_id_configured.assert_called_once()
        flow.async_create_entry.assert_called_once()
        call_kwargs = flow.async_create_entry.call_args[1]
        assert call_kwargs["data"] == USER_INPUT
        assert call_kwargs["title"] == "Palazzo Rossi"

    async def test_missing_system_name_falls_back_to_default_title(self):
        flow = _make_flow()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(return_value=[])
        mock_api.get_system_info = AsyncMock(return_value={"id": "SYS1"})

        with patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_credentials(USER_INPUT)

        call_kwargs = flow.async_create_entry.call_args[1]
        assert call_kwargs["title"] == "Glutz eAccess"

    async def test_missing_system_id_sets_cannot_connect(self):
        flow = _make_flow()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(return_value=[])
        mock_api.get_system_info = AsyncMock(return_value={"name": "Palazzo Rossi"})

        with patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_credentials(USER_INPUT)

        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "cannot_connect"
        flow.async_create_entry.assert_not_called()

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

    async def test_system_info_connection_error_sets_cannot_connect(self):
        flow = _make_flow()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(return_value=[])
        mock_api.get_system_info = AsyncMock(side_effect=GlutzConnectionError)

        with patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_credentials(USER_INPUT)

        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "cannot_connect"
        flow.async_create_entry.assert_not_called()


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
            "system_id": "SYS123",
        }
        assert flow.async_show_form.call_args[1]["step_id"] == "invitation_confirm"


class TestAsyncStepInvitationConfirm:
    def _flow_with_invitation(self, system_id: str | None = "SYS123") -> GlutzConfigFlow:
        flow = _make_flow()
        flow._invitation = {
            "host": "instance.example.com",
            "email": "user@example.com",
            "token": "TOK123",
        }
        if system_id:
            flow._invitation["system_id"] = system_id
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
        mock_api = AsyncMock()
        mock_api.get_system_info = AsyncMock(
            return_value={"id": "SYS-API", "name": "Palazzo Rossi"}
        )
        with patch(
            "glutz_eaccess.config_flow.set_new_password", new=AsyncMock()
        ) as mock_setpw, patch(
            "glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api
        ):
            await flow.async_step_invitation_confirm(self._submit())
        mock_setpw.assert_awaited_once_with(
            flow.hass, "instance.example.com", "TOK123", "Secure1!"
        )
        flow.async_set_unique_id.assert_awaited_once_with("SYS-API")
        flow._abort_if_unique_id_configured.assert_called_once()
        call_kwargs = flow.async_create_entry.call_args[1]
        assert call_kwargs["title"] == "Palazzo Rossi"
        assert call_kwargs["data"] == {
            "host": "https://instance.example.com",
            "username": "user@example.com",
            "password": "Secure1!",
        }

    async def test_falls_back_to_invitation_system_id_when_api_fails(self):
        flow = self._flow_with_invitation()
        mock_api = AsyncMock()
        mock_api.get_system_info = AsyncMock(side_effect=GlutzConnectionError)
        with patch(
            "glutz_eaccess.config_flow.set_new_password", new=AsyncMock()
        ), patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_invitation_confirm(self._submit())
        flow.async_set_unique_id.assert_awaited_once_with("SYS123")
        call_kwargs = flow.async_create_entry.call_args[1]
        assert call_kwargs["title"] == "Glutz eAccess"

    async def test_no_system_id_anywhere_sets_cannot_connect(self):
        flow = self._flow_with_invitation(system_id=None)
        mock_api = AsyncMock()
        mock_api.get_system_info = AsyncMock(return_value={"name": "Palazzo Rossi"})
        with patch(
            "glutz_eaccess.config_flow.set_new_password", new=AsyncMock()
        ), patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_invitation_confirm(self._submit())
        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "cannot_connect"
        flow.async_create_entry.assert_not_called()

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


class TestAsyncStepReauth:
    def _flow_with_reauth_entry(self) -> GlutzConfigFlow:
        flow = _make_flow()
        entry = MagicMock()
        entry.data = {
            "host": "https://example.com",
            "username": "user@example.com",
            "password": "old_password",
        }
        entry.unique_id = "SYS1"
        flow._reauth_entry = entry
        flow._get_reauth_entry = MagicMock(return_value=entry)
        return flow

    async def test_reauth_entrypoint_shows_confirm_form(self):
        flow = self._flow_with_reauth_entry()
        await flow.async_step_reauth(flow._reauth_entry.data)
        flow.async_show_form.assert_called_once()
        assert flow.async_show_form.call_args[1]["step_id"] == "reauth_confirm"

    async def test_shows_form_when_no_input(self):
        flow = self._flow_with_reauth_entry()
        await flow.async_step_reauth_confirm(None)
        flow.async_show_form.assert_called_once()
        assert flow.async_show_form.call_args[1]["step_id"] == "reauth_confirm"

    def _submit(
        self,
        host: str = "https://example.com",
        username: str = "user@example.com",
        password: str = "new_password",
    ) -> dict:
        return {"host": host, "username": username, "password": password}

    async def test_success_updates_entry_and_aborts(self):
        flow = self._flow_with_reauth_entry()
        flow.async_update_reload_and_abort = MagicMock(
            return_value={
                "type": "abort",
                "reason": "reauth_successful",
                "data_updates": self._submit(),
                "entry": flow._reauth_entry,
            }
        )
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(return_value=[])
        mock_api.get_system_info = AsyncMock(return_value={"id": "SYS1"})

        with patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            result = await flow.async_step_reauth_confirm(self._submit())

        flow.async_set_unique_id.assert_awaited_once_with("SYS1")
        flow._abort_if_unique_id_mismatch.assert_called_once_with(reason="wrong_account")
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"
        assert result["entry"] is flow._reauth_entry

    async def test_invalid_auth_shows_error(self):
        flow = self._flow_with_reauth_entry()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(side_effect=GlutzAuthError)

        with patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_reauth_confirm(self._submit(password="wrong"))

        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "invalid_auth"

    async def test_connection_error_shows_error(self):
        flow = self._flow_with_reauth_entry()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(side_effect=GlutzConnectionError)

        with patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_reauth_confirm(self._submit())

        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "cannot_connect"

    async def test_missing_system_id_shows_cannot_connect(self):
        flow = self._flow_with_reauth_entry()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(return_value=[])
        mock_api.get_system_info = AsyncMock(return_value={"name": "Palazzo"})

        with patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_reauth_confirm(self._submit())

        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "cannot_connect"
        flow._abort_if_unique_id_mismatch.assert_not_called()

    async def test_uses_submitted_host_and_username(self):
        flow = self._flow_with_reauth_entry()
        flow.async_update_reload_and_abort = MagicMock(return_value={"type": "abort"})
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(return_value=[])
        mock_api.get_system_info = AsyncMock(return_value={"id": "SYS1"})

        with patch(
            "glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api
        ) as mock_cls:
            await flow.async_step_reauth_confirm(
                self._submit(host="https://new.example.com", username="new@example.com")
            )

        args = mock_cls.call_args[0]
        assert args[1] == "https://new.example.com"
        assert args[2] == "new@example.com"
        assert args[3] == "new_password"

    async def test_form_schema_prefills_host_and_username(self):
        flow = self._flow_with_reauth_entry()
        await flow.async_step_reauth_confirm(None)
        schema = flow.async_show_form.call_args[1]["data_schema"]
        defaults = {str(k): k.default() for k in schema.schema if k.default is not vol.UNDEFINED}
        assert defaults["host"] == "https://example.com"
        assert defaults["username"] == "user@example.com"
