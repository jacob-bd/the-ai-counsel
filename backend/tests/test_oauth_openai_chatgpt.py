"""OpenAI ChatGPT deviceauth + PKCE (mocked)."""

import respx
from httpx import Response

from backend.oauth import openai_chatgpt


@respx.mock
async def test_device_code_and_pkce_exchange():
    respx.post("https://auth.openai.com/api/accounts/deviceauth/usercode").mock(
        return_value=Response(
            200,
            json={
                "device_auth_id": "dev1",
                "user_code": "ABCD-EFGH",
                "interval": "1",
                "expires_in": 300,
            },
        )
    )
    # First poll pending 403, then success
    token_route = respx.post("https://auth.openai.com/api/accounts/deviceauth/token")
    token_route.side_effect = [
        Response(403, json={}),
        Response(
            200,
            json={"authorization_code": "code", "code_verifier": "verifier"},
        ),
    ]
    respx.post("https://auth.openai.com/oauth/token").mock(
        return_value=Response(
            200,
            json={
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 3600,
                "id_token": None,
            },
        )
    )

    device = await openai_chatgpt.request_openai_device_code()
    assert device["user_code"] == "ABCD-EFGH"
    assert openai_chatgpt.open_ai_device_code_url().endswith("/codex/device")

    async def _sleep(_ms):
        return None

    tokens, account = await openai_chatgpt.poll_openai_device_code_token(
        device, sleep=_sleep
    )
    assert tokens["access_token"] == "access"
    assert account is None
