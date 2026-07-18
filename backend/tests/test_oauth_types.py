"""OAuth credential blob helpers."""

import time

from backend.oauth.types import (
    access_token_is_expiring,
    oauth_credential_needs_refresh,
    tokens_to_stored_credential,
)


def test_tokens_to_stored_preserves_account():
    cred = tokens_to_stored_credential(
        {"access_token": "a", "refresh_token": "r", "expires_in": 60},
        account_id="acct_1",
        provider_data={"x": 1},
    )
    assert cred["type"] == "oauth"
    assert cred["access"] == "a"
    assert cred["refresh"] == "r"
    assert cred["accountId"] == "acct_1"
    assert cred["providerData"] == {"x": 1}
    assert cred["expires"] > time.time() * 1000


def test_needs_refresh_skew():
    cred = {"expires": int(time.time() * 1000) + 30_000}  # 30s
    assert oauth_credential_needs_refresh(cred, skew_ms=120_000) is True
    cred2 = {"expires": int(time.time() * 1000) + 600_000}
    assert oauth_credential_needs_refresh(cred2, skew_ms=120_000) is False


def test_jwt_expiring_opaque_false():
    assert access_token_is_expiring("not-a-jwt") is False
