"""Benchmarks: compare 2-4 analyses (competitors, markets or periods). The first analysis is "yours"."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from ..analytics.benchmark import run_summary
from ..analytics.frame import load_run_frame
from ..assistant import benchmark_ai
from ..context import AppContext, get_ctx
from ..db import utcnow
from ..models import Benchmark, Run, RunStatus
from ..providers import resolve_config
from ..schemas import LLMConfigIn, RunOut

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


class BenchmarkIn(BaseModel):
    run_ids: list[str] = Field(min_length=2, max_length=4)
    name: str | None = Field(None, max_length=200)


class InsightsIn(BaseModel):
    llm: LLMConfigIn


def _runs(ctx: AppContext, run_ids: list[str]) -> list[Run]:
    if len(set(run_ids)) != len(run_ids):
        raise HTTPException(400, "Pick different analyses.")
    with ctx.db.session() as s:
        runs = [s.get(Run, rid) for rid in run_ids]
    if any(r is None for r in runs):
        raise HTTPException(404, "One of these analyses no longer exists.")
    if any(r.status != RunStatus.COMPLETED for r in runs):
        raise HTTPException(409, "Only finished analyses can be compared.")
    return runs


def _get(ctx: AppContext, benchmark_id: str) -> Benchmark:
    with ctx.db.session() as s:
        found = s.get(Benchmark, benchmark_id)
    if found is None:
        raise HTTPException(404, "Benchmark not found.")
    return found


def _brief(b: Benchmark, ctx: AppContext) -> dict:
    with ctx.db.session() as s:
        runs = [s.get(Run, rid) for rid in b.run_ids]
    return {
        "id": b.id,
        "name": b.name,
        "apps": [
            {"run_id": r.id, "title": r.app.title or r.app.store_id, "icon_url": r.app.icon_url, "country": r.country}
            for r in runs
            if r is not None
        ],
        "updated_at": b.updated_at.isoformat() + "Z",
    }


@router.get("")
def list_benchmarks(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    with ctx.db.session() as s:
        rows = s.scalars(select(Benchmark).order_by(Benchmark.updated_at.desc())).all()
    return [_brief(b, ctx) for b in rows]


@router.post("", status_code=201)
def create_benchmark(body: BenchmarkIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    runs = _runs(ctx, body.run_ids)
    name = body.name or " vs ".join(dict.fromkeys(r.app.title or r.app.store_id for r in runs))
    b = Benchmark(id=uuid.uuid4().hex, name=name[:200], run_ids=body.run_ids)
    with ctx.db.session() as s:
        s.add(b)
    return _brief(b, ctx)


@router.get("/{benchmark_id}")
def get_benchmark(benchmark_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    b = _get(ctx, benchmark_id)
    with ctx.db.session() as s:
        runs = [s.get(Run, rid) for rid in b.run_ids]
    columns = []
    for run in runs:
        if run is None:
            continue
        df = load_run_frame(ctx.db, run.id, ctx.frames)
        columns.append({"run": RunOut.model_validate(run).model_dump(mode="json"), "summary": run_summary(df)})
    return {
        "id": b.id,
        "name": b.name,
        "columns": columns,
        "insights": b.content,
        "provider": b.provider,
        "model": b.model,
        "updated_at": b.updated_at.isoformat() + "Z",
    }


@router.post("/{benchmark_id}/insights")
async def generate_insights(benchmark_id: str, body: InsightsIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    b = _get(ctx, benchmark_id)
    runs = _runs(ctx, b.run_ids)
    llm = resolve_config(body.llm.to_config())
    if not llm.model:
        raise HTTPException(400, "Choose an AI model in settings first.")
    frames = [load_run_frame(ctx.db, r.id, ctx.frames) for r in runs]
    if any(not df["tagged"].any() for df in frames):
        raise HTTPException(409, "Every analysis needs AI tags. Run older analyses again first.")
    provider = ctx.provider_factory(llm)
    try:
        content = await benchmark_ai.generate(provider, runs, frames, [run_summary(df) for df in frames])
    finally:
        await provider.aclose()
    with ctx.db.session() as s:
        row = s.get(Benchmark, benchmark_id)
        row.content, row.provider, row.model, row.updated_at = content, llm.provider, llm.model, utcnow()
    return get_benchmark(benchmark_id, ctx)


@router.delete("/{benchmark_id}", status_code=204)
def delete_benchmark(benchmark_id: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    _get(ctx, benchmark_id)
    with ctx.db.session() as s:
        s.execute(delete(Benchmark).where(Benchmark.id == benchmark_id))
    return Response(status_code=204)
