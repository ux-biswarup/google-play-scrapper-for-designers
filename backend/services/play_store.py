"""Google Play access: app lookup, search, and review fetching."""

from __future__ import annotations

import re
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import certifi
from google_play_scraper import Sort
from google_play_scraper import app as gp_app
from google_play_scraper import reviews as gp_reviews
from google_play_scraper import search as gp_search
from google_play_scraper.constants.element import ElementSpec, ElementSpecs
from google_play_scraper.exceptions import NotFoundError

# google-play-scraper turns off TLS certificate verification for the whole process on import.
# Turn it back on, using certifi's CA bundle so it also works on Python builds without system certs.
_CA_FILE = certifi.where()


def _verified_https_context(*args, **kwargs) -> ssl.SSLContext:
    if not any(k in kwargs for k in ("cafile", "capath", "cadata")):
        kwargs["cafile"] = _CA_FILE
    return ssl.create_default_context(*args, **kwargs)


ssl._create_default_https_context = _verified_https_context

# google-play-scraper 1.2.7 reads the top search result's app ID (the app the user most likely wants,
# e.g. "com.duolingo" for "duolingo") from a position Google no longer fills. Read it from the
# store link instead, keeping the old position as a fallback.
_old_top_id = ElementSpecs.SearchResultOnTop["appId"]


def _id_from_store_link(url):
    return (parse_qs(urlparse(url).query).get("id") or [None])[0] if isinstance(url, str) else None


ElementSpecs.SearchResultOnTop["appId"] = ElementSpec(
    None, [2, 41, 0, 2], _id_from_store_link, fallback_value=_old_top_id
)

PAGE_SIZE = 200
_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")


class AppNotFound(Exception):
    pass


def parse_store_id(value: str) -> str:
    """Accept a package name (com.example.app) or a Play Store URL and return the package name."""
    value = (value or "").strip()
    if value.startswith(("http://", "https://", "play.google.com")):
        parsed = urlparse(value if "://" in value else f"https://{value}")
        value = (parse_qs(parsed.query).get("id") or [""])[0]
    if not _PACKAGE_RE.match(value):
        raise ValueError("Enter a Play Store app ID like com.example.app or a Play Store link.")
    return value


@dataclass
class AppDetails:
    store_id: str
    title: str | None
    developer: str | None
    icon_url: str | None
    genre: str | None
    score: float | None
    ratings_count: int | None
    installs: str | None
    version: str | None
    store_url: str | None
    summary: str | None = None


@dataclass
class AppSearchHit:
    store_id: str
    title: str | None
    developer: str | None
    icon_url: str | None
    score: float | None


@dataclass
class StoreReview:
    review_id: str
    rating: int
    content: str
    reviewed_at: datetime | None
    app_version: str | None
    thumbs_up: int
    reply_content: str | None


ProgressFn = Callable[[int, int], None]

MAX_SCAN = 10_000  # reviews to page through when looking for a date range


@dataclass
class ReviewWindow:
    """Reviews found in a date range by paging newest-first through Google Play."""

    reviews: list[StoreReview]  # newest first, inside the range
    scanned: int
    complete: bool  # reached reviews older than the range start for every rating filter
    oldest_reached: datetime | None
    created: float = field(default_factory=time.time)


def pick_reviews(reviews: list[StoreReview], count: int, sampling: str) -> list[StoreReview]:
    """Choose `count` reviews: the newest, or spread evenly across the period so trends cover all of it."""
    if count >= len(reviews):
        return list(reviews)
    if sampling != "spread":
        return reviews[:count]
    oldest_first = sorted(reviews, key=lambda r: r.reviewed_at or datetime.min)
    if count == 1:
        return [oldest_first[-1]]
    step = (len(oldest_first) - 1) / (count - 1)
    picked = [oldest_first[round(i * step)] for i in range(count)]
    return sorted(picked, key=lambda r: r.reviewed_at or datetime.min, reverse=True)


class WindowCache:
    """Keeps recent date-range scans so starting an analysis right after counting doesn't scan again."""

    def __init__(self, ttl: float = 900):
        self.ttl = ttl
        self._items: dict[tuple, ReviewWindow] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple) -> ReviewWindow | None:
        with self._lock:
            hit = self._items.get(key)
            return hit if hit and time.time() - hit.created < self.ttl else None

    def put(self, key: tuple, window: ReviewWindow) -> None:
        with self._lock:
            self._items = {k: v for k, v in self._items.items() if time.time() - v.created < self.ttl}
            self._items[key] = window


def _clean_version(value) -> str | None:
    if not value or isinstance(value, (list, dict)):
        return None
    return str(value).strip() or None


