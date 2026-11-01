"""AI layer for benchmarks. The first app is "yours"; the others are competitors, markets or periods.

1. The model groups each app's themes into shared topics (validated against the real theme lists).
2. Code compares the apps per topic and journey stage and decides what is a lead, a lag or something to learn
   from, with the numbers and a few quotes from both sides.
3. The model explains each finding in words and cites from that finding's quotes only.
"""

from __future__ import annotations

import json
import string
from typing import Any

import pandas as pd

from ..analytics.benchmark import theme_inventory, topic_stats
from ..analytics.insights import review_dict
from ..models import Run
from ..providers import LLMProvider
from .artifacts import _ids, _strip_ids, _tidy

MAX_TOPICS = 12
MAX_POINTS = 4
MIN_MENTIONS = 3  # fewer reviews than this say nothing about a topic
GAP = 0.15  # difference in negative share that counts as a lead or lag
PRAISED = 0.3  # a topic with at most this negative share is something users like
LEARN_MIN = 5  # a lesson from a competitor needs at least this many of its reviews

TOPICS_SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "members": {
                        "type": "object",
                        "additionalProperties": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "required": ["name", "members"],
            },
        },
    },
    "required": ["topics"],
}
TOPICS_SYSTEM = """You line up app store review themes of several apps. Group the apps' themes into up to
{max_topics} shared topics that mean the same thing across apps (e.g. "login issues" in A and "can't sign in" in
B). name: short lowercase subject, no feelings ("login", "battery drain", "in-app purchases"). members: for each
app label, the exact theme names from that app's list that belong to the topic; omit apps without one. A topic
may belong to one app only."""

WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding": {"type": "string"},
                    "point": {"type": "string"},
                    "review_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["finding", "point", "review_ids"],
            },
        },
    },
    "required": ["headline", "points"],
}
WRITE_SYSTEM = """You write a competitive review comparison for a product team whose app is {yours}. The
comparisons were computed from the reviews: whether each finding is a lead, a lag or something to learn is
already decided, so never contradict it and never invent numbers. Call apps by name. Write in {language}.

headline: one sentence on how {yours} compares overall, using the overall comparisons.
points: one per finding. finding: its id. point: 1-2 plain sentences on what users actually say on each side
and what it means for {yours}'s design or product. review_ids: 1-2 ids copied from that finding's quotes."""


def _label(i: int) -> str:
    return string.ascii_uppercase[i]


def _stage_name(stage: str) -> str:
    return stage.replace("_", " ")


def _quotes(df: pd.DataFrame, mask: pd.Series, positive: bool, used: set[str], n: int = 2) -> list[dict]:
    g = df[mask & (df["rating"] >= 4 if positive else df["rating"] <= 2) & ~df["review_id"].isin(used)]
    g = g[g["content"].str.len() >= 20].sort_values("thumbs_up", ascending=False).head(n)
    return [review_dict(r, max_chars=220) for r in g.to_dict(orient="records")]


def _pct(share: float) -> str:
    return f"{share * 100:.0f}%"


def _compare(subject: str, stats: list[dict], names: list[str]) -> list[dict]:
    """Leads, lags and lessons for one subject. stats[i] = {"mentions", "share", "negative_share"} per app."""
    yours, others = stats[0], [(i, s) for i, s in enumerate(stats) if i and s["mentions"] >= MIN_MENTIONS]
    out = []
    if yours["mentions"] >= MIN_MENTIONS and others:
        best_i, best = min(others, key=lambda x: x[1]["negative_share"])
        worst_i, worst = max(others, key=lambda x: x[1]["negative_share"])
        if yours["negative_share"] - best["negative_share"] >= GAP:
            out.append(
                {
                    "kind": "lag",
                    "other": best_i,
                    "gap": yours["negative_share"] - best["negative_share"],
                    "evidence": f"{_pct(yours['negative_share'])} negative for {names[0]} vs "
                    f"{_pct(best['negative_share'])} for {names[best_i]}",
                }
            )
        elif worst["negative_share"] - yours["negative_share"] >= GAP and all(
            s["negative_share"] - yours["negative_share"] >= GAP for _, s in others
        ):
            out.append(
                {
                    "kind": "lead",
                    "other": worst_i,
                    "gap": min(s["negative_share"] for _, s in others) - yours["negative_share"],
                    "evidence": f"{_pct(yours['negative_share'])} negative for {names[0]} vs "
                    f"{_pct(worst['negative_share'])} for {names[worst_i]}",
                }
            )
    elif yours["mentions"] < MIN_MENTIONS:
        praised = [(i, s) for i, s in others if s["negative_share"] <= PRAISED and s["mentions"] >= LEARN_MIN]
        if praised:
            i, s = max(praised, key=lambda x: x[1]["share"])
            out.append(
                {
                    "kind": "learn",
                    "other": i,
                    "gap": s["share"] * (1 - s["negative_share"]) * 3,
                    "evidence": f"{s['mentions']} reviews of {names[i]}, {_pct(1 - s['negative_share'])} not "
                    f"negative; {names[0]} reviews barely mention it",
                }
            )
    if (
        yours["mentions"] >= MIN_MENTIONS
        and yours["negative_share"] >= 0.6
        and yours["share"] >= 0.05
        and not others
        and len(stats) > 1
    ):
        out.append(
            {
                "kind": "lag",
                "other": None,
                "gap": yours["negative_share"],
                "evidence": f"{yours['mentions']} reviews of {names[0]}, {_pct(yours['negative_share'])} negative; "
                "competitors' reviews rarely raise it",
            }
        )
    for f in out:
        f["subject"] = subject
        f["score"] = round(f["gap"] * (yours["share"] + (stats[f["other"]]["share"] if f["other"] else 0)), 6)
        if f["other"] is None:  # less certain than a head-to-head gap: other apps may word it differently
            f["score"] /= 2
    return out


