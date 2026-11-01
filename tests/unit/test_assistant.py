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


def _new_chat(client, run_id: str) -> str:
    return client.post(f"/api/runs/{run_id}/chat/sessions").json()["id"]


def _ask(client, run_id: str, chat_id: str, message: str):
    return client.post(f"/api/runs/{run_id}/chat/sessions/{chat_id}/messages", json={"message": message, "llm": LLM})


def test_chat_answers_with_tools_and_citations(client, llm_calls):
    run_id = _finished_run(client)
    chat_id = _new_chat(client, run_id)
    events = _events(_ask(client, run_id, chat_id, "What hurts most?"))
    kinds = [e["type"] for e in events]
    assert kinds[0] == "tool" and events[0]["label"] == "Read the problem board"
    assert events[1]["type"] == "tool_result" and events[1]["ok"] and events[1]["reviews"]
    text = "".join(e["delta"] for e in events if e["type"] == "text")
    cited = text.split("[[r:")[1].rstrip("]")
    assert cited in events[1]["reviews"]  # the citation points at a real review the tool returned
    assert kinds[-1] == "done"

    chat = client.get(f"/api/runs/{run_id}/chat/sessions/{chat_id}").json()
    assert chat["title"] == "What hurts most?" and chat["questions"] == 1  # titled from the first question
    assert [t["role"] for t in chat["turns"]] == ["user", "assistant"]
    assistant = chat["turns"][1]
    assert assistant["steps"][0]["label"] == "Read the problem board"
    assert cited in assistant["reviews"] and "[[r:" in assistant["text"]

    # A follow-up sends the earlier conversation (user, tool call, tool result, answer) back to the model.
    _ask(client, run_id, chat_id, "And the second?")
    assert llm_calls["chat_history_sizes"][-2] == 5
    assert client.get(f"/api/runs/{run_id}/chat/sessions/{chat_id}").json()["title"] == "What hurts most?"


def test_chats_never_share_context(client, llm_calls):
    first_run, other_run = _finished_run(client), _finished_run(client)
    first = _new_chat(client, first_run)
    _ask(client, first_run, first, "What hurts most?")

    # A second chat on the same analysis starts empty: the model sees only the new question.
    second = _new_chat(client, first_run)
    _ask(client, first_run, second, "Anything else?")
    assert llm_calls["chat_history_sizes"][-2] == 1
    assert [t["text"] for t in client.get(f"/api/runs/{first_run}/chat/sessions/{second}").json()["turns"][:1]] == [
        "Anything else?"
    ]

    # Another analysis can't read or continue this analysis's chats, and lists none of them.
    assert client.get(f"/api/runs/{other_run}/chat/sessions/{first}").status_code == 404
    assert _ask(client, other_run, first, "hi").status_code == 404
    assert client.get(f"/api/runs/{other_run}/chat/sessions").json()["sessions"] == []

    listed = client.get(f"/api/runs/{first_run}/chat/sessions").json()
    assert [c["id"] for c in listed["sessions"]] == [second, first]  # most recent first
    assert listed["suggestions"][0] == "Why are users unhappy about login problems?"


def test_search_chat_history(client):
    run_id, other_run = _finished_run(client), _finished_run(client)
    login = _new_chat(client, run_id)
    _ask(client, run_id, login, "What hurts most?")  # the fake answer says "The biggest problem is login."
    other = _new_chat(client, run_id)
    _ask(client, run_id, other, "Anything about dark mode?")
    _ask(client, other_run, _new_chat(client, other_run), "What hurts most?")

    search = lambda q, rid=run_id: client.get(f"/api/runs/{rid}/chat/sessions", params={"q": q}).json()["sessions"]  # noqa: E731
    assert [(c["id"], c["snippet"]) for c in search("HURTS")] == [(login, None)]  # title match, any case
    by_answer = search("biggest problem")
    assert {c["id"] for c in by_answer} == {login, other}  # found in the answers
    assert all("biggest problem is login" in c["snippet"] and "[[r:" not in c["snippet"] for c in by_answer)
    assert search("nothing like this") == []
    assert len(search("hurts", other_run)) == 1  # only that analysis's own chats


