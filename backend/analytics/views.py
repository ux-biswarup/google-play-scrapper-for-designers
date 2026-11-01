"""Decision-oriented views over one analysis: feedback boards, journey map, emotions, segments and risks."""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher

import pandas as pd

from ..services.tagging import EMOTIONS, JOURNEY_STAGES
from .insights import _momentum, review_dict
from .metrics import auto_grain, bucket_dates

BOARD_TYPES = ("bug", "feature_request", "ux_friction", "complaint")
SEVERITY_WEIGHT = {"high": 1.0, "medium": 0.5, "low": 0.2, "none": 0.0}
EMOTION_MEANING = {
    "confusion": "Clarity problem: unclear screens, wording or flows. Usually fixed by design.",
    "frustration": "Friction or bugs that stop people finishing what they came to do.",
    "anger": "Broken trust: money, bans, data loss or policy. Needs product or policy decisions.",
    "disappointment": "Unmet expectations: a change people dislike or something missing.",
    "neutral": "Factual feedback without strong feeling.",
    "satisfaction": "Things working as expected.",
    "delight": "What people love. Protect it when changing the product.",
}
SEGMENT_DIMENSIONS = {
    "sentiment": ("Sentiment", ["negative", "neutral", "positive"], False),
    "user_type": ("User type", ["new_user", "long_time_user", "paying_user", "unknown"], True),
    "app_version": ("App version", None, False),
    "detail": ("Review detail", ["short", "medium", "detailed"], False),
    "upvotes": ("Helpful votes", ["none", "some", "many"], False),
    "replied": ("Developer reply", ["replied", "not_replied"], False),
}


def _quotes(
    g: pd.DataFrame, n: int = 2, worst_first: bool = True, chars: int = 300, used: set[str] | None = None
) -> list[dict]:
    """Representative quotes; skips reviews already quoted elsewhere in the same view when `used` is given."""
    pool = g[g["content"].str.len() >= 20]
    if pool.empty:
        pool = g
    if used is not None:
        # Never repeat a quote within a view; a theme whose reviews were all quoted above shows none.
        pool = pool[~pool["review_id"].isin(used)]
    ranked = pool.sort_values(["thumbs_up", "rating"], ascending=[False, worst_first])
    quotes = [review_dict(r, max_chars=chars) for r in ranked.head(n).to_dict(orient="records")]
    if used is not None:
        used.update(q["review_id"] for q in quotes)
    return quotes


def _midpoint(df: pd.DataFrame):
    dated = df["date"].dropna()
    return dated.min() + (dated.max() - dated.min()) / 2 if len(dated) else None


def _trend(g: pd.DataFrame, df: pd.DataFrame, mid) -> str:
    if mid is None:
        return "steady"
    recent_total, prior_total = int((df["date"] >= mid).sum()), int((df["date"] < mid).sum())
    _, _, trend = _momentum(int((g["date"] >= mid).sum()), recent_total, int((g["date"] < mid).sum()), prior_total)
    return trend


def _shares(series: pd.Series, order: list[str] | None = None, top: int | None = None) -> list[dict]:
    counts = series.dropna().value_counts()
    total = int(counts.sum())
    if not total:
        return []
    keys = [k for k in order if k in counts] if order else list(counts.index)
    rows = [{"value": str(k), "count": int(counts[k]), "share": round(int(counts[k]) / total, 4)} for k in keys]
    return rows[:top] if top else rows


def _theme_rows(g: pd.DataFrame) -> pd.DataFrame:
    exploded = g.assign(theme=g["themes"]).explode("theme")
    return exploded[exploded["theme"].notna()]


def _has_v2(df: pd.DataFrame) -> bool:
    return bool(df["severity"].notna().any())


# ---- Bugs, feature requests, UX friction, complaints ----------------------------------------


