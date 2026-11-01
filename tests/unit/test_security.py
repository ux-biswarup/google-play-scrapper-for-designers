"""API keys stay out of the browser and the disk in plain text; other websites can't use the server."""

from __future__ import annotations

import json
import stat

import pytest
from conftest import RUN_BODY, wait_for_run

from backend.services.chatgpt_auth import ChatGPTAuth
from backend.services.vault import Vault, VaultError, mask

SECRET = "sk-live-this-is-a-very-secret-key-a1b2"


def test_vault_encrypts_at_rest_and_masks(tmp_path):
    vault = Vault(tmp_path, use_keychain=False)
    info = vault.set("provider:openai", SECRET)
    assert info["hint"] == "sk-…a1b2" and info["storage"] == "saved"
    raw = (tmp_path / "secrets.enc").read_bytes()
    assert SECRET.encode() not in raw  # encrypted on disk
    assert stat.S_IMODE((tmp_path / "secrets.enc").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / ".vault-key").stat().st_mode) == 0o600
    assert Vault(tmp_path, use_keychain=False).get("provider:openai") == SECRET  # survives restarts

    vault.set("provider:groq", "gsk_session_only_9999", remember=False)
    assert vault.describe("provider:groq")["storage"] == "session"
    assert Vault(tmp_path, use_keychain=False).get("provider:groq") is None  # gone after a restart
    vault.delete("provider:openai")
    assert vault.get("provider:openai") is None
    assert mask("short") == "…rt"


def test_vault_with_wrong_master_key_cannot_read(tmp_path):
    Vault(tmp_path, use_keychain=False).set("provider:openai", SECRET)
    (tmp_path / ".vault-key").write_bytes(b"x" * 43 + b"=")  # someone swaps or loses the key
    with pytest.raises((VaultError, ValueError)):
        Vault(tmp_path, use_keychain=False)._read()


def test_keys_api_never_returns_the_key(client):
    saved = client.put("/api/keys/openai", json={"api_key": SECRET})
    assert saved.status_code == 200 and SECRET not in saved.text
    listing = client.get("/api/keys").json()
    assert listing["protection"] == "file" and listing["keys"][0]["hint"] == "sk-…a1b2"
    providers = {p["id"]: p for p in client.get("/api/providers").json()}
    assert providers["openai"]["saved_key"]["hint"] == "sk-…a1b2"
    assert SECRET not in client.get("/api/providers").text
    assert client.put("/api/keys/chatgpt", json={"api_key": "x"}).status_code == 404
    assert client.delete("/api/keys/openai").status_code == 204
    assert client.get("/api/keys").json()["keys"] == []


def test_saved_key_is_used_when_the_browser_sends_none(client, monkeypatch):
    seen = []
    ctx = client.app.state.ctx
    original = ctx.provider_factory

    def spy(config):
        seen.append(config.api_key)
        return original(config)

    monkeypatch.setattr(ctx, "provider_factory", spy)
    monkeypatch.setattr(ctx.pipeline, "provider_factory", spy)
    client.put("/api/keys/anthropic", json={"api_key": SECRET})
    body = RUN_BODY | {"llm": {"provider": "anthropic", "model": "fake-model"}}  # no key from the browser
    run = wait_for_run(client, client.post("/api/runs", json=body).json()["id"])
    assert run["status"] == "completed"
    assert seen and all(key == SECRET for key in seen)


def test_other_websites_and_hosts_are_blocked(client):
    evil = client.post("/api/keys/openai", json={"api_key": SECRET}, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    evil_put = client.put("/api/keys/openai", json={"api_key": SECRET}, headers={"Origin": "https://evil.example"})
    assert evil_put.status_code == 403 and client.get("/api/keys").json()["keys"] == []
    ok = client.put("/api/keys/openai", json={"api_key": SECRET}, headers={"Origin": "http://localhost:5173"})
    assert ok.status_code == 200
    rebinding = client.get("/api/health", headers={"Host": "attacker.example"})
    assert rebinding.status_code == 421
    headers = client.get("/api/health").headers
    assert headers["x-frame-options"] == "DENY" and headers["x-content-type-options"] == "nosniff"


def test_chatgpt_tokens_are_encrypted_at_rest(tmp_path):
    vault = Vault(tmp_path, use_keychain=False)
    legacy = {"client_id": "oaiapp_1", "access_token": "secret-access", "scopes": [], "email": "a@b.c"}
    (tmp_path / "chatgpt-auth.json").write_text(json.dumps(legacy))  # file from before encryption
    auth = ChatGPTAuth(tmp_path, cipher=vault)
    assert auth.credentials()["access_token"] == "secret-access"
    assert b"secret-access" not in (tmp_path / "chatgpt-auth.json").read_bytes()  # re-saved encrypted
    assert auth.credentials()["email"] == "a@b.c"
