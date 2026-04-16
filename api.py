from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import ssl
from urllib.parse import urlparse

import aiohttp

_LOGGER = logging.getLogger(__name__)


class GlutzAuthError(Exception):
    """Raised when authentication fails (invalid credentials)."""


class GlutzConnectionError(Exception):
    """Raised when the API is unreachable or returns an unexpected response."""


async def fetch_server_cert_pem(host: str) -> str:
    """Open a TLS connection to host:443 and return the server certificate in PEM format.

    Used during config flow to pin the certificate on first use (TOFU).
    Only the TLS handshake is performed — no HTTP request is sent.
    Raises GlutzConnectionError if the host is unreachable.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, 443, ssl=ctx), timeout=10
        )
        cert_der = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
        writer.close()
        await writer.wait_closed()
    except Exception as err:
        _LOGGER.warning("Failed to fetch certificate from %s: %s", host, err)
        raise GlutzConnectionError(f"Could not fetch certificate from {host}: {err}") from err

    return ssl.DER_cert_to_PEM_cert(cert_der)


def _build_ssl_context(cert_pem: str | None) -> aiohttp.Fingerprint | bool:
    """Return an aiohttp Fingerprint for TOFU certificate pinning.

    Falls back to ssl=False if no cert is provided (backwards compatibility).
    """
    if not cert_pem:
        return False

    der = ssl.PEM_cert_to_DER_cert(cert_pem)
    return aiohttp.Fingerprint(hashlib.sha256(der).digest())


async def resolve_instance_host(cloud_host: str, system_path: str) -> str:
    """Resolve the actual Glutz instance hostname from the cloud host.

    Performs a GET without following redirects. If the server returns a 3xx,
    the hostname is extracted from the Location header. Otherwise the cloud
    host itself is returned unchanged.
    """
    url = f"https://{cloud_host}/{system_path}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (301, 302, 307, 308):
                    location = resp.headers.get("Location", "")
                    resolved = urlparse(location).hostname
                    if resolved:
                        return resolved
    except aiohttp.ClientError as err:
        _LOGGER.warning("Failed to resolve instance host from %s: %s", url, err)
        raise GlutzConnectionError(f"Could not resolve instance host from {url}: {err}") from err

    return cloud_host


class GlutzAPI:
    """Client for the Glutz eAccess JSON-RPC API."""

    def __init__(self, host: str, username: str, password: str, cert_pem: str | None = None, language: str = "en") -> None:
        self._url = f"{host}/rpc/"
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {token}",
            "Accept": "*/*",
            "Accept-Language": language,
            "User-Agent": "eAccess/76 CFNetwork/3826.500.131 Darwin/24.5.0",
        }
        self._connector = aiohttp.TCPConnector(ssl=_build_ssl_context(cert_pem))

    async def _rpc(self, method: str, params: list) -> dict:
        """Send a JSON-RPC 2.0 request and return the result payload."""
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        try:
            async with aiohttp.ClientSession(
                connector=self._connector, connector_owner=False
            ) as session:
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

    async def open_access_point(self, access_point_id: str, action: int) -> bool:
        """Trigger an action on an access point (e.g. open the door)."""
        result = await self._rpc(
            "eAccess.executeAccessPointAsLoggedInUser",
            [access_point_id, action],
        )
        return result.get("status") == "success"

    async def close(self) -> None:
        """Close the underlying TCP connector and release resources."""
        await self._connector.close()
