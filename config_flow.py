from __future__ import annotations

from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from .api import GlutzAPI, GlutzAuthError, GlutzConnectionError, fetch_server_cert_pem
from .const import CONF_CERT_PEM, DOMAIN

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class GlutzConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
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
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
