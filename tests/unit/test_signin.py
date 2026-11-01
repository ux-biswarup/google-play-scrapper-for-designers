"""Sign in with ChatGPT and OpenRouter connect, with OpenAI/OpenRouter servers faked."""

from __future__ import annotations

import base64
import hashlib
import stat
import time
from urllib.parse import parse_qs, urlparse

import pytest

from backend.providers import ChatMessage, ToolCall
from backend.providers.chatgpt_provider import _to_input, safe_prefix, split_tool_calls
from backend.services.chatgpt_auth import (
    PLAN_SCOPE,
    REGISTRATION_CLIENT,
    TOKEN_URL,
    ChatGPTAuth,
    ChatGPTAuthError,
)

SCOPES = f"openid profile email offline_access resource.invoke {PLAN_SCOPE}"


class FakeOpenAI:
    """Stands in for auth.openai.com token, refresh and revoke endpoints."""

    def __init__(self):
        self.requests: list[tuple[str, dict]] = []
        self.refresh_error: str | None = None

    def post_form(self, url: str, fields: dict) -> dict:
        self.requests.append((url, fields))
        if url != TOKEN_URL:
            return {}
        if fields["grant_type"] == "refresh_token":
            if self.refresh_error:
                raise ChatGPTAuthError("refresh failed", self.refresh_error)
            return {"access_token": "access-2", "refresh_token": "refresh-2", "expires_in": 3600, "scope": SCOPES}
        return {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "id_token": "id-token",
            "expires_in": 3600,
            "scope": SCOPES,
        }


@pytest.fixture
def server():
    return FakeOpenAI()


@pytest.fixture
def auth(tmp_path, server):
    def verify(id_token, client_id, nonce):
        return {"sub": "user-1", "email": "designer@example.com", "aud": client_id, "nonce": nonce}

    return ChatGPTAuth(tmp_path, post_form=server.post_form, verify_id_token=verify)


def _sign_in(auth: ChatGPTAuth, issued_client: str = "oaiapp_123") -> dict:
    url = auth.start(port=8000, return_to="http://127.0.0.1:8000")
    params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    auth.complete({"code": "code-1", "state": params["state"], "client_id": issued_client, "scope": SCOPES})
    return params


def test_authorize_url_follows_openai_spec(auth):
    url = auth.start(port=8123, return_to="http://127.0.0.1:8123")
    assert url.startswith("https://auth.openai.com/api/accounts/authorize?")
    params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert params["client_id"] == REGISTRATION_CLIENT and params["agent_name_hint"] == "Review Insights"
    assert params["redirect_uri"] == "http://127.0.0.1:8123/api/auth/chatgpt/callback"
    assert params["scope"] == SCOPES and params["resource"] == "https://api.openai.com/v1"
    assert params["response_type"] == "code" and params["code_challenge_method"] == "S256"
    assert params["ext_agent_host_id"].startswith("urn:uuid:")
    pending = auth._pending[params["state"]]
    expected = base64.urlsafe_b64encode(hashlib.sha256(pending.verifier.encode()).digest()).rstrip(b"=").decode()
    assert params["code_challenge"] == expected


def test_sign_in_stores_tokens_privately_and_reuses_the_issued_client(auth, server, tmp_path):
    first = _sign_in(auth)
    exchange = server.requests[0][1]
    assert exchange["grant_type"] == "authorization_code" and exchange["client_id"] == "oaiapp_123"
    assert exchange["redirect_uri"].startswith("http://127.0.0.1:8000/") and exchange["code_verifier"]
    assert auth.status() == {"signed_in": True, "email": "designer@example.com", "plan_usage": True}
    creds = tmp_path / "chatgpt-auth.json"
    assert stat.S_IMODE(creds.stat().st_mode) == 0o600
    assert auth.access_token() == "access-1"

    # Signing in again reuses the issued client ID and stops sending the registration hint.
    url = auth.start(port=8000, return_to="http://127.0.0.1:8000")
    params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert params["client_id"] == "oaiapp_123" and "agent_name_hint" not in params
    assert params["ext_agent_host_id"] == first["ext_agent_host_id"]


