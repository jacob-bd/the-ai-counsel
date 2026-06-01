"""Provider, model, and health MCP tool."""

from __future__ import annotations

import json

import httpx

from ..client import CouncilClient


def register(server, base_url: str) -> None:
    """Register providers tool."""

    @server.tool(description=(
        "Provider and model utilities. action: 'list_models', 'health', 'test', "
        "'set_api_key', 'set_search'. test requires provider; set_api_key requires "
        "provider + api_key; set_search requires provider (optional api_key)."
    ))
    async def providers(
        action: str,
        provider: str | None = None,
        api_key: str | None = None,
    ) -> str:
        action = action.strip().lower()
        valid = ("list_models", "health", "test", "set_api_key", "set_search")
        if action not in valid:
            return f"Error: action must be one of: {', '.join(valid)}."

        try:
            if action == "list_models":
                async with CouncilClient(base_url) as client:
                    models = await client.get_all_models()
                if not models:
                    return "No models available. Check that providers are configured and reachable."
                lines = [f"Found {len(models)} models:"]
                for m in models:
                    name = m.get("name", m.get("id", "unknown"))
                    model_id = m.get("id", "")
                    prov = m.get("provider", "")
                    line = f"  • {name} [{prov}] — {model_id}"
                    if m.get("is_free"):
                        line += " (free)"
                    lines.append(line)
                return "\n".join(lines)

            if action == "health":
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    try:
                        resp = await http_client.get(f"{base_url}/api/health")
                        backend_ok = resp.status_code == 200
                        backend_msg = "reachable" if backend_ok else f"error {resp.status_code}"
                    except httpx.RequestError as e:
                        return json.dumps({
                            "backend": "unreachable",
                            "error": str(e),
                            "base_url": base_url,
                        }, indent=2)

                try:
                    async with CouncilClient(base_url) as client:
                        settings = await client.get_settings()
                except Exception as settings_exc:
                    return json.dumps({
                        "backend": backend_msg,
                        "base_url": base_url,
                        "settings_error": str(settings_exc),
                    }, indent=2)

                configured = []
                for key in ("openrouter", "openai", "anthropic", "google", "mistral", "deepseek", "groq",
                            "opencode", "tavily", "brave", "serper", "tinyfish"):
                    if settings.get(f"{key}_api_key_set"):
                        configured.append(key)

                custom_name = settings.get("custom_endpoint_name")
                custom_url = settings.get("custom_endpoint_url")
                if custom_name or custom_url or settings.get("custom_endpoint_api_key_set"):
                    configured.append(f"custom ({custom_name or custom_url or 'unnamed'})")

                return json.dumps({
                    "backend": backend_msg,
                    "base_url": base_url,
                    "council_models": settings.get("council_models", []),
                    "chairman_model": settings.get("chairman_model"),
                    "execution_mode": settings.get("execution_mode"),
                    "search_provider": settings.get("search_provider"),
                    "configured_providers": configured,
                    "ollama_url": settings.get("ollama_base_url"),
                }, indent=2)

            if action == "test":
                if not provider:
                    return "Error: provider is required for test."
                try:
                    async with CouncilClient(base_url) as client:
                        result = await client.test_provider(provider, api_key)
                    return json.dumps(result, indent=2)
                except Exception as exc:
                    return json.dumps({"success": False, "message": str(exc)}, indent=2)

            if action == "set_api_key":
                if not provider or not api_key:
                    return "Error: provider and api_key are required for set_api_key."
                key_map = {
                    "openrouter": "openrouter_api_key",
                    "openai": "openai_api_key",
                    "anthropic": "anthropic_api_key",
                    "google": "google_api_key",
                    "mistral": "mistral_api_key",
                    "deepseek": "deepseek_api_key",
                    "groq": "groq_api_key",
                    "opencode": "opencode_api_key",
                    "opencode-zen": "opencode_api_key",
                    "opencode-go": "opencode_api_key",
                    "tinyfish": "tinyfish_api_key",
                    "tavily": "tavily_api_key",
                    "brave": "brave_api_key",
                    "serper": "serper_api_key",
                }
                if provider not in key_map:
                    return f"Error: unknown provider '{provider}'."
                async with CouncilClient(base_url) as client:
                    await client.update_settings(**{key_map[provider]: api_key})
                return f"API key for '{provider}' saved."

            if action == "set_search":
                if not provider:
                    return "Error: provider is required for set_search."
                valid_providers = ("duckduckgo", "tavily", "brave", "serper", "tinyfish")
                if provider not in valid_providers:
                    return f"Error: invalid provider '{provider}'. Must be one of: {', '.join(valid_providers)}."
                updates = {"search_provider": provider}
                if api_key:
                    updates[f"{provider}_api_key"] = api_key
                async with CouncilClient(base_url) as client:
                    await client.update_settings(**updates)
                msg = f"Search provider set to '{provider}'."
                if api_key:
                    msg += " API key saved."
                return msg
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)}, indent=2)
