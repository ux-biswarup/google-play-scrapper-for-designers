"""Starter questions for the assistant, written from what this analysis actually found.

Each suggestion has a short tag saying why it's there (Top problem, Rising, Churn risk...). Everything is computed
from the tagged reviews, so suggestions are instant, free and always about things the data can answer.
"""

from __future__ import annotations

import re

import pandas as pd

from ..analytics import views
from ..analytics.insights import problem_board

MAX_SUGGESTIONS = 5
MIN_REVIEWS = 3  # don't suggest a question the analysis has too little evidence for

STAGE_NAMES = {
    "install_onboarding": "onboarding",
    "account_login": "signing in",
    "core_experience": "the core experience",
    "search_navigation": "finding their way around",
    "payments_subscription": "payments and subscriptions",
    "notifications": "notifications",
    "settings_privacy": "settings and privacy",
    "support_help": "getting support",
    "app_updates": "app updates",
}

FALLBACK = [
    ("What do users love that we should protect?", "Strength"),
    ("Write How Might We questions for the top problem.", "Ideation"),
    ("Draft a short stakeholder update from this analysis.", "Summary"),
]


def _version_key(version: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.\-]", version))


def _latest_release(df: pd.DataFrame) -> str | None:
    """The newest app version with enough reviews to compare against earlier ones."""
    counts = df["app_version"][df["app_version"].fillna("unknown") != "unknown"].value_counts()
    versions = sorted((v for v, n in counts.items() if n >= MIN_REVIEWS), key=_version_key)
    return versions[-1] if len(versions) >= 2 else None


def suggest(df: pd.DataFrame | None) -> list[dict]:
    """Up to five {"text", "tag"} questions, most useful first. Each theme appears at most once."""
    if df is None or df.empty or not df["tagged"].any():
        return [{"text": t, "tag": tag} for t, tag in FALLBACK]

    out: list[dict] = []
    used: set[str] = set()

    def add(text: str, tag: str, theme: str | None = None) -> None:
        if len(out) < MAX_SUGGESTIONS and (theme is None or theme not in used):
            out.append({"text": text, "tag": tag})
            if theme:
                used.add(theme)

    board = problem_board(df, limit=10, quotes=0)
    problems = [p for p in board["problems"] if p["mentions"] >= MIN_REVIEWS]
    if problems:
        top = problems[0]
        add(f"Why are users unhappy about {top['theme']}?", "Top problem", top["theme"])
    rising = next((p for p in problems if p["trend"] == "rising" and p["theme"] not in used), None)
    if rising:
        add(f"What's behind the recent rise in {rising['theme']} complaints?", "Rising", rising["theme"])

    risks = views.risks_view(df)
    leaving = risks["churn"]["left"] + risks["churn"]["considering"]
    if leaving >= MIN_REVIEWS:
        add(f"Why do {leaving} reviewers say they're leaving, and what would keep them?", "Churn risk")

    journey = views.journey_map(df)
    worst = journey.get("worst_stage")
    stage = next((s for s in journey["stages"] if s["stage"] == worst), None)
    if stage and stage["reviews"] >= MIN_REVIEWS and stage["negative_share"] >= 0.4 and worst in STAGE_NAMES:
        add(f"Where do users get stuck with {STAGE_NAMES[worst]}?", "Journey")

    competitor = next((c for c in risks["competitors"] if c["mentions"] >= 2), None)
    if competitor:
        add(f"What do users say {competitor['name']} does better?", "Competitor")

    release = _latest_release(df)
    if release:
        add(f"Did version {release} make things better or worse?", "Release")

    requests = views.feedback_boards(df, limit=3)["boards"]["feature_request"]["items"]
    request = next((r for r in requests if r["theme"] not in used and r["mentions"] >= 2), None)
    if request:
        add(f"What are users asking for around {request['theme']}?", "Request", request["theme"])

    if risks["payments"]["count"] >= MIN_REVIEWS:
        add("What frustrates paying users about payments and subscriptions?", "Money")

    strength = next((s for s in board["strengths"] if s["mentions"] >= MIN_REVIEWS and s["theme"] not in used), None)
    if strength:
        add(f"What do users love about {strength['theme']}, and how do we protect it?", "Strength", strength["theme"])

    if views.accessibility_view(df)["count"] >= 2:
        add("What accessibility barriers do users run into?", "Accessibility")

    for text, tag in FALLBACK:
        if not any(s["tag"] == tag for s in out):
            add(text, tag)
    return out