def test_rename_and_delete_chats(client):
    run_id = _finished_run(client)
    chat_id = _new_chat(client, run_id)
    _ask(client, run_id, chat_id, "What hurts most?")
    renamed = client.patch(f"/api/runs/{run_id}/chat/sessions/{chat_id}", json={"title": "  Login   deep dive "})
    assert renamed.json()["title"] == "Login deep dive"
    assert client.delete(f"/api/runs/{run_id}/chat/sessions/{chat_id}").status_code == 204
    assert client.get(f"/api/runs/{run_id}/chat/sessions/{chat_id}").status_code == 404
    assert client.get(f"/api/runs/{run_id}/chat/sessions").json()["sessions"] == []


def test_messages_from_before_sessions_become_one_chat(client):
    from backend.models import ChatEntry

    run_id = _finished_run(client)
    db = client.app.state.ctx.db
    with db.session() as s:
        s.add_all(
            [
                ChatEntry(
                    run_id=run_id, role="user", content="An old question about crashes and much more besides that"
                ),
                ChatEntry(run_id=run_id, role="assistant", content="An old answer."),
            ]
        )
    sessions = client.get(f"/api/runs/{run_id}/chat/sessions").json()["sessions"]
    assert len(sessions) == 1 and sessions[0]["questions"] == 1
    assert sessions[0]["title"] == "An old question about crashes and much more besides that"
    turns = client.get(f"/api/runs/{run_id}/chat/sessions/{sessions[0]['id']}").json()["turns"]
    assert [t["text"] for t in turns] == ["An old question about crashes and much more besides that", "An old answer."]


def test_long_titles_are_shortened():
    from backend.api.chat import title_from

    title = title_from("Which of the onboarding problems hurt new users the most, and what should we fix first?")
    assert title.endswith("…") and len(title) <= 61 and "  " not in title


def test_bad_tool_arguments_are_reported_back_to_the_model(client):
    run_id = _finished_run(client)
    events = _events(_ask(client, run_id, _new_chat(client, run_id), "bad metric please"))
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["ok"] is False
    text = "".join(e["delta"] for e in events if e["type"] == "text")
    assert "Unknown measures" in text


def test_chat_errors_are_streamed_not_raised(client, provider_failure):
    from backend.providers import LLMError

    run_id = _finished_run(client)
    chat_id = _new_chat(client, run_id)
    provider_failure["error"] = LLMError("OpenAI rejected the API key.", fatal=True)
    events = _events(_ask(client, run_id, chat_id, "hi"))
    assert events[-1] == {"type": "error", "message": "OpenAI rejected the API key."}
    assert client.post("/api/runs/missing/chat/sessions").status_code == 404


def test_failed_answers_are_saved_and_left_out_when_retrying(client, provider_failure, llm_calls):
    from backend.providers import LLMError

    run_id = _finished_run(client)
    chat_id = _new_chat(client, run_id)
    provider_failure["error"] = LLMError("OpenAI rejected the API key.", fatal=True)
    _ask(client, run_id, chat_id, "What hurts most?")

    # After a reload the chat still says why there's no answer.
    turns = client.get(f"/api/runs/{run_id}/chat/sessions/{chat_id}").json()["turns"]
    assert turns[0]["text"] == "What hurts most?"
    assert turns[1]["error"] == "OpenAI rejected the API key." and turns[1]["text"] == ""

    # Retrying sends the model only the new question, not the failed one or the error.
    provider_failure.clear()
    _ask(client, run_id, chat_id, "What hurts most?")
    assert llm_calls["chat_history_sizes"][0] == 1


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


def test_long_tool_results_stay_valid_json():
    from backend.assistant.agent import fit_json

    big = {"items": [{"review_id": f"r{i}", "text": "word " * 200} for i in range(300)], "total": 300}
    text = fit_json(big, limit=12_000)
    data = json.loads(text)  # never cut mid-way
    assert len(text) <= 12_000 and data["total"] == 300 and "note" in data
    assert 1 <= len(data["items"]) <= 12 and data["items"][0]["review_id"] == "r0"
    assert fit_json({"a": 1}) == '{"a": 1}'


def test_reviews_are_recovered_from_results_cut_by_older_versions():
    from backend.api.chat import _reviews_in

    whole = json.dumps({"quotes": [{"review_id": "a", "text": "one"}, {"review_id": "b", "text": "two"}]})
    assert set(_reviews_in(whole[:-20])) == {"a"}  # "b" was cut off, "a" is complete
    assert set(_reviews_in(whole)) == {"a", "b"}
