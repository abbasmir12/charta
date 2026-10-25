"""Observability: opt-in Sentry Agent Tracing, doing nothing until asked.

Two families of tests:
  * without the SDK (or without a DSN) every helper must be a silent no-op —
    `pytest -q` runs these on every machine, since Charta must never grow a
    hard dependency for an optional feature;
  * with a fake ``_sentry`` module patched in, the spans must carry the
    GenAI attribute names Agent Tracing expects (ops, tool names, usage).
"""
from __future__ import annotations

import json

import pytest

from charta.core import observability as obs


# -- no-op when the SDK is absent or nothing was configured -------------------


def test_importing_the_module_costs_nothing_even_without_the_sdk():
    """Charta runs on machines without sentry-sdk — clean import, no-op."""
    import charta.core.agent  # touches observability at import time
    import charta.core.llm

    assert True


def test_without_a_dsn_nothing_is_alive_and_nothing_raises():
    assert obs.enabled() is False
    obs.init(type("Cfg", (), {"sentry_dsn": "", "sentry_record_inputs": False}))
    span = obs.agent_run("what is here?")
    span.set("gen_ai.usage.input_tokens", 5)
    obs.finish_agent(span, "an answer")
    obs.finish_model(span, {"usage": {"prompt_tokens": 2}}, "m")
    obs.finish_tool(span, "result", ok=False)
    obs.tool_call("search_index", {"q": "x"}, "desc").end()
    obs.set_conversation("abc")
    obs.clear_conversation()
    obs.shutdown()
    assert obs.enabled() is False


def test_a_span_set_alone_still_records_its_attribute_for_the_fake_tests():
    s = obs.Span()
    assert s.set("gen_ai.agent.name", obs.AGENT_NAME) is s
    assert s.attrs["gen_ai.agent.name"] == obs.AGENT_NAME
    s.end()  # ending a never-started span is a no-op


# -- with a fake SDK: the span shape Sentry's Agent Tracing understands -------


class FakeSpan:
    def __init__(self, log: list, op: str, name: str) -> None:
        self.log = log
        self.op = op
        self.name = name
        self.attrs: dict = {}
        self.status = ""
        log.append(self)

    def set_attribute(self, key: str, value: object) -> None:
        self.attrs[key] = value

    def set_status(self, status: str) -> None:
        self.status = status


class FakeSentry:
    def __init__(self) -> None:
        self.init_calls: list[dict] = []
        self.spans: list[FakeSpan] = []

    def init(self, **kwargs) -> None:
        self.init_calls.append(kwargs)

    def start_span(self, op: str, name: str = "") -> FakeSpan:
        return FakeSpan(self.spans, op, name)

    def flush(self, timeout: float = 0) -> None:
        pass

    class _AI:
        @staticmethod
        def set_conversation_id(cid: str) -> None:
            pass

        @staticmethod
        def remove_conversation_id() -> None:
            pass

    ai = _AI()


@pytest.fixture()
def fake_sentry(monkeypatch: pytest.MonkeyPatch) -> FakeSentry:
    fake = FakeSentry()
    monkeypatch.setattr(obs, "_sentry", fake, raising=False)
    yield fake
    obs.shutdown()  # put the module in its silent state again


def _alive_cfg(**kw: object):  # noqa: ANN202 - small local cfg stub
    base = {"sentry_dsn": "https://key@o1.ingest.sentry.io/2",
            "sentry_record_inputs": False, "sentry_record_outputs": False,
            "sentry_sample_rate": 1.0}
    base.update(kw)
    return type("Cfg", (), base)


def test_init_only_becomes_alive_with_a_dsn(fake_sentry: FakeSentry):
    assert obs.init(_alive_cfg(sentry_dsn="")) is False
    assert obs.init(_alive_cfg()) is True
    assert fake_sentry.init_calls == [{  # privacy defaults reach the SDK untouched
        "dsn": "https://key@o1.ingest.sentry.io/2",
        "traces_sample_rate": 1.0,
        "data_collection": {"gen_ai": {"inputs": False, "outputs": False}}},
    ]
    assert obs.enabled() is True
    assert obs.shutdown() is None
    assert obs.enabled() is False


def test_the_agent_span_carries_the_agent_attributes(fake_sentry: FakeSentry):
    obs.init(_alive_cfg())
    span = obs.agent_run("what did I spend on electricity?")
    span.end()
    [agent] = fake_sentry.spans
    assert agent.op == "gen_ai.invoke_agent"
    assert agent.name == f"invoke_agent {obs.AGENT_NAME}"
    assert agent.attrs["gen_ai.agent.name"] == obs.AGENT_NAME
    assert agent.attrs["gen_ai.operation.name"] == "invoke_agent"
    # prompts are not collected by default
    assert "gen_ai.input.messages" not in agent.attrs


