"""xAI device-code OAuth (mocked)."""

import respx
from httpx import Response

from backend.oauth import xai


@respx.mock
async def test_xai_device_code_pending_then_success():
    respx.post("https://auth.x.ai/oauth2/device/code").mock(
        return_value=Response(
            200,
            json={
                "device_code": "dc",
                "user_code": "WXYZ",
                "verification_uri": "https://auth.x.ai/device",
                "interval": 1,
                "expires_in": 300,
            },
        )
    )
    token_route = respx.post("https://auth.x.ai/oauth2/token")
    token_route.side_effect = [
        Response(400, json={"error": "authorization_pending"}),
        Response(
            200,
            json={
                "access_token": "xa",
                "refresh_token": "xr",
                "expires_in": 3600,
            },
        ),
    ]

    device = await xai.request_xai_device_code()
    assert device["user_code"] == "WXYZ"

    async def _sleep(_ms):
        return None

    tokens = await xai.poll_xai_device_code_token(device, sleep=_sleep)
    assert tokens["access_token"] == "xa"
