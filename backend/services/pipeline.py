"""End-to-end analysis run: fetch app + reviews, tag with AI in batches, group themes, persist."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy import select, update

from ..config import Settings
from ..db import Database, utcnow
from ..models import App, Insight, Review, Run, RunReview, RunStatus
from ..providers import LLMConfig, LLMError, LLMProvider, Usage
from .play_store import AppDetails, AppNotFound, PlayStoreClient, StoreReview
from .tagging import ReviewInput, TagResult, tag_reviews
from .themes import build_theme_map

log = logging.getLogger(__name__)

ProviderFactory = Callable[[LLMConfig], LLMProvider]


class PipelineError(Exception):
    """A run failed for a reason the user can act on."""


class _Cancelled(Exception):
    pass


@dataclass
class RunRequest:
    store_id: str
    country: str
    lang: str
    count: int
    ratings: list[int] | None
    output_language: str
    llm: LLMConfig


class AnalysisPipeline:
    def __init__(self, db: Database, store: PlayStoreClient, provider_factory: ProviderFactory, settings: Settings):
        self.db = db
        self.store = store
        self.provider_factory = provider_factory
        self.settings = settings

    # ----- run lifecycle -------------------------------------------------

    def create_run(self, req: RunRequest) -> str:
        with self.db.session() as s:
            app = self._get_or_create_app(s, req.store_id)
            run = Run(
                id=uuid.uuid4().hex,
                app_id=app.id,
                country=req.country,
                lang=req.lang,
                ratings=sorted(set(req.ratings)) if req.ratings else None,
                requested_count=req.count,
                output_language=req.output_language,
                provider=req.llm.provider,
                model=req.llm.model,
                status=RunStatus.QUEUED,
                message="Waiting to start…",
            )
            s.add(run)
            return run.id

    def mark_interrupted(self) -> None:
        """Runs can't survive a server restart (the API key only lived in memory)."""
        with self.db.session() as s:
            s.execute(
                update(Run)
                .where(Run.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]))
                .values(
                    status=RunStatus.FAILED,
                    error="Interrupted because the server restarted. Start the analysis again.",
                    finished_at=utcnow(),
                )
            )

    async def execute(self, run_id: str, llm: LLMConfig, cancel: asyncio.Event) -> None:
        provider: LLMProvider | None = None
        try:
            run = self._get_run(run_id)
            store_id, country, lang = run.app.store_id, run.country or "us", run.lang or "en"
            self._update(run_id, status=RunStatus.RUNNING, started_at=utcnow(), stage="fetching_app",
                         message="Looking up the app…")
            details = await asyncio.to_thread(self.store.app_details, store_id, lang=lang, country=country)
            self._save_app(run.app_id, details)
            self._check(cancel)

            self._update(run_id, stage="fetching_reviews", progress_done=0, progress_total=run.requested_count,
                         message="Downloading reviews from Google Play…")

            def on_fetch(done: int, total: int) -> None:
                self._update(run_id, progress_done=done, progress_total=total)

            reviews = await asyncio.to_thread(
                self.store.fetch_reviews, store_id, lang=lang, country=country,
                count=run.requested_count, ratings=run.ratings, on_progress=on_fetch,
            )
            if not reviews:
                raise PipelineError("No reviews found for this app with these settings. Try another country or language.")
            review_ids = self._save_reviews(run, reviews)
            self._check(cancel)

            todo = self._untagged(review_ids, llm.model_key)
            reused = len(review_ids) - len(todo)
            note = f" ({reused} already analyzed with this model)" if reused else ""
            self._update(run_id, stage="analyzing", review_count=len(review_ids), progress_done=reused,
                         progress_total=len(review_ids), message=f"Analyzing {len(todo)} reviews with AI{note}…")

            provider = self.provider_factory(llm)

            async def on_batch(results: dict[int, TagResult], done: int, _total: int, usage: Usage) -> None:
                self._save_insights(results, llm.model_key)
                self._update(run_id, progress_done=reused + done,
                             input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)

            outcome = await tag_reviews(
                provider, todo,
                batch_size=self.settings.batch_size, concurrency=self.settings.llm_concurrency,
                output_language=run.output_language, on_batch_done=on_batch, cancel=cancel,
                app_context=" ".join(filter(None, [details.title, f"({details.genre})" if details.genre else ""])),
            )
            self._check(cancel)
            if todo and outcome.failed >= len(todo):
                detail = f" Last error: {outcome.errors[-1]}" if outcome.errors else ""
                raise PipelineError(f"The AI could not analyze any reviews.{detail}")

            self._update(run_id, stage="grouping_themes", message="Grouping similar themes…")
            usage = outcome.usage
            theme_map, grouping_usage, warning = await build_theme_map(
                provider, self._label_counts(review_ids, llm.model_key), output_language=run.output_language
            )
            usage.add(grouping_usage)

            notes = []
            if outcome.failed:
                notes.append(f"{outcome.failed} reviews could not be analyzed")
            if warning:
                notes.append(warning)
            self._update(
                run_id, status=RunStatus.COMPLETED, stage="done", theme_map=theme_map,
                tagged_count=len(review_ids) - outcome.failed, failed_count=outcome.failed,
                input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                progress_done=len(review_ids), finished_at=utcnow(),
                message="Analysis complete" + (f" ({'; '.join(notes)})" if notes else ""),
            )
        except (_Cancelled, asyncio.CancelledError) as exc:
            self._update(run_id, status=RunStatus.CANCELLED, message="Cancelled", finished_at=utcnow())
            if isinstance(exc, asyncio.CancelledError):
                raise
        except (PipelineError, LLMError, AppNotFound, ValueError) as exc:
            self._update(run_id, status=RunStatus.FAILED, error=str(exc), finished_at=utcnow())
        except Exception as exc:  # noqa: BLE001 - surface anything unexpected to the user
            log.exception("Run %s failed", run_id)
            self._update(run_id, status=RunStatus.FAILED, error=f"Unexpected error: {exc}", finished_at=utcnow())
        finally:
            if provider is not None:
                await provider.aclose()

    # ----- persistence helpers -------------------------------------------

    @staticmethod
    def _check(cancel: asyncio.Event) -> None:
        if cancel.is_set():
            raise _Cancelled()

    def _get_run(self, run_id: str) -> Run:
        with self.db.session() as s:
            run = s.get(Run, run_id)
            if run is None:
                raise PipelineError("Run not found.")
            return run

    def _update(self, run_id: str, **values) -> None:
        with self.db.session() as s:
            s.execute(update(Run).where(Run.id == run_id).values(**values))

    def _get_or_create_app(self, s, store_id: str) -> App:
        platform = self.store.platform
        app = s.scalar(select(App).where(App.platform == platform, App.store_id == store_id))
        if app is None:
            app = App(platform=platform, store_id=store_id)
            s.add(app)
            s.flush()
        return app

    def _save_app(self, app_id: int, d: AppDetails) -> None:
        with self.db.session() as s:
            s.execute(
                update(App).where(App.id == app_id).values(
                    title=d.title, developer=d.developer, icon_url=d.icon_url, genre=d.genre, score=d.score,
                    ratings_count=d.ratings_count, installs=d.installs, version=d.version, store_url=d.store_url,
                    updated_at=utcnow(),
                )
            )

    def _save_reviews(self, run: Run, reviews: Sequence[StoreReview]) -> list[int]:
        with self.db.session() as s:
            existing = {
                r.store_review_id: r
                for r in s.scalars(
                    select(Review).where(
                        Review.app_id == run.app_id,
                        Review.store_review_id.in_([r.review_id for r in reviews]),
                    )
                )
            }
            rows: list[Review] = []
            for r in reviews:
                row = existing.get(r.review_id)
                if row is None:
                    row = Review(app_id=run.app_id, store_review_id=r.review_id)
                    s.add(row)
                # Reviews can be edited on the store; keep the latest text.
                row.rating, row.content, row.reviewed_at = r.rating, r.content, r.reviewed_at
                row.app_version, row.thumbs_up, row.reply_content = r.app_version, r.thumbs_up, r.reply_content
                row.country, row.lang = run.country, run.lang
                rows.append(row)
            s.flush()
            ids = [row.id for row in rows]
            s.add_all(RunReview(run_id=run.id, review_id=i) for i in ids)
            return ids

    def _untagged(self, review_ids: list[int], model_key: str) -> list[ReviewInput]:
        with self.db.session() as s:
            done = set(
                s.scalars(select(Insight.review_id).where(Insight.model_key == model_key, Insight.review_id.in_(review_ids)))
            )
            rows = s.execute(select(Review.id, Review.rating, Review.content).where(Review.id.in_(review_ids))).all()
        return [ReviewInput(r.id, r.rating, r.content or "") for r in rows if r.id not in done]

    def _save_insights(self, results: dict[int, TagResult], model_key: str) -> None:
        if not results:
            return
        with self.db.session() as s:
            have = set(
                s.scalars(select(Insight.review_id).where(Insight.model_key == model_key, Insight.review_id.in_(list(results))))
            )
            s.add_all(
                Insight(review_id=rid, model_key=model_key, category=t.category, themes=t.themes,
                        journey_stage=t.journey_stage, emotion=t.emotion)
                for rid, t in results.items()
                if rid not in have
            )

    def _label_counts(self, review_ids: list[int], model_key: str) -> Counter:
        counts: Counter = Counter()
        with self.db.session() as s:
            for themes in s.scalars(
                select(Insight.themes).where(Insight.model_key == model_key, Insight.review_id.in_(review_ids))
            ):
                counts.update(themes or [])
        return counts
