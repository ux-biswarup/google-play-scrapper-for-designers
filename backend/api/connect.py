"""Details the frontend needs to show copy-paste MCP setup for Claude, ChatGPT, Cursor, Codex and VS Code."""

from __future__ import annotations

import sys

from fastapi import APIRouter, Request

from ..assistant.tools import TOOLS
from ..config import ROOT_DIR

router = APIRouter(prefix="/connect", tags=["connect"])


@router.get("/mcp")
def mcp_info(request: Request) -> dict:
    base = str(request.base_url).rstrip("/")
    return {
        "server_name": "review-insights",
        "http_url": f"{base}/mcp/",
        "python": sys.executable,
        "project_dir": str(ROOT_DIR),
        "module": "backend.mcp_server",
        "tools": [{"name": t.name, "description": t.description.split("\n")[0]} for t in TOOLS.values()],
    }
