from __future__ import annotations

import base64
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from glutz_eaccess.api import (
    GlutzAPI,
    GlutzAuthError,
    GlutzConnectionError,
    _build_ssl_context,
    fetch_server_cert_pem,
    parse_invitation,
    resolve_instance_host,
    set_new_password,
)

INVITE_URL = (
    "https://eaccess.ac.glutz.com/invite///cloud.eaccess.glutz.com/building-name"
    "?systemid=SYS123&email=user%40example.com&token=TOK123"
)


def _mock_get_session(status: int, headers: dict | None = None, client_error: Exception | None = None):
    """Return a mock aiohttp.ClientSession that responds to GET with the given status/headers."""
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.headers = headers or {}
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    if client_error:
        mock_session.get = MagicMock(side_effect=client_error)
    else:
        mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def _mock_session(status: int, json_body: dict | None = None, client_error: Exception | None = None):
    """Return a mock aiohttp.ClientSession that responds to POST with the given status/body."""
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=json_body or {})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    if client_error:
        mock_session.post = MagicMock(side_effect=client_error)
    else:
        mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


class TestBuildSslContext:
    def test_none_returns_false(self):
        assert _build_ssl_context(None) is False

    def test_empty_string_returns_false(self):
        assert _build_ssl_context("") is False

    def test_valid_cert_returns_fingerprint(self):
        fake_der = b"fake_der_bytes"
        with patch("glutz_eaccess.api.ssl.PEM_cert_to_DER_cert", return_value=fake_der):
            result = _build_ssl_context("FAKE_PEM")
        assert isinstance(result, aiohttp.Fingerprint)
        assert result.fingerprint == hashlib.sha256(fake_der).digest()


class TestFetchServerCertPem:
    async def test_returns_pem_on_success(self):
        fake_der = b"fake_cert_der"
        mock_ssl_obj = MagicMock()
        mock_ssl_obj.getpeercert.return_value = fake_der
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = mock_ssl_obj
        mock_writer.wait_closed = AsyncMock()

        with patch("glutz_eaccess.api.asyncio.wait_for", new=AsyncMock(return_value=(None, mock_writer))), \
             patch("glutz_eaccess.api.ssl.DER_cert_to_PEM_cert", return_value="FAKE_PEM"):
            result = await fetch_server_cert_pem("example.com")
        assert result == "FAKE_PEM"

    async def test_raises_connection_error_on_network_failure(self):
        with patch("glutz_eaccess.api.asyncio.wait_for", side_effect=OSError("refused")):
            with pytest.raises(GlutzConnectionError):
                await fetch_server_cert_pem("unreachable.example.com")


class TestGlutzAPIInit:
    def test_authorization_header(self):
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"):
            api = GlutzAPI("https://example.com", "user", "secret")
        expected = "Basic " + base64.b64encode(b"user:secret").decode()
        assert api._headers["Authorization"] == expected

    def test_default_language_is_en(self):
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"):
            api = GlutzAPI("https://example.com", "user", "pass")
        assert api._headers["Accept-Language"] == "en"

    def test_custom_language(self):
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"):
            api = GlutzAPI("https://example.com", "user", "pass", language="it")
        assert api._headers["Accept-Language"] == "it"

    def test_url_built_from_host(self):
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"):
            api = GlutzAPI("https://example.com", "user", "pass")
        assert api._url == "https://example.com/rpc/"


class TestGlutzAPIRpc:
    async def test_success_returns_result(self):
        session = _mock_session(200, json_body={"result": {"foo": "bar"}})
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            api = GlutzAPI("https://example.com", "user", "pass")
            result = await api._rpc("some.method", [])
        assert result == {"foo": "bar"}

    async def test_401_raises_auth_error(self):
        session = _mock_session(401, json_body={})
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            api = GlutzAPI("https://example.com", "user", "pass")
            with pytest.raises(GlutzAuthError):
                await api._rpc("some.method", [])

    async def test_error_field_raises_connection_error(self):
        session = _mock_session(200, json_body={"error": {"code": -1, "message": "fail"}})
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            api = GlutzAPI("https://example.com", "user", "pass")
            with pytest.raises(GlutzConnectionError):
                await api._rpc("some.method", [])

    async def test_network_error_raises_connection_error(self):
        session = _mock_session(200, client_error=aiohttp.ClientConnectorError(MagicMock(), OSError()))
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            api = GlutzAPI("https://example.com", "user", "pass")
            with pytest.raises(GlutzConnectionError):
                await api._rpc("some.method", [])


