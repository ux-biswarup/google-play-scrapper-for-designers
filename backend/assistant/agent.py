"""The in-app research assistant: a tool-calling loop over one analysis, streamed as events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from ..providers import ChatMessage, LLMProvider, TextDelta, ToolSpec, TurnEnd, Usage
from .tools import TOOLS, ToolContext, run_tool

MAX_STEPS = 8
MAX_TOOL_CHARS = 12_000
MAX_HISTORY = 40
CITATION = "[[r:REVIEW_ID]]"

SYSTEM = """You are the research assistant inside Review Insights. You help a product designer or PM understand
Google Play reviews of {app} ({package}). This conversation is about one analysis: {reviews} reviews from
{market}, {ratings}, written between {date_from} and {date_to}, tagged by AI ({model}).

How to work:
- Answer from this analysis only, using the tools. Never invent numbers, themes or quotes.
- Start with get_problems or get_overview when you need context; use search_reviews to find evidence.
- Cite every review you rely on by writing {citation} right after the claim, with the review_id from a tool
  result. Quote short phrases word for word.
- If the data can't answer a question, say so plainly and suggest what would (more reviews, another market,
  all ratings, a longer period).
- Lead with the answer. Keep it short: brief paragraphs or bullets, key numbers in bold, percentages rounded.
- For design artifacts (problem statements, How Might We questions, personas, journey notes, tickets,
  stakeholder summaries) ground every point in the evidence and cite it.
Reply in {language}."""


def chat_tools() -> list[ToolSpec]:
    """Tools for the in-app chat: bound to the current analysis, so run_id is filled in automatically."""
    specs = []
    for tool in TOOLS.values():
        if tool.name in ("list_analyses", "compare_analyses"):  # about other analyses; MCP only
            continue
        params = json.loads(json.dumps(tool.parameters))
        params.get("properties", {}).pop("run_id", None)
        params["required"] = [r for r in params.get("required", []) if r != "run_id"]
        specs.append(ToolSpec(tool.name, tool.description, params))
    return specs


def step_label(name: str, args: dict[str, Any]) -> str:
    """Plain-language description of a tool call, shown to the user while the assistant works."""
    if name == "search_reviews":
        about = [f"“{args['text']}”" if args.get("text") else "", args.get("theme") or ""]
        detail = " ".join(a for a in about if a)
        return f"Searched reviews {detail}".strip() if detail else "Searched reviews"
    if name == "query_metrics":
        measures = ", ".join(m.replace("_", " ") for m in args.get("measures", []))
        dims = ", ".join(d.replace("_", " ") for d in args.get("dimensions") or [])
        return f"Calculated {measures}" + (f" by {dims}" if dims else "")
    if name == "compare_periods":
        return f"Compared before and after {args.get('pivot', '')}".strip()
    return {
        "get_problems": "Read the problem board",
        "get_overview": "Read the overview",
        "get_trends": "Checked trends over time",
        "describe_metrics": "Looked up metric definitions",
        "get_feedback_types": "Read the bug, request and complaint boards",
        "get_journey_map": "Read the journey map",
        "get_segments": f"Compared segments by {str(args.get('by', 'user type')).replace('_', ' ')}",
        "get_risks": "Checked churn, competitor and payment risks",
    }.get(name, name.replace("_", " ").capitalize())


def _shrink(value: Any, keep: int, chars: int) -> Any:
    if isinstance(value, dict):
        return {k: _shrink(v, keep, chars) for k, v in value.items()}
    if isinstance(value, list):
        return [_shrink(v, keep, chars) for v in value[:keep]]
    if isinstance(value, str) and len(value) > chars:
        return value[:chars].rstrip() + "…"
    return value


def fit_json(value: Any, limit: int = MAX_TOOL_CHARS) -> str:
    """A tool result as JSON under limit characters. Long lists and texts are shortened step by step instead of
    cutting the text, so the model, the saved chat and the citations always get valid JSON."""
    text = json.dumps(value, default=str, ensure_ascii=False)
    keep, chars = 12, 400
    while len(text) > limit and keep >= 1:
        shrunk = _shrink(value, keep, chars)
        if isinstance(shrunk, dict):
            shrunk["note"] = "Shortened to fit. Ask for fewer items or a narrower filter to see more."
        text = json.dumps(shrunk, default=str, ensure_ascii=False)
        keep, chars = keep // 2, max(80, chars * 2 // 3)
    if len(text) > limit:
        return json.dumps({"error": "That result was too large. Ask for fewer items or a narrower filter."})
    return text


def collect_reviews(value: Any, found: dict[str, dict] | None = None) -> dict[str, dict]:
    """Find review objects in a tool result so the interface can show cited reviews."""
    found = {} if found is None else found
    if isinstance(value, dict):
        if "review_id" in value and "text" in value:
            found[str(value["review_id"])] = value
        for item in value.values():
            collect_reviews(item, found)
    elif isinstance(value, list):
        for item in value:
            collect_reviews(item, found)
    return found


async def run_agent(
    provider: LLMProvider,
    *,
    system: str,
    history: list[ChatMessage],
    ctx: ToolContext,
    run_id: str,
    new_messages: list[ChatMessage],
) -> AsyncIterator[dict]:
    """Run the assistant until it answers. Yields interface events; appends produced messages to new_messages."""
    tools = chat_tools()
    usage = Usage()
    conversation = history[-MAX_HISTORY:]
    for _step in range(MAX_STEPS):
        text = ""
        end: TurnEnd | None = None
        async for event in provider.chat_stream(system=system, messages=conversation + new_messages, tools=tools):
            if isinstance(event, TextDelta):
                text += event.text
                yield {"type": "text", "delta": event.text}
            else:
                end = event
        calls = end.tool_calls if end else []
        if end:
            usage.add(end.usage)
        new_messages.append(ChatMessage("assistant", text, tool_calls=calls))
        if not calls:
            yield {"type": "done", "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}}
            return
        for call in calls:
            label = step_label(call.name, call.arguments)
            yield {"type": "tool", "id": call.id, "name": call.name, "label": label}
            try:
                result = await asyncio.to_thread(run_tool, ctx, call.name, {**call.arguments, "run_id": run_id})
                content = fit_json(result)
                # Cite only what the model actually saw (the result may have been shortened).
                seen = collect_reviews(json.loads(content))
                yield {"type": "tool_result", "id": call.id, "ok": True, "reviews": seen}
            except (ValueError, TypeError) as exc:  # bad arguments from the model: tell it, let it retry
                content = json.dumps({"error": str(exc)})
                yield {"type": "tool_result", "id": call.id, "ok": False, "reviews": {}}
            new_messages.append(ChatMessage("tool", content, tool_call_id=call.id, name=call.name))
    note = "\n\nI stopped after several lookups without finishing. Try a narrower question."
    new_messages.append(ChatMessage("assistant", note))
    yield {"type": "text", "delta": note}
    yield {"type": "done", "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}}
