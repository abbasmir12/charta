"""Opt-in agent tracing: Sentry Agent Tracing for Charta's ask agent.

Charta is local-first and zero-telemetry by default. This module is the one
deliberate window outward, and only when the user asks for it: if (and only
if) a Sentry DSN is configured in ``[observability]`` of config.toml (or the
``CHARTA_SENTRY_DSN`` environment variable), the agent's work — every model
call, every tool call, token usage, latency, failures — is traced to *the
user's own* Sentry project, so they can see exactly how an answer was made.

Two hard rules, deliberate:
  * Prompt and answer text is OFF by default (``record_inputs`` /
    ``record_outputs`` in config). Latency, tokens, tool names and model
    names are always safe to send; file contents and questions are not.
  * Without a DSN, or with the optional ``sentry-sdk`` package not installed,
    every helper here is a complete no-op: the import is guarded and the
    handles below do nothing. Charta never grows a hard dependency for an
    optional feature.

Span layout (moments Sentry's Agent Tracing understands):
    gen_ai.invoke_agent   the whole ask run            ("invoke_agent charta-ask")
    └─ gen_ai.chat        one call to the model         ("chat gemma4:e4b")
    └─ gen_ai.execute_tool  one tool the agent ran       ("execute_tool search_index")
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

AGENT_NAME = "charta-ask"

# The optional SDK is imported lazily and guarded — absent is a normal state.
try:  # pragma: no cover - exercised by the "no-op without the SDK" tests
    import sentry_sdk as _sentry
except Exception:  # noqa: BLE001 — ImportError or a broken install
    _sentry = None

_ALIVE = False  # set by init() once a DSN is actually configured
_RECORD_IN = False  # collect question/prompt text (user's explicit choice)
_RECORD_OUT = False  # collect answer text (user's explicit choice)


def enabled() -> bool:
    """True when tracing is actually running (SDK present *and* configured)."""
    return bool(_sentry is not None and _ALIVE)


def init(cfg) -> bool:
    """Turn tracing on if the config carries a DSN. Returns whether it is on.

    Called once when the backend starts. Prompt/answer text is only collected
    when the user flips ``record_inputs`` / ``record_outputs`` — never because
    of a default somewhere.
    """
    global _ALIVE, _RECORD_IN, _RECORD_OUT
    _ALIVE, _RECORD_IN, _RECORD_OUT = False, False, False
    dsn = (getattr(cfg, "sentry_dsn", "") or "").strip()
    if not dsn or _sentry is None:
        return False
    _RECORD_IN = bool(getattr(cfg, "sentry_record_inputs", False))
    _RECORD_OUT = bool(getattr(cfg, "sentry_record_outputs", False))
    try:
        _sentry.init(
            dsn=dsn,
            traces_sample_rate=float(getattr(cfg, "sentry_sample_rate", 1.0) or 1.0),
            data_collection={"gen_ai": {"inputs": _RECORD_IN,
                                        "outputs": _RECORD_OUT}},
        )
        _ALIVE = True
    except Exception:  # noqa: BLE001 — a bad DSN must never break startup
        _ALIVE = False
    return _ALIVE


def shutdown() -> None:
    """Flush and forget (the backend calls this on exit when it can)."""
    global _ALIVE, _RECORD_IN, _RECORD_OUT
    if enabled():
        try:
            _sentry.flush(timeout=2)
        except Exception:  # noqa: BLE001
            pass
    _ALIVE, _RECORD_IN, _RECORD_OUT = False, False, False


# -- conversations ----------------------------------------------------------


def set_conversation(chat_id: str) -> None:
    """Group the trace under the folder's chat id (Sentry Conversations)."""
    if enabled():
        try:
            _sentry.ai.set_conversation_id(chat_id)
        except Exception:  # noqa: BLE001 — older SDKs: simply not traced
            pass


def clear_conversation() -> None:
    """Detach the chat id once the ask run is over."""
    if enabled():
        try:
            _sentry.ai.remove_conversation_id()
        except Exception:  # noqa: BLE001
            pass


# -- handles ----------------------------------------------------------------


@dataclass
class Span:
    """A started span (or a silent one when tracing is off).

    ``set`` adds a GenAI attribute; ``end`` closes it. Both are always safe
    to call, enabled or not — the agents above never branch on ``enabled()``.
    """

    inner: object | None = None
    attrs: dict = field(default_factory=dict)

    def set(self, key: str, value: object) -> "Span":
        if self.inner is not None:
            try:
                self.inner.set_attribute(key, value)
            except Exception:  # noqa: BLE001 — older SDK: set_data instead
                try:
                    self.inner.set_data(key, value)
                except Exception:  # noqa: BLE001
                    pass
        self.attrs[key] = value
        return self

    def end(self) -> None:
        if self.inner is not None:
            try:
                self.inner.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self.inner = None


