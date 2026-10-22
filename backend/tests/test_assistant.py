"""AI assistant: the tool loop with a fake Claude client (no network), every tool against real data, and
the not-configured path."""

import json
from types import SimpleNamespace

import pytest

from app.config import settings
from app.services import assistant_service
from tests.test_goods_receipts import approved_order, world  # noqa: F401


class FakeClient:
    """Answers with scripted responses and records what it was sent."""

    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})  # a snapshot of this call
        return self.script.pop(0)


def tool_use(name, args, id="t1"):
    return SimpleNamespace(stop_reason="tool_use", content=[
        SimpleNamespace(type="text", text="Let me check."),
        SimpleNamespace(type="tool_use", id=id, name=name, input=args)])


def final(text):
    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])


def test_tool_loop_reads_live_data_and_returns_the_answer(db, world):
    client = FakeClient([tool_use("search_batches", {"query": "EXIST"}), final("EXIST has 5 sheets available.")])
    out = assistant_service.ask(db, "How much AH36 plate is available?", [], client=client)
    assert out["answer"] == "EXIST has 5 sheets available."
    assert out["tools_used"] == [{"tool": "search_batches", "input": {"query": "EXIST"}}]
    sent_back = client.calls[1]["messages"][-1]["content"][0]
    assert sent_back["type"] == "tool_result" and sent_back["tool_use_id"] == "t1"
    batches = json.loads(sent_back["content"])["batches"]
    assert [(b["id"], b["available"], b["unit"]) for b in batches] == [("EXIST", 5, "sheets")]
    assert client.calls[0]["system"].startswith("You are the assistant") and len(client.calls[0]["tools"]) == len(assistant_service.TOOLS)


def test_history_is_passed_and_bad_tool_input_is_reported_not_raised(db, world):
    client = FakeClient([tool_use("search_batches", {"status": "Nonsense"}), final("No such status.")])
    out = assistant_service.ask(db, "and now?", [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}], client=client)
    assert [m["role"] for m in client.calls[0]["messages"]] == ["user", "assistant", "user"]
    assert "error" in json.loads(client.calls[1]["messages"][-1]["content"][0]["content"])
    assert out["answer"] == "No such status."


def test_runaway_tool_use_stops(db, world):
    client = FakeClient([tool_use("stock_summary", {}, id=f"t{i}") for i in range(assistant_service.MAX_ROUNDS)])
    assert "too many lookups" in assistant_service.ask(db, "loop", [], client=client)["answer"]


@pytest.mark.parametrize("name, args", [
    ("search_batches", {"status": "Healthy", "yard": "Y1"}), ("batch_history", {"batch_id": "EXIST"}),
    ("stock_summary", {}), ("list_transfers", {"status": "Requested"}), ("list_purchase_orders", {"overdue": True}),
    ("list_inspections", {}), ("audit_events", {"source": "purchase_order"}), ("analytics", {}), ("suppliers", {"search": "Sup"}),
])
def test_every_tool_runs_against_real_data(client, db, world, name, args):
    approved_order(client)
    result = assistant_service.run_tool(db, name, args)
    json.dumps(result, default=assistant_service._plain)  # serialisable for the model
    assert "error" not in result


def test_endpoint_without_a_key(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert client.get("/api/v1/assistant/status").json()["data"]["enabled"] is False
    r = client.post("/api/v1/assistant/ask", json={"question": "hello"})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_endpoint_reports_ai_failures_as_502(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    def boom(*a, **k):
        raise ConnectionError("down")
    monkeypatch.setattr(assistant_service, "ask", boom)
    r = client.post("/api/v1/assistant/ask", json={"question": "hello"})
    assert r.status_code == 502 and "ConnectionError" in r.json()["detail"]
