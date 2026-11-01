"""AI-written decision artifacts: decisions, research report, what changed, personas.

Each artifact is generated from a fact sheet computed from the analysis (numbers, themes, quotes with
review IDs). The model may only cite review IDs from that sheet; anything else is dropped. Priority
(now / next / later) is computed here from the model's impact, confidence and effort ratings.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pandas as pd

from ..analytics import trends
from ..analytics.insights import overview, problem_board
from ..analytics.views import feedback_boards, journey_map, risks_view, segments_view
from ..models import Run
from ..providers import LLMProvider

KINDS = ("decisions", "report", "what_changed", "personas")
LEVEL = {"high": 3, "medium": 2, "low": 1}
STATUSES = ("todo", "planned", "in_progress", "done", "dismissed")

PREAMBLE = """You advise the product designer and product manager of {app}. You get a fact sheet computed from
{reviews} Google Play reviews. Use only these facts. Never invent numbers, themes or quotes. Cite the reviews
that support each point by copying their ids exactly (from the "id" fields) into review_ids: every finding,
opportunity, decision and change needs 1-3 of them. Be specific and practical:
name the screen, flow or policy involved when the reviews make it clear. Write in {language}."""


# ---- fact sheet --------------------------------------------------------------------------------


class FactSheet:
    """Facts for the model plus the reviews it is allowed to cite."""

    def __init__(self, df: pd.DataFrame, run: Run):
        self.df, self.run = df, run
        self.citable: dict[str, dict] = {}

    def cite(self, reviews: list[dict], chars: int = 220) -> list[dict]:
        out = []
        for r in reviews or []:
            if not r:
                continue
            self.citable[r["review_id"]] = r
            text = r["content"] if len(r["content"]) <= chars else r["content"][:chars].rstrip() + "…"
            out.append({"id": r["review_id"], "rating": r["rating"], "text": text})
        return out

    def basics(self) -> dict:
        k = overview(self.df)["kpis"]
        run = self.run
        return {
            "app": run.app.title or run.app.store_id,
            "market": (run.country or "unknown").upper(),
            "star_filter": run.ratings or "all ratings",
            "reviews": k["review_count"],
            "average_rating": k["avg_rating"],
            "negative_share": k["negative_share"],
            "positive_share": k["positive_share"],
            "period": [(k["date_from"] or "")[:10], (k["date_to"] or "")[:10]],
        }

    def problems(self, limit: int = 10, quotes: int = 2) -> dict:
        board = problem_board(self.df, limit=limit, quotes=quotes)

        def compact(t: dict, n: int) -> dict:
            return {
                "theme": t["theme"],
                "mentions": t["mentions"],
                "share_of_reviews": t["reach"],
                "negative_share": t["negative_share"],
                "trend": t["trend"],
                "impact_score": t["impact"],
                "type": t["categories"][0]["value"] if t["categories"] else None,
                "journey_stage": t["journey_stages"][0]["value"] if t["journey_stages"] else None,
                "emotion": t["emotions"][0]["value"] if t["emotions"] else None,
                "quotes": self.cite(t["quotes"][:n]),
            }

        return {
            "problems": [compact(t, quotes) for t in board["problems"]],
            "strengths": [compact(t, 1) for t in board["strengths"][:5]],
        }

    def feedback(self, limit: int = 5) -> dict:
        boards = feedback_boards(self.df, limit=limit)["boards"]
        return {
            kind: [
                {
                    "theme": i["theme"],
                    "mentions": i["mentions"],
                    "helpful_votes": i["helpful_votes"],
                    "high_severity_share": i["high_severity_share"],
                    "trend": i["trend"],
                    "quotes": self.cite(i["quotes"][:1]),
                }
                for i in board["items"]
            ]
            for kind, board in boards.items()
        }

    def journey(self) -> dict:
        data = journey_map(self.df)
        return {
            "most_painful_stage": data["worst_stage"],
            "stages": [
                {
                    "stage": s["stage"],
                    "reviews": s["reviews"],
                    "avg_rating": s["avg_rating"],
                    "negative_share": s["negative_share"],
                    "problems": [p["theme"] for p in s["problems"]],
                    "works_well": [p["theme"] for p in s["praise"]],
                }
                for s in data["stages"]
            ],
        }

    def risks(self) -> dict | None:
        data = risks_view(self.df)
        if not data["available"]:
            return None
        return {
            "said_they_left": data["churn"]["left"],
            "may_leave": data["churn"]["considering"],
            "reasons": data["churn"]["themes"],
            "who": data["churn"]["by_user_type"],
            "quotes": self.cite(data["churn"]["quotes"][:2]),
            "competitors_named": [{"name": c["name"], "mentions": c["mentions"]} for c in data["competitors"]],
            "payment_problems": data["payments"]["count"],
        }

    def user_types(self) -> list[dict] | None:
        data = segments_view(self.df, "user_type")
        if data["needs_reanalysis"]:
            return None
        return [
            {
                "user_type": s["value"],
                "reviews": s["reviews"],
                "avg_rating": s["avg_rating"],
                "negative_share": s["negative_share"],
                "talk_about_more": [d["theme"] for d in s["distinctive_themes"]],
                "top_themes": [t["theme"] for t in s["top_themes"][:4]],
            }
            for s in data["segments"]
        ]

    def change(self) -> dict:
        """Before/after comparison: the latest app version if there are several, otherwise the newer half."""
        versions = [v for v in trends.versions(self.df) if v["app_version"] != "unknown" and v["review_count"] >= 3]
        if len(versions) >= 2:
            pivot, mode = versions[-1]["app_version"], "version"
        else:
            dated = self.df["date"].dropna()
            if dated.empty:
                return {"comparison": None}
            pivot, mode = (dated.min() + (dated.max() - dated.min()) / 2).strftime("%Y-%m-%d"), "date"
        cmp = trends.compare(self.df, mode, pivot)
        shift = ("theme", "before_share", "after_share", "after_count")
        return {
            "comparison": {
                "compared": f"app version {pivot} vs earlier"
                if mode == "version"
                else f"reviews from {pivot} vs earlier",
                "before": {k: cmp["before"][k] for k in ("review_count", "avg_rating", "negative_share")},
                "after": {k: cmp["after"][k] for k in ("review_count", "avg_rating", "negative_share")},
                "new_themes": [{k: s[k] for k in shift} for s in cmp["new_themes"][:6]],
                "rising_themes": [{k: s[k] for k in shift} for s in cmp["rising_themes"][:6]],
                "falling_themes": [{k: s[k] for k in shift} for s in cmp["falling_themes"][:6]],
            },
            "one_star_spikes": trends.spikes(self.df, "day")["spikes"][:5],
            "trending_this_week": trends.trending_themes(self.df, limit=8),
        }

    def detailed_reviews(self, n: int = 25) -> list[dict]:
        from ..analytics.insights import review_dict

        pool = self.df[self.df["content"].str.len() >= 120].sort_values("thumbs_up", ascending=False).head(n)
        return self.cite([review_dict(r) for r in pool.to_dict(orient="records")], chars=400)


# ---- schemas -------------------------------------------------------------------------------------

_IDS = {"type": "array", "items": {"type": "string"}}
_LEVEL = {"type": "string", "enum": ["high", "medium", "low"]}

DECISIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "lens": {"type": "string", "enum": ["design", "product"]},
                    "action": {
                        "type": "string",
                        "enum": ["fix", "redesign", "build", "reconsider", "protect", "investigate"],
                    },
                    "theme": {"type": "string"},
                    "problem": {"type": "string"},
                    "evidence": {"type": "string"},
                    "review_ids": _IDS,
                    "who": {"type": "string"},
                    "root_causes": {"type": "array", "items": {"type": "string"}},
                    "how_might_we": {"type": "array", "items": {"type": "string"}},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"idea": {"type": "string"}, "effort": _LEVEL},
                            "required": ["idea", "effort"],
                        },
                    },
                    "impact": _LEVEL,
                    "confidence": _LEVEL,
                    "effort": _LEVEL,
                    "metric": {"type": "string"},
                    "risk_of_inaction": {"type": "string"},
                },
                "required": [
                    "title",
                    "lens",
                    "action",
                    "theme",
                    "problem",
                    "evidence",
                    "review_ids",
                    "who",
                    "root_causes",
                    "how_might_we",
                    "options",
                    "impact",
                    "confidence",
                    "effort",
                    "metric",
                    "risk_of_inaction",
                ],
            },
        }
    },
    "required": ["decisions"],
}

_POINT = {
    "type": "object",
    "properties": {"heading": {"type": "string"}, "detail": {"type": "string"}, "review_ids": _IDS},
    "required": ["heading", "detail", "review_ids"],
}
REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "key_findings": {"type": "array", "items": _POINT},
        "user_needs": {"type": "array", "items": {"type": "string"}},
        "opportunities": {"type": "array", "items": _POINT},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "detail": {"type": "string"},
                    "when": {"type": "string", "enum": ["now", "next", "later"]},
                },
                "required": ["heading", "detail", "when"],
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "summary",
        "key_findings",
        "user_needs",
        "opportunities",
        "recommendations",
        "open_questions",
    ],
}

WHAT_CHANGED_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["new", "worse", "better", "steady"]},
                    "theme": {"type": "string"},
                    "detail": {"type": "string"},
                    "review_ids": _IDS,
                },
                "required": ["kind", "theme", "detail", "review_ids"],
            },
        },
        "next_step": {"type": "string"},
    },
    "required": ["headline", "changes", "next_step"],
}

PERSONAS_SCHEMA = {
    "type": "object",
    "properties": {
        "personas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "who": {"type": "string"},
                    "goals": {"type": "array", "items": {"type": "string"}},
                    "frustrations": {"type": "array", "items": {"type": "string"}},
                    "behaviours": {"type": "array", "items": {"type": "string"}},
                    "how_common": {"type": "string"},
                    "design_implications": {"type": "array", "items": {"type": "string"}},
                    "review_ids": _IDS,
                },
                "required": [
                    "name",
                    "who",
                    "goals",
                    "frustrations",
                    "behaviours",
                    "how_common",
                    "design_implications",
                    "review_ids",
                ],
            },
        }
    },
    "required": ["personas"],
}

# ---- prompts -------------------------------------------------------------------------------------

DECISIONS_TASK = """Turn the facts into 6-10 decisions the team should make, most important first.
Mix design decisions (lens "design": fix or redesign a flow, screen, wording or interaction) and product
decisions (lens "product": what to build, fix first, reconsider in policy/pricing/ads, or protect).
Each decision targets one theme from the facts. Include one "protect" decision for a strength if there are any.
- title: an imperative action, e.g. "Make account recovery self-service".
- problem: one sentence a designer could put on a sticky note. evidence: the key numbers from the facts.
- who: which users are affected. root_causes: 1-3 likely causes, phrased as hypotheses.
- how_might_we: 2 "How might we..." questions. options: 2-3 concrete ideas with rough effort.
- impact: how much acting would improve ratings or retention given reach and negativity.
  confidence: how solid the evidence is. effort: rough size of the work.
