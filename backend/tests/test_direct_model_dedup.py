from types import SimpleNamespace

import pytest

import backend.main as main


class _FakeProvider:
    def __init__(self, models):
        self.models = models
        self.calls = 0

    async def get_models(self):
        self.calls += 1
        return list(self.models)


def _settings(custom_url: str, notion_url: str):
    return SimpleNamespace(
        custom_endpoint_url=custom_url,
        notion2api_base_url=notion_url,
    )


@pytest.mark.asyncio
async def test_direct_models_prefers_dedicated_notion2api_for_same_endpoint(monkeypatch):
    custom = _FakeProvider([{"id": "custom:baseten-glm-5.2"}])
    notion = _FakeProvider([{"id": "notion2api:baseten-glm-5.2"}])
    monkeypatch.setattr(main, "PROVIDERS", {"custom": custom, "notion2api": notion})
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: _settings("http://127.0.0.1:8120/v1/", "http://127.0.0.1:8120/v1"),
    )

    assert await main.get_direct_models() == [
        {"id": "notion2api:baseten-glm-5.2"},
    ]
    assert custom.calls == 1
    assert notion.calls == 1


@pytest.mark.asyncio
async def test_direct_models_keeps_custom_as_fallback_when_dedicated_empty(monkeypatch):
    custom = _FakeProvider([{"id": "custom:baseten-glm-5.2"}])
    notion = _FakeProvider([])
    monkeypatch.setattr(main, "PROVIDERS", {"custom": custom, "notion2api": notion})
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: _settings("http://127.0.0.1:8120/v1", "http://127.0.0.1:8120/v1"),
    )

    assert await main.get_direct_models() == [
        {"id": "custom:baseten-glm-5.2"},
    ]


@pytest.mark.asyncio
async def test_direct_models_keeps_both_when_endpoints_differ(monkeypatch):
    custom = _FakeProvider([{"id": "custom:model-a"}])
    notion = _FakeProvider([{"id": "notion2api:model-a"}])
    monkeypatch.setattr(main, "PROVIDERS", {"custom": custom, "notion2api": notion})
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: _settings("http://127.0.0.1:9000/v1", "http://127.0.0.1:8120/v1"),
    )

    assert await main.get_direct_models() == [
        {"id": "custom:model-a"},
        {"id": "notion2api:model-a"},
    ]
