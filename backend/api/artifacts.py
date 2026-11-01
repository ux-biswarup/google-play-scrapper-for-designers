"""AI-written decision artifacts for a run: decisions, research report, what changed, personas."""

from __future__ import annotations

import copy
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from ..analytics.frame import load_run_frame
from ..assistant import artifacts
from ..context import AppContext, get_ctx
from ..db import utcnow
from ..models import Artifact, Run, RunStatus
from ..providers import resolve_config
from ..schemas import LLMConfigIn

router = APIRouter(prefix="/runs/{run_id}/artifacts", tags=["artifacts"])


class GenerateIn(BaseModel):
    llm: LLMConfigIn


class StatusIn(BaseModel):
    status: str


def _run(ctx: AppContext, run_id: str) -> Run:
    with ctx.db.session() as s:
        run = s.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Analysis not found.")
    return run


def _kind(kind: str) -> str:
    if kind not in artifacts.KINDS:
        raise HTTPException(404, f"Unknown artifact '{kind}'.")
    return kind


def _get(ctx: AppContext, run_id: str, kind: str) -> Artifact | None:
    with ctx.db.session() as s:
        return s.scalar(select(Artifact).where(Artifact.run_id == run_id, Artifact.kind == kind))


def _out(a: Artifact) -> dict:
    return {
        "kind": a.kind,
        "content": a.content,
        "provider": a.provider,
        "model": a.model,
        "created_at": a.created_at.isoformat() + "Z",
    }


@router.get("/{kind}")
def get_artifact(run_id: str, kind: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    _run(ctx, run_id)
    found = _get(ctx, run_id, _kind(kind))
    return {"artifact": _out(found) if found else None}


@router.post("/{kind}")
async def generate_artifact(run_id: str, kind: str, body: GenerateIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    run = _run(ctx, run_id)
    _kind(kind)
    if run.status != RunStatus.COMPLETED:
        raise HTTPException(409, "Wait for the analysis to finish first.")
    llm = resolve_config(body.llm.to_config())
    if not llm.model:
        raise HTTPException(400, "Choose an AI model in settings first.")
    df = load_run_frame(ctx.db, run_id, ctx.frames)
    if df is None or not df["tagged"].any():
        raise HTTPException(409, "This analysis has no AI tags to work from. Run it again.")
    existing = _get(ctx, run_id, kind)
    provider = ctx.provider_factory(llm)
    try:
        content = await artifacts.generate(kind, provider, df, run, previous=existing.content if existing else None)
    finally:
        await provider.aclose()
    with ctx.db.session() as s:
        row = s.scalar(select(Artifact).where(Artifact.run_id == run_id, Artifact.kind == kind))
        if row is None:
            row = Artifact(run_id=run_id, kind=kind, content=content, provider=llm.provider, model=llm.model)
            s.add(row)
        else:
            row.content, row.provider, row.model, row.created_at = content, llm.provider, llm.model, utcnow()
        s.flush()
        return {"artifact": _out(row)}


@router.patch("/decisions/{item_id}")
def set_decision_status(run_id: str, item_id: str, body: StatusIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    with ctx.db.session() as s:
        row = s.scalar(select(Artifact).where(Artifact.run_id == run_id, Artifact.kind == "decisions"))
        if row is None:
            raise HTTPException(404, "Generate decisions first.")
        # Edit a deep copy and flag the column: in-place edits to JSON values aren't detected otherwise.
        row.content = artifacts.set_status(copy.deepcopy(row.content), item_id, body.status)
        flag_modified(row, "content")
        return {"artifact": _out(row)}


@router.get("/report/markdown", include_in_schema=False)
def report_markdown(run_id: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    run = _run(ctx, run_id)
    found = _get(ctx, run_id, "report")
    if found is None:
        raise HTTPException(404, "Generate the report first.")
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{run.app.store_id}-ux-research-report.md")
    return Response(
        artifacts.to_markdown(found.content, run),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
