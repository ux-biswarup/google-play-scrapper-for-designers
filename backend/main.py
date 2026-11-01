"""FastAPI application. Run with: uvicorn backend.main:app --reload --port 8000"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google_play_scraper.exceptions import ExtraHTTPError

from .analytics.frame import FrameCache
from .api import apps, insights, providers, runs
from .config import Settings, load_settings
from .context import AppContext
from .db import Database
from .jobs import JobManager
from .providers import LLMError, create_provider
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
    ctx = AppContext(
        settings=settings, db=db, store=store, provider_factory=provider_factory, jobs=jobs,
        pipeline=AnalysisPipeline(db, store, provider_factory, settings), frames=FrameCache(),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        db.init()
        ctx.pipeline.mark_interrupted()
        yield
        await jobs.shutdown()

    app = FastAPI(title="Play Store Review Insights API", version=__version__, lifespan=lifespan)
    app.state.ctx = ctx
    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"]
    )

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

    for router in (providers.router, apps.router, runs.router, insights.router):
        app.include_router(router, prefix="/api")
    return app


load_dotenv()  # optional fallback API keys; keys pasted in the interface take precedence
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
