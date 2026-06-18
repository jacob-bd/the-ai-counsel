from the_ai_counsel_mcp.errors import classify_http_error, classify_exception


def test_classify_429():
    err = classify_http_error(429, "Too Many Requests")
    assert err["type"] == "rate_limit"
    assert err["retryable"] is True


def test_classify_401():
    err = classify_http_error(401, "Unauthorized")
    assert err["type"] == "auth_error"
    assert err["retryable"] is False


def test_classify_403():
    err = classify_http_error(403, "Forbidden")
    assert err["type"] == "auth_error"
    assert err["retryable"] is False


def test_classify_404():
    err = classify_http_error(404, "Not Found")
    assert err["type"] == "model_not_found"
    assert err["retryable"] is False


def test_classify_500():
    err = classify_http_error(500, "Server Error")
    assert err["type"] == "provider_error"
    assert err["retryable"] is False


def test_classify_timeout_exception():
    import httpx
    exc = httpx.TimeoutException("timed out")
    err = classify_exception(exc)
    assert err["type"] == "timeout"
    assert err["retryable"] is True


def test_classify_connect_exception():
    import httpx
    exc = httpx.ConnectError("connection refused")
    err = classify_exception(exc)
    assert err["type"] == "network_error"
    assert err["retryable"] is True