def _words(subject: str) -> set[str]:
    return {w for w in subject.split() if len(w) >= 4 and w not in {"experience", "issues", "problems", "game"}}


def _same(a: dict, b: dict) -> bool:
    """Two findings about the same thing: mostly the same reviews, or a topic and a journey stage sharing a word."""
    if len(a["rows"] & b["rows"]) >= 0.5 * len(a["rows"] | b["rows"]):
        return True
    return a["scope"] != b["scope"] and bool(_words(a["subject"]) & _words(b["subject"]))


def find_gaps(names: list[str], frames: list[pd.DataFrame], topics: list[dict], summaries: list[dict]) -> list[dict]:
    """Every lead, lag and lesson worth mentioning, strongest first, with quotes from both sides."""
    findings = []
    for topic in topics:
        for f in _compare(topic["name"], topic["apps"], names):
            masks = [
                frames[i]["themes"].apply(lambda ts, w=set(a["themes"]): bool(w.intersection(ts)))
                for i, a in enumerate(topic["apps"])
            ]
            findings.append({**f, "scope": "topic", "masks": masks})
    stages = {s for summary in summaries for s in summary["journey"] if s != "other"}
    for stage in sorted(stages):
        stats = []
        for summary in summaries:
            j = summary["journey"].get(stage)
            stats.append(
                {"mentions": j["reviews"], "share": j["share"], "negative_share": j["negative_share"]}
                if j
                else {"mentions": 0, "share": 0.0, "negative_share": 0.0}
            )
        for f in _compare(_stage_name(stage), stats, names):
            if f["kind"] == "learn":  # "nobody talks about onboarding" isn't a lesson
                continue
            masks = [df["journey_stage"] == stage for df in frames]
            findings.append({**f, "scope": "journey stage", "masks": masks})

    findings.sort(key=lambda f: f["score"], reverse=True)
    picked: list[dict] = []
    seen: set[tuple[str, str]] = set()
    used: set[str] = set()  # each review is quoted once across the whole comparison
    for f in findings:
        key = (f["kind"], f["subject"])
        if key in seen or sum(1 for p in picked if p["kind"] == f["kind"]) >= MAX_POINTS:
            continue
        # A topic and a journey stage often describe the same reviews ("login" and "account login").
        f["rows"] = set(frames[0].loc[f["masks"][0], "review_id"]) or set(
            frames[f["other"]].loc[f["masks"][f["other"]], "review_id"]
        )
        if any(p["kind"] == f["kind"] and _same(f, p) for p in picked):
            continue
        seen.add(key)
        quotes = []
        if f["kind"] != "learn":
            quotes += [(0, q) for q in _quotes(frames[0], f["masks"][0], f["kind"] == "lead", used)]
        if f["other"] is not None:
            o = f["other"]
            quotes += [(o, q) for q in _quotes(frames[o], f["masks"][o], f["kind"] != "lead", used)]
        if not quotes:
            continue
        used.update(q["review_id"] for _, q in quotes)
        f["quotes"] = [{**q, "app": names[i]} for i, q in quotes]
        picked.append(f)
    for f in picked:
        del f["masks"], f["rows"]
    return picked


def _overall(names: list[str], summaries: list[dict]) -> list[str]:
    """Overall comparisons in words, with the better/worse label computed here."""
    lines = []
    metrics = (
        ("average rating", "avg_rating", True, 0.1, lambda v: f"{v:.2f}"),
        ("share of 1-2 star reviews", "negative_share", False, 0.03, _pct),
        ("share saying they're leaving", "churn_share", False, 0.02, _pct),
    )
    yours = summaries[0]
    for label, key, higher_better, tolerance, fmt in metrics:
        for i, other in enumerate(summaries[1:], start=1):
            a, b = yours.get(key), other.get(key)
            if a is None or b is None:
                continue
            if abs(a - b) < tolerance:
                verdict = "about the same"
            else:
                verdict = "better" if (a > b) == higher_better else "worse"
            lines.append(f"{label}: {names[0]} {fmt(a)} vs {names[i]} {fmt(b)}, {names[0]} is {verdict}")
    return lines


