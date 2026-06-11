import json
from typing import Any
from urllib import error, parse, request

from config import http_timeout


def _decode_error(exc: error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8")
    except Exception:
        raw = exc.reason if hasattr(exc, "reason") else str(exc)

    if not raw:
        return f"{exc.code} {exc.reason}"

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    if isinstance(payload, dict):
        if isinstance(payload.get("error"), dict):
            message = payload["error"].get("message")
            if message:
                return str(message)
        if payload.get("message"):
            return str(payload["message"])
    return raw


def fetch_json(
    url: str,
    *,
    method: str = "GET",
    payload: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = http_timeout,
    proxy: str | None = None,
) -> Any:
    body = None
    final_headers = {"Accept": "application/json"}
    if headers:
        final_headers.update(headers)

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        final_headers.setdefault("Content-Type", "application/json")

    req = request.Request(url, data=body, headers=final_headers, method=method.upper())

    if proxy:
        proxy_handler = request.ProxyHandler({"http": proxy, "https": proxy})
        opener = request.build_opener(proxy_handler)
    else:
        opener = request.build_opener()

    try:
        with opener.open(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset("utf-8")
            raw = resp.read().decode(charset)
            if not raw:
                return {}
            return json.loads(raw)
    except error.HTTPError as exc:
        raise RuntimeError(_decode_error(exc)) from exc
    except error.URLError as exc:
        reason = exc.reason if hasattr(exc, "reason") else str(exc)
        raise RuntimeError(str(reason)) from exc


def fetch_text(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    timeout: int = http_timeout,
    proxy: str | None = None,
) -> str:
    final_headers = {"Accept": "*/*"}
    if headers:
        final_headers.update(headers)

    req = request.Request(url, headers=final_headers, method=method.upper())

    if proxy:
        proxy_handler = request.ProxyHandler({"http": proxy, "https": proxy})
        opener = request.build_opener(proxy_handler)
    else:
        opener = request.build_opener()

    try:
        with opener.open(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset("utf-8")
            return resp.read().decode(charset)
    except error.HTTPError as exc:
        raise RuntimeError(_decode_error(exc)) from exc
    except error.URLError as exc:
        reason = exc.reason if hasattr(exc, "reason") else str(exc)
        raise RuntimeError(str(reason)) from exc


def fetch_stream(
    url: str,
    *,
    method: str = "POST",
    payload: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = http_timeout,
    proxy: str | None = None,
):
    """Return a raw urllib response object for line-by-line streaming reads."""
    body = None
    final_headers = {}
    if headers:
        final_headers.update(headers)

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        final_headers.setdefault("Content-Type", "application/json")

    req = request.Request(url, data=body, headers=final_headers, method=method.upper())

    if proxy:
        proxy_handler = request.ProxyHandler({"http": proxy, "https": proxy})
        opener = request.build_opener(proxy_handler)
    else:
        opener = request.build_opener()

    return opener.open(req, timeout=timeout)


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
