"""Authentication for HTTP transport.

Bearer token auth for remote/tunnel access. Set ``OBSIDIAN_MCP_API_TOKEN`` env var.
Every HTTP request must include ``Authorization: Bearer <token>``.

If the env var is **unset or empty**, bearer auth is disabled — this keeps
localhost-only setups working without any configuration.
"""

from __future__ import annotations

import json
import logging
import os
import secrets

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_BEARER_TOKEN: str | None = None
_BEARER_CHECKED: bool = False

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "[::1]"})


def is_loopback(host: str) -> bool:
    """True for binds that only this machine can reach."""
    return host.strip().lower() in LOOPBACK_HOSTS


def check_http_policy(host: str, token: str | None, writes: bool) -> str | None:
    """Return a refusal reason for this HTTP bind, or None when it is allowed.

    Rules (DD-462 Phase C, step C4):

    * loopback bind, read-only, no token: allowed;
    * any non-loopback bind requires ``OBSIDIAN_MCP_API_TOKEN``;
    * writes enabled over HTTP require the token on every bind, loopback included.
    """
    if token:
        return None
    if not is_loopback(host):
        return (
            f"HTTP bind on {host} is not loopback and OBSIDIAN_MCP_API_TOKEN is unset. Set a token, or bind 127.0.0.1."
        )
    if writes:
        return (
            "OBSIDIAN_MCP_WRITES is enabled over HTTP and OBSIDIAN_MCP_API_TOKEN is unset. "
            "Writes over HTTP always need a token, even on loopback."
        )
    return None


def get_bearer_token() -> str | None:
    """Return the bearer token from env, or None if not configured."""
    global _BEARER_TOKEN, _BEARER_CHECKED  # noqa: PLW0603
    if _BEARER_CHECKED:
        return _BEARER_TOKEN
    _BEARER_CHECKED = True
    token = os.environ.get("OBSIDIAN_MCP_API_TOKEN", "").strip()
    _BEARER_TOKEN = token if token else None
    return _BEARER_TOKEN


class BearerAuthMiddleware:
    """Starlette-compatible ASGI middleware for Bearer token auth.

    When ``OBSIDIAN_MCP_API_TOKEN`` is set, every request must carry a matching
    ``Authorization: Bearer <token>`` header. Requests without a valid token
    receive a ``401 Unauthorized`` JSON response.

    If the env var is unset or empty, this middleware is a transparent pass-through.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        expected = get_bearer_token()
        if expected is None:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_value = headers.get(b"authorization", b"").decode("latin-1")

        provided = ""
        if auth_value.lower().startswith("bearer "):
            provided = auth_value[7:]

        if provided and secrets.compare_digest(provided, expected):
            await self.app(scope, receive, send)
            return

        body = json.dumps({"error": "Unauthorized"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
