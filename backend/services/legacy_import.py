"""Import analyses made by the old Streamlit version (reports/<app>_reviews.json) into the database.

Old files only contain per-review topics, so imported runs have themes but no feedback type,
journey stage or emotion. Re-run the app to get the full analysis.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from ..db import Database, utcnow
from ..models import App, Insight, Review, Run, RunReview, RunStatus
from .tagging import MAX_THEMES_PER_REVIEW, normalize_theme

log = logging.getLogger(__name__)

LEGACY_PROVIDER = "legacy"
LEGACY_MODEL = "streamlit-import"


def _parse_date(value):
    ts = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(ts) else ts.to_pydatetime()


def import_legacy_reports(db: Database, reports_dir: Path) -> list[str]:
    """Create one completed run per app that has a *_reviews.json file. Skips apps imported before."""
    created: list[str] = []
    for path in sorted(reports_dir.glob("*_reviews.json")):
        store_id = path.name.removesuffix("_reviews.json")
        try:
            rows = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Skipping %s: %s", path.name, exc)
            continue
        if not rows:
            continue
        info: dict = {}
        report_path = reports_dir / f"{store_id}_report.json"
        if report_path.exists():
            info = json.loads(report_path.read_text()).get("app_info") or {}

        with db.session() as s:
            app = s.scalar(select(App).where(App.platform == "android", App.store_id == store_id))
            if app is None:
                app = App(platform="android", store_id=store_id)
                s.add(app)
                s.flush()
            elif s.scalar(select(Run.id).where(Run.app_id == app.id, Run.provider == LEGACY_PROVIDER)):
                continue
            app.title = app.title or info.get("title")
            app.developer = app.developer or info.get("developer")
            app.score = app.score or info.get("score")
            app.ratings_count = app.ratings_count or info.get("reviews")
            app.installs = app.installs or info.get("installs")

            run = Run(
                id=uuid.uuid4().hex,
                app_id=app.id,
                country=None,
                lang=None,
                ratings=None,
                requested_count=len(rows),
                provider=LEGACY_PROVIDER,
                model=LEGACY_MODEL,
                status=RunStatus.COMPLETED,
                stage="done",
                progress_done=len(rows),
                progress_total=len(rows),
                message="Imported from the previous version (themes only)",
                theme_map={},
                created_at=datetime.fromtimestamp(path.stat().st_mtime, UTC).replace(tzinfo=None),
                finished_at=utcnow(),
            )
            s.add(run)
            existing = {r.store_review_id: r for r in s.scalars(select(Review).where(Review.app_id == app.id))}
            model_key = f"{LEGACY_PROVIDER}:{LEGACY_MODEL}"
            seen: set[int] = set()
            for i, row in enumerate(rows):
                review_key = str(row.get("review_id") or f"legacy-{i}")
                review = existing.get(review_key)
                if review is None:
                    review = Review(
                        app_id=app.id,
                        store_review_id=review_key,
                        rating=int(row.get("rating") or 3),
                        content=row.get("content") or "",
                        reviewed_at=_parse_date(row.get("date")),
                        app_version=None
                        if row.get("app_version") in (None, "", "unknown")
                        else str(row["app_version"]),
                    )
                    s.add(review)
                    s.flush()
                    existing[review_key] = review
                if review.id in seen:
                    continue
                seen.add(review.id)
                s.add(RunReview(run_id=run.id, review_id=review.id))
                themes = []
                for label in row.get("topics") or []:
                    label = normalize_theme(label)
                    if label and label != "error" and label not in themes:
                        themes.append(label)
                s.add(Insight(review_id=review.id, model_key=model_key, themes=themes[:MAX_THEMES_PER_REVIEW]))
            run.review_count = run.tagged_count = len(seen)
            created.append(run.id)
            log.info("Imported %s (%d reviews)", store_id, len(seen))
    return created
