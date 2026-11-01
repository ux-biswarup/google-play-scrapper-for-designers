"""Sign-in options that avoid pasting API keys: ChatGPT plan and OpenRouter."""

from __future__ import annotations

import asyncio
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import certifi
from fastapi import APIRouter, HTTPException
from fastapi import Request as HttpRequest
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..services.chatgpt_auth import ChatGPTAuthError, get_auth

router = APIRouter(prefix="/auth", tags=["auth"])

OPENROUTER_KEYS_URL = "https://openrouter.ai/api/v1/auth/keys"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _local_origin(value: str) -> str:
    """Only send people back to this app on this computer (never an arbitrary site)."""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in LOCAL_HOSTS:
        raise HTTPException(400, "Sign-in must start from the app on this computer.")
    return f"{parsed.scheme}://{parsed.netloc}"


class StartIn(BaseModel):
    return_to: str


@router.get("/chatgpt")
def chatgpt_status() -> dict:
    return get_auth().status()


@router.post("/chatgpt/start")
def chatgpt_start(body: StartIn, request: HttpRequest) -> dict:
    return_to = _local_origin(body.return_to)
    port = request.url.port or 8000
    return {"url": get_auth().start(port=port, return_to=return_to)}


@router.get("/chatgpt/callback", include_in_schema=False)
async def chatgpt_callback(request: HttpRequest) -> RedirectResponse:
    params = dict(request.query_params)
    try:
        return_to = await asyncio.to_thread(get_auth().complete, params)
        query = {"chatgpt": "connected"}
    except ChatGPTAuthError as exc:
        return_to = f"http://127.0.0.1:{request.url.port or 8000}"
        query = {"chatgpt_error": str(exc)}
    return RedirectResponse(f"{return_to}/settings?{urlencode(query)}", status_code=303)


@router.post("/chatgpt/signout")
async def chatgpt_signout() -> dict:
    return {"revoked": await asyncio.to_thread(get_auth().sign_out)}


class OpenRouterExchangeIn(BaseModel):
    code: str = Field(min_length=1)
    code_verifier: str = Field(min_length=43)


@router.post("/openrouter/exchange")
async def openrouter_exchange(body: OpenRouterExchangeIn) -> dict:
    """Swap the code from OpenRouter's login page for a user API key (OAuth PKCE, no client secret)."""

    def exchange() -> dict:
        request = Request(
            OPENROUTER_KEYS_URL,
            data=json.dumps(
                {"code": body.code, "code_verifier": body.code_verifier, "code_challenge_method": "S256"}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, context=ssl.create_default_context(cafile=certifi.where()), timeout=30) as r:
                return json.loads(r.read())
        except HTTPError as exc:
            raise HTTPException(400, f"OpenRouter didn't accept the sign-in (HTTP {exc.code}). Try again.") from exc
        except URLError as exc:
            raise HTTPException(502, "Could not reach OpenRouter.") from exc

    data = await asyncio.to_thread(exchange)
    if not data.get("key"):
        raise HTTPException(400, "OpenRouter didn't return a key. Try again.")
    return {"key": data["key"]}
