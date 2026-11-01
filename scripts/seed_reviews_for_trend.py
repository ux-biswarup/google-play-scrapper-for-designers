"""One-off: fetch reviews (no Claude), build enriched_reviews, save _reviews.json for Trend tab."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_review_analyzer import _sentiment_from_rating
from google_play_scraper import reviews, Sort

APP_ID = "com.nianticlabs.pokemongo"
COUNT = 150


def main():
    r, _ = reviews(APP_ID, lang="en", country="us", count=COUNT, sort=Sort.NEWEST)
    enriched = []
    for rev in r:
        at = rev.get("at")
        date_str = at.isoformat() if hasattr(at, "isoformat") else str(at) if at else ""
        ver = rev.get("reviewCreatedVersion") or rev.get("appVersion") or "unknown"
        if isinstance(ver, (list, dict)):
            ver = "unknown"
        ver = str(ver).strip() or "unknown"
        enriched.append({
            "review_id": rev.get("reviewId") or "",
            "date": date_str,
            "rating": int(rev.get("score", 0)),
            "content": (rev.get("content") or "") or "",
            "sentiment": _sentiment_from_rating(int(rev.get("score", 3))),
            "app_version": ver,
            "topics": [],
            "issues": [],
            "praises": [],
        })
    os.makedirs("reports", exist_ok=True)
    path = f"reports/{APP_ID}_reviews.json"
    with open(path, "w") as f:
        json.dump(enriched, f, indent=2)
    print(f"Wrote {path} with {len(enriched)} reviews")


if __name__ == "__main__":
    main()
