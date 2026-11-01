"""Chats with the research assistant about one analysis. Each analysis has its own chats (sessions); a chat only
ever sees its own messages and its own analysis. Replies stream as server-sent events."""

from __future__ import annotations

import json
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from ..analytics.frame import load_run_frame
from ..analytics.insights import problem_board
from ..assistant.agent import CITATION, SUGGESTIONS, SYSTEM, collect_reviews, run_agent, step_label
from ..assistant.tools import ToolContext
from ..context import AppContext, get_ctx
from ..db import utcnow
from ..models import ChatEntry, ChatSession, Run, RunStatus
from ..providers import ChatMessage, LLMError, ToolCall, resolve_config
from ..schemas import LLMConfigIn

router = APIRouter(prefix="/runs/{run_id}/chat", tags=["chat"])
log = logging.getLogger(__name__)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    llm: LLMConfigIn


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)


TITLE_CHARS = 60


def title_from(message: str) -> str:
    """A chat's title: its first question, shortened at a word boundary."""
    text = " ".join(message.split())
    if len(text) <= TITLE_CHARS:
        return text
    cut = text[:TITLE_CHARS].rsplit(" ", 1)[0]
    return (cut or text[:TITLE_CHARS]).rstrip(",.;:") + "…"


def _completed_run(ctx: AppContext, run_id: str) -> Run:
    with ctx.db.session() as s:
        run = s.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Analysis not found.")
    if run.status != RunStatus.COMPLETED:
        raise HTTPException(409, "The assistant is available once the analysis has finished.")
    return run


def _session(ctx: AppContext, run_id: str, session_id: str) -> ChatSession:
    """A chat of this analysis. A chat id from another analysis is treated as not found, so context never mixes."""
    with ctx.db.session() as s:
        found = s.get(ChatSession, session_id)
    if found is None or found.run_id != run_id:
        raise HTTPException(404, "Chat not found.")
    return found


def _adopt_orphans(ctx: AppContext, run_id: str) -> None:
    """Move messages saved before chats had sessions into one "Earlier conversation" chat."""
    with ctx.db.session() as s:
        orphans = s.scalars(
            select(ChatEntry).where(ChatEntry.run_id == run_id, ChatEntry.session_id.is_(None)).order_by(ChatEntry.id)
        ).all()
        if not orphans:
            return
        first_question = next((e.content for e in orphans if e.role == "user"), "")
        chat = ChatSession(
            id=uuid.uuid4().hex,
            run_id=run_id,
            title=title_from(first_question) if first_question else "Earlier conversation",
            created_at=orphans[0].created_at,
            updated_at=orphans[-1].created_at,
        )
        s.add(chat)
        s.flush()
        for e in orphans:
            e.session_id = chat.id


def _history(ctx: AppContext, session_id: str) -> list[ChatMessage]:
    with ctx.db.session() as s:
        entries = s.scalars(select(ChatEntry).where(ChatEntry.session_id == session_id).order_by(ChatEntry.id)).all()
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


def for_model(history: list[ChatMessage]) -> list[ChatMessage]:
    """What the model sees: saved errors are for people, and a question whose answer failed is left out too, so a
    retry doesn't send the same question twice in a row."""
    keep: list[ChatMessage] = []
    for i, m in enumerate(history):
        if m.role == "error":
            continue
        if m.role == "user" and i + 1 < len(history) and history[i + 1].role == "error":
            continue
        keep.append(m)
    return keep


def _save(ctx: AppContext, chat: ChatSession, messages: list[ChatMessage]) -> None:
    now = utcnow()
    with ctx.db.session() as s:
        s.add_all(
            ChatEntry(
                run_id=chat.run_id,
                session_id=chat.id,
                role=m.role,
                content=m.content,
                tool_calls=[{"id": c.id, "name": c.name, "arguments": c.arguments} for c in m.tool_calls],
                tool_call_id=m.tool_call_id,
                name=m.name,
                created_at=now,
            )
            for m in messages
        )
        row = s.get(ChatSession, chat.id)
        if row is not None:
            row.updated_at = now


def _session_out(chat: ChatSession, questions: int = 0) -> dict:
    return {
        "id": chat.id,
        "title": chat.title,
        "questions": questions,
        "created_at": chat.created_at.isoformat() + "Z",
        "updated_at": chat.updated_at.isoformat() + "Z",
    }


def _suggestions(ctx: AppContext, run_id: str) -> list[str]:
    """Starter questions; the first names this analysis's biggest problem."""
    df = load_run_frame(ctx.db, run_id, ctx.frames)
    top = problem_board(df, limit=1, quotes=0)["problems"] if df is not None and df["tagged"].any() else []
    first = [f"Why are users unhappy about {top[0]['theme']}?"] if top else []
    return first + SUGGESTIONS[:4]


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


def _reviews_in(content: str) -> dict[str, dict]:
    """Reviews in a saved tool result. Older versions cut long results mid-way; recover every complete review."""
    try:
        return collect_reviews(json.loads(content))
    except json.JSONDecodeError:
        decoder, found, at = json.JSONDecoder(), {}, content.find('{"review_id"')
        while at >= 0:
            try:
                value, end = decoder.raw_decode(content, at)
                collect_reviews(value, found)
            except json.JSONDecodeError:
                end = at + 1
            at = content.find('{"review_id"', end)
        return found


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
        if m.role == "error":
            turn["error"] = m.content
        elif m.role == "assistant":
            turn["text"] += m.content
            for call in m.tool_calls:
                labels[call.id] = step_label(call.name, call.arguments)
                turn["steps"].append({"id": call.id, "label": labels[call.id], "ok": True})
        elif m.role == "tool":
            turn["reviews"].update(_reviews_in(m.content))
    return turns


