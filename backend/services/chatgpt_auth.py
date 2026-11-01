"""Sign in with ChatGPT: lets ChatGPT Plus/Pro users run analyses and chat on their ChatGPT plan.

Implements OpenAI's documented flow for open-source apps (developers.openai.com/siwc, "ChatGPT plan
usage"): Authorization Code + PKCE with OpenID Connect, a loopback redirect on 127.0.0.1, dynamic client
registration, ID-token validation against OpenAI's published keys, and rotating refresh tokens.

Tokens never reach the browser: they live in data/chatgpt-auth.json (mode 0600, git-ignored).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import ssl
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi
import jwt

ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = f"{ISSUER}/api/accounts/authorize"
TOKEN_URL = f"{ISSUER}/api/accounts/oauth/token"
REVOKE_URL = f"{ISSUER}/api/accounts/oauth/revoke"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
REGISTRATION_CLIENT = "dynamic_agent_client"
APP_NAME = "Review Insights"
CALLBACK_PATH = "/api/auth/chatgpt/callback"
REFRESH_MARGIN_SECONDS = 120
PENDING_TTL_SECONDS = 600
# Refresh errors that mean the token set is dead and the user must sign in again.
TERMINAL_REFRESH_ERRORS = {
    "invalid_grant",
    "invalid_refresh_token",
    "token_expired",
    "refresh_token_expired",
    "refresh_token_invalidated",
    "refresh_token_reused",
}

_SSL = ssl.create_default_context(cafile=certifi.where())


class ChatGPTAuthError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _post_form(url: str, fields: dict[str, str]) -> dict:
    request = Request(
        url,
        data=urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urlopen(request, context=_SSL, timeout=30) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except HTTPError as exc:
        try:
            error = json.loads(exc.read() or b"{}")
        except json.JSONDecodeError:
            error = {}
        code = error.get("error") if isinstance(error.get("error"), str) else None
        detail = error.get("error_description") or code or f"HTTP {exc.code}"
        raise ChatGPTAuthError(f"OpenAI sign-in failed: {detail}", code) from exc
    except URLError as exc:
        raise ChatGPTAuthError("Could not reach OpenAI. Check your internet connection.", "network") from exc


@dataclass
class PendingSignIn:
    state: str
    nonce: str
    verifier: str
    redirect_uri: str
    client_id: str
    return_to: str
    created: float = field(default_factory=time.time)


class ChatGPTAuth:
    def __init__(self, data_dir: Path, post_form=_post_form, verify_id_token=None, cipher=None):
        self.data_dir = data_dir
        self._cipher = cipher  # Vault: encrypts the token file at rest
        self._post_form = post_form
        self._verify = verify_id_token or self._verify_with_jwks
        self._pending: dict[str, PendingSignIn] = {}
        self._lock = threading.Lock()  # serialise refreshes: refresh tokens rotate

    # ---- storage --------------------------------------------------------------------------

    @property
    def _creds_path(self) -> Path:
        return self.data_dir / "chatgpt-auth.json"

    @property
    def _host_path(self) -> Path:
        return self.data_dir / "chatgpt-host.json"

    def _read(self, path: Path) -> dict | None:
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def _write(self, path: Path, data: dict) -> None:
        """Atomic write, readable only by the current user."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)

    def _host(self) -> dict:
        """Stable per-install host ID plus the client ID OpenAI issued at first registration."""
        host = self._read(self._host_path) or {}
        if not host.get("ext_agent_host_id"):
            host["ext_agent_host_id"] = f"urn:uuid:{uuid.uuid4()}"
            self._write(self._host_path, host)
        return host

    def credentials(self) -> dict | None:
        path = self._creds_path
        if not path.exists():
            return None
        raw = path.read_bytes()
        if self._cipher is not None:
            try:
                return json.loads(self._cipher.decrypt(raw))
            except Exception:  # noqa: BLE001 - older plain-text file: read it, then re-save encrypted
                pass
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if self._cipher is not None:
            self._write_creds(data)
        return data

    def _write_creds(self, data: dict) -> None:
        if self._cipher is None:
            self._write(self._creds_path, data)
            return
        tmp = self._creds_path.with_suffix(".tmp")
        self._creds_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(self._cipher.encrypt(json.dumps(data).encode()))
        os.replace(tmp, self._creds_path)

    # ---- sign-in ----------------------------------------------------------------------------

    def status(self) -> dict:
        creds = self.credentials()
        if not creds:
            return {"signed_in": False, "email": None, "plan_usage": False}
        return {
            "signed_in": True,
            "email": creds.get("email"),
            "plan_usage": PLAN_SCOPE in creds.get("scopes", []),
        }

    def start(self, port: int, return_to: str) -> str:
        """Build the authorization URL. The redirect must be an http loopback URL on 127.0.0.1."""
        now = time.time()
        self._pending = {k: v for k, v in self._pending.items() if now - v.created < PENDING_TTL_SECONDS}
        host = self._host()
        client_id = host.get("client_id") or REGISTRATION_CLIENT
        verifier = _b64url(secrets.token_bytes(48))
        pending = PendingSignIn(
            state=secrets.token_urlsafe(24),
            nonce=secrets.token_urlsafe(24),
            verifier=verifier,
            redirect_uri=f"http://127.0.0.1:{port}{CALLBACK_PATH}",
            client_id=client_id,
            return_to=return_to,
        )
        self._pending[pending.state] = pending
        params = {
            "client_id": client_id,
            "ext_agent_host_id": host["ext_agent_host_id"],
            "response_type": "code",
            "redirect_uri": pending.redirect_uri,
            "scope": SCOPES,
            "resource": RESOURCE,
            "state": pending.state,
            "nonce": pending.nonce,
            "code_challenge_method": "S256",
            "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
        }
        if client_id == REGISTRATION_CLIENT:
            params["agent_name_hint"] = APP_NAME
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    def complete(self, params: dict[str, str]) -> str:
        """Handle the redirect back from OpenAI. Returns the app origin to send the user back to."""
        pending = self._pending.pop(params.get("state", ""), None)
        if pending is None:
            raise ChatGPTAuthError("This sign-in link expired. Start again from Settings.", "invalid_state")
        if params.get("error"):
            if params["error"] == "access_denied":
                raise ChatGPTAuthError("Sign-in was cancelled.", "access_denied")
            raise ChatGPTAuthError(f"OpenAI sign-in failed: {params.get('error_description') or params['error']}")
        issued = params.get("client_id") or ""
        if pending.client_id == REGISTRATION_CLIENT:
            if not issued:
                raise ChatGPTAuthError("OpenAI didn't finish registering this app. Try again.", "registration")
            client_id = issued
        else:
            if issued and issued != pending.client_id:
                raise ChatGPTAuthError("OpenAI returned a different app registration. Try again.", "client_mismatch")
            client_id = pending.client_id

        tokens = self._post_form(
            TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": params.get("code", ""),
                "code_verifier": pending.verifier,
                "redirect_uri": pending.redirect_uri,
                "resource": RESOURCE,
            },
        )
        claims = self._verify(tokens.get("id_token", ""), client_id, pending.nonce)
        scopes = (tokens.get("scope") or params.get("scope") or "").replace("+", " ").split()
        host = self._host()
        host["client_id"] = client_id
        self._write(self._host_path, host)
        self._save_tokens(tokens, client_id, scopes, claims)
        return pending.return_to

    def _save_tokens(self, tokens: dict, client_id: str, scopes: list[str], claims: dict | None) -> None:
        previous = self.credentials() or {}
        self._write_creds(
            {
                "email": (claims or {}).get("email") or previous.get("email"),
                "subject": (claims or {}).get("sub") or previous.get("subject"),
                "client_id": client_id,
                "id_token": tokens.get("id_token") or previous.get("id_token"),
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token") or previous.get("refresh_token"),
                "token_type": tokens.get("token_type", "Bearer"),
                "expires_at": time.time() + float(tokens.get("expires_in") or 3600),
                "scopes": scopes or previous.get("scopes", []),
            },
        )

    def _verify_with_jwks(self, id_token: str, client_id: str, nonce: str) -> dict:
        try:
            key = jwt.PyJWKClient(JWKS_URL, ssl_context=_SSL).get_signing_key_from_jwt(id_token)
            claims = jwt.decode(id_token, key.key, algorithms=["RS256"], audience=client_id, issuer=ISSUER)
        except jwt.PyJWTError as exc:
            raise ChatGPTAuthError(f"Couldn't verify the sign-in with OpenAI: {exc}", "id_token") from exc
        if claims.get("nonce") != nonce:
            raise ChatGPTAuthError("Sign-in verification failed (nonce mismatch). Try again.", "nonce")
        return claims

    # ---- use ------------------------------------------------------------------------------

    def access_token(self) -> str:
        """A valid access token for plan usage, refreshed when close to expiry."""
        with self._lock:
            creds = self.credentials()
            if not creds:
                raise ChatGPTAuthError("Sign in with ChatGPT in Settings first.", "signed_out")
            if PLAN_SCOPE not in creds.get("scopes", []):
                raise ChatGPTAuthError(
                    "Your ChatGPT sign-in doesn't include plan usage. It needs an eligible Plus or Pro plan; "
                    "sign out and sign in again, or use an API key instead.",
                    "no_plan_usage",
                )
            if creds.get("expires_at", 0) - time.time() > REFRESH_MARGIN_SECONDS:
                return creds["access_token"]
            try:
                tokens = self._post_form(
                    TOKEN_URL,
                    {
                        "grant_type": "refresh_token",
                        "client_id": creds["client_id"],
                        "refresh_token": creds.get("refresh_token", ""),
                        "resource": RESOURCE,
                    },
                )
            except ChatGPTAuthError as exc:
                if exc.code in TERMINAL_REFRESH_ERRORS:
                    self._creds_path.unlink(missing_ok=True)
                    raise ChatGPTAuthError(
                        "Your ChatGPT sign-in expired. Sign in again in Settings.", exc.code
                    ) from exc
                raise
            self._save_tokens(tokens, creds["client_id"], (tokens.get("scope") or "").split(), None)
            return tokens["access_token"]

    def sign_out(self) -> bool:
        """Revoke the refresh token and forget the tokens. Returns whether OpenAI confirmed revocation."""
        creds = self.credentials()
        confirmed = False
        if creds and creds.get("refresh_token"):
            try:
                self._post_form(
                    REVOKE_URL,
                    {
                        "token": creds["refresh_token"],
                        "token_type_hint": "refresh_token",
                        "client_id": creds["client_id"],
                    },
                )
                confirmed = True
            except ChatGPTAuthError:
                confirmed = False
        self._creds_path.unlink(missing_ok=True)
        return confirmed


_instance: ChatGPTAuth | None = None


def configure(data_dir: Path, cipher=None) -> ChatGPTAuth:
    global _instance
    _instance = ChatGPTAuth(data_dir, cipher=cipher)
    return _instance


def get_auth() -> ChatGPTAuth:
    if _instance is None:
        raise ChatGPTAuthError("ChatGPT sign-in is not configured.", "not_configured")
    return _instance
