"""Load one run's reviews + AI tags into a pandas DataFrame (the input to every analytics function)."""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock

import pandas as pd
from sqlalchemy import and_, select

from ..db import Database
from ..models import Insight, Review, Run, RunReview

COLUMNS = [
    "review_id", "date", "rating", "sentiment", "content", "app_version", "thumbs_up", "reply",
    "category", "themes", "journey_stage", "emotion", "tagged",
]


def sentiment_from_rating(rating: int) -> str:
    if rating <= 2:
        return "negative"
    if rating == 3:
        return "neutral"
    return "positive"


class FrameCache:
    """Small LRU so dashboards don't rebuild the DataFrame on every request."""

    def __init__(self, size: int = 16):
        self._size = size
        self._items: OrderedDict[str, tuple[tuple, pd.DataFrame]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str, stamp: tuple) -> pd.DataFrame | None:
        with self._lock:
            hit = self._items.get(key)
            if hit and hit[0] == stamp:
                self._items.move_to_end(key)
                return hit[1]
            return None

    def put(self, key: str, stamp: tuple, df: pd.DataFrame) -> None:
        with self._lock:
            self._items[key] = (stamp, df)
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)


def load_run_frame(db: Database, run_id: str, cache: FrameCache | None = None) -> pd.DataFrame | None:
    with db.session() as s:
        run = s.get(Run, run_id)
        if run is None:
            return None
        stamp = (run.status, run.finished_at, run.progress_done)
        if cache and (hit := cache.get(run_id, stamp)) is not None:
            return hit.copy()
        theme_map: dict[str, str] = run.theme_map or {}
        rows = s.execute(
            select(
                Review.store_review_id, Review.reviewed_at, Review.rating, Review.content, Review.app_version,
                Review.thumbs_up, Review.reply_content, Insight.id.label("insight_id"), Insight.category,
                Insight.themes, Insight.journey_stage, Insight.emotion,
            )
            .join(RunReview, RunReview.review_id == Review.id)
            .outerjoin(Insight, and_(Insight.review_id == Review.id, Insight.model_key == run.model_key))
            .where(RunReview.run_id == run_id)
        ).all()

    records = []
    for r in rows:
        themes: list[str] = []
        for label in r.themes or []:
            canonical = theme_map.get(label, label)
            if canonical and canonical not in themes:  # "" = discarded as too vague
                themes.append(canonical)
        records.append({
            "review_id": r.store_review_id,
            "date": r.reviewed_at,
            "rating": int(r.rating),
            "sentiment": sentiment_from_rating(int(r.rating)),
            "content": r.content or "",
            "app_version": r.app_version or "unknown",
            "thumbs_up": int(r.thumbs_up or 0),
            "reply": r.reply_content,
            "category": r.category,
            "themes": themes,
            "journey_stage": r.journey_stage,
            "emotion": r.emotion,
            "tagged": r.insight_id is not None,
        })
    df = pd.DataFrame.from_records(records, columns=COLUMNS)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if cache:
        cache.put(run_id, stamp, df)
    return df.copy()