class TestGlutzAPIMethods:
    async def test_get_access_points_returns_list(self):
        aps = [{"accessPointId": "ap-1"}, {"accessPointId": "ap-2"}]
        session = _mock_session(200, json_body={"result": {"accessPoints": aps}})
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            api = GlutzAPI("https://example.com", "user", "pass")
            result = await api.get_access_points()
        assert result == aps

    async def test_open_access_point_sends_action_2(self):
        session = _mock_session(200, json_body={"result": {"status": "success"}})
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            api = GlutzAPI("https://example.com", "user", "pass")
            result = await api.open_access_point("ap-1")
        assert result is True
        payload = session.post.call_args[1]["json"]
        assert payload["params"] == ["ap-1", 2]

    async def test_open_access_point_returns_false_on_non_success(self):
        session = _mock_session(200, json_body={"result": {"status": "error"}})
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            api = GlutzAPI("https://example.com", "user", "pass")
            result = await api.open_access_point("ap-1")
        assert result is False

    async def test_close_access_point_sends_action_16(self):
        session = _mock_session(200, json_body={"result": {"status": "success"}})
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            api = GlutzAPI("https://example.com", "user", "pass")
            result = await api.close_access_point("ap-1")
        assert result is True
        payload = session.post.call_args[1]["json"]
        assert payload["params"] == ["ap-1", 16]

    async def test_close_access_point_returns_false_on_non_success(self):
        session = _mock_session(200, json_body={"result": {"status": "error"}})
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            api = GlutzAPI("https://example.com", "user", "pass")
            result = await api.close_access_point("ap-1")
        assert result is False

    async def test_close_awaits_connector(self):
        mock_connector = AsyncMock()
        with patch("glutz_eaccess.api.aiohttp.TCPConnector", return_value=mock_connector):
            api = GlutzAPI("https://example.com", "user", "pass")
        await api.close()
        mock_connector.close.assert_awaited_once()


class TestParseInvitation:
    def test_valid_url(self):
        result = parse_invitation(INVITE_URL)
        assert result == {
            "cloud_host": "cloud.eaccess.glutz.com",
            "system_path": "building-name",
            "email": "user@example.com",
            "token": "TOK123",
        }

    def test_mobile_deep_link(self):
        result = parse_invitation(
            "eaccessmobile://cloud.eaccess.glutz.com/lugano-parco-brentani"
            "?systemid=5951.4109&email=user%40example.com&token=TOK123"
        )
        assert result == {
            "cloud_host": "cloud.eaccess.glutz.com",
            "system_path": "lugano-parco-brentani",
            "email": "user@example.com",
            "token": "TOK123",
        }

    def test_missing_invite_prefix(self):
        with pytest.raises(ValueError):
            parse_invitation("https://eaccess.ac.glutz.com/foo/cloud.example.com/bar?email=a&token=b")

    def test_missing_token(self):
        with pytest.raises(ValueError):
            parse_invitation("https://eaccess.ac.glutz.com/invite///cloud.example.com/bar?email=a")

    def test_missing_email(self):
        with pytest.raises(ValueError):
            parse_invitation("https://eaccess.ac.glutz.com/invite///cloud.example.com/bar?token=b")

    def test_missing_system_path(self):
        with pytest.raises(ValueError):
            parse_invitation("https://eaccess.ac.glutz.com/invite///cloud.example.com?email=a&token=b")


class TestResolveInstanceHost:
    async def test_redirect_returns_location_hostname(self):
        session = _mock_get_session(302, headers={"Location": "https://instance.example.com/foo"})
        with patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            result = await resolve_instance_host("cloud.example.com", "building")
        assert result == "instance.example.com"

    async def test_redirect_without_hostname_falls_back(self):
        session = _mock_get_session(302, headers={"Location": ""})
        with patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            result = await resolve_instance_host("cloud.example.com", "building")
        assert result == "cloud.example.com"

    async def test_non_redirect_returns_cloud_host(self):
        session = _mock_get_session(200)
        with patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            result = await resolve_instance_host("cloud.example.com", "building")
        assert result == "cloud.example.com"

    async def test_client_error_raises_connection_error(self):
        session = _mock_get_session(200, client_error=aiohttp.ClientConnectorError(MagicMock(), OSError()))
        with patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            with pytest.raises(GlutzConnectionError):
                await resolve_instance_host("cloud.example.com", "building")


class TestSetNewPassword:
    async def test_success_returns_none(self):
        session = _mock_session(200, json_body={})
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            result = await set_new_password("host.example.com", "tok", "Secret1!", None)
        assert result is None

    async def test_401_raises_auth_error(self):
        session = _mock_session(401)
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            with pytest.raises(GlutzAuthError):
                await set_new_password("host.example.com", "tok", "Secret1!", None)

    async def test_500_raises_connection_error(self):
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(MagicMock(), (), status=500)
        )
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        session = AsyncMock()
        session.post = MagicMock(return_value=mock_resp)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            with pytest.raises(GlutzConnectionError):
                await set_new_password("host.example.com", "tok", "Secret1!", None)

    async def test_network_error_raises_connection_error(self):
        session = _mock_session(200, client_error=aiohttp.ClientConnectorError(MagicMock(), OSError()))
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            with pytest.raises(GlutzConnectionError):
                await set_new_password("host.example.com", "tok", "Secret1!", None)

    async def test_sends_expected_payload(self):
        session = _mock_session(200, json_body={})
        with patch("glutz_eaccess.api.aiohttp.TCPConnector"), \
             patch("glutz_eaccess.api.aiohttp.ClientSession", return_value=session):
            await set_new_password("host.example.com", "tok", "Secret1!", None)
        call_kwargs = session.post.call_args
        assert call_kwargs[0][0] == "https://host.example.com/api/unauthorized/setnewpassword"
        assert call_kwargs[1]["json"] == {"token": "tok", "password": "Secret1!"}