async def _align_topics(provider: LLMProvider, frames: list[pd.DataFrame]) -> list[dict]:
    inventories: list[set[str]] = []
    apps = []
    for i, df in enumerate(frames):
        themes = theme_inventory(df)
        inventories.append({t["theme"] for t in themes})
        apps.append({"label": _label(i), "themes": [{"theme": t["theme"], "mentions": t["mentions"]} for t in themes]})
    data, _usage = await provider.complete_json(
        system=TOPICS_SYSTEM.format(max_topics=MAX_TOPICS),
        prompt="THEMES:\n" + json.dumps({"apps": apps}, ensure_ascii=False),
        schema=TOPICS_SCHEMA,
        max_tokens=4000,
    )
    topics = []
    for topic in data.get("topics") or []:
        if not isinstance(topic, dict) or not topic.get("name"):
            continue
        members = topic.get("members") if isinstance(topic.get("members"), dict) else {}
        per_app = []
        for i, df in enumerate(frames):
            names = [str(n) for n in members.get(_label(i)) or [] if str(n) in inventories[i]]
            stats = topic_stats(df, names) if names else {"mentions": 0, "share": 0.0, "negative_share": None}
            per_app.append({"themes": names, **stats})
        if any(a["themes"] for a in per_app):
            topics.append({"name": " ".join(str(topic["name"]).lower().split())[:60], "apps": per_app})
    topics.sort(key=lambda t: sum(a["mentions"] for a in t["apps"]), reverse=True)
    return topics[:MAX_TOPICS]


async def generate(provider: LLMProvider, runs: list[Run], frames: list[pd.DataFrame], summaries: list[dict]) -> dict:
    names = [run.app.title or run.app.store_id for run in runs]
    if len(set(names)) < len(names):  # same app in several markets or periods
        names = [
            f"{n} ({(r.country or '?').upper()}, {r.created_at:%b %Y})" if names.count(n) > 1 else n
            for n, r in zip(names, runs, strict=True)
        ]
    topics = await _align_topics(provider, frames)
    for t in topics:  # the comparison needs a number, not None, for apps without the topic
        for a in t["apps"]:
            a["negative_share"] = a["negative_share"] if a["negative_share"] is not None else 0.0
    findings = find_gaps(names, frames, topics, summaries)
    for t in topics:
        for a in t["apps"]:
            if not a["mentions"]:
                a["negative_share"] = None

    citable = {q["review_id"]: q for f in findings for q in f["quotes"]}
    facts = {
        "overall": _overall(names, summaries),
        "findings": [
            {
                "finding": f"F{n}",
                "kind": {"lead": "where you lead", "lag": "where you lag", "learn": "learn from others"}[f["kind"]],
                f"{f['scope']}": f["subject"],
                "numbers": f["evidence"],
                "quotes": [
                    {"id": q["review_id"], "app": q["app"], "rating": q["rating"], "text": q["content"]}
                    for q in f["quotes"]
                ],
            }
            for n, f in enumerate(findings, start=1)
        ],
    }
    data, _usage = await provider.complete_json(
        system=WRITE_SYSTEM.format(yours=names[0], language=runs[0].output_language),
        prompt="FACTS:\n" + json.dumps(_tidy(facts), ensure_ascii=False, default=str),
        schema=WRITE_SCHEMA,
        max_tokens=6000,
    )
    written = {}
    for p in data.get("points") or []:
        if isinstance(p, dict) and p.get("finding"):
            written[str(p["finding"]).strip()] = p

    content: dict[str, Any] = {"headline": str(data.get("headline") or "").strip(), "topics": topics}
    for key in ("leads", "lags", "opportunities"):
        content[key] = []
    for n, f in enumerate(findings, start=1):
        own = {q["review_id"]: q for q in f["quotes"]}
        p = written.get(f"F{n}") or {}
        text, inline = _strip_ids(str(p.get("point") or ""), own)
        ids = (_ids(p.get("review_ids"), own) or inline or [f["quotes"][0]["review_id"]])[:1]
        # Show both sides: add the best quote from an app the first quote isn't from.
        other = next((q for q in f["quotes"] if q["app"] != own[ids[0]]["app"]), None)
        if other:
            ids.append(other["review_id"])
        key = {"lead": "leads", "lag": "lags", "learn": "opportunities"}[f["kind"]]
        content[key].append(
            {
                "subject": f["subject"],
                "scope": f["scope"],
                "point": text or f"{f['subject'].capitalize()}: {f['evidence']}.",
                "evidence": f["evidence"],
                "review_ids": ids[:2],
            }
        )
    cited = {i for key in ("leads", "lags", "opportunities") for p in content[key] for i in p["review_ids"]}
    content["reviews"] = {
        i: {
            k: citable[i].get(k)
            for k in ("review_id", "rating", "date", "content", "app_version", "thumbs_up", "themes", "app")
        }
        for i in cited
    }
    return content