_CITE = re.compile(r"\[\[r:[^\]]*\]\]")
SNIPPET_CHARS = 90


def snippet(text: str, query: str) -> str | None:
    """A short excerpt of text around the first match of query (case-insensitive), or None."""
    clean = " ".join(_CITE.sub("", text).split())
    at = clean.lower().find(query)
    if at < 0:
        return None
    start = max(0, at - 30)
    end = min(len(clean), start + SNIPPET_CHARS)
    return ("…" if start else "") + clean[start:end].strip() + ("…" if end < len(clean) else "")


@router.get("/sessions")
def list_sessions(run_id: str, q: str | None = None, ctx: AppContext = Depends(get_ctx)) -> dict:
    """This analysis's chats, most recent first. With q, only chats whose title, questions or answers mention it;
    a match inside the conversation comes with a snippet."""
    _completed_run(ctx, run_id)
    _adopt_orphans(ctx, run_id)
    query = " ".join((q or "").split()).lower()[:200]
    with ctx.db.session() as s:
        counts = dict(
            s.execute(
                select(ChatEntry.session_id, func.count())
                .where(ChatEntry.run_id == run_id, ChatEntry.role == "user")
                .group_by(ChatEntry.session_id)
            ).all()
        )
        chats = s.scalars(
            select(ChatSession).where(ChatSession.run_id == run_id).order_by(ChatSession.updated_at.desc())
        ).all()
        texts: dict[str, list[str]] = {}
        if query:
            rows = s.execute(
                select(ChatEntry.session_id, ChatEntry.content)
                .where(ChatEntry.run_id == run_id, ChatEntry.role.in_(("user", "assistant")))
                .order_by(ChatEntry.id)
            ).all()
            for session_id, content in rows:
                texts.setdefault(session_id, []).append(content or "")
    out = []
    for chat in chats:
        item = _session_out(chat, counts.get(chat.id, 0))
        if query:
            if query in chat.title.lower():
                item["snippet"] = None
            else:
                found = next((m for t in texts.get(chat.id, []) if (m := snippet(t, query))), None)
                if found is None:
                    continue
                item["snippet"] = found
        out.append(item)
    return {"sessions": out, "suggestions": _suggestions(ctx, run_id)}


@router.post("/sessions", status_code=201)
def create_session(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    _completed_run(ctx, run_id)
    chat = ChatSession(id=uuid.uuid4().hex, run_id=run_id)
    with ctx.db.session() as s:
        s.add(chat)
    return _session_out(chat)


@router.get("/sessions/{session_id}")
def get_session(run_id: str, session_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    chat = _session(ctx, run_id, session_id)
    turns = transcript(_history(ctx, session_id))
    return {**_session_out(chat, sum(1 for t in turns if t["role"] == "user")), "turns": turns}


@router.patch("/sessions/{session_id}")
def rename_session(run_id: str, session_id: str, body: RenameIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    _session(ctx, run_id, session_id)
    with ctx.db.session() as s:
        row = s.get(ChatSession, session_id)
        row.title = " ".join(body.title.split())[:120]
        s.flush()
        return _session_out(row)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(run_id: str, session_id: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    _session(ctx, run_id, session_id)
    with ctx.db.session() as s:
        # Explicit: databases upgraded from older versions have no foreign key on session_id.
        s.execute(delete(ChatEntry).where(ChatEntry.session_id == session_id))
        s.execute(delete(ChatSession).where(ChatSession.id == session_id))
    return Response(status_code=204)


@router.post("/sessions/{session_id}/messages")
async def send_message(
    run_id: str, session_id: str, body: ChatIn, ctx: AppContext = Depends(get_ctx)
) -> StreamingResponse:
    run = _completed_run(ctx, run_id)
    chat = _session(ctx, run_id, session_id)
    llm = resolve_config(body.llm.to_config())
    if not llm.model:
        raise HTTPException(400, "Choose an AI model in settings first.")
    provider = ctx.provider_factory(llm)  # raises LLMError (400) for a missing key or unknown provider
    history = for_model(_history(ctx, session_id))  # this chat only: never other chats or other analyses
    question = ChatMessage("user", body.message.strip())
    system = _system_prompt(ctx, run)
    if not any(m.role == "user" for m in history) and chat.title == "New chat":
        with ctx.db.session() as s:
            s.get(ChatSession, session_id).title = title_from(question.content)
    _save(ctx, chat, [question])

    async def stream():
        produced: list[ChatMessage] = []
        error: str | None = None
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
            error = str(exc)
            yield f"data: {json.dumps({'type': 'error', 'message': error})}\n\n"
        except Exception as exc:  # noqa: BLE001 - report instead of dropping the stream
            log.exception("Chat failed for run %s", run_id)
            error = f"Unexpected error: {exc}"
            yield f"data: {json.dumps({'type': 'error', 'message': error})}\n\n"
        finally:
            # Save what was produced, even if the user stopped the reply part-way, and why it failed, so the chat
            # still explains itself after a reload.
            if error:
                produced.append(ChatMessage("error", error))
            if produced:
                _save(ctx, chat, produced)
            await provider.aclose()

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
