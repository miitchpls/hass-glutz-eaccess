from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from .api import (
    GlutzAPI,
    GlutzAuthError,
    GlutzConnectionError,
    fetch_server_cert_pem,
    parse_invitation,
    resolve_instance_host,
    set_new_password,
)
from .const import CONF_CERT_PEM, DOMAIN


def _is_valid_password(pwd: str) -> bool:
    return (
        len(pwd) >= 8
        and any(c.isupper() for c in pwd)
        and any(c.islower() for c in pwd)
        and any(c.isdigit() for c in pwd)
        and any(not c.isalnum() for c in pwd)
    )


STEP_CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_INVITATION_SCHEMA = vol.Schema({vol.Required("invite_url"): str})

def _invitation_confirm_schema(host: str, email: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=host): str,
            vol.Required(CONF_USERNAME, default=email): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )


class GlutzConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._invitation: dict[str, str] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        return self.async_show_menu(
            step_id="user", menu_options=["credentials", "invitation"]
        )

    async def async_step_credentials(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            for entry in self._async_current_entries():
                if (
                    entry.data.get(CONF_HOST) == user_input[CONF_HOST]
                    and entry.data.get(CONF_USERNAME) == user_input[CONF_USERNAME]
                ):
                    return self.async_abort(reason="already_configured")

            parsed = urlparse(user_input[CONF_HOST])
            hostname = parsed.hostname or user_input[CONF_HOST]
            try:
                cert_pem = await fetch_server_cert_pem(hostname)
            except GlutzConnectionError:
                errors["base"] = "cannot_connect"
                cert_pem = None

            if not errors:
                api = GlutzAPI(
                    user_input[CONF_HOST],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    cert_pem=cert_pem,
                )
                try:
                    await api.get_access_points()
                    return self.async_create_entry(
                        title="Glutz eAccess",
                        data={**user_input, CONF_CERT_PEM: cert_pem},
                    )
                except GlutzAuthError:
                    errors["base"] = "invalid_auth"
                except GlutzConnectionError:
                    errors["base"] = "cannot_connect"
                finally:
                    await api.close()

        return self.async_show_form(
            step_id="credentials", data_schema=STEP_CREDENTIALS_SCHEMA, errors=errors
        )

    async def async_step_invitation(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                parsed = parse_invitation(user_input["invite_url"])
            except ValueError:
                errors["base"] = "invalid_invitation"

            if not errors:
                try:
                    host = await resolve_instance_host(
                        parsed["cloud_host"], parsed["system_path"]
                    )
                    cert_pem = await fetch_server_cert_pem(host)
                except GlutzConnectionError:
                    errors["base"] = "cannot_connect"

            if not errors:
                self._invitation = {
                    "host": host,
                    "email": parsed["email"],
                    "token": parsed["token"],
                    "cert_pem": cert_pem,
                }
                return await self.async_step_invitation_confirm()

        return self.async_show_form(
            step_id="invitation", data_schema=STEP_INVITATION_SCHEMA, errors=errors
        )

    async def async_step_invitation_confirm(
        self, user_input: dict[str, Any] | None = None
    ):
        assert self._invitation is not None
        errors: dict[str, str] = {}
        default_host = f"https://{self._invitation['host']}"
        default_email = self._invitation["email"]

        if user_input is not None:
            full_host = user_input[CONF_HOST]
            email = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            if not _is_valid_password(password):
                errors["base"] = "invalid_password"

            if not errors:
                for entry in self._async_current_entries():
                    if (
                        entry.data.get(CONF_HOST) == full_host
                        and entry.data.get(CONF_USERNAME) == email
                    ):
                        return self.async_abort(reason="already_configured")

                try:
                    await set_new_password(
                        urlparse(full_host).hostname or full_host,
                        self._invitation["token"],
                        password,
                        self._invitation["cert_pem"],
                    )
                    return self.async_create_entry(
                        title="Glutz eAccess",
                        data={
                            CONF_HOST: full_host,
                            CONF_USERNAME: email,
                            CONF_PASSWORD: password,
                            CONF_CERT_PEM: self._invitation["cert_pem"],
                        },
                    )
                except GlutzAuthError:
                    errors["base"] = "invalid_auth"
                except GlutzConnectionError:
                    errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="invitation_confirm",
            data_schema=_invitation_confirm_schema(default_host, default_email),
            errors=errors,
        )
