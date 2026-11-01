"""MCP server: lets Claude, ChatGPT, Cursor, Codex and other MCP apps answer questions about your analyses.

Two ways to connect:
- stdio (desktop and CLI apps launch it):  python -m backend.mcp_server
- HTTP (served by the main app):           http://127.0.0.1:8000/mcp/
All tools are read-only. Start analyses in the Review Insights app.
"""

from __future__ import annotations

import functools
import inspect
import os

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from .analytics.frame import FrameCache
from .assistant.tools import TOOLS, ToolContext
from .config import load_settings
from .db import Database

INSTRUCTIONS = """Review Insights holds AI analyses of Google Play app reviews for product designers and PMs.
Start with list_analyses to find a run_id, then use get_problems, get_overview, get_trends,
search_reviews, compare_periods or query_metrics. Back every claim with numbers from these tools and
quote real reviews (with their review_id) as evidence. Say so when the data doesn't cover a question."""


def build_mcp_server(ctx: ToolContext) -> MCPServer:
    server = MCPServer(name="review-insights", title="Review Insights", instructions=INSTRUCTIONS)
    for spec in TOOLS.values():
        server.tool(
            name=spec.name,
            description=spec.description,
            annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
        )(_bind(spec.fn, ctx))
    return server


def _bind(fn, ctx: ToolContext):
    """Expose a tool function without its context argument, keeping its typed signature for the schema."""

    @functools.wraps(fn)
    def wrapper(**kwargs):
        return fn(ctx, **kwargs)

    # Resolve string annotations (from `from __future__ import annotations`) to real types here,
    # because the MCP SDK would otherwise evaluate them in this module's namespace.
    hints = inspect.get_annotations(fn, eval_str=True)
    signature = inspect.signature(fn)
    params = [p.replace(annotation=hints[p.name]) for p in list(signature.parameters.values())[1:]]
    wrapper.__signature__ = signature.replace(parameters=params, return_annotation=hints.get("return", dict))
    wrapper.__annotations__ = {k: v for k, v in hints.items() if k != "ctx"}
    del wrapper.__wrapped__  # make introspection use the signature above
    return wrapper


def http_security() -> TransportSecuritySettings:
    """Only accept local requests by default (protects against DNS-rebinding attacks from web pages).
    Add hosts with MCP_ALLOWED_HOSTS=example.com,other.host if you put the server behind a tunnel."""
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    extra = [h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts + extra,
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*"] + [f"https://{h}" for h in extra],
    )


def main() -> None:
    db = Database(load_settings().db_url)
    db.init()
    build_mcp_server(ToolContext(db, FrameCache())).run("stdio")


if __name__ == "__main__":
    main()
