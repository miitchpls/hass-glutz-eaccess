from __future__ import annotations

from unittest.mock import MagicMock

from glutz_eaccess.diagnostics import async_get_config_entry_diagnostics


ENTRY_DATA = {
    "host": "https://example.com",
    "username": "user",
    "password": "secret",
    "cert_pem": "FAKE_PEM",
}


class TestAsyncGetConfigEntryDiagnostics:
    async def test_redacts_password(self):
        entry = MagicMock()
        entry.data = ENTRY_DATA

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert result["password"] == "**REDACTED**"

    async def test_redacts_cert_pem(self):
        entry = MagicMock()
        entry.data = ENTRY_DATA

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert result["cert_pem"] == "**REDACTED**"

    async def test_preserves_non_sensitive_fields(self):
        entry = MagicMock()
        entry.data = ENTRY_DATA

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert result["host"] == "https://example.com"
        assert result["username"] == "user"
