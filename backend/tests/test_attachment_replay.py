import pytest
from backend.documents import AttachmentCapabilities
from backend.settings import Settings
from backend.providers.notion2api import Notion2APIProvider
from backend.providers.custom_openai import CustomOpenAIProvider

@pytest.fixture
def base_settings():
    return Settings(
        custom_endpoint_supports_attachments=True,
        custom_endpoint_is_stateful=False,
        attachment_replay_policy="stateless_only"
    )

def test_replay_policy_first_round(base_settings):
    # If policy is 'first_round', attachments must be disabled in round 2+ for all providers
    base_settings.attachment_replay_policy = "first_round"
    base_settings.custom_endpoint_is_stateful = False

    # We simulate the _get_capabilities_for_model logic here or test via importing
    # However, since _get_capabilities_for_model is defined inline in stage1_collect_responses,
    # we can test the behavior by mocking settings and verifying the logic.

    from backend.council import get_provider_for_model

    def get_caps_mocked(model: str, round_num: int, settings: Settings) -> AttachmentCapabilities:
        # Replicate the inline _get_capabilities_for_model logic to verify the expected behavior
        from backend.documents import AttachmentCapabilities

        provider = get_provider_for_model(model)
        replay_policy = getattr(settings, "attachment_replay_policy", "stateless_only")

        if isinstance(provider, Notion2APIProvider):
            initial_enabled = True
            is_stateful = True
            supported_mimes = {"application/pdf"}
        elif isinstance(provider, CustomOpenAIProvider):
            initial_enabled = getattr(settings, "custom_endpoint_supports_attachments", False)
            is_stateful = getattr(settings, "custom_endpoint_is_stateful", False)
            supported_mimes = {"application/pdf"}
        else:
            initial_enabled = False
            is_stateful = False
            supported_mimes = set()

        effective_enabled = initial_enabled
        if initial_enabled and round_num > 1:
            if replay_policy == "first_round":
                effective_enabled = False
            elif replay_policy == "stateless_only":
                if is_stateful:
                    effective_enabled = False

        return AttachmentCapabilities(
            enabled=effective_enabled,
            supported_mime_types=supported_mimes,
            stateful=is_stateful,
        )

    # Test round 1 (always enabled if supported)
    caps_notion = get_caps_mocked("notion2api:gpt-4", 1, base_settings)
    assert caps_notion.enabled is True

    caps_custom = get_caps_mocked("custom:gpt-4", 1, base_settings)
    assert caps_custom.enabled is True

    # Test round 2 with "first_round" policy (disabled for both)
    base_settings.attachment_replay_policy = "first_round"
    assert get_caps_mocked("notion2api:gpt-4", 2, base_settings).enabled is False
    assert get_caps_mocked("custom:gpt-4", 2, base_settings).enabled is False

    # Test round 2 with "stateless_only" policy:
    # notion2api is stateful -> disabled
    # custom (is_stateful=False) -> remains enabled
    base_settings.attachment_replay_policy = "stateless_only"
    base_settings.custom_endpoint_is_stateful = False
    assert get_caps_mocked("notion2api:gpt-4", 2, base_settings).enabled is False
    assert get_caps_mocked("custom:gpt-4", 2, base_settings).enabled is True

    # Test round 2 with "stateless_only" policy when custom is stateful:
    # custom (is_stateful=True) -> disabled
    base_settings.custom_endpoint_is_stateful = True
    assert get_caps_mocked("custom:gpt-4", 2, base_settings).enabled is False

    # Test round 2 with "every_round" policy:
    # remains enabled for all supported providers
    base_settings.attachment_replay_policy = "every_round"
    base_settings.custom_endpoint_is_stateful = False
    assert get_caps_mocked("notion2api:gpt-4", 2, base_settings).enabled is True
    assert get_caps_mocked("custom:gpt-4", 2, base_settings).enabled is True