def _start(op: str, name: str, agent: bool = True) -> Span:
    if not enabled():
        return Span()
    try:
        inner = _sentry.start_span(op=op, name=name)
        if agent:
            inner.set_attribute("gen_ai.agent.name", AGENT_NAME)
        return Span(inner=inner)
    except Exception:  # noqa: BLE001 — tracing must never break the ask
        return Span()


def _flat_messages(messages: list[dict] | None) -> list[dict]:
    """OpenAI-style messages → Sentry's legacy ``{role, content}`` shape."""
    out: list[dict] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        content = m.get("content", "")
        if isinstance(content, list):  # vision-style parts → the text only
            content = " ".join(str(p.get("text", "")) for p in content
                               if isinstance(p, dict))
        out.append({"role": str(m.get("role", "user")), "content": str(content)})
    return out


# -- the three moment types -------------------------------------------------


def agent_run(question: str) -> Span:
    """The whole ask run: ``gen_ai.invoke_agent`` wrapping everything below."""
    span = _start("gen_ai.invoke_agent", f"invoke_agent {AGENT_NAME}")
    span.set("gen_ai.operation.name", "invoke_agent")
    if _RECORD_IN:
        span.set("gen_ai.input.messages", json.dumps(
            [{"role": "user", "content": question}]))
    return span


def finish_agent(span: Span, answer: str) -> None:
    """Close the agent span with the final answer (text only when opted in)."""
    if _RECORD_OUT:
        span.set("gen_ai.output.messages", json.dumps(
            [{"role": "assistant", "content": answer}]))
    span.end()


def model_call(model: str, provider: str = "",
               messages: list[dict] | None = None) -> Span:
    """One call to an OpenAI-compatible endpoint: ``gen_ai.chat``."""
    span = _start("gen_ai.chat", f"chat {model}")
    span.set("gen_ai.operation.name", "chat")
    span.set("gen_ai.request.model", model)
    if provider:
        span.set("gen_ai.provider.name", provider)
    if _RECORD_IN and messages:
        span.set("gen_ai.input.messages", json.dumps(_flat_messages(messages)))
    return span


def finish_model(span: Span, resp: dict, model: str, text: str = "",
                 ok: bool = True) -> None:
    """Close a model span with response metadata and token usage.

    ``resp`` is the endpoint's OpenAI-compatible reply — ``usage``,
    ``choices[0].finish_reason``, ``id``, ``model`` — whatever it sent.
    Latency, tokens and model names are always collected; the answer text
    only when the user opted in.
    """
    if not resp and not ok:
        span.set("error.type", "provider_error")
    else:
        usage = resp.get("usage") if isinstance(resp, dict) else None
        if isinstance(usage, dict):
            span.set("gen_ai.usage.input_tokens", _int(usage.get("prompt_tokens")))
            span.set("gen_ai.usage.output_tokens", _int(usage.get("completion_tokens")))
            span.set("gen_ai.usage.total_tokens", _int(usage.get("total_tokens")))
            details = usage.get("prompt_tokens_details")
            cached = details.get("cached_tokens") if isinstance(details, dict) else None
            if cached:
                span.set("gen_ai.usage.cache_read.input_tokens", _int(cached))
        resp_model = resp.get("model") if isinstance(resp, dict) else None
        span.set("gen_ai.response.model", str(resp_model or model))
        if isinstance(resp, dict) and resp.get("id"):
            span.set("gen_ai.response.id", str(resp["id"]))
        if isinstance(resp, dict):
            try:
                finish = resp["choices"][0].get("finish_reason")
                if finish:
                    span.set("gen_ai.response.finish_reasons",
                             json.dumps([str(finish)]))
            except (KeyError, IndexError, TypeError):
                pass
        if ok and _RECORD_OUT:
            span.set("gen_ai.output.messages", json.dumps(
                [{"role": "assistant", "content": text}]))
    span.end()


def tool_call(name: str, args: dict | None = None, description: str = "") -> Span:
    """One tool the agent executed: ``gen_ai.execute_tool``."""
    span = _start("gen_ai.execute_tool", f"execute_tool {name}")
    span.set("gen_ai.operation.name", "execute_tool")
    span.set("gen_ai.tool.name", name)
    if description:
        span.set("gen_ai.tool.description", description)
    span.set("gen_ai.tool.call.arguments", json.dumps(args or {}))
    return span


def finish_tool(span: Span, result: str, ok: bool = True) -> None:
    """Close a tool span; a failed tool marks the span as an error."""
    span.set("gen_ai.tool.call.result", result[:2000] if isinstance(result, str)
             else json.dumps(result)[:2000])
    if not ok and span.inner is not None:
        try:
            span.inner.set_status("internal_error")
            span.set("error.type", "tool_error")
        except Exception:  # noqa: BLE001
            pass
    span.end()


def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
