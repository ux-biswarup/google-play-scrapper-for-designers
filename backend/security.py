"""Request-level protections for a server that holds API keys on the user's computer.

- Host check: only local host names are served, which defeats DNS-rebinding attacks (a website whose domain
  suddenly resolves to 127.0.0.1).
- Origin check: requests that change something (POST, PUT, PATCH, DELETE) must come from this app, so other
  websites open in the same browser can't spend your saved keys or change settings (CSRF).
- Security headers: no framing (clickjacking), no MIME sniffing, no referrer leakage, and a strict
  Content-Security-Policy on the app's pages so injected scripts can't run.
"""

from __future__ import annotations

from urllib.parse import urlparse

from starlette.types import ASGIApp, Message, Receive, Scope, Send

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",  # charts set inline styles
        "img-src 'self' data: blob: https:",  # app icons come from Google's image servers
        "font-src 'self' data:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ]
)


def _json_response(status: int, detail: str) -> tuple[Message, Message]:
    body = ('{"detail": "' + detail + '"}').encode()
    start = {
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
    }
    return start, {"type": "http.response.body", "body": body}


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp, allowed_hosts: tuple[str, ...]):
        self.app = app
        self.allowed = {h.lower() for h in allowed_hosts}

    def _host_ok(self, value: str | None) -> bool:
        if not value:
            return False
        host = urlparse(f"//{value}").hostname or ""
        return host.lower() in self.allowed

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        if not self._host_ok(headers.get("host")):
            for message in _json_response(421, "This server only answers requests made to it on this computer."):
                await send(message)
            return
        origin = headers.get("origin")
        if scope["method"] not in SAFE_METHODS and origin and origin != "null":
            if not self._host_ok(urlparse(origin).netloc):
                for message in _json_response(403, "Requests from other websites are blocked."):
                    await send(message)
                return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cross-origin-opener-policy", b"same-origin"),
                ]
                content_type = dict(message.get("headers", [])).get(b"content-type", b"")
                if content_type.startswith(b"text/html"):
                    extra.append((b"content-security-policy", CSP.encode()))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, with_headers)
