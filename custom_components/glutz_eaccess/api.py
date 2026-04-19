"""Thin re-export of pyglutz_eaccess.client.

The full JSON-RPC client lives in the standalone `pyglutz-eaccess` package;
this module exists so integration-internal imports (`.api`) stay stable.
"""
from __future__ import annotations

from pyglutz_eaccess.client import (
    GlutzAPI,
    GlutzAuthError,
    GlutzConnectionError,
    parse_invitation,
    resolve_instance_host,
    set_new_password,
)

__all__ = [
    "GlutzAPI",
    "GlutzAuthError",
    "GlutzConnectionError",
    "parse_invitation",
    "resolve_instance_host",
    "set_new_password",
]
