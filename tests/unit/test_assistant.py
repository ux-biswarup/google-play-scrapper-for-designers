"""Chat assistant, shared tools and MCP server, tested offline with the scripted fake model."""

from __future__ import annotations

import asyncio
import json

from conftest import RUN_BODY, wait_for_run
from mcp import Client

from backend.assistant.agent import chat_tools, step_label
from backend.assistant.tools import TOOLS, ToolContext
from backend.mcp_server import build_mcp_server

LLM = {"provider": "anthropic", "model": "fake-model", "api_key": "sk-test"}


def _events(response) -> list[dict]:
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _finished_run(client) -> str:
    run = wait_for_run(client, client.post("/api/runs", json=RUN_BODY).json()["id"])
    assert run["status"] == "completed"
    return run["id"]


def test_chat_tools_are_bound_to_the_analysis():
    tools = {t.name: t for t in chat_tools()}
    assert "list_analyses" not in tools
    assert all("run_id" not in t.parameters.get("properties", {}) for t in tools.values())
    assert "run_id" in TOOLS["get_problems"].parameters["required"]  # MCP keeps it
    assert step_label("search_reviews", {"text": "login", "theme": ""}) == "Searched reviews “login”"
    assert step_label("query_metrics", {"measures": ["review_count"], "dimensions": ["theme"]}).endswith("by theme")


def test_chat_answers_with_tools_and_citations(client, llm_calls):
    run_id = _finished_run(client)
    response = client.post(f"/api/runs/{run_id}/chat", json={"message": "What hurts most?", "llm": LLM})
    events = _events(response)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "tool" and events[0]["label"] == "Read the problem board"
    assert events[1]["type"] == "tool_result" and events[1]["ok"] and events[1]["reviews"]
    text = "".join(e["delta"] for e in events if e["type"] == "text")
    cited = text.split("[[r:")[1].rstrip("]")
    assert cited in events[1]["reviews"]  # the citation points at a real review the tool returned
    assert kinds[-1] == "done"

    chat = client.get(f"/api/runs/{run_id}/chat").json()
    assert [t["role"] for t in chat["turns"]] == ["user", "assistant"]
    assistant = chat["turns"][1]
    assert assistant["steps"][0]["label"] == "Read the problem board"
    assert cited in assistant["reviews"] and "[[r:" in assistant["text"]
    assert chat["suggestions"]

    # A follow-up sends the earlier conversation (user, tool call, tool result, answer) back to the model.
    client.post(f"/api/runs/{run_id}/chat", json={"message": "And the second?", "llm": LLM})
    assert llm_calls["chat_history_sizes"][-2] == 5
    assert client.delete(f"/api/runs/{run_id}/chat").status_code == 204
    assert client.get(f"/api/runs/{run_id}/chat").json()["turns"] == []


def test_bad_tool_arguments_are_reported_back_to_the_model(client):
    run_id = _finished_run(client)
    events = _events(client.post(f"/api/runs/{run_id}/chat", json={"message": "bad metric please", "llm": LLM}))
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["ok"] is False
    text = "".join(e["delta"] for e in events if e["type"] == "text")
    assert "Unknown measures" in text


def test_chat_errors_are_streamed_not_raised(client, provider_failure):
    from backend.providers import LLMError

    run_id = _finished_run(client)
    provider_failure["error"] = LLMError("OpenAI rejected the API key.", fatal=True)
    events = _events(client.post(f"/api/runs/{run_id}/chat", json={"message": "hi", "llm": LLM}))
    assert events[-1] == {"type": "error", "message": "OpenAI rejected the API key."}
    assert client.post("/api/runs/missing/chat", json={"message": "hi", "llm": LLM}).status_code == 404


def test_mcp_server_serves_the_same_tools(client):
    run_id = _finished_run(client)
    app_ctx = client.app.state.ctx
    server = build_mcp_server(ToolContext(app_ctx.db, app_ctx.frames))

    async def talk():
        async with Client(server) as mcp:
            tools = await mcp.list_tools()
            names = {t.name for t in tools.tools}
            listed = json.loads((await mcp.call_tool("list_analyses", {})).content[0].text)
            problems = json.loads((await mcp.call_tool("get_problems", {"run_id": run_id})).content[0].text)
            return names, listed, problems

    names, listed, problems = asyncio.run(talk())
    assert names == set(TOOLS)
    assert listed["analyses"][0]["run_id"] == run_id
    assert problems["problems"][0]["theme"] == "login problems"


def test_mcp_connection_details(client):
    info = client.get("/api/connect/mcp").json()
    assert info["http_url"].endswith("/mcp/")
    assert info["module"] == "backend.mcp_server" and len(info["tools"]) == len(TOOLS)
