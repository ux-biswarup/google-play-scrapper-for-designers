"""Decision views for one analysis: feedback boards, journey map, emotions, segments, risks, accessibility and
developer replies (with AI reply drafts)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..analytics import views
from ..analytics.frame import load_run_frame
from ..analytics.insights import review_dict
from ..context import AppContext, get_ctx
from ..models import Run
from ..providers import resolve_config
from ..schemas import LLMConfigIn

router = APIRouter(prefix="/runs/{run_id}/views", tags=["views"])


def _frame(ctx: AppContext, run_id: str):
    df = load_run_frame(ctx.db, run_id, ctx.frames)
    if df is None:
        raise HTTPException(404, "Analysis not found.")
    return df


@router.get("/feedback")
def feedback(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return views.feedback_boards(_frame(ctx, run_id))


@router.get("/journey")
def journey(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return views.journey_map(_frame(ctx, run_id))


@router.get("/emotions")
def emotions(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return views.emotions_view(_frame(ctx, run_id))


@router.get("/segments")
def segments(run_id: str, by: str = "sentiment", ctx: AppContext = Depends(get_ctx)) -> dict:
    return views.segments_view(_frame(ctx, run_id), by)


@router.get("/risks")
def risks(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return views.risks_view(_frame(ctx, run_id))


@router.get("/accessibility")
def accessibility(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return views.accessibility_view(_frame(ctx, run_id))


@router.get("/replies")
def replies(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return views.replies_view(_frame(ctx, run_id))


class DraftIn(BaseModel):
    review_id: str
    llm: LLMConfigIn


REPLY_SYSTEM = f"""You write a reply from an app's team to a Google Play review. At most {views.PLAY_REPLY_LIMIT}
characters (Google Play's limit). Thank them briefly, name their specific problem in plain words, and give one
honest next step (a workaround, a fix in progress only if the review says it was acknowledged, or "[support link]"
to reach support). Never promise features or dates, never blame the user, no marketing. Match the tone of the
team's earlier replies if given. Write in the review's language. Return {{"reply": "..."}}."""


@router.post("/replies/draft")
async def draft_reply(run_id: str, body: DraftIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    df = _frame(ctx, run_id)
    rows = df[df["review_id"] == body.review_id]
    if rows.empty:
        raise HTTPException(404, "That review isn't part of this analysis.")
    llm = resolve_config(body.llm.to_config())
    if not llm.model:
        raise HTTPException(400, "Choose an AI model in settings first.")
    review = review_dict(rows.iloc[0].to_dict())
    earlier = [str(r) for r in df["reply"].dropna().unique()[:3]]
    with ctx.db.session() as s:
        run = s.get(Run, run_id)
        app_name = run.app.title or run.app.store_id
    prompt = {
        "app": app_name,
        "review": {"rating": review["rating"], "text": review["content"], "themes": review["themes"]},
        "earlier_replies": earlier,
    }
    provider = ctx.provider_factory(llm)
    try:
        data, _usage = await provider.complete_json(
            system=REPLY_SYSTEM,
            prompt=json.dumps(prompt, ensure_ascii=False),
            schema={"type": "object", "properties": {"reply": {"type": "string"}}, "required": ["reply"]},
            max_tokens=600,
        )
    finally:
        await provider.aclose()
    reply = " ".join(str(data.get("reply") or "").split())
    if len(reply) > views.PLAY_REPLY_LIMIT:  # cut at the last full sentence or word that fits
        cut = reply[: views.PLAY_REPLY_LIMIT]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        reply = cut[: end + 1] if end > 150 else cut.rsplit(" ", 1)[0] + "…"
    return {"review_id": body.review_id, "reply": reply, "limit": views.PLAY_REPLY_LIMIT}
