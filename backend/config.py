from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT_DIR / "data"
    database_url: str | None = None
    # Reviews sent to the model per request, and how many requests run in parallel.
    batch_size: int = 25
    llm_concurrency: int = 4
    max_reviews_per_run: int = 2000
    cors_origins: tuple[str, ...] = field(
        default=("http://localhost:5173", "http://127.0.0.1:5173")
    )

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'app.db'}"


def load_settings() -> Settings:
    defaults = Settings()
    origins = os.getenv("CORS_ORIGINS")
    return Settings(
        data_dir=Path(os.getenv("APP_DATA_DIR", str(defaults.data_dir))),
        database_url=os.getenv("DATABASE_URL") or None,
        batch_size=int(os.getenv("LLM_BATCH_SIZE", defaults.batch_size)),
        llm_concurrency=int(os.getenv("LLM_CONCURRENCY", defaults.llm_concurrency)),
        cors_origins=tuple(o.strip() for o in origins.split(",")) if origins else defaults.cors_origins,
    )
