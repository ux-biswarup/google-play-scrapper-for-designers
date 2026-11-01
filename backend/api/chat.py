"""Chat with the research assistant about one analysis. Replies stream as server-sent events."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from ..analytics.frame import load_run_frame
from ..assistant.agent import CITATION, SUGGESTIONS, SYSTEM, collect_reviews, run_agent, step_label
from ..assistant.tools import ToolContext
from ..context import AppContext, get_ctx
from ..db import utcnow
from ..models import ChatEntry, Run, RunStatus
from ..providers import ChatMessage, LLMError, ToolCall, resolve_config
from ..schemas import LLMConfigIn

router = APIRouter(prefix="/runs/{run_id}/chat", tags=["chat"])
log = logging.getLogger(__name__)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    llm: LLMConfigIn


def _completed_run(ctx: AppContext, run_id: str) -> Run:
    with ctx.db.session() as s:
        run = s.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Analysis not found.")
    if run.status != RunStatus.COMPLETED:
        raise HTTPException(409, "The assistant is available once the analysis has finished.")
    return run


def _history(ctx: AppContext, run_id: str) -> list[ChatMessage]:
    with ctx.db.session() as s:
        entries = s.scalars(select(ChatEntry).where(ChatEntry.run_id == run_id).order_by(ChatEntry.id)).all()
    return [
        ChatMessage(
            e.role,
            e.content,
            tool_calls=[ToolCall(c["id"], c["name"], c.get("arguments", {})) for c in e.tool_calls or []],
            tool_call_id=e.tool_call_id,
            name=e.name,
        )
        for e in entries
    ]


def _save(ctx: AppContext, run_id: str, messages: list[ChatMessage]) -> None:
    with ctx.db.session() as s:
        s.add_all(
            ChatEntry(
                run_id=run_id,
                role=m.role,
                content=m.content,
                tool_calls=[{"id": c.id, "name": c.name, "arguments": c.arguments} for c in m.tool_calls],
                tool_call_id=m.tool_call_id,
                name=m.name,
                created_at=utcnow(),
            )
            for m in messages
        )


def _system_prompt(ctx: AppContext, run: Run) -> str:
    df = load_run_frame(ctx.db, run.id, ctx.frames)
    dates = df["date"].dropna() if df is not None else []
    ratings = "all star ratings" if not run.ratings else f"only {', '.join(map(str, run.ratings))}-star reviews"
    return SYSTEM.format(
        app=run.app.title or run.app.store_id,
        package=run.app.store_id,
        reviews=run.review_count,
        market=(run.country or "an unknown market").upper(),
        ratings=ratings,
        date_from=dates.min().date() if len(dates) else "unknown",
        date_to=dates.max().date() if len(dates) else "unknown",
        model=run.model,
        citation=CITATION,
        language=run.output_language,
    )


def transcript(history: list[ChatMessage]) -> list[dict]:
    """Group stored messages into turns for display: user text, and assistant text with the steps it took."""
    turns: list[dict] = []
    labels: dict[str, str] = {}
    for m in history:
        if m.role == "user":
            turns.append({"role": "user", "text": m.content})
            continue
        if not turns or turns[-1]["role"] != "assistant":
            turns.append({"role": "assistant", "text": "", "steps": [], "reviews": {}})
        turn = turns[-1]
        if m.role == "assistant":
            turn["text"] += m.content
            for call in m.tool_calls:
                labels[call.id] = step_label(call.name, call.arguments)
                turn["steps"].append({"id": call.id, "label": labels[call.id], "ok": True})
        elif m.role == "tool":
            try:
                turn["reviews"].update(collect_reviews(json.loads(m.content)))
            except json.JSONDecodeError:
                pass
    return turns


@router.get("")
def get_chat(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    _completed_run(ctx, run_id)
    return {"turns": transcript(_history(ctx, run_id)), "suggestions": SUGGESTIONS}


@router.delete("", status_code=204)
def clear_chat(run_id: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    with ctx.db.session() as s:
        s.execute(delete(ChatEntry).where(ChatEntry.run_id == run_id))
    return Response(status_code=204)


@router.post("")
async def send_message(run_id: str, body: ChatIn, ctx: AppContext = Depends(get_ctx)) -> StreamingResponse:
    run = _completed_run(ctx, run_id)
    llm = resolve_config(body.llm.to_config())
    if not llm.model:
        raise HTTPException(400, "Choose an AI model in settings first.")
    provider = ctx.provider_factory(llm)  # raises LLMError (400) for a missing key or unknown provider
    history = _history(ctx, run_id)
    question = ChatMessage("user", body.message.strip())
    system = _system_prompt(ctx, run)
    _save(ctx, run_id, [question])

    async def stream():
        produced: list[ChatMessage] = []
        try:
            async for event in run_agent(
                provider,
                system=system,
                history=history + [question],
                ctx=ToolContext(ctx.db, ctx.frames),
                run_id=run_id,
                new_messages=produced,
            ):
                yield f"data: {json.dumps(event, default=str, ensure_ascii=False)}\n\n"
        except LLMError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        except Exception as exc:  # noqa: BLE001 - report instead of dropping the stream
            log.exception("Chat failed for run %s", run_id)
            yield f"data: {json.dumps({'type': 'error', 'message': f'Unexpected error: {exc}'})}\n\n"
        finally:
            # Save what was produced, even if the user stopped the reply part-way.
            if produced:
                _save(ctx, run_id, produced)
            await provider.aclose()

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
