"""Save, replace and remove API keys. Keys go into the encrypted vault; only masked hints come back."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, SecretStr

from ..providers import PROVIDERS
from ..services.vault import VaultError, get_vault

router = APIRouter(prefix="/keys", tags=["keys"])


class KeyIn(BaseModel):
    api_key: SecretStr = Field(description="The key. Stored encrypted; never returned.")
    remember: bool = Field(True, description="False keeps it in memory until the app stops.")


def _vault():
    vault = get_vault()
    if vault is None:
        raise HTTPException(503, "Key storage isn't available.")
    return vault


def _provider(provider: str) -> str:
    if provider not in PROVIDERS or provider == "chatgpt":
        raise HTTPException(404, f"Unknown provider '{provider}'.")
    return provider


@router.get("")
def list_keys() -> dict:
    vault = _vault()
    return {"protection": vault.protection, "keys": vault.list()}


@router.put("/{provider}")
def save_key(provider: str, body: KeyIn) -> dict:
    try:
        return _vault().set(f"provider:{_provider(provider)}", body.api_key.get_secret_value(), remember=body.remember)
    except VaultError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/{provider}", status_code=204)
def delete_key(provider: str) -> Response:
    _vault().delete(f"provider:{_provider(provider)}")
    return Response(status_code=204)
