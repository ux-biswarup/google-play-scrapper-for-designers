from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from .analytics.frame import FrameCache
from .config import Settings
from .db import Database
from .jobs import JobManager
from .services.pipeline import AnalysisPipeline, ProviderFactory
from .services.play_store import PlayStoreClient


@dataclass
class AppContext:
    settings: Settings
    db: Database
    store: PlayStoreClient
    provider_factory: ProviderFactory
    jobs: JobManager
    pipeline: AnalysisPipeline
    frames: FrameCache


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx
