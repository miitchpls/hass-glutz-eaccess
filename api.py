from __future__ import annotations

import base64
import logging
from urllib.parse import parse_qs, urlparse

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class GlutzAuthError(Exception):
    """Raised when authentication fails (invalid credentials)."""


class GlutzConnectionError(Exception):
    """Raised when the API is unreachable or returns an unexpected response."""


def parse_invitation(url: str) -> dict[str, str]:
    """Parse a Glutz eAccess invitation URL into its components.

    Accepts both the web and mobile deep-link formats:
        https://eaccess.ac.glutz.com/invite///cloud.eaccess.glutz.com/building-name
            ?systemid=XXXX&email=user%40example.com&token=XXXXX
        eaccessmobile://cloud.eaccess.glutz.com/building-name
            ?systemid=XXXX&email=user%40example.com&token=XXXXX
    """
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    try:
        email = query["email"][0]
        token = query["token"][0]
    except (KeyError, IndexError) as err:
        raise ValueError("Missing email or token") from err

    if parsed.scheme == "eaccessmobile":
        cloud_host = parsed.netloc
        system_path = parsed.path.lstrip("/")
    else:
        prefix = "/invite/"
        if not parsed.path.startswith(prefix):
            raise ValueError("Missing /invite/ prefix")
        remainder = parsed.path[len(prefix):].lstrip("/")
        parts = remainder.split("/", 1)
        if len(parts) != 2:
            raise ValueError("Missing cloud host or system path")
        cloud_host, system_path = parts

    if not cloud_host or not system_path:
        raise ValueError("Missing cloud host or system path")

    return {
        "cloud_host": cloud_host,
        "system_path": system_path,
        "email": email,
        "token": token,
    }


async def resolve_instance_host(hass: HomeAssistant, cloud_host: str, system_path: str) -> str:
    url = f"https://{cloud_host}/{system_path}"
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            url,
            allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status in (301, 302, 307, 308):
                resolved = urlparse(resp.headers.get("Location", "")).hostname
                if resolved:
                    return resolved
    except aiohttp.ClientError as err:
        raise GlutzConnectionError(f"Could not resolve instance host from {url}: {err}") from err

    return cloud_host


async def set_new_password(hass: HomeAssistant, host: str, token: str, password: str) -> None:
    url = f"https://{host}/api/unauthorized/setnewpassword"
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            url,
            json={"token": token, "password": password},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 401:
                raise GlutzAuthError("Invalid or expired invitation token")
            resp.raise_for_status()
    except aiohttp.ClientError as err:
        raise GlutzConnectionError(f"Could not set new password at {url}: {err}") from err


class GlutzAPI:
    """Client for the Glutz eAccess JSON-RPC API."""

    def __init__(self, hass: HomeAssistant, host: str, username: str, password: str, language: str = "en") -> None:
        self._hass = hass
        self._url = f"{host}/rpc/"
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {token}",
            "Accept": "*/*",
            "Accept-Language": language,
            "User-Agent": "eAccess/76 CFNetwork/3826.500.131 Darwin/24.5.0",
        }

    async def _rpc(self, method: str, params: list) -> dict:
        """Send a JSON-RPC 2.0 request and return the result payload."""
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        session = async_get_clientsession(self._hass)
        try:
            async with session.post(self._url, json=payload, headers=self._headers) as resp:
                _LOGGER.debug("RPC %s returned HTTP %s", method, resp.status)
                if resp.status == 401:
                    raise GlutzAuthError("Invalid credentials")
                resp.raise_for_status()
                data = await resp.json()
                if "error" in data:
                    _LOGGER.warning("RPC %s returned error: %s", method, data["error"])
                    raise GlutzConnectionError(data["error"])
                return data["result"]
        except aiohttp.ClientError as err:
            _LOGGER.warning("RPC %s network error: %s", method, err)
            raise GlutzConnectionError(str(err)) from err

    async def get_access_points(self) -> list[dict]:
        """Return all access points available to the authenticated user."""
        result = await self._rpc("eAccess.getAccessPointsRelatedToLoggedInUser", [])
        return result["accessPoints"]

    async def open_access_point(self, access_point_id: str) -> bool:
        """Open an access point for 3 seconds (action 2, hardware auto-relock)."""
        result = await self._rpc(
            "eAccess.executeAccessPointAsLoggedInUser",
            [access_point_id, 2],
        )
        return result.get("status") == "success"

    async def close_access_point(self, access_point_id: str) -> bool:
        """Force-lock an access point using action 16."""
        result = await self._rpc(
            "eAccess.executeAccessPointAsLoggedInUser",
            [access_point_id, 16],
        )
        return result.get("status") == "success"
