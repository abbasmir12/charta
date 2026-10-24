"""Chats: Ask conversations persisted as files the user owns.

Each conversation lives at ``.charta/chats/<id>.json`` — human-readable,
renamable, deletable, like everything else Charta keeps. A follow-up
question sends the previous turns back to the model, so "and what about
June?" works exactly like a person continuing a conversation.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import uuid

_ID = re.compile(r"^[A-Za-z0-9-]+$")
MAX_HISTORY_TURNS = 6          # turns (user+assistant) sent back to the model
MAX_HISTORY_CHARS = 1600       # per-message cap: history briefs, not dumps


def _dir(folder: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(folder) / ".charta" / "chats"


def _path(folder: str | pathlib.Path, chat_id: str) -> pathlib.Path:
    if not _ID.fullmatch(chat_id or ""):
        raise ValueError("bad chat id")
    return _dir(folder) / f"{chat_id}.json"


def new_id() -> str:
    return (datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            + "-" + uuid.uuid4().hex[:4])


def save(folder: str | pathlib.Path, chat: dict) -> None:
    p = _path(folder, str(chat.get("id", "")))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(chat, indent=2), encoding="utf-8")


def new_chat(folder: str | pathlib.Path) -> dict:
    chat = {"id": new_id(),
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "title": "", "messages": []}
    save(folder, chat)
    return chat


def load(folder: str | pathlib.Path, chat_id: str) -> dict | None:
    try:
        p = _path(folder, chat_id)
    except ValueError:
        return None
    if not p.exists():
        return None
    try:
        chat = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — unreadable file is just no chat
        return None
    return chat if isinstance(chat, dict) and "id" in chat else None


def list_chats(folder: str | pathlib.Path, limit: int = 20) -> list[dict]:
    """Summaries for the chats strip: newest first."""
    root = _dir(folder)
    if not root.exists():
        return []
    out: list[dict] = []
    for p in root.glob("*.json"):
        try:
            chat = json.loads(p.read_text(encoding="utf-8"))
            msgs = chat.get("messages") or []
            out.append({"id": chat.get("id", p.stem),
                        "title": chat.get("title") or "(untitled)",
                        "count": len(msgs),
                        "updated": (msgs[-1] or {}).get("at", "")
                        if msgs else chat.get("created", "")})
        except Exception:  # noqa: BLE001 — one broken chat hides all
            continue
    out.sort(key=lambda c: c.get("updated") or "", reverse=True)
    return out[:limit]


def append_message(folder: str | pathlib.Path, chat_id: str, q: str,
                   answer: str, **extra: object) -> dict:
    """Record one question-and-answer turn; creates the chat when needed."""
    chat = load(folder, chat_id)
    if chat is None:
        chat = {"id": chat_id, "created": "", "title": "", "messages": []}
    chat["messages"] = chat.get("messages", [])
    chat["messages"].append({
        "q": q.strip(), "answer": answer,
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        **{k: v for k, v in extra.items() if v is not None},
    })
    save(folder, chat)
    return chat


def fallback_title(question: str) -> str:
    """The no-model title: the first line of the question, trimmed."""
    first = question.strip().splitlines()[0] if question.strip() else "New conversation"
    return first[:60].strip(" -—:,")


def set_title(folder: str | pathlib.Path, chat_id: str, title: str) -> bool:
    """Name a conversation once — later edits never overwrite a real title."""
    chat = load(folder, chat_id)
    if chat is None or chat.get("title"):
        return False
    title = (title or "").strip()
    if not title:
        return False
    chat["title"] = title[:60]
    save(folder, chat)
    return True


def ai_title(question: str, answer: str, client: object,
             timeout: float = 15.0) -> str | None:
    """Ask the model for a short conversation title from the first exchange.

    Strict JSON reply; one call (the client itself retries the transport),
    and a fallback is expected from the caller when this returns None.
    """
    system = ('You name folder conversations. Reply with strict JSON only: '
              '{"title": "2-6 word title"}. Keep the user\'s language, '
              'no quotes inside the title, no commentary.')
    prompt = (f"First question: {question[:300]}\n"
              f"Answer (excerpt): {answer[:500]}")
    try:
        res = client.chat([{"role": "user", "content": prompt}],
                          system=system, timeout=timeout)
    except Exception:  # noqa: BLE001 — naming must never break the answer
        return None
    if not getattr(res, "ok", False):
        return None
    match = re.search(r'"title"\s*:\s*"([^"]{1,80})"', getattr(res, "text", "") or "")
    return match.group(1).strip() if match else None


def rel_time(iso: str, now: datetime.datetime | None = None) -> str:
    """A short human age for the rail meta ('3 h ago', 'yesterday')."""
    if not iso:
        return ""
    try:
        stamp = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return ""
    now = now or datetime.datetime.now()
    seconds = (now - stamp).total_seconds()
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{max(1, int(seconds // 60))} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} h ago"
    if seconds < 172800:
        return "yesterday"
    if seconds < 2592000:
        return f"{int(seconds // 86400)} d ago"
    return stamp.strftime("%d %b")


def meta_line(count: int, updated: str) -> str:
    """The rail item's meta: '2 messages, 3 h ago'. No dots, no em dashes."""
    n = int(count or 0)
    noun = "message" if n == 1 else "messages"
    age = rel_time(updated)
    return f"{n} {noun}, {age}" if age else f"{n} {noun}"


def history_for(folder: str | pathlib.Path, chat_id: str,
                limit: int = MAX_HISTORY_TURNS) -> list[dict]:
    """The previous turns as model messages, newest-n first.

    Answers go back as plain text: the model must see what it said, in the
    compressed form the blocks renderer shows — not re-parse its own JSON.
    """
    chat = load(folder, chat_id)
    if chat is None:
        return []
    out: list[dict] = []
    for msg in (chat.get("messages") or [])[-limit:]:
        q = (msg.get("q") or "").strip()
        a = (msg.get("answer") or "").strip()
        if q:
            out.append({"role": "user", "content": q[:MAX_HISTORY_CHARS]})
        if a:
            out.append({"role": "assistant", "content": a[:MAX_HISTORY_CHARS]})
    return out
