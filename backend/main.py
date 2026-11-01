"""FastAPI application. Run with: uvicorn backend.main:app --reload --port 8000

If the frontend has been built (web/dist), it is served from the same address.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google_play_scraper.exceptions import ExtraHTTPError

from .analytics.frame import FrameCache
from .api import apps, artifacts, auth, chat, connect, insights, keys, providers, runs, views
from .assistant.tools import ToolContext
from .config import Settings, load_settings
from .context import AppContext
from .db import Database
from .jobs import JobManager
from .mcp_server import build_mcp_server, http_security
from .providers import LLMError, create_provider
from .security import LocalOnlyMiddleware
from .services import chatgpt_auth, vault
from .services.pipeline import AnalysisPipeline, ProviderFactory
from .services.play_store import AppNotFound, PlayStoreClient

__version__ = "0.2.0"


def create_app(
    settings: Settings | None = None,
    *,
    db: Database | None = None,
    store: PlayStoreClient | None = None,
    provider_factory: ProviderFactory | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    db = db or Database(settings.db_url)
    store = store or PlayStoreClient()
    provider_factory = provider_factory or create_provider
    jobs = JobManager()
    secrets = vault.configure(settings.data_dir, use_keychain=settings.use_keychain)
    chatgpt_auth.configure(settings.data_dir, cipher=secrets)
    ctx = AppContext(
        settings=settings,
        db=db,
        store=store,
        provider_factory=provider_factory,
        jobs=jobs,
        pipeline=AnalysisPipeline(db, store, provider_factory, settings),
        frames=FrameCache(),
    )

    # MCP over HTTP at /mcp/ for MCP apps that connect by URL.
    mcp = build_mcp_server(ToolContext(db, ctx.frames))
    mcp_http = mcp.streamable_http_app(streamable_http_path="/", transport_security=http_security())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        db.init()
        ctx.pipeline.mark_interrupted()
        async with mcp.session_manager.run():
            yield
        await jobs.shutdown()

    app = FastAPI(title="Play Store Review Insights API", version=__version__, lifespan=lifespan)
    app.state.ctx = ctx
    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"]
    )
    extra_hosts = tuple(h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip())
    app.add_middleware(LocalOnlyMiddleware, allowed_hosts=settings.allowed_hosts + extra_hosts)

    @app.exception_handler(ValueError)
    async def _bad_request(_req: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(LLMError)
    async def _llm_error(_req: Request, exc: LLMError):
        return JSONResponse({"detail": str(exc)}, status_code=400 if exc.fatal else 502)

    @app.exception_handler(AppNotFound)
    async def _not_found(_req: Request, exc: AppNotFound):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(ExtraHTTPError)
    async def _store_error(_req: Request, _exc: ExtraHTTPError):
        return JSONResponse({"detail": "Google Play did not respond as expected. Try again shortly."}, status_code=502)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    for router in (
        providers.router,
        apps.router,
        runs.router,
        insights.router,
        chat.router,
        connect.router,
        auth.router,
        views.router,
        artifacts.router,
        keys.router,
    ):
        app.include_router(router, prefix="/api")
    app.mount("/mcp", mcp_http)
    if (settings.web_dist / "index.html").is_file():
        _serve_frontend(app, settings.web_dist)
    return app


def _serve_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built single-page app; unknown paths fall back to index.html for client-side routing."""
    root = dist.resolve()
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(root / "index.html")


load_dotenv()  # optional fallback API keys; keys pasted in the interface take precedence
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