def test_callback_rejects_bad_state_cancel_and_mismatched_client(auth):
    with pytest.raises(ChatGPTAuthError, match="expired"):
        auth.complete({"state": "unknown", "code": "x"})
    url = auth.start(port=8000, return_to="http://127.0.0.1:8000")
    state = parse_qs(urlparse(url).query)["state"][0]
    with pytest.raises(ChatGPTAuthError, match="cancelled"):
        auth.complete({"state": state, "error": "access_denied"})
    url = auth.start(port=8000, return_to="http://127.0.0.1:8000")
    state = parse_qs(urlparse(url).query)["state"][0]
    with pytest.raises(ChatGPTAuthError, match="registering"):
        auth.complete({"state": state, "code": "x"})  # first registration must return a client_id


def test_refresh_near_expiry_and_terminal_refresh_errors(auth, server):
    _sign_in(auth)
    creds = auth.credentials()
    creds["expires_at"] = time.time() + 30
    auth._write(auth._creds_path, creds)
    assert auth.access_token() == "access-2"
    assert server.requests[-1][1]["grant_type"] == "refresh_token"
    assert auth.credentials()["refresh_token"] == "refresh-2"  # rotated token saved

    creds = auth.credentials()
    creds["expires_at"] = 0
    auth._write(auth._creds_path, creds)
    server.refresh_error = "refresh_token_reused"
    with pytest.raises(ChatGPTAuthError, match="Sign in again"):
        auth.access_token()
    assert auth.status()["signed_in"] is False


def test_missing_plan_scope_blocks_inference(auth, server):
    _sign_in(auth)
    creds = auth.credentials()
    creds["scopes"] = ["openid", "email"]
    auth._write(auth._creds_path, creds)
    with pytest.raises(ChatGPTAuthError, match="Plus or Pro"):
        auth.access_token()


def test_sign_out_revokes_refresh_token(auth, server):
    _sign_in(auth)
    assert auth.sign_out() is True
    url, fields = server.requests[-1]
    assert url.endswith("/oauth/revoke") and fields["token"] == "refresh-1"
    assert fields["token_type_hint"] == "refresh_token" and fields["client_id"] == "oaiapp_123"
    assert auth.status()["signed_in"] is False


def test_text_tool_protocol():
    text, calls = split_tool_calls(
        'Let me check.\n<tool_call>{"name": "get_problems", "arguments": {"limit": 3}}</tool_call>\n'
        '<tool_call>{"name": "search_reviews", "arguments": {"text": "ban"}}</tool_call>'
    )
    assert text == "Let me check."
    assert [(c.name, c.arguments) for c in calls] == [
        ("get_problems", {"limit": 3}),
        ("search_reviews", {"text": "ban"}),
    ]
    assert split_tool_calls("Plain answer.") == ("Plain answer.", [])
    # Streaming never shows a tool tag or its beginning.
    assert safe_prefix("Hello <tool") == len("Hello ")
    assert safe_prefix("Hello <tool_call>{") == len("Hello ")
    assert safe_prefix("Hello world") == len("Hello world")

    items = _to_input(
        [
            ChatMessage("user", "hi"),
            ChatMessage("assistant", "", tool_calls=[ToolCall("c1", "get_problems", {})]),
            ChatMessage("tool", '{"a": 1}', tool_call_id="c1", name="get_problems"),
            ChatMessage("tool", '{"b": 2}', tool_call_id="c2", name="get_overview"),
        ]
    )
    assert [i["role"] for i in items] == ["user", "assistant", "user"]
    assert "<tool_call>" in items[1]["content"] and items[2]["content"].count("<tool_result") == 2


def test_signin_api_guards(client):
    providers = {p["id"]: p for p in client.get("/api/providers").json()}
    assert providers["chatgpt"]["requires_key"] is False and providers["chatgpt"]["connected"] in (True, False)
    evil = client.post("/api/auth/chatgpt/start", json={"return_to": "https://evil.example"})
    assert evil.status_code == 400
    ok = client.post("/api/auth/chatgpt/start", json={"return_to": "http://localhost:5173"}).json()
    assert ok["url"].startswith("https://auth.openai.com/")
    expired = client.get("/api/auth/chatgpt/callback", params={"state": "nope", "code": "x"}, follow_redirects=False)
    assert expired.status_code == 303 and "chatgpt_error" in expired.headers["location"]
    assert client.post("/api/auth/openrouter/exchange", json={"code": "c", "code_verifier": "short"}).status_code == 422