def feedback_boards(df: pd.DataFrame, limit: int = 12) -> dict:
    """What to fix (bugs), what to build (requests), what to redesign (friction), what to reconsider (complaints)."""
    tagged = df[df["category"].notna()]
    total = len(tagged)
    mid = _midpoint(df)
    boards = {}
    for category in BOARD_TYPES:
        g = tagged[tagged["category"] == category]
        items = []
        used: set[str] = set()
        for theme, t in _theme_rows(g).groupby("theme"):
            mentions = len(t)
            high = float((t["severity"] == "high").mean()) if t["severity"].notna().any() else None
            votes = int(t["thumbs_up"].sum())
            if category == "bug":
                score = mentions * (1 + (high or 0))
            elif category == "feature_request":
                score = mentions + votes / 10
            else:
                score = mentions * (1 + float((t["rating"] <= 2).mean()))
            items.append(
                {
                    "theme": theme,
                    "mentions": mentions,
                    "helpful_votes": votes,
                    "avg_rating": round(float(t["rating"].mean()), 2),
                    "high_severity_share": None if high is None else round(high, 4),
                    "trend": _trend(t, df, mid),
                    "versions": _shares(t["app_version"][t["app_version"] != "unknown"], top=3),
                    "first_seen": None if t["date"].isna().all() else t["date"].min().isoformat(),
                    "_rows": t,
                    "_score": score,
                }
            )
        items.sort(key=lambda i: i["_score"], reverse=True)
        items = items[:limit]
        for item in items:  # pick quotes in rank order so higher-ranked themes get first choice
            item.pop("_score")
            item["quotes"] = _quotes(item.pop("_rows"), 2, worst_first=category != "feature_request", used=used)
        boards[category] = {
            "count": len(g),
            "share": round(len(g) / total, 4) if total else 0,
            "trend": _trend(g, df, mid),
            "severity": _shares(g["severity"], ["high", "medium", "low", "none"]),
            "items": items,
        }
    return {"total_tagged": total, "has_severity": _has_v2(df), "boards": boards}


# ---- Journey map -----------------------------------------------------------------------------


def journey_map(df: pd.DataFrame) -> dict:
    """Each step of the user journey with volume, sentiment, emotions, top problems and a quote."""
    tagged = df[df["journey_stage"].notna()]
    total = len(tagged)
    stages = []
    for stage in JOURNEY_STAGES:
        g = tagged[tagged["journey_stage"] == stage]
        if g.empty:
            continue
        themes = _theme_rows(g)
        problems, praise = [], []
        for theme, t in themes.groupby("theme"):
            neg, pos = float((t["rating"] <= 2).mean()), float((t["rating"] >= 4).mean())
            row = {"theme": theme, "mentions": len(t), "negative_share": round(neg, 4)}
            if neg >= 0.4:
                problems.append(row)
            elif pos >= 0.6:
                praise.append(row)
        negative = g[g["rating"] <= 2]
        negative_share = len(negative) / len(g)
        stages.append(
            {
                "stage": stage,
                "reviews": len(g),
                "share": round(len(g) / total, 4),
                "avg_rating": round(float(g["rating"].mean()), 2),
                "negative_share": round(negative_share, 4),
                "pain": round(100 * (len(g) / total) * negative_share, 2),
                "emotions": _shares(g["emotion"], list(EMOTIONS)),
                "problems": sorted(problems, key=lambda r: r["mentions"], reverse=True)[:3],
                "praise": sorted(praise, key=lambda r: r["mentions"], reverse=True)[:2],
                "quote": (_quotes(negative if len(negative) else g, 1) or [None])[0],
            }
        )
    worst = max(stages, key=lambda s: s["pain"])["stage"] if stages else None
    return {"total_tagged": total, "worst_stage": worst, "stages": stages}


# ---- Emotions --------------------------------------------------------------------------------


def emotions_view(df: pd.DataFrame, top_themes: int = 12) -> dict:
    """Which feelings dominate, which themes trigger them, and how that changed over time."""
    tagged = df[df["emotion"].notna()]
    themes = _theme_rows(tagged)
    top = themes["theme"].value_counts().head(top_themes).index.tolist()
    matrix = [
        {
            "theme": theme,
            "counts": {e: int(((themes["theme"] == theme) & (themes["emotion"] == e)).sum()) for e in EMOTIONS},
        }
        for theme in top
    ]
    dated = tagged[tagged["date"].notna()]
    grain = auto_grain(dated["date"]) if len(dated) else "day"
    series = []
    if len(dated):
        buckets = bucket_dates(dated["date"], grain)
        for bucket, g in dated.groupby(buckets):
            counts = g["emotion"].value_counts()
            series.append(
                {
                    "date": bucket.strftime("%Y-%m-%d"),
                    "total": len(g),
                    **{e: round(int(counts.get(e, 0)) / len(g), 4) for e in EMOTIONS},
                }
            )
    return {
        "distribution": _shares(tagged["emotion"], list(EMOTIONS)),
        "matrix": matrix,
        "grain": grain,
        "series": series,
        "meaning": EMOTION_MEANING,
        "quotes": {e: _quotes(tagged[tagged["emotion"] == e], 2) for e in EMOTIONS if (tagged["emotion"] == e).any()},
    }


