"""Encrypted storage for API keys and sign-in tokens, so they never have to live in the browser.

- Secrets are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) in data/secrets.enc.
- The encryption key is kept in the operating system's keychain (macOS Keychain, Windows Credential
  Manager, Linux Secret Service). Copying the data folder alone does not reveal any secret.
- Where no keychain is available (servers, CI) the encryption key falls back to data/.vault-key,
  readable only by the current user; the app reports this so users know the protection level.
- "Session only" keys are kept in memory and disappear when the server stops.
- Nothing here ever returns a full key to the API; callers get masked hints.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

SERVICE = "review-insights"
KEYCHAIN_ENTRY = "vault-master-key"


class VaultError(Exception):
    pass


def mask(secret: str) -> str:
    """A recognisable but useless hint, e.g. 'sk-…a1b2'."""
    secret = secret.strip()
    if len(secret) <= 8:
        return "…" + secret[-2:]
    prefix = secret[:3] if secret[:3].isascii() else ""
    return f"{prefix}…{secret[-4:]}"


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


class Vault:
    def __init__(self, data_dir: Path, *, use_keychain: bool | None = None, master_key: bytes | None = None):
        self.data_dir = data_dir
        self._path = data_dir / "secrets.enc"
        self._lock = threading.Lock()
        self._session: dict[str, dict] = {}
        if use_keychain is None:
            use_keychain = os.getenv("REVIEW_INSIGHTS_KEYCHAIN", "on").lower() not in ("off", "0", "false")
        self.protection = "provided"
        self._fernet = Fernet(master_key or self._load_master_key(use_keychain))

    # ---- master key ------------------------------------------------------------------------

    def _load_master_key(self, use_keychain: bool) -> bytes:
        if use_keychain:
            try:
                import keyring
                from keyring.errors import KeyringError

                try:
                    existing = keyring.get_password(SERVICE, KEYCHAIN_ENTRY)
                    if not existing:
                        existing = Fernet.generate_key().decode()
                        keyring.set_password(SERVICE, KEYCHAIN_ENTRY, existing)
                    self.protection = "keychain"
                    return existing.encode()
                except KeyringError:
                    pass
            except ImportError:
                pass
        key_file = self.data_dir / ".vault-key"
        if not key_file.exists():
            _write_private(key_file, Fernet.generate_key())
        self.protection = "file"
        return key_file.read_bytes().strip()

    # ---- encryption helpers (also used for ChatGPT tokens) ------------------------------------

    def encrypt(self, data: bytes) -> bytes:
        return self._fernet.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        try:
            return self._fernet.decrypt(token)
        except InvalidToken as exc:
            raise VaultError(
                "Saved secrets can't be decrypted (the encryption key changed). Save your keys again."
            ) from exc

    # ---- stored keys -----------------------------------------------------------------------

    def _read(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        return json.loads(self.decrypt(self._path.read_bytes()))

    def _write(self, data: dict[str, dict]) -> None:
        _write_private(self._path, self.encrypt(json.dumps(data).encode()))

    def set(self, name: str, secret: str, *, remember: bool = True) -> dict:
        secret = secret.strip()
        if not secret:
            raise VaultError("The key is empty.")
        entry = {"secret": secret, "saved_at": time.time()}
        with self._lock:
            stored = self._read()
            if remember:
                stored[name] = entry
                self._session.pop(name, None)
            else:
                stored.pop(name, None)
                self._session[name] = entry
            self._write(stored)
        return self.describe(name)

    def get(self, name: str) -> str | None:
        with self._lock:
            entry = self._session.get(name)
            if entry is None:
                try:
                    entry = self._read().get(name)
                except VaultError:
                    entry = None
        return entry["secret"] if entry else None

    def delete(self, name: str) -> None:
        with self._lock:
            self._session.pop(name, None)
            stored = self._read()
            if stored.pop(name, None) is not None:
                self._write(stored)

    def describe(self, name: str) -> dict | None:
        with self._lock:
            if name in self._session:
                entry, storage = self._session[name], "session"
            else:
                entry, storage = self._read().get(name), "saved"
        if not entry:
            return None
        return {"name": name, "hint": mask(entry["secret"]), "storage": storage, "saved_at": entry["saved_at"]}

    def list(self) -> list[dict]:
        with self._lock:
            names = set(self._read()) | set(self._session)
        return [d for d in (self.describe(n) for n in sorted(names)) if d]


_instance: Vault | None = None


def configure(data_dir: Path, **kwargs) -> Vault:
    global _instance
    _instance = Vault(data_dir, **kwargs)
    return _instance


def get_vault() -> Vault | None:
    return _instance
