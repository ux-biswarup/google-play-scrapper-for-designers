from __future__ import annotations

import asyncio
import math

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select

from ..context import AppContext, get_ctx
from ..models import Run, RunStatus
from ..providers import resolve_config
from ..schemas import EstimateIn, RunCreate, RunOut
from ..services.pipeline import RunRequest
from ..services.play_store import PAGE_SIZE, parse_store_id

router = APIRouter(prefix="/runs", tags=["runs"])

# Rough per-review token sizes for the estimate (prompt text + JSON answer).
_INPUT_TOKENS_PER_REVIEW = 90
_OUTPUT_TOKENS_PER_REVIEW = 45
_PROMPT_TOKENS_PER_BATCH = 450
_SECONDS_PER_BATCH = 15
_SECONDS_PER_REVIEW_PAGE = 2


def _get_run(ctx: AppContext, run_id: str) -> Run:
    with ctx.db.session() as s:
        run = s.get(Run, run_id)
        if run is None:
            raise HTTPException(404, "Analysis not found.")
        return run


@router.post("/estimate")
def estimate(body: EstimateIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    batches = math.ceil(body.count / ctx.settings.batch_size)
    rounds = math.ceil(batches / ctx.settings.llm_concurrency)
    seconds = math.ceil(body.count / PAGE_SIZE) * _SECONDS_PER_REVIEW_PAGE + rounds * _SECONDS_PER_BATCH + 10
    return {
        "reviews": body.count,
        "ai_requests": batches + 1,
        "input_tokens": body.count * _INPUT_TOKENS_PER_REVIEW + batches * _PROMPT_TOKENS_PER_BATCH + 3000,
        "output_tokens": body.count * _OUTPUT_TOKENS_PER_REVIEW + 1500,
        "seconds": seconds,
        "note": "Rough estimate. Reviews already analyzed with the same model are reused and cost nothing.",
    }


@router.post("", status_code=201)
async def create_run(body: RunCreate, ctx: AppContext = Depends(get_ctx)) -> RunOut:
    store_id = parse_store_id(body.app)
    llm = resolve_config(body.llm.to_config())
    if not llm.model:
        raise HTTPException(400, "Choose an AI model.")
    # Fail fast on missing keys/unknown providers before creating the run.
    await ctx.provider_factory(llm).aclose()

    run_id = ctx.pipeline.create_run(RunRequest(
        store_id=store_id, country=body.country, lang=body.lang, count=body.count, ratings=body.ratings,
        output_language=body.output_language, llm=llm,
    ))
    ctx.jobs.start(run_id, lambda cancel: ctx.pipeline.execute(run_id, llm, cancel))
    return RunOut.model_validate(_get_run(ctx, run_id))


@router.get("")
def list_runs(limit: int = 50, ctx: AppContext = Depends(get_ctx)) -> list[RunOut]:
    with ctx.db.session() as s:
        runs = s.scalars(select(Run).order_by(Run.created_at.desc()).limit(min(max(limit, 1), 200))).all()
        return [RunOut.model_validate(r) for r in runs]


@router.get("/{run_id}")
def get_run(run_id: str, ctx: AppContext = Depends(get_ctx)) -> RunOut:
    return RunOut.model_validate(_get_run(ctx, run_id))


@router.get("/{run_id}/events")
async def run_events(run_id: str, request: Request, ctx: AppContext = Depends(get_ctx)) -> StreamingResponse:
    """Server-sent events with the run's progress until it finishes."""
    _get_run(ctx, run_id)

    async def stream():
        last = None
        while not await request.is_disconnected():
            run = RunOut.model_validate(await asyncio.to_thread(_get_run, ctx, run_id))
            payload = run.model_dump_json()
            if payload != last:
                yield f"event: progress\ndata: {payload}\n\n"
                last = payload
            if run.status in RunStatus.TERMINAL:
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/{run_id}/cancel", status_code=202)
def cancel_run(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    run = _get_run(ctx, run_id)
    if run.status in RunStatus.TERMINAL or not ctx.jobs.cancel(run_id):
        raise HTTPException(409, "This analysis is not running.")
    return {"status": "cancelling"}


@router.delete("/{run_id}", status_code=204)
def delete_run(run_id: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    _get_run(ctx, run_id)
    if ctx.jobs.is_active(run_id):
        raise HTTPException(409, "Cancel the analysis before deleting it.")
    with ctx.db.session() as s:
        s.execute(delete(Run).where(Run.id == run_id))
    return Response(status_code=204)
