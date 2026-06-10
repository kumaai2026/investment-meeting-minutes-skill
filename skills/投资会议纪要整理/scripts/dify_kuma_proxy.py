#!/usr/bin/env python3
"""Small reverse proxy for sharing the working dify.d91.global hostname.

Requests under /kuma are routed to the Kuma workbench service on port 1000.
Known meeting-note frontend paths are also routed there directly so relative
links emitted by Dify do not fall through to the Dify SPA and return 404.
Everything else is passed through to the existing Dify service on port 81.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Iterable

import requests
from aiohttp import ClientSession, WSMsgType, web


LISTEN_HOST = os.environ.get("DIFY_KUMA_PROXY_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("DIFY_KUMA_PROXY_PORT", "18081"))
DIFY_ORIGIN = os.environ.get("DIFY_ORIGIN", "http://127.0.0.1:81").rstrip("/")
KUMA_ORIGIN = os.environ.get("KUMA_ORIGIN", "http://127.0.0.1:1000").rstrip("/")
KUMA_PREFIX = os.environ.get("KUMA_PREFIX", "/kuma").rstrip("/")
DIFY_ASSET_CACHE_BUSTER = os.environ.get("DIFY_ASSET_CACHE_BUSTER", "d91fix20260513")

DIRECT_KUMA_PATHS = {
    "/account",
    "/access-audit",
    "/access-login",
    "/access-logout",
    "/access-users",
    "/agent-status",
    "/confirm",
    "/confirm-archive",
    "/confirm-input",
    "/dashboard",
    "/download",
    "/drafts",
    "/external-sources",
    "/external-view",
    "/health",
    "/health-report",
    "/history",
    "/knowledge",
    "/latest",
    "/mapping-audit",
    "/mp",
    "/review",
    "/result",
    "/save",
    "/sync-status",
    "/target-query",
    "/view",
}
DIRECT_KUMA_PREFIXES = (
    "/apps/meeting-minutes",
    "/api/access-audit",
    "/api/access-users",
    "/api/agent-status",
    "/api/dashboard",
    "/api/drafts",
    "/api/external-sources",
    "/api/health-report",
    "/api/history",
    "/api/import-status",
    "/api/import-upload",
    "/api/mapping-audit",
    "/api/sync-status",
    "/api/target-query",
)

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _target_for(path_qs: str) -> tuple[str, str, bool]:
    path = "/" + path_qs.lstrip("/")
    clean_path = path.split("?", 1)[0]
    if path == KUMA_PREFIX or path.startswith(KUMA_PREFIX + "/"):
        stripped = path[len(KUMA_PREFIX) :] or "/"
        return KUMA_ORIGIN, stripped, True
    if clean_path in DIRECT_KUMA_PATHS or any(
        clean_path == prefix or clean_path.startswith(prefix + "/") for prefix in DIRECT_KUMA_PREFIXES
    ):
        return KUMA_ORIGIN, path, False
    return DIFY_ORIGIN, path, False


def _headers(headers: Iterable[tuple[str, str]], host: str) -> dict[str, str]:
    clean = {}
    for key, value in headers:
        lower = key.lower()
        if lower not in HOP_BY_HOP and lower != "accept-encoding":
            clean[key] = value
    clean["Host"] = host
    # requests auto-decompresses upstream bodies; force identity so we do not
    # forward stale Content-Encoding headers with decoded content.
    clean["Accept-Encoding"] = "identity"
    return clean


def _rewrite_location(location: str, is_kuma: bool) -> str:
    if not is_kuma:
        return location
    if location.startswith(KUMA_ORIGIN):
        location = location[len(KUMA_ORIGIN) :] or "/"
    if location.startswith("/") and not location.startswith(KUMA_PREFIX + "/"):
        return KUMA_PREFIX + location
    return location


def _rewrite_html(body: bytes, content_type: str, is_kuma: bool) -> bytes:
    if "text/html" not in content_type.lower():
        return body
    text = body.decode("utf-8", errors="replace")
    if not is_kuma:
        # Bypass stale Cloudflare cache entries created before the proxy stopped
        # forwarding decoded bodies with a gzip Content-Encoding header.
        def bust(match: re.Match[str]) -> str:
            quote = match.group(1)
            url = match.group(2)
            if "?" in url:
                return match.group(0)
            return f"{quote}{url}?v={DIFY_ASSET_CACHE_BUSTER}{quote}"

        text = re.sub(r"([\"'])(/_next/static/[^\"']+)(\1)", bust, text)
        return text.encode("utf-8")

    replacements = {
        'href="/': f'href="{KUMA_PREFIX}/',
        'src="/': f'src="{KUMA_PREFIX}/',
        'action="/': f'action="{KUMA_PREFIX}/',
        'fetch("/': f'fetch("{KUMA_PREFIX}/',
        "fetch('/": f"fetch('{KUMA_PREFIX}/",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("utf-8")


async def proxy_http(request: web.Request) -> web.StreamResponse:
    origin, target_path, is_kuma = _target_for(request.rel_url.raw_path_qs)
    url = origin + target_path
    origin_host = origin.split("://", 1)[1]
    host_header = origin_host if is_kuma else request.headers.get("Host", origin_host)
    data = await request.read()

    def do_request() -> requests.Response:
        return requests.request(
            request.method,
            url,
            headers=_headers(request.headers.items(), host_header),
            data=data,
            allow_redirects=False,
            timeout=120,
        )

    upstream = await asyncio.to_thread(do_request)
    headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in HOP_BY_HOP and key.lower() not in {"content-length", "content-encoding"}
    }
    if "Location" in headers:
        headers["Location"] = _rewrite_location(headers["Location"], is_kuma)
    body = _rewrite_html(upstream.content, headers.get("Content-Type", ""), is_kuma)
    return web.Response(status=upstream.status_code, headers=headers, body=body)


async def proxy_ws(request: web.Request) -> web.StreamResponse:
    origin, target_path, _is_kuma = _target_for(request.rel_url.raw_path_qs)
    scheme = "wss" if origin.startswith("https://") else "ws"
    origin_host = origin.split("://", 1)[1]
    host_header = origin_host if _is_kuma else request.headers.get("Host", origin_host)
    url = scheme + "://" + origin_host + target_path
    ws_server = web.WebSocketResponse()
    await ws_server.prepare(request)
    session: ClientSession = request.app["session"]
    async with session.ws_connect(url, headers=_headers(request.headers.items(), host_header)) as ws_client:
        async def client_to_origin() -> None:
            async for msg in ws_server:
                if msg.type == WSMsgType.TEXT:
                    await ws_client.send_str(msg.data)
                elif msg.type == WSMsgType.BINARY:
                    await ws_client.send_bytes(msg.data)
                elif msg.type == WSMsgType.CLOSE:
                    await ws_client.close()

        async def origin_to_client() -> None:
            async for msg in ws_client:
                if msg.type == WSMsgType.TEXT:
                    await ws_server.send_str(msg.data)
                elif msg.type == WSMsgType.BINARY:
                    await ws_server.send_bytes(msg.data)
                elif msg.type == WSMsgType.CLOSE:
                    await ws_server.close()

        await asyncio.gather(client_to_origin(), origin_to_client())
    return ws_server


async def handler(request: web.Request) -> web.StreamResponse:
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await proxy_ws(request)
    return await proxy_http(request)


async def on_startup(app: web.Application) -> None:
    app["session"] = ClientSession()


async def on_cleanup(app: web.Application) -> None:
    await app["session"].close()


def main() -> None:
    app = web.Application(client_max_size=1024**3)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_route("*", "/{tail:.*}", handler)
    web.run_app(app, host=LISTEN_HOST, port=LISTEN_PORT)


if __name__ == "__main__":
    main()