class PlayStoreClient:
    """Thin, synchronous wrapper. Call from a worker thread in async code."""

    platform = "android"

    def app_details(self, store_id: str, *, lang: str, country: str) -> AppDetails:
        try:
            info = gp_app(store_id, lang=lang, country=country)
        except NotFoundError as exc:
            raise AppNotFound(f"No Play Store app found with ID '{store_id}' in {country.upper()}.") from exc
        return AppDetails(
            store_id=store_id,
            title=info.get("title"),
            developer=info.get("developer"),
            icon_url=info.get("icon"),
            genre=info.get("genre"),
            score=info.get("score"),
            ratings_count=info.get("ratings"),
            installs=info.get("installs"),
            version=_clean_version(info.get("version")),
            store_url=info.get("url"),
            summary=info.get("summary"),
        )

    def search(self, query: str, *, lang: str, country: str, limit: int = 10) -> list[AppSearchHit]:
        hits = gp_search(query, n_hits=limit, lang=lang, country=country)
        return [
            AppSearchHit(h["appId"], h.get("title"), h.get("developer"), h.get("icon"), h.get("score"))
            for h in hits
            if h.get("appId")
        ]

    def fetch_reviews(
        self,
        store_id: str,
        *,
        lang: str,
        country: str,
        count: int,
        ratings: list[int] | None = None,
        on_progress: ProgressFn | None = None,
    ) -> list[StoreReview]:
        """Newest `count` reviews, optionally limited to some star ratings (fetched server-side per rating)."""
        filters: list[int | None] = sorted(set(ratings)) if ratings else [None]
        collected: dict[str, StoreReview] = {}
        target = count * len(filters)
        fetched = 0
        for score in filters:
            token = None
            got = 0
            while got < count:
                batch, token = gp_reviews(
                    store_id,
                    lang=lang,
                    country=country,
                    sort=Sort.NEWEST,
                    count=min(PAGE_SIZE, count - got),
                    filter_score_with=score,
                    continuation_token=token,
                )
                for raw in batch:
                    review = self._to_review(raw)
                    if review:
                        collected[review.review_id] = review
                got += len(batch)
                fetched += len(batch)
                if on_progress:
                    on_progress(min(fetched, target), target)
                if not batch or token is None or token.token is None:
                    break
        newest_first = sorted(collected.values(), key=lambda r: r.reviewed_at or datetime.min, reverse=True)
        return newest_first[:count]

    def scan_window(
        self,
        store_id: str,
        *,
        lang: str,
        country: str,
        date_from: date | None,
        date_to: date | None,
        ratings: list[int] | None = None,
        max_scan: int = MAX_SCAN,
        on_progress: ProgressFn | None = None,
    ) -> ReviewWindow:
        """All reviews written between date_from and date_to (inclusive days), within a scanning budget.

        Google Play has no date filter, so this pages newest-first: it skips reviews newer than the range and
        stops at the first review older than it.
        """
        start = datetime.combine(date_from, datetime.min.time()) if date_from else None
        end = datetime.combine(date_to, datetime.min.time()) + timedelta(days=1) if date_to else None
        filters: list[int | None] = sorted(set(ratings)) if ratings else [None]
        budget = max(PAGE_SIZE, max_scan // len(filters))
        found: dict[str, StoreReview] = {}
        scanned, complete, oldest = 0, True, None
        for score in filters:
            token, seen, reached = None, 0, False
            while seen < budget and not reached:
                batch, token = gp_reviews(
                    store_id,
                    lang=lang,
                    country=country,
                    sort=Sort.NEWEST,
                    count=PAGE_SIZE,
                    filter_score_with=score,
                    continuation_token=token,
                )
                for raw in batch:
                    review = self._to_review(raw)
                    if not review or review.reviewed_at is None:
                        continue
                    oldest = review.reviewed_at if oldest is None else min(oldest, review.reviewed_at)
                    if start and review.reviewed_at < start:
                        reached = True
                        break
                    if end is None or review.reviewed_at < end:
                        found[review.review_id] = review
                seen += len(batch)
                scanned += len(batch)
                if on_progress:
                    on_progress(min(scanned, max_scan), max_scan)
                if not batch or token is None or token.token is None:
                    reached = True  # no older reviews exist
            complete = complete and reached
        reviews = sorted(found.values(), key=lambda r: r.reviewed_at or datetime.min, reverse=True)
        return ReviewWindow(reviews=reviews, scanned=scanned, complete=complete, oldest_reached=oldest)

    @staticmethod
    def _to_review(raw: dict) -> StoreReview | None:
        review_id = raw.get("reviewId")
        score = raw.get("score")
        if not review_id or not score:
            return None
        return StoreReview(
            review_id=str(review_id),
            rating=int(score),
            content=(raw.get("content") or "").strip(),
            reviewed_at=raw.get("at"),
            app_version=_clean_version(raw.get("reviewCreatedVersion") or raw.get("appVersion")),
            thumbs_up=int(raw.get("thumbsUpCount") or 0),
            reply_content=raw.get("replyContent"),
        )
