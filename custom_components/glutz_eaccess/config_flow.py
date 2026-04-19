from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from .api import (
    GlutzAPI,
    GlutzAuthError,
    GlutzConnectionError,
    parse_invitation,
    resolve_instance_host,
    set_new_password,
)
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult

_LOGGER = logging.getLogger(__name__)

DEFAULT_TITLE = "Glutz eAccess"


async def _resolve_system_info(api: GlutzAPI) -> dict[str, str]:
    """Fetch system info, returning an empty dict on transient errors."""
    try:
        return await api.get_system_info()
    except (GlutzAuthError, GlutzConnectionError) as err:
        _LOGGER.warning("Could not fetch system info: %s", err)
        return {}


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


def _reauth_confirm_schema(host: str, username: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=host): str,
            vol.Required(CONF_USERNAME, default=username): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )


class GlutzConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._invitation: dict[str, str] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="user", menu_options=["credentials", "invitation"]
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            api = GlutzAPI(
                self.hass,
                user_input[CONF_HOST],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await api.get_access_points()
                info = await api.get_system_info()
            except GlutzAuthError:
                errors["base"] = "invalid_auth"
            except GlutzConnectionError:
                errors["base"] = "cannot_connect"
            else:
                system_id = info.get("id")
                if not system_id:
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(system_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=info.get("name") or DEFAULT_TITLE, data=user_input
                    )

        return self.async_show_form(
            step_id="credentials", data_schema=STEP_CREDENTIALS_SCHEMA, errors=errors
        )

    async def async_step_invitation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                parsed = parse_invitation(user_input["invite_url"])
            except ValueError:
                errors["base"] = "invalid_invitation"
            else:
                try:
                    host = await resolve_instance_host(
                        self.hass, parsed["cloud_host"], parsed["system_path"]
                    )
                except GlutzConnectionError:
                    errors["base"] = "cannot_connect"
                else:
                    self._invitation = {
                        "host": host,
                        "email": parsed["email"],
                        "token": parsed["token"],
                    }
                    if system_id := parsed.get("system_id"):
                        self._invitation["system_id"] = system_id
                    return await self.async_step_invitation_confirm()

        return self.async_show_form(
            step_id="invitation", data_schema=STEP_INVITATION_SCHEMA, errors=errors
        )

    async def async_step_invitation_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
                try:
                    await set_new_password(
                        self.hass,
                        urlparse(full_host).hostname or full_host,
                        self._invitation["token"],
                        password,
                    )
                except GlutzAuthError:
                    errors["base"] = "invalid_auth"
                except GlutzConnectionError:
                    errors["base"] = "cannot_connect"

                if not errors:
                    api = GlutzAPI(self.hass, full_host, email, password)
                    info = await _resolve_system_info(api)
                    system_id = info.get("id") or self._invitation.get("system_id")
                    if not system_id:
                        errors["base"] = "cannot_connect"
                    else:
                        await self.async_set_unique_id(system_id)
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=info.get("name") or DEFAULT_TITLE,
                            data={
                                CONF_HOST: full_host,
                                CONF_USERNAME: email,
                                CONF_PASSWORD: password,
                            },
                        )

        return self.async_show_form(
            step_id="invitation_confirm",
            data_schema=_invitation_confirm_schema(default_host, default_email),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            api = GlutzAPI(
                self.hass,
                user_input[CONF_HOST],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await api.get_access_points()
                info = await api.get_system_info()
            except GlutzAuthError:
                errors["base"] = "invalid_auth"
            except GlutzConnectionError:
                errors["base"] = "cannot_connect"
            else:
                system_id = info.get("id")
                if not system_id:
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(system_id)
                    self._abort_if_unique_id_mismatch(reason="wrong_account")
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            CONF_HOST: user_input[CONF_HOST],
                            CONF_USERNAME: user_input[CONF_USERNAME],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_reauth_confirm_schema(
                entry.data[CONF_HOST], entry.data[CONF_USERNAME]
            ),
            errors=errors,
        )
