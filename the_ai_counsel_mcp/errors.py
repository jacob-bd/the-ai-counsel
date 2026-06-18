"""Error classification for The AI Counsel MCP server."""



ERROR_TYPES = {
    "rate_limit": {"retryable": True, "description": "Rate limit exceeded"},
    "auth_error": {"retryable": False, "description": "Authentication failed"},
    "timeout": {"retryable": True, "description": "Request timed out"},
    "model_not_found": {"retryable": False, "description": "Model not found"},
    "network_error": {"retryable": True, "description": "Network connection failed"},
    "provider_error": {"retryable": False, "description": "Provider-side error"},
}


def classify_http_error(status_code: int, message: str = "") -> dict:
    """Classify an HTTP error into a structured error dict."""
    if status_code == 429:
        error_type = "rate_limit"
    elif status_code in (401, 403):
        error_type = "auth_error"
    elif status_code == 404:
        error_type = "model_not_found"
    else:
        error_type = "provider_error"

    return {
        "type": error_type,
        "message": message or f"HTTP {status_code}",
        "retryable": ERROR_TYPES[error_type]["retryable"],
    }


def classify_exception(exc: Exception) -> dict:
    """Classify a Python exception into a structured error dict."""
    exc_name = type(exc).__name__
    msg = str(exc)

    if "timeout" in exc_name.lower() or "timeout" in msg.lower():
        error_type = "timeout"
    elif any(x in exc_name.lower() for x in ("connect", "network", "connection")):
        error_type = "network_error"
    else:
        error_type = "provider_error"

    return {
        "type": error_type,
        "message": msg,
        "retryable": ERROR_TYPES[error_type]["retryable"],
    }