# ---- Segments --------------------------------------------------------------------------------


def segments_view(df: pd.DataFrame, by: str = "sentiment") -> dict:
    """Compare groups of reviewers: what each group talks about, and what's distinctive for it."""
    if by not in SEGMENT_DIMENSIONS:
        raise ValueError(f"Segment by one of: {', '.join(SEGMENT_DIMENSIONS)}.")
    label, order, needs_v2 = SEGMENT_DIMENSIONS[by]
    available = [
        {"id": k, "label": v[0], "needs_reanalysis": v[2] and not _has_v2(df)} for k, v in SEGMENT_DIMENSIONS.items()
    ]
    data = df[df[by].notna()].copy()
    if by == "app_version":
        top = data[data["app_version"] != "unknown"]["app_version"].value_counts().head(6).index.tolist()
        data["app_version"] = data["app_version"].where(data["app_version"].isin(top), "other")
        order = top + ["other"]
    total = len(data)
    overall = Counter(t for themes in data["themes"] for t in themes)
    segments = []
    for value in order or sorted(data[by].unique()):
        g = data[data[by] == value]
        if g.empty:
            continue
        counts = Counter(t for themes in g["themes"] for t in themes)
        distinctive = []
        for theme, n in counts.items():
            if n < 2 or not overall[theme]:
                continue
            lift = (n / len(g)) / (overall[theme] / total)
            if lift >= 1.3:
                distinctive.append({"theme": theme, "mentions": n, "lift": round(lift, 2)})
        segments.append(
            {
                "value": value,
                "reviews": len(g),
                "share": round(len(g) / total, 4) if total else 0,
                "avg_rating": round(float(g["rating"].mean()), 2),
                "negative_share": round(float((g["rating"] <= 2).mean()), 4),
                "feedback_types": _shares(g["category"], top=4),
                "top_themes": [
                    {"theme": t, "mentions": n, "share": round(n / len(g), 4)} for t, n in counts.most_common(5)
                ],
                "distinctive_themes": sorted(distinctive, key=lambda d: d["lift"], reverse=True)[:3],
                "quote": (_quotes(g, 1) or [None])[0],
            }
        )
    return {
        "by": by,
        "label": label,
        "available": available,
        "needs_reanalysis": needs_v2 and not _has_v2(df),
        "segments": segments,
    }


# ---- Risks -----------------------------------------------------------------------------------


def risks_view(df: pd.DataFrame) -> dict:
    """Early warnings for a PM: people leaving, competitors named, and money problems."""
    tagged = df[df["tagged"]]
    total = len(tagged)
    mid = _midpoint(df)
    churn = tagged[tagged["churn_risk"].isin(["left", "considering"])]
    churn_themes = Counter(t for themes in churn["themes"] for t in themes)

    competitors = []
    named = tagged.assign(competitor=tagged["competitors"]).explode("competitor")
    named = named[named["competitor"].notna() & (named["competitor"] != "")]
    for name, g in named.groupby(named["competitor"].str.strip().str.title()):
        competitors.append(
            {
                "name": name,
                "mentions": len(g),
                "avg_rating": round(float(g["rating"].mean()), 2),
                "switching": int(g["churn_risk"].isin(["left", "considering"]).sum()),
                "quote": (_quotes(g, 1) or [None])[0],
            }
        )
    payments = tagged[(tagged["journey_stage"] == "payments_subscription") & (tagged["rating"] <= 2)]
    payment_themes = Counter(t for themes in payments["themes"] for t in themes)
    return {
        "available": _has_v2(df),
        "total_tagged": total,
        "churn": {
            "left": int((churn["churn_risk"] == "left").sum()),
            "considering": int((churn["churn_risk"] == "considering").sum()),
            "share": round(len(churn) / total, 4) if total else 0,
            "trend": _trend(churn, df, mid),
            "themes": [{"theme": t, "mentions": n} for t, n in churn_themes.most_common(6)],
            "by_user_type": _shares(churn["user_type"]),
            "quotes": _quotes(churn, 3),
        },
        "competitors": sorted(competitors, key=lambda c: c["mentions"], reverse=True)[:10],
        "payments": {
            "count": len(payments),
            "share": round(len(payments) / total, 4) if total else 0,
            "themes": [{"theme": t, "mentions": n} for t, n in payment_themes.most_common(5)],
            "quotes": _quotes(payments, 2),
        },
    }


# ---- Accessibility ---------------------------------------------------------------------------

# Accessibility needs, matched by keywords inside reviews the AI flagged as accessibility feedback.
# Each has what to check in the design, with the matching WCAG success criterion.
ACCESSIBILITY_AREAS: dict[str, tuple[tuple[str, ...], str]] = {
    "Text size and zoom": (
        ("font", "text size", "small text", "tiny text", "zoom", "magnif", "large text", "bigger text", "too small"),
        "Support the system text size up to 200% without clipped or overlapping text (WCAG 1.4.4).",
    ),
    "Contrast and colour": (
        ("contrast", "colour blind", "color blind", "colorblind", "colour", "color", "dark mode", "too bright"),
        "Text contrast of at least 4.5:1, and never use colour alone to carry meaning (WCAG 1.4.3, 1.4.1).",
    ),
    "Screen readers": (
        ("talkback", "screen reader", "screenreader", "voiceover", "blind", "visually impaired", "label"),
        "Every control has a spoken name and role, in a sensible reading order (WCAG 4.1.2, 1.3.2).",
    ),
    "Motion and flashing": (
        ("flash", "flicker", "seizure", "epilep", "motion sick", "animation", "dizzy", "vertigo"),
        "Nothing flashes more than 3 times a second; respect the system's reduce-motion setting (WCAG 2.3.1).",
    ),
    "Touch and dexterity": (
        ("tap", "button", "tremor", "arthritis", "one hand", "one-hand", "dexterity", "swipe", "gesture"),
        "Touch targets of at least 24×24 px (48 dp on Android) and a simple alternative to gestures "
        "(WCAG 2.5.8, 2.5.1).",
    ),
    "Hearing and captions": (
        ("caption", "subtitle", "deaf", "hearing", "hard of hearing", "audio cue", "sound only"),
        "Captions for speech and a visual alternative to sound cues (WCAG 1.2.2).",
    ),
    "Cognitive load": (
        ("confus", "overwhelm", "dyslex", "adhd", "autis", "memory", "complicated", "too many steps"),
        "Plain language, predictable navigation and no time pressure without a way to extend it (WCAG 3.2.3, 2.2.1).",
    ),
    "Mobility and physical activity": (
        ("wheelchair", "disab", "mobility", "can't walk", "cannot walk", "walking", "elderly", "senior", "chronic"),
        "Core features shouldn't require walking, standing or travel; offer an alternative way to take part.",
    ),
}


def accessibility_view(df: pd.DataFrame) -> dict:
    """Reviews about accessibility, grouped into needs with what to check in the design."""
    tagged = df[df["tagged"]]
    total = len(tagged)
    a11y = tagged[tagged["accessibility"] == "yes"]
    text = a11y["content"].fillna("").str.lower()
    used: set[str] = set()
    areas = []
    matched = pd.Series(False, index=a11y.index)
    for area, (keywords, check) in ACCESSIBILITY_AREAS.items():
        hit = text.apply(lambda t, kw=keywords: any(k in t for k in kw))
        matched |= hit
        g = a11y[hit]
        if len(g):
            areas.append(
                {
                    "area": area,
                    "count": len(g),
                    "negative_share": round(float((g["rating"] <= 2).mean()), 4),
                    "check": check,
                    "quotes": _quotes(g, 1, used=used),
                }
            )
    areas.sort(key=lambda a: a["count"], reverse=True)
    themes = Counter(t for ts in a11y["themes"] for t in ts)
    return {
        "available": bool(tagged["accessibility"].notna().any()),
        "total_tagged": total,
        "count": len(a11y),
        "share": round(len(a11y) / total, 4) if total else 0,
        "avg_rating": round(float(a11y["rating"].mean()), 2) if len(a11y) else None,
        "overall_avg_rating": round(float(tagged["rating"].mean()), 2) if total else None,
        "negative_share": round(float((a11y["rating"] <= 2).mean()), 4) if len(a11y) else None,
        "trend": _trend(a11y, df, _midpoint(df)),
        "areas": areas,
        "unmatched": int((~matched).sum()),
        "themes": [{"theme": t, "mentions": n} for t, n in themes.most_common(6)],
        "stages": _shares(a11y["journey_stage"], list(JOURNEY_STAGES)),
        "quotes": _quotes(a11y, 4, used=used),
    }


# ---- Developer replies -----------------------------------------------------------------------

PLAY_REPLY_LIMIT = 350  # characters Google Play allows in a developer reply


def _normalize_reply(text: str) -> str:
    return " ".join("".join(c for c in text.lower() if c.isalpha() or c.isspace()).split())


def _reply_templates(replies: list[str], similarity: float = 0.85) -> list[list[str]]:
    """Group replies that are the same text give or take a few words (typos, names, links)."""
    groups: list[tuple[str, list[str]]] = []
    for reply in replies:
        norm = _normalize_reply(reply)
        for key, members in groups:
            if SequenceMatcher(None, key, norm, autojunk=False).ratio() >= similarity:
                members.append(reply)
                break
        else:
            groups.append((norm, [reply]))
    return [members for _, members in groups]


def replies_view(df: pd.DataFrame) -> dict:
    """How the team answers reviews: reply rates, templated replies, and which complaints go unanswered."""
    total = len(df)
    has_reply = df["reply"].fillna("").str.strip() != ""
    replied = df[has_reply]
    negative = df["rating"] <= 2
    unanswered_neg = df[negative & ~has_reply]

    by_rating = []
    for star in range(1, 6):
        g = df[df["rating"] == star]
        if len(g):
            by_rating.append(
                {"rating": star, "reviews": len(g), "reply_rate": round(float(has_reply[g.index].mean()), 4)}
            )

    groups = _reply_templates(replied["reply"].tolist())
    templated = sum(len(g) for g in groups if len(g) >= 2)
    templates = [
        {"text": " ".join(str(g[0]).split())[:400], "uses": len(g)}
        for g in sorted(groups, key=len, reverse=True)
        if len(g) >= 2
    ][:3]

    themes = Counter(t for ts in unanswered_neg["themes"] for t in ts)
    votes = Counter()
    for ts, up in zip(unanswered_neg["themes"], unanswered_neg["thumbs_up"], strict=True):
        for t in ts:
            votes[t] += int(up)
    first = unanswered_neg[unanswered_neg["content"].str.len() >= 20].sort_values("thumbs_up", ascending=False)
    reply_first = [review_dict(r, max_chars=400) for r in first.head(5).to_dict(orient="records")]
    examples = replied[replied["rating"] <= 3].sort_values("thumbs_up", ascending=False)
    return {
        "total": total,
        "replied": len(replied),
        "reply_rate": round(len(replied) / total, 4) if total else 0,
        "negative": int(negative.sum()),
        "negative_reply_rate": round(float(has_reply[negative].mean()), 4) if negative.any() else None,
        "avg_rating_replied": round(float(replied["rating"].mean()), 2) if len(replied) else None,
        "avg_rating_not_replied": round(float(df[~has_reply]["rating"].mean()), 2) if (~has_reply).any() else None,
        "by_rating": by_rating,
        "templated_share": round(templated / len(replied), 4) if len(replied) else None,
        "templates": templates,
        "avg_reply_chars": int(replied["reply"].str.len().mean()) if len(replied) else None,
        "unanswered_themes": [{"theme": t, "reviews": n, "helpful_votes": votes[t]} for t, n in themes.most_common(8)],
        "reply_first": reply_first,
        "examples": [review_dict(r, max_chars=400) for r in examples.head(3).to_dict(orient="records")],
    }
