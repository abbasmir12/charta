"""Chats: conversations saved as files the user owns, and follow-ups remember."""
from __future__ import annotations

import json
import re

from charta.core import chats


def test_new_chat_gets_a_readable_id_and_file(tmp_path):
    chat = chats.new_chat(tmp_path)
    assert re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", chat["id"])
    path = tmp_path / ".charta" / "chats" / f"{chat['id']}.json"
    assert path.exists()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["id"] == chat["id"] and on_disk["messages"] == []


def test_append_message_records_turns_and_titles_from_the_first_question(tmp_path):
    cid = chats.new_id()
    chats.append_message(tmp_path, cid, "What bills are here?", "Electricity, March.")
    chats.append_message(tmp_path, cid, "And June?", "None found.")
    chat = chats.load(tmp_path, cid)
    assert chat["title"].startswith("What bills are here?")
    assert [m["q"] for m in chat["messages"]] == ["What bills are here?", "And June?"]
    assert chat["messages"][0]["answer"] == "Electricity, March."


def test_history_for_sends_recent_turns_as_model_messages(tmp_path):
    cid = chats.new_id()
    for i in range(4):
        chats.append_message(tmp_path, cid, f"question {i}", f"answer {i}")
    history = chats.history_for(tmp_path, cid)
    # only the most recent turns come back, oldest first, as a conversation
    assert history[-1] == {"role": "assistant", "content": "answer 3"}
    assert history[-2] == {"role": "user", "content": "question 3"}
    assert all(h["role"] in ("user", "assistant") for h in history)


def test_history_is_never_loaded_from_a_broken_or_foreign_id(tmp_path):
    assert chats.load(tmp_path, "../escape") is None  # path traversal refused
    assert chats.history_for(tmp_path, "nope") == []


def test_list_chats_is_newest_first_with_count_and_title(tmp_path):
    first = chats.new_chat(tmp_path)
    chats.append_message(tmp_path, first["id"], "first chat question", "ok")
    second = chats.new_chat(tmp_path)
    chats.append_message(tmp_path, second["id"], "second chat question", "ok")
    listed = chats.list_chats(tmp_path)
    assert [c["id"] for c in listed] == [second["id"], first["id"]]
    titles = [c["title"] for c in listed]
    assert titles[0].startswith("second chat") and titles[1].startswith("first chat")
    assert all(c["count"] == 1 for c in listed)
