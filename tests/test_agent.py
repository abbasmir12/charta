"""The agent: the model calls the folder's tools, then answers.

The fake provider plays a model that reads a tool call out of the prompt, so
the whole loop (call -> run -> feed back -> answer) is exercised without a
real model.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from charta.core import index_db
from charta.core.agent import (_json_action, ask_with_tools, catalogue, run_tool)
from charta.core.charter import preset_charter
from charta.core.config import AppConfig
from charta.core.llm import LLMClient
from charta.core.pipeline import process_new_file


def _cfg(fake) -> AppConfig:
    return AppConfig(llm_provider="custom", llm_base_url=fake.base_url,
                     llm_api_key="test-key", generation_model="fake-model",
                     llm_timeout=5, llm_retries=1)


def _folder(tmp_path) -> pathlib.Path:
    folder = tmp_path / "receipts"
    folder.mkdir()
    (folder / "sponsorship_2026.txt").write_text(
        "Sponsorship agreement 2026 with Acme Corp. Amount: 5000 EUR Date: 2026-02-10",
        encoding="utf-8")
    (folder / "receipt_edf_2026-03-14.txt").write_text(
        "receipt from EDF date: 2026-03-14 total: 87.40 category: electricity",
        encoding="utf-8")
    charter = preset_charter("freelancer")
    for path in sorted(folder.iterdir()):
        process_new_file(folder, path, charter)
    return folder


def test_the_catalogue_lists_the_files_with_their_metadata(tmp_path):
    folder = _folder(tmp_path)
    text = catalogue(folder)
    assert "sponsorship_2026.txt" in text
    assert "receipt" in text and "edf" in text
    assert "2026-03-14" in text


def test_a_tool_call_is_read_out_of_the_models_reply(tmp_path):
    assert _json_action('{"tool":"search_index","args":{"q":"edf"}}') == \
        ("search_index", {"q": "edf"})
    assert _json_action("Here is my answer, no tool needed.") is None


def test_the_search_tool_finds_files_by_metadata(tmp_path):
    folder = _folder(tmp_path)
    out = run_tool("search_index", {"q": "sponsorship"}, folder)
    assert "sponsorship_2026.txt" in out
    out = run_tool("search_index", {"q": "electricity"}, folder)
    assert "receipt_edf_2026-03-14.txt" in out
    assert "no match" in run_tool("search_index", {"q": "zzzz"}, folder)


def test_the_read_tool_returns_the_stored_text(tmp_path):
    folder = _folder(tmp_path)
    out = run_tool("read_file", {"path": "sponsorship_2026.txt"}, folder)
    assert "5000 EUR" in out
    assert "not in the index" in run_tool("read_file", {"path": "nope.txt"}, folder)


def test_the_model_can_call_a_tool_and_then_answer(fake_provider, tmp_path):
    folder = _folder(tmp_path)
    calls: list[str] = []

    def reply(payload):
        # Play a model: first it searches, then it answers.
        if not calls:
            calls.append("search")
            return json.dumps({"tool": "search_index", "args": {"q": "sponsorship"}})
        calls.append("read")
        if len(calls) == 2:
            return json.dumps({"tool": "read_file", "args": {"path": "sponsorship_2026.txt"}})
        return "The 2026 sponsorship with Acme Corp is 5000 EUR [sponsorship_2026.txt p1]\nFINAL: 5000 EUR"

    fake_provider.reply = reply
    steps: list[dict] = []
    result = ask_with_tools("what is the 2026 sponsorship?", folder,
                             LLMClient(_cfg(fake_provider)), steps=steps)
    assert result.used_tools is True
    assert [c.name for c in result.calls] == ["search_index", "read_file"]
    assert "5000" in result.answer
    assert result.files == ["sponsorship_2026.txt"]
    assert result.citations and result.citations[0].file == "sponsorship_2026.txt"
    # The UI can show every step, including the tool calls.
    assert any(s["kind"] == "tool" for s in steps)


def test_a_model_that_never_calls_a_tool_still_answers(fake_provider, tmp_path):
    folder = _folder(tmp_path)
    fake_provider.reply = lambda payload: "It is 5000 EUR.\nFINAL: 5000 EUR"
    result = ask_with_tools("what is the 2026 sponsorship?", folder,
                             LLMClient(_cfg(fake_provider)))
    assert result.used_tools is False
    assert "5000" in result.answer


def test_a_tool_call_in_a_final_answer_is_stripped():
    from charta.core.agent import strip_tool_calls

    assert strip_tool_calls('{"tool":"search_index","args":{"q":"x"}}') == ""
    assert strip_tool_calls('Here you go\n{"tool":"read_file","args":{"path":"a.txt"}}') == "Here you go"
    assert strip_tool_calls("A normal answer.") == "A normal answer."


def test_a_model_that_only_calls_tools_still_ends_with_an_answer(fake_provider, tmp_path):
    """A model stuck in a tool loop must not leave the user without an answer."""
    folder = _folder(tmp_path)
    fake_provider.reply = lambda payload: json.dumps(
        {"tool": "search_index", "args": {"q": "sponsorship"}})
    result = ask_with_tools("what is the 2026 sponsorship?", folder,
                             LLMClient(_cfg(fake_provider)))
    # The loop ends with a request for the final answer; the raw tool call is
    # never handed to the user as an answer.
    assert not result.answer.strip().startswith("{")
