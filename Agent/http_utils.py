import json
from typing import Any, AsyncGenerator
from urllib import parse

import httpx

from config import http_timeout

# Module-level async HTTP client singleton for connection reuse
_async_client: httpx.AsyncClient | None = None


def _get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(
            timeout=httpx.Timeout(http_timeout),
            limits=httpx.Limits(max_connections=20),
        )
    return _async_client


async def close_async_client() -> None:
    global _async_client
    if _async_client is not None and not _async_client.is_closed:
        await _async_client.aclose()
        _async_client = None


def append_query(url: str, **params: Any) -> str:
    filtered = {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }
    if not filtered:
        return url
    query = parse.urlencode(filtered)
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query}"


# ---------------------------------------------------------------------------
# Async HTTP helpers (httpx-based)
# ---------------------------------------------------------------------------


def _client_for(proxy: str | None = None) -> httpx.AsyncClient:
    """Return a client.  When *proxy* is given, create a temporary client
    configured with that proxy; otherwise reuse the module-level singleton."""
    if proxy:
        return httpx.AsyncClient(
            proxy=proxy,
            timeout=httpx.Timeout(http_timeout),
        )
    return _get_async_client()


async def async_fetch_json(
    url: str,
    *,
    method: str = "GET",
    payload: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = http_timeout,
    proxy: str | None = None,
) -> Any:
    """Fetch JSON with shared connection pooling unless a per-request proxy is used."""
    final_headers = {"Accept": "application/json"}
    if headers:
        final_headers.update(headers)

    client = _client_for(proxy)
    try:
        kwargs: dict[str, Any] = {"headers": final_headers, "timeout": timeout}
        if payload is not None:
            kwargs["json"] = payload

        resp = await client.request(method.upper(), url, **kwargs)
        resp.raise_for_status()
        raw = resp.text
        if not raw:
            return {}
        return json.loads(raw)
    finally:
        if proxy and not client.is_closed:
            await client.aclose()


async def async_fetch_text(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    timeout: int = http_timeout,
    proxy: str | None = None,
) -> str:
    """Fetch plain text for APIs that do not return JSON."""
    final_headers = {"Accept": "*/*"}
    if headers:
        final_headers.update(headers)

    client = _client_for(proxy)
    try:
        kwargs: dict[str, Any] = {"headers": final_headers, "timeout": timeout}
        resp = await client.request(method.upper(), url, **kwargs)
        resp.raise_for_status()
        return resp.text
    finally:
        if proxy and not client.is_closed:
            await client.aclose()


async def async_fetch_stream_lines(
    url: str,
    *,
    method: str = "POST",
    payload: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = http_timeout,
    proxy: str | None = None,
) -> AsyncGenerator[str, None]:
    """Yield streamed response lines for Ollama and OpenAI-compatible SSE."""
    final_headers: dict[str, str] = {}
    if headers:
        final_headers.update(headers)

    client = _client_for(proxy)
    try:
        kwargs: dict[str, Any] = {"headers": final_headers, "timeout": timeout}
        if payload is not None:
            kwargs["json"] = payload

        async with client.stream(method.upper(), url, **kwargs) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                yield line
    finally:
        if proxy and not client.is_closed:
            await client.aclose()
