from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from glutz_eaccess.api import GlutzAuthError, GlutzConnectionError
from glutz_eaccess.config_flow import GlutzConfigFlow

USER_INPUT = {
    "host": "https://example.com",
    "username": "user",
    "password": "secret",
}


def _make_flow() -> GlutzConfigFlow:
    flow = GlutzConfigFlow()
    flow.async_show_form = MagicMock(return_value={"type": "form"})
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    return flow


class TestAsyncStepUser:
    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        result = await flow.async_step_user(None)
        flow.async_show_form.assert_called_once()
        assert result == {"type": "form"}

    async def test_success_creates_entry(self):
        flow = _make_flow()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(return_value=[])

        with patch("glutz_eaccess.config_flow.fetch_server_cert_pem", return_value="CERT_PEM"), \
             patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_user(USER_INPUT)

        flow.async_create_entry.assert_called_once()
        call_kwargs = flow.async_create_entry.call_args[1]
        assert call_kwargs["data"]["host"] == "https://example.com"
        assert call_kwargs["data"]["cert_pem"] == "CERT_PEM"

    async def test_cert_fetch_failure_sets_cannot_connect(self):
        flow = _make_flow()

        with patch("glutz_eaccess.config_flow.fetch_server_cert_pem", side_effect=GlutzConnectionError):
            await flow.async_step_user(USER_INPUT)

        flow.async_show_form.assert_called_once()
        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "cannot_connect"

    async def test_auth_error_sets_invalid_auth(self):
        flow = _make_flow()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(side_effect=GlutzAuthError)

        with patch("glutz_eaccess.config_flow.fetch_server_cert_pem", return_value="CERT_PEM"), \
             patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_user(USER_INPUT)

        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "invalid_auth"

    async def test_connection_error_sets_cannot_connect(self):
        flow = _make_flow()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(side_effect=GlutzConnectionError)

        with patch("glutz_eaccess.config_flow.fetch_server_cert_pem", return_value="CERT_PEM"), \
             patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_user(USER_INPUT)

        errors = flow.async_show_form.call_args[1]["errors"]
        assert errors["base"] == "cannot_connect"

    async def test_api_close_always_called(self):
        flow = _make_flow()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(side_effect=GlutzAuthError)

        with patch("glutz_eaccess.config_flow.fetch_server_cert_pem", return_value="CERT_PEM"), \
             patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_user(USER_INPUT)

        mock_api.close.assert_awaited_once()

    async def test_hostname_extracted_from_full_url(self):
        flow = _make_flow()
        mock_api = AsyncMock()
        mock_api.get_access_points = AsyncMock(return_value=[])

        with patch("glutz_eaccess.config_flow.fetch_server_cert_pem", return_value="CERT") as mock_cert, \
             patch("glutz_eaccess.config_flow.GlutzAPI", return_value=mock_api):
            await flow.async_step_user({**USER_INPUT, "host": "https://myhost.example.com"})

        mock_cert.assert_awaited_once_with("myhost.example.com")