def test_model_spans_carry_usage_tokens_and_finish_reason(fake_sentry: FakeSentry):
    obs.init(_alive_cfg())
    span = obs.model_call("gemma4:e4b", provider="ollama",
                          messages=[{"role": "user", "content": "hi"}])
    obs.finish_model(span, {
        "id": "cmpl-1", "model": "gemma4:e4b",
        "usage": {"prompt_tokens": 120, "completion_tokens": 30,
                  "total_tokens": 150},
        "choices": [{"finish_reason": "stop"}],
    }, "gemma4:e4b", text="the answer", ok=True)
    [chat] = fake_sentry.spans
    assert chat.op == "gen_ai.chat"
    assert chat.name == "chat gemma4:e4b"
    assert chat.attrs["gen_ai.request.model"] == "gemma4:e4b"
    assert chat.attrs["gen_ai.provider.name"] == "ollama"
    assert chat.attrs["gen_ai.response.model"] == "gemma4:e4b"
    assert chat.attrs["gen_ai.response.id"] == "cmpl-1"
    assert json.loads(chat.attrs["gen_ai.response.finish_reasons"]) == ["stop"]
    assert chat.attrs["gen_ai.usage.input_tokens"] == 120
    assert chat.attrs["gen_ai.usage.output_tokens"] == 30
    assert chat.attrs["gen_ai.usage.total_tokens"] == 150
    assert "gen_ai.input.messages" not in chat.attrs, "prompts stay local by default"
    assert "gen_ai.output.messages" not in chat.attrs, "answers stay local by default"


def test_prompts_and_answers_are_only_collected_when_opted_in(
        fake_sentry: FakeSentry):
    obs.init(_alive_cfg(sentry_record_inputs=True, sentry_record_outputs=True))
    span = obs.model_call("m", messages=[{"role": "user", "content": "hi"}])
    obs.finish_model(span, {}, "m", text="an answer", ok=True)
    [chat] = fake_sentry.spans
    assert json.loads(chat.attrs["gen_ai.input.messages"]) == [
        {"role": "user", "content": "hi"}]
    assert json.loads(chat.attrs["gen_ai.output.messages"]) == [
        {"role": "assistant", "content": "an answer"}]


def test_tool_spans_carry_the_tool_name_and_can_mark_a_failure(
        fake_sentry: FakeSentry):
    obs.init(_alive_cfg())
    span = obs.tool_call("search_index", {"q": "electricity"},
                         "Search this folder's metadata index.")
    obs.finish_tool(span, "search_index('electricity') → 2 match(es)")
    [tool] = fake_sentry.spans
    assert tool.op == "gen_ai.execute_tool"
    assert tool.name == "execute_tool search_index"
    assert tool.attrs["gen_ai.tool.name"] == "search_index"
    assert json.loads(tool.attrs["gen_ai.tool.call.arguments"]) == {
        "q": "electricity"}
    assert tool.attrs["gen_ai.tool.call.result"].startswith("search_index(")

    failing = obs.tool_call("nope", {})
    obs.finish_tool(failing, "Unknown tool 'nope'.", ok=False)
    bad = fake_sentry.spans[-1]
    assert bad.name == "execute_tool nope" and bad.status == "internal_error"
    assert bad.attrs.get("error.type") == "tool_error"


# -- the real agent loop under a fake client ----------------------------------


class _FakeClient:
    """The two-round script: call a tool, then give a FINAL blocks answer."""

    def __init__(self) -> None:
        self.n = 0

    def chat(self, messages: list[dict], system: str = ""):
        from charta.core.llm import LLMResult
        self.n += 1
        if self.n == 1:
            return LLMResult(ok=True, text='{"tool":"search_index","args":{"q":"x"}}')
        return LLMResult(ok=True, text=(
            'FINAL: {"blocks":[{"type":"p","text":"Nothing here."}]}'))


def test_a_full_ask_run_produces_agent_and_tool_spans(
        fake_sentry: FakeSentry, tmp_path):
    obs.init(_alive_cfg())
    from charta.core.agent import ask_with_tools

    result = ask_with_tools("anything here?", tmp_path, _FakeClient())
    assert result.answer
    ops = [s.op for s in fake_sentry.spans]
    assert "gen_ai.invoke_agent" in ops
    assert "gen_ai.execute_tool" in ops
    tool = next(s for s in fake_sentry.spans if s.op == "gen_ai.execute_tool")
    assert tool.attrs["gen_ai.tool.name"] == "search_index"


def test_a_full_ask_run_is_silent_without_tracing(tmp_path, monkeypatch):
    """No SDK alive: exactly today's behaviour, no error, no crash."""
    assert obs.enabled() is False
    from charta.core.agent import ask_with_tools

    result = ask_with_tools("anything here?", tmp_path, _FakeClient())
    assert result.answer and result.used_tools