- metric: what to watch after shipping (use the app's own numbers, e.g. "negative share of login issues, now 83%").
- risk_of_inaction: what happens if nothing is done."""

REPORT_TASK = """Write a UX research report a designer could share with stakeholders.
- title: short and specific. summary: 3-5 sentences with the most important numbers.
- key_findings: 4-7 findings, each with a heading, 2-3 sentences of detail and supporting review_ids.
- user_needs: 3-6 underlying needs, phrased as "Users need to ...".
- opportunities: 3-5 design or product opportunities with review_ids.
- recommendations: 3-6, each marked now, next or later.
- open_questions: 2-4 questions reviews can't answer that need further research."""

WHAT_CHANGED_TASK = """Explain what changed between the two periods in the comparison, for a weekly product review.
- headline: one sentence with the most important change and its numbers.
- changes: 3-8 items: new themes (kind new), themes getting worse or better, and anything notable that
  stayed the same. Use the shares from the facts. Cite reviews from the newer period when possible.
- next_step: one practical recommendation.
If the comparison has too few reviews to conclude anything, say so in the headline."""

PERSONAS_TASK = """Draft 2-4 proto-personas grounded only in these reviews. They are hypotheses to validate with
research, not facts. Give each a short descriptive name (e.g. "The long-time raider"), who they are, goals,
frustrations, typical behaviours, how common they seem in these reviews (based on the counts), and design
implications. Cite the reviews each persona is based on."""


# ---- generation --------------------------------------------------------------------------------


def _ids(value: Any, citable: dict) -> list[str]:
    return [str(i) for i in (value or []) if str(i) in citable][:4]


def _matching_ids(text: str, citable: dict, n: int = 2) -> list[str]:
    """Fallback evidence when the model forgot to cite: reviews whose themes appear in the point's text."""
    lowered = text.lower()
    hits = [rid for rid, r in citable.items() if any(t and t.lower() in lowered for t in r.get("themes") or [])]
    return hits[:n]


def _tidy(value: Any, key: str = "") -> Any:
    """Round numbers for the model: shares as whole percentages, everything else to 2 decimals."""
    if isinstance(value, dict):
        return {k: _tidy(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_tidy(v, key) for v in value]
    if isinstance(value, float):
        return f"{value * 100:.0f}%" if key.endswith("share") else round(value, 2)
    return value


def _level(value: Any, default: str = "medium") -> str:
    value = str(value or "").lower()
    return value if value in LEVEL else default


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def priority(impact: str, confidence: str, effort: str) -> tuple[float, str]:
    """Impact x confidence / effort, bucketed into now / next / later."""
    score = LEVEL[impact] * LEVEL[confidence] / LEVEL[effort]
    return round(score, 2), "now" if score >= 4.5 else "next" if score >= 2 else "later"


def _clean_decisions(data: dict, citable: dict, previous: dict | None) -> dict:
    statuses = {(d["lens"], d["theme"]): d.get("status", "todo") for d in (previous or {}).get("decisions", [])}
    out = []
    for item in data.get("decisions") or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        lens = item.get("lens") if item.get("lens") in ("design", "product") else "product"
        impact, confidence, effort = (_level(item.get(k)) for k in ("impact", "confidence", "effort"))
        score, bucket = priority(impact, confidence, effort)
        theme = str(item.get("theme") or "")
        out.append(
            {
                "id": _slug(f"{lens}-{theme}-{item['title']}"),
                "title": str(item["title"]),
                "lens": lens,
                "action": str(item.get("action") or "investigate"),
                "theme": theme,
                "problem": str(item.get("problem") or ""),
                "evidence": str(item.get("evidence") or ""),
                "review_ids": _ids(item.get("review_ids"), citable),
                "who": str(item.get("who") or ""),
                "root_causes": [str(x) for x in item.get("root_causes") or []][:3],
                "how_might_we": [str(x) for x in item.get("how_might_we") or []][:3],
                "options": [
                    {"idea": str(o.get("idea", "")), "effort": _level(o.get("effort"))}
                    for o in item.get("options") or []
                    if isinstance(o, dict) and o.get("idea")
                ][:3],
                "impact": impact,
                "confidence": confidence,
                "effort": effort,
                "score": score,
                "priority": bucket,
                "metric": str(item.get("metric") or ""),
                "risk_of_inaction": str(item.get("risk_of_inaction") or ""),
                "status": statuses.get((lens, theme), "todo"),
            }
        )
    out.sort(key=lambda d: d["score"], reverse=True)
    return {"decisions": out}


def _clean_points(items: Any, citable: dict) -> list[dict]:
    points = []
    for p in items or []:
        if not isinstance(p, dict) or not p.get("heading"):
            continue
        heading, detail = str(p.get("heading", "")), str(p.get("detail", ""))
        ids = _ids(p.get("review_ids"), citable) or _matching_ids(f"{heading} {detail}", citable)
        points.append({"heading": heading, "detail": detail, "review_ids": ids})
    return points


def _clean_report(data: dict, citable: dict, facts: FactSheet) -> dict:
    b = facts.basics()
    run = facts.run
    stars = "" if b["star_filter"] == "all ratings" else f" ({', '.join(map(str, b['star_filter']))}-star reviews only)"
    method = (
        f"{b['reviews']} Google Play reviews of {b['app']} from {b['market']}{stars},"
        f" written between {b['period'][0]} and {b['period'][1]}. Each review was tagged by AI ({run.model}) for"
        " feedback type, themes, journey stage and emotion; themes were then grouped. Numbers come from those tags;"
        " quotes are verbatim."
    )
    return {
        "title": str(data.get("title") or f"What {b['app']} users are telling us"),
        "summary": str(data.get("summary") or ""),
        "method": method,
        "key_findings": _clean_points(data.get("key_findings"), citable),
        "user_needs": [str(x) for x in data.get("user_needs") or []],
        "opportunities": _clean_points(data.get("opportunities"), citable),
        "recommendations": [
            {
                "heading": str(r.get("heading", "")),
                "detail": str(r.get("detail", "")),
                "when": r.get("when") if r.get("when") in ("now", "next", "later") else "next",
            }
            for r in data.get("recommendations") or []
            if isinstance(r, dict) and r.get("heading")
        ],
        "open_questions": [str(x) for x in data.get("open_questions") or []],
    }


def _clean_what_changed(data: dict, citable: dict, facts_change: dict) -> dict:
    return {
        "headline": str(data.get("headline") or ""),
        "compared": (facts_change.get("comparison") or {}).get("compared"),
        "changes": [
            {
                "kind": c.get("kind") if c.get("kind") in ("new", "worse", "better", "steady") else "steady",
                "theme": str(c.get("theme", "")),
                "detail": str(c.get("detail", "")),
                "review_ids": _ids(c.get("review_ids"), citable),
            }
            for c in data.get("changes") or []
            if isinstance(c, dict) and c.get("detail")
        ],
        "next_step": str(data.get("next_step") or ""),
    }


def _clean_personas(data: dict, citable: dict) -> dict:
    def strings(value: Any) -> list[str]:
        return [str(x) for x in value or []][:5]

    return {
        "personas": [
            {
                "name": str(p.get("name", "")),
                "who": str(p.get("who", "")),
                "goals": strings(p.get("goals")),
                "frustrations": strings(p.get("frustrations")),
                "behaviours": strings(p.get("behaviours")),
                "how_common": str(p.get("how_common", "")),
                "design_implications": strings(p.get("design_implications")),
                "review_ids": _ids(p.get("review_ids"), citable),
            }
            for p in data.get("personas") or []
            if isinstance(p, dict) and p.get("name")
        ][:4]
    }


async def generate(kind: str, provider: LLMProvider, df: pd.DataFrame, run: Run, previous: dict | None = None) -> dict:
    """Build the fact sheet for `kind`, ask the model, validate. Returns content incl. the cited reviews."""
    if kind not in KINDS:
        raise ValueError(f"Unknown artifact '{kind}'.")
    facts = FactSheet(df, run)
    sheet: dict[str, Any] = {"analysis": facts.basics()}
    clean: Callable[[dict], dict]
    if kind == "decisions":
        sheet |= facts.problems() | {"feedback_types": facts.feedback(), "journey": facts.journey()}
        sheet |= {"risks": facts.risks(), "user_types": facts.user_types()}
        task, schema = DECISIONS_TASK, DECISIONS_SCHEMA
        clean = lambda d: _clean_decisions(d, facts.citable, previous)  # noqa: E731
    elif kind == "report":
        sheet |= facts.problems(quotes=2) | {"feedback_types": facts.feedback(3), "journey": facts.journey()}
        sheet |= {"risks": facts.risks(), "user_types": facts.user_types()}
        task, schema = REPORT_TASK, REPORT_SCHEMA
        clean = lambda d: _clean_report(d, facts.citable, facts)  # noqa: E731
    elif kind == "what_changed":
        change = facts.change()
        sheet |= change
        # quotes from the newer period about the themes that moved
        newer = facts.problems(limit=8, quotes=2)
        sheet |= {"current_problems": newer["problems"]}
        task, schema = WHAT_CHANGED_TASK, WHAT_CHANGED_SCHEMA
        clean = lambda d: _clean_what_changed(d, facts.citable, change)  # noqa: E731
    else:
        sheet |= {"user_types": facts.user_types(), "journey": facts.journey()} | facts.problems(limit=8, quotes=1)
        sheet |= {"detailed_reviews": facts.detailed_reviews()}
        task, schema = PERSONAS_TASK, PERSONAS_SCHEMA
        clean = lambda d: _clean_personas(d, facts.citable)  # noqa: E731

    import json

    system = PREAMBLE.format(
        app=sheet["analysis"]["app"], reviews=sheet["analysis"]["reviews"], language=run.output_language
    )
    prompt = f"{task}\n\nFACTS:\n{json.dumps(_tidy(sheet), ensure_ascii=False, default=str)}"
    data, _usage = await provider.complete_json(system=system, prompt=prompt, schema=schema, max_tokens=8000)
    content = clean(data)
    cited = {i for i in _all_ids(content)}
    content["reviews"] = {i: _public_review(facts.citable[i]) for i in cited if i in facts.citable}
    return content


def _all_ids(value: Any):
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "review_ids":
                yield from v
            else:
                yield from _all_ids(v)
    elif isinstance(value, list):
        for item in value:
            yield from _all_ids(item)


def _public_review(r: dict) -> dict:
    return {k: r.get(k) for k in ("review_id", "rating", "date", "content", "app_version", "thumbs_up", "themes")}


def set_status(content: dict, item_id: str, status: str) -> dict:
    if status not in STATUSES:
        raise ValueError(f"Status must be one of {', '.join(STATUSES)}.")
    for decision in content.get("decisions", []):
        if decision["id"] == item_id:
            decision["status"] = status
            return content
    raise ValueError("Decision not found.")


def to_markdown(content: dict, run: Run) -> str:
    """Research report as Markdown with quotes written out (for sharing outside the app)."""
    reviews = content.get("reviews", {})

    def quotes(ids: list[str]) -> str:
        lines = []
        for i in ids:
            r = reviews.get(i)
            if r:
                text = " ".join(str(r["content"]).split())
                lines.append(f"> “{text}” ({r['rating']}★, {str(r.get('date') or '')[:10]})")
        return ("\n\n" + "\n>\n".join(lines)) if lines else ""

    md = [f"# {content['title']}", "", content["summary"], "", "## Method", "", content["method"], ""]
    md += ["## Key findings", ""]
    for f in content["key_findings"]:
        md += [f"### {f['heading']}", "", f["detail"] + quotes(f["review_ids"]), ""]
    if content["user_needs"]:
        md += ["## User needs", ""] + [f"- {n}" for n in content["user_needs"]] + [""]
    if content["opportunities"]:
        md += ["## Opportunities", ""]
        for o in content["opportunities"]:
            md += [f"### {o['heading']}", "", o["detail"] + quotes(o["review_ids"]), ""]
    if content["recommendations"]:
        md += ["## Recommendations", ""]
        md += [f"- **{r['heading']}** ({r['when']}): {r['detail']}" for r in content["recommendations"]] + [""]
    if content["open_questions"]:
        md += ["## Open questions", ""] + [f"- {q}" for q in content["open_questions"]] + [""]
    md += [f"*Generated by Review Insights from an analysis of {run.app.title or run.app.store_id}.*", ""]
    return "\n".join(md)
