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
    assert "no text in the index" in run_tool("read_file", {"path": "nope.txt"}, folder)


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


def test_reading_an_unknown_file_says_so_and_points_elsewhere(tmp_path):
    """A path that is not indexed must not return empty text: the model is
    told why, so it stops guessing and uses search_index or the catalogue."""
    folder = _folder(tmp_path)
    out = run_tool("read_file", {"path": "photo.png"}, folder)
    assert "no text in the index" in out
    assert "search_index" in out


def test_a_question_with_no_match_names_what_the_folder_has(tmp_path, fake_provider):
    """'hi' matches nothing, but the folder still lists what it contains."""
    from charta.core.ask import answer_query

    folder = _folder(tmp_path)
    from charta.core.ask import _doc
    index = [_doc("sponsorship_2026.txt", 1, "x")]
    empty = answer_query("hi", [], LLMClient(_cfg(fake_provider)))
    assert "no indexed files" in empty.text
    miss = answer_query("hi", index, LLMClient(_cfg(fake_provider)))
    assert "hi" in miss.text
    assert "sponsorship_2026.txt" in miss.text


def test_renames_and_gaps_are_split_from_the_answer():
    """Textarea answer, Review proposals, Gap notes — never prose."""
    from charta.core.agent import parse_ai_lines

    text = ("Answer, with **facts**.\nRENAME: read me.txt -> "
            "2026-03 report.txt\nMOVE: scan.pdf -> Bills 2026/\n"
            "GAP: no invoice for June")
    clean, gaps, props = parse_ai_lines(text)
    assert "**facts**" in clean
    assert "read me" not in clean
    assert gaps == ["no invoice for June"]
    rename = next(p for p in props if p.source.startswith("read"))
    assert rename.dest_dir == "" and rename.new_name.endswith("report.txt")
    assert rename.origin == "llm"
    move = next(p for p in props if p.source.startswith("scan"))
    assert move.dest_dir == "Bills 2026/"
    assert move.new_name == "scan.pdf"


def test_a_gapped_answer_still_clean():
    from charta.core.agent import parse_ai_lines

    clean, gaps, props = parse_ai_lines("FINAL: plain answer, no organisation lines")
    assert clean == "plain answer, no organisation lines"
    assert not gaps and not props


def test_the_answer_protocol_validates_blocks_and_never_leaks_hashes():
    """The FINAL line is strict blocks JSON: validated, cleaned, and any
    markdown the model added inside block text is stripped."""
    import json as j

    from charta.core.agent import structured_answer

    payload = j.dumps({"blocks": [
        {"type": "heading", "level": 1, "text": "### Rent overview"},
        {"type": "facts", "entries": [{"label": "Total", "value": "900 EUR"}]},
        {"type": "table", "columns": ["Month", "Paid"],
         "rows": [["2026-03", "900 EUR"]]},
        {"type": "list", "items": ["### bullet one"]},
        {"type": "p", "text": "See [rent.txt p1]."},
    ]})
    text = f"FINAL: {payload}\nGAP: no June receipt"
    clean, blocks, gaps, props = structured_answer(text)
    assert [b["type"] for b in blocks] == ["heading", "facts", "table", "list", "p"]
    assert blocks[0]["text"] == "Rent overview"
    assert blocks[3]["items"] == ["bullet one"]
    assert "###" not in j.dumps(blocks)
    assert gaps == ["no June receipt"] and not props
    # the plain text keeps citations for the citation detector
    assert "[rent.txt p1]" in clean


def test_a_protocol_miss_degrades_to_clean_blocks_not_raw_markdown():
    """Even a completely off-protocol answer renders safely: no literal
    hashes, tables or pipes can leak into a heading again."""
    from charta.core.agent import structured_answer

    clean, blocks, _, _ = structured_answer(
        "FINAL: ### oops\n## not json at all")
    assert all(b["type"] == "p" for b in blocks)
    assert "###" not in clean and "##" not in clean
